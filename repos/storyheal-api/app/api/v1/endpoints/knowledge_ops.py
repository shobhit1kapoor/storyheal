"""Human-governed knowledge operations and usefulness analytics."""

import csv
import io
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import public_rate_limit
from app.core.security import get_current_active_user, require_permission
from app.models import (
    KnowledgeAuditEvent,
    KnowledgeAgentStage,
    KnowledgeEvaluation,
    KnowledgeEvidence,
    KnowledgeFinding,
    KnowledgeProposal,
    KnowledgeRun,
    Platform,
    ProposalStatus,
    ResponseMetric,
    Staff,
    StoryblokConnection,
    StoryblokOperation,
    StoryblokWebhookReceipt,
    VisitorSession,
)
from app.schemas.knowledge_ops import (
    AnalyzeSessionRequest,
    AnalyticsSummary,
    AuditEventView,
    EvaluationRunRequest,
    EvaluationView,
    HelpfulFeedbackRequest,
    KnowledgeFindingView,
    KnowledgeProposalView,
    KnowledgeRunView,
    KnowledgeAgentStageView,
    ProposalDecision,
    ProposalReject,
    PublicHelpfulFeedbackRequest,
    StoryblokOperationView,
)
from app.services.ai_client import ai_service_client
from app.services.knowledge_ops_service import audit, credentials_for, evidence_payload
from app.services.storyblok_client import DELIVERY_BASES, StoryblokAPIError, StoryblokClient
from app.tasks.knowledge_ops import process_storyblok_webhook, run_knowledge_analysis

router = APIRouter()


def _proposal(
    db: Session, proposal_id: UUID, project_id: UUID, *, lock: bool = False
) -> KnowledgeProposal:
    query = db.query(KnowledgeProposal).filter_by(id=proposal_id, project_id=project_id)
    item = query.with_for_update().first() if lock else query.first()
    if not item:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return item


