"""Contract tests for the security and schema invariants of StoryHeal's loop."""

import hashlib
import hmac
from uuid import uuid4

import pytest

from app.services.knowledge_ops_service import apply_storyblok_translations, redact_text
from app.services.storyblok_client import (
    StoryblokAPIError, StoryblokClient, StoryblokCredentials, verify_webhook_signature,
)
from app.services.storyblok_components import COMPONENT_DEFINITIONS
from app.api.v1.endpoints.storyblok_webhook import unpack_storyblok_event
from app.schemas.knowledge_ops import StoryblokConnectionView


def test_redaction_removes_common_pii_and_secrets() -> None:
    text = "Email Pat@example.com, call +1 (312) 555-0199, token=top-secret, SSN 123-45-6789"
    redacted, count = redact_text(text)
    assert count == 4
    assert "Pat@example.com" not in redacted
    assert "555-0199" not in redacted
    assert "top-secret" not in redacted
    assert "123-45-6789" not in redacted
    for marker in ("[EMAIL]", "[PHONE]", "[SECRET]", "[GOVERNMENT_ID]"):
        assert marker in redacted


def test_webhook_signature_accepts_only_exact_hmac_sha1() -> None:
    body = b'{"action":"story.published","story":{"uuid":"abc"}}'
    secret = "sandbox-webhook-secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    assert verify_webhook_signature(body, signature, secret)
    assert verify_webhook_signature(body, f"sha1={signature}", secret)
    assert not verify_webhook_signature(body + b" ", signature, secret)
    assert not verify_webhook_signature(body, "0" * 40, secret)


def test_webhook_contract_accepts_documented_envelope_and_direct_payload() -> None:
    payload, trigger = unpack_storyblok_event([{
        "trigger": "story.published",
        "payload": {"action": "published", "space_id": 42, "story_id": 7, "full_slug": "help/reset"},
    }])
    assert trigger == "story.published"
    assert payload["full_slug"] == "help/reset"
    direct, direct_trigger = unpack_storyblok_event(
        {"action": "unpublished", "space_id": 42, "story_id": 7, "full_slug": "help/reset"}
    )
    assert direct_trigger == "story.unpublished"
    assert direct["story_id"] == 7


def test_storyblok_schema_has_every_canonical_root_and_reusable_block() -> None:
    definitions = {str(item["name"]): item for item in COMPONENT_DEFINITIONS}
    assert {
        "sh_faq", "sh_documentation", "sh_troubleshooting", "sh_policy",
        "sh_known_issue", "sh_product", "sh_release_note",
    } <= definitions.keys()
    assert {
        "sh_evidence", "sh_step", "sh_applicability", "sh_related_content", "sh_channel_variant",
    } <= definitions.keys()
    for name, definition in definitions.items():
        if definition["is_root"]:
            schema = definition["schema"]
            assert schema["title"]["translatable"] is True
            assert schema["body"]["translatable"] is True
            assert schema["source_proposal_id"]["required"] is True
            assert schema["evidence"]["component_whitelist"] == ["sh_evidence"]


def test_field_level_i18n_uses_storyblok_management_representation() -> None:
    content = {"component": "sh_faq", "title": "Reset password", "source_proposal_id": "p-1"}
    translated = apply_storyblok_translations(
        content,
        {"es": {"title": "Restablecer contraseña", "source_proposal_id": "must-not-change"}},
        ["en", "es"],
    )
    assert translated["title"] == "Reset password"
    assert translated["title__i18n__es"] == "Restablecer contraseña"
    assert "source_proposal_id__i18n__es" not in translated


def test_connection_response_never_contains_credential_fragments() -> None:
    fields = set(StoryblokConnectionView.model_fields)
    assert {
        "draft_token_configured", "publisher_token_configured",
        "delivery_token_configured", "webhook_secret_configured",
    } <= fields
    assert not any("masked" in field for field in fields)


@pytest.mark.asyncio
async def test_storyblok_client_retries_429_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code
            self.text = "rate limited" if status_code == 429 else "ok"
            self.headers = {"retry-after": "0"}
            self.content = b"{}"
            self.is_error = status_code >= 400

        def json(self) -> dict[str, object]:
            return {"space": {"id": 1}}

    responses = [Response(429), Response(200)]

    class Client:
        def __init__(self, **_: object) -> None: pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_: object) -> None: return None
        async def request(self, *_: object, **__: object) -> Response: return responses.pop(0)

    async def no_sleep(_: float) -> None: return None
    monkeypatch.setattr("app.services.storyblok_client.httpx.AsyncClient", Client)
    monkeypatch.setattr("app.services.storyblok_client.asyncio.sleep", no_sleep)
    credentials = StoryblokCredentials(uuid4(), "eu", "1", "draft", "publisher", "delivery", "secret")
    assert (await StoryblokClient(credentials).get_space())["space"] == {"id": 1}
    assert responses == []


@pytest.mark.asyncio
async def test_storyblok_client_does_not_retry_authentication_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    class Response:
        status_code = 401
        text = "unauthorized"
        headers: dict[str, str] = {}
        content = b"{}"
        is_error = True
        def json(self) -> dict[str, object]: return {}
    class Client:
        def __init__(self, **_: object) -> None: pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_: object) -> None: return None
        async def request(self, *_: object, **__: object) -> Response:
            nonlocal calls
            calls += 1
            return Response()
    monkeypatch.setattr("app.services.storyblok_client.httpx.AsyncClient", Client)
    credentials = StoryblokCredentials(uuid4(), "eu", "1", "draft", "publisher", "delivery", "secret")
    with pytest.raises(StoryblokAPIError) as error:
        await StoryblokClient(credentials).get_space()
    assert error.value.status_code == 401
    assert calls == 1
