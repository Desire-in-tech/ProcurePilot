import uuid
from decimal import Decimal

import pytest

from app.db.database import SessionLocal
from app.models import (
    OfferEvidence,
    Organization,
    Procurement,
    ResearchRun,
    ResearchSource,
    SupplierOffer,
)
from app.services.offer_comparison import compare_offers


def create_organization(db):
    organization = Organization(
        name="Comparison Test Org",
        slug=f"comparison-{uuid.uuid4().hex[:12]}",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def cleanup(db, organization_id):
    organization = db.get(Organization, organization_id)

    if organization is not None:
        db.delete(organization)

    db.commit()


@pytest.mark.asyncio
async def test_compare_offers_ranks_eligible_offers():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Engineering Laptops",
            description="Laptop procurement",
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
            url="https://example.com/laptops",
            title="Laptop supplier",
            source_type="supplier",
            provider="mock",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        expensive = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Supplier A",
            product_name="Laptop A",
            price=Decimal("1500.00"),
            currency="EUR",
            matching_result={
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
            },
            evidence=[
                OfferEvidence(
                    source_id=source.id,
                    field="ram",
                    value="32GB",
                ),
            ],
        )

        cheaper = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Supplier B",
            product_name="Laptop B",
            price=Decimal("1200.00"),
            currency="EUR",
            matching_result={
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
            },
            evidence=[
                OfferEvidence(
                    source_id=source.id,
                    field="ram",
                    value="32GB",
                ),
                OfferEvidence(
                    source_id=source.id,
                    field="storage",
                    value="1TB SSD",
                ),
            ],
        )

        db.add_all([expensive, cheaper])
        db.commit()

        results = await compare_offers(db, run)

        assert len(results) == 2

        assert results[0]["supplier_name"] == "Supplier B"
        assert results[0]["rank"] == 1
        assert results[0]["price_rank"] == 1

        assert results[1]["supplier_name"] == "Supplier A"
        assert results[1]["rank"] == 2
        assert results[1]["price_rank"] == 2

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_compare_offers_prioritizes_eligibility_over_price():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Laptops",
            description="Laptop procurement",
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

        eligible = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Eligible Supplier",
            product_name="Laptop A",
            price=Decimal("1500.00"),
            currency="EUR",
            matching_result={
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
            },
        )

        review = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Review Supplier",
            product_name="Laptop B",
            price=Decimal("900.00"),
            currency="EUR",
            matching_result={
                "status": "needs_review",
                "mandatory_requirements_met": 2,
                "mandatory_requirements_total": 3,
            },
        )

        db.add_all([eligible, review])
        db.commit()

        results = await compare_offers(db, run)

        assert results[0]["supplier_name"] == "Eligible Supplier"
        assert results[0]["status"] == "eligible"

        assert results[1]["supplier_name"] == "Review Supplier"
        assert results[1]["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_compare_offers_does_not_compare_different_currencies():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Laptops",
            description="Laptop procurement",
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

        eur_offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="EUR Supplier",
            product_name="Laptop EUR",
            price=Decimal("1200.00"),
            currency="EUR",
            matching_result={
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
            },
        )

        usd_offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="USD Supplier",
            product_name="Laptop USD",
            price=Decimal("1000.00"),
            currency="USD",
            matching_result={
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
            },
        )

        db.add_all([eur_offer, usd_offer])
        db.commit()

        results = await compare_offers(db, run)

        assert results[0]["price_rank"] == 1
        assert results[1]["price_rank"] == 1

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_compare_offers_records_completed_research_task():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Laptops",
            description="Laptop procurement",
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

        offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Supplier A",
            product_name="Laptop A",
            matching_result={
                "status": "eligible",
                "mandatory_requirements_met": 1,
                "mandatory_requirements_total": 1,
            },
        )
        db.add(offer)
        db.commit()

        results = await compare_offers(db, run)

        assert len(results) == 1

        task = db.scalar(
            __import__("sqlalchemy").select(
                __import__("app.models", fromlist=["ResearchTask"]).ResearchTask
            ).where(
                __import__("app.models", fromlist=["ResearchTask"]).ResearchTask.research_run_id == run.id,
                __import__("app.models", fromlist=["ResearchTask"]).ResearchTask.task_type == "compare_offers",
            )
        )

        assert task is not None
        assert task.status == "completed"
        assert task.output_data["offer_count"] == 1

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
