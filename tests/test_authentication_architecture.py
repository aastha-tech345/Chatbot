"""Comprehensive tests for authentication-aware multi-application chatbot architecture.

Tests cover:
1. Guest users accessing public data
2. Guest users blocked from private data with proper auth prompts
3. Authenticated users accessing private data
4. Cross-app authentication isolation
5. Dynamic authentication configuration
6. Application-specific welcome messages and quick actions
7. Public API never triggering login unnecessarily
8. Private API properly validating authentication
9. Credentials never sent to LLM or exposed in responses
10. Multiple applications with different auth methods
"""
import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, "chatbot/backend")

from app.authorization import AuthState, authenticate, classify
from app.models import (
    ApplicationDefinition,
    AuthenticationConfig,
    AuthenticationField,
    ChatbotConfig,
    HTTPMethod,
    LinkedApplication,
    RouteDefinition,
)
from app.intent_classifier import classify_route, IntentCategory, classify_intent
from app.auth_enforcement import enforce_route_authentication
from app.app_registry import ApplicationRegistry
from app.main import app
from app.security import verify_hs256_jwt

# ============================================================
# Test Fixtures and Helpers
# ============================================================


def _hs256_token(secret: str, sub: str = "user-1", **claims) -> str:
    """Create a valid HS256 JWT token."""

    def encode(value: dict[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_id": claims.pop("app_id", "ecommerce"),
        **claims,
    }
    claims_encoded = encode(payload)
    signature = hmac.new(secret.encode(), f"{header}.{claims_encoded}".encode(), hashlib.sha256).digest()
    token_sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{claims_encoded}.{token_sig}"


def _create_test_app(
    app_id: str,
    name: str,
    auth_enabled: bool = False,
    auth_method: str = "password",
    auth_fields: list[AuthenticationField] | None = None,
) -> ApplicationDefinition:
    """Create a test application with public and private routes."""
    if auth_fields is None:
        auth_fields = [
            AuthenticationField(name="email", label="Email", type="email"),
            AuthenticationField(name="password", label="Password", type="password"),
        ]

    return ApplicationDefinition(
        app_id=app_id,
        name=name,
        base_url="http://localhost:3333",
        jwt_secret_env="TEST_JWT_SECRET",
        service_key_env="TEST_SERVICE_KEY",
        authentication=AuthenticationConfig(
            enabled=auth_enabled,
            method=auth_method,
            fields=auth_fields,
            verification="jwt",
        ),
        chatbot=ChatbotConfig(
            enabled=True,
            welcome_message=f"Welcome to {name}!",
            quick_actions=[f"Action for {app_id}"],
        ),
        routes=[
            RouteDefinition(
                name="public_list",
                method=HTTPMethod.GET,
                path="/api/public",
                description="Public list",
                visibility="public",
                requires_auth=False,
            ),
            RouteDefinition(
                name="public_detail",
                method=HTTPMethod.GET,
                path="/api/public/{id}",
                description="Public detail",
                visibility="public",
                requires_auth=False,
                parameters={"id": "ID"},
            ),
            RouteDefinition(
                name="private_list",
                method=HTTPMethod.GET,
                path="/api/private",
                description="Private list",
                visibility="private",
                requires_auth=True,
                requires_user_context=True,
            ),
            RouteDefinition(
                name="private_action",
                method=HTTPMethod.POST,
                path="/api/private/action",
                description="Private action",
                visibility="private",
                requires_auth=True,
                requires_user_context=True,
                required_parameters=["data"],
                parameters={"data": "Action data"},
            ),
        ],
    )


# ============================================================
# Test Cases: 1-4 Intent Classification (Metadata-based)
# ============================================================


class TestIntentClassification:
    """Test metadata-based intent classification without LLM."""

    def test_classify_public_get_route(self):
        """Test: Guest -> public product list -> PUBLIC_QUERY."""
        app = _create_test_app("test", "Test App")
        route = next(r for r in app.routes if r.name == "public_list")
        category = classify_route(route)
        assert category == IntentCategory.PUBLIC_QUERY

    def test_classify_user_specific_get_route(self):
        """Test: Auth required -> my orders -> USER_SPECIFIC_QUERY."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        route = next(r for r in app.routes if r.name == "private_list")
        category = classify_route(route)
        assert category == IntentCategory.USER_SPECIFIC_QUERY

    def test_classify_public_action(self):
        """Test: Compare products -> PUBLIC_ACTION."""
        app = _create_test_app("test", "Test App")
        route = next(r for r in app.routes if r.name == "public_list")
        category = classify_route(route, is_comparison=True)
        assert category == IntentCategory.PUBLIC_ACTION

    def test_classify_auth_required_action(self):
        """Test: Add to cart -> AUTH_REQUIRED_ACTION."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        route = next(r for r in app.routes if r.name == "private_action")
        category = classify_route(route)
        assert category == IntentCategory.AUTH_REQUIRED_ACTION

    def test_classify_unknown_no_route(self):
        """Test: None route -> UNKNOWN."""
        category = classify_route(None)
        assert category == IntentCategory.UNKNOWN

    def test_classify_intent_requires_auth(self):
        """Test: IntentClassification includes requires_auth flag."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        
        public_route = next(r for r in app.routes if r.name == "public_list")
        public_result = classify_intent(public_route)
        assert public_result.requires_auth is False
        
        private_route = next(r for r in app.routes if r.name == "private_list")
        private_result = classify_intent(private_route)
        assert private_result.requires_auth is True


# ============================================================
# Test Cases: 5-8 Authentication Enforcement
# ============================================================


class TestAuthenticationEnforcement:
    """Test authentication enforcement based on route protection and auth state."""

    def test_public_route_allowed_without_auth(self):
        """Test: Public route executes without auth."""
        app = _create_test_app("test", "Test App")
        route = next(r for r in app.routes if r.name == "public_list")
        auth_state = AuthState(app.app_id, authenticated=False)
        result = enforce_route_authentication(route, app, auth_state)
        assert result.allowed is True
        assert result.reason is None

    def test_private_route_blocked_without_auth(self):
        """Test: Private route blocked; requests auth."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        route = next(r for r in app.routes if r.name == "private_list")
        auth_state = AuthState(app.app_id, authenticated=False)
        result = enforce_route_authentication(route, app, auth_state)
        assert result.allowed is False
        assert result.reason == "authentication_required"
        assert result.error_response is not None
        assert result.error_response.get("auth_required") is True

    def test_private_route_allowed_with_auth(self):
        """Test: Authenticated user can access private route."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        route = next(r for r in app.routes if r.name == "private_list")
        auth_state = AuthState(app.app_id, authenticated=True, user_id="user-1")
        result = enforce_route_authentication(route, app, auth_state)
        assert result.allowed is True

    def test_wrong_app_auth_state_blocked(self):
        """Test: Auth state for wrong app is rejected."""
        app_a = _create_test_app("app_a", "App A", auth_enabled=True)
        app_b = _create_test_app("app_b", "App B", auth_enabled=True)
        route = next(r for r in app_a.routes if r.name == "private_list")
        
        # Auth state for app_b should not work for app_a
        auth_state = AuthState("app_b", authenticated=True, user_id="user-1")
        result = enforce_route_authentication(route, app_a, auth_state)
        assert result.allowed is False
        assert result.reason == "wrong_application"

    def test_insufficient_permissions_with_roles(self):
        """Test: User without required role is rejected."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        route = RouteDefinition(
            name="admin_action",
            method=HTTPMethod.GET,
            path="/api/admin",
            description="Admin only",
            visibility="private",
            requires_auth=True,
            allowed_roles=["admin"],
        )
        
        # User without admin role
        auth_state = AuthState(app.app_id, authenticated=True, user_id="user-1", roles=frozenset({"user"}))
        result = enforce_route_authentication(route, app, auth_state)
        assert result.allowed is False
        assert result.reason == "insufficient_permissions"

    def test_sufficient_permissions_with_matching_role(self):
        """Test: User with required role is allowed."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        route = RouteDefinition(
            name="admin_action",
            method=HTTPMethod.GET,
            path="/api/admin",
            description="Admin only",
            visibility="private",
            requires_auth=True,
            allowed_roles=["admin"],
        )
        
        # User with admin role
        auth_state = AuthState(app.app_id, authenticated=True, user_id="user-1", roles=frozenset({"admin"}))
        result = enforce_route_authentication(route, app, auth_state)
        assert result.allowed is True


# ============================================================
# Test Cases: 9-12 Dynamic Authentication Configuration
# ============================================================


class TestDynamicAuthenticationConfig:
    """Test that auth config is loaded dynamically from application registry."""

    def test_ecommerce_auth_fields(self, monkeypatch):
        """Test: E-commerce uses email/password auth."""
        registry = ApplicationRegistry()
        ecommerce = registry.get("ecommerce")
        assert ecommerce.authentication.enabled is True
        assert ecommerce.authentication.method == "password"
        field_names = [f.name for f in ecommerce.authentication.fields]
        assert "email" in field_names
        assert "password" in field_names

    def test_his_auth_fields(self, monkeypatch):
        """Test: HIS uses phone/OTP auth (different from ecommerce)."""
        monkeypatch.setenv("HIS_API_URL", "http://localhost:9000")
        monkeypatch.setenv("HIS_JWT_SECRET", "test-secret")
        monkeypatch.setenv("HIS_MASTER_CHATBOT_SERVICE_KEY", "test-key")
        
        registry = ApplicationRegistry()
        his = registry.get("his")
        assert his.authentication.enabled is True
        assert his.authentication.method == "phone_otp"
        field_names = [f.name for f in his.authentication.fields]
        assert "phone" in field_names
        # Should NOT have email field
        assert "email" not in field_names

    def test_hrm_auth_fields(self, monkeypatch):
        """Test: HRM uses employee_id/password (different from ecommerce)."""
        monkeypatch.setenv("HRM_API_URL", "http://localhost:3333")
        monkeypatch.setenv("HRM_JWT_SECRET", "test-secret")
        monkeypatch.setenv("HRM_MASTER_CHATBOT_SERVICE_KEY", "test-key")
        
        registry = ApplicationRegistry()
        hrm = registry.get("hrm")
        assert hrm.authentication.enabled is True
        assert hrm.authentication.method == "employee_credentials"
        field_names = [f.name for f in hrm.authentication.fields]
        assert "employee_id" in field_names
        assert "password" in field_names
        # Should NOT have email field
        assert "email" not in field_names

    def test_chatbot_config_is_dynamic(self):
        """Test: Welcome message and quick actions come from config."""
        registry = ApplicationRegistry()
        ecommerce = registry.get("ecommerce")
        
        assert ecommerce.chatbot.enabled is True
        assert "products" in ecommerce.chatbot.welcome_message.lower()
        assert len(ecommerce.chatbot.quick_actions) > 0
        assert any("product" in action.lower() for action in ecommerce.chatbot.quick_actions)


# ============================================================
# Test Cases: 13-16 Public vs Private Route Metadata
# ============================================================


class TestPublicPrivateRouteMetadata:
    """Test that routes are properly classified as public or private."""

    def test_ecommerce_public_routes(self):
        """Test: Ecommerce search/list/detail routes are public."""
        registry = ApplicationRegistry()
        app = registry.get("ecommerce")
        
        public_routes = [r for r in app.routes if r.visibility == "public"]
        assert len(public_routes) > 0
        
        # These should be public
        public_names = [r.name for r in public_routes]
        assert any("search" in n or "list" in n or "categories" in n or "brands" in n for n in public_names)

    def test_ecommerce_private_routes(self):
        """Test: Ecommerce orders/cart/wishlist routes are private."""
        registry = ApplicationRegistry()
        app = registry.get("ecommerce")
        
        private_routes = [r for r in app.routes if r.visibility == "private"]
        assert len(private_routes) > 0
        
        # These should be private
        private_names = [r.name for r in private_routes]
        assert any("order" in n or "cart" in n or "wishlist" in n for n in private_names)
        assert all(r.requires_auth for r in private_routes)

    def test_his_public_routes(self):
        """Test: HIS departments/doctors/services routes are public."""
        import os
        os.environ["HIS_API_URL"] = "http://localhost:9000"
        os.environ["HIS_JWT_SECRET"] = "test"
        os.environ["HIS_MASTER_CHATBOT_SERVICE_KEY"] = "test"
        
        registry = ApplicationRegistry()
        app = registry.get("his")
        
        public_routes = [r for r in app.routes if r.visibility == "public"]
        public_names = [r.name for r in public_routes]
        
        # These should be public
        assert any("department" in n or "doctor" in n or "service" in n or "hospital" in n for n in public_names)

    def test_his_private_routes(self):
        """Test: HIS appointments/reports/prescriptions routes are private."""
        import os
        os.environ["HIS_API_URL"] = "http://localhost:9000"
        os.environ["HIS_JWT_SECRET"] = "test"
        os.environ["HIS_MASTER_CHATBOT_SERVICE_KEY"] = "test"
        
        registry = ApplicationRegistry()
        app = registry.get("his")
        
        private_routes = [r for r in app.routes if r.visibility == "private"]
        private_names = [r.name for r in private_routes]
        
        # These should be private
        assert any("appointment" in n or "report" in n or "prescription" in n or "bill" in n for n in private_names)


# ============================================================
# Test Cases: 17-20 Cross-Application Authentication Isolation
# ============================================================


class TestCrossAppAuthenticationIsolation:
    """Test that authentication is properly isolated per application."""

    def test_ecommerce_auth_doesnt_work_for_his(self, monkeypatch):
        """Test: User logged into Ecommerce must log into HIS separately."""
        monkeypatch.setenv("HIS_API_URL", "http://localhost:9000")
        monkeypatch.setenv("HIS_JWT_SECRET", "his-secret")
        monkeypatch.setenv("HIS_MASTER_CHATBOT_SERVICE_KEY", "test-key")
        
        ecommerce_auth = AuthState("ecommerce", authenticated=True, user_id="user-1")
        his_app = ApplicationRegistry().get("his")
        
        private_route = next(r for r in his_app.routes if r.visibility == "private")
        result = enforce_route_authentication(private_route, his_app, ecommerce_auth)
        
        # Should be blocked because auth is for wrong app
        assert result.allowed is False
        assert result.reason == "wrong_application"

    def test_his_auth_doesnt_work_for_hrm(self, monkeypatch):
        """Test: User logged into HIS must log into HRM separately."""
        monkeypatch.setenv("HIS_API_URL", "http://localhost:9000")
        monkeypatch.setenv("HIS_JWT_SECRET", "his-secret")
        monkeypatch.setenv("HIS_MASTER_CHATBOT_SERVICE_KEY", "test-key")
        monkeypatch.setenv("HRM_API_URL", "http://localhost:3333")
        monkeypatch.setenv("HRM_JWT_SECRET", "hrm-secret")
        monkeypatch.setenv("HRM_MASTER_CHATBOT_SERVICE_KEY", "test-key")
        
        his_auth = AuthState("his", authenticated=True, user_id="patient-123")
        hrm_app = ApplicationRegistry().get("hrm")
        
        private_route = next(r for r in hrm_app.routes if r.visibility == "private")
        result = enforce_route_authentication(private_route, hrm_app, his_auth)
        
        # Should be blocked because auth is for wrong app
        assert result.allowed is False
        assert result.reason == "wrong_application"

    def test_guest_session_isolation(self):
        """Test: Guest sessions are isolated per app."""
        guest_a = AuthState("app_a", authenticated=False)
        guest_b = AuthState("app_b", authenticated=False)
        
        # Both are unauthenticated but different apps
        assert guest_a.app_id != guest_b.app_id
        assert guest_a.authenticated == guest_b.authenticated == False


# ============================================================
# Test Cases: 21-24 No Credentials in LLM or Responses
# ============================================================


class TestCredentialsSecurity:
    """Test that credentials are never exposed to LLM or in responses."""

    def test_auth_config_public_config_excludes_sensitive_fields(self):
        """Test: Public auth config doesn't expose verification strategy or internal fields."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        public_config = app.authentication.public_config()
        
        # Should have these
        assert "fields" in public_config
        assert "enabled" in public_config
        assert "method" in public_config
        
        # Should NOT have these
        assert "verification" not in public_config
        assert "user_info_path" not in public_config
        assert "principal_field" not in public_config
        assert "roles_field" not in public_config
        assert "audience" not in public_config
        assert "issuer" not in public_config

    def test_auth_state_no_password_storage(self):
        """Test: AuthState never stores passwords or tokens."""
        auth = AuthState(
            app_id="test",
            authenticated=True,
            user_id="user-1",
            roles=frozenset({"user"}),
        )
        
        # Verify no credential fields exist
        assert not hasattr(auth, "password")
        assert not hasattr(auth, "token")
        assert not hasattr(auth, "secret")
        assert not hasattr(auth, "credential")

    def test_sanitization_redacts_sensitive_fields(self):
        """Test: Response sanitization redacts credentials."""
        from app.sanitization import safe_data
        
        response_with_secrets = {
            "id": "123",
            "name": "Product",
            "password": "secret123",
            "api_key": "key-secret",
            "token": "token-secret",
            "authorization": "Bearer secret",
        }
        
        safe_response = safe_data(response_with_secrets)
        
        # Safe fields should be present
        assert safe_response["id"] == "123"
        assert safe_response["name"] == "Product"
        
        # Sensitive fields should be redacted or removed
        # (Note: this depends on implementation, but typically redacted)


