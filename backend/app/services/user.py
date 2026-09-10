from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User
from app.schemas import UserCreate


def normalize_email(email: str) -> str:
    return email.strip().lower()


def list_users(
    db: Session,
    organization_id: UUID,
) -> list[User]:
    statement = (
        select(User)
        .where(User.organization_id == organization_id)
        .order_by(User.created_at.asc())
    )
    return list(db.scalars(statement).all())


def create_member(
    db: Session,
    organization_id: UUID,
    data: UserCreate,
) -> User:
    email = normalize_email(str(data.email))

    existing_user = db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.email == email,
        )
    )

    if existing_user is not None:
        raise ValueError("A user with this email already exists")

    user = User(
        organization_id=organization_id,
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role="member",
    )

    db.add(user)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(user)
    return user
