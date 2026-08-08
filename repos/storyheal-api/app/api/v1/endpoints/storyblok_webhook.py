"""Fast signed Storyblok webhook receiver with durable deduplication."""

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import public_rate_limit
from app.models import StoryblokConnection, StoryblokWebhookReceipt
from app.services.knowledge_ops_service import credentials_for
from app.services.storyblok_client import verify_webhook_signature
from app.tasks.knowledge_ops import process_storyblok_webhook

router = APIRouter()


def unpack_storyblok_event(decoded: object) -> tuple[dict[str, object], str]:
    """Accept Storyblok's direct payload and documented trigger/payload envelope."""
    if isinstance(decoded, list) and len(decoded) == 1:
        decoded = decoded[0]
    if not isinstance(decoded, dict):
        raise ValueError("Webhook body must be an object")
    envelope_trigger = str(decoded.get("trigger") or "")
    payload = decoded.get("payload") if isinstance(decoded.get("payload"), dict) else decoded
    trigger = envelope_trigger or str(payload.get("trigger") or payload.get("action") or "")
    trigger = {
        "published": "story.published",
        "unpublished": "story.unpublished",
        "deleted": "story.deleted",
    }.get(trigger, trigger)
    return payload, trigger


@router.post("/storyblok", status_code=202)
async def receive_storyblok_webhook(
    request: Request,
    _: None = Depends(public_rate_limit),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    raw_body = await request.body()
    try:
        decoded = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON webhook") from exc
    try:
        payload, trigger = unpack_storyblok_event(decoded)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    space_id = str(payload.get("space_id") or payload.get("spaceId") or "")
    connection = db.query(StoryblokConnection).filter_by(space_id=space_id, is_active=True).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Unknown Storyblok space")
    signature = request.headers.get("webhook-signature", "")
    if not verify_webhook_signature(raw_body, signature, credentials_for(connection).webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    story = payload.get("story") if isinstance(payload.get("story"), dict) else {}
    if trigger not in {"story.published", "story.unpublished", "story.deleted"}:
        raise HTTPException(status_code=422, detail="Unsupported webhook action")
    story_id = str(payload.get("story_id") or story.get("id") or "")
    full_slug = str(payload.get("full_slug") or story.get("full_slug") or "") or None
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    locale = str(payload.get("language") or payload.get("locale") or "all")
    published_at = str(payload.get("published_at") or story.get("published_at") or "")
    content_hash = str(payload.get("content_hash") or payload_hash)
    event_key = hashlib.sha256(
        f"{story_id}:{locale}:{published_at}:{content_hash}:{trigger}".encode("utf-8")
    ).hexdigest()

    existing = db.query(StoryblokWebhookReceipt).filter_by(
        project_id=connection.project_id, event_key=event_key
    ).first()
    if existing:
        return {"accepted": True, "duplicate": True, "receipt_id": str(existing.id)}

    receipt = StoryblokWebhookReceipt(
        project_id=connection.project_id,
        event_key=event_key,
        trigger=trigger,
        story_id=story_id,
        full_slug=full_slug,
        payload_hash=payload_hash,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    try:
        process_storyblok_webhook.delay(str(receipt.id))
    except Exception:
        # The receipt is the durable outbox. A worker recovery scan can enqueue it later.
        pass
    return {"accepted": True, "duplicate": False, "receipt_id": str(receipt.id)}
