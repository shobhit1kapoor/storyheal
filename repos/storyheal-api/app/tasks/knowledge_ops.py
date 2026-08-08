"""Durable closed-loop tasks. Every task is idempotent and safe to retry."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID
from urllib.parse import urlsplit

from sqlalchemy import func, or_

from app.core.database import SessionLocal
from app.core.metrics import KNOWLEDGE_RUNS, RAG_INDEXING_DURATION, RAG_REFRESHES, WEBHOOKS
from app.models import (
    KnowledgeProposal,
    KnowledgeEvidence,
    KnowledgeAgentStage,
    KnowledgeRun,
    ProposalStatus,
    StoryblokConnection,
    StoryblokWebhookReceipt,
)
from app.services.knowledge_ops_service import (
    audit,
    credentials_for,
    normalize_story,
    purge_expired_evidence,
    run_analysis_pipeline,
)
from app.services.rag_client import rag_client
from app.services.storyblok_client import StoryblokClient
from app.tasks.celery_app import celery_app


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(
    name="app.tasks.knowledge_ops.run_knowledge_analysis",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 4},
)
def run_knowledge_analysis(self, run_id: str) -> None:
    try:
        with SessionLocal() as db:
            _run(run_analysis_pipeline(db, UUID(run_id)))
            run = db.query(KnowledgeRun).filter_by(id=UUID(run_id)).first()
            KNOWLEDGE_RUNS.labels(result=run.status if run else "missing").inc()
    except Exception as exc:
        KNOWLEDGE_RUNS.labels(result="failed").inc()
        with SessionLocal() as failure_db:
            run = failure_db.query(KnowledgeRun).filter_by(id=UUID(run_id)).first()
            if run:
                run.status = "failed"
                run.error = str(exc)[:2000]
                run.completed_at = datetime.now(timezone.utc)
                failure_db.add(KnowledgeAgentStage(
                    project_id=run.project_id,
                    run_id=run.id,
                    agent_type=run.current_stage or "pipeline",
                    status="failed",
                    prompt_version=run.prompt_version,
                    token_count=0,
                    evidence_ids=[],
                    retry_count=int(self.request.retries),
                    output={},
                    error=run.error,
                ))
                failure_db.commit()
        raise


async def _process_receipt(receipt_id: UUID) -> None:
    with SessionLocal() as db:
        receipt = db.query(StoryblokWebhookReceipt).filter_by(id=receipt_id).first()
        if not receipt or receipt.status == "processed":
            return
        connection = db.query(StoryblokConnection).filter_by(
            project_id=receipt.project_id, is_active=True
        ).first()
        if not connection:
            raise RuntimeError("No active Storyblok connection for webhook")

        receipt.status = "processing"
        db.commit()
        client = StoryblokClient(credentials_for(connection), db=db)
        proposal = db.query(KnowledgeProposal).filter(
            KnowledgeProposal.project_id == receipt.project_id,
            or_(
                KnowledgeProposal.storyblok_story_id == receipt.story_id,
                KnowledgeProposal.storyblok_full_slug == receipt.full_slug,
            ),
        ).first()

        try:
            if receipt.trigger == "story.published":
                if not receipt.full_slug:
                    raise RuntimeError("Published webhook did not include a full slug")
                if proposal:
                    proposal.status = ProposalStatus.INDEXING.value
                    db.commit()
                indexed_at = datetime.now(timezone.utc)
                indexed_uuid: str | None = None
                published_at: datetime | None = None
                indexed_hash: str | None = None
                for locale in connection.locales:
                    response = await client.get_published_story(receipt.full_slug, locale)
                    story = response.get("story")
                    if not isinstance(story, dict):
                        raise RuntimeError(f"CDA returned no published story for locale {locale}")
                    normalized = normalize_story(story, locale)
                    public_origin = urlsplit(connection.public_webhook_url)
                    source_url = f"{public_origin.scheme}://{public_origin.netloc}/help/{normalized['full_slug']}"
                    indexed_uuid = str(normalized["story_uuid"])
                    indexed_hash = str(normalized["content_hash"])
                    raw_published_at = normalized.get("published_at")
                    if isinstance(raw_published_at, str) and raw_published_at:
                        try:
                            published_at = datetime.fromisoformat(raw_published_at.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    await rag_client.upsert_storyblok_source(
                        project_id=str(receipt.project_id),
                        collection_id=connection.rag_collection_id,
                        story_uuid=indexed_uuid,
                        source={
                            "locale": locale,
                            "title": normalized["title"],
                            "slug": normalized["full_slug"],
                            "content_type": normalized["content_type"],
                            "content": normalized["text"],
                            "content_hash": normalized["content_hash"],
                            "published_at": normalized["published_at"],
                            "source_url": source_url,
                            "citations": normalized["citations"],
                            "channel_variants": normalized["channel_variants"],
                            "metadata": normalized["metadata"],
                        },
                    )
                if proposal:
                    proposal.storyblok_uuid = indexed_uuid or proposal.storyblok_uuid
                    proposal.content_hash = indexed_hash
                    proposal.status = ProposalStatus.INDEXED.value
                    proposal.indexed_at = indexed_at
                    proposal.published_at = published_at or indexed_at
                action = "storyblok.publication.indexed"
            else:
                story_uuid = proposal.storyblok_uuid if proposal else None
                if not story_uuid:
                    raise RuntimeError("Cannot remove vectors without the Storyblok UUID")
                await rag_client.delete_storyblok_source(
                    project_id=str(receipt.project_id),
                    collection_id=connection.rag_collection_id,
                    story_uuid=story_uuid,
                )
                if proposal:
                    proposal.status = ProposalStatus.REVIEWING.value
                    proposal.indexed_at = None
                action = "storyblok.publication.removed"

            receipt.status = "processed"
            receipt.processed_at = datetime.now(timezone.utc)
            receipt.error = None
            audit(
                db,
                project_id=receipt.project_id,
                actor_type="webhook",
                action=action,
                entity_type="storyblok_story",
                entity_id=receipt.story_id,
                detail={"trigger": receipt.trigger, "full_slug": receipt.full_slug},
            )
            db.commit()
            WEBHOOKS.labels(trigger=receipt.trigger, result="processed").inc()
            RAG_REFRESHES.labels(event=receipt.trigger, result="success").inc()
            received_at = receipt.received_at
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
            RAG_INDEXING_DURATION.observe(max(0, (receipt.processed_at - received_at).total_seconds()))
        except Exception as exc:
            receipt.status = "failed"
            receipt.error = str(exc)[:2000]
            if proposal:
                proposal.status = ProposalStatus.FAILED.value
                proposal.last_error = receipt.error
            db.commit()
            WEBHOOKS.labels(trigger=receipt.trigger, result="failed").inc()
            RAG_REFRESHES.labels(event=receipt.trigger, result="failure").inc()
            raise


@celery_app.task(
    name="app.tasks.knowledge_ops.process_storyblok_webhook",
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_jitter=True,
    retry_kwargs={"max_retries": 8},
)
def process_storyblok_webhook(receipt_id: str) -> None:
    _run(_process_receipt(UUID(receipt_id)))


@celery_app.task(name="app.tasks.knowledge_ops.purge_expired_evidence_task")
def purge_expired_evidence_task() -> int:
    with SessionLocal() as db:
        return purge_expired_evidence(db)


@celery_app.task(name="app.tasks.knowledge_ops.recover_storyblok_webhooks")
def recover_storyblok_webhooks() -> int:
    """Requeue receipts left behind by broker failure or a terminated worker."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    with SessionLocal() as db:
        receipts = db.query(StoryblokWebhookReceipt).filter(
            or_(
                StoryblokWebhookReceipt.status.in_(["queued", "failed"]),
                (StoryblokWebhookReceipt.status == "processing")
                & (StoryblokWebhookReceipt.received_at < cutoff),
            )
        ).order_by(StoryblokWebhookReceipt.received_at.asc()).limit(100).all()
        ids = [str(receipt.id) for receipt in receipts]
        for receipt in receipts:
            receipt.status = "queued"
            receipt.error = None
        db.commit()
    for receipt_id in ids:
        process_storyblok_webhook.delay(receipt_id)
    return len(ids)


