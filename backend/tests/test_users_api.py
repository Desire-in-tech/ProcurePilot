import uuid

from app.core.security import create_access_token, hash_password
from app.db.database import SessionLocal
from app.models import Organization, User
from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def create_organization(name: str) -> uuid.UUID:
    organization_id = uuid.uuid4()

    with SessionLocal() as db:
        organization = Organization(
            id=organization_id,
            name=name,
            slug=f"{name.lower().replace(' ', '-')}-{organization_id.hex[:8]}",
        )
        db.add(organization)
        db.commit()

    return organization_id


def create_user(
    organization_id: uuid.UUID,
    role: str,
) -> tuple[uuid.UUID, str]:
    user_id = uuid.uuid4()

    with SessionLocal() as db:
        user = User(
            id=user_id,
            organization_id=organization_id,
            name=f"Test {role.title()}",
            email=f"{user_id.hex[:12]}@example.com",
            password_hash=hash_password("TestPassword123!"),
            role=role,
        )
        db.add(user)
        db.commit()

    token = create_access_token(
        subject=str(user_id),
        organization_id=str(organization_id),
        role=role,
    )

    return user_id, token


def delete_organization(organization_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        organization = db.get(Organization, organization_id)
        if organization is not None:
            db.delete(organization)
            db.commit()


def test_admin_can_list_organization_users():
    organization_id = create_organization("User List Test")
    admin_id, admin_token = create_user(organization_id, "admin")
    member_id, _ = create_user(organization_id, "member")

    try:
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200

        users = response.json()
        user_ids = {user["id"] for user in users}

        assert str(admin_id) in user_ids
        assert str(member_id) in user_ids

    finally:
        delete_organization(organization_id)


def test_admin_can_create_member():
    organization_id = create_organization("User Creation Test")
    _, admin_token = create_user(organization_id, "admin")

    try:
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "New Member",
                "email": "new.member@example.com",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 201

        data = response.json()

        assert data["name"] == "New Member"
        assert data["email"] == "new.member@example.com"
        assert data["role"] == "member"
        assert data["organization_id"] == str(organization_id)

    finally:
        delete_organization(organization_id)


def test_member_cannot_list_users():
    organization_id = create_organization("User List Authorization Test")
    _, member_token = create_user(organization_id, "member")

    try:
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {member_token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    finally:
        delete_organization(organization_id)


def test_member_cannot_create_user():
    organization_id = create_organization("User Creation Authorization Test")
    _, member_token = create_user(organization_id, "member")

    try:
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {member_token}"},
            json={
                "name": "Unauthorized User",
                "email": "unauthorized@example.com",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    finally:
        delete_organization(organization_id)


def test_admin_cannot_see_users_from_another_organization():
    organization_a = create_organization("User Tenant A")
    organization_b = create_organization("User Tenant B")

    try:
        _, admin_token_a = create_user(organization_a, "admin")
        _, admin_token_b = create_user(organization_b, "admin")

        _, member_token_b = create_user(organization_b, "member")

        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token_a}"},
        )

        assert response.status_code == 200

        users = response.json()
        user_ids = {user["id"] for user in users}

        with SessionLocal() as db:
            organization_b_users = db.query(User).filter(
                User.organization_id == organization_b
            ).all()

        for user in organization_b_users:
            assert str(user.id) not in user_ids

        assert member_token_b
        assert admin_token_b

    finally:
        delete_organization(organization_a)
        delete_organization(organization_b)


def test_admin_cannot_create_duplicate_email_in_same_organization():
    organization_id = create_organization("Duplicate User Test")
    _, admin_token = create_user(organization_id, "admin")

    try:
        payload = {
            "name": "First Member",
            "email": "duplicate@example.com",
            "password": "SecurePassword123!",
        }

        first_response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )

        assert first_response.status_code == 201

        second_response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                **payload,
                "name": "Second Member",
            },
        )

        assert second_response.status_code == 409
        assert second_response.json()["detail"] == (
            "A user with this email already exists"
        )

    finally:
        delete_organization(organization_id)
