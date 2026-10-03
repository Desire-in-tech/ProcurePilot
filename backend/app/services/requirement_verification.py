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


# Longer tokens first so ">=" is not read as ">".
_LEADING_OPERATORS = (">=", "<=", ">", "<", "=")

# Exact normalised name or category. Not a substring match.
_PRICE_REQUIREMENT_LABELS = frozenset(
    {"price", "budget", "cost", "price cap", "price-cap"}
)


def _parse_leading_operator(value: str) -> str | None:
    text = value.strip()

    for operator in _LEADING_OPERATORS:
        if text.startswith(operator):
            return operator

    return None


def _is_price_requirement(requirement: Requirement) -> bool:
    labels = {
        _normalise_text(requirement.name),
        _normalise_text(requirement.category),
    }
    return bool(labels & _PRICE_REQUIREMENT_LABELS)


def _uses_keyword_minimum(
    expected_text: str,
    specification_key: str | None,
) -> bool:
    key = _normalise_text(specification_key)

    if (
        "ram" in expected_text
        or "memory" in expected_text
        or "ram" in key
    ):
        return True

    if (
        "storage" in expected_text
        or "ssd" in expected_text
        or "storage" in key
    ):
        return True

    if "warranty" in expected_text or "warranty" in key:
        return True

    return False


def _compare_numbers(
    actual: Decimal,
    expected: Decimal,
    operator: str,
) -> bool:
    if operator == ">=":
        return actual >= expected
    if operator == "<=":
        return actual <= expected
    if operator == ">":
        return actual > expected
    if operator == "<":
        return actual < expected
    return actual == expected


def _comparison_reason(
    operator: str,
    *,
    met: bool,
    is_price: bool = False,
) -> str:
    if operator in {"<=", "<"}:
        subject = "price" if is_price else "value"
        if met:
            return f"Supplier {subject} is within the maximum allowed {subject}."
        return f"Supplier {subject} exceeds the maximum allowed {subject}."

    if operator in {">=", ">"}:
        if is_price:
            if met:
                return "Supplier price meets the required minimum."
            return "Supplier price is below the required minimum."
        if met:
            return "Supplier value meets the required minimum."
        return "Supplier value is below the required minimum."

    if is_price:
        if met:
            return "Supplier price equals the required value."
        return "Supplier price does not equal the required value."

    if met:
        return "Supplier value equals the required value."

    return "Supplier value does not equal the required value."


def _evidence_payload(evidence: OfferEvidence | None) -> dict[str, str] | None:
    if evidence is None:
        return None

    return {
        "source_id": str(evidence.source_id),
        "field": evidence.field,
    }


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


def _evaluate_price_requirement(
    db: Session,
    offer: SupplierOffer,
    requirement: Requirement,
    explicit_operator: str | None,
) -> dict[str, Any]:
    """
    Compare offer.price with a price, budget, cost, or price-cap requirement.

    Detection is an exact match of the normalised name or category against
    price, budget, cost, price cap, or price-cap. The numeric actual is
    offer.price, not a specification entry. An explicit leading operator
    wins. Without one, the comparison is <=.
    """
    expected = requirement.value
    unit = _normalise_text(requirement.unit)
    currency = _normalise_text(offer.currency)

    if unit and currency and unit != currency:
        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": "unknown",
            "reason": "Requirement unit does not match the offer currency.",
            "expected": expected,
            "actual": None if offer.price is None else str(offer.price),
            "evidence": None,
        }

    expected_number = _extract_number(expected)

    if expected_number is None or offer.price is None:
        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": "unknown",
            "reason": "No offer price could be compared with the requirement.",
            "expected": expected,
            "actual": None if offer.price is None else str(offer.price),
            "evidence": None,
        }

    _, specification_key = _find_specification(offer, requirement)
    operator = explicit_operator or "<="
    status = (
        "met"
        if _compare_numbers(offer.price, expected_number, operator)
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
        "reason": _comparison_reason(
            operator,
            met=status == "met",
            is_price=True,
        ),
        "expected": expected,
        "actual": str(offer.price),
        "evidence": _evidence_payload(evidence),
    }


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

    explicit_operator = _parse_leading_operator(str(expected))

    if _is_price_requirement(requirement):
        return _evaluate_price_requirement(
            db,
            offer,
            requirement,
            explicit_operator,
        )

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
        evidence = _matching_evidence(
            db,
            offer,
            specification_key or requirement.name,
        )

        # A unit is not an operator. Ram/memory, storage/ssd, and
        # warranty stay minimums. Any other operator-less number
        # that carries a unit is ambiguous. Operator-less numbers
        # without a unit stay equality.
        if (
            explicit_operator is None
            and requirement.unit
            and _normalise_text(requirement.unit)
            and not _uses_keyword_minimum(expected_text, specification_key)
        ):
            return {
                "requirement_id": str(requirement.id),
                "requirement": requirement.name,
                "status": "unknown",
                "reason": (
                    "Comparison is ambiguous because no operator "
                    "was provided."
                ),
                "expected": expected,
                "actual": actual,
                "evidence": _evidence_payload(evidence),
            }

        if explicit_operator is not None:
            operator = explicit_operator
        elif _uses_keyword_minimum(expected_text, specification_key):
            operator = ">="
        else:
            operator = "="

        status = (
            "met"
            if _compare_numbers(actual_number, expected_number, operator)
            else "not_met"
        )

        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": status,
            "reason": _comparison_reason(operator, met=status == "met"),
            "expected": expected,
            "actual": actual,
            "evidence": _evidence_payload(evidence),
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
