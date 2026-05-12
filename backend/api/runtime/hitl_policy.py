from __future__ import annotations

from typing import Any

HITL_MESSAGE = "HITL이 실행되었습니다. 계속 진행하시겠습니까?"
RESERVED_CREW_INPUTS = {"human_feedback"}
VALID_HITL_OUTCOMES = {"approved", "needs_revision", "rejected"}


def normalize_hitl_contract(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"HITL node {node_id} data must be an object.")

    raw_max_attempts = data.get("maxAttempts", 3)
    if isinstance(raw_max_attempts, bool) or not isinstance(raw_max_attempts, int) or raw_max_attempts < 1:
        raise ValueError(f"HITL node {node_id} maxAttempts must be a positive integer.")

    return {"maxAttempts": raw_max_attempts}


def retry_budget_metadata(*, attempt_number: int, max_attempts: int) -> dict[str, int]:
    retry_count = max(attempt_number - 1, 0)
    remaining_retries = max(max_attempts - retry_count, 0)
    return {
        "attempt_number": attempt_number,
        "retry_count": retry_count,
        "max_attempts": max_attempts,
        "remaining_retries": remaining_retries,
    }


def should_inject_human_feedback(*, policy: str, outcome: str) -> bool:
    if policy == "none":
        return False
    if policy == "needs_revision_only":
        return outcome == "needs_revision"
    if policy == "approved_and_needs_revision":
        return outcome in {"approved", "needs_revision"}
    if policy == "all_decisions":
        return True
    return False
