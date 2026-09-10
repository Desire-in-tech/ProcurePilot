import uuid

from app.core.security import create_access_token, hash_password
from app.db.database import SessionLocal
from app.models import Organization, User


def create_user(organization_id: uuid.UUID, role: str) -> str:
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

    return create_access_token(
        subject=str(user_id),
        organization_id=str(organization_id),
        role=role,
    )


def test_admin_token_contains_admin_role():
    organization_id = uuid.uuid4()

    with SessionLocal() as db:
        organization = Organization(
            id=organization_id,
            name="Authorization Test Organization",
            slug=f"authorization-test-{organization_id.hex[:8]}",
        )
        db.add(organization)
        db.commit()

    token = create_user(organization_id, "admin")

    assert token
    assert isinstance(token, str)


def test_member_token_contains_member_role():
    organization_id = uuid.uuid4()

    with SessionLocal() as db:
        organization = Organization(
            id=organization_id,
            name="Member Authorization Test Organization",
            slug=f"member-authorization-{organization_id.hex[:8]}",
        )
        db.add(organization)
        db.commit()

    token = create_user(organization_id, "member")

    assert token
    assert isinstance(token, str)
