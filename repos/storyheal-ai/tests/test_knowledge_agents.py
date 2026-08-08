import pytest
from pydantic import ValidationError

from app.api.v1.knowledge_agents import FindingOutput, StoryblokDraftContent, _clean_json


def test_clean_json_accepts_fenced_object() -> None:
    assert _clean_json('```json\n{"detected": false}\n```') == {"detected": False}


def test_finding_requires_explicit_detection_decision() -> None:
    with pytest.raises(ValidationError):
        FindingOutput.model_validate(
            {
                "kind": "gap",
                "title": "Missing reset instructions",
                "summary": "Users cannot find reset instructions.",
                "representative_question": "How do I reset it?",
                "severity": "medium",
                "confidence": 0.9,
                "occurrence_count": 2,
            }
        )


def test_draft_rejects_non_storyheal_root_component() -> None:
    with pytest.raises(ValidationError):
        StoryblokDraftContent.model_validate(
            {
                "component": "generic_page",
                "title": "Reset instructions",
                "summary": "How to reset the product.",
                "body": {"type": "doc", "content": []},
                "channels": ["web"],
                "evidence": [{"id": "ev-1"}],
                "source_proposal_id": "proposal-1",
            }
        )
