import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import ResearchProvider, ScrapeResult
from app.models import Procurement, ResearchRun, ResearchSource, ResearchTask
from app.research.states import (
    RESEARCH_RUN_TRANSITIONS,
    ResearchRunStatus,
    ResearchTaskStatus,
    ResearchTaskType,
    validate_transition,
)


def build_search_query(procurement: Procurement) -> str:
    """
    Build a deterministic supplier-search query from the procurement
    and its requirements.
    """
    parts = [
        f"Find suppliers and products for: {procurement.title}.",
        procurement.description.strip(),
    ]

    if procurement.requirements:
        requirements = []

        for requirement in procurement.requirements:
            value = requirement.value or ""
            unit = requirement.unit or ""

            requirement_text = requirement.name

            if value:
                requirement_text += f": {value}"

            if unit:
                requirement_text += f" {unit}"

            if requirement.is_mandatory:
                requirement_text += " (mandatory)"

            requirements.append(requirement_text)

        parts.append(
            "Requirements: " + "; ".join(requirements) + "."
        )

    parts.append(
        "Prioritize reputable suppliers, current product information, "
        "pricing, availability, and relevant specifications."
    )

    return " ".join(parts)


# Providers are asked for this many results, and the returned list is
# cut to the same number before any source is stored or scraped.
# Anakin's search call sends a limit, but the adapter keeps every
# result the API returns, so the slice is the reliable bound.
SUPPLIER_SEARCH_SOURCE_CAP = 3

# Anakin URL Scraper jobs are pending, processing, completed, or failed.
# https://anakin.io/docs/api-reference/url-scraper/get-job-status
_SCRAPE_POLL_INTERVAL_SECONDS = 4
_SCRAPE_POLL_MAX_ATTEMPTS = 15
_SCRAPE_FAILURE_STATUSES = frozenset({"failed", "error"})


def _scrape_job_status(result: ScrapeResult) -> str:
    status = result.metadata.get("status")

    if status is None:
        return ""

    return str(status).strip().lower()


async def await_completed_scrape(
    provider: ResearchProvider,
    job_id: str,
) -> ScrapeResult:
    """
    Poll provider.get_scrape_job until Anakin reports a terminal status.

    completed returns immediately. failed and error raise. Any other
    status, including pending and processing, waits and is tried again
    until the attempt limit.
    """
    last_status = "unknown"

    for attempt in range(1, _SCRAPE_POLL_MAX_ATTEMPTS + 1):
        result = await provider.get_scrape_job(job_id)
        status = _scrape_job_status(result)

        if status == "completed":
            return result

        if status in _SCRAPE_FAILURE_STATUSES:
            detail = result.metadata.get("error")
            message = f"Scrape job failed ({status})"

            if detail:
                message = f"{message}: {detail}"

            raise RuntimeError(message)

        last_status = status or "unknown"

        if attempt < _SCRAPE_POLL_MAX_ATTEMPTS:
            await asyncio.sleep(_SCRAPE_POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        "Scrape job timed out after "
        f"{_SCRAPE_POLL_MAX_ATTEMPTS} attempts "
        f"(last status: {last_status})."
    )


