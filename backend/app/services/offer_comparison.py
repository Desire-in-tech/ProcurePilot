from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    OfferEvidence,
    Procurement,
    SupplierOffer,
)
from app.models.research import ResearchRun, ResearchTask
from app.research.states import ResearchTaskStatus, ResearchTaskType


STATUS_PRIORITY = {
    "eligible": 0,
    "needs_review": 1,
    "not_eligible": 2,
}


def _status_priority(status: str | None) -> int:
    return STATUS_PRIORITY.get(status or "needs_review", 1)


def _mandatory_ratio(result: dict[str, Any]) -> float:
    total = result.get("mandatory_requirements_total", 0)
    if not total:
        return 0.0

    met = result.get("mandatory_requirements_met", 0)
    return met / total


def _evidence_count(db: Session, offer_id) -> int:
    statement = select(OfferEvidence).where(
        OfferEvidence.offer_id == offer_id,
    )
    return len(db.scalars(statement).all())


def _currency_groups(
    offers: list[SupplierOffer],
) -> dict[str, list[SupplierOffer]]:
    groups: dict[str, list[SupplierOffer]] = {}

    for offer in offers:
        if offer.price is None or not offer.currency:
            continue

        currency = offer.currency.upper()
        groups.setdefault(currency, []).append(offer)

    return groups


def _price_rank(
    offer: SupplierOffer,
    currency_offers: list[SupplierOffer],
) -> int | None:
    if offer.price is None:
        return None

    ordered = sorted(
        currency_offers,
        key=lambda item: item.price
        if item.price is not None
        else Decimal("Infinity"),
    )

    for index, candidate in enumerate(ordered, start=1):
        if candidate.id == offer.id:
            return index

    return None


async def compare_offers(
    db: Session,
    run: ResearchRun,
) -> list[dict[str, Any]]:
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == run.procurement_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    offers = list(
        db.scalars(
            select(SupplierOffer)
            .where(
                SupplierOffer.procurement_id == procurement.id,
            )
            .order_by(SupplierOffer.created_at.asc())
        ).all()
    )

    task = ResearchTask(
        research_run_id=run.id,
        task_type=ResearchTaskType.COMPARE_OFFERS.value,
        status=ResearchTaskStatus.RUNNING.value,
        provider="internal",
        input_data={
            "offer_count": len(offers),
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        currency_groups = _currency_groups(offers)
        comparisons: list[dict[str, Any]] = []

        for offer in offers:
            matching_result = offer.matching_result or {}
            status = matching_result.get("status", "needs_review")
            evidence_count = _evidence_count(db, offer.id)

            comparable_prices = currency_groups.get(
                offer.currency.upper()
                if offer.currency
                else "",
                [],
            )

            price_rank = _price_rank(
                offer,
                comparable_prices,
            )

            comparisons.append(
                {
                    "offer_id": str(offer.id),
                    "supplier_name": offer.supplier_name,
                    "product_name": offer.product_name,
                    "model": offer.model,
                    "status": status,
                    "mandatory_requirements_met": matching_result.get(
                        "mandatory_requirements_met",
                        0,
                    ),
                    "mandatory_requirements_total": matching_result.get(
                        "mandatory_requirements_total",
                        0,
                    ),
                    "mandatory_requirement_ratio": _mandatory_ratio(
                        matching_result,
                    ),
                    "evidence_count": evidence_count,
                    "price": (
                        str(offer.price)
                        if offer.price is not None
                        else None
                    ),
                    "currency": offer.currency,
                    "price_rank": price_rank,
                    "availability": offer.availability,
                    "warranty": offer.warranty,
                }
            )

        comparisons.sort(
            key=lambda item: (
                _status_priority(item["status"]),
                -item["mandatory_requirement_ratio"],
                -item["evidence_count"],
                (
                    item["price_rank"]
                    if item["price_rank"] is not None
                    else 999999
                ),
            )
        )

        for rank, comparison in enumerate(comparisons, start=1):
            comparison["rank"] = rank

        task.status = ResearchTaskStatus.COMPLETED.value
        task.output_data = {
            "offer_count": len(comparisons),
            "ranked_offer_ids": [
                comparison["offer_id"]
                for comparison in comparisons
            ],
        }
        db.commit()
        db.refresh(task)

        return comparisons

    except Exception as exc:
        db.rollback()

        task = db.get(ResearchTask, task.id)

        if task is not None:
            task.status = ResearchTaskStatus.FAILED.value
            task.error = str(exc)
            db.commit()

        raise
