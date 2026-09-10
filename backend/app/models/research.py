import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    procurement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procurements.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )
    plan: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    procurement: Mapped["Procurement"] = relationship(
        back_populates="research_runs",
    )
    tasks: Mapped[list["ResearchTask"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    sources: Mapped[list["ResearchSource"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )
    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    external_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    input_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    output_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    research_run: Mapped["ResearchRun"] = relationship(
        back_populates="tasks",
    )
    sources: Mapped[list["ResearchSource"]] = relationship(
        back_populates="task",
    )


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_tasks.id"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    source_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    raw_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    research_run: Mapped["ResearchRun"] = relationship(
        back_populates="sources",
    )
    task: Mapped["ResearchTask | None"] = relationship(
        back_populates="sources",
    )
    evidence: Mapped[list["OfferEvidence"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class SupplierOffer(Base):
    __tablename__ = "supplier_offers"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    procurement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procurements.id"),
        nullable=False,
        index=True,
    )
    supplier_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    model: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )
    currency: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    availability: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    warranty: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    specifications: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    matching_result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    procurement: Mapped["Procurement"] = relationship(
        back_populates="supplier_offers",
    )
    evidence: Mapped[list["OfferEvidence"]] = relationship(
        back_populates="offer",
        cascade="all, delete-orphan",
    )


class OfferEvidence(Base):
    __tablename__ = "offer_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("supplier_offers.id"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    evidence_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    offer: Mapped["SupplierOffer"] = relationship(
        back_populates="evidence",
    )
    source: Mapped["ResearchSource"] = relationship(
        back_populates="evidence",
    )
