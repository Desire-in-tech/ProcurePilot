from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import ResearchProvider
from app.services.research import await_completed_scrape
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


def _source_hostname(source_url: str | None) -> str | None:
    if not source_url:
        return None

    hostname = urlparse(source_url).hostname

    if not hostname or not str(hostname).strip():
        return None

    return str(hostname)


def _normalise_offer_item(
    offer: Any,
    *,
    supplier_fallback: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(offer, dict):
        return None

    supplier_name = offer.get("supplier_name")
    product_name = offer.get("product_name")

    if not supplier_name:
        supplier_name = supplier_fallback

    if not supplier_name or not product_name:
        return None

    specifications = offer.get("specifications")

    if specifications is not None and not isinstance(
        specifications,
        dict,
    ):
        specifications = None

    return {
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


def _normalise_offer_list(offers: list[Any]) -> list[dict[str, Any]]:
    normalised: list[dict[str, Any]] = []

    for offer in offers:
        item = _normalise_offer_item(offer)

        if item is not None:
            normalised.append(item)

    return normalised


def _normalise_offers(
    data: Any,
    *,
    source_url: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    offers = data.get("offers")

    if isinstance(offers, list):
        return _normalise_offer_list(offers)

    inner = data.get("data")

    if not isinstance(inner, dict):
        return []

    nested_offers = inner.get("offers")

    if isinstance(nested_offers, list):
        return _normalise_offer_list(nested_offers)

    if not inner.get("product_name"):
        return []

    item = _normalise_offer_item(
        inner,
        supplier_fallback=_source_hostname(source_url),
    )

    if item is None:
        return []

    return [item]


def _evidence_value(field: str, value: Any) -> str:
    if field == "specifications":
        return str(value)

    return str(value)


_DIAGNOSTIC_STRING_CAP = 200
_DIAGNOSTIC_LIST_CAP = 3
_DIAGNOSTIC_DEPTH_CAP = 8
_DIAGNOSTIC_JSON_CAP = 8192


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"

    if isinstance(value, bool):
        return "bool"

    if isinstance(value, str):
        return "str"

    if isinstance(value, int):
        return "int"

    if isinstance(value, float):
        return "float"

    if isinstance(value, list):
        return "list"

    if isinstance(value, dict):
        return "object"

    return type(value).__name__


def _truncate_json_value(value: Any, depth: int = 0) -> Any:
    if depth >= _DIAGNOSTIC_DEPTH_CAP:
        return {"_truncated": True, "type": _json_type_name(value)}

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= _DIAGNOSTIC_STRING_CAP:
            return value

        return value[:_DIAGNOSTIC_STRING_CAP] + "…"

    if isinstance(value, list):
        items = [
            _truncate_json_value(item, depth + 1)
            for item in value[:_DIAGNOSTIC_LIST_CAP]
        ]

        if len(value) > _DIAGNOSTIC_LIST_CAP:
            items.append(
                {"_omitted_items": len(value) - _DIAGNOSTIC_LIST_CAP}
            )

        return items

    if isinstance(value, dict):
        return {
            str(key): _truncate_json_value(item, depth + 1)
            for key, item in value.items()
        }

    return str(value)[:_DIAGNOSTIC_STRING_CAP]


def _json_size(value: Any) -> int:
    return len(
        json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
    )


def _cap_diagnostic_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if _json_size(summary) <= _DIAGNOSTIC_JSON_CAP:
        return summary

    capped = dict(summary)
    capped["truncated_payload"] = {
        "omitted": True,
        "reason": "exceeded 8192 bytes",
    }

    if _json_size(capped) <= _DIAGNOSTIC_JSON_CAP:
        return capped

    keys = capped.get("top_level_keys")

    if isinstance(keys, list):
        capped["top_level_keys"] = [str(key)[:80] for key in keys[:30]]

    return capped


def summarize_generated_json(
    data: Any,
    *,
    missing_after_poll: bool = False,
) -> dict[str, Any]:
    """
    Bounded shape summary of an extract scrape's generatedJson.

    Does not keep page markdown. Strings and lists are capped, and the
    summary itself stays within _DIAGNOSTIC_JSON_CAP.
    """
    summary: dict[str, Any] = {
        "top_level_type": _json_type_name(data),
    }

    if data is None:
        summary["note"] = (
            "poll returned no generatedJson"
            if missing_after_poll
            else "null"
        )
        summary["truncated_payload"] = None
        return summary

    if isinstance(data, dict):
        summary["top_level_keys"] = [str(key) for key in data.keys()]
        summary["has_offers"] = "offers" in data
        summary["has_supplier_name"] = "supplier_name" in data
        summary["has_product_name"] = "product_name" in data
        offers = data.get("offers")

        if isinstance(offers, list):
            summary["offer_count"] = len(offers)

            if offers and isinstance(offers[0], dict):
                summary["first_item_keys"] = [
                    str(key) for key in offers[0].keys()
                ]
                summary["first_item_has_supplier_name"] = (
                    "supplier_name" in offers[0]
                )
                summary["first_item_has_product_name"] = (
                    "product_name" in offers[0]
                )
    elif isinstance(data, list):
        summary["item_count"] = len(data)

        if data and isinstance(data[0], dict):
            summary["first_item_keys"] = [
                str(key) for key in data[0].keys()
            ]

    try:
        payload = copy.deepcopy(data)
    except Exception:
        payload = data

    summary["truncated_payload"] = _truncate_json_value(payload)
    return _cap_diagnostic_summary(summary)


def _fit_extraction_diagnostics(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if _json_size(entries) <= _DIAGNOSTIC_JSON_CAP:
        return entries

    fitted: list[dict[str, Any]] = []

    for entry in entries:
        generated = dict(entry.get("generated_json") or {})
        generated["truncated_payload"] = {
            "omitted": True,
            "reason": "extraction_diagnostics exceeded 8192 bytes",
        }
        fitted.append({**entry, "generated_json": generated})

    if _json_size(fitted) <= _DIAGNOSTIC_JSON_CAP:
        return fitted

    kept: list[dict[str, Any]] = []

    for entry in fitted:
        candidate = [*kept, entry]

        if kept and _json_size(candidate) > _DIAGNOSTIC_JSON_CAP:
            break

        kept.append(entry)

    omitted = len(entries) - len(kept)

    if omitted:
        kept.append({"omitted_entries": omitted})

    return kept


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
    diagnostics: list[dict[str, Any]] = []

    try:
        for source in sources:
            result = await provider.scrape(
                source.url,
                schema=SUPPLIER_OFFER_SCHEMA,
                use_browser=True,
            )

            structured_data = result.structured_data

            job_id = result.metadata.get("job_id")
            missing_after_poll = False

            if job_id and not structured_data:
                task.external_job_id = str(job_id)
                scrape_result = await await_completed_scrape(
                    provider,
                    job_id,
                )

                structured_data = scrape_result.structured_data
                missing_after_poll = structured_data is None
                polled_job_id = scrape_result.metadata.get("job_id")

                if polled_job_id:
                    job_id = polled_job_id
                    task.external_job_id = str(job_id)

                if scrape_result.title:
                    source.title = scrape_result.title

                if scrape_result.content:
                    source.raw_content = scrape_result.content
            elif job_id:
                task.external_job_id = str(job_id)

            diagnostics.append(
                {
                    "source_id": str(source.id),
                    "url": source.url,
                    "job_id": None if not job_id else str(job_id),
                    "generated_json": summarize_generated_json(
                        structured_data,
                        missing_after_poll=missing_after_poll,
                    ),
                }
            )

            if not structured_data:
                continue

            offers = _normalise_offers(
                structured_data,
                source_url=source.url,
            )

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
            **(task.output_data or {}),
            "source_count": len(sources),
            "offer_count": len(created_offers),
            "extraction_diagnostics": _fit_extraction_diagnostics(
                diagnostics,
            ),
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
