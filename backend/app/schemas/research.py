from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ResearchRunCreated(BaseModel):
    research_run_id: UUID
    procurement_id: UUID
    status: str
    source_ids: list[UUID]


class ResearchEvidenceResponse(BaseModel):
    id: UUID
    field: str
    value: str
    evidence_text: str | None
    confidence: str | None
    source_id: UUID
    source_url: str
    source_title: str | None


class ResearchOfferResponse(BaseModel):
    id: UUID
    supplier_name: str
    product_name: str
    model: str | None
    url: str | None
    price: str | None
    currency: str | None
    availability: str | None
    warranty: str | None
    specifications: dict[str, Any] | None
    matching_result: dict[str, Any] | None
    evidence: list[ResearchEvidenceResponse]


class ResearchRunResponse(BaseModel):
    research_run_id: UUID
    procurement_id: UUID
    status: str
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    offers: list[ResearchOfferResponse]
    compare_offers: dict[str, Any] | None
    recommendation: dict[str, Any] | None
