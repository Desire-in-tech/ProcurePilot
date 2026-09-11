import uuid

import pytest

from app.ai.providers.base import SearchResult
from app.db.database import SessionLocal
from app.models import (
    Organization,
    Procurement,
    ResearchRun,
    ResearchSource,
    ResearchTask,
)
from app.services.research import (
    create_research_run,
    execute_supplier_search,
)


class SuccessfulProvider:
    name = "test-provider"

    async def search(self, query: str, *, max_results: int = 5):
        return [
            SearchResult(
                title="Supplier One",
                url="https://supplier-one.example",
                snippet="Laptop supplier with current pricing.",
                metadata={"country": "Uganda"},
            ),
            SearchResult(
                title="Supplier Two",
                url="https://supplier-two.example",
                snippet="Business laptop supplier.",
                metadata={"country": "Kenya"},
            ),
        ]


class FailingProvider:
    name = "failing-provider"

    async def search(self, query: str, *, max_results: int = 5):
        raise RuntimeError("Provider search failed")


def create_organization(db) -> Organization:
    organization = Organization(
        name="Research Test Organization",
        slug=f"research-{uuid.uuid4().hex[:12]}",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def create_procurement(
    db,
    organization_id,
) -> Procurement:
    procurement = Procurement(
        organization_id=organization_id,
        title="Business Laptops",
        description="Purchase laptops for the engineering team.",
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
async def test_create_research_run_starts_pending():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        run = create_research_run(
            db,
            procurement.id,
        )

        assert run.status == "pending"
        assert run.started_at is None

        persisted = db.get(ResearchRun, run.id)

        assert persisted is not None
        assert persisted.status == "pending"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_supplier_search_persists_sources_and_completes_task():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        run = create_research_run(
            db,
            procurement.id,
        )

        sources = await execute_supplier_search(
            db,
            run,
            SuccessfulProvider(),
            max_results=5,
        )

        assert len(sources) == 2

        persisted_run = db.get(ResearchRun, run.id)
        assert persisted_run is not None
        assert persisted_run.status == "executing"
        assert persisted_run.started_at is not None

        tasks = (
            db.query(ResearchTask)
            .filter(ResearchTask.research_run_id == run.id)
            .all()
        )

        assert len(tasks) == 1
        assert tasks[0].task_type == "search_suppliers"
        assert tasks[0].status == "completed"
        assert tasks[0].provider == "test-provider"
        assert tasks[0].output_data["result_count"] == 2

        persisted_sources = (
            db.query(ResearchSource)
            .filter(ResearchSource.research_run_id == run.id)
            .all()
        )

        assert len(persisted_sources) == 2
        assert {
            source.url for source in persisted_sources
        } == {
            "https://supplier-one.example",
            "https://supplier-two.example",
        }

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_supplier_search_failure_persists_failed_run_and_task():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        run = create_research_run(
            db,
            procurement.id,
        )

        with pytest.raises(RuntimeError, match="Provider search failed"):
            await execute_supplier_search(
                db,
                run,
                FailingProvider(),
            )

        persisted_run = db.get(ResearchRun, run.id)

        assert persisted_run is not None
        assert persisted_run.status == "failed"
        assert persisted_run.error == "Provider search failed"
        assert persisted_run.completed_at is not None

        tasks = (
            db.query(ResearchTask)
            .filter(ResearchTask.research_run_id == run.id)
            .all()
        )

        assert len(tasks) == 1
        assert tasks[0].status == "failed"
        assert tasks[0].error == "Provider search failed"
        assert tasks[0].completed_at is not None

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
