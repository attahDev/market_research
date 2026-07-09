import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    UUID, String, Text, SmallInteger, Integer, Numeric,
    DateTime, Index, ForeignKey, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.config import settings

SCHEMA = settings.db_schema


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (
        Index("ix_research_jobs_query_normalized", "query_normalized"),
        Index("ix_research_jobs_status", "status"),
        Index("ix_research_jobs_expires_at", "expires_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="fresh")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    processing_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plan_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    result: Mapped[Optional["ResearchResult"]] = relationship(
        "ResearchResult", back_populates="job", uselist=False, lazy="selectin"
    )
    participants: Mapped[list["ResearchJobParticipant"]] = relationship(
        "ResearchJobParticipant", back_populates="job", lazy="selectin"
    )


class ResearchResult(Base):
    __tablename__ = "research_results"
    __table_args__ = (
        Index("ix_research_results_query_normalized", "query_normalized"),
        UniqueConstraint("job_id", name="uq_research_results_job_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.research_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    query_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    balance: Mapped[str] = mapped_column(Text, nullable=False)
    trend_summary: Mapped[str] = mapped_column(Text, nullable=False)
    insights: Mapped[list] = mapped_column(JSONB, nullable=False)
    opportunities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    risks: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    classifier_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    classifier_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    data_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    fetched_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc
    )

    job: Mapped["ResearchJob"] = relationship("ResearchJob", back_populates="result")


class ResearchJobParticipant(Base):
    """
    Every user attached to a job — the original requester AND anyone who joined
    an in-flight job for the same query_normalized.

    This exists because a job has exactly one outcome (success/failure), but
    potentially many users waiting on it, each with their own credit
    reservation against the main GMBTE DB. When the pipeline finishes, it
    loops over every row here and commits/refunds each participant's own
    reference_id based on the job's real outcome — instead of only being able
    to settle the original requester's reservation.
    """
    __tablename__ = "research_job_participants"
    __table_args__ = (
        Index("ix_research_job_participants_job_id", "job_id"),
        Index("ix_research_job_participants_settled", "settled"),
        UniqueConstraint("job_id", "reference_id", name="uq_job_participant_reference"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.research_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Ties this row to the specific reservation made against the main GMBTE DB
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    # 'original' = created the job, 'joined' = attached to an in-flight job
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="original")
    # Whether commit/refund has already been executed for this participant —
    # prevents double-settling if the pipeline's finally-block runs twice.
    settled: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc
    )

    job: Mapped["ResearchJob"] = relationship("ResearchJob", back_populates="participants")
