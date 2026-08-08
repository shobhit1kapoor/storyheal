"""Deterministic StoryHeal component definitions installed into Storyblok."""

from __future__ import annotations

from typing import Final


def field(field_type: str, position: int, *, required: bool = False, translatable: bool = False, **extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "type": field_type,
        "pos": position,
        "required": required,
        "translatable": translatable,
    }
    value.update(extra)
    return value


COMMON_ROOT_FIELDS: Final[dict[str, dict[str, object]]] = {
    "title": field("text", 0, required=True, translatable=True),
    "summary": field("textarea", 1, required=True, translatable=True),
    "body": field("richtext", 2, required=True, translatable=True),
    "category": field("text", 3),
    "tags": field("options", 4, source="self"),
    "product": field("text", 5),
    "versions": field("textarea", 6),
    "effective_from": field("datetime", 7),
    "review_at": field("datetime", 8),
    "channels": field(
        "options",
        9,
        source="self",
        options=[
            {"name": "Help center", "value": "web"},
            {"name": "AI assistant", "value": "assistant"},
            {"name": "Support agent", "value": "support"},
            {"name": "Widget", "value": "widget"},
        ],
    ),
    "evidence": field("bloks", 10, restrict_components=True, component_whitelist=["sh_evidence"]),
    "channel_variants": field(
        "bloks", 11, restrict_components=True, component_whitelist=["sh_channel_variant"]
    ),
    "applicability": field(
        "bloks", 12, restrict_components=True, component_whitelist=["sh_applicability"]
    ),
    "related_content": field(
        "bloks", 13, restrict_components=True, component_whitelist=["sh_related_content"]
    ),
    "source_proposal_id": field("text", 14, required=True),
    "content_health": field("number", 15),
}


COMPONENT_DEFINITIONS: Final[list[dict[str, object]]] = [
    {
        "name": "sh_evidence",
        "display_name": "Evidence citation",
        "is_root": False,
        "is_nestable": True,
        "schema": {
            "source_type": field("option", 0, required=True, source="self", options=[
                {"name": "Conversation", "value": "conversation"},
                {"name": "Published Storyblok entry", "value": "storyblok"},
                {"name": "External URL", "value": "url"},
            ]),
            "title": field("text", 1, required=True, translatable=True),
            "uri": field("text", 2),
            "excerpt": field("textarea", 3, translatable=True),
            "observed_at": field("datetime", 4),
            "checksum": field("text", 5, required=True),
        },
    },
    {
        "name": "sh_step",
        "display_name": "Procedure step",
        "is_root": False,
        "is_nestable": True,
        "schema": {
            "title": field("text", 0, required=True, translatable=True),
            "instruction": field("richtext", 1, required=True, translatable=True),
            "expected_result": field("textarea", 2, translatable=True),
        },
    },
    {
        "name": "sh_channel_variant",
        "display_name": "Channel-specific answer",
        "is_root": False,
        "is_nestable": True,
        "schema": {
            "channel": field("option", 0, required=True, source="self", options=[
                {"name": "Help center", "value": "web"},
                {"name": "AI assistant", "value": "assistant"},
                {"name": "Support agent", "value": "support"},
                {"name": "Widget", "value": "widget"},
            ]),
            "headline": field("text", 1, translatable=True),
            "answer": field("richtext", 2, required=True, translatable=True),
        },
    },
    {
        "name": "sh_applicability",
        "display_name": "Product applicability",
        "is_root": False,
        "is_nestable": True,
        "schema": {
            "product": field("text", 0, required=True),
            "versions": field("textarea", 1),
            "audience": field("text", 2, translatable=True),
            "platform": field("text", 3),
        },
    },
    {
        "name": "sh_related_content",
        "display_name": "Related content",
        "is_root": False,
        "is_nestable": True,
        "schema": {
            "story": field("multilink", 0, required=True),
            "relationship": field("text", 1, translatable=True),
            "display_title": field("text", 2, translatable=True),
        },
    },
    {
        "name": "sh_faq",
        "display_name": "FAQ",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "question": field("text", 20, required=True, translatable=True),
            "short_answer": field("textarea", 21, required=True, translatable=True),
            "related_questions": field("textarea", 22, translatable=True),
        },
    },
    {
        "name": "sh_documentation",
        "display_name": "Documentation page",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "prerequisites": field("richtext", 20, translatable=True),
            "steps": field("bloks", 21, restrict_components=True, component_whitelist=["sh_step"]),
        },
    },
    {
        "name": "sh_troubleshooting",
        "display_name": "Troubleshooting guide",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "problem": field("textarea", 20, required=True, translatable=True),
            "symptoms": field("richtext", 21, translatable=True),
            "diagnosis": field("richtext", 22, translatable=True),
            "resolution_steps": field("bloks", 23, restrict_components=True, component_whitelist=["sh_step"]),
            "escalation": field("richtext", 24, translatable=True),
        },
    },
    {
        "name": "sh_policy",
        "display_name": "Policy",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "scope": field("textarea", 20, required=True, translatable=True),
            "policy_owner": field("text", 21),
            "expires_at": field("datetime", 22),
        },
    },
    {
        "name": "sh_known_issue",
        "display_name": "Known issue",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "issue_status": field("option", 20, required=True, source="self", options=[
                {"name": "Investigating", "value": "investigating"},
                {"name": "Workaround", "value": "workaround"},
                {"name": "Resolved", "value": "resolved"},
            ]),
            "symptoms": field("richtext", 21, required=True, translatable=True),
            "workaround": field("richtext", 22, translatable=True),
            "resolution": field("richtext", 23, translatable=True),
        },
    },
    {
        "name": "sh_product",
        "display_name": "Product information",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "features": field("richtext", 20, translatable=True),
            "requirements": field("richtext", 21, translatable=True),
            "limitations": field("richtext", 22, translatable=True),
        },
    },
    {
        "name": "sh_release_note",
        "display_name": "Release note",
        "is_root": True,
        "is_nestable": False,
        "schema": {
            **COMMON_ROOT_FIELDS,
            "version": field("text", 20, required=True),
            "released_at": field("datetime", 21, required=True),
            "changes": field("richtext", 22, required=True, translatable=True),
            "breaking_changes": field("richtext", 23, translatable=True),
        },
    },
]
