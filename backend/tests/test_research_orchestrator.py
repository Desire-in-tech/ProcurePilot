import uuid

import pytest

from app.ai.providers import MockResearchProvider, ScrapeResult, SearchResult
from app.db.database import SessionLocal
from app.models import (
    OfferEvidence,
    Organization,
    Procurement,
    ResearchRun,
    ResearchSource,
    ResearchTask,
    SupplierOffer,
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
        assert run.status == "completed"
        assert run.completed_at is not None
        assert len(sources) > 0

        for source in sources:
            assert source.source_type == "scraped"
            assert source.raw_content == "Mock scraped content."

        persisted_run = db.get(ResearchRun, run.id)

        assert persisted_run is not None
        assert persisted_run.status == "completed"
        assert persisted_run.completed_at is not None

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

        recommendation_tasks = [
            task
            for task in tasks
            if task.task_type == "generate_recommendation"
        ]

        assert len(recommendation_tasks) == 1
        assert recommendation_tasks[0].status == "completed"

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

        active_run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(active_run)
        db.commit()

        with pytest.raises(
            ValueError,
            match="Procurement already has an active research run",
        ):
            await start_research(
                db,
                procurement.id,
                MockResearchProvider(),
            )

        runs = (
            db.query(ResearchRun)
            .filter(ResearchRun.procurement_id == procurement.id)
            .all()
        )

        assert len(runs) == 1
        assert runs[0].id == active_run.id
        assert runs[0].status == "executing"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


class PendingScrapeProvider(MockResearchProvider):
    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ):
        return [
            SearchResult(
                title="Pending Supplier",
                url="https://example.com/pending",
                snippet="original search snippet",
            )
        ][:max_results]

    async def scrape(
        self,
        url: str,
        *,
        schema=None,
        use_browser: bool = False,
    ):
        return ScrapeResult(
            url=url,
            content=None,
            metadata={
                "job_id": "job-1",
                "status": "pending",
            },
        )

    async def get_scrape_job(
        self,
        external_job_id: str,
    ):
        return ScrapeResult(
            url="https://example.com/pending",
            content=None,
            structured_data=None,
            metadata={
                "status": "pending",
                "job_id": external_job_id,
            },
        )


class FailedScrapeStatusProvider(PendingScrapeProvider):
    async def get_scrape_job(
        self,
        external_job_id: str,
    ):
        return ScrapeResult(
            url="https://example.com/pending",
            content=None,
            structured_data=None,
            metadata={
                "status": "failed",
                "job_id": external_job_id,
            },
        )


class ExtractFailProvider(MockResearchProvider):
    async def scrape(
        self,
        url: str,
        *,
        schema=None,
        use_browser: bool = False,
    ):
        if schema is not None:
            raise RuntimeError("extract scrape failed")

        return await super().scrape(
            url,
            schema=schema,
            use_browser=use_browser,
        )


class SearchFailProvider(MockResearchProvider):
    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ):
        raise RuntimeError("Provider search failed")


def procurement_runs(db, procurement_id):
    return (
        db.query(ResearchRun)
        .filter(ResearchRun.procurement_id == procurement_id)
        .all()
    )


def assert_no_offers_or_evidence(db, procurement_id, run_id) -> None:
    offers = (
        db.query(SupplierOffer)
        .filter(SupplierOffer.procurement_id == procurement_id)
        .all()
    )
    evidence = (
        db.query(OfferEvidence)
        .join(ResearchSource)
        .filter(ResearchSource.research_run_id == run_id)
        .all()
    )

    assert offers == []
    assert evidence == []


