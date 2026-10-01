"""Deterministic policy engine — the FINAL authority on action eligibility.

The LLM MUST NOT override, extend, or bypass the result of this engine.
No randomness, no AI inference — pure rule evaluation in a defined order.

Evaluation order (per spec):
 1. Policy exists
 2. Policy enabled
 3. User authenticated
 4. Order status allowed
 5. Product / category exclusions
 6. Date/time window
 7. (Duplicate / previous request check is deferred to action API — second gate)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .policy_models import (
    ActionPolicy,
    EligibilityChecks,
    EligibilityResult,
    PolicyAction,
    PolicyResolution,
)

logger = logging.getLogger(__name__)

# Human-readable labels for window basis fields
_BASIS_LABELS: dict[str, str] = {
    "order_created_at": "order creation",
    "payment_date": "payment",
    "shipment_date": "shipment",
    "delivery_date": "delivery",
}

_ACTION_LABELS: dict[PolicyAction, str] = {
    "cancel": "cancellation",
    "return": "return",
    "refund": "refund",
    "replacement": "replacement",
}


def _get_date(order: dict[str, Any], field: str) -> datetime | None:
    """Extract and parse a date field from an order dict. Returns None if absent/invalid."""
    raw = order.get(field)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _no_policy_result(action: PolicyAction) -> EligibilityResult:
    label = _ACTION_LABELS.get(action, action)
    return EligibilityResult(
        eligible=False,
        action=action,
        policy_found=False,
        reason_code="NO_POLICY_CONFIGURED",
        message=(
            f"I don't have a configured policy for {label} requests, "
            f"so I can't process this {label}."
        ),
        checks=EligibilityChecks(policy_exists=False),
    )


def check_action_eligibility(
    *,
    action: PolicyAction,
    order: dict[str, Any],
    order_item: dict[str, Any] | None,
    resolution: PolicyResolution,
    authenticated: bool,
    current_datetime: datetime | None = None,
) -> EligibilityResult:
    """Evaluate whether an action is permitted.

    Args:
        action: The requested action (cancel / return / refund / replacement).
        order: Order dict from the API (must contain status, dates, item details).
        order_item: Order item dict (required for item-level actions).
        resolution: Result from policy_registry.resolve_policy().
        authenticated: Whether the user is authenticated.
        current_datetime: Override for testing; defaults to now(UTC).

    Returns:
        EligibilityResult — eligible=True only when ALL gates pass.
    """
    now = current_datetime or datetime.now(timezone.utc)
    checks = EligibilityChecks()
    label = _ACTION_LABELS.get(action, action)

    # ── Gate 1: Policy exists ────────────────────────────────────────────────
    if not resolution.policy_found or resolution.policy is None:
        return _no_policy_result(action)

    policy: ActionPolicy = resolution.policy
    checks.policy_exists = True

    # ── Gate 2: Policy enabled ───────────────────────────────────────────────
    if not policy.enabled:
        return EligibilityResult(
            eligible=False,
            action=action,
            policy_found=True,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            reason_code="POLICY_DISABLED",
            message=f"{label.capitalize()} requests are not currently accepted.",
            checks=checks,
        )
    checks.policy_enabled = True

    # ── Gate 3: Authentication ───────────────────────────────────────────────
    if not authenticated:
        return EligibilityResult(
            eligible=False,
            action=action,
            policy_found=True,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            reason_code="AUTHENTICATION_REQUIRED",
            message=f"You need to be signed in to submit a {label} request.",
            checks=checks,
        )
    checks.authenticated = True

    # ── Gate 4: Order status ─────────────────────────────────────────────────
    order_status = str(order.get("status", "")).lower()
    if policy.allowed_statuses:
        allowed_lower = [s.lower() for s in policy.allowed_statuses]
        if order_status not in allowed_lower:
            return EligibilityResult(
                eligible=False,
                action=action,
                policy_found=True,
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                reason_code="ORDER_STATUS_NOT_ALLOWED",
                message=(
                    f"I can't process this {label} because the order status "
                    f"is '{order_status}'. {label.capitalize()} is only allowed "
                    f"for orders with status: {', '.join(policy.allowed_statuses)}."
                ),
                checks=checks,
            )
    checks.status_allowed = True

    # ── Gate 5: Product / category exclusions ───────────────────────────────
    item = order_item or {}
    product_id = str(item.get("product_id") or item.get("slug") or "")
    category = str(item.get("category") or item.get("category_slug") or "")

    if product_id and policy.excluded_products and product_id in policy.excluded_products:
        return EligibilityResult(
            eligible=False,
            action=action,
            policy_found=True,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            reason_code="PRODUCT_EXCLUDED",
            message=f"This product is not eligible for {label}.",
            checks=checks,
        )
    if category and policy.excluded_categories and category in policy.excluded_categories:
        return EligibilityResult(
            eligible=False,
            action=action,
            policy_found=True,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            reason_code="CATEGORY_EXCLUDED",
            message=f"Products in the '{category}' category are not eligible for {label}.",
            checks=checks,
        )
    checks.product_eligible = True

    # ── Gate 6: Date/time window ─────────────────────────────────────────────
    if policy.window is not None:
        basis_field = policy.window.based_on
        basis_date = _get_date(order, basis_field)

        if basis_date is None:
            # If the required date is missing we cannot evaluate — fail closed
            logger.warning(
                "[POLICY] missing basis date action=%s field=%s order_id=%s",
                action,
                basis_field,
                order.get("id") or order.get("order_id"),
            )
            return EligibilityResult(
                eligible=False,
                action=action,
                policy_found=True,
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                reason_code="WINDOW_BASIS_DATE_MISSING",
                message=(
                    f"I couldn't verify the {label} window because the required "
                    f"date ({_BASIS_LABELS.get(basis_field, basis_field)}) is not available. "
                    "Please contact support."
                ),
                checks=checks,
            )

        from datetime import timedelta

        deadline = basis_date + timedelta(seconds=policy.window.duration_seconds())

        if now > deadline:
            return EligibilityResult(
                eligible=False,
                action=action,
                policy_found=True,
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                deadline=deadline,
                reason_code=f"{action.upper()}_WINDOW_EXPIRED",
                message=_expired_message(action, label, basis_field, basis_date, deadline),
                checks=checks,
                window_basis_date=basis_date,
                window_basis_field=basis_field,
            )

    checks.time_window = True

    # ── All gates passed ─────────────────────────────────────────────────────
    deadline = None
    if policy.window is not None and basis_date is not None:  # type: ignore[possibly-undefined]
        from datetime import timedelta
        deadline = basis_date + timedelta(seconds=policy.window.duration_seconds())

    return EligibilityResult(
        eligible=True,
        action=action,
        policy_found=True,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        deadline=deadline,
        reason_code=None,
        message=f"{label.capitalize()} is allowed.",
        checks=checks,
    )


def _expired_message(
    action: PolicyAction,
    label: str,
    basis_field: str,
    basis_date: datetime,
    deadline: datetime,
) -> str:
    basis_label = _BASIS_LABELS.get(basis_field, basis_field)
    return (
        f"I can't process this {label} because the {label} window has expired.\n"
        f"{basis_label.capitalize()} date: {basis_date.strftime('%B %d, %Y')}\n"
        f"{label.capitalize()} deadline: {deadline.strftime('%B %d, %Y')}"
    )
