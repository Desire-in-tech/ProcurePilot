from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import ResearchProvider
from app.models import (
    OfferEvidence,
    Procurement,
    ResearchRun,
    ResearchSource,
    ResearchTask,
    SupplierOffer,
)
from app.research.states import ResearchTaskStatus, ResearchTaskType


SUPPLIER_OFFER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "offers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "supplier_name": {
                        "type": ["string", "null"],
                    },
                    "product_name": {
                        "type": ["string", "null"],
                    },
                    "model": {
                        "type": ["string", "null"],
                    },
                    "price": {
                        "type": ["number", "null"],
                    },
                    "currency": {
                        "type": ["string", "null"],
                    },
                    "availability": {
                        "type": ["string", "null"],
                    },
                    "warranty": {
                        "type": ["string", "null"],
                    },
                    "specifications": {
                        "type": ["object", "null"],
                    },
                },
                "required": [
                    "supplier_name",
                    "product_name",
                ],
            },
        }
    },
    "required": ["offers"],
}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _normalise_offers(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    offers = data.get("offers")

    if not isinstance(offers, list):
        return []

    normalised: list[dict[str, Any]] = []

    for offer in offers:
        if not isinstance(offer, dict):
            continue

        supplier_name = offer.get("supplier_name")
        product_name = offer.get("product_name")

        if not supplier_name or not product_name:
            continue

        specifications = offer.get("specifications")

        if specifications is not None and not isinstance(
            specifications,
            dict,
        ):
            specifications = None

        normalised.append(
            {
                "supplier_name": str(supplier_name),
                "product_name": str(product_name),
                "model": (
                    str(offer["model"])
                    if offer.get("model") is not None
                    else None
                ),
                "price": _decimal_or_none(offer.get("price")),
                "currency": (
                    str(offer["currency"])
                    if offer.get("currency") is not None
                    else None
                ),
                "availability": (
                    str(offer["availability"])
                    if offer.get("availability") is not None
                    else None
                ),
                "warranty": (
                    str(offer["warranty"])
                    if offer.get("warranty") is not None
                    else None
                ),
                "specifications": specifications,
            }
        )

    return normalised


def _evidence_value(field: str, value: Any) -> str:
    if field == "specifications":
        return str(value)

    return str(value)


async def extract_offers_from_sources(
    db: Session,
    run: ResearchRun,
    provider: ResearchProvider,
    sources: list[ResearchSource] | None = None,
) -> list[SupplierOffer]:
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == run.procurement_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    if sources is None:
        sources = list(
            db.scalars(
                select(ResearchSource).where(
                    ResearchSource.research_run_id == run.id,
                )
            )
        )

    task = ResearchTask(
        research_run_id=run.id,
        task_type=ResearchTaskType.EXTRACT_OFFERS.value,
        status=ResearchTaskStatus.RUNNING.value,
        provider=getattr(provider, "name", None),
        input_data={
            "source_count": len(sources),
            "schema": SUPPLIER_OFFER_SCHEMA,
        },
        started_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    created_offers: list[SupplierOffer] = []

    try:
        for source in sources:
            result = await provider.scrape(
                source.url,
                schema=SUPPLIER_OFFER_SCHEMA,
                use_browser=True,
            )

            structured_data = result.structured_data

            job_id = result.metadata.get("job_id")

            if job_id and not structured_data:
                scrape_result = await provider.get_scrape_job(job_id)

                structured_data = scrape_result.structured_data

                if scrape_result.title:
                    source.title = scrape_result.title

                if scrape_result.content:
                    source.raw_content = scrape_result.content

            if not structured_data:
                continue

            offers = _normalise_offers(structured_data)

            for offer_data in offers:
                offer = SupplierOffer(
                    procurement_id=procurement.id,
                    supplier_name=offer_data["supplier_name"],
                    product_name=offer_data["product_name"],
                    model=offer_data["model"],
                    url=source.url,
                    price=offer_data["price"],
                    currency=offer_data["currency"],
                    availability=offer_data["availability"],
                    warranty=offer_data["warranty"],
                    specifications=offer_data["specifications"],
                )

                db.add(offer)
                db.flush()

                evidence_fields = (
                    "supplier_name",
                    "product_name",
                    "model",
                    "price",
                    "currency",
                    "availability",
                    "warranty",
                    "specifications",
                )

                for field in evidence_fields:
                    value = offer_data.get(field)

                    if value is None:
                        continue

                    db.add(
                        OfferEvidence(
                            offer_id=offer.id,
                            source_id=source.id,
                            field=field,
                            value=_evidence_value(field, value),
                            evidence_text=None,
                            confidence=None,
                        )
                    )

                created_offers.append(offer)

        task.status = ResearchTaskStatus.COMPLETED.value
        task.output_data = {
            "source_count": len(sources),
            "offer_count": len(created_offers),
        }
        task.completed_at = datetime.now(timezone.utc)

        db.commit()

        for offer in created_offers:
            db.refresh(offer)

        return created_offers

    except Exception as exc:
        db.rollback()

        failed_task = db.get(ResearchTask, task.id)

        if failed_task is not None:
            failed_task.status = ResearchTaskStatus.FAILED.value
            failed_task.error = str(exc)
            failed_task.completed_at = datetime.now(timezone.utc)

        db.commit()
        raise