@router.get("/findings", response_model=list[KnowledgeFindingView])
def list_findings(
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> list[KnowledgeFinding]:
    query = db.query(KnowledgeFinding).filter_by(project_id=current_user.project_id)
    if status:
        query = query.filter(KnowledgeFinding.status == status)
    if kind:
        query = query.filter(KnowledgeFinding.kind == kind)
    return query.order_by(KnowledgeFinding.detected_at.desc()).limit(500).all()


@router.get("/proposals", response_model=list[KnowledgeProposalView])
def list_proposals(
    status: str | None = Query(default=None),
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> list[KnowledgeProposal]:
    query = db.query(KnowledgeProposal).filter_by(project_id=current_user.project_id)
    if status:
        query = query.filter(KnowledgeProposal.status == status)
    return query.order_by(KnowledgeProposal.created_at.desc()).limit(500).all()


@router.get("/proposals/{proposal_id}", response_model=KnowledgeProposalView)
def get_proposal(
    proposal_id: UUID,
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> KnowledgeProposal:
    return _proposal(db, proposal_id, current_user.project_id)


@router.get("/proposals/{proposal_id}/review-context")
async def proposal_review_context(
    proposal_id: UUID,
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    proposal = _proposal(db, proposal_id, current_user.project_id)
    finding = db.query(KnowledgeFinding).filter_by(id=proposal.finding_id).first()
    run = db.query(KnowledgeRun).filter_by(id=finding.run_id).first() if finding else None
    connection = db.query(StoryblokConnection).filter_by(project_id=current_user.project_id).first()
    evidence: list[KnowledgeEvidence] = []
    if finding:
        ids = [UUID(value) for value in finding.evidence_ids]
        evidence = db.query(KnowledgeEvidence).filter(KnowledgeEvidence.id.in_(ids)).all() if ids else []
    draft: dict[str, object] | None = None
    published: dict[str, object] | None = None
    editor_url: str | None = None
    if connection and proposal.storyblok_story_id:
        client = StoryblokClient(credentials_for(connection), db=db, proposal_id=proposal.id)
        draft = await client.get_management_story(proposal.storyblok_story_id)
        editor_url = f"https://app.storyblok.com/#/me/spaces/{connection.space_id}/stories/0/0/{proposal.storyblok_story_id}"
        if proposal.storyblok_full_slug:
            try:
                published = await client.get_published_story(proposal.storyblok_full_slug, "en")
            except StoryblokAPIError:
                published = None
    return {
        "proposal": KnowledgeProposalView.model_validate(proposal).model_dump(mode="json"),
        "finding": KnowledgeFindingView.model_validate(finding).model_dump(mode="json") if finding else None,
        "agent_outputs": run.stage_results if run else {},
        "evidence": evidence_payload(evidence),
        "live_draft": draft,
        "published_entry": published,
        "editor_url": editor_url,
    }


async def _rerun_approval_gates(
    db: Session, proposal: KnowledgeProposal, live_story: dict[str, object]
) -> tuple[float, float, bool]:
    finding = db.query(KnowledgeFinding).filter_by(id=proposal.finding_id).first()
    ids = [UUID(value) for value in finding.evidence_ids] if finding else []
    evidence = db.query(KnowledgeEvidence).filter(KnowledgeEvidence.id.in_(ids)).all() if ids else []
    gate_input = {
        "finding": {
            "title": finding.title if finding else proposal.title,
            "summary": finding.summary if finding else "",
            "confidence": finding.confidence if finding else 0,
        },
        "evidence": evidence_payload(evidence),
        "draft": live_story,
        "approval_recheck": True,
    }
    verified = await ai_service_client.run_knowledge_agent(
        str(proposal.project_id), "evidence_verification", gate_input
    )
    checked = await ai_service_client.run_knowledge_agent(
        str(proposal.project_id), "quality_check", gate_input
    )
    verification = verified.get("output") if isinstance(verified.get("output"), dict) else {}
    quality = checked.get("output") if isinstance(checked.get("output"), dict) else {}
    passed = (
        verification.get("supported") is True
        and quality.get("schema_valid") is True
        and quality.get("citations_complete") is True
        and float(quality.get("duplicate_risk", 1)) <= 0.4
    )
    return float(verification.get("evidence_score", 0)), float(quality.get("quality_score", 0)), passed


@router.post("/proposals/{proposal_id}/approve", response_model=KnowledgeProposalView)
async def approve_and_publish(
    proposal_id: UUID,
    decision: ProposalDecision,
    current_user: Staff = Depends(require_permission("knowledge:publish")),
    db: Session = Depends(get_db),
) -> KnowledgeProposal:
    proposal = _proposal(db, proposal_id, current_user.project_id, lock=True)
    if proposal.status != ProposalStatus.REVIEWING.value:
        raise HTTPException(status_code=409, detail="Only a Reviewing proposal can be approved")
    if not proposal.storyblok_story_id:
        raise HTTPException(status_code=409, detail="Proposal has no Storyblok draft")
    connection = db.query(StoryblokConnection).filter_by(project_id=current_user.project_id).first()
    if not connection:
        raise HTTPException(status_code=409, detail="Storyblok is not connected")

    client = StoryblokClient(credentials_for(connection), db=db, proposal_id=proposal.id)
    live = await client.get_management_story(proposal.storyblok_story_id, publisher=True)
    live_story = live.get("story")
    if not isinstance(live_story, dict):
        raise HTTPException(status_code=502, detail="Storyblok draft could not be re-fetched")
    evidence_score, quality_score, structural_gates = await _rerun_approval_gates(db, proposal, live_story)
    if (
        evidence_score < settings.KNOWLEDGE_MIN_EVIDENCE_SCORE
        or quality_score < settings.KNOWLEDGE_MIN_QUALITY_SCORE
        or not structural_gates
    ):
        audit(
            db, project_id=current_user.project_id, actor_type="staff", actor_id=str(current_user.id),
            action="proposal.approval_gate_failed", entity_type="proposal", entity_id=str(proposal.id),
            detail={"evidence_score": evidence_score, "quality_score": quality_score},
        )
        db.commit()
        raise HTTPException(status_code=422, detail="Latest draft no longer passes evidence and quality gates")

    proposal.published_snapshot = live_story
    proposal.evidence_score = evidence_score
    proposal.quality_score = quality_score
    proposal.reviewer_id = current_user.id
    proposal.review_reason = decision.reason
    proposal.approved_at = datetime.now(timezone.utc)
    proposal.status = ProposalStatus.APPROVED.value
    try:
        ready_stage = connection.workflow_stage_ids.get("ready_to_publish")
        if ready_stage:
            await client.move_to_stage(proposal.storyblok_story_id, ready_stage, publisher=True)
        proposal.status = ProposalStatus.PUBLISHING.value
        db.commit()
        await client.publish_story(proposal.storyblok_story_id, live_story)
    except StoryblokAPIError as exc:
        db.refresh(proposal)
        if proposal.status == ProposalStatus.INDEXED.value:
            return proposal
        proposal.status = ProposalStatus.FAILED.value
        proposal.last_error = str(exc)[:2000]
        audit(
            db, project_id=current_user.project_id, actor_type="staff", actor_id=str(current_user.id),
            action="proposal.publish_failed", entity_type="proposal", entity_id=str(proposal.id),
            detail={"error": proposal.last_error},
        )
        db.commit()
        raise HTTPException(status_code=502, detail="Storyblok publish failed; the proposal is safe to retry") from exc
    audit(
        db, project_id=current_user.project_id, actor_type="staff", actor_id=str(current_user.id),
        action="proposal.approved_and_published", entity_type="proposal", entity_id=str(proposal.id),
        detail={"reason": decision.reason, "evidence_score": evidence_score, "quality_score": quality_score},
    )
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/proposals/{proposal_id}/reject", response_model=KnowledgeProposalView)
async def reject_proposal(
    proposal_id: UUID,
    decision: ProposalReject,
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> KnowledgeProposal:
    proposal = _proposal(db, proposal_id, current_user.project_id, lock=True)
    if proposal.status != ProposalStatus.REVIEWING.value:
        raise HTTPException(status_code=409, detail="Only a Reviewing proposal can be rejected")
    proposal.status = ProposalStatus.REJECTED.value
    proposal.reviewer_id = current_user.id
    proposal.review_reason = decision.reason
    audit(
        db, project_id=current_user.project_id, actor_type="staff", actor_id=str(current_user.id),
        action="proposal.rejected", entity_type="proposal", entity_id=str(proposal.id),
        detail={"reason": decision.reason},
    )
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/proposals/{proposal_id}/retry", response_model=KnowledgeProposalView)
def retry_proposal(
    proposal_id: UUID,
    current_user: Staff = Depends(require_permission("knowledge:publish")),
    db: Session = Depends(get_db),
) -> KnowledgeProposal:
    proposal = _proposal(db, proposal_id, current_user.project_id, lock=True)
    if proposal.status != ProposalStatus.FAILED.value:
        raise HTTPException(status_code=409, detail="Only a failed proposal can be retried")
    receipt = db.query(StoryblokWebhookReceipt).filter_by(
        project_id=current_user.project_id, story_id=proposal.storyblok_story_id, status="failed"
    ).order_by(StoryblokWebhookReceipt.received_at.desc()).first()
    if not receipt:
        proposal.status = ProposalStatus.REVIEWING.value
        proposal.retry_count += 1
        proposal.last_error = None
        audit(
            db, project_id=current_user.project_id, actor_type="staff", actor_id=str(current_user.id),
            action="proposal.publish_retry_requested", entity_type="proposal", entity_id=str(proposal.id),
            detail={},
        )
        db.commit()
        db.refresh(proposal)
        return proposal
    receipt.status = "queued"
    receipt.error = None
    proposal.status = ProposalStatus.INDEXING.value
    proposal.retry_count += 1
    proposal.last_error = None
    db.commit()
    process_storyblok_webhook.delay(str(receipt.id))
    return proposal


@router.post("/analyze", response_model=KnowledgeRunView)
def analyze_session(
    payload: AnalyzeSessionRequest,
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> KnowledgeRun:
    session = db.query(VisitorSession).filter_by(
        id=payload.session_id, project_id=current_user.project_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    run = KnowledgeRun(project_id=current_user.project_id, session_id=session.id, trigger="manual")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_knowledge_analysis.delay(str(run.id))
    return run


@router.get("/runs", response_model=list[KnowledgeRunView])
def list_runs(
    current_user: Staff = Depends(require_permission("knowledge:review")), db: Session = Depends(get_db)
) -> list[KnowledgeRun]:
    return db.query(KnowledgeRun).filter_by(project_id=current_user.project_id).order_by(
        KnowledgeRun.created_at.desc()
    ).limit(500).all()


@router.get("/runs/{run_id}/stages", response_model=list[KnowledgeAgentStageView])
def list_run_stages(
    run_id: UUID,
    current_user: Staff = Depends(require_permission("knowledge:review")),
    db: Session = Depends(get_db),
) -> list[KnowledgeAgentStage]:
    run = db.query(KnowledgeRun).filter_by(id=run_id, project_id=current_user.project_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return db.query(KnowledgeAgentStage).filter_by(run_id=run.id).order_by(
        KnowledgeAgentStage.created_at.asc()
    ).all()


@router.get("/evaluations", response_model=list[EvaluationView])
def list_evaluations(
    current_user: Staff = Depends(require_permission("knowledge:analytics")),
    db: Session = Depends(get_db),
) -> list[KnowledgeEvaluation]:
    return db.query(KnowledgeEvaluation).filter_by(project_id=current_user.project_id).order_by(
        KnowledgeEvaluation.created_at.desc()
    ).limit(1000).all()


@router.post("/evaluations/run", response_model=EvaluationView)
def record_frozen_evaluation(
    payload: EvaluationRunRequest,
    current_user: Staff = Depends(require_permission("knowledge:analytics")),
    db: Session = Depends(get_db),
) -> KnowledgeEvaluation:
    """Score a frozen question replay using approved facts and published citations."""
    proposal = _proposal(db, payload.proposal_id, current_user.project_id)
    answer = " ".join(payload.answer.lower().split())
    fact_matches = [" ".join(fact.lower().split()) in answer for fact in payload.expected_facts]
    fact_score = sum(fact_matches) / len(fact_matches)
    citation_ok = bool(
        proposal.storyblok_uuid and proposal.storyblok_uuid in set(payload.citation_uuids)
    )
    accuracy = fact_score if citation_ok else fact_score * 0.8
    result = KnowledgeEvaluation(
        project_id=current_user.project_id,
        proposal_id=proposal.id,
        phase=payload.phase,
        question=payload.question,
        expected_facts=payload.expected_facts,
        answer=payload.answer,
        citation_uuids=payload.citation_uuids,
        accuracy_score=accuracy,
        response_time_ms=payload.response_time_ms,
        passed=accuracy >= 0.8 and citation_ok,
    )
    db.add(result)
    audit(
        db,
        project_id=current_user.project_id,
        actor_type="staff",
        actor_id=str(current_user.id),
        action="evaluation.recorded",
        entity_type="proposal",
        entity_id=str(proposal.id),
        detail={"phase": payload.phase, "accuracy": accuracy, "citation_ok": citation_ok},
    )
    db.commit()
    db.refresh(result)
    return result


@router.post("/feedback")
def record_helpful_feedback(
    payload: HelpfulFeedbackRequest,
    current_user: Staff = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    metric = ResponseMetric(
        project_id=current_user.project_id,
        session_id=payload.session_id,
        question_hash=payload.question_hash,
        helpful=payload.helpful,
        source_refs=payload.source_refs,
    )
    db.add(metric)
    db.commit()
    return {"recorded": True, "id": str(metric.id)}


@router.post("/public/feedback")
def record_public_feedback(
    payload: PublicHelpfulFeedbackRequest,
    _: None = Depends(public_rate_limit),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    platform = db.query(Platform).filter_by(api_key=payload.platform_api_key, is_active=True).first()
    if not platform:
        raise HTTPException(status_code=401, detail="Invalid platform key")
    metric = ResponseMetric(
        project_id=platform.project_id,
        question_hash=payload.question_hash,
        helpful=payload.helpful,
        source_refs=payload.source_refs,
    )
    db.add(metric)
    db.commit()
    return {"recorded": True, "id": str(metric.id)}


def _analytics(db: Session, project_id: UUID) -> AnalyticsSummary:
    findings = db.query(KnowledgeFinding).filter_by(project_id=project_id).all()
    proposals = db.query(KnowledgeProposal).filter_by(project_id=project_id).all()
    operations = db.query(StoryblokOperation).filter_by(project_id=project_id).all()
    evaluations = db.query(KnowledgeEvaluation).filter_by(project_id=project_id).all()
    metrics = db.query(ResponseMetric).filter_by(project_id=project_id).all()
    paired: dict[UUID, dict[str, float]] = {}
    for item in evaluations:
        paired.setdefault(item.proposal_id, {})[item.phase] = item.accuracy_score
    improvements = [(v["after"] - v["before"]) * 100 for v in paired.values() if "before" in v and "after" in v]
    published_evaluations = [item for item in evaluations if item.phase == "after"] or evaluations
    eligible = [m for m in metrics if m.resolution_outcome]
    resolved = [m for m in eligible if m.resolution_outcome == "resolved" and not m.handed_off and not m.reopened_within_24h]
    feedback = [m for m in metrics if m.helpful is not None]
    times = [m.response_time_ms for m in metrics if m.response_time_ms is not None]
    indexed = [p for p in proposals if p.indexed_at and p.published_at]
    indexing_ms = [
        (p.indexed_at - p.published_at).total_seconds() * 1000 for p in indexed
    ]
    connection = db.query(StoryblokConnection).filter_by(project_id=project_id, is_active=True).first()
    findings_by_type: dict[str, int] = {}
    proposals_by_status: dict[str, int] = {}
    content_types: dict[str, int] = {}
    channels_published: dict[str, int] = {}
    daily: dict[str, dict[str, object]] = {}
    for finding in findings:
        findings_by_type[finding.kind] = findings_by_type.get(finding.kind, 0) + 1
        key = finding.detected_at.date().isoformat()
        daily.setdefault(key, {"date": key, "questions": 0, "findings": 0, "drafts": 0, "published": 0})["findings"] += 1
    for proposal in proposals:
        proposals_by_status[proposal.status] = proposals_by_status.get(proposal.status, 0) + 1
        content_types[proposal.content_type] = content_types.get(proposal.content_type, 0) + 1
        key = proposal.created_at.date().isoformat()
        bucket = daily.setdefault(key, {"date": key, "questions": 0, "findings": 0, "drafts": 0, "published": 0})
        bucket["drafts"] += 1
        if proposal.published_at:
            publish_key = proposal.published_at.date().isoformat()
            daily.setdefault(publish_key, {"date": publish_key, "questions": 0, "findings": 0, "drafts": 0, "published": 0})["published"] += 1
            channels = proposal.content_payload.get("channels", [])
            for channel in channels if isinstance(channels, list) else []:
                channels_published[str(channel)] = channels_published.get(str(channel), 0) + 1
    evidence_rows = db.query(KnowledgeEvidence).filter_by(project_id=project_id).all()
    for evidence in evidence_rows:
        key = evidence.observed_at.date().isoformat()
        daily.setdefault(key, {"date": key, "questions": 0, "findings": 0, "drafts": 0, "published": 0})["questions"] += 1
    paired_rows = [
        {"proposal_id": str(proposal_id), "before": phases["before"], "after": phases["after"],
         "improvement": (phases["after"] - phases["before"]) * 100}
        for proposal_id, phases in paired.items() if "before" in phases and "after" in phases
    ]
    return AnalyticsSummary(
        questions_processed=db.query(func.count(KnowledgeEvidence.id)).filter_by(project_id=project_id).scalar() or 0,
        gaps_detected=sum(f.kind == "gap" for f in findings),
        contradictions_detected=sum(f.kind == "contradiction" for f in findings),
        stale_content_detected=sum(f.kind == "stale" for f in findings),
        drafts_generated=len(proposals),
        drafts_approved=sum(p.approved_at is not None for p in proposals),
        drafts_rejected=sum(p.status == ProposalStatus.REJECTED.value for p in proposals),
        stories_published=sum(p.published_at is not None for p in proposals),
        stories_indexed=sum(p.indexed_at is not None for p in proposals),
        storyblok_api_operations=len(operations),
        storyblok_api_failures=sum(not op.success for op in operations),
        response_accuracy=(sum(e.passed for e in published_evaluations) / len(published_evaluations) * 100)
        if published_evaluations else 0,
        resolution_rate=(len(resolved) / len(eligible) * 100) if eligible else 0,
        helpful_rate=(sum(bool(m.helpful) for m in feedback) / len(feedback) * 100) if feedback else 0,
        average_response_time_ms=sum(times) / len(times) if times else None,
        average_indexing_time_ms=sum(indexing_ms) / len(indexing_ms) if indexing_ms else None,
        improvement_percentage_points=sum(improvements) / len(improvements) if improvements else 0,
        findings_by_type=findings_by_type,
        proposals_by_status=proposals_by_status,
        content_types=content_types,
        locales_indexed={locale: len(indexed) for locale in (connection.locales if connection else [])},
        channels_published=channels_published,
        daily_activity=[daily[key] for key in sorted(daily)[-30:]],
        paired_evaluations=paired_rows,
    )


@router.get("/analytics", response_model=AnalyticsSummary)
def analytics(
    current_user: Staff = Depends(require_permission("knowledge:analytics")), db: Session = Depends(get_db)
) -> AnalyticsSummary:
    return _analytics(db, current_user.project_id)


@router.get("/audit-events", response_model=list[AuditEventView])
def audit_events(
    current_user: Staff = Depends(require_permission("knowledge:audit")), db: Session = Depends(get_db)
) -> list[KnowledgeAuditEvent]:
    return db.query(KnowledgeAuditEvent).filter_by(project_id=current_user.project_id).order_by(
        KnowledgeAuditEvent.created_at.desc()
    ).limit(1000).all()


@router.get("/storyblok-operations", response_model=list[StoryblokOperationView])
def storyblok_operations(
    current_user: Staff = Depends(require_permission("knowledge:audit")),
    db: Session = Depends(get_db),
) -> list[StoryblokOperation]:
    return db.query(StoryblokOperation).filter_by(project_id=current_user.project_id).order_by(
        StoryblokOperation.created_at.desc()
    ).limit(1000).all()


@router.get("/analytics/export")
def export_analytics(
    format: str = Query("json", pattern="^(json|csv)$"),
    current_user: Staff = Depends(require_permission("knowledge:analytics")),
    db: Session = Depends(get_db),
):
    data = _analytics(db, current_user.project_id).model_dump(mode="json")
    if format == "json":
        payload = json.dumps(data, indent=2).encode("utf-8")
        return StreamingResponse(io.BytesIO(payload), media_type="application/json", headers={
            "Content-Disposition": "attachment; filename=storyheal-usefulness.json"
        })
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["metric", "value"])
    writer.writerows(data.items())
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=storyheal-usefulness.csv"
    })
