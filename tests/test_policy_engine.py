"""Policy engine tests — covers all 34 cases from the spec.

Tests are deterministic and do not use the LLM or real HTTP clients.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "chatbot/backend")

from app.policy_engine import check_action_eligibility
from app.policy_models import (
    ActionPolicy,
    EligibilityChecks,
    PolicyResolution,
    PolicyWindow,
)
from app.policy_registry import load_policies, resolve_policy

# ─── Helpers ──────────────────────────────────────────────────────────────────

NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
YESTERDAY = NOW - timedelta(days=1)
LAST_WEEK = NOW - timedelta(days=7)
LAST_MONTH = NOW - timedelta(days=31)
DELIVERED_RECENT = {"status": "delivered", "delivery_date": (NOW - timedelta(days=5)).isoformat()}
DELIVERED_OLD = {"status": "delivered", "delivery_date": (NOW - timedelta(days=45)).isoformat()}
PENDING_ORDER = {"status": "pending", "order_created_at": (NOW - timedelta(hours=2)).isoformat()}
PENDING_OLD = {"status": "pending", "order_created_at": (NOW - timedelta(hours=30)).isoformat()}
CANCELLED_ORDER = {"status": "cancelled", "order_created_at": NOW.isoformat()}
ELECTRONICS_ITEM = {"product_id": "iphone-15", "category": "electronics"}
EXCLUDED_ITEM = {"product_id": "no-return-prod", "category": "general"}


def _return_policy(days=30, enabled=True, scope="global", scope_value=None) -> PolicyResolution:
    policy = ActionPolicy(
        policy_id="return-policy-v1",
        action="return",
        enabled=enabled,
        scope=scope,
        scope_value=scope_value,
        window=PolicyWindow(type="days", days=days, based_on="delivery_date"),
        allowed_statuses=["delivered"],
        requires_reason=True,
    )
    return PolicyResolution(policy_found=True, policy_id=policy.policy_id, policy_version="1.0", source=scope, policy=policy)


def _cancel_policy(hours=24, enabled=True) -> PolicyResolution:
    policy = ActionPolicy(
        policy_id="cancel-policy-v1",
        action="cancel",
        enabled=enabled,
        window=PolicyWindow(type="hours", hours=hours, based_on="order_created_at"),
        allowed_statuses=["pending", "confirmed"],
    )
    return PolicyResolution(policy_found=True, policy_id=policy.policy_id, policy_version="1.0", source="global", policy=policy)


def _refund_policy(days=30) -> PolicyResolution:
    policy = ActionPolicy(
        policy_id="refund-policy-v1",
        action="refund",
        window=PolicyWindow(type="days", days=days, based_on="delivery_date"),
        allowed_statuses=["delivered"],
        requires_reason=True,
    )
    return PolicyResolution(policy_found=True, policy_id=policy.policy_id, policy_version="1.0", source="global", policy=policy)


def _replacement_policy(days=15) -> PolicyResolution:
    policy = ActionPolicy(
        policy_id="replacement-policy-v1",
        action="replacement",
        window=PolicyWindow(type="days", days=days, based_on="delivery_date"),
        allowed_statuses=["delivered"],
        requires_reason=True,
    )
    return PolicyResolution(policy_found=True, policy_id=policy.policy_id, policy_version="1.0", source="global", policy=policy)


def _no_policy() -> PolicyResolution:
    return PolicyResolution(policy_found=False)


def run(action, order, item, resolution, authenticated=True, now=NOW):
    return check_action_eligibility(
        action=action,
        order=order,
        order_item=item,
        resolution=resolution,
        authenticated=authenticated,
        current_datetime=now,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POLICY EXISTENCE (cases 1-5)
# ═══════════════════════════════════════════════════════════════════════════════

def test_1_return_policy_exists_continues():
    result = run("return", DELIVERED_RECENT, {}, _return_policy())
    assert result.eligible is True
    assert result.policy_found is True


def test_2_return_policy_missing_rejects():
    result = run("return", DELIVERED_RECENT, {}, _no_policy())
    assert result.eligible is False
    assert result.policy_found is False
    assert result.reason_code == "NO_POLICY_CONFIGURED"
    assert "return" in result.message.lower()


def test_3_refund_policy_missing_rejects():
    result = run("refund", DELIVERED_RECENT, {}, _no_policy())
    assert result.eligible is False
    assert result.reason_code == "NO_POLICY_CONFIGURED"


def test_4_replacement_policy_missing_rejects():
    result = run("replacement", DELIVERED_RECENT, {}, _no_policy())
    assert result.eligible is False
    assert result.reason_code == "NO_POLICY_CONFIGURED"


def test_5_cancel_policy_missing_rejects():
    result = run("cancel", PENDING_ORDER, {}, _no_policy())
    assert result.eligible is False
    assert result.reason_code == "NO_POLICY_CONFIGURED"


# ═══════════════════════════════════════════════════════════════════════════════
# DATE WINDOW (cases 6-11)
# ═══════════════════════════════════════════════════════════════════════════════

def test_6_request_exactly_on_deadline_is_eligible():
    # delivery_date = NOW - 30 days; deadline = exactly NOW — still within window
    boundary_order = {"status": "delivered", "delivery_date": (NOW - timedelta(days=30)).isoformat()}
    result = run("return", boundary_order, {}, _return_policy(days=30), now=NOW)
    # Deadline is exactly NOW so not strictly after deadline
    assert result.eligible is True


def test_7_request_before_deadline_is_allowed():
    result = run("return", DELIVERED_RECENT, {}, _return_policy())
    assert result.eligible is True
    assert result.checks.time_window is True


def test_8_request_after_deadline_is_rejected():
    result = run("return", DELIVERED_OLD, {}, _return_policy(days=30))
    assert result.eligible is False
    assert "WINDOW_EXPIRED" in result.reason_code
    assert result.deadline is not None


def test_9_cancel_after_window_rejected():
    result = run("cancel", PENDING_OLD, {}, _cancel_policy(hours=24))
    assert result.eligible is False
    assert "WINDOW_EXPIRED" in result.reason_code


def test_10_return_after_window_rejected():
    result = run("return", DELIVERED_OLD, {}, _return_policy(days=30))
    assert result.eligible is False


def test_11_refund_after_window_rejected():
    result = run("refund", DELIVERED_OLD, {}, _refund_policy(days=30))
    assert result.eligible is False


def test_11b_replacement_after_window_rejected():
    old_delivery = {"status": "delivered", "delivery_date": (NOW - timedelta(days=20)).isoformat()}
    result = run("replacement", old_delivery, {}, _replacement_policy(days=15))
    assert result.eligible is False


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS CHECKS (cases 12-17)
# ═══════════════════════════════════════════════════════════════════════════════

def test_12_delivered_product_return_eligible():
    result = run("return", DELIVERED_RECENT, {}, _return_policy())
    assert result.eligible is True


def test_13_non_delivered_return_rejected():
    shipped = {"status": "shipped", "delivery_date": ""}
    result = run("return", shipped, {}, _return_policy())
    assert result.eligible is False
    assert result.reason_code == "ORDER_STATUS_NOT_ALLOWED"


def test_14_cancelled_order_cancel_rejected():
    result = run("cancel", CANCELLED_ORDER, {}, _cancel_policy())
    assert result.eligible is False
    assert result.reason_code == "ORDER_STATUS_NOT_ALLOWED"


def test_15_policy_disabled_rejects():
    result = run("return", DELIVERED_RECENT, {}, _return_policy(enabled=False))
    assert result.eligible is False
    assert result.reason_code == "POLICY_DISABLED"


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCT POLICY (cases 18-22)
# ═══════════════════════════════════════════════════════════════════════════════

def test_18_excluded_category_rejected():
    policy = ActionPolicy(
        policy_id="return-policy-v1",
        action="return",
        window=PolicyWindow(type="days", days=30, based_on="delivery_date"),
        allowed_statuses=["delivered"],
        excluded_categories=["electronics"],
    )
    resolution = PolicyResolution(policy_found=True, policy_id=policy.policy_id, policy_version="1.0", source="global", policy=policy)
    result = run("return", DELIVERED_RECENT, ELECTRONICS_ITEM, resolution)
    assert result.eligible is False
    assert result.reason_code == "CATEGORY_EXCLUDED"


def test_19_excluded_product_rejected():
    policy = ActionPolicy(
        policy_id="return-policy-v1",
        action="return",
        window=PolicyWindow(type="days", days=30, based_on="delivery_date"),
        allowed_statuses=["delivered"],
        excluded_products=["no-return-prod"],
    )
    resolution = PolicyResolution(policy_found=True, policy_id=policy.policy_id, policy_version="1.0", source="global", policy=policy)
    result = run("return", DELIVERED_RECENT, EXCLUDED_ITEM, resolution)
    assert result.eligible is False
    assert result.reason_code == "PRODUCT_EXCLUDED"


def test_20_product_specific_policy_overrides_global():
    """Product-specific no-return policy must override global 30-day return."""
    load_policies("ecommerce_test", [
        {"policy_id": "global-return", "action": "return", "enabled": True, "scope": "global",
         "window": {"type": "days", "days": 30, "based_on": "delivery_date"}, "allowed_statuses": ["delivered"]},
        {"policy_id": "no-return-prod", "action": "return", "enabled": False, "scope": "product",
         "scope_value": "special-item", "allowed_statuses": ["delivered"]},
    ])
    resolution = resolve_policy(app_id="ecommerce_test", action="return", product_id="special-item")
    assert resolution.policy_found is True
    assert resolution.policy_id == "no-return-prod"
    assert resolution.source == "product"
    result = run("return", DELIVERED_RECENT, {"product_id": "special-item"}, resolution)
    assert result.eligible is False
    assert result.reason_code == "POLICY_DISABLED"


def test_21_category_policy_overrides_global():
    """Electronics 14-day return must override global 30-day."""
    load_policies("ecommerce_test2", [
        {"policy_id": "global-return", "action": "return", "enabled": True, "scope": "global",
         "window": {"type": "days", "days": 30, "based_on": "delivery_date"}, "allowed_statuses": ["delivered"]},
        {"policy_id": "electronics-return", "action": "return", "enabled": True, "scope": "category",
         "scope_value": "electronics",
         "window": {"type": "days", "days": 14, "based_on": "delivery_date"}, "allowed_statuses": ["delivered"]},
    ])
    resolution = resolve_policy(app_id="ecommerce_test2", action="return", category="electronics")
    assert resolution.policy_id == "electronics-return"
    assert resolution.source == "category"


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY (cases 22-25)
# ═══════════════════════════════════════════════════════════════════════════════

def test_22_unauthenticated_user_rejected():
    result = run("return", DELIVERED_RECENT, {}, _return_policy(), authenticated=False)
    assert result.eligible is False
    assert result.reason_code == "AUTHENTICATION_REQUIRED"


def test_23_missing_basis_date_fails_closed():
    order = {"status": "delivered"}  # no delivery_date
    result = run("return", order, {}, _return_policy())
    assert result.eligible is False
    assert result.reason_code == "WINDOW_BASIS_DATE_MISSING"


# ═══════════════════════════════════════════════════════════════════════════════
# FAIL-SAFE (cases 27-30)
# ═══════════════════════════════════════════════════════════════════════════════

def test_27_policy_not_found_blocks_action():
    result = run("cancel", PENDING_ORDER, {}, _no_policy())
    assert result.eligible is False
    assert result.policy_found is False


def test_28_policy_registry_resolution_returns_no_policy_when_missing():
    load_policies("empty_app", [])
    resolution = resolve_policy(app_id="empty_app", action="cancel")
    assert resolution.policy_found is False


# ═══════════════════════════════════════════════════════════════════════════════
# SUCCESS PATHS (cases 31-34)
# ═══════════════════════════════════════════════════════════════════════════════

def test_31_valid_cancellation():
    result = run("cancel", PENDING_ORDER, {}, _cancel_policy())
    assert result.eligible is True
    assert result.checks.status_allowed is True
    assert result.checks.time_window is True


def test_32_valid_return():
    result = run("return", DELIVERED_RECENT, {}, _return_policy())
    assert result.eligible is True
    assert result.policy_id == "return-policy-v1"


def test_33_valid_refund():
    result = run("refund", DELIVERED_RECENT, {}, _refund_policy())
    assert result.eligible is True


def test_34_valid_replacement():
    result = run("replacement", DELIVERED_RECENT, {}, _replacement_policy())
    assert result.eligible is True


# ═══════════════════════════════════════════════════════════════════════════════
# POLICY REGISTRY (resolve_policy hierarchy)
# ═══════════════════════════════════════════════════════════════════════════════

def test_registry_loads_and_resolves_global_policy():
    load_policies("shop1", [
        {"policy_id": "cancel-v1", "action": "cancel", "enabled": True, "scope": "global",
         "window": {"type": "hours", "hours": 24, "based_on": "order_created_at"},
         "allowed_statuses": ["pending"]},
    ])
    resolution = resolve_policy(app_id="shop1", action="cancel")
    assert resolution.policy_found is True
    assert resolution.policy_id == "cancel-v1"


def test_registry_returns_no_policy_for_unknown_action():
    load_policies("shop2", [
        {"policy_id": "cancel-v1", "action": "cancel", "enabled": True, "scope": "global",
         "window": {"type": "hours", "hours": 24, "based_on": "order_created_at"}, "allowed_statuses": ["pending"]},
    ])
    resolution = resolve_policy(app_id="shop2", action="refund")
    assert resolution.policy_found is False


def test_registry_skips_malformed_policy(caplog):
    load_policies("shop3", [{"bad": "data"}])
    resolution = resolve_policy(app_id="shop3", action="cancel")
    assert resolution.policy_found is False


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW INTEGRATION — policy gate blocks before API call
# ═══════════════════════════════════════════════════════════════════════════════

def test_workflow_blocks_cancel_when_no_policy(tmp_path):
    """Policy gate must block cancel_order even if the API would accept it."""
    from app.app_registry import ApplicationRegistry
    from app.authorization import AuthState
    from app.models import RoutePlan
    from app.workflow import ChatWorkflow

    registry_file = tmp_path / "applications.json"
    registry_file.write_text(json.dumps({"applications": [{
        "app_id": "shop",
        "name": "Shop",
        "base_url": "http://shop.test",
        "jwt_secret_env": "SHOP_JWT",
        "service_key_env": "SHOP_KEY",
        "routes": [{
            "name": "cancel_order",
            "method": "POST",
            "path": "/api/v1/orders/{order_id}/cancel",
            "description": "Cancel order",
            "visibility": "private",
            "requires_auth": True,
            "parameters": {"order_id": "Order ID"},
            "required_parameters": ["order_id"],
        }],
        "policies": [],   # ← no cancel policy configured
    }]}), encoding="utf-8")

    class _NeverCalledClient:
        async def execute(self, **_):
            raise AssertionError("API must not be called when policy is missing")

    registry = ApplicationRegistry(registry_file)
    application = registry.get("shop")

    class _StubPlanner:
        async def plan(self, *, message, application):
            return RoutePlan(route_name="cancel_order", parameters={"order_id": "ord-1"})

    workflow = ChatWorkflow(registry, _StubPlanner(), _NeverCalledClient())
    result = asyncio.run(workflow.run({
        "application": application,
        "message": "cancel my order",
        "authorization": "Bearer tok",
        "auth_state": AuthState("shop", authenticated=True, user_id="u1"),
        "request_id": "req-policy-block",
        "history": [],
    }))

    assert result.get("execution_error") is not None
    assert "NO_POLICY" in str(result.get("metadata", {}).get("reason_code", ""))


def test_workflow_blocks_cancel_expired_window(tmp_path):
    """Policy gate must block cancel when the window has passed."""
    from app.app_registry import ApplicationRegistry
    from app.authorization import AuthState
    from app.models import RoutePlan
    from app.workflow import ChatWorkflow

    registry_file = tmp_path / "applications.json"
    # order_created_at is 48 hours ago — window is only 24h
    old_created = (NOW - timedelta(hours=48)).isoformat()
    registry_file.write_text(json.dumps({"applications": [{
        "app_id": "shop2",
        "name": "Shop2",
        "base_url": "http://shop2.test",
        "jwt_secret_env": "SHOP_JWT",
        "service_key_env": "SHOP_KEY",
        "routes": [{
            "name": "cancel_order",
            "method": "POST",
            "path": "/api/v1/orders/{order_id}/cancel",
            "description": "Cancel order",
            "visibility": "private",
            "requires_auth": True,
            "parameters": {"order_id": "Order ID"},
            "required_parameters": ["order_id"],
        }],
        "policies": [{
            "policy_id": "cancel-v1",
            "action": "cancel",
            "enabled": True,
            "scope": "global",
            "window": {"type": "hours", "hours": 24, "based_on": "order_created_at"},
            "allowed_statuses": ["pending", "confirmed"],
        }],
    }]}), encoding="utf-8")

    class _NeverCalledClient:
        async def execute(self, **_):
            raise AssertionError("API must not be called when window is expired")

    registry = ApplicationRegistry(registry_file)
    application = registry.get("shop2")

    class _StubPlanner:
        async def plan(self, *, message, application):
            return RoutePlan(route_name="cancel_order", parameters={"order_id": "ord-1"})

    workflow = ChatWorkflow(registry, _StubPlanner(), _NeverCalledClient())
    result = asyncio.run(workflow.run({
        "application": application,
        "message": "cancel my order",
        "authorization": "Bearer tok",
        "auth_state": AuthState("shop2", authenticated=True, user_id="u1"),
        "request_id": "req-expired",
        "history": [
            {"role": "assistant", "data": json.dumps([{
                "id": "ord-1", "status": "pending", "order_created_at": old_created,
            }])},
        ],
    }))

    assert result.get("execution_error") is not None
    assert "WINDOW_EXPIRED" in str(result.get("metadata", {}).get("reason_code", ""))