def create_research_run(
    db: Session,
    procurement_id: UUID,
) -> ResearchRun:
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == procurement_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    run = ResearchRun(
        procurement_id=procurement_id,
        status="pending",
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    return run


async def execute_supplier_search(
    db: Session,
    run: ResearchRun,
    provider: ResearchProvider,
    *,
    max_results: int = SUPPLIER_SEARCH_SOURCE_CAP,
) -> list[ResearchSource]:
    """
    Execute the initial supplier search and persist the returned
    sources against the research run.
    """
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == run.procurement_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    if run.status == ResearchRunStatus.PENDING.value:
        validate_transition(
            run.status,
            ResearchRunStatus.PLANNING.value,
            RESEARCH_RUN_TRANSITIONS,
        )
        run.status = ResearchRunStatus.PLANNING.value
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

    validate_transition(
        run.status,
        ResearchRunStatus.EXECUTING.value,
        RESEARCH_RUN_TRANSITIONS,
    )
    run.status = ResearchRunStatus.EXECUTING.value

    query = build_search_query(procurement)
    source_limit = min(max_results, SUPPLIER_SEARCH_SOURCE_CAP)

    task = ResearchTask(
        research_run_id=run.id,
        task_type=ResearchTaskType.SEARCH_SUPPLIERS.value,
        status=ResearchTaskStatus.RUNNING.value,
        provider=getattr(provider, "name", None),
        input_data={
            "query": query,
            "max_results": source_limit,
        },
        started_at=datetime.now(timezone.utc),
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        results = await provider.search(
            query,
            max_results=source_limit,
        )
        results = list(results)[:source_limit]

        sources: list[ResearchSource] = []

        for result in results:
            source = ResearchSource(
                research_run_id=run.id,
                task_id=task.id,
                url=result.url,
                title=result.title or None,
                source_type="search",
                provider=getattr(provider, "name", None),
                external_reference=None,
                retrieved_at=datetime.now(timezone.utc),
                raw_content=result.snippet,
                metadata_json=result.metadata or None,
            )

            db.add(source)
            sources.append(source)

        task.status = ResearchTaskStatus.COMPLETED.value
        task.output_data = {
            "result_count": len(sources),
            "urls": [source.url for source in sources],
        }
        task.completed_at = datetime.now(timezone.utc)

        db.commit()

        for source in sources:
            db.refresh(source)

        return sources

    except Exception as exc:
        db.rollback()

        failed_task = db.get(ResearchTask, task.id)
        failed_run = db.get(ResearchRun, run.id)

        if failed_task is not None:
            failed_task.status = ResearchTaskStatus.FAILED.value
            failed_task.error = str(exc)
            failed_task.completed_at = datetime.now(timezone.utc)

        if failed_run is not None:
            validate_transition(
                failed_run.status,
                ResearchRunStatus.FAILED.value,
                RESEARCH_RUN_TRANSITIONS,
            )
            failed_run.status = ResearchRunStatus.FAILED.value
            failed_run.error = str(exc)
            failed_run.completed_at = datetime.now(timezone.utc)

        db.commit()

        raise


async def collect_source_content(
    db: Session,
    run: ResearchRun,
    provider: ResearchProvider,
    sources: list[ResearchSource],
) -> list[ResearchSource]:
    """
    Scrape discovered research sources and persist their content.

    Providers may return completed content immediately (as the mock provider
    does) or return an external asynchronous scraping job that must be polled.
    """
    if not sources:
        return []

    task = ResearchTask(
        research_run_id=run.id,
        task_type=ResearchTaskType.SCRAPE_SOURCE.value,
        status=ResearchTaskStatus.RUNNING.value,
        provider=getattr(provider, "name", None),
        input_data={
            "source_count": len(sources),
            "urls": [source.url for source in sources],
        },
        started_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        collected_sources: list[ResearchSource] = []

        for source in sources:
            scrape_result = await provider.scrape(source.url)

            job_id = scrape_result.metadata.get("job_id")

            if job_id and not scrape_result.content:
                task.external_job_id = job_id
                db.commit()

                scrape_result = await await_completed_scrape(
                    provider,
                    job_id,
                )

            source.title = scrape_result.title or source.title
            source.raw_content = scrape_result.content
            source.source_type = "scraped"

            existing_metadata = source.metadata_json or {}
            scrape_metadata = scrape_result.metadata or {}

            source.metadata_json = {
                **existing_metadata,
                **scrape_metadata,
            }

            collected_sources.append(source)

        task.status = ResearchTaskStatus.COMPLETED.value
        task.output_data = {
            "source_count": len(collected_sources),
            "urls": [source.url for source in collected_sources],
        }
        task.completed_at = datetime.now(timezone.utc)

        db.commit()

        for source in collected_sources:
            db.refresh(source)

        return collected_sources

    except Exception as exc:
        db.rollback()

        failed_task = db.get(ResearchTask, task.id)

        if failed_task is not None:
            failed_task.status = ResearchTaskStatus.FAILED.value
            failed_task.error = str(exc)
            failed_task.completed_at = datetime.now(timezone.utc)

        db.commit()
        raise
