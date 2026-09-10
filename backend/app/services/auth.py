from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models import Organization, User
from app.schemas import LoginRequest, RegisterRequest


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(
    db: Session,
    data: RegisterRequest,
) -> User:
    email = normalize_email(str(data.email))

    organization = db.scalar(
        select(Organization).where(
            Organization.slug == data.organization_slug
        )
    )

    if organization is not None:
        raise ValueError("Organization slug is already registered")

    organization = Organization(
        name=data.organization_name.strip(),
        slug=data.organization_slug,
    )

    user = User(
        organization=organization,
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role="admin",
    )

    db.add(organization)
    db.add(user)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(user)

    return user


def authenticate_user(
    db: Session,
    data: LoginRequest,
) -> User:
    email = normalize_email(str(data.email))

    organization = db.scalar(
        select(Organization).where(
            Organization.slug == data.organization_slug
        )
    )

    if organization is None:
        raise ValueError("Invalid organization, email, or password")

    user = db.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == email,
        )
    )

    if user is None or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise ValueError("Invalid organization, email, or password")

    return user


def create_user_access_token(user: User) -> str:
    return create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
    )
