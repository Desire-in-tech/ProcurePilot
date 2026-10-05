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


_NEGATION_TOKENS = frozenset(
    {"no", "not", "without", "non", "none", "na"}
)
_AMBIGUOUS_TOKENS = frozenset(
    {"pending", "unknown", "unclear", "tbd", "maybe", "unspecified"}
)


def _mentions_warranty(requirement: Requirement, expected_text: str) -> bool:
    return (
        "warranty" in _normalise_text(requirement.name)
        or "warranty" in _normalise_text(requirement.category)
        or "warranty" in expected_text
    )


def _text_tokens(value: str) -> list[str]:
    return re.findall(
        r"[a-z0-9]+",
        _normalise_text(value).replace("n/a", "na"),
    )


def _containment_status(expected_text: str, actual_text: str) -> str:
    """
    Judge a positive text claim.

    not_met: the phrase is absent, a negation token is immediately
    before it, or it is followed by "not included" or "excluded".
    unknown: the phrase is present but not safely affirmative. A single
    negation token immediately after the phrase is unknown, because
    punctuation between clauses is lost during tokenizing.
    met: the phrase is present and affirmative.
    """
    if not expected_text or expected_text not in actual_text:
        return "not_met"

    expected_tokens = _text_tokens(expected_text)
    actual_tokens = _text_tokens(actual_text)

    if not expected_tokens:
        return "not_met"

    width = len(expected_tokens)

    for index in range(len(actual_tokens) - width + 1):
        if actual_tokens[index:index + width] != expected_tokens:
            continue

        before = actual_tokens[index - 1] if index else None
        after = actual_tokens[index + width:]

        if before in _NEGATION_TOKENS:
            return "not_met"

        if after[:2] == ["not", "included"]:
            return "not_met"

        if after and after[0] == "excluded":
            return "not_met"

        if after and after[0] in _NEGATION_TOKENS:
            return "unknown"

        if before in _AMBIGUOUS_TOKENS or (
            after and after[0] in _AMBIGUOUS_TOKENS
        ):
            return "unknown"

        return "met"

    return "unknown"


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

    items = [
        (_normalise_text(key), value)
        for key, value in specifications.items()
    ]

    for key, value in items:
        if key in candidates:
            return value, key

    def contains_sequence(haystack: list[str], needle: list[str]) -> bool:
        width = len(needle)

        if not needle or width > len(haystack):
            return False

        return any(
            haystack[index:index + width] == needle
            for index in range(len(haystack) - width + 1)
        )

    # Whole tokens only. "ram" is a token of "system ram" and of
    # "ram size", and "battery" is a token of requirement "battery life".
    # It is not a token of "program" or "framebuffer".
    for key, value in items:
        key_tokens = _text_tokens(key)

        if not key_tokens:
            continue

        for candidate in candidates:
            candidate_tokens = _text_tokens(candidate)

            if not candidate_tokens:
                continue

            if contains_sequence(key_tokens, candidate_tokens) or (
                contains_sequence(candidate_tokens, key_tokens)
            ):
                return value, key

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

    warranty_column = False

    if actual is None and _mentions_warranty(requirement, expected_text):
        if offer.warranty and str(offer.warranty).strip():
            actual = offer.warranty
            warranty_column = True
            # Same lookup key the old fallback used: the requirement name.
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

    # A unit is not an operator. Ram/memory, storage/ssd, and
    # warranty stay minimums, including a qualified value such as
    # "32GB DDR5". Prose under those keys can still match on its
    # first number. Any other operator-less number that carries a
    # unit is ambiguous. Outside those categories, and without an
    # explicit operator, numbers are not compared.
    if (
        expected_number is not None
        and actual_number is not None
        and explicit_operator is None
        and requirement.unit
        and _normalise_text(requirement.unit)
        and not _uses_keyword_minimum(expected_text, specification_key)
    ):
        evidence = _matching_evidence(
            db,
            offer,
            specification_key or requirement.name,
        )
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

    if expected_number is not None and actual_number is not None and (
        explicit_operator is not None
        or _uses_keyword_minimum(expected_text, specification_key)
    ):
        evidence = _matching_evidence(
            db,
            offer,
            specification_key or requirement.name,
        )

        if explicit_operator is not None:
            operator = explicit_operator
        else:
            operator = ">="

        status = (
            "met"
            if _compare_numbers(actual_number, expected_number, operator)
            else "not_met"
        )
        reason = _comparison_reason(operator, met=status == "met")

        if status == "met" and (
            _mentions_warranty(requirement, expected_text)
            or "warranty" in _normalise_text(specification_key)
        ):
            support = _containment_status(
                expected_text,
                _normalise_text(actual),
            )
            if support == "not_met" and expected_text in _normalise_text(
                actual
            ):
                status = "not_met"
                reason = "Supplier claim is negated."
            elif support == "unknown":
                status = "unknown"
                reason = "Supplier claim is not clearly affirmative."

        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": status,
            "reason": reason,
            "expected": expected,
            "actual": actual,
            "evidence": _evidence_payload(evidence),
        }

    actual_text = _normalise_text(actual)

    if (
        warranty_column
        and expected_number is not None
        and actual_number is None
        and expected_text not in actual_text
    ):
        return {
            "requirement_id": str(requirement.id),
            "requirement": requirement.name,
            "status": "unknown",
            "reason": "No matching supplier evidence was found.",
            "expected": expected,
            "actual": actual,
            "evidence": None,
        }

    # Both sides have a number, there is no explicit operator, and this
    # is not a keyword minimum. The unit-ambiguous return above did not
    # fire, and price never reaches here. Keep the text-path met result
    # only when the claim is affirmative and the first numbers are equal.
    # Otherwise the comparison is not reliable.
    if (
        expected_number is not None
        and actual_number is not None
        and explicit_operator is None
        and not _uses_keyword_minimum(expected_text, specification_key)
    ):
        if not (
            _containment_status(expected_text, actual_text) == "met"
            and _compare_numbers(actual_number, expected_number, "=")
        ):
            evidence = _matching_evidence(
                db,
                offer,
                specification_key or requirement.name,
            )
            return {
                "requirement_id": str(requirement.id),
                "requirement": requirement.name,
                "status": "unknown",
                "reason": "Supplier value could not be reliably compared.",
                "expected": expected,
                "actual": actual,
                "evidence": _evidence_payload(evidence),
            }

    status = _containment_status(expected_text, actual_text)
    if status == "met":
        reason = "Supplier evidence matches the requirement."
    elif status == "unknown":
        reason = "Supplier claim is not clearly affirmative."
    elif expected_text in actual_text:
        status = "not_met"
        reason = "Supplier claim is negated."
    else:
        reason = "Supplier evidence does not match the requirement."

    evidence = _matching_evidence(
        db,
        offer,
        specification_key or requirement.name,
    )

    return {
        "requirement_id": str(requirement.id),
        "requirement": requirement.name,
        "status": status,
        "reason": reason,
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
