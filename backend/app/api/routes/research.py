from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.anakin import AnakinProvider
from app.core.config import settings
from app.dependencies import get_current_user, get_database
from app.models import (
    OfferEvidence,
    ResearchRun,
    ResearchSource,
    ResearchTask,
    SupplierOffer,
    User,
)
from app.research.states import ResearchTaskType
from app.schemas.research import (
    ResearchEvidenceResponse,
    ResearchOfferResponse,
    ResearchRunCreated,
    ResearchRunResponse,
)
from app.services.procurement import get_procurement
from app.services.research_orchestrator import start_research


router = APIRouter(
    prefix="/api/v1/procurements",
    tags=["Research"],
)


def _latest_run(
    db: Session,
    procurement_id: UUID,
) -> ResearchRun | None:
    return db.scalar(
        select(ResearchRun)
        .where(ResearchRun.procurement_id == procurement_id)
        .order_by(ResearchRun.created_at.desc())
    )


def _task_output(
    db: Session,
    run_id: UUID,
    task_type: str,
) -> dict | None:
    task = db.scalar(
        select(ResearchTask)
        .where(
            ResearchTask.research_run_id == run_id,
            ResearchTask.task_type == task_type,
        )
        .order_by(ResearchTask.created_at.desc())
    )

    if task is None or task.output_data is None:
        return None

    return task.output_data


def _offers_for_run(
    db: Session,
    run_id: UUID,
) -> list[SupplierOffer]:
    """
    Offers have no research_run_id. Extraction stores OfferEvidence
    against the ResearchSource for this run, and that source has
    research_run_id.
    """
    offer_ids = (
        select(OfferEvidence.offer_id)
        .join(ResearchSource)
        .where(ResearchSource.research_run_id == run_id)
    )

    return list(
        db.scalars(
            select(SupplierOffer)
            .where(SupplierOffer.id.in_(offer_ids))
            .order_by(SupplierOffer.created_at.asc())
        ).all()
    )


def _offer_response(
    offer: SupplierOffer,
    run_id: UUID,
) -> ResearchOfferResponse:
    evidence: list[ResearchEvidenceResponse] = []

    for item in offer.evidence:
        source = item.source

        if source.research_run_id != run_id:
            continue

        evidence.append(
            ResearchEvidenceResponse(
                id=item.id,
                field=item.field,
                value=item.value,
                evidence_text=item.evidence_text,
                confidence=(
                    None
                    if item.confidence is None
                    else str(item.confidence)
                ),
                source_id=item.source_id,
                source_url=source.url,
                source_title=source.title,
            )
        )

    return ResearchOfferResponse(
        id=offer.id,
        supplier_name=offer.supplier_name,
        product_name=offer.product_name,
        model=offer.model,
        url=offer.url,
        price=None if offer.price is None else str(offer.price),
        currency=offer.currency,
        availability=offer.availability,
        warranty=offer.warranty,
        specifications=offer.specifications,
        matching_result=offer.matching_result,
        evidence=evidence,
    )


@router.post(
    "/{procurement_id}/research",
    response_model=ResearchRunCreated,
)
async def start(
    procurement_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    procurement = get_procurement(
        db=db,
        organization_id=current_user.organization_id,
        procurement_id=procurement_id,
    )

    if procurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procurement not found",
        )

    if procurement.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only approved procurements can start research",
        )

    if not settings.anakin_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anakin API key is not configured",
        )

    provider = AnakinProvider(settings.anakin_api_key)

    try:
        run, sources = await start_research(
            db,
            procurement.id,
            provider,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        failed_run = _latest_run(db, procurement.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(exc),
                "research_run_id": (
                    None if failed_run is None else str(failed_run.id)
                ),
                "status": None if failed_run is None else failed_run.status,
            },
        ) from exc

    return ResearchRunCreated(
        research_run_id=run.id,
        procurement_id=procurement.id,
        status=run.status,
        source_ids=[source.id for source in sources],
    )


@router.get(
    "/{procurement_id}/research",
    response_model=ResearchRunResponse,
)
def get_result(
    procurement_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    procurement = get_procurement(
        db=db,
        organization_id=current_user.organization_id,
        procurement_id=procurement_id,
    )

    if procurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procurement not found",
        )

    run = _latest_run(db, procurement.id)

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No research run found",
        )

    offers = _offers_for_run(db, run.id)

    return ResearchRunResponse(
        research_run_id=run.id,
        procurement_id=procurement.id,
        status=run.status,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        offers=[_offer_response(offer, run.id) for offer in offers],
        compare_offers=_task_output(
            db,
            run.id,
            ResearchTaskType.COMPARE_OFFERS.value,
        ),
        recommendation=_task_output(
            db,
            run.id,
            ResearchTaskType.GENERATE_RECOMMENDATION.value,
        ),
    )
