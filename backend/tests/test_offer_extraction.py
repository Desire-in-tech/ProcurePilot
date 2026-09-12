import uuid

import pytest

from app.ai.providers import MockResearchProvider
from app.db.database import SessionLocal
from app.models import (
    Organization,
    OfferEvidence,
    Procurement,
    ResearchRun,
    ResearchSource,
    ResearchTask,
    SupplierOffer,
)
from app.services.offer_extraction import extract_offers_from_sources


def create_organization(db) -> Organization:
    organization = Organization(
        name="Offer Extraction Test Organization",
        slug=f"offer-{uuid.uuid4().hex[:12]}",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def cleanup(db, organization_id) -> None:
    organization = db.get(Organization, organization_id)

    if organization is not None:
        db.delete(organization)

    db.commit()


@pytest.mark.asyncio
async def test_extract_offers_persists_offers_and_evidence():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Engineering Laptops",
            description="Purchase laptops for the engineering team.",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        source = ResearchSource(
            research_run_id=run.id,
            url="https://supplier.example.com/laptop",
            title="Business Laptop Pro 14",
            source_type="scraped",
            provider="mock",
            raw_content="Mock scraped content.",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        offers = await extract_offers_from_sources(
            db,
            run,
            MockResearchProvider(),
            [source],
        )

        assert len(offers) == 1

        offer = offers[0]

        assert offer.supplier_name == "Nordic Tech Supply"
        assert offer.product_name == "Business Laptop Pro 14"
        assert offer.model == "BLP14"
        assert str(offer.price) == "1180.00"
        assert offer.currency == "EUR"
        assert offer.availability == "In stock"
        assert offer.warranty == "3 years"
        assert offer.specifications == {
            "ram": "16GB",
            "storage": "512GB SSD",
        }
        assert offer.url == source.url

        evidence = (
            db.query(OfferEvidence)
            .filter(OfferEvidence.offer_id == offer.id)
            .all()
        )

        assert len(evidence) == 8
        assert {item.field for item in evidence} == {
            "supplier_name",
            "product_name",
            "model",
            "price",
            "currency",
            "availability",
            "warranty",
            "specifications",
        }
        assert all(item.source_id == source.id for item in evidence)
        assert all(item.confidence is None for item in evidence)

        tasks = (
            db.query(ResearchTask)
            .filter(ResearchTask.research_run_id == run.id)
            .all()
        )

        assert len(tasks) == 1
        assert tasks[0].task_type == "extract_offers"
        assert tasks[0].status == "completed"
        assert tasks[0].output_data["source_count"] == 1
        assert tasks[0].output_data["offer_count"] == 1

        persisted_offer = db.get(SupplierOffer, offer.id)
        assert persisted_offer is not None

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_extract_offers_skips_invalid_structured_offer():
    class InvalidProvider(MockResearchProvider):
        async def scrape(
            self,
            url,
            *,
            schema=None,
            use_browser=False,
        ):
            from app.ai.providers.base import ScrapeResult

            return ScrapeResult(
                url=url,
                title="Invalid Source",
                content="Invalid content.",
                structured_data={
                    "offers": [
                        {
                            "supplier_name": None,
                            "product_name": "Laptop",
                        },
                        {
                            "supplier_name": "Valid Supplier",
                            "product_name": "Valid Laptop",
                        },
                    ]
                },
            )

    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Laptops",
            description="Purchase laptops.",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        source = ResearchSource(
            research_run_id=run.id,
            url="https://supplier.example.com/product",
            provider="mock",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        offers = await extract_offers_from_sources(
            db,
            run,
            InvalidProvider(),
            [source],
        )

        assert len(offers) == 1
        assert offers[0].supplier_name == "Valid Supplier"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
