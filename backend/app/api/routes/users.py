from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_database, require_admin
from app.models import User
from app.schemas import ManagedUserResponse, UserCreate
from app.services import create_member, list_users


router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
)


@router.get(
    "",
    response_model=list[ManagedUserResponse],
)
def get_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_database),
):
    return list_users(
        db,
        organization_id=current_user.organization_id,
    )


@router.post(
    "",
    response_model=ManagedUserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    data: UserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_database),
):
    try:
        return create_member(
            db,
            organization_id=current_user.organization_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
