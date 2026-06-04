from __future__ import annotations

from copy import deepcopy
from typing import Any


READ_ONLY_EXECUTION_POLICY_VERSION = "metis_read_only_execution_policy.v0.1"


READ_ONLY_EXECUTION_POLICY: dict[str, Any] = {
    "schema_version": READ_ONLY_EXECUTION_POLICY_VERSION,
    "phase": "0Q",
    "status": "active_contract_with_scoped_read_only_receipts",
    "execution_enabled": False,
    "execution_enabled_meaning": "Arbitrary or autonomous execution is disabled; only scoped approved read-only receipt lanes listed here may run after proposal review.",
    "scoped_read_only_receipts_enabled": True,
    "active_approved_read_only_lanes": ["time.now", "filesystem.read", "git.status"],
    "contract_path": "docs/READ_ONLY_EXECUTION_POLICY_v0_1.md",
    "candidate_lanes": [
        {
            "lane": "time.now",
            "status": "active_approved_read_only",
            "minimum_gate": "side_effect_class=none, reviewed proposal, no shell, no network, no filesystem, receipt required",
        },
        {
            "lane": "filesystem.read",
            "status": "active_approved_read_only",
            "minimum_gate": "current repo allowlist, text extension allowlist, 32KB size limit, redacted/truncated preview, explicit operator approval",
        },
        {
            "lane": "git.status",
            "status": "active_approved_read_only",
            "minimum_gate": "current repo allowlist, fixed no-shell arguments, output truncation, no mutation commands",
        },
        {
            "lane": "fetch.url",
            "status": "future_only",
            "minimum_gate": "domain allowlist, timeout, size limit, content-type filter, no credential forwarding",
        },
        {
            "lane": "boh.retrieve",
            "status": "existing_read_only_bridge",
            "minimum_gate": "retrieval token only, never operator token, no mutation, no corpus copy",
        },
    ],
    "required_gates": [
        "proposal_id",
        "review_status=approved",
        "approved_read_only_or_stricter_permission_mode",
        "side_effect_class_none_or_read_only",
        "lane_policy_match",
        "pre_result_execution_receipt",
        "redaction_before_state_log_dashboard_artifact",
    ],
    "redaction_requirements": [
        "raw_secrets",
        "full_file_contents",
        "full_command_output",
        "raw_external_http_bodies",
        "raw_boh_corpus_chunks_beyond_contract",
        "concrete_temp_audio_paths",
    ],
    "receipt_required_fields": [
        "receipt_id",
        "proposal_id",
        "tool_id",
        "policy_decision",
        "execution_allowed",
        "execution_status",
        "side_effect_class",
        "risk_class",
        "created_at",
        "redactions",
        "operator_review_required",
        "output_hash",
        "output_summary",
    ],
    "phase_boundary": "Arbitrary execution remains disabled. Scoped approved read-only lanes may return bounded audit receipts only after proposal review and lane gates.",
}


def read_only_execution_policy() -> dict[str, Any]:
    return deepcopy(READ_ONLY_EXECUTION_POLICY)
