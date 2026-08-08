"""Specialized, schema-constrained agents for StoryHeal knowledge healing."""

from __future__ import annotations

import json
import re
import secrets
import time
from enum import Enum
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.config import settings
from app.models.llm_provider import LLMProvider
from app.models.project_ai_config import ProjectAIConfig
from app.schemas.chat import ChatCompletionRequest, ChatMessage, ResponseFormat
from app.services.chat_service import ChatService

router = APIRouter()


class KnowledgeAgentType(str, Enum):
    GAP_DETECTION = "gap_detection"
    CONTRADICTION_STALENESS = "contradiction_staleness"
    CONTENT_DRAFTING = "content_drafting"
    EVIDENCE_VERIFICATION = "evidence_verification"
    LOCALIZATION = "localization"
    QUALITY_CHECK = "quality_check"


class KnowledgeAgentRequest(BaseModel):
    evidence: list[dict[str, object]] = Field(default_factory=list)
    current_content: list[dict[str, object]] = Field(default_factory=list)
    finding: Optional[dict[str, object]] = None
    draft: Optional[dict[str, object]] = None
    occurrence_count: int = Field(default=1, ge=1)
    locales: list[str] = Field(default_factory=lambda: ["en", "es"])
    prompt_version: str = "v1"


class FindingOutput(BaseModel):
    detected: bool
    kind: str
    title: str
    summary: str
    representative_question: str
    severity: str
    confidence: float = Field(ge=0, le=1)
    occurrence_count: int = Field(ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    related_story_uuids: list[str] = Field(default_factory=list)


class StoryblokDraftContent(BaseModel):
    model_config = ConfigDict(extra="allow")

    component: Literal[
        "sh_faq", "sh_documentation", "sh_troubleshooting", "sh_policy",
        "sh_known_issue", "sh_product", "sh_release_note",
    ]
    title: str
    summary: str
    body: dict[str, object]
    channels: list[Literal["web", "assistant", "support", "widget"]]
    evidence: list[dict[str, object]] = Field(min_length=1)
    channel_variants: list[dict[str, object]] = Field(default_factory=list)
    applicability: list[dict[str, object]] = Field(default_factory=list)
    related_content: list[dict[str, object]] = Field(default_factory=list)
    source_proposal_id: str


class DraftOutput(BaseModel):
    content_type: str
    title: str
    slug: str
    content: StoryblokDraftContent
    expected_facts: list[str] = Field(default_factory=list)


class VerificationOutput(BaseModel):
    supported: bool
    evidence_score: float = Field(ge=0, le=1)
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class LocalizationOutput(BaseModel):
    localization_score: float = Field(ge=0, le=1)
    translations: dict[str, dict[str, object]]
    untranslated_fields: list[str] = Field(default_factory=list)


class QualityOutput(BaseModel):
    quality_score: float = Field(ge=0, le=100)
    duplicate_risk: float = Field(ge=0, le=1)
    schema_valid: bool
    citations_complete: bool
    issues: list[str] = Field(default_factory=list)


class KnowledgeAgentResponse(BaseModel):
    agent_type: KnowledgeAgentType
    prompt_version: str
    model: str
    duration_ms: int
    token_count: int
    output: dict[str, object]


OUTPUT_MODELS: dict[KnowledgeAgentType, type[BaseModel]] = {
    KnowledgeAgentType.GAP_DETECTION: FindingOutput,
    KnowledgeAgentType.CONTRADICTION_STALENESS: FindingOutput,
    KnowledgeAgentType.CONTENT_DRAFTING: DraftOutput,
    KnowledgeAgentType.EVIDENCE_VERIFICATION: VerificationOutput,
    KnowledgeAgentType.LOCALIZATION: LocalizationOutput,
    KnowledgeAgentType.QUALITY_CHECK: QualityOutput,
}


SYSTEM_PROMPTS: dict[KnowledgeAgentType, str] = {
    KnowledgeAgentType.GAP_DETECTION: (
        "You are StoryHeal's knowledge-gap detector. Compare real support evidence with current canonical content. "
        "Set detected=false when canonical content already answers the evidence. Otherwise return the one "
        "highest-value finding as strict JSON. Never invent evidence IDs. Use kind gap or frequent."
    ),
    KnowledgeAgentType.CONTRADICTION_STALENESS: (
        "You are StoryHeal's contradiction and staleness detector. Identify claims in canonical content that conflict "
        "with support evidence or are no longer current. Set detected=false when there is no supported conflict. "
        "Return strict JSON using kind contradiction or stale."
    ),
    KnowledgeAgentType.CONTENT_DRAFTING: (
        "You are StoryHeal's structured content drafter. Produce a complete Storyblok story using exactly one root "
        "component: sh_faq, sh_documentation, sh_troubleshooting, sh_policy, sh_known_issue, sh_product, or "
        "sh_release_note. The content object must include component, title, summary, body, channels, evidence, "
        "channel_variants, source_proposal_id, and type-specific fields. Body fields use Storyblok rich-text JSON."
    ),
    KnowledgeAgentType.EVIDENCE_VERIFICATION: (
        "You are StoryHeal's source verifier. Evaluate every factual draft claim only against supplied evidence. "
        "Mark unsupported claims explicitly. Return strict JSON and never accept a citation not present in evidence."
    ),
    KnowledgeAgentType.LOCALIZATION: (
        "You are StoryHeal's localization agent. Translate only user-facing title, summary, and body fields into "
        "every requested locale. Return only localization_score, translations keyed by locale, and "
        "untranslated_fields. Do not repeat evidence, current content, metadata, or schemas. Preserve product names, "
        "version strings, code, URLs, and evidence checksums."
    ),
    KnowledgeAgentType.QUALITY_CHECK: (
        "You are StoryHeal's final quality gate. Score clarity, completeness, schema validity, citation coverage, "
        "safety, localization, and duplicate risk. A score of 85 or more means publishable after human review."
    ),
}


def _clean_json(content: str) -> dict[str, object]:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1]
        value = value.rsplit("```", 1)[0]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Agent returned a non-object JSON value")
    return parsed


