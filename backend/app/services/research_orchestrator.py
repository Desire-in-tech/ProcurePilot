from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.research_agent import OpenRouterResearchAgent
from app.ai.providers import ResearchProvider
from app.models import Procurement, ResearchRun
from app.research.states import (
    RESEARCH_RUN_TRANSITIONS,
    ResearchRunStatus,
    validate_transition,
)
from app.services.offer_extraction import extract_offers_from_sources
from app.services.offer_comparison import compare_offers
from app.services.recommendation import generate_recommendation
from app.services.requirement_verification import verify_offers
from app.services.research import (
    build_search_query,
    collect_source_content,
    create_research_run,
    execute_supplier_search,
)


ACTIVE_RUN_STATUSES = {
    ResearchRunStatus.PENDING.value,
    ResearchRunStatus.PLANNING.value,
    ResearchRunStatus.EXECUTING.value,
    ResearchRunStatus.EVALUATING.value,
}

_OPEN_RUN_STATUSES = {
    ResearchRunStatus.PLANNING.value,
    ResearchRunStatus.EXECUTING.value,
    ResearchRunStatus.EVALUATING.value,
}


def _fail_run_if_still_open(
    db: Session,
    run_id: UUID,
    exc: Exception,
) -> None:
    """
    Mark an in-progress run failed after a later stage raises.

    Search already stores failed itself. Do not transition again in
    that case. Roll back first so uncommitted stage writes are dropped.
    """
    db.rollback()

    failed_run = db.get(ResearchRun, run_id)

    if failed_run is None:
        return

    if failed_run.status not in _OPEN_RUN_STATUSES:
        return

    validate_transition(
        failed_run.status,
        ResearchRunStatus.FAILED.value,
        RESEARCH_RUN_TRANSITIONS,
    )
    failed_run.status = ResearchRunStatus.FAILED.value
    failed_run.error = str(exc)
    failed_run.completed_at = datetime.now(timezone.utc)
    db.commit()


def _complete_run(
    db: Session,
    run: ResearchRun,
) -> ResearchRun:
    validate_transition(
        run.status,
        ResearchRunStatus.EVALUATING.value,
        RESEARCH_RUN_TRANSITIONS,
    )
    run.status = ResearchRunStatus.EVALUATING.value

    validate_transition(
        run.status,
        ResearchRunStatus.COMPLETED.value,
        RESEARCH_RUN_TRANSITIONS,
    )
    run.status = ResearchRunStatus.COMPLETED.value
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)

    return run


async def start_research(
    db: Session,
    procurement_id: UUID,
    provider: ResearchProvider,
    research_agent: OpenRouterResearchAgent | None = None,
):
    """
    Start the autonomous research workflow for an approved procurement.

    This orchestration slice performs supplier discovery, source
    collection, offer extraction, requirement verification, deterministic
    offer comparison, and recommendation generation.
    """
    procurement = db.scalar(
        select(Procurement).where(Procurement.id == procurement_id)
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    if procurement.status != "approved":
        raise ValueError("Only approved procurements can start research")

    active_run = db.scalar(
        select(ResearchRun)
        .where(
            ResearchRun.procurement_id == procurement_id,
            ResearchRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(ResearchRun.created_at.desc())
    )

    if active_run is not None:
        raise ValueError("Procurement already has an active research run")

    run = create_research_run(db, procurement_id)

    validate_transition(
        run.status,
        ResearchRunStatus.PLANNING.value,
        RESEARCH_RUN_TRANSITIONS,
    )
    run.status = ResearchRunStatus.PLANNING.value
    db.commit()
    db.refresh(run)

    run_id = run.id

    try:
        if research_agent is None:
            sources = await execute_supplier_search(
                db,
                run,
                provider,
            )
            collected_sources = await collect_source_content(
                db,
                run,
                provider,
                sources,
            )
        else:
            sources = []
            scraped_source_ids: set[UUID] = set()

            async def search_suppliers(query: str) -> list[dict]:
                found = await execute_supplier_search(
                    db,
                    run,
                    provider,
                    query=query,
                )
                sources.extend(found)
                return [
                    {
                        "url": source.url,
                        "title": source.title,
                        "snippet": source.raw_content,
                    }
                    for source in found
                ]

            async def scrape_source(url: str) -> dict:
                source = next(
                    (source for source in sources if source.url == url),
                    None,
                )
                if source is None:
                    raise ValueError("Source is not part of this research run")

                await collect_source_content(
                    db,
                    run,
                    provider,
                    [source],
                )
                scraped_source_ids.add(source.id)
                return {
                    "url": source.url,
                    "title": source.title,
                    "content": source.raw_content,
                }

            await research_agent.research(
                build_search_query(procurement),
                search_suppliers=search_suppliers,
                scrape_source=scrape_source,
            )

            remaining_sources = [
                source
                for source in sources
                if source.id not in scraped_source_ids
            ]
            await collect_source_content(
                db,
                run,
                provider,
                remaining_sources,
            )
            collected_sources = sources

        await extract_offers_from_sources(
            db,
            run,
            provider,
            collected_sources,
        )

        await verify_offers(
            db,
            run,
        )

        comparisons = await compare_offers(
            db,
            run,
        )

        await generate_recommendation(
            db,
            run,
            comparisons,
        )

        return _complete_run(db, run), collected_sources
    except Exception as exc:
        _fail_run_if_still_open(db, run_id, exc)
        raise
