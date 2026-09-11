from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import ResearchProvider
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
    max_results: int = 5,
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

    task = ResearchTask(
        research_run_id=run.id,
        task_type=ResearchTaskType.SEARCH_SUPPLIERS.value,
        status=ResearchTaskStatus.RUNNING.value,
        provider=getattr(provider, "name", None),
        input_data={
            "query": query,
            "max_results": max_results,
        },
        started_at=datetime.now(timezone.utc),
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        results = await provider.search(
            query,
            max_results=max_results,
        )

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

                scrape_result = await provider.get_scrape_job(job_id)

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
