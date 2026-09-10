import uuid

import pytest
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models import Organization, User
from app.schemas import LoginRequest, RegisterRequest
from app.services import (
    authenticate_user,
    create_user_access_token,
    register_user,
)


def test_register_and_authenticate_user():
    db = SessionLocal()

    slug = f"auth-test-{uuid.uuid4().hex[:8]}"
    email = "TEST.USER@EXAMPLE.COM"

    try:
        registration = RegisterRequest(
            organization_name="Auth Service Test Organization",
            organization_slug=slug,
            name="Test User",
            email=email,
            password="TestPassword123!",
        )

        user = register_user(db, registration)

        assert user.id is not None
        assert user.name == "Test User"
        assert user.email == "test.user@example.com"
        assert user.role == "admin"
        assert user.password_hash != "TestPassword123!"

        organization = db.get(Organization, user.organization_id)

        assert organization is not None
        assert organization.name == "Auth Service Test Organization"
        assert organization.slug == slug

        login = LoginRequest(
            organization_slug=slug,
            email=email,
            password="TestPassword123!",
        )

        authenticated_user = authenticate_user(db, login)

        assert authenticated_user.id == user.id
        assert authenticated_user.organization_id == user.organization_id

        token = create_user_access_token(authenticated_user)

        payload = decode_access_token(token)

        assert payload["sub"] == str(user.id)
        assert payload["organization_id"] == str(user.organization_id)
        assert payload["role"] == "admin"
        assert "exp" in payload

    finally:
        organization = db.scalar(
            select(Organization).where(Organization.slug == slug)
        )

        if organization is not None:
            db.delete(organization)
            db.commit()

        db.close()


def test_wrong_password_is_rejected():
    db = SessionLocal()

    slug = f"auth-test-{uuid.uuid4().hex[:8]}"

    try:
        registration = RegisterRequest(
            organization_name="Wrong Password Test Organization",
            organization_slug=slug,
            name="Test User",
            email="user@example.com",
            password="CorrectPassword123!",
        )

        register_user(db, registration)

        login = LoginRequest(
            organization_slug=slug,
            email="user@example.com",
            password="WrongPassword123!",
        )

        with pytest.raises(ValueError, match="Invalid organization, email, or password"):
            authenticate_user(db, login)

    finally:
        organization = db.scalar(
            select(Organization).where(Organization.slug == slug)
        )

        if organization is not None:
            db.delete(organization)
            db.commit()

        db.close()


def test_unknown_organization_is_rejected():
    db = SessionLocal()

    try:
        login = LoginRequest(
            organization_slug=f"does-not-exist-{uuid.uuid4().hex[:8]}",
            email="user@example.com",
            password="SomePassword123!",
        )

        with pytest.raises(ValueError, match="Invalid organization, email, or password"):
            authenticate_user(db, login)

    finally:
        db.close()


def test_duplicate_organization_slug_is_rejected():
    db = SessionLocal()

    slug = f"auth-test-{uuid.uuid4().hex[:8]}"

    try:
        registration = RegisterRequest(
            organization_name="Duplicate Slug Test Organization",
            organization_slug=slug,
            name="First User",
            email="first@example.com",
            password="Password123!",
        )

        register_user(db, registration)

        duplicate_registration = RegisterRequest(
            organization_name="Another Organization",
            organization_slug=slug,
            name="Second User",
            email="second@example.com",
            password="Password123!",
        )

        with pytest.raises(ValueError, match="Organization slug is already registered"):
            register_user(db, duplicate_registration)

    finally:
        organization = db.scalar(
            select(Organization).where(Organization.slug == slug)
        )

        if organization is not None:
            db.delete(organization)
            db.commit()

        db.close()
