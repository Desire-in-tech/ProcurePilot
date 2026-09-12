from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

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


async def start_research(
    db: Session,
    procurement_id: UUID,
    provider: ResearchProvider,
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

    return run, collected_sources
