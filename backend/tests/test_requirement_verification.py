import uuid
from decimal import Decimal

import pytest

from app.db.database import SessionLocal
from app.models import (
    OfferEvidence,
    Organization,
    Procurement,
    Requirement,
    ResearchRun,
    ResearchSource,
    SupplierOffer,
)
from app.services.requirement_verification import (
    _containment_status,
    verify_offers,
)


def create_organization(db):
    organization = Organization(
        name="Verification Test Org",
        slug=f"verification-{uuid.uuid4().hex[:12]}",
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def cleanup(db, organization_id):
    organization = db.get(Organization, organization_id)

    if organization is not None:
        db.delete(organization)

    db.commit()


@pytest.mark.asyncio
async def test_verify_offer_marks_matching_requirements_as_eligible():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Engineering Laptops",
            description="25 laptops for engineering",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        requirement_ram = Requirement(
            procurement_id=procurement.id,
            name="RAM",
            value="16GB",
            unit="GB",
            is_mandatory=True,
        )

        requirement_storage = Requirement(
            procurement_id=procurement.id,
            name="Storage",
            value="512GB",
            unit="GB",
            is_mandatory=True,
        )

        requirement_warranty = Requirement(
            procurement_id=procurement.id,
            name="Warranty",
            value="3 years",
            unit="years",
            is_mandatory=True,
        )

        db.add_all(
            [
                requirement_ram,
                requirement_storage,
                requirement_warranty,
            ]
        )
        db.commit()

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        source = ResearchSource(
            research_run_id=run.id,
            url="https://example.com/laptop",
            title="Business Laptop Pro 14",
            source_type="supplier",
            provider="mock",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Nordic Tech Supply",
            product_name="Business Laptop Pro 14",
            model="BLP14",
            price=Decimal("1180.00"),
            currency="EUR",
            availability="In stock",
            warranty="3 years",
            specifications={
                "ram": "16GB",
                "storage": "512GB SSD",
            },
            evidence=[
                OfferEvidence(
                    source_id=source.id,
                    field="ram",
                    value="16GB",
                ),
                OfferEvidence(
                    source_id=source.id,
                    field="storage",
                    value="512GB SSD",
                ),
                OfferEvidence(
                    source_id=source.id,
                    field="warranty",
                    value="3 years",
                ),
            ],
        )

        db.add(offer)
        db.commit()
        db.refresh(offer)

        offers = await verify_offers(db, run)

        assert len(offers) == 1

        result = offers[0].matching_result

        assert result["status"] == "eligible"
        assert result["mandatory_requirements_met"] == 3
        assert result["mandatory_requirements_total"] == 3

        statuses = {
            item["requirement"]: item["status"]
            for item in result["requirements"]
        }

        assert statuses == {
            "RAM": "met",
            "Storage": "met",
            "Warranty": "met",
        }

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_verify_offer_marks_failed_mandatory_requirement_not_eligible():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Engineering Laptops",
            description="Engineering laptops",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        db.add(
            Requirement(
                procurement_id=procurement.id,
                name="RAM",
                value="32GB",
                unit="GB",
                is_mandatory=True,
            )
        )
        db.commit()

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        source = ResearchSource(
            research_run_id=run.id,
            url="https://example.com/laptop",
            title="Laptop",
            source_type="supplier",
            provider="mock",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        offer = SupplierOffer(
            procurement_id=procurement.id,
            supplier_name="Supplier A",
            product_name="Laptop A",
            specifications={"ram": "16GB"},
            evidence=[
                OfferEvidence(
                    source_id=source.id,
                    field="ram",
                    value="16GB",
                )
            ],
        )
        db.add(offer)
        db.commit()

        offers = await verify_offers(db, run)

        result = offers[0].matching_result

        assert result["status"] == "not_eligible"
        assert result["mandatory_requirements_met"] == 0

        assert result["requirements"][0]["status"] == "not_met"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_verify_offer_marks_missing_evidence_for_review():
    db = SessionLocal()
    organization = None

    try:
        organization = create_organization(db)

        procurement = Procurement(
            organization_id=organization.id,
            title="Laptops",
            description="Laptop procurement",
            status="approved",
        )
        db.add(procurement)
        db.commit()
        db.refresh(procurement)

        db.add(
            Requirement(
                procurement_id=procurement.id,
                name="Warranty",
                value="3 years",
                unit="years",
                is_mandatory=True,
            )
        )
        db.commit()

        run = ResearchRun(
            procurement_id=procurement.id,
            status="executing",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        db.add(
            SupplierOffer(
                procurement_id=procurement.id,
                supplier_name="Supplier A",
                product_name="Laptop A",
                specifications={
                    "ram": "16GB",
                },
            )
        )
        db.commit()

        offers = await verify_offers(db, run)

        result = offers[0].matching_result

        assert result["status"] == "needs_review"
        assert result["requirements"][0]["status"] == "unknown"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


async def verify_requirements(db, requirements, offers):
    """
    Create one procurement and verify the given offers.

    No OfferEvidence rows are created. Requirement status does not
    read those rows, so these cases do not depend on evidence keys.
    """
    organization = create_organization(db)
    procurement = Procurement(
        organization_id=organization.id,
        title="Engineering Laptops",
        description="Laptop procurement",
        status="approved",
    )
    db.add(procurement)
    db.commit()
    db.refresh(procurement)

    for requirement in requirements:
        db.add(Requirement(procurement_id=procurement.id, **requirement))

    run = ResearchRun(
        procurement_id=procurement.id,
        status="executing",
    )
    db.add(run)

    for offer in offers:
        db.add(
            SupplierOffer(
                procurement_id=procurement.id,
                supplier_name=offer.get("supplier_name", "Supplier A"),
                product_name=offer.get("product_name", "Laptop A"),
                model=offer.get("model"),
                price=offer.get("price"),
                currency=offer.get("currency"),
                warranty=offer.get("warranty"),
                specifications=offer.get("specifications"),
            )
        )

    db.commit()
    verified = await verify_offers(db, run)
    return organization, verified


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "name",
        "value",
        "unit",
        "price",
        "specifications",
        "requirement_status",
        "offer_status",
    ),
    [
        (
            "Budget",
            "<= 1200",
            "EUR",
            Decimal("1500"),
            None,
            "not_met",
            "not_eligible",
        ),
        (
            "Budget",
            "<= 1200",
            "EUR",
            Decimal("1100"),
            None,
            "met",
            "eligible",
        ),
        (
            "Budget",
            "1200",
            "EUR",
            Decimal("1500"),
            None,
            "not_met",
            "not_eligible",
        ),
        (
            "Budget",
            "1200",
            "EUR",
            Decimal("1100"),
            None,
            "met",
            "eligible",
        ),
        (
            "RAM",
            ">= 16",
            "GB",
            None,
            {"ram": "8GB"},
            "not_met",
            "not_eligible",
        ),
        (
            "RAM",
            ">= 16",
            "GB",
            None,
            {"ram": "16GB"},
            "met",
            "eligible",
        ),
        (
            "RAM",
            ">= 16",
            "GB",
            None,
            {"ram": "32GB"},
            "met",
            "eligible",
        ),
        (
            "RAM",
            "= 16",
            "GB",
            None,
            {"ram": "16GB"},
            "met",
            "eligible",
        ),
        (
            "RAM",
            "= 16",
            "GB",
            None,
            {"ram": "32GB"},
            "not_met",
            "not_eligible",
        ),
        (
            "RAM",
            "16GB",
            "GB",
            None,
            {"ram": "32GB"},
            "met",
            "eligible",
        ),
        (
            "Weight",
            "2",
            "kg",
            None,
            {"weight": "5"},
            "unknown",
            "needs_review",
        ),
        (
            "Weight",
            "<= 2",
            "kg",
            None,
            {"weight": "5"},
            "not_met",
            "not_eligible",
        ),
        (
            "Battery life",
            "10",
            "hours",
            None,
            {"battery life": "12 hours"},
            "unknown",
            "needs_review",
        ),
    ],
)
async def test_operator_and_price_comparisons(
    name,
    value,
    unit,
    price,
    specifications,
    requirement_status,
    offer_status,
):
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "price": price,
                    "currency": "EUR" if price is not None else None,
                    "specifications": specifications,
                }
            ],
        )

        result = offers[0].matching_result
        requirement_result = result["requirements"][0]

        assert requirement_result["status"] == requirement_status
        assert result["status"] == offer_status

        if value == "<= 1200" and price == Decimal("1500"):
            assert requirement_result["reason"] == (
                "Supplier price exceeds the maximum allowed price."
            )

        if value == "<= 2" and name == "Weight":
            assert requirement_result["reason"] == (
                "Supplier value exceeds the maximum allowed value."
            )

        if value == ">= 16" and requirement_status == "not_met":
            assert requirement_result["reason"] == (
                "Supplier value is below the required minimum."
            )

        if requirement_status == "unknown" and name in {"Weight", "Battery life"}:
            assert requirement_result["reason"] == (
                "Comparison is ambiguous because no operator was provided."
            )

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_procurement_with_no_mandatory_requirements_is_eligible():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [],
            [
                {"supplier_name": "Supplier A", "product_name": "Laptop A"},
                {"supplier_name": "Supplier B", "product_name": "Laptop B"},
            ],
        )

        assert len(offers) == 2
        assert all(
            offer.matching_result["status"] == "eligible"
            for offer in offers
        )
        assert all(
            offer.matching_result["mandatory_requirements_total"] == 0
            for offer in offers
        )

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_price_currency_mismatch_is_unknown():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "Budget",
                    "value": "<= 1200",
                    "unit": "EUR",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "price": Decimal("1100"),
                    "currency": "USD",
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_substring_does_not_satisfy_a_different_model():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "SKU",
                    "value": "12",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "model": "X120",
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["requirements"][0]["status"] != "met"
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_warranty_column_matches_the_same_duration():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "Warranty",
                    "value": "3 years",
                    "unit": "years",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "warranty": "3 years",
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "met"
        assert result["requirements"][0]["actual"] == "3 years"
        assert result["status"] == "eligible"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "warranty_text",
    [
        "no warranty",
        "warranty not included",
        "without warranty",
        "warranty excluded",
        "none",
        "n/a",
    ],
)
async def test_negated_warranty_does_not_satisfy_a_positive_claim(
    warranty_text,
):
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "Warranty",
                    "value": "warranty",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "warranty": warranty_text,
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "not_met"
        assert result["status"] == "not_eligible"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_unverifiable_warranty_text_is_unknown():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "Warranty",
                    "value": "warranty",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "warranty": "warranty pending",
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.parametrize(
    ("expected_text", "actual_text"),
    [
        ("black", "black, no scratches"),
        ("wifi 6", "wifi 6, no bluetooth"),
        ("bluetooth", "bluetooth not required"),
    ],
)
def test_post_match_negation_is_unknown(expected_text, actual_text):
    status = _containment_status(expected_text, actual_text)

    assert status == "unknown"
    assert status != "met"
    assert status != "not_met"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("specifications", "requirement_status", "offer_status", "actual"),
    [
        (
            {"program": "8GB", "ram": "16GB"},
            "met",
            "eligible",
            "16GB",
        ),
        (
            {"ram": "16GB", "program": "8GB"},
            "met",
            "eligible",
            "16GB",
        ),
        (
            {"ram size": "16GB"},
            "met",
            "eligible",
            "16GB",
        ),
        (
            {"program": "8GB"},
            "unknown",
            "needs_review",
            None,
        ),
    ],
)
async def test_exact_ram_key_wins_over_an_earlier_program_key(
    specifications,
    requirement_status,
    offer_status,
    actual,
):
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "RAM",
                    "value": "16GB",
                    "unit": "GB",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": specifications,
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == requirement_status
        assert result["requirements"][0]["actual"] == actual
        assert result["status"] == offer_status

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_wifi_sentence_is_not_a_numeric_match():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "WiFi",
                    "value": "WiFi 6",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": {
                        "wifi": "WiFi 6, no bluetooth",
                    },
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_exact_wifi_text_is_met():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "WiFi",
                    "value": "WiFi 6",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": {
                        "wifi": "WiFi 6",
                    },
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "met"
        assert result["status"] == "eligible"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_different_cpu_model_is_unknown():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "CPU",
                    "value": "i7-1355U",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": {
                        "cpu": "i7-1165G7",
                    },
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["requirements"][0]["reason"] == (
            "Supplier value could not be reliably compared."
        )
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_exact_cpu_string_is_met():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "CPU",
                    "value": "i7-1355U",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": {
                        "cpu": "i7-1355U",
                    },
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "met"
        assert result["status"] == "eligible"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
