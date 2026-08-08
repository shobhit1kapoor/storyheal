"""add StoryHeal Storyblok knowledge loop

Revision ID: 0028_storyheal_knowledge_loop
Revises: 0027_agent_only_ai_routing
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0028_storyheal_knowledge_loop"
down_revision = "0027_agent_only_ai_routing"
branch_labels = None
depends_on = None

UUID = sa.UUID()
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("api_visitor_sessions", sa.Column("resolution_outcome", sa.String(24), nullable=True))
    op.add_column("api_visitor_sessions", sa.Column("helpful", sa.Boolean(), nullable=True))
    op.add_column("api_visitor_sessions", sa.Column("first_response_time_ms", sa.Integer(), nullable=True))
    op.add_column("api_visitor_sessions", sa.Column("reopened_at", sa.DateTime(), nullable=True))
    op.add_column(
        "api_visitor_sessions",
        sa.Column("reopened_within_24h", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "sh_storyblok_connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("space_id", sa.String(32), nullable=False),
        sa.Column("draft_token_encrypted", sa.Text(), nullable=False),
        sa.Column("publisher_token_encrypted", sa.Text(), nullable=False),
        sa.Column("delivery_token_encrypted", sa.Text(), nullable=False),
        sa.Column("webhook_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("folder_id", sa.String(32)),
        sa.Column("folder_slug", sa.String(120), nullable=False),
        sa.Column("rag_collection_id", sa.String(64), nullable=False),
        sa.Column("locales", JSONB, nullable=False),
        sa.Column("workflow_stage_ids", JSONB, nullable=False),
        sa.Column("component_ids", JSONB, nullable=False),
        sa.Column("public_webhook_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index("ix_sh_storyblok_connections_project_id", "sh_storyblok_connections", ["project_id"])

    op.create_table(
        "sh_knowledge_evidence",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("api_visitor_sessions.id", ondelete="SET NULL")),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_uri", sa.String(500)),
        sa.Column("excerpt_encrypted", sa.Text()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("redaction_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "session_id", "content_hash", name="uq_sh_evidence_session_hash"),
    )
    op.create_index("ix_sh_knowledge_evidence_project_id", "sh_knowledge_evidence", ["project_id"])
    op.create_index("ix_sh_knowledge_evidence_session_id", "sh_knowledge_evidence", ["session_id"])
    op.create_index("ix_sh_knowledge_evidence_expires_at", "sh_knowledge_evidence", ["expires_at"])

    op.create_table(
        "sh_knowledge_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("api_visitor_sessions.id", ondelete="SET NULL")),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_stage", sa.String(64)),
        sa.Column("model", sa.String(120)),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("stage_results", JSONB, nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sh_knowledge_runs_project_id", "sh_knowledge_runs", ["project_id"])
    op.create_index("ix_sh_knowledge_runs_session_id", "sh_knowledge_runs", ["session_id"])
    op.create_index("ix_sh_knowledge_runs_status", "sh_knowledge_runs", ["status"])

    op.create_table(
        "sh_knowledge_agent_stages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("sh_knowledge_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("evidence_ids", JSONB, nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("output", JSONB, nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sh_knowledge_agent_stages_project_id", "sh_knowledge_agent_stages", ["project_id"])
    op.create_index("ix_sh_knowledge_agent_stages_run_id", "sh_knowledge_agent_stages", ["run_id"])
    op.create_index("ix_sh_knowledge_agent_stages_agent_type", "sh_knowledge_agent_stages", ["agent_type"])

    op.create_table(
        "sh_knowledge_findings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("sh_knowledge_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("representative_question", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("evidence_ids", JSONB, nullable=False),
        sa.Column("related_story_uuids", JSONB, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sh_knowledge_findings_project_id", "sh_knowledge_findings", ["project_id"])
    op.create_index("ix_sh_knowledge_findings_run_id", "sh_knowledge_findings", ["run_id"])
    op.create_index("ix_sh_knowledge_findings_kind", "sh_knowledge_findings", ["kind"])
    op.create_index("ix_sh_knowledge_findings_status", "sh_knowledge_findings", ["status"])
    op.create_index("ix_sh_findings_project_status", "sh_knowledge_findings", ["project_id", "status"])

    op.create_table(
        "sh_knowledge_proposals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", UUID, sa.ForeignKey("sh_knowledge_findings.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("storyblok_story_id", sa.String(32)),
        sa.Column("storyblok_uuid", sa.String(64)),
        sa.Column("storyblok_full_slug", sa.String(500)),
        sa.Column("content_payload", JSONB, nullable=False),
        sa.Column("published_snapshot", JSONB),
        sa.Column("evidence_score", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("localization_score", sa.Float(), nullable=False),
        sa.Column("reviewer_id", UUID, sa.ForeignKey("api_staff.id", ondelete="SET NULL")),
        sa.Column("review_reason", sa.Text()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for name, cols in (
        ("ix_sh_knowledge_proposals_project_id", ["project_id"]),
        ("ix_sh_knowledge_proposals_status", ["status"]),
        ("ix_sh_knowledge_proposals_storyblok_story_id", ["storyblok_story_id"]),
        ("ix_sh_knowledge_proposals_storyblok_uuid", ["storyblok_uuid"]),
    ):
        op.create_index(name, "sh_knowledge_proposals", cols)

    op.create_table(
        "sh_storyblok_operations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_id", UUID, sa.ForeignKey("sh_knowledge_proposals.id", ondelete="SET NULL")),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("method", sa.String(12), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.String(32)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sh_storyblok_operations_project_id", "sh_storyblok_operations", ["project_id"])
    op.create_index("ix_sh_storyblok_operations_proposal_id", "sh_storyblok_operations", ["proposal_id"])
    op.create_index("ix_sh_storyblok_operations_created_at", "sh_storyblok_operations", ["created_at"])

    op.create_table(
        "sh_storyblok_webhook_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=False),
        sa.Column("story_id", sa.String(32), nullable=False),
        sa.Column("full_slug", sa.String(500)),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "event_key", name="uq_sh_webhook_event"),
    )
    op.create_index("ix_sh_storyblok_webhook_receipts_project_id", "sh_storyblok_webhook_receipts", ["project_id"])

    op.create_table(
        "sh_audit_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.String(64)),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("detail", JSONB, nullable=False),
        sa.Column("request_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sh_audit_events_project_id", "sh_audit_events", ["project_id"])
    op.create_index("ix_sh_audit_events_action", "sh_audit_events", ["action"])
    op.create_index("ix_sh_audit_events_created_at", "sh_audit_events", ["created_at"])

    op.create_table(
        "sh_knowledge_evaluations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_id", UUID, sa.ForeignKey("sh_knowledge_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_facts", JSONB, nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("citation_uuids", JSONB, nullable=False),
        sa.Column("accuracy_score", sa.Float(), nullable=False),
        sa.Column("response_time_ms", sa.Integer()),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sh_knowledge_evaluations_project_id", "sh_knowledge_evaluations", ["project_id"])
    op.create_index("ix_sh_knowledge_evaluations_proposal_id", "sh_knowledge_evaluations", ["proposal_id"])

    op.create_table(
        "sh_response_metrics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey("api_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("api_visitor_sessions.id", ondelete="SET NULL")),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("response_time_ms", sa.Integer()),
        sa.Column("helpful", sa.Boolean()),
        sa.Column("resolution_outcome", sa.String(24)),
        sa.Column("handed_off", sa.Boolean(), nullable=False),
        sa.Column("reopened_within_24h", sa.Boolean(), nullable=False),
        sa.Column("source_refs", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sh_response_metrics_project_id", "sh_response_metrics", ["project_id"])
    op.create_index("ix_sh_response_metrics_session_id", "sh_response_metrics", ["session_id"])
    op.create_index("ix_sh_response_metrics_created_at", "sh_response_metrics", ["created_at"])

    permissions = sa.table(
        "api_permissions", sa.column("id", UUID), sa.column("resource", sa.String()),
        sa.column("action", sa.String()), sa.column("description", sa.String()),
    )
    op.bulk_insert(permissions, [
        {"id": "3f15a287-487a-4f05-9010-000000000001", "resource": "storyblok", "action": "admin", "description": "Configure and provision Storyblok"},
        {"id": "3f15a287-487a-4f05-9010-000000000002", "resource": "knowledge", "action": "review", "description": "Review findings and reject proposals"},
        {"id": "3f15a287-487a-4f05-9010-000000000003", "resource": "knowledge", "action": "publish", "description": "Approve and publish proposals"},
        {"id": "3f15a287-487a-4f05-9010-000000000004", "resource": "knowledge", "action": "analytics", "description": "View usefulness analytics"},
        {"id": "3f15a287-487a-4f05-9010-000000000005", "resource": "knowledge", "action": "audit", "description": "View append-only audit events"},
    ])


def downgrade() -> None:
    op.execute("DELETE FROM api_permissions WHERE id::text LIKE '3f15a287-487a-4f05-9010-%'")
    for table in (
        "sh_response_metrics", "sh_knowledge_evaluations", "sh_audit_events",
        "sh_storyblok_webhook_receipts", "sh_storyblok_operations", "sh_knowledge_proposals",
        "sh_knowledge_findings", "sh_knowledge_agent_stages", "sh_knowledge_runs", "sh_knowledge_evidence",
        "sh_storyblok_connections",
    ):
        op.drop_table(table)
    for column in (
        "reopened_within_24h", "reopened_at", "first_response_time_ms", "helpful", "resolution_outcome"
    ):
        op.drop_column("api_visitor_sessions", column)
