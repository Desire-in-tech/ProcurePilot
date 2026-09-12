import uuid

import pytest

from app.db.database import SessionLocal
from app.models import Organization, Procurement, ResearchRun, ResearchTask
from app.services.recommendation import generate_recommendation


def create_organization(db):
    organization = Organization(
        name="Recommendation Test Org",
        slug=f"recommendation-{uuid.uuid4().hex[:12]}",
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
async def test_generate_recommendation_selects_top_eligible_offer():
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

        first_offer_id = str(uuid.uuid4())
        second_offer_id = str(uuid.uuid4())
        review_offer_id = str(uuid.uuid4())

        comparisons = [
            {
                "offer_id": first_offer_id,
                "supplier_name": "Best Supplier",
                "product_name": "Best Laptop",
                "model": "BEST-1",
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
                "mandatory_requirement_ratio": 1.0,
                "evidence_count": 3,
                "price": "1000.00",
                "currency": "EUR",
                "price_rank": 1,
            },
            {
                "offer_id": second_offer_id,
                "supplier_name": "Alternative Supplier",
                "product_name": "Alternative Laptop",
                "model": "ALT-1",
                "status": "eligible",
                "mandatory_requirements_met": 3,
                "mandatory_requirements_total": 3,
                "mandatory_requirement_ratio": 1.0,
                "evidence_count": 2,
                "price": "1100.00",
                "currency": "EUR",
                "price_rank": 2,
            },
            {
                "offer_id": review_offer_id,
                "supplier_name": "Review Supplier",
                "product_name": "Review Laptop",
                "model": "REV-1",
                "status": "needs_review",
                "mandatory_requirements_met": 2,
                "mandatory_requirements_total": 3,
                "mandatory_requirement_ratio": 0.667,
                "evidence_count": 3,
                "price": "900.00",
                "currency": "EUR",
                "price_rank": 1,
            },
        ]

        recommendation = await generate_recommendation(
            db,
            run,
            comparisons,
        )

        assert recommendation["status"] == "recommended"
        assert recommendation["recommended_offer_id"] == first_offer_id
        assert recommendation["supplier_name"] == "Best Supplier"
        assert recommendation["eligible_offer_count"] == 2
        assert recommendation["alternative_offer_ids"] == [
            second_offer_id
        ]
        assert recommendation["human_review_required"] is False

        task = db.query(ResearchTask).filter(
            ResearchTask.research_run_id == run.id,
            ResearchTask.task_type == "generate_recommendation",
        ).one()

        assert task.status == "completed"
        assert task.output_data["recommended_offer_id"] == first_offer_id

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_generate_recommendation_requests_human_review_when_no_offer_is_eligible():
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

        comparisons = [
            {
                "offer_id": str(uuid.uuid4()),
                "supplier_name": "Supplier A",
                "product_name": "Laptop A",
                "status": "needs_review",
                "price": "1000.00",
                "currency": "EUR",
            },
            {
                "offer_id": str(uuid.uuid4()),
                "supplier_name": "Supplier B",
                "product_name": "Laptop B",
                "status": "not_eligible",
                "price": "900.00",
                "currency": "EUR",
            },
        ]

        recommendation = await generate_recommendation(
            db,
            run,
            comparisons,
        )

        assert recommendation["status"] == "needs_human_input"
        assert recommendation["recommended_offer_id"] is None
        assert recommendation["eligible_offer_count"] == 0
        assert recommendation["human_review_required"] is True

        task = db.query(ResearchTask).filter(
            ResearchTask.research_run_id == run.id,
            ResearchTask.task_type == "generate_recommendation",
        ).one()

        assert task.status == "completed"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
