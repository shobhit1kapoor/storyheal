"""Canonical external content indexed from Storyblok."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDMixin


class StoryblokExternalSource(Base, UUIDMixin, TimestampMixin):
    """Tracks one published Storyblok story locale and its indexed document."""

    __tablename__ = "rag_storyblok_external_sources"

    project_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    collection_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_collections.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_file_documents.id", ondelete="SET NULL"), nullable=True
    )
    story_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    channel_variants: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "collection_id", "story_uuid", "locale",
            name="uq_rag_storyblok_external_source",
        ),
        Index("idx_rag_storyblok_story_uuid", "story_uuid"),
        Index("idx_rag_storyblok_content_hash", "content_hash"),
        Index("idx_rag_storyblok_status", "status"),
    )
