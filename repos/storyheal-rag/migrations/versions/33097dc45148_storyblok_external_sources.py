"""add Storyblok external source identity

Revision ID: 33097dc45148
Revises: 32097dc45147
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "33097dc45148"
down_revision = "32097dc45147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_storyblok_external_sources",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("collection_id", sa.UUID(), sa.ForeignKey("rag_collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("rag_file_documents.id", ondelete="SET NULL")),
        sa.Column("story_uuid", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("slug", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("channel_variants", postgresql.JSONB(), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint(
            "project_id", "collection_id", "story_uuid", "locale",
            name="uq_rag_storyblok_external_source",
        ),
    )
    op.create_index("idx_rag_storyblok_story_uuid", "rag_storyblok_external_sources", ["story_uuid"])
    op.create_index("idx_rag_storyblok_content_hash", "rag_storyblok_external_sources", ["content_hash"])
    op.create_index("idx_rag_storyblok_status", "rag_storyblok_external_sources", ["status"])


def downgrade() -> None:
    op.drop_table("rag_storyblok_external_sources")
