from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_database
from app.schemas import ProcurementCreate, ProcurementResponse, ProcurementUpdate
from app.services import (
    approve_procurement,
    create_procurement,
    delete_procurement,
    get_procurement,
    list_procurements,
    update_procurement,
)


router = APIRouter(
    prefix="/api/v1/procurements",
    tags=["Procurements"],
)


@router.post(
    "",
    response_model=ProcurementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    data: ProcurementCreate,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    try:
        return create_procurement(
            db=db,
            organization_id=organization_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[ProcurementResponse],
)
def list_all(
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    return list_procurements(
        db=db,
        organization_id=organization_id,
    )


@router.get(
    "/{procurement_id}",
    response_model=ProcurementResponse,
)
def get_one(
    procurement_id: UUID,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    procurement = get_procurement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
    )

    if procurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procurement not found",
        )

    return procurement


@router.patch(
    "/{procurement_id}",
    response_model=ProcurementResponse,
)
def update(
    procurement_id: UUID,
    data: ProcurementUpdate,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    procurement = get_procurement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
    )

    if procurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procurement not found",
        )

    return update_procurement(
        db=db,
        procurement=procurement,
        data=data,
    )


@router.delete(
    "/{procurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete(
    procurement_id: UUID,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    procurement = get_procurement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
    )

    if procurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procurement not found",
        )

    delete_procurement(
        db=db,
        procurement=procurement,
    )


@router.post(
    "/{procurement_id}/approve",
    response_model=ProcurementResponse,
)
def approve(
    procurement_id: UUID,
    organization_id: UUID,
    db: Session = Depends(get_database),
):
    procurement = get_procurement(
        db=db,
        organization_id=organization_id,
        procurement_id=procurement_id,
    )

    if procurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procurement not found",
        )

    try:
        return approve_procurement(
            db=db,
            procurement=procurement,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
