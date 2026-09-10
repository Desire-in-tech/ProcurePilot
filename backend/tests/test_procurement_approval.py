import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models import Organization


client = TestClient(app)


def create_organization(name: str) -> uuid.UUID:
    organization_id = uuid.uuid4()

    with SessionLocal() as db:
        organization = Organization(
            id=organization_id,
            name=name,
        )
        db.add(organization)
        db.commit()

    return organization_id


def delete_organization(organization_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        organization = db.get(Organization, organization_id)

        if organization is not None:
            db.delete(organization)
            db.commit()


def create_procurement(
    organization_id: uuid.UUID,
    title: str = "Approval Test Procurement",
) -> str:
    response = client.post(
        "/api/v1/procurements",
        params={"organization_id": str(organization_id)},
        json={
            "title": title,
            "description": "Procurement used to test approval rules.",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def add_requirement(
    organization_id: uuid.UUID,
    procurement_id: str,
) -> None:
    response = client.post(
        f"/api/v1/procurements/{procurement_id}/requirements",
        params={"organization_id": str(organization_id)},
        json={
            "name": "Required item",
            "description": "A required procurement item.",
            "category": "Equipment",
            "value": "10",
            "unit": "units",
            "is_mandatory": True,
        },
    )

    assert response.status_code == 201


def move_to_review(
    organization_id: uuid.UUID,
    procurement_id: str,
) -> None:
    with SessionLocal() as db:
        from app.models import Procurement

        procurement = db.get(Procurement, uuid.UUID(procurement_id))

        assert procurement is not None

        procurement.status = "review"
        db.commit()


def test_draft_procurement_cannot_be_approved():
    organization_id = create_organization("Approval Draft Test")

    try:
        procurement_id = create_procurement(organization_id)

        response = client.post(
            f"/api/v1/procurements/{procurement_id}/approve",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Only procurements in review status can be approved"
        )

    finally:
        delete_organization(organization_id)


def test_review_procurement_requires_requirement_before_approval():
    organization_id = create_organization("Approval Requirement Test")

    try:
        procurement_id = create_procurement(organization_id)
        move_to_review(organization_id, procurement_id)

        response = client.post(
            f"/api/v1/procurements/{procurement_id}/approve",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Procurement must have at least one requirement "
            "before approval"
        )

    finally:
        delete_organization(organization_id)


def test_review_procurement_with_requirement_can_be_approved():
    organization_id = create_organization("Approval Success Test")

    try:
        procurement_id = create_procurement(organization_id)
        add_requirement(organization_id, procurement_id)
        move_to_review(organization_id, procurement_id)

        before = datetime.now(timezone.utc)

        response = client.post(
            f"/api/v1/procurements/{procurement_id}/approve",
            params={"organization_id": str(organization_id)},
        )

        after = datetime.now(timezone.utc)

        assert response.status_code == 200

        procurement = response.json()

        assert procurement["id"] == procurement_id
        assert procurement["status"] == "approved"
        assert procurement["approved_at"] is not None

        approved_at = datetime.fromisoformat(
            procurement["approved_at"].replace("Z", "+00:00")
        )

        assert before <= approved_at <= after

    finally:
        delete_organization(organization_id)


def test_approved_procurement_cannot_be_approved_again():
    organization_id = create_organization("Approval Repeat Test")

    try:
        procurement_id = create_procurement(organization_id)
        add_requirement(organization_id, procurement_id)
        move_to_review(organization_id, procurement_id)

        response = client.post(
            f"/api/v1/procurements/{procurement_id}/approve",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == 200

        response = client.post(
            f"/api/v1/procurements/{procurement_id}/approve",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Only procurements in review status can be approved"
        )

    finally:
        delete_organization(organization_id)


def test_wrong_organization_cannot_approve_procurement():
    organization_a = create_organization("Approval Organization A")
    organization_b = create_organization("Approval Organization B")

    try:
        procurement_id = create_procurement(organization_a)
        add_requirement(organization_a, procurement_id)
        move_to_review(organization_a, procurement_id)

        response = client.post(
            f"/api/v1/procurements/{procurement_id}/approve",
            params={"organization_id": str(organization_b)},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Procurement not found"

    finally:
        delete_organization(organization_a)
        delete_organization(organization_b)
