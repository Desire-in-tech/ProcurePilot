from uuid import UUID

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, Procurement, Requirement
from app.schemas import ProcurementCreate, ProcurementUpdate


def create_procurement(
    db: Session,
    organization_id: UUID,
    data: ProcurementCreate,
) -> Procurement:
    organization = db.get(Organization, organization_id)

    if organization is None:
        raise ValueError("Organization not found")

    procurement = Procurement(
        organization_id=organization_id,
        title=data.title,
        description=data.description,
    )

    db.add(procurement)
    db.commit()
    db.refresh(procurement)

    return procurement


def list_procurements(
    db: Session,
    organization_id: UUID,
) -> list[Procurement]:
    statement = (
        select(Procurement)
        .where(Procurement.organization_id == organization_id)
        .order_by(Procurement.created_at.desc())
    )

    return list(db.scalars(statement).all())


def get_procurement(
    db: Session,
    organization_id: UUID,
    procurement_id: UUID,
) -> Procurement | None:
    statement = select(Procurement).where(
        Procurement.id == procurement_id,
        Procurement.organization_id == organization_id,
    )

    return db.scalar(statement)


def update_procurement(
    db: Session,
    procurement: Procurement,
    data: ProcurementUpdate,
) -> Procurement:
    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(procurement, field, value)

    db.commit()
    db.refresh(procurement)

    return procurement


def approve_procurement(
    db: Session,
    procurement: Procurement,
) -> Procurement:
    if procurement.status != "review":
        raise ValueError(
            "Only procurements in review status can be approved"
        )

    requirement_exists = db.scalar(
        select(Requirement.id)
        .where(Requirement.procurement_id == procurement.id)
        .limit(1)
    )

    if requirement_exists is None:
        raise ValueError(
            "Procurement must have at least one requirement before approval"
        )

    procurement.status = "approved"
    procurement.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(procurement)

    return procurement


def delete_procurement(
    db: Session,
    procurement: Procurement,
) -> None:
    db.delete(procurement)
    db.commit()
