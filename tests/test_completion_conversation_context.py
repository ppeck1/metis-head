from datetime import UTC, datetime

from metis_head.conversation_context import TrustedConversationContext, assemble_conversation_context


def test_authoritative_context_contains_trusted_selection_time_and_untrusted_evidence() -> None:
    context = assemble_conversation_context(
        state={"interaction_mode": "human", "conversation_depth_bucket": "rationale", "initiative_bucket": "helpful", "source_grounding_enabled": True},
        history=({"role": "user", "content": "What is tomorrow?"},),
        trusted=TrustedConversationContext(
            now=datetime(2026, 9, 16, 13, tzinfo=UTC),
            timezone_name="America/New_York",
            selected_account_id="personal@example.test",
            selected_calendar_ids=("primary",),
            selected_project_id="metis-project",
            available_accounts=("personal@example.test", "work@example.test"),
            allowed_tools=("google.calendar.list", "atlas.project.status"),
        ),
        retrieval_context="BOH-SENTINEL-EVIDENCE",
    )

    assert "2026-09-16" in context.system_instructions
    assert "America/New_York" in context.system_instructions
    assert "personal@example.test" in context.system_instructions
    assert "primary" in context.system_instructions
    assert "metis-project" in context.system_instructions
    assert context.evidence_supplied is True
    assert "BOH-SENTINEL-EVIDENCE" in context.conversation[0]["content"]
    assert "untrusted" in context.conversation[0]["content"].lower()
