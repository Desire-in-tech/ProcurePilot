from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_database
from app.schemas import (
    RequirementCreate,
    RequirementResponse,
    RequirementUpdate,
)
from app.services import (
    create_requirement,
    delete_requirement,
    get_requirement,
    list_requirements,
    update_requirement,
)


router = APIRouter(
    prefix="/api/v1/procurements/{procurement_id}/requirements",
    tags=["Requirements"],
)


@router.post(
    "",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    procurement_id: UUID,
    data: RequirementCreate,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    try:
        return create_requirement(
            db=db,
            organization_id=organization_id,
            procurement_id=procurement_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[RequirementResponse],
)
def list_all(
    procurement_id: UUID,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    try:
        return list_requirements(
            db=db,
            organization_id=organization_id,
            procurement_id=procurement_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{requirement_id}",
    response_model=RequirementResponse,
)
def get_one(
    procurement_id: UUID,
    requirement_id: UUID,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    requirement = get_requirement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
        requirement_id=requirement_id,
    )

    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement not found",
        )

    return requirement


@router.patch(
    "/{requirement_id}",
    response_model=RequirementResponse,
)
def update(
    procurement_id: UUID,
    requirement_id: UUID,
    data: RequirementUpdate,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    requirement = get_requirement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
        requirement_id=requirement_id,
    )

    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement not found",
        )

    return update_requirement(
        db=db,
        requirement=requirement,
        data=data,
    )


@router.delete(
    "/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete(
    procurement_id: UUID,
    requirement_id: UUID,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    requirement = get_requirement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
        requirement_id=requirement_id,
    )

    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requirement not found",
        )

    delete_requirement(
        db=db,
        requirement=requirement,
    )