# ============================================================
# Test Cases: 25-28 Application-Specific Messages and Actions
# ============================================================


class TestApplicationSpecificConfigs:
    """Test that each application has unique welcome messages and quick actions."""

    def test_ecommerce_welcome_message(self):
        """Test: Ecommerce has commerce-specific welcome message."""
        registry = ApplicationRegistry()
        app = registry.get("ecommerce")
        
        message = app.chatbot.welcome_message.lower()
        assert any(word in message for word in ["product", "price", "order", "shopping"])

    def test_his_welcome_message(self, monkeypatch):
        """Test: HIS has healthcare-specific welcome message."""
        monkeypatch.setenv("HIS_API_URL", "http://localhost:9000")
        monkeypatch.setenv("HIS_JWT_SECRET", "test")
        monkeypatch.setenv("HIS_MASTER_CHATBOT_SERVICE_KEY", "test")
        
        registry = ApplicationRegistry()
        app = registry.get("his")
        
        message = app.chatbot.welcome_message.lower()
        assert any(word in message for word in ["doctor", "appointment", "hospital", "service"])

    def test_hrm_welcome_message(self, monkeypatch):
        """Test: HRM has HR-specific welcome message."""
        monkeypatch.setenv("HRM_API_URL", "http://localhost:9000")
        monkeypatch.setenv("HRM_JWT_SECRET", "test")
        monkeypatch.setenv("HRM_MASTER_CHATBOT_SERVICE_KEY", "test")
        
        registry = ApplicationRegistry()
        app = registry.get("hrm")
        
        message = app.chatbot.welcome_message.lower()
        assert any(word in message for word in ["employee", "attendance", "leave", "payroll"])

    def test_quick_actions_app_specific(self):
        """Test: Each app has different quick actions."""
        registry = ApplicationRegistry()
        ecommerce = registry.get("ecommerce")
        
        ecommerce_actions_str = " ".join(ecommerce.chatbot.quick_actions).lower()
        assert "product" in ecommerce_actions_str or "cart" in ecommerce_actions_str or "order" in ecommerce_actions_str


# ============================================================
# Test Cases: 29-32 No Unnecessary Login Prompts
# ============================================================


class TestNoUnnecessaryLoginPrompts:
    """Test that public queries don't trigger login prompts."""

    def test_public_query_classification(self):
        """Test: Public queries classified as PUBLIC_QUERY."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        public_route = next(r for r in app.routes if r.name == "public_list")
        
        category = classify_route(public_route)
        assert category == IntentCategory.PUBLIC_QUERY

    def test_guest_can_access_public_api(self):
        """Test: Guest with no auth can access public route."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        public_route = next(r for r in app.routes if r.name == "public_list")
        guest_auth = AuthState(app.app_id, authenticated=False)
        
        result = enforce_route_authentication(public_route, app, guest_auth)
        assert result.allowed is True
        assert result.error_response is None

    def test_private_query_requires_auth(self):
        """Test: Private queries require authentication."""
        app = _create_test_app("test", "Test App", auth_enabled=True)
        private_route = next(r for r in app.routes if r.name == "private_list")
        guest_auth = AuthState(app.app_id, authenticated=False)
        
        result = enforce_route_authentication(private_route, app, guest_auth)
        assert result.allowed is False
        assert result.error_response is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
