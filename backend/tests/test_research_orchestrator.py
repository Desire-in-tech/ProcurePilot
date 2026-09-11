import uuid

import pytest

from app.ai.providers import MockResearchProvider
from app.db.database import SessionLocal
from app.models import (
    Organization,
    Procurement,
    ResearchRun,
    ResearchSource,
    ResearchTask,
)
from app.services.research_orchestrator import start_research


def create_organization(db) -> Organization:
    organization = Organization(
        name="Research Orchestrator Test Organization",
        slug=f"orchestrator-{uuid.uuid4().hex[:12]}",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def create_procurement(
    db,
    organization_id,
    *,
    status: str = "approved",
) -> Procurement:
    procurement = Procurement(
        organization_id=organization_id,
        title="Business Laptops",
        description="Purchase laptops for the engineering team.",
        status=status,
    )
    db.add(procurement)
    db.commit()
    db.refresh(procurement)
    return procurement


def cleanup(db, organization_id) -> None:
    organization = db.get(Organization, organization_id)

    if organization is not None:
        db.delete(organization)

    db.commit()


@pytest.mark.asyncio
async def test_start_research_creates_run_and_sources():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(
            db,
            organization.id,
        )

        run, sources = await start_research(
            db,
            procurement.id,
            MockResearchProvider(),
        )

        assert run.procurement_id == procurement.id
        assert run.status == "executing"
        assert len(sources) > 0

        for source in sources:
            assert source.source_type == "scraped"
            assert source.raw_content == "Mock scraped content."

        persisted_run = db.get(ResearchRun, run.id)

        assert persisted_run is not None
        assert persisted_run.status == "executing"

        persisted_sources = (
            db.query(ResearchSource)
            .filter(ResearchSource.research_run_id == run.id)
            .all()
        )

        assert len(persisted_sources) == len(sources)
        assert all(
            source.source_type == "scraped"
            for source in persisted_sources
        )
        assert all(
            source.raw_content == "Mock scraped content."
            for source in persisted_sources
        )

        tasks = (
            db.query(ResearchTask)
            .filter(ResearchTask.research_run_id == run.id)
            .all()
        )

        scrape_tasks = [
            task
            for task in tasks
            if task.task_type == "scrape_source"
        ]

        assert len(scrape_tasks) == 1
        assert scrape_tasks[0].status == "completed"
        assert scrape_tasks[0].output_data["source_count"] == len(sources)

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_start_research_requires_approved_procurement():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = create_procurement(
            db,
            organization.id,
            status="review",
        )

        with pytest.raises(
            ValueError,
            match="Only approved procurements can start research",
        ):
            await start_research(
                db,
                procurement.id,
                MockResearchProvider(),
            )

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_start_research_prevents_duplicate_active_runs():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(
            db,
            organization.id,
        )

        first_run, _ = await start_research(
            db,
            procurement.id,
            MockResearchProvider(),
        )

        assert first_run.status == "executing"

        with pytest.raises(
            ValueError,
            match="Procurement already has an active research run",
        ):
            await start_research(
                db,
                procurement.id,
                MockResearchProvider(),
            )

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
