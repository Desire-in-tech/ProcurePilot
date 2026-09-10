import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.main import app
from app.models import Organization, Procurement, Requirement


client = TestClient(app)


def create_organization(db, name: str) -> Organization:
    organization = Organization(name=name)
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def create_procurement(
    db,
    organization_id,
    title: str = "Office Equipment",
) -> Procurement:
    procurement = Procurement(
        organization_id=organization_id,
        title=title,
        description="Procurement for office equipment",
    )
    db.add(procurement)
    db.commit()
    db.refresh(procurement)
    return procurement


def cleanup(
    db,
    organization_ids: list[uuid.UUID],
) -> None:
    for organization_id in organization_ids:
        organization = db.get(Organization, organization_id)

        if organization is not None:
            db.delete(organization)

    db.commit()


def test_requirement_crud_and_tenant_isolation():
    db = SessionLocal()
    organization_a = None
    organization_b = None

    try:
        organization_a = create_organization(db, "Requirement Test Org A")
        organization_b = create_organization(db, "Requirement Test Org B")

        procurement = create_procurement(
            db,
            organization_a.id,
        )

        base_url = (
            f"/api/v1/procurements/{procurement.id}/requirements"
        )

        # Create
        response = client.post(
            base_url,
            params={"organization_id": str(organization_a.id)},
            json={
                "name": "Laptop",
                "description": "Business laptop",
                "category": "IT Equipment",
                "value": "16GB RAM",
                "unit": "item",
                "is_mandatory": True,
            },
        )

        assert response.status_code == 201

        requirement = response.json()

        assert requirement["name"] == "Laptop"
        assert requirement["category"] == "IT Equipment"
        assert requirement["is_mandatory"] is True
        assert requirement["procurement_id"] == str(procurement.id)

        requirement_id = requirement["id"]

        # List
        response = client.get(
            base_url,
            params={"organization_id": str(organization_a.id)},
        )

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == requirement_id

        # Retrieve
        response = client.get(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_a.id)},
        )

        assert response.status_code == 200
        assert response.json()["id"] == requirement_id

        # Update
        response = client.patch(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_a.id)},
            json={
                "name": "Business Laptop",
                "value": "32GB RAM",
            },
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Business Laptop"
        assert response.json()["value"] == "32GB RAM"

        # Cross-organization retrieve must fail
        response = client.get(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_b.id)},
        )

        assert response.status_code == 404

        # Cross-organization update must fail
        response = client.patch(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_b.id)},
            json={"name": "Unauthorized Change"},
        )

        assert response.status_code == 404

        # Cross-organization delete must fail
        response = client.delete(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_b.id)},
        )

        assert response.status_code == 404

        # Correct organization can delete
        response = client.delete(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_a.id)},
        )

        assert response.status_code == 204

        # Deleted requirement must no longer exist
        response = client.get(
            f"{base_url}/{requirement_id}",
            params={"organization_id": str(organization_a.id)},
        )

        assert response.status_code == 404

    finally:
        organization_ids = []

        if organization_a is not None:
            organization_ids.append(organization_a.id)

        if organization_b is not None:
            organization_ids.append(organization_b.id)

        cleanup(db, organization_ids)
        db.close()


def test_requirement_requires_existing_procurement():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(
            db,
            "Missing Procurement Test Org",
        )

        missing_procurement_id = uuid.uuid4()

        response = client.post(
            f"/api/v1/procurements/{missing_procurement_id}/requirements",
            params={"organization_id": str(organization.id)},
            json={
                "name": "Laptop",
                "is_mandatory": True,
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Procurement not found"

    finally:
        if organization is not None:
            cleanup(db, [organization.id])

        db.close()


def test_requirement_cannot_be_accessed_through_wrong_procurement():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(
            db,
            "Wrong Procurement Test Org",
        )

        procurement_a = create_procurement(
            db,
            organization.id,
            "Procurement A",
        )

        procurement_b = create_procurement(
            db,
            organization.id,
            "Procurement B",
        )

        create_url = (
            f"/api/v1/procurements/{procurement_a.id}/requirements"
        )

        response = client.post(
            create_url,
            params={"organization_id": str(organization.id)},
            json={
                "name": "Laptop",
                "is_mandatory": True,
            },
        )

        assert response.status_code == 201
        requirement_id = response.json()["id"]

        wrong_procurement_url = (
            f"/api/v1/procurements/"
            f"{procurement_b.id}/requirements/{requirement_id}"
        )

        response = client.get(
            wrong_procurement_url,
            params={"organization_id": str(organization.id)},
        )

        assert response.status_code == 404

    finally:
        if organization is not None:
            cleanup(db, [organization.id])

        db.close()
