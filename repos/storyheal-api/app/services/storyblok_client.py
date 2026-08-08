"""Production Storyblok Management and Content Delivery API client."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.metrics import STORYBLOK_OPERATIONS, STORYBLOK_OPERATION_DURATION
from app.models import StoryblokOperation
from app.services.storyblok_components import COMPONENT_DEFINITIONS

logger = get_logger("services.storyblok")


MANAGEMENT_BASES: dict[str, str] = {
    "eu": "https://mapi.storyblok.com/v1",
    "us": "https://api-us.storyblok.com/v1",
    "ca": "https://api-ca.storyblok.com/v1",
    "ap": "https://api-ap.storyblok.com/v1",
    "cn": "https://app.storyblokchina.cn/v1",
}

DELIVERY_BASES: dict[str, str] = {
    "eu": "https://api.storyblok.com/v2/cdn",
    "us": "https://api-us.storyblok.com/v2/cdn",
    "ca": "https://api-ca.storyblok.com/v2/cdn",
    "ap": "https://api-ap.storyblok.com/v2/cdn",
    "cn": "https://app.storyblokchina.cn/v2/cdn",
}


@dataclass(frozen=True)
class StoryblokCredentials:
    project_id: UUID
    region: str
    space_id: str
    draft_token: str
    publisher_token: str
    delivery_token: str
    webhook_secret: str


class StoryblokAPIError(RuntimeError):
    def __init__(self, operation: str, status_code: int, detail: str) -> None:
        super().__init__(f"Storyblok {operation} failed ({status_code}): {detail}")
        self.operation = operation
        self.status_code = status_code
        self.detail = detail


class StoryblokClient:
    def __init__(
        self,
        credentials: StoryblokCredentials,
        *,
        db: Optional[Session] = None,
        proposal_id: Optional[UUID] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if credentials.region not in MANAGEMENT_BASES:
            raise ValueError(f"Unsupported Storyblok region: {credentials.region}")
        self.credentials = credentials
        self.db = db
        self.proposal_id = proposal_id
        self.timeout_seconds = timeout_seconds

    async def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        token: str,
        json_body: Optional[dict[str, object]] = None,
        params: Optional[dict[str, object]] = None,
        delivery: bool = False,
        max_attempts: int = 4,
    ) -> dict[str, object]:
        base = DELIVERY_BASES[self.credentials.region] if delivery else MANAGEMENT_BASES[self.credentials.region]
        headers = {"Accept": "application/json"}
        if not delivery:
            headers["Authorization"] = token
            headers["Content-Type"] = "application/json"
        request_params = dict(params or {})
        if delivery:
            request_params["token"] = token

        last_error: Optional[str] = None
        for attempt in range(1, max_attempts + 1):
            started = time.perf_counter()
            status_code: Optional[int] = None
            try:
                # Storyblok's Delivery API currently canonicalizes some CDN
                # endpoints with a redirect. Follow it so sync/indexing always
                # parses the published CDA payload rather than an empty 301.
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    follow_redirects=delivery,
                ) as client:
                    response = await client.request(
                        method,
                        f"{base}/{path.lstrip('/')}",
                        headers=headers,
                        params=request_params,
                        json=json_body,
                    )
                status_code = response.status_code
                duration_ms = int((time.perf_counter() - started) * 1000)
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = response.text[:1000]
                    self._record(operation, method, status_code, False, duration_ms, attempt, last_error)
                    if attempt < max_attempts:
                        retry_after = response.headers.get("retry-after")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** (attempt - 1), 8)
                        await asyncio.sleep(delay)
                        continue
                if response.is_error:
                    self._record(operation, method, status_code, False, duration_ms, attempt, response.text[:1000])
                    raise StoryblokAPIError(operation, response.status_code, response.text[:1000])
                self._record(operation, method, status_code, True, duration_ms, attempt, None)
                if not response.content:
                    return {}
                data = response.json()
                if not isinstance(data, dict):
                    raise StoryblokAPIError(operation, response.status_code, "Expected a JSON object")
                return data
            except httpx.RequestError as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                last_error = str(exc)
                self._record(operation, method, status_code, False, duration_ms, attempt, last_error)
                if attempt < max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 8))
                    continue
                raise StoryblokAPIError(operation, status_code or 503, last_error) from exc

        raise StoryblokAPIError(operation, 503, last_error or "Request exhausted retries")

    def _record(
        self,
        operation: str,
        method: str,
        status_code: Optional[int],
        success: bool,
        duration_ms: int,
        attempt: int,
        error: Optional[str],
    ) -> None:
        STORYBLOK_OPERATIONS.labels(
            operation=operation,
            result="success" if success else "failure",
            status_code=str(status_code or 0),
        ).inc()
        STORYBLOK_OPERATION_DURATION.labels(operation=operation).observe(duration_ms / 1000)
        if self.db is None:
            return
        self.db.add(
            StoryblokOperation(
                project_id=self.credentials.project_id,
                proposal_id=self.proposal_id,
                operation=operation,
                method=method,
                status_code=status_code,
                success=success,
                duration_ms=duration_ms,
                attempt=attempt,
                error=error,
            )
        )

    async def get_space(self, *, publisher: bool = False) -> dict[str, object]:
        token = self.credentials.publisher_token if publisher else self.credentials.draft_token
        return await self._request(
            "GET", f"spaces/{self.credentials.space_id}", operation="space.read", token=token
        )

    async def get_published_story(self, identifier: str, locale: str = "en") -> dict[str, object]:
        return await self._request(
            "GET",
            f"stories/{identifier}",
            operation="delivery.story.read",
            token=self.credentials.delivery_token,
            params={"version": "published", "language": locale, "cv": int(time.time())},
            delivery=True,
        )

    async def list_published_stories(self, starts_with: str, locale: str = "en") -> dict[str, object]:
        return await self._request(
            "GET",
            "stories",
            operation="delivery.stories.list",
            token=self.credentials.delivery_token,
            params={
                "version": "published",
                "language": locale,
                "fallback_lang": "en",
                "starts_with": starts_with.rstrip("/") + "/",
                "per_page": 100,
                "cv": int(time.time()),
            },
            delivery=True,
        )

    async def get_management_story(self, story_id: str, *, publisher: bool = False) -> dict[str, object]:
        token = self.credentials.publisher_token if publisher else self.credentials.draft_token
        return await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/stories/{story_id}",
            operation="story.read",
            token=token,
        )

    async def find_management_story(self, full_slug: str, parent_id: int) -> Optional[dict[str, object]]:
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/stories",
            operation="story.find",
            token=self.credentials.draft_token,
            params={"with_slug": full_slug, "story_only": True},
        )
        stories = data.get("stories", [])
        if isinstance(stories, list):
            for story in stories:
                if not isinstance(story, dict):
                    continue
                if story.get("full_slug") == full_slug or (
                    story.get("slug") == full_slug.rsplit("/", 1)[-1]
                    and int(story.get("parent_id") or 0) == parent_id
                ):
                    return story
        return None

    async def create_draft(
        self,
        *,
        name: str,
        slug: str,
        content: dict[str, object],
        parent_id: int,
    ) -> dict[str, object]:
        return await self._request(
            "POST",
            f"spaces/{self.credentials.space_id}/stories",
            operation="story.draft.create",
            token=self.credentials.draft_token,
            json_body={
                "publish": False,
                "story": {"name": name, "slug": slug, "parent_id": parent_id, "content": content},
            },
        )

    async def move_to_stage(self, story_id: str, workflow_stage_id: int, *, publisher: bool = False) -> dict[str, object]:
        token = self.credentials.publisher_token if publisher else self.credentials.draft_token
        return await self._request(
            "POST",
            f"spaces/{self.credentials.space_id}/workflow_stage_changes/",
            operation="workflow.stage.change",
            token=token,
            json_body={"workflow_stage_change": {"story_id": int(story_id), "workflow_stage_id": workflow_stage_id}},
        )

    async def update_draft(self, story_id: str, story: dict[str, object]) -> dict[str, object]:
        return await self._request(
            "PUT",
            f"spaces/{self.credentials.space_id}/stories/{story_id}",
            operation="story.draft.update",
            token=self.credentials.draft_token,
            json_body={"publish": False, "story": story},
        )

    async def publish_story(self, story_id: str, story: dict[str, object]) -> dict[str, object]:
        return await self._request(
            "PUT",
            f"spaces/{self.credentials.space_id}/stories/{story_id}",
            operation="story.publish",
            token=self.credentials.publisher_token,
            json_body={"publish": True, "story": story},
        )

    async def provision(
        self,
        *,
        folder_slug: str,
        public_webhook_url: str,
        webhook_secret: str,
    ) -> tuple[str, dict[str, int], dict[str, int], Optional[int]]:
        group_id = await self._ensure_component_group()
        component_ids = await self._ensure_components(group_id)
        folder_id = await self._ensure_story_folder(folder_slug)
        workflow_stage_ids = await self._ensure_workflow_stage_ids()
        webhook_id = await self._ensure_webhook(public_webhook_url, webhook_secret)
        return folder_id, component_ids, workflow_stage_ids, webhook_id

    async def _ensure_component_group(self) -> str:
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/component_groups/",
            operation="component_group.list",
            token=self.credentials.draft_token,
        )
        groups = data.get("component_groups", [])
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict) and group.get("name") == "StoryHeal Knowledge":
                    return str(group.get("uuid") or group.get("id"))
        created = await self._request(
            "POST",
            f"spaces/{self.credentials.space_id}/component_groups/",
            operation="component_group.create",
            token=self.credentials.draft_token,
            json_body={"component_group": {"name": "StoryHeal Knowledge"}},
        )
        group = created.get("component_group", {})
        if not isinstance(group, dict):
            raise StoryblokAPIError("component_group.create", 500, "Missing component_group response")
        return str(group.get("uuid") or group.get("id"))

    async def _ensure_components(self, group_id: str) -> dict[str, int]:
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/components",
            operation="component.list",
            token=self.credentials.draft_token,
        )
        existing_raw = data.get("components", [])
        existing: dict[str, dict[str, object]] = {}
        if isinstance(existing_raw, list):
            existing = {
                str(item.get("name")): item
                for item in existing_raw
                if isinstance(item, dict) and item.get("name")
            }

        component_ids: dict[str, int] = {}
        for definition in COMPONENT_DEFINITIONS:
            name = str(definition["name"])
            payload = {**definition, "component_group_id": group_id}
            current = existing.get(name)
            if current and current.get("id"):
                component_id = int(current["id"])
                await self._request(
                    "PUT",
                    f"spaces/{self.credentials.space_id}/components/{component_id}",
                    operation="component.update",
                    token=self.credentials.draft_token,
                    json_body={"component": payload},
                )
            else:
                created = await self._request(
                    "POST",
                    f"spaces/{self.credentials.space_id}/components/",
                    operation="component.create",
                    token=self.credentials.draft_token,
                    json_body={"component": payload},
                )
                component = created.get("component", {})
                if not isinstance(component, dict) or not component.get("id"):
                    raise StoryblokAPIError("component.create", 500, f"Missing component id for {name}")
                component_id = int(component["id"])
            component_ids[name] = component_id
        return component_ids

    async def _ensure_story_folder(self, folder_slug: str) -> str:
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/stories",
            operation="story.folder.find",
            token=self.credentials.draft_token,
            # `with_slug` does not return folders in the Management API. Query
            # root folders explicitly so a retry cannot attempt a duplicate slug.
            params={"folder_only": True, "in_folder": 0, "per_page": 100},
        )
        stories = data.get("stories", [])
        if isinstance(stories, list):
            for story in stories:
                if isinstance(story, dict) and story.get("slug") == folder_slug and story.get("is_folder"):
                    return str(story["id"])
        created = await self._request(
            "POST",
            f"spaces/{self.credentials.space_id}/stories",
            operation="story.folder.create",
            token=self.credentials.draft_token,
            json_body={
                "publish": False,
                "story": {"name": "StoryHeal Knowledge", "slug": folder_slug, "parent_id": 0, "is_folder": True},
            },
        )
        story = created.get("story", {})
        if not isinstance(story, dict) or not story.get("id"):
            raise StoryblokAPIError("story.folder.create", 500, "Missing folder story id")
        return str(story["id"])

    async def _ensure_workflow(self) -> int:
        content_types = [
            str(item["name"]) for item in COMPONENT_DEFINITIONS if item.get("is_root") is True
        ]
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/workflows",
            operation="workflow.list",
            token=self.credentials.publisher_token,
        )
        workflows = data.get("workflows", [])
        if isinstance(workflows, list):
            for workflow in workflows:
                if isinstance(workflow, dict) and workflow.get("name") == "StoryHeal Knowledge":
                    workflow_id = int(workflow["id"])
                    await self._request(
                        "PUT",
                        f"spaces/{self.credentials.space_id}/workflows/{workflow_id}",
                        operation="workflow.update",
                        token=self.credentials.publisher_token,
                        json_body={
                            "workflow": {
                                "name": "StoryHeal Knowledge",
                                "content_types": content_types,
                            }
                        },
                    )
                    return workflow_id
            # Storyblok trial spaces include one native workflow but may not allow
            # creating or updating a custom workflow. Reuse that canonical workflow;
            # StoryHeal still creates/verifies the mandatory three editorial stages
            # below. This keeps repeated provisioning idempotent on paid and trial
            # spaces while retaining Storyblok-native approval state.
            for workflow in workflows:
                if isinstance(workflow, dict) and workflow.get("id"):
                    return int(workflow["id"])
        created = await self._request(
            "POST",
            f"spaces/{self.credentials.space_id}/workflows",
            operation="workflow.create",
            token=self.credentials.publisher_token,
            json_body={"workflow": {"name": "StoryHeal Knowledge", "content_types": content_types}},
        )
        workflow = created.get("workflow", {})
        if not isinstance(workflow, dict) or not workflow.get("id"):
            raise StoryblokAPIError("workflow.create", 500, "Missing workflow id")
        return int(workflow["id"])

    async def _ensure_workflow_stage_ids(self) -> dict[str, int]:
        workflow_id = await self._ensure_workflow()
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/workflow_stages/",
            operation="workflow.stage.list",
            token=self.credentials.publisher_token,
        )
        raw_stages = data.get("workflow_stages", [])
        result: dict[str, int] = {}
        aliases = {
            "drafting": "drafting",
            "reviewing": "reviewing",
            "ready to publish": "ready_to_publish",
        }
        if isinstance(raw_stages, list):
            for stage in raw_stages:
                if isinstance(stage, dict):
                    if stage.get("workflow_id") not in (None, workflow_id):
                        continue
                    name = str(stage.get("name", "")).strip().lower()
                    if name in aliases and stage.get("id"):
                        result[aliases[name]] = int(stage["id"])

        definitions = (
            ("drafting", "Drafting", "#64748b", 1, True, False),
            ("reviewing", "Reviewing", "#f59e0b", 2, False, False),
            ("ready_to_publish", "Ready to Publish", "#10b981", 3, False, True),
        )
        for alias, name, color, position, is_default, can_publish in definitions:
            if alias in result:
                continue
            created = await self._request(
                "POST",
                f"spaces/{self.credentials.space_id}/workflow_stages",
                operation="workflow.stage.create",
                token=self.credentials.publisher_token,
                json_body={
                    "workflow_stage": {
                        "name": name,
                        "color": color,
                        "position": position,
                        "workflow_id": workflow_id,
                        "is_default": is_default,
                        "allow_admin_change": True,
                        "allow_editor_change": True,
                        "allow_all_users": not can_publish,
                        "allow_all_stages": False,
                        "allow_publish": False,
                        "allow_admin_publish": can_publish,
                        "space_role_ids": [],
                        "user_ids": [],
                        "workflow_stage_ids": [],
                    }
                },
            )
            stage = created.get("workflow_stage", {})
            if not isinstance(stage, dict) or not stage.get("id"):
                raise StoryblokAPIError("workflow.stage.create", 500, f"Missing stage id for {name}")
            result[alias] = int(stage["id"])
        return result

    async def _ensure_webhook(self, url: str, secret: str) -> Optional[int]:
        data = await self._request(
            "GET",
            f"spaces/{self.credentials.space_id}/webhook_endpoints/",
            operation="webhook.list",
            token=self.credentials.publisher_token,
        )
        webhooks = data.get("webhook_endpoints", [])
        if isinstance(webhooks, list):
            for webhook in webhooks:
                if isinstance(webhook, dict) and (
                    webhook.get("endpoint") == url
                    or webhook.get("name") == "StoryHeal RAG refresh"
                ):
                    webhook_id = int(webhook["id"])
                    await self._request(
                        "PUT",
                        f"spaces/{self.credentials.space_id}/webhook_endpoints/{webhook_id}",
                        operation="webhook.update",
                        token=self.credentials.publisher_token,
                        json_body={
                            "webhook_endpoint": {
                                "name": "StoryHeal RAG refresh",
                                "endpoint": url,
                                "actions": ["story.published", "story.unpublished", "story.deleted"],
                                "secret": secret,
                                "activated": True,
                            }
                        },
                    )
                    return webhook_id
        created = await self._request(
            "POST",
            f"spaces/{self.credentials.space_id}/webhook_endpoints/",
            operation="webhook.create",
            token=self.credentials.publisher_token,
            json_body={
                "webhook_endpoint": {
                    "name": "StoryHeal RAG refresh",
                    "endpoint": url,
                    "actions": ["story.published", "story.unpublished", "story.deleted"],
                    "secret": secret,
                    "activated": True,
                }
            },
        )
        webhook = created.get("webhook_endpoint", {})
        return int(webhook["id"]) if isinstance(webhook, dict) and webhook.get("id") else None


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha1).hexdigest()
    candidate = signature.removeprefix("sha1=")
    return hmac.compare_digest(expected, candidate)
