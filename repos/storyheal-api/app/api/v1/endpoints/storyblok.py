"""Storyblok connection, provisioning, synchronization, and canonical delivery APIs."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import public_rate_limit
from app.core.security import get_current_active_user, require_permission
from app.models import Staff, StoryblokConnection, StoryblokOperation, StoryblokWebhookReceipt
from app.schemas.knowledge_ops import (
    StoryblokConnectionUpsert,
    StoryblokConnectionView,
    StoryblokDraftTokenRotate,
    StoryblokProvisionResult,
    StoryblokTestResult,
)
from app.services.knowledge_ops_service import audit, credentials_for, normalize_story
from app.services.storyblok_client import StoryblokAPIError, StoryblokClient
from app.tasks.knowledge_ops import process_storyblok_webhook
from app.utils.crypto import decrypt_str, encrypt_str

router = APIRouter()


def _connection_view(connection: StoryblokConnection) -> StoryblokConnectionView:
    return StoryblokConnectionView(
        id=connection.id,
        project_id=connection.project_id,
        region=connection.region,
        space_id=connection.space_id,
        folder_id=connection.folder_id,
        folder_slug=connection.folder_slug,
        rag_collection_id=connection.rag_collection_id,
        locales=connection.locales,
        workflow_stage_ids=connection.workflow_stage_ids,
        component_ids=connection.component_ids,
        public_webhook_url=connection.public_webhook_url,
        is_active=connection.is_active,
        draft_token_configured=bool(connection.draft_token_encrypted),
        publisher_token_configured=bool(connection.publisher_token_encrypted),
        delivery_token_configured=bool(connection.delivery_token_encrypted),
        webhook_secret_configured=bool(connection.webhook_secret_encrypted),
        last_tested_at=connection.last_tested_at,
        last_synced_at=connection.last_synced_at,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _get_connection(db: Session, project_id) -> StoryblokConnection:
    connection = db.query(StoryblokConnection).filter_by(project_id=project_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Storyblok is not connected")
    return connection


@router.get("/connection", response_model=StoryblokConnectionView)
def get_connection(
    current_user: Staff = Depends(get_current_active_user), db: Session = Depends(get_db)
) -> StoryblokConnectionView:
    return _connection_view(_get_connection(db, current_user.project_id))


@router.put("/connection", response_model=StoryblokConnectionView)
def upsert_connection(
    payload: StoryblokConnectionUpsert,
    current_user: Staff = Depends(require_permission("storyblok:admin")),
    db: Session = Depends(get_db),
) -> StoryblokConnectionView:
    connection = db.query(StoryblokConnection).filter_by(project_id=current_user.project_id).first()
    if not connection:
        connection = StoryblokConnection(project_id=current_user.project_id)
        db.add(connection)
    connection.region = payload.region
    connection.space_id = payload.space_id
    connection.draft_token_encrypted = encrypt_str(payload.draft_token.get_secret_value())
    connection.publisher_token_encrypted = encrypt_str(payload.publisher_token.get_secret_value())
    connection.delivery_token_encrypted = encrypt_str(payload.delivery_token.get_secret_value())
    connection.webhook_secret_encrypted = encrypt_str(payload.webhook_secret.get_secret_value())
    connection.folder_slug = payload.folder_slug
    connection.rag_collection_id = str(payload.rag_collection_id)
    connection.locales = list(dict.fromkeys(payload.locales))
    connection.public_webhook_url = payload.public_webhook_url
    connection.is_active = True
    audit(
        db,
        project_id=current_user.project_id,
        actor_type="staff",
        actor_id=str(current_user.id),
        action="storyblok.connection.updated",
        entity_type="storyblok_connection",
        entity_id=str(connection.id),
        detail={"region": payload.region, "space_id": payload.space_id, "locales": connection.locales},
    )
    db.commit()
    db.refresh(connection)
    return _connection_view(connection)


@router.patch("/connection/draft-token", response_model=StoryblokConnectionView)
def rotate_draft_token(
    payload: StoryblokDraftTokenRotate,
    current_user: Staff = Depends(require_permission("storyblok:admin")),
    db: Session = Depends(get_db),
) -> StoryblokConnectionView:
    """Rotate only the encrypted draft credential without exposing other secrets."""
    connection = _get_connection(db, current_user.project_id)
    connection.draft_token_encrypted = encrypt_str(payload.draft_token.get_secret_value())
    connection.updated_at = datetime.now(timezone.utc)
    audit(
        db,
        project_id=current_user.project_id,
        actor_type="staff",
        actor_id=str(current_user.id),
        action="storyblok.draft_token.rotated",
        entity_type="storyblok_connection",
        entity_id=str(connection.id),
        detail={},
    )
    db.commit()
    db.refresh(connection)
    return _connection_view(connection)


@router.post("/test", response_model=StoryblokTestResult)
async def test_connection(
    current_user: Staff = Depends(require_permission("storyblok:admin")), db: Session = Depends(get_db)
) -> StoryblokTestResult:
    connection = _get_connection(db, current_user.project_id)
    client = StoryblokClient(credentials_for(connection), db=db)
    try:
        draft_space = await client.get_space()
        publisher_space = await client.get_space(publisher=True)
        await client.list_published_stories(connection.folder_slug, connection.locales[0])
        connection.last_tested_at = datetime.now(timezone.utc)
        db.commit()
        space = draft_space.get("space")
        name = str(space.get("name")) if isinstance(space, dict) and space.get("name") else None
        return StoryblokTestResult(
            success=True,
            space_name=name,
            region=connection.region,
            draft_can_write=bool(draft_space),
            publisher_can_publish=bool(publisher_space),
            delivery_can_read=True,
            detail="All Storyblok credentials and the Content Delivery API are reachable.",
        )
    except StoryblokAPIError as exc:
        db.commit()
        return StoryblokTestResult(
            success=False,
            region=connection.region,
            draft_can_write=False,
            publisher_can_publish=False,
            delivery_can_read=False,
            detail=str(exc),
        )


@router.post("/provision", response_model=StoryblokProvisionResult)
async def provision(
    current_user: Staff = Depends(require_permission("storyblok:admin")), db: Session = Depends(get_db)
) -> StoryblokProvisionResult:
    connection = _get_connection(db, current_user.project_id)
    before = db.query(StoryblokOperation).filter_by(project_id=current_user.project_id).count()
    client = StoryblokClient(credentials_for(connection), db=db)
    folder_id, component_ids, workflow_stage_ids, webhook_id = await client.provision(
        folder_slug=connection.folder_slug,
        public_webhook_url=connection.public_webhook_url,
        webhook_secret=decrypt_str(connection.webhook_secret_encrypted) or "",
    )
    connection.folder_id = folder_id
    connection.component_ids = component_ids
    connection.workflow_stage_ids = workflow_stage_ids
    audit(
        db,
        project_id=current_user.project_id,
        actor_type="staff",
        actor_id=str(current_user.id),
        action="storyblok.space.provisioned",
        entity_type="storyblok_connection",
        entity_id=str(connection.id),
        detail={"folder_id": folder_id, "components": list(component_ids)},
    )
    db.commit()
    operations = db.query(StoryblokOperation).filter_by(project_id=current_user.project_id).count() - before
    return StoryblokProvisionResult(
        folder_id=folder_id,
        component_ids=component_ids,
        workflow_stage_ids=workflow_stage_ids,
        webhook_id=webhook_id,
        operations=operations,
    )


@router.post("/sync")
async def sync_published(
    current_user: Staff = Depends(require_permission("storyblok:admin")), db: Session = Depends(get_db)
) -> dict[str, int]:
    connection = _get_connection(db, current_user.project_id)
    client = StoryblokClient(credentials_for(connection), db=db)
    primary_locale = connection.locales[0] if connection.locales else "en"
    response = await client.list_published_stories(connection.folder_slug, primary_locale)
    stories = response.get("stories", [])
    receipt_ids: list[str] = []
    for story in stories if isinstance(stories, list) else []:
        if not isinstance(story, dict):
            continue
        normalized = normalize_story(story, primary_locale)
        event_key = hashlib.sha256(
            f"sync:{normalized['story_uuid']}:{normalized['content_hash']}".encode("utf-8")
        ).hexdigest()
        if db.query(StoryblokWebhookReceipt).filter_by(
            project_id=current_user.project_id, event_key=event_key
        ).first():
            continue
        receipt = StoryblokWebhookReceipt(
            project_id=current_user.project_id,
            event_key=event_key,
            trigger="story.published",
            story_id=str(story.get("id") or ""),
            full_slug=str(story.get("full_slug") or ""),
            payload_hash=str(normalized["content_hash"]),
        )
        db.add(receipt)
        db.flush()
        receipt_ids.append(str(receipt.id))
    connection.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    for receipt_id in receipt_ids:
        try:
            process_storyblok_webhook.delay(receipt_id)
        except Exception:
            pass
    return {"queued": len(receipt_ids)}


@router.get("/public/content")
async def public_content(
    project_id: UUID | None = Query(default=None), locale: str = Query("en"),
    _: None = Depends(public_rate_limit), db: Session = Depends(get_db)
) -> dict[str, Any]:
    if project_id:
        connection = _get_connection(db, project_id)
    else:
        connection = db.query(StoryblokConnection).filter_by(is_active=True).order_by(
            StoryblokConnection.created_at.asc()
        ).first()
        if not connection:
            raise HTTPException(status_code=404, detail="No public help center is configured")
    if locale not in connection.locales:
        raise HTTPException(status_code=404, detail="Locale is not configured")
    client = StoryblokClient(credentials_for(connection))
    data = await client.list_published_stories(connection.folder_slug, locale)
    stories = data.get("stories", [])
    return {
        "locale": locale,
        "source": "storyblok-cda",
        "stories": [normalize_story(item, locale) for item in stories if isinstance(item, dict)]
        if isinstance(stories, list) else [],
    }
