"""Contracts for Storyblok external-source indexing."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StoryblokSourceUpsert(BaseModel):
    project_id: UUID
    locale: str = Field(min_length=2, max_length=16)
    title: str = Field(min_length=1, max_length=500)
    slug: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    published_at: datetime | None = None
    source_url: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    channel_variants: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryblokSourceView(BaseModel):
    id: UUID
    story_uuid: str
    locale: str
    content_hash: str
    status: str
    document_id: UUID | None
    indexed_at: datetime | None
    unchanged: bool = False

    model_config = {"from_attributes": True}