@celery_app.task(name="app.tasks.knowledge_ops.cluster_repeated_questions")
def cluster_repeated_questions() -> int:
    """Queue exact redacted-question clusters repeated across sessions in seven days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    run_ids: list[str] = []
    with SessionLocal() as db:
        hashes = db.query(KnowledgeEvidence.project_id, KnowledgeEvidence.content_hash).filter(
            KnowledgeEvidence.observed_at >= cutoff,
            KnowledgeEvidence.purged_at.is_(None),
            KnowledgeEvidence.session_id.is_not(None),
        ).group_by(KnowledgeEvidence.project_id, KnowledgeEvidence.content_hash).having(
            func.count(func.distinct(KnowledgeEvidence.session_id)) >= 2
        ).all()
        for project_id, content_hash in hashes:
            evidence = db.query(KnowledgeEvidence).filter(
                KnowledgeEvidence.project_id == project_id,
                KnowledgeEvidence.content_hash == content_hash,
                KnowledgeEvidence.observed_at >= cutoff,
                KnowledgeEvidence.purged_at.is_(None),
            ).order_by(KnowledgeEvidence.observed_at.desc()).limit(50).all()
            if not evidence:
                continue
            already_queued = db.query(KnowledgeRun).filter(
                KnowledgeRun.project_id == evidence[0].project_id,
                KnowledgeRun.trigger == "scheduled_cluster",
                KnowledgeRun.created_at >= cutoff,
                KnowledgeRun.stage_results["cluster_hash"].astext == content_hash,
            ).first()
            if already_queued:
                continue
            run = KnowledgeRun(
                project_id=evidence[0].project_id,
                session_id=evidence[0].session_id,
                trigger="scheduled_cluster",
                stage_results={
                    "cluster_hash": content_hash,
                    "cluster_evidence_ids": [str(item.id) for item in evidence],
                },
            )
            db.add(run)
            db.flush()
            run_ids.append(str(run.id))
        db.commit()
    for run_id in run_ids:
        run_knowledge_analysis.delay(run_id)
    return len(run_ids)
