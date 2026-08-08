"""Persistence models for StoryHeal's closed-loop knowledge operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FindingKind(str, Enum):
    GAP = "gap"
    CONTRADICTION = "contradiction"
    STALE = "stale"
    FREQUENT = "frequent"


class FindingStatus(str, Enum):
    TRIAGE = "triage"
    DRAFTABLE = "draftable"
    DRAFTED = "drafted"
    DISMISSED = "dismissed"


class ProposalStatus(str, Enum):
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class StoryblokConnection(Base):
    __tablename__ = "sh_storyblok_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    region: Mapped[str] = mapped_column(String(16), nullable=False, default="eu")
    space_id: Mapped[str] = mapped_column(String(32), nullable=False)
    draft_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    publisher_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    folder_id: Mapped[Optional[str]] = mapped_column(String(32))
    folder_slug: Mapped[str] = mapped_column(String(120), nullable=False, default="knowledge")
    rag_collection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    locales: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=lambda: ["en", "es"])
    workflow_stage_ids: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    component_ids: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    public_webhook_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeEvidence(Base):
    __tablename__ = "sh_knowledge_evidence"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("api_visitor_sessions.id", ondelete="SET NULL"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="conversation")
    source_uri: Mapped[Optional[str]] = mapped_column(String(500))
    excerpt_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    redaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    purged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("project_id", "session_id", "content_hash", name="uq_sh_evidence_session_hash"),
    )


class KnowledgeRun(Base):
    __tablename__ = "sh_knowledge_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("api_visitor_sessions.id", ondelete="SET NULL"), index=True
    )
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    stage_results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeAgentStage(Base):
    __tablename__ = "sh_knowledge_agent_stages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("sh_knowledge_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed")
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeFinding(Base):
    __tablename__ = "sh_knowledge_findings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("sh_knowledge_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=FindingStatus.TRIAGE.value, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    representative_question: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    related_story_uuids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_sh_findings_project_status", "project_id", "status"),)


class KnowledgeProposal(Base):
    __tablename__ = "sh_knowledge_proposals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("sh_knowledge_findings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=ProposalStatus.DRAFTING.value, index=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    storyblok_story_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    storyblok_uuid: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    storyblok_full_slug: Mapped[Optional[str]] = mapped_column(String(500))
    content_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    published_snapshot: Mapped[Optional[dict[str, object]]] = mapped_column(JSONB)
    evidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    localization_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    reviewer_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("api_staff.id", ondelete="SET NULL"))
    review_reason: Mapped[Optional[str]] = mapped_column(Text)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StoryblokOperation(Base):
    __tablename__ = "sh_storyblok_operations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposal_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("sh_knowledge_proposals.id", ondelete="SET NULL"), index=True
    )
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    story_id: Mapped[Optional[str]] = mapped_column(String(32))
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class StoryblokWebhookReceipt(Base):
    __tablename__ = "sh_storyblok_webhook_receipts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    story_id: Mapped[str] = mapped_column(String(32), nullable=False)
    full_slug: Mapped[Optional[str]] = mapped_column(String(500))
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    error: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("project_id", "event_key", name="uq_sh_webhook_event"),)


class KnowledgeAuditEvent(Base):
    __tablename__ = "sh_audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    request_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class KnowledgeEvaluation(Base):
    __tablename__ = "sh_knowledge_evaluations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("sh_knowledge_proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_facts: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    answer: Mapped[Optional[str]] = mapped_column(Text)
    citation_uuids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    accuracy_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResponseMetric(Base):
    __tablename__ = "sh_response_metrics"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("api_visitor_sessions.id", ondelete="SET NULL"), index=True
    )
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    helpful: Mapped[Optional[bool]] = mapped_column(Boolean)
    resolution_outcome: Mapped[Optional[str]] = mapped_column(String(24))
    handed_off: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reopened_within_24h: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_refs: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