def _normalize_agent_output(
    agent_type: KnowledgeAgentType, output: dict[str, object]
) -> dict[str, object]:
    """Normalize common OpenAI-compatible structured-output wrappers."""
    if agent_type == KnowledgeAgentType.LOCALIZATION and "translations" not in output:
        translations = {
            key: value
            for key, value in output.items()
            if isinstance(value, dict) and len(key) in {2, 5}
        }
        if translations:
            return {
                "localization_score": 1.0,
                "translations": translations,
                "untranslated_fields": [],
            }
    if agent_type != KnowledgeAgentType.CONTENT_DRAFTING:
        return output
    nested = output.get("content")
    content = nested if isinstance(nested, dict) and nested.get("component") else output
    if not isinstance(content, dict) or not content.get("component"):
        return output
    title = str(output.get("title") or content.get("title") or "Knowledge update")
    slug = str(output.get("slug") or content.get("slug") or "")
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "knowledge-update"
    return {
        **output,
        "content_type": str(output.get("content_type") or content.get("type") or content["component"]),
        "title": title,
        "slug": slug,
        "content": content,
        "expected_facts": output.get("expected_facts") or content.get("expected_facts") or [],
    }


@router.post("/{agent_type}/run", response_model=KnowledgeAgentResponse)
async def run_knowledge_agent(
    agent_type: KnowledgeAgentType,
    request: KnowledgeAgentRequest,
    project_id: str = Query(...),
    x_internal_key: str = Header(..., alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeAgentResponse:
    from uuid import NAMESPACE_URL, UUID, uuid5

    if not secrets.compare_digest(x_internal_key, settings.internal_service_api_key):
        raise HTTPException(status_code=401, detail="Invalid internal service key")
    project_uuid = UUID(project_id)
    config = await db.scalar(select(ProjectAIConfig).where(ProjectAIConfig.project_id == project_uuid))
    provider_id = config.default_chat_provider_id if config else None
    model = config.default_chat_model if config else None
    if provider_id is None:
        provider_id = await db.scalar(
            select(LLMProvider.id)
            .where(LLMProvider.project_id == project_uuid, LLMProvider.is_active.is_(True))
            .order_by(LLMProvider.synced_at.desc())
        )
    if provider_id is None:
        if not settings.allow_local_provider_fallback:
            raise HTTPException(status_code=409, detail="Configure an active AI provider before running knowledge agents")
        provider_id = uuid5(NAMESPACE_URL, f"storyheal:ollama:{project_uuid}")
        provider = await db.get(LLMProvider, provider_id)
        if provider is None:
            provider = LLMProvider(
                id=provider_id,
                project_id=project_uuid,
                alias="storyheal-local-ollama",
                provider_kind="openai_compatible",
                vendor="ollama",
                api_base_url=settings.ollama_base_url.rstrip("/") + "/v1",
                api_key="ollama",
                default_model=settings.ollama_model,
                is_active=True,
            )
            db.add(provider)
            await db.flush()
        model = model or settings.ollama_model
    if not model:
        provider = await db.get(LLMProvider, provider_id)
        model = provider.default_model if provider and provider.default_model else "qwen3:8b"
    else:
        provider = await db.get(LLMProvider, provider_id)

    is_ollama = bool(provider and provider.vendor == "ollama")

    response_schema = OUTPUT_MODELS[agent_type].model_json_schema()
    payload = request.model_dump(mode="json")
    user_prompt = json.dumps(
        {"input": payload, "required_response_schema": response_schema},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    completion_request = ChatCompletionRequest(
        provider_id=provider_id,
        model=model,
        messages=[
            # Qwen3 defaults to an extended reasoning trace. Structured agent
            # stages need the validated JSON result, not a long hidden chain, and
            # local CPU deployments must stay within the durable worker timeout.
            ChatMessage(
                role="system",
                content=("/no_think\n" if is_ollama else "") + SYSTEM_PROMPTS[agent_type],
            ),
            ChatMessage(role="user", content=user_prompt),
        ],
        stream=False,
        temperature=0.1,
        max_tokens=2400 if agent_type == KnowledgeAgentType.LOCALIZATION else 1600,
        # NVIDIA NIM follows the OpenAI-compatible contract but its models do
        # not accept Ollama's `none` reasoning value. Omit the field for remote
        # providers and use it only for the local Qwen fallback.
        reasoning_effort="none" if is_ollama else None,
        response_format=ResponseFormat(type="json_object"),
        auto_execute_tools=False,
    )
    started = time.perf_counter()
    completion = await ChatService(db).create_completion(completion_request, project_uuid)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if not completion.choices or not completion.choices[0].message.content:
        raise HTTPException(status_code=502, detail="Knowledge agent returned no content")
    try:
        raw_output = _normalize_agent_output(
            agent_type, _clean_json(completion.choices[0].message.content)
        )
        validated = TypeAdapter(OUTPUT_MODELS[agent_type]).validate_python(raw_output)
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail=f"Invalid structured agent output: {exc}") from exc

    token_count = completion.usage.total_tokens if completion.usage else 0
    return KnowledgeAgentResponse(
        agent_type=agent_type,
        prompt_version=request.prompt_version,
        model=model,
        duration_ms=duration_ms,
        token_count=token_count,
        output=validated.model_dump(mode="json"),
    )
