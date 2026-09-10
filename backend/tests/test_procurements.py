import uuid

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


def test_procurement_crud_and_tenant_isolation():
    organization_a = create_organization("Test Organization A")
    organization_b = create_organization("Test Organization B")

    try:
        # Create
        response = client.post(
            "/api/v1/procurements",
            params={"organization_id": str(organization_a)},
            json={
                "title": "Test Procurement",
                "description": "Test procurement description.",
            },
        )

        assert response.status_code == 201

        procurement = response.json()
        procurement_id = procurement["id"]

        assert procurement["organization_id"] == str(organization_a)
        assert procurement["title"] == "Test Procurement"
        assert procurement["status"] == "draft"

        # List
        response = client.get(
            "/api/v1/procurements",
            params={"organization_id": str(organization_a)},
        )

        assert response.status_code == 200
        procurements = response.json()

        assert len(procurements) == 1
        assert procurements[0]["id"] == procurement_id

        # Retrieve
        response = client.get(
            f"/api/v1/procurements/{procurement_id}",
            params={"organization_id": str(organization_a)},
        )

        assert response.status_code == 200
        assert response.json()["id"] == procurement_id

        # Tenant isolation
        response = client.get(
            f"/api/v1/procurements/{procurement_id}",
            params={"organization_id": str(organization_b)},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Procurement not found"

        # Update
        response = client.patch(
            f"/api/v1/procurements/{procurement_id}",
            params={"organization_id": str(organization_a)},
            json={
                "title": "Updated Test Procurement",
            },
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated Test Procurement"

        # Delete
        response = client.delete(
            f"/api/v1/procurements/{procurement_id}",
            params={"organization_id": str(organization_a)},
        )

        assert response.status_code == 204
        assert response.content == b""

        # Confirm deletion
        response = client.get(
            f"/api/v1/procurements/{procurement_id}",
            params={"organization_id": str(organization_a)},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Procurement not found"

    finally:
        delete_organization(organization_a)
        delete_organization(organization_b)