@pytest.mark.asyncio
async def test_pending_scrape_does_not_store_an_empty_page_and_fails_the_run():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(RuntimeError, match="Scrape job is not completed"):
            await start_research(
                db,
                procurement.id,
                PendingScrapeProvider(),
            )

        failed_run = procurement_runs(db, procurement.id)[0]

        assert failed_run.status == "failed"
        assert failed_run.completed_at is not None
        assert failed_run.error == "Scrape job is not completed"

        source = (
            db.query(ResearchSource)
            .filter(ResearchSource.research_run_id == failed_run.id)
            .one()
        )

        assert source.raw_content == "original search snippet"
        assert source.source_type == "search"

        scrape_task = (
            db.query(ResearchTask)
            .filter(
                ResearchTask.research_run_id == failed_run.id,
                ResearchTask.task_type == "scrape_source",
            )
            .one()
        )

        assert scrape_task.status == "failed"
        assert_no_offers_or_evidence(db, procurement.id, failed_run.id)

        completed_run, _ = await start_research(
            db,
            procurement.id,
            MockResearchProvider(),
        )

        assert completed_run.status == "completed"
        assert completed_run.id != failed_run.id

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_scrape_job_status_failed_fails_the_run():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(RuntimeError, match="Scrape job is not completed"):
            await start_research(
                db,
                procurement.id,
                FailedScrapeStatusProvider(),
            )

        failed_run = procurement_runs(db, procurement.id)[0]

        assert failed_run.status == "failed"
        assert failed_run.completed_at is not None

        source = (
            db.query(ResearchSource)
            .filter(ResearchSource.research_run_id == failed_run.id)
            .one()
        )

        assert source.source_type == "search"
        assert source.raw_content == "original search snippet"
        assert_no_offers_or_evidence(db, procurement.id, failed_run.id)

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_extract_scrape_exception_fails_the_run_and_allows_another():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(RuntimeError, match="extract scrape failed"):
            await start_research(
                db,
                procurement.id,
                ExtractFailProvider(),
            )

        failed_run = procurement_runs(db, procurement.id)[0]

        assert failed_run.status == "failed"
        assert failed_run.completed_at is not None
        assert failed_run.error == "extract scrape failed"

        extract_task = (
            db.query(ResearchTask)
            .filter(
                ResearchTask.research_run_id == failed_run.id,
                ResearchTask.task_type == "extract_offers",
            )
            .one()
        )

        assert extract_task.status == "failed"
        assert_no_offers_or_evidence(db, procurement.id, failed_run.id)

        completed_run, _ = await start_research(
            db,
            procurement.id,
            MockResearchProvider(),
        )

        assert completed_run.status == "completed"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_verify_exception_fails_the_run(monkeypatch):
    async def explode(db, run):
        raise RuntimeError("verify failed")

    monkeypatch.setattr(
        "app.services.research_orchestrator.verify_offers",
        explode,
    )

    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(RuntimeError, match="verify failed"):
            await start_research(
                db,
                procurement.id,
                MockResearchProvider(),
            )

        failed_run = procurement_runs(db, procurement.id)[0]

        assert failed_run.status == "failed"
        assert failed_run.completed_at is not None
        assert failed_run.error == "verify failed"

        offers = (
            db.query(SupplierOffer)
            .filter(SupplierOffer.procurement_id == procurement.id)
            .all()
        )

        assert offers
        assert all(offer.matching_result is None for offer in offers)

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_compare_exception_fails_the_run(monkeypatch):
    async def explode(db, run):
        raise RuntimeError("compare failed")

    monkeypatch.setattr(
        "app.services.research_orchestrator.compare_offers",
        explode,
    )

    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(RuntimeError, match="compare failed"):
            await start_research(
                db,
                procurement.id,
                MockResearchProvider(),
            )

        failed_run = procurement_runs(db, procurement.id)[0]

        assert failed_run.status == "failed"
        assert failed_run.completed_at is not None
        assert failed_run.error == "compare failed"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_recommendation_exception_fails_the_run(monkeypatch):
    from app.services.recommendation import generate_recommendation

    async def fail_inside_recommendation(db, run, comparisons):
        return await generate_recommendation(db, run, [None])

    monkeypatch.setattr(
        "app.services.research_orchestrator.generate_recommendation",
        fail_inside_recommendation,
    )

    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(AttributeError):
            await start_research(
                db,
                procurement.id,
                MockResearchProvider(),
            )

        failed_run = procurement_runs(db, procurement.id)[0]

        assert failed_run.status == "failed"
        assert failed_run.completed_at is not None

        recommendation_task = (
            db.query(ResearchTask)
            .filter(
                ResearchTask.research_run_id == failed_run.id,
                ResearchTask.task_type == "generate_recommendation",
            )
            .one()
        )

        assert recommendation_task.status == "failed"
        assert recommendation_task.error

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_search_failure_inside_start_research_stays_failed():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)
        procurement = create_procurement(db, organization.id)

        with pytest.raises(RuntimeError, match="Provider search failed"):
            await start_research(
                db,
                procurement.id,
                SearchFailProvider(),
            )

        runs = procurement_runs(db, procurement.id)

        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error == "Provider search failed"
        assert runs[0].completed_at is not None

        completed_run, _ = await start_research(
            db,
            procurement.id,
            MockResearchProvider(),
        )

        assert completed_run.status == "completed"
        assert len(procurement_runs(db, procurement.id)) == 2

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
