from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Procurement, Requirement
from app.schemas import RequirementCreate, RequirementUpdate


def create_requirement(
    db: Session,
    organization_id: UUID,
    procurement_id: UUID,
    data: RequirementCreate,
) -> Requirement:
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == procurement_id,
            Procurement.organization_id == organization_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    requirement = Requirement(
        procurement_id=procurement_id,
        name=data.name,
        description=data.description,
        category=data.category,
        value=data.value,
        unit=data.unit,
        is_mandatory=data.is_mandatory,
    )

    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    return requirement


def list_requirements(
    db: Session,
    organization_id: UUID,
    procurement_id: UUID,
) -> list[Requirement]:
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == procurement_id,
            Procurement.organization_id == organization_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    statement = (
        select(Requirement)
        .where(Requirement.procurement_id == procurement_id)
        .order_by(Requirement.created_at.asc())
    )

    return list(db.scalars(statement).all())


def get_requirement(
    db: Session,
    organization_id: UUID,
    procurement_id: UUID,
    requirement_id: UUID,
) -> Requirement | None:
    statement = (
        select(Requirement)
        .join(Procurement)
        .where(
            Requirement.id == requirement_id,
            Requirement.procurement_id == procurement_id,
            Procurement.organization_id == organization_id,
        )
    )

    return db.scalar(statement)


def update_requirement(
    db: Session,
    requirement: Requirement,
    data: RequirementUpdate,
) -> Requirement:
    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(requirement, field, value)

    db.commit()
    db.refresh(requirement)

    return requirement


def delete_requirement(
    db: Session,
    requirement: Requirement,
) -> None:
    db.delete(requirement)
    db.commit()
