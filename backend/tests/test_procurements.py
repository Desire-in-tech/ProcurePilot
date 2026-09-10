import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.core.security import create_access_token, hash_password
from app.models import Organization, User


client = TestClient(app)


def create_organization(name: str) -> uuid.UUID:
    organization_id = uuid.uuid4()

    with SessionLocal() as db:
        organization = Organization(
            id=organization_id,
            name=name,
            slug=f"test-{uuid.uuid4().hex[:12]}",
        )
        db.add(organization)
        db.commit()

    return organization_id


def create_user(organization_id: uuid.UUID) -> str:
    user_id = uuid.uuid4()

    with SessionLocal() as db:
        user = User(
            id=user_id,
            organization_id=organization_id,
            name="Test User",
            email=f"{user_id.hex[:12]}@example.com",
            password_hash=hash_password("TestPassword123!"),
            role="admin",
        )
        db.add(user)
        db.commit()

    return create_access_token(
        subject=str(user_id),
        organization_id=str(organization_id),
        role="admin",
    )


def delete_organization(organization_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        organization = db.get(Organization, organization_id)

        if organization is not None:
            db.delete(organization)
            db.commit()


def test_procurement_crud_and_tenant_isolation():
    organization_a = create_organization("Test Organization A")
    organization_b = create_organization("Test Organization B")
    token_a = create_user(organization_a)
    token_b = create_user(organization_b)

    try:
        # Create
        response = client.post(
            "/api/v1/procurements",
            headers={"Authorization": f"Bearer {token_a}"},
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
            headers={"Authorization": f"Bearer {token_a}"},
        )

        assert response.status_code == 200
        procurements = response.json()

        assert len(procurements) == 1
        assert procurements[0]["id"] == procurement_id

        # Retrieve
        response = client.get(
            f"/api/v1/procurements/{procurement_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

        assert response.status_code == 200
        assert response.json()["id"] == procurement_id

        # Tenant isolation
        response = client.get(
            f"/api/v1/procurements/{procurement_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Procurement not found"

        # Update
        response = client.patch(
            f"/api/v1/procurements/{procurement_id}",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "title": "Updated Test Procurement",
            },
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated Test Procurement"

        # Delete
        response = client.delete(
            f"/api/v1/procurements/{procurement_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

        assert response.status_code == 204
        assert response.content == b""

        # Confirm deletion
        response = client.get(
            f"/api/v1/procurements/{procurement_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Procurement not found"

    finally:
        delete_organization(organization_a)
        delete_organization(organization_b)


def test_member_cannot_delete_procurement():
    organization_id = create_organization("Member Delete Test")
    admin_token = create_user(organization_id)

    user_id = uuid.uuid4()

    with SessionLocal() as db:
        member = User(
            id=user_id,
            organization_id=organization_id,
            name="Test Member",
            email=f"{user_id.hex[:12]}@example.com",
            password_hash=hash_password("TestPassword123!"),
            role="member",
        )
        db.add(member)
        db.commit()

    member_token = create_access_token(
        subject=str(user_id),
        organization_id=str(organization_id),
        role="member",
    )

    try:
        response = client.post(
            "/api/v1/procurements",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "title": "Protected Procurement",
                "description": "Should not be deleted by a member.",
            },
        )

        assert response.status_code == 201
        procurement_id = response.json()["id"]

        response = client.delete(
            f"/api/v1/procurements/{procurement_id}",
            headers={"Authorization": f"Bearer {member_token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    finally:
        delete_organization(organization_id)
