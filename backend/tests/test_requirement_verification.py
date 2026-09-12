import uuid
from decimal import Decimal

import pytest

from app.db.database import SessionLocal
from app.models import (
    OfferEvidence,
    Organization,
    Procurement,
    Requirement,
    ResearchRun,
    ResearchSource,
    SupplierOffer,
)
from app.services.requirement_verification import verify_offers


def create_organization(db):
    organization = Organization(
        name="Verification Test Org",
        slug=f"verification-{uuid.uuid4().hex[:12]}",
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
async def test_verify_offer_marks_matching_requirements_as_eligible():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Engineering Laptops",
            description="25 laptops for engineering",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        requirement_ram = Requirement(
            procurement_id=procurement.id,
            name="RAM",
            value="16GB",
            unit="GB",
            is_mandatory=True,
        )

        requirement_storage = Requirement(
            procurement_id=procurement.id,
            name="Storage",
            value="512GB",
            unit="GB",
            is_mandatory=True,
        )

        requirement_warranty = Requirement(
            procurement_id=procurement.id,
            name="Warranty",
            value="3 years",
            unit="years",
            is_mandatory=True,
        )

        db.add_all(
            [
                requirement_ram,
                requirement_storage,
                requirement_warranty,
            ]
        )
        db.commit()

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        source = ResearchSource(
            research_run_id=run.id,
            url="https://example.com/laptop",
            title="Business Laptop Pro 14",
            source_type="supplier",
            provider="mock",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Nordic Tech Supply",
            product_name="Business Laptop Pro 14",
            model="BLP14",
            price=Decimal("1180.00"),
            currency="EUR",
            availability="In stock",
            warranty="3 years",
            specifications={
                "ram": "16GB",
                "storage": "512GB SSD",
            },
            evidence=[
                OfferEvidence(
                    source_id=source.id,
                    field="ram",
                    value="16GB",
                ),
                OfferEvidence(
                    source_id=source.id,
                    field="storage",
                    value="512GB SSD",
                ),
                OfferEvidence(
                    source_id=source.id,
                    field="warranty",
                    value="3 years",
                ),
            ],
        )

        db.add(offer)
        db.commit()
        db.refresh(offer)

        offers = await verify_offers(db, run)

        assert len(offers) == 1

        result = offers[0].matching_result

        assert result["status"] == "eligible"
        assert result["mandatory_requirements_met"] == 3
        assert result["mandatory_requirements_total"] == 3

        statuses = {
            item["requirement"]: item["status"]
            for item in result["requirements"]
        }

        assert statuses == {
            "RAM": "met",
            "Storage": "met",
            "Warranty": "met",
        }

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_verify_offer_marks_failed_mandatory_requirement_not_eligible():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Engineering Laptops",
            description="Engineering laptops",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        db.add(
            Requirement(
                procurement_id=procurement.id,
                name="RAM",
                value="32GB",
                unit="GB",
                is_mandatory=True,
            )
        )
        db.commit()

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        source = ResearchSource(
            research_run_id=run.id,
            url="https://example.com/laptop",
            title="Laptop",
            source_type="supplier",
            provider="mock",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Supplier A",
            product_name="Laptop A",
            specifications={"ram": "16GB"},
            evidence=[
                OfferEvidence(
                    source_id=source.id,
                    field="ram",
                    value="16GB",
                )
            ],
        )
        db.add(offer)
        db.commit()

        offers = await verify_offers(db, run)

        result = offers[0].matching_result

        assert result["status"] == "not_eligible"
        assert result["mandatory_requirements_met"] == 0

        assert result["requirements"][0]["status"] == "not_met"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_verify_offer_marks_missing_evidence_for_review():
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

        db.add(
            Requirement(
                procurement_id=procurement.id,
                name="Warranty",
                value="3 years",
                unit="years",
                is_mandatory=True,
            )
        )
        db.commit()

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        db.add(
            SupplierOffer(
                procurement_id=procurement.id,
                supplier_name="Supplier A",
                product_name="Laptop A",
                specifications={
                    "ram": "16GB",
                },
            )
        )
        db.commit()

        offers = await verify_offers(db, run)

        result = offers[0].matching_result

        assert result["status"] == "needs_review"
        assert result["requirements"][0]["status"] == "unknown"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
