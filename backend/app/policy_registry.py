"""Policy registry — loads and resolves action policies per application.

Policies are loaded from DB (chatbot_config_json.policies) during startup via
ApplicationRegistry._reload_from_db(), then cached in memory here.
Resolution follows product → category → global priority order.
No LLM involvement; this module is entirely deterministic.
"""
from __future__ import annotations

import logging
from typing import Any

from .policy_models import ActionPolicy, PolicyAction, PolicyResolution, PolicySet

logger = logging.getLogger(__name__)

# In-memory cache: app_id → PolicySet
_cache: dict[str, PolicySet] = {}


def load_policies(app_id: str, raw_policies: list[dict[str, Any]]) -> PolicySet:
    """Parse and cache policies from the DB chatbot_config_json policies list."""
    parsed: list[ActionPolicy] = []
    for item in raw_policies:
        try:
            parsed.append(ActionPolicy.model_validate(item))
        except Exception as exc:
            logger.warning("[POLICY] skipping malformed policy app_id=%s error=%s", app_id, exc)
    policy_set = PolicySet(app_id=app_id, policies=parsed)
    _cache[app_id] = policy_set
    logger.info("[POLICY] loaded app_id=%s count=%d", app_id, len(parsed))
    return policy_set


def get_policy_set(app_id: str) -> PolicySet | None:
    return _cache.get(app_id)


def resolve_policy(
    *,
    app_id: str,
    action: PolicyAction,
    product_id: str | None = None,
    category: str | None = None,
) -> PolicyResolution:
    """Resolve the most specific applicable policy for an action.

    Priority: product-specific → category-specific → global.
    Returns PolicyResolution with policy_found=False if nothing is configured.
    """
    policy_set = _cache.get(app_id)
    if policy_set is None:
        logger.warning("[POLICY] no policies loaded for app_id=%s", app_id)
        return PolicyResolution(policy_found=False)

    candidates = [p for p in policy_set.policies if p.action == action]
    if not candidates:
        return PolicyResolution(policy_found=False)

    # 1. Product-specific
    if product_id:
        for p in candidates:
            if p.scope == "product" and p.scope_value == product_id:
                return PolicyResolution(
                    policy_found=True,
                    policy_id=p.policy_id,
                    policy_version=p.policy_version,
                    source="product",
                    policy=p,
                )

    # 2. Category-specific
    if category:
        for p in candidates:
            if p.scope == "category" and p.scope_value == category:
                return PolicyResolution(
                    policy_found=True,
                    policy_id=p.policy_id,
                    policy_version=p.policy_version,
                    source="category",
                    policy=p,
                )

    # 3. Global
    for p in candidates:
        if p.scope == "global":
            return PolicyResolution(
                policy_found=True,
                policy_id=p.policy_id,
                policy_version=p.policy_version,
                source="global",
                policy=p,
            )

    return PolicyResolution(policy_found=False)
