from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    OfferEvidence,
    Procurement,
    Requirement,
    SupplierOffer,
)
from app.models.research import ResearchRun


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _extract_number(value: Any) -> Decimal | None:
    if value is None:
        return None

    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None

    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _find_specification(
    offer: SupplierOffer,
    requirement: Requirement,
) -> tuple[Any, str | None]:
    specifications = offer.specifications or {}

    requirement_name = _normalise_text(requirement.name)
    requirement_category = _normalise_text(requirement.category)

    aliases = {
        "ram": {"ram", "memory", "memory size"},
        "storage": {"storage", "ssd", "disk", "disk storage"},
        "warranty": {"warranty"},
        "cpu": {"cpu", "processor", "processor type"},
        "screen": {"screen", "display", "display size"},
    }

    candidates = {
        requirement_name,
        requirement_category,
    }

    for canonical, names in aliases.items():
        if requirement_name in names or requirement_category in names:
            candidates.add(canonical)
            candidates.update(names)

    for key, value in specifications.items():
        normalised_key = _normalise_text(key)

        if normalised_key in candidates:
            return value, normalised_key

        if any(
            candidate and (
                candidate in normalised_key
                or normalised_key in candidate
            )
            for candidate in candidates
        ):
            return value, normalised_key

    return None, None


def _matching_evidence(
    db: Session,
    offer: SupplierOffer,
    field: str,
) -> OfferEvidence | None:
    statement = (
        select(OfferEvidence)
        .where(
            OfferEvidence.offer_id == offer.id,
            OfferEvidence.field == field,
        )
        .order_by(OfferEvidence.created_at.desc())
    )

    return db.scalar(statement)


def _evaluate_requirement(
    db: Session,
    offer: SupplierOffer,
    requirement: Requirement,
) -> dict[str, Any]:
    expected = requirement.value

    if expected is None:
        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": "unknown",
            "reason": "Requirement has no expected value.",
            "expected": None,
            "actual": None,
            "evidence": None,
        }

    expected_text = _normalise_text(expected)

    actual, specification_key = _find_specification(
        offer,
        requirement,
    )

    if actual is None:
        combined_text = " ".join(
            filter(
                None,
                [
                    offer.product_name,
                    offer.model,
                    offer.availability,
                    offer.warranty,
                    str(offer.specifications or {}),
                ],
            )
        )

        if expected_text in _normalise_text(combined_text):
            actual = expected
            specification_key = requirement.name

    if actual is None:
        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": "unknown",
            "reason": "No matching supplier evidence was found.",
            "expected": expected,
            "actual": None,
            "evidence": None,
        }

    expected_number = _extract_number(expected)
    actual_number = _extract_number(actual)

    if expected_number is not None and actual_number is not None:
        expected_unit = _normalise_text(requirement.unit)

        if (
            "ram" in expected_text
            or "memory" in expected_text
            or "ram" in _normalise_text(specification_key)
        ):
            status = (
                "met"
                if actual_number >= expected_number
                else "not_met"
            )
        elif (
            "storage" in expected_text
            or "ssd" in expected_text
            or "storage" in _normalise_text(specification_key)
        ):
            status = (
                "met"
                if actual_number >= expected_number
                else "not_met"
            )
        elif "warranty" in expected_text or "warranty" in _normalise_text(
            specification_key
        ):
            status = (
                "met"
                if actual_number >= expected_number
                else "not_met"
            )
        elif expected_unit:
            status = (
                "met"
                if actual_number >= expected_number
                else "not_met"
            )
        else:
            status = (
                "met"
                if actual_number == expected_number
                else "not_met"
            )

        evidence = _matching_evidence(
            db,
            offer,
            specification_key or requirement.name,
        )

        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": status,
            "reason": (
                "Supplier value satisfies the required threshold."
                if status == "met"
                else "Supplier value is below the required threshold."
            ),
            "expected": expected,
            "actual": actual,
            "evidence": (
                {
                    "source_id": str(evidence.source_id),
                    "field": evidence.field,
                }
                if evidence is not None
                else None
            ),
        }

    actual_text = _normalise_text(actual)

    status = "met" if expected_text in actual_text else "not_met"

    evidence = _matching_evidence(
        db,
        offer,
        specification_key or requirement.name,
    )

    return {
        "requirement_id": str(requirement.id),
        "requirement": requirement.name,
        "status": status,
        "reason": (
            "Supplier evidence matches the requirement."
            if status == "met"
            else "Supplier evidence does not match the requirement."
        ),
        "expected": expected,
        "actual": actual,
        "evidence": (
            {
                "source_id": str(evidence.source_id),
                "field": evidence.field,
            }
            if evidence is not None
            else None
        ),
    }


async def verify_offers(
    db: Session,
    run: ResearchRun,
) -> list[SupplierOffer]:
    procurement = db.scalar(
        select(Procurement).where(
            Procurement.id == run.procurement_id,
        )
    )

    if procurement is None:
        raise ValueError("Procurement not found")

    requirements = list(
        db.scalars(
            select(Requirement)
            .where(
                Requirement.procurement_id == procurement.id,
            )
            .order_by(Requirement.created_at.asc())
        ).all()
    )

    offers = list(
        db.scalars(
            select(SupplierOffer)
            .where(
                SupplierOffer.procurement_id == procurement.id,
            )
            .order_by(SupplierOffer.created_at.asc())
        ).all()
    )

    for offer in offers:
        results = [
            _evaluate_requirement(db, offer, requirement)
            for requirement in requirements
        ]

        mandatory_results = [
            result
            for result, requirement in zip(results, requirements)
            if requirement.is_mandatory
        ]

        mandatory_met = sum(
            result["status"] == "met"
            for result in mandatory_results
        )

        mandatory_total = len(mandatory_results)

        if any(
            result["status"] == "not_met"
            for result in mandatory_results
        ):
            overall_status = "not_eligible"
        elif any(
            result["status"] == "unknown"
            for result in mandatory_results
        ):
            overall_status = "needs_review"
        else:
            overall_status = "eligible"

        offer.matching_result = {
            "status": overall_status,
            "mandatory_requirements_met": mandatory_met,
            "mandatory_requirements_total": mandatory_total,
            "requirements": results,
        }

    db.commit()

    for offer in offers:
        db.refresh(offer)

    return offers
