import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.main import app
from app.models import Organization


client = TestClient(app)


def cleanup_organization(slug: str) -> None:
    db = SessionLocal()

    try:
        organization = db.scalar(
            select(Organization).where(Organization.slug == slug)
        )

        if organization is not None:
            db.delete(organization)
            db.commit()
    finally:
        db.close()


def test_register_login_and_get_current_user():
    slug = f"api-auth-{uuid.uuid4().hex[:8]}"

    try:
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "API Auth Test Organization",
                "organization_slug": slug,
                "name": "API Test User",
                "email": "API.USER@EXAMPLE.COM",
                "password": "TestPassword123!",
            },
        )

        assert register_response.status_code == 201

        registered_user = register_response.json()

        assert registered_user["name"] == "API Test User"
        assert registered_user["email"] == "api.user@example.com"
        assert registered_user["role"] == "admin"
        assert "password" not in registered_user
        assert "password_hash" not in registered_user

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "organization_slug": slug,
                "email": "api.user@example.com",
                "password": "TestPassword123!",
            },
        )

        assert login_response.status_code == 200

        token = login_response.json()["access_token"]

        assert token
        assert login_response.json()["token_type"] == "bearer"

        me_response = client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert me_response.status_code == 200

        current_user = me_response.json()

        assert current_user["id"] == registered_user["id"]
        assert current_user["organization_id"] == registered_user["organization_id"]
        assert current_user["email"] == "api.user@example.com"
        assert current_user["role"] == "admin"

    finally:
        cleanup_organization(slug)


def test_me_requires_authentication():
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_rejects_invalid_token():
    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer definitely-not-a-valid-token",
        },
    )

    assert response.status_code == 401


def test_login_rejects_wrong_password():
    slug = f"api-auth-{uuid.uuid4().hex[:8]}"

    try:
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Wrong Password API Test",
                "organization_slug": slug,
                "name": "API Test User",
                "email": "user@example.com",
                "password": "CorrectPassword123!",
            },
        )

        assert register_response.status_code == 201

        response = client.post(
            "/api/v1/auth/login",
            json={
                "organization_slug": slug,
                "email": "user@example.com",
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code == 401
        assert response.json()["detail"] == (
            "Invalid organization, email, or password"
        )

    finally:
        cleanup_organization(slug)
