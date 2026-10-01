"""Audit logging for every policy decision.

Every eligibility check — pass or fail — is recorded here.
This is critical for debugging and dispute resolution.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .policy_models import EligibilityResult, PolicyAuditEntry, PolicyAction

logger = logging.getLogger(__name__)


def log_policy_decision(
    *,
    request_id: str,
    user_id: str | None,
    app_id: str,
    order_id: str | None,
    order_item_id: str | None,
    action: PolicyAction,
    result: EligibilityResult,
) -> None:
    """Record a structured audit entry for a policy eligibility decision."""
    entry = PolicyAuditEntry(
        request_id=request_id,
        user_id=user_id,
        app_id=app_id,
        order_id=order_id,
        order_item_id=order_item_id,
        action=action,
        policy_id=result.policy_id,
        policy_version=result.policy_version,
        eligible=result.eligible,
        reason_code=result.reason_code,
        checked_at=datetime.now(timezone.utc),
        deadline=result.deadline,
        checks=result.checks.model_dump(),
    )
    logger.info(
        "[POLICY_AUDIT] %s",
        json.dumps(entry.model_dump(mode="json"), default=str),
    )
