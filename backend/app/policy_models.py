"""Policy data models for post-order action eligibility."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PolicyAction = Literal["cancel", "return", "refund", "replacement"]
PolicySource = Literal["product", "category", "global"]
WindowBasis = Literal["order_created_at", "payment_date", "shipment_date", "delivery_date"]


class PolicyWindow(BaseModel):
    """Time window definition for a policy."""

    type: Literal["hours", "days"]
    hours: int | None = None
    days: int | None = None
    based_on: WindowBasis

    def duration_seconds(self) -> int:
        if self.type == "hours" and self.hours is not None:
            return self.hours * 3600
        if self.type == "days" and self.days is not None:
            return self.days * 86400
        return 0


class ActionPolicy(BaseModel):
    """A single configured policy for one post-order action."""

    policy_id: str
    policy_version: str = "1.0"
    action: PolicyAction
    enabled: bool = True
    window: PolicyWindow | None = None
    allowed_statuses: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    excluded_products: list[str] = Field(default_factory=list)
    requires_reason: bool = False
    # Scope: product_id / category slug / None (global)
    scope: PolicySource = "global"
    scope_value: str | None = None  # product slug or category slug


class PolicySet(BaseModel):
    """All policies registered for one application."""

    app_id: str
    policies: list[ActionPolicy] = Field(default_factory=list)


class PolicyResolution(BaseModel):
    """Result of resolving which policy governs an action."""

    policy_found: bool
    policy_id: str | None = None
    policy_version: str | None = None
    source: PolicySource | None = None
    policy: ActionPolicy | None = None


class EligibilityChecks(BaseModel):
    """Individual gate results recorded for audit."""

    policy_exists: bool = False
    policy_enabled: bool = False
    authenticated: bool = False
    status_allowed: bool = False
    product_eligible: bool = False
    time_window: bool = False


class EligibilityResult(BaseModel):
    """Structured response from the policy engine."""

    eligible: bool
    action: PolicyAction
    policy_found: bool
    policy_id: str | None = None
    policy_version: str | None = None
    deadline: datetime | None = None
    reason_code: str | None = None
    message: str
    checks: EligibilityChecks = Field(default_factory=EligibilityChecks)
    # Extra fields for transparent user messaging
    window_basis_date: datetime | None = None
    window_basis_field: str | None = None


class PolicyAuditEntry(BaseModel):
    """Immutable audit record for every policy decision."""

    request_id: str
    user_id: str | None
    app_id: str
    order_id: str | None
    order_item_id: str | None
    action: PolicyAction
    policy_id: str | None
    policy_version: str | None
    eligible: bool
    reason_code: str | None
    checked_at: datetime
    deadline: datetime | None
    checks: dict[str, Any]
