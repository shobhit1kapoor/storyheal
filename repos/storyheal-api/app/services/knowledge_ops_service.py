"""Core orchestration for StoryHeal's conversation-to-Storyblok feedback loop."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import (
    FindingStatus,
    KnowledgeAgentStage,
    KnowledgeAuditEvent,
    KnowledgeEvidence,
    KnowledgeFinding,
    KnowledgeProposal,
    KnowledgeRun,
    ProposalStatus,
    StoryblokConnection,
)
from app.services.ai_client import ai_service_client
from app.services.storyblok_client import StoryblokClient, StoryblokCredentials
from app.services.storyblok_components import COMPONENT_DEFINITIONS
from app.utils.crypto import decrypt_str, encrypt_str

logger = get_logger("services.knowledge_ops")

ROOT_COMPONENTS = {
    str(definition["name"]) for definition in COMPONENT_DEFINITIONS if definition.get("is_root") is True
}


REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[GOVERNMENT_ID]"),
    (re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"), "[PHONE]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[PAYMENT_CARD]"),
    (re.compile(r"\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+", re.IGNORECASE), "[SECRET]"),
)


def redact_text(text: str) -> tuple[str, int]:
    redacted = text.strip()
    count = 0
    for pattern, replacement in REDACTION_PATTERNS:
        redacted, replacements = pattern.subn(replacement, redacted)
        count += replacements
    return redacted, count


def capture_evidence(
    db: Session,
    *,
    project_id: UUID,
    text: str,
    session_id: Optional[UUID] = None,
    source_uri: Optional[str] = None,
    source_type: str = "conversation",
) -> KnowledgeEvidence:
    redacted, redaction_count = redact_text(text)
    content_hash = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
    existing = db.query(KnowledgeEvidence).filter(
        KnowledgeEvidence.project_id == project_id,
        KnowledgeEvidence.session_id == session_id,
        KnowledgeEvidence.content_hash == content_hash,
    ).first()
    if existing:
        return existing
    evidence = KnowledgeEvidence(
        project_id=project_id,
        session_id=session_id,
        source_type=source_type,
        source_uri=source_uri,
        excerpt_encrypted=encrypt_str(redacted),
        content_hash=content_hash,
        redaction_count=redaction_count,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.KNOWLEDGE_EVIDENCE_RETENTION_DAYS),
    )
    db.add(evidence)
    db.flush()
    audit(
        db,
        project_id=project_id,
        actor_type="system",
        action="evidence.captured",
        entity_type="evidence",
        entity_id=str(evidence.id),
        detail={"source_type": source_type, "redaction_count": redaction_count, "content_hash": content_hash},
    )
    return evidence


def audit(
    db: Session,
    *,
    project_id: UUID,
    actor_type: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    detail: Optional[dict[str, object]] = None,
    actor_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> KnowledgeAuditEvent:
    event = KnowledgeAuditEvent(
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail or {},
        request_id=request_id,
    )
    db.add(event)
    return event


def credentials_for(connection: StoryblokConnection) -> StoryblokCredentials:
    draft = decrypt_str(connection.draft_token_encrypted)
    publisher = decrypt_str(connection.publisher_token_encrypted)
    delivery = decrypt_str(connection.delivery_token_encrypted)
    webhook_secret = decrypt_str(connection.webhook_secret_encrypted)
    if not all((draft, publisher, delivery, webhook_secret)):
        raise RuntimeError("Storyblok credentials cannot be decrypted")
    return StoryblokCredentials(
        project_id=connection.project_id,
        region=connection.region,
        space_id=connection.space_id,
        draft_token=draft,
        publisher_token=publisher,
        delivery_token=delivery,
        webhook_secret=webhook_secret,
    )


def evidence_payload(evidence: list[KnowledgeEvidence]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in evidence:
        result.append(
            {
                "id": str(item.id),
                "source_type": item.source_type,
                "source_uri": item.source_uri,
                "excerpt": decrypt_str(item.excerpt_encrypted or "") or "[PURGED]",
                "content_hash": item.content_hash,
                "observed_at": item.observed_at.isoformat() if item.observed_at else None,
            }
        )
    return result


def _agent_output(response: dict[str, object]) -> dict[str, object]:
    output = response.get("output")
    if not isinstance(output, dict):
        raise RuntimeError("Knowledge agent response is missing an output object")
    return output


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _record_agent_stage(
    db: Session,
    run: KnowledgeRun,
    agent_type: str,
    response: dict[str, object],
    output: dict[str, object],
    evidence: list[KnowledgeEvidence],
) -> None:
    """Persist one immutable, independently queryable agent execution record."""
    db.add(
        KnowledgeAgentStage(
            project_id=run.project_id,
            run_id=run.id,
            agent_type=agent_type,
            status="completed",
            prompt_version=run.prompt_version,
            model=str(response.get("model") or "") or None,
            latency_ms=int(response.get("duration_ms", 0) or 0),
            token_count=int(response.get("token_count", 0) or 0),
            evidence_ids=_strings(output.get("evidence_ids")) or [str(item.id) for item in evidence],
            confidence=(
                float(output["confidence"])
                if isinstance(output.get("confidence"), (int, float))
                else None
            ),
            retry_count=int(response.get("retry_count", 0) or 0),
            output=output,
        )
    )


def apply_storyblok_translations(
    content: dict[str, object], translations: dict[str, object], locales: list[str]
) -> dict[str, object]:
    result = dict(content)
    for locale in locales:
        if locale == "en":
            continue
        localized = translations.get(locale)
        if not isinstance(localized, dict):
            continue
        if isinstance(localized.get("draft"), dict):
            localized = localized["draft"]
        for key, value in localized.items():
            if key in {"component", "source_proposal_id"}:
                continue
            result[f"{key}__i18n__{locale}"] = value
    return result


def _storyblok_richtext(value: object) -> dict[str, object]:
    if isinstance(value, dict) and value.get("type") == "doc" and isinstance(value.get("content"), list):
        return value
    text = richtext_to_text(value).strip()
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    if not paragraphs:
        paragraphs = ["Knowledge update"]
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": paragraph}]}
            for paragraph in paragraphs
        ],
    }


def normalize_storyblok_content(content: dict[str, object]) -> dict[str, object]:
    """Coerce agent JSON into the exact component contracts provisioned in Storyblok."""
    result = dict(content)
    result["body"] = _storyblok_richtext(result.get("body"))
    for key, value in list(result.items()):
        if key.startswith("body__i18n__"):
            result[key] = _storyblok_richtext(value)

    citations: list[dict[str, object]] = []
    raw_evidence = result.get("evidence")
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if not isinstance(item, dict):
                continue
            source_type = str(item.get("source_type") or "conversation")
            if source_type not in {"conversation", "storyblok", "url"}:
                source_type = "conversation"
            citations.append({
                "_uid": str(uuid4()),
                "component": "sh_evidence",
                "source_type": source_type,
                "title": str(item.get("title") or "Support conversation evidence"),
                "uri": str(item.get("uri") or item.get("source_uri") or ""),
                "excerpt": str(item.get("excerpt") or ""),
                "observed_at": item.get("observed_at"),
                "checksum": str(item.get("checksum") or item.get("content_hash") or item.get("id") or ""),
            })
    result["evidence"] = citations

    variants: list[dict[str, object]] = []
    raw_variants = result.get("channel_variants")
    if isinstance(raw_variants, list):
        for item in raw_variants:
            if not isinstance(item, dict):
                continue
            if item.get("component") == "sh_channel_variant" and item.get("channel"):
                normalized = dict(item)
                normalized["_uid"] = str(normalized.get("_uid") or uuid4())
                normalized["answer"] = _storyblok_richtext(normalized.get("answer"))
                variants.append(normalized)
                continue
            entries = (
                [(str(item.get("channel")), item)]
                if item.get("channel")
                else [(str(channel), payload) for channel, payload in item.items()]
            )
            for channel, payload in entries:
                if channel not in {"web", "assistant", "support", "widget"}:
                    continue
                payload_dict = payload if isinstance(payload, dict) else {"answer": payload}
                variants.append({
                    "_uid": str(uuid4()),
                    "component": "sh_channel_variant",
                    "channel": channel,
                    "headline": str(payload_dict.get("headline") or payload_dict.get("title") or result.get("title") or ""),
                    "answer": _storyblok_richtext(payload_dict.get("answer") or payload_dict.get("summary") or result.get("summary")),
                })
    result["channel_variants"] = variants

    component = str(result.get("component") or "")
    summary = str(result.get("summary") or result.get("title") or "Knowledge update")
    if component == "sh_policy":
        result["scope"] = str(result.get("scope") or summary)
    elif component == "sh_faq":
        result["question"] = str(result.get("question") or result.get("title") or summary)
        result["short_answer"] = str(result.get("short_answer") or summary)
    elif component == "sh_troubleshooting":
        result["problem"] = str(result.get("problem") or summary)
    elif component == "sh_known_issue":
        result["issue_status"] = str(result.get("issue_status") or "investigating")
        result["symptoms"] = _storyblok_richtext(result.get("symptoms") or result.get("body"))
    elif component == "sh_release_note":
        result["version"] = str(result.get("version") or "Unspecified")
        result["released_at"] = result.get("released_at") or datetime.now(timezone.utc).isoformat()
        result["changes"] = _storyblok_richtext(result.get("changes") or result.get("body"))
    return result


async def run_analysis_pipeline(db: Session, run_id: UUID) -> None:
    run = db.query(KnowledgeRun).filter(KnowledgeRun.id == run_id).first()
    if not run:
        raise RuntimeError(f"Knowledge run {run_id} not found")
    if run.status == "completed":
        return
    connection = db.query(StoryblokConnection).filter(
        StoryblokConnection.project_id == run.project_id,
        StoryblokConnection.is_active.is_(True),
    ).first()
    if not connection:
        run.status = "failed"
        run.error = "Storyblok is not connected"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    existing_proposal = db.query(KnowledgeProposal).join(
        KnowledgeFinding, KnowledgeProposal.finding_id == KnowledgeFinding.id
    ).filter(KnowledgeFinding.run_id == run.id).first()
    if existing_proposal:
        finding = db.query(KnowledgeFinding).filter_by(id=existing_proposal.finding_id).first()
        if existing_proposal.status not in {ProposalStatus.DRAFTING.value, ProposalStatus.FAILED.value}:
            run.status = "completed"
            run.current_stage = "human_review"
            run.error = None
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        storyblok = StoryblokClient(credentials_for(connection), db=db, proposal_id=existing_proposal.id)
        if not existing_proposal.storyblok_story_id:
            full_slug = f"{connection.folder_slug.rstrip('/')}/{existing_proposal.slug}"
            story = await storyblok.find_management_story(full_slug, int(connection.folder_id or 0))
            if story is None:
                response = await storyblok.create_draft(
                    name=existing_proposal.title,
                    slug=existing_proposal.slug,
                    content=existing_proposal.content_payload,
                    parent_id=int(connection.folder_id or 0),
                )
                story = response.get("story") if isinstance(response.get("story"), dict) else None
            if not story or not story.get("id"):
                raise RuntimeError("Could not recover the Storyblok draft")
            existing_proposal.storyblok_story_id = str(story["id"])
            existing_proposal.storyblok_uuid = str(story.get("uuid") or "") or None
            existing_proposal.storyblok_full_slug = str(story.get("full_slug") or full_slug)
        reviewing_stage_id = connection.workflow_stage_ids.get("reviewing")
        if reviewing_stage_id:
            await storyblok.move_to_stage(existing_proposal.storyblok_story_id, reviewing_stage_id)
        existing_proposal.status = ProposalStatus.REVIEWING.value
        if finding:
            finding.status = FindingStatus.DRAFTED.value
        run.status = "completed"
        run.current_stage = "human_review"
        run.error = None
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    clustered_ids = run.stage_results.get("cluster_evidence_ids") if isinstance(run.stage_results, dict) else None
    evidence_query = db.query(KnowledgeEvidence).filter(
        KnowledgeEvidence.project_id == run.project_id,
        KnowledgeEvidence.purged_at.is_(None),
    )
    if isinstance(clustered_ids, list) and clustered_ids:
        evidence_query = evidence_query.filter(
            KnowledgeEvidence.id.in_([UUID(str(value)) for value in clustered_ids])
        )
    else:
        evidence_query = evidence_query.filter(KnowledgeEvidence.session_id == run.session_id)
    evidence = evidence_query.order_by(KnowledgeEvidence.observed_at.asc()).all()
    if not evidence:
        run.status = "failed"
        run.error = "No conversation evidence was captured for this session"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.current_stage = "load_canonical_content"
    db.commit()

    storyblok = StoryblokClient(credentials_for(connection), db=db)
    current_content_response = await storyblok.list_published_stories(connection.folder_slug, "en")
    current_raw = current_content_response.get("stories", [])
    current_content = [item for item in current_raw if isinstance(item, dict)] if isinstance(current_raw, list) else []
    distinct_sessions = {str(item.session_id) for item in evidence if item.session_id}
    occurrence_count = len(distinct_sessions) if distinct_sessions else len(evidence)
    agent_input: dict[str, object] = {
        "evidence": evidence_payload(evidence),
        "current_content": current_content,
        "occurrence_count": occurrence_count,
        "locales": connection.locales,
        "prompt_version": run.prompt_version,
    }

    findings: list[KnowledgeFinding] = []
    stage_results: dict[str, object] = {}
    total_tokens = 0
    for agent_type in ("gap_detection", "contradiction_staleness"):
        run.current_stage = agent_type
        db.commit()
        response = await ai_service_client.run_knowledge_agent(str(run.project_id), agent_type, agent_input)
        output = _agent_output(response)
        stage_results[agent_type] = output
        total_tokens += int(response.get("token_count", 0) or 0)
        _record_agent_stage(db, run, agent_type, response, output, evidence)
        if output.get("detected") is not True:
            db.commit()
            continue
        confidence = _number(output.get("confidence"))
        occurrence_count = max(occurrence_count, 1)
        severity = str(output.get("severity", "medium"))
        draftable = confidence >= settings.KNOWLEDGE_MIN_CONFIDENCE and (
            occurrence_count >= settings.KNOWLEDGE_MIN_OCCURRENCES or severity == "critical"
        )
        finding = KnowledgeFinding(
            project_id=run.project_id,
            run_id=run.id,
            kind=str(output.get("kind", "gap")),
            status=FindingStatus.DRAFTABLE.value if draftable else FindingStatus.TRIAGE.value,
            title=str(output.get("title", "Knowledge issue detected")),
            summary=str(output.get("summary", "Support evidence does not match canonical knowledge.")),
            representative_question=str(output.get("representative_question", "")),
            severity=severity,
            confidence=confidence,
            occurrence_count=occurrence_count,
            evidence_ids=_strings(output.get("evidence_ids")) or [str(item.id) for item in evidence],
            related_story_uuids=_strings(output.get("related_story_uuids")),
        )
        db.add(finding)
        db.flush()
        findings.append(finding)
        audit(
            db,
            project_id=run.project_id,
            actor_type="agent",
            actor_id=agent_type,
            action="finding.detected",
            entity_type="finding",
            entity_id=str(finding.id),
            detail={"kind": finding.kind, "confidence": confidence, "draftable": draftable},
        )
        db.commit()

    candidates = [item for item in findings if item.status == FindingStatus.DRAFTABLE.value]
    if not candidates:
        run.status = "completed"
        run.current_stage = "triage"
        run.stage_results = stage_results
        run.token_count = total_tokens
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    primary = max(candidates, key=lambda item: item.confidence)
    proposal_id = uuid4()
    draft_input = {
        **agent_input,
        "finding": {
            "id": str(primary.id),
            "kind": primary.kind,
            "title": primary.title,
            "summary": primary.summary,
            "representative_question": primary.representative_question,
            "severity": primary.severity,
            "confidence": primary.confidence,
            "source_proposal_id": str(proposal_id),
        },
    }
    run.current_stage = "content_drafting"
    db.commit()
    draft_response = await ai_service_client.run_knowledge_agent(str(run.project_id), "content_drafting", draft_input)
    draft_output = _agent_output(draft_response)
    _record_agent_stage(db, run, "content_drafting", draft_response, draft_output, evidence)
    total_tokens += int(draft_response.get("token_count", 0) or 0)
    content = draft_output.get("content")
    if not isinstance(content, dict):
        raise RuntimeError("Drafting agent did not return Storyblok content")
    if content.get("component") not in ROOT_COMPONENTS:
        raise RuntimeError("Drafting agent returned an unsupported Storyblok root component")
    content["source_proposal_id"] = str(proposal_id)
    stage_results["content_drafting"] = draft_output

    verification_input = {**draft_input, "draft": draft_output}
    run.current_stage = "evidence_verification"
    db.commit()
    verification_response = await ai_service_client.run_knowledge_agent(
        str(run.project_id), "evidence_verification", verification_input
    )
    verification = _agent_output(verification_response)
    _record_agent_stage(db, run, "evidence_verification", verification_response, verification, evidence)
    total_tokens += int(verification_response.get("token_count", 0) or 0)
    evidence_score = _number(verification.get("evidence_score"))
    stage_results["evidence_verification"] = verification

    run.current_stage = "localization"
    db.commit()
    localization_response = await ai_service_client.run_knowledge_agent(
        str(run.project_id), "localization", verification_input
    )
    localization = _agent_output(localization_response)
    _record_agent_stage(db, run, "localization", localization_response, localization, evidence)
    total_tokens += int(localization_response.get("token_count", 0) or 0)
    translations = localization.get("translations")
    content = apply_storyblok_translations(
        content,
        translations if isinstance(translations, dict) else {},
        connection.locales,
    )
    content = normalize_storyblok_content(content)
    stage_results["localization"] = localization

    quality_input = {**verification_input, "draft": {**draft_output, "content": content}}
    run.current_stage = "quality_check"
    db.commit()
    quality_response = await ai_service_client.run_knowledge_agent(
        str(run.project_id), "quality_check", quality_input
    )
    quality = _agent_output(quality_response)
    _record_agent_stage(db, run, "quality_check", quality_response, quality, evidence)
    total_tokens += int(quality_response.get("token_count", 0) or 0)
    quality_score = _number(quality.get("quality_score"))
    localization_score = _number(localization.get("localization_score"))
    stage_results["quality_check"] = quality

    gates_passed = (
        verification.get("supported") is True
        and evidence_score >= settings.KNOWLEDGE_MIN_EVIDENCE_SCORE
        and quality_score >= settings.KNOWLEDGE_MIN_QUALITY_SCORE
        and quality.get("schema_valid") is True
        and quality.get("citations_complete") is True
        and _number(quality.get("duplicate_risk"), 1) <= 0.4
    )
    if not gates_passed:
        primary.status = FindingStatus.TRIAGE.value
        run.status = "completed"
        run.current_stage = "quality_triage"
        run.stage_results = stage_results
        run.token_count = total_tokens
        run.completed_at = datetime.now(timezone.utc)
        audit(
            db,
            project_id=run.project_id,
            actor_type="agent",
            actor_id="quality_check",
            action="proposal.gate_failed",
            entity_type="finding",
            entity_id=str(primary.id),
            detail={
                "evidence_score": evidence_score,
                "quality_score": quality_score,
                "supported": verification.get("supported"),
                "schema_valid": quality.get("schema_valid"),
                "citations_complete": quality.get("citations_complete"),
                "duplicate_risk": quality.get("duplicate_risk"),
            },
        )
        db.commit()
        return

    proposal = KnowledgeProposal(
        id=proposal_id,
        project_id=run.project_id,
        finding_id=primary.id,
        status=ProposalStatus.DRAFTING.value,
        content_type=str(draft_output.get("content_type", content.get("component", "sh_faq"))),
        title=str(draft_output.get("title", primary.title)),
        slug=str(draft_output.get("slug", f"knowledge-{proposal_id.hex[:8]}")),
        content_payload=content,
        evidence_score=evidence_score,
        quality_score=quality_score,
        localization_score=localization_score,
    )
    db.add(proposal)
    db.flush()

    run.current_stage = "storyblok_draft"
    db.commit()
    storyblok = StoryblokClient(credentials_for(connection), db=db, proposal_id=proposal.id)
    draft = await storyblok.create_draft(
        name=proposal.title,
        slug=proposal.slug,
        content=content,
        parent_id=int(connection.folder_id or 0),
    )
    story = draft.get("story")
    if not isinstance(story, dict) or not story.get("id"):
        raise RuntimeError("Storyblok draft response is missing the story")
    proposal.storyblok_story_id = str(story["id"])
    proposal.storyblok_uuid = str(story.get("uuid") or "") or None
    proposal.storyblok_full_slug = str(story.get("full_slug") or "") or None
    reviewing_stage_id = connection.workflow_stage_ids.get("reviewing")
    if reviewing_stage_id:
        await storyblok.move_to_stage(proposal.storyblok_story_id, reviewing_stage_id)
    proposal.status = ProposalStatus.REVIEWING.value
    primary.status = FindingStatus.DRAFTED.value
    run.status = "completed"
    run.current_stage = "human_review"
    run.stage_results = stage_results
    run.token_count = total_tokens
    run.model = str(draft_response.get("model") or "") or None
    run.completed_at = datetime.now(timezone.utc)
    audit(
        db,
        project_id=run.project_id,
        actor_type="agent",
        actor_id="content_drafting",
        action="storyblok.draft_created",
        entity_type="proposal",
        entity_id=str(proposal.id),
        detail={
            "story_id": proposal.storyblok_story_id,
            "story_uuid": proposal.storyblok_uuid,
            "quality_score": quality_score,
            "evidence_score": evidence_score,
        },
    )
    db.commit()


def purge_expired_evidence(db: Session) -> int:
    now = datetime.now(timezone.utc)
    rows = db.query(KnowledgeEvidence).filter(
        KnowledgeEvidence.expires_at <= now,
        KnowledgeEvidence.purged_at.is_(None),
    ).all()
    for item in rows:
        item.excerpt_encrypted = None
        item.purged_at = now
    db.commit()
    return len(rows)


def richtext_to_text(value: object) -> str:
    parts: list[str] = []

    def visit(node: object) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str):
                parts.append(text)
            for key, child in node.items():
                if key not in {"text", "type", "attrs", "_uid", "component", "checksum", "source_proposal_id"}:
                    visit(child)

    visit(value)
    return "\n".join(dict.fromkeys(part.strip() for part in parts if part.strip()))


def normalize_story(story: dict[str, object], locale: str) -> dict[str, object]:
    content = story.get("content")
    content_object = content if isinstance(content, dict) else {}
    title = str(content_object.get("title") or story.get("name") or "Knowledge entry")
    raw_citations = content_object.get("evidence") or content_object.get("citations") or []
    citations = raw_citations if isinstance(raw_citations, list) else []
    raw_channels = content_object.get("channel_variants") or []
    channels: dict[str, object] = {}
    if isinstance(raw_channels, list):
        for item in raw_channels:
            if isinstance(item, dict) and item.get("channel"):
                channels[str(item["channel"])] = item.get("body") or item.get("answer") or ""
    body_text = richtext_to_text(content_object.get("body"))
    summary_text = str(content_object.get("summary") or "").strip()
    canonical_text = "\n\n".join(part for part in (summary_text, body_text) if part).strip()
    return {
        "external_id": f"{story.get('uuid')}:{locale}",
        "source_type": "storyblok",
        "story_uuid": str(story.get("uuid") or ""),
        "story_id": str(story.get("id") or ""),
        "full_slug": str(story.get("full_slug") or ""),
        "title": title,
        "locale": locale,
        "content_type": str(content_object.get("component") or "knowledge"),
        "published_at": story.get("published_at") or story.get("first_published_at"),
        "text": canonical_text or title,
        "content_hash": hashlib.sha256(
            json.dumps(content_object, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "citations": citations,
        "channel_variants": channels,
        "metadata": {
            "storyblok_uuid": str(story.get("uuid") or ""),
            "full_slug": str(story.get("full_slug") or ""),
            "locale": locale,
            "published_at": story.get("published_at") or story.get("first_published_at"),
            "source_url": f"/help/{story.get('full_slug')}",
        },
    }


def count_questions_processed(db: Session, project_id: UUID) -> int:
    return int(db.query(func.count(KnowledgeEvidence.id)).filter(KnowledgeEvidence.project_id == project_id).scalar() or 0)
