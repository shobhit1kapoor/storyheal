"""Environment-gated contract test for an authorized Storyblok hackathon space."""

import os
from uuid import UUID

import pytest

from app.services.storyblok_client import StoryblokClient, StoryblokCredentials


pytestmark = pytest.mark.skipif(
    os.getenv("STORYHEAL_LIVE_STORYBLOK") != "1",
    reason="Set STORYHEAL_LIVE_STORYBLOK=1 for the authorized sandbox",
)


def credentials() -> StoryblokCredentials:
    return StoryblokCredentials(
        project_id=UUID(os.environ["STORYHEAL_LIVE_PROJECT_ID"]),
        region=os.getenv("STORYHEAL_LIVE_REGION", "eu"),
        space_id=os.environ["STORYHEAL_LIVE_SPACE_ID"],
        draft_token=os.environ["STORYHEAL_LIVE_DRAFT_TOKEN"],
        publisher_token=os.environ["STORYHEAL_LIVE_PUBLISHER_TOKEN"],
        delivery_token=os.environ["STORYHEAL_LIVE_DELIVERY_TOKEN"],
        webhook_secret=os.environ["STORYHEAL_LIVE_WEBHOOK_SECRET"],
    )


@pytest.mark.asyncio
async def test_live_tokens_and_cda_are_reachable() -> None:
    client = StoryblokClient(credentials())
    assert (await client.get_space()).get("space")
    assert (await client.get_space(publisher=True)).get("space")
    result = await client.list_published_stories(os.getenv("STORYHEAL_LIVE_FOLDER", "knowledge"), "en")
    assert isinstance(result.get("stories", []), list)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("STORYHEAL_LIVE_MUTATE") != "1",
    reason="Set STORYHEAL_LIVE_MUTATE=1 to provision the authorized sandbox",
)
async def test_live_idempotent_provisioning() -> None:
    client = StoryblokClient(credentials())
    first = await client.provision(
        folder_slug=os.getenv("STORYHEAL_LIVE_FOLDER", "knowledge"),
        public_webhook_url=os.environ["STORYHEAL_LIVE_WEBHOOK_URL"],
        webhook_secret=os.environ["STORYHEAL_LIVE_WEBHOOK_SECRET"],
    )
    second = await client.provision(
        folder_slug=os.getenv("STORYHEAL_LIVE_FOLDER", "knowledge"),
        public_webhook_url=os.environ["STORYHEAL_LIVE_WEBHOOK_URL"],
        webhook_secret=os.environ["STORYHEAL_LIVE_WEBHOOK_SECRET"],
    )
    assert first == second