async def test_chip_m2_against_usb_text_is_unknown():
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": "Chip",
                    "value": "M2",
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": {
                        "chip": "USB 2, chip M1",
                    },
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["requirements"][0]["reason"] == (
            "Supplier value could not be reliably compared."
        )
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "value", "specifications"),
    [
        ("Screen", "14in", {"display": "14 inch"}),
        ("Cores", "8 cores", {"cores": "8-core"}),
        ("Ports", "3", {"ports": "2 x USB 3"}),
    ],
)
async def test_ambiguous_non_trusted_numbers_are_unknown(
    name,
    value,
    specifications,
):
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": name,
                    "value": value,
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": specifications,
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "unknown"
        assert result["requirements"][0]["reason"] == (
            "Supplier value could not be reliably compared."
        )
        assert result["status"] == "needs_review"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "value", "unit", "specifications"),
    [
        ("RAM", ">= 16GB", "GB", {"ram": "32GB DDR5"}),
        ("RAM", ">= 16GB", "GB", {"ram": "32GB, non-ECC"}),
        (
            "Storage",
            ">= 512GB",
            "GB",
            {"storage": "1024GB PCIe 4.0 SSD"},
        ),
    ],
)
async def test_qualified_quantity_stays_a_minimum(
    name,
    value,
    unit,
    specifications,
):
    db = SessionLocal()
    organization = None

    try:
        organization, offers = await verify_requirements(
            db,
            [
                {
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "is_mandatory": True,
                }
            ],
            [
                {
                    "specifications": specifications,
                }
            ],
        )

        result = offers[0].matching_result

        assert result["requirements"][0]["status"] == "met"
        assert result["status"] == "eligible"

    finally:
        if organization is not None:
            cleanup(db, organization.id)

        db.close()
