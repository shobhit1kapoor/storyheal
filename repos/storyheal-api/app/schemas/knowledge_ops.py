"""Typed API contracts for Storyblok and the StoryHeal knowledge loop."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


StoryblokRegion = Literal["eu", "us", "ca", "ap", "cn"]
ContentType = Literal[
    "sh_faq",
    "sh_documentation",
    "sh_troubleshooting",
    "sh_policy",
    "sh_known_issue",
    "sh_product",
    "sh_release_note",
]


class StoryblokConnectionUpsert(BaseModel):
    region: StoryblokRegion = "eu"
    space_id: str = Field(min_length=1, max_length=32)
    draft_token: SecretStr
    publisher_token: SecretStr
    delivery_token: SecretStr
    webhook_secret: SecretStr = Field(min_length=16)
    folder_slug: str = Field(default="knowledge", pattern=r"^[a-z0-9][a-z0-9-/]*$")
    rag_collection_id: UUID
    locales: list[str] = Field(default_factory=lambda: ["en", "es"], min_length=1)
    public_webhook_url: str = Field(pattern=r"^https://")


class StoryblokConnectionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    region: str
    space_id: str
    folder_id: Optional[str]
    folder_slug: str
    rag_collection_id: str
    locales: list[str]
    workflow_stage_ids: dict[str, int]
    component_ids: dict[str, int]
    public_webhook_url: str
    is_active: bool
    draft_token_configured: bool
    publisher_token_configured: bool
    delivery_token_configured: bool
    webhook_secret_configured: bool
    last_tested_at: Optional[datetime]
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class StoryblokTestResult(BaseModel):
    success: bool
    space_name: Optional[str] = None
    region: str
    draft_can_write: bool
    publisher_can_publish: bool
    delivery_can_read: bool
    detail: str


class StoryblokProvisionResult(BaseModel):
    folder_id: str
    component_ids: dict[str, int]
    workflow_stage_ids: dict[str, int]
    webhook_id: Optional[int] = None
    operations: int


class EvidenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: Optional[UUID]
    source_type: str
    source_uri: Optional[str]
    excerpt: Optional[str]
    content_hash: str
    redaction_count: int
    observed_at: datetime
    expires_at: datetime
    purged_at: Optional[datetime]


class KnowledgeRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: Optional[UUID]
    trigger: str
    status: str
    current_stage: Optional[str]
    model: Optional[str]
    prompt_version: str
    stage_results: dict[str, object]
    token_count: int
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class KnowledgeAgentStageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    agent_type: str
    status: str
    prompt_version: str
    model: Optional[str]
    latency_ms: Optional[int]
    token_count: int
    evidence_ids: list[str]
    confidence: Optional[float]
    retry_count: int
    output: dict[str, object]
    error: Optional[str]
    created_at: datetime


class KnowledgeFindingView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    kind: str
    status: str
    title: str
    summary: str
    representative_question: str
    severity: str
    confidence: float
    occurrence_count: int
    evidence_ids: list[str]
    related_story_uuids: list[str]
    detected_at: datetime


class KnowledgeProposalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID
    status: str
    content_type: str
    title: str
    slug: str
    storyblok_story_id: Optional[str]
    storyblok_uuid: Optional[str]
    storyblok_full_slug: Optional[str]
    content_payload: dict[str, object]
    published_snapshot: Optional[dict[str, object]]
    evidence_score: float
    quality_score: float
    localization_score: float
    reviewer_id: Optional[UUID]
    review_reason: Optional[str]
    approved_at: Optional[datetime]
    published_at: Optional[datetime]
    indexed_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class ProposalDecision(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class ProposalReject(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class AnalyzeSessionRequest(BaseModel):
    session_id: UUID


class HelpfulFeedbackRequest(BaseModel):
    session_id: Optional[UUID] = None
    question_hash: str = Field(min_length=64, max_length=64)
    helpful: bool
    source_refs: list[dict[str, object]] = Field(default_factory=list)


class PublicHelpfulFeedbackRequest(BaseModel):
    platform_api_key: str = Field(min_length=8, max_length=255)
    question_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    helpful: bool
    source_refs: list[dict[str, object]] = Field(default_factory=list)


class SourceCitation(BaseModel):
    story_uuid: str
    full_slug: str
    title: str
    locale: str
    published_at: Optional[datetime] = None
    url: str


class StoryblokWebhookEnvelope(BaseModel):
    trigger: Literal["story.published", "story.unpublished", "story.deleted"]
    payload: dict[str, object]


class AnalyticsSummary(BaseModel):
    questions_processed: int
    gaps_detected: int
    contradictions_detected: int
    stale_content_detected: int
    drafts_generated: int
    drafts_approved: int
    drafts_rejected: int
    stories_published: int
    stories_indexed: int
    storyblok_api_operations: int
    storyblok_api_failures: int
    response_accuracy: float
    resolution_rate: float
    helpful_rate: float
    average_response_time_ms: Optional[float]
    average_indexing_time_ms: Optional[float]
    improvement_percentage_points: float
    findings_by_type: dict[str, int] = Field(default_factory=dict)
    proposals_by_status: dict[str, int] = Field(default_factory=dict)
    content_types: dict[str, int] = Field(default_factory=dict)
    locales_indexed: dict[str, int] = Field(default_factory=dict)
    channels_published: dict[str, int] = Field(default_factory=dict)
    daily_activity: list[dict[str, object]] = Field(default_factory=list)
    paired_evaluations: list[dict[str, object]] = Field(default_factory=list)


class StoryblokOperationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proposal_id: Optional[UUID]
    operation: str
    method: str
    status_code: Optional[int]
    success: bool
    duration_ms: Optional[int]
    attempt: int
    story_id: Optional[str]
    error: Optional[str]
    created_at: datetime


class AuditEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_type: str
    actor_id: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[str]
    detail: dict[str, object]
    request_id: Optional[str]
    created_at: datetime


class EvaluationRunRequest(BaseModel):
    proposal_id: UUID
    phase: Literal["before", "after"]
    question: str = Field(min_length=3, max_length=4000)
    expected_facts: list[str] = Field(min_length=1, max_length=50)
    answer: str = Field(min_length=1)
    citation_uuids: list[str] = Field(default_factory=list)
    response_time_ms: Optional[int] = Field(default=None, ge=0)


class EvaluationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proposal_id: UUID
    phase: str
    question: str
    expected_facts: list[str]
    answer: Optional[str]
    citation_uuids: list[str]
    accuracy_score: float
    response_time_ms: Optional[int]
    passed: bool
    created_at: datetime
