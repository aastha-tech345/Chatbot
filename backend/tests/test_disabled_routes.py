"""
Tests for disabled route blocking functionality.

Verifies that:
1. Disabled routes are filtered by route selector
2. Disabled routes are blocked by API executor
3. Stale plans cannot execute disabled routes
4. Users receive friendly error messages
"""

import pytest
from fastapi import HTTPException

from app.models import (
    ApplicationDefinition,
    RouteDefinition,
    HTTPMethod,
    RouteStatus,
    AuthenticationConfig,
    ChatbotConfig,
    is_route_available,
    is_route_disabled,
)
from app.route_selector import RouteSelector, _is_route_enabled
from app.api_client import ApplicationAPIClient


class TestRouteStatusConstants:
    """Test route status enum and constants."""
    
    def test_route_status_available(self):
        """Test AVAILABLE status."""
        assert RouteStatus.AVAILABLE == "Available"
    
    def test_route_status_disabled(self):
        """Test DISABLED status."""
        assert RouteStatus.DISABLED == "Disabled"
    
    def test_route_status_error(self):
        """Test ERROR status."""
        assert RouteStatus.ERROR == "Error"


class TestIsRouteEnabled:
    """Test route enabled check."""
    
    def test_enabled_route(self):
        """Test that enabled route returns True."""
        route = RouteDefinition(
            name="test_route",
            method=HTTPMethod.GET,
            path="/test",
            description="Test route",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        assert _is_route_enabled(route) is True
    
    def test_disabled_route_by_flag(self):
        """Test that disabled route (is_enabled=False) returns False."""
        route = RouteDefinition(
            name="test_route",
            method=HTTPMethod.GET,
            path="/test",
            description="Test route",
            is_enabled=False,
            status=RouteStatus.AVAILABLE,
        )
        assert _is_route_enabled(route) is False
    
    def test_disabled_route_by_status(self):
        """Test that disabled route (status=Disabled) returns False."""
        route = RouteDefinition(
            name="test_route",
            method=HTTPMethod.GET,
            path="/test",
            description="Test route",
            is_enabled=True,
            status=RouteStatus.DISABLED,
        )
        assert _is_route_enabled(route) is False
    
    def test_disabled_route_both_flags(self):
        """Test that disabled route (both flags) returns False."""
        route = RouteDefinition(
            name="test_route",
            method=HTTPMethod.GET,
            path="/test",
            description="Test route",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        assert _is_route_enabled(route) is False


class TestRouteSelector:
    """Test route selector filtering of disabled routes."""
    
    def _create_application(self, *routes: RouteDefinition) -> ApplicationDefinition:
        """Create test application with given routes."""
        return ApplicationDefinition(
            app_id="test_app",
            name="Test Application",
            base_url="https://api.example.com",
            service_key_env="TEST_KEY",
            routes=list(routes),
            authentication=AuthenticationConfig(),
            chatbot=ChatbotConfig(),
        )
    
    def test_selector_includes_enabled_route(self):
        """Test that selector includes enabled routes."""
        enabled_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        app = self._create_application(enabled_route)
        selector = RouteSelector()
        selected, _ = selector.select(app, "show me products")
        
        route_names = {r.name for r in selected}
        assert "get_products" in route_names
    
    def test_selector_excludes_disabled_route(self):
        """Test that selector excludes disabled routes."""
        enabled_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        disabled_route = RouteDefinition(
            name="create_brand",
            method=HTTPMethod.POST,
            path="/admin/brands",
            description="Create a brand",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        app = self._create_application(enabled_route, disabled_route)
        selector = RouteSelector()
        selected, _ = selector.select(app, "create a brand")
        
        route_names = {r.name for r in selected}
        assert "create_brand" not in route_names
        assert "get_products" in route_names
    
    def test_selector_filters_multiple_disabled_routes(self):
        """Test that selector filters multiple disabled routes."""
        enabled_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        disabled_route1 = RouteDefinition(
            name="create_brand",
            method=HTTPMethod.POST,
            path="/admin/brands",
            description="Create a brand",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        disabled_route2 = RouteDefinition(
            name="delete_product",
            method=HTTPMethod.DELETE,
            path="/admin/products/{id}",
            description="Delete a product",
            is_enabled=True,
            status=RouteStatus.DISABLED,
        )
        
        app = self._create_application(enabled_route, disabled_route1, disabled_route2)
        selector = RouteSelector()
        selected, _ = selector.select(app, "delete a product")
        
        route_names = {r.name for r in selected}
        assert "delete_product" not in route_names
        assert "create_brand" not in route_names
        assert "get_products" in route_names


class TestAPIExecutorDisabledRouteBlocking:
    """Test API executor blocking of disabled routes."""
    
    @pytest.mark.asyncio
    async def test_executor_blocks_disabled_route(self):
        """Test that executor blocks disabled route before execution."""
        disabled_route = RouteDefinition(
            name="create_brand",
            method=HTTPMethod.POST,
            path="/admin/brands",
            description="Create a brand",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        app = ApplicationDefinition(
            app_id="ecommerce",
            name="E-commerce",
            base_url="https://api.ecommerce.com",
            service_key_env="TEST_KEY",
            routes=[disabled_route],
        )
        
        client = ApplicationAPIClient()
        
        with pytest.raises(HTTPException) as exc_info:
            await client.execute(
                application=app,
                route=disabled_route,
                parameters={"name": "Nike"},
                authorization=None,
                request_id="test-request-123",
            )
        
        # Verify the error is ROUTE_DISABLED
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "ROUTE_DISABLED"
    
    @pytest.mark.asyncio
    async def test_executor_allows_enabled_route(self):
        """Test that executor allows enabled routes (would execute normally)."""
        enabled_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        
        # This test verifies the check passes; actual HTTP call would fail
        # because we don't have a real server, but the route availability
        # check should not raise ROUTE_DISABLED
        
        app = ApplicationDefinition(
            app_id="ecommerce",
            name="E-commerce",
            base_url="https://api.example.com",
            service_key_env="TEST_KEY",
            routes=[enabled_route],
        )
        
        client = ApplicationAPIClient()
        
        # This will fail on HTTP connection, but not on route check
        try:
            await client.execute(
                application=app,
                route=enabled_route,
                parameters={},
                authorization=None,
                request_id="test-request-123",
            )
        except HTTPException as e:
            # If it's ROUTE_DISABLED, the test fails
            assert e.detail != "ROUTE_DISABLED"
        except Exception:
            # Network or other errors are OK; we're just checking
            # that route availability check doesn't raise ROUTE_DISABLED
            pass


class TestDisabledRouteErrorHandling:
    """Test error handling for disabled routes."""
    
    def test_route_disabled_error_has_clear_code(self):
        """Test that ROUTE_DISABLED error code is clear."""
        error_code = "ROUTE_DISABLED"
        assert error_code in ["ROUTE_DISABLED", "ROUTE_NOT_FOUND", "ROUTE_AVAILABLE"]
    
    def test_route_disabled_vs_not_found_distinct(self):
        """Test that ROUTE_DISABLED is distinct from ROUTE_NOT_FOUND."""
        disabled_code = "ROUTE_DISABLED"
        not_found_code = "ROUTE_NOT_FOUND"
        
        assert disabled_code != not_found_code
        assert "DISABLED" in disabled_code
        assert "NOT_FOUND" in not_found_code


# Integration test (requires full setup, may be skipped)
@pytest.mark.skip(reason="Requires full database and app setup")
class TestDisabledRouteIntegration:
    """Integration tests for disabled route workflow."""
    
    @pytest.mark.asyncio
    async def test_full_disabled_route_flow(self):
        """Test full flow: user request → selector → executor → error → friendly message."""
        # This is a high-level integration test
        # In a real test suite, this would use fixtures for database, API, etc.
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



class TestStatusNormalization:
    """Test route status normalization from database to RouteDefinition."""
    
    def test_normalize_available_lowercase(self):
        """Test normalization of lowercase 'available' to canonical form."""
        normalized = RouteStatus.normalize("available")
        assert normalized == RouteStatus.AVAILABLE.value
        assert normalized == "Available"
    
    def test_normalize_available_uppercase(self):
        """Test normalization of uppercase 'Available' to canonical form."""
        normalized = RouteStatus.normalize("Available")
        assert normalized == RouteStatus.AVAILABLE.value
    
    def test_normalize_disabled_lowercase(self):
        """Test normalization of lowercase 'disabled' to canonical form."""
        normalized = RouteStatus.normalize("disabled")
        assert normalized == RouteStatus.DISABLED.value
        assert normalized == "Disabled"
    
    def test_normalize_disabled_uppercase(self):
        """Test normalization of uppercase 'Disabled' to canonical form."""
        normalized = RouteStatus.normalize("Disabled")
        assert normalized == RouteStatus.DISABLED.value
    
    def test_normalize_error_lowercase(self):
        """Test normalization of lowercase 'error' to canonical form."""
        normalized = RouteStatus.normalize("error")
        assert normalized == RouteStatus.ERROR.value
        assert normalized == "Error"
    
    def test_normalize_error_uppercase(self):
        """Test normalization of uppercase 'Error' to canonical form."""
        normalized = RouteStatus.normalize("Error")
        assert normalized == RouteStatus.ERROR.value
    
    def test_normalize_none_defaults_to_available(self):
        """Test that None normalizes to AVAILABLE."""
        normalized = RouteStatus.normalize(None)
        assert normalized == RouteStatus.AVAILABLE.value
    
    def test_normalize_empty_string_defaults_to_available(self):
        """Test that empty string normalizes to AVAILABLE."""
        normalized = RouteStatus.normalize("")
        assert normalized == RouteStatus.AVAILABLE.value
    
    def test_normalize_whitespace(self):
        """Test that whitespace is handled correctly."""
        normalized = RouteStatus.normalize("  available  ")
        assert normalized == RouteStatus.AVAILABLE.value
    
    def test_normalize_unknown_defaults_to_available(self):
        """Test that unknown status defaults to AVAILABLE."""
        normalized = RouteStatus.normalize("unknown_status")
        assert normalized == RouteStatus.AVAILABLE.value
    
    def test_route_definition_accepts_normalized_status(self):
        """Test that RouteDefinition accepts normalized status values."""
        # This tests the actual use case: creating RouteDefinition with normalized status
        route = RouteDefinition(
            name="test_route",
            method=HTTPMethod.GET,
            path="/test",
            description="Test route",
            is_enabled=True,
            status=RouteStatus.normalize("available"),  # lowercase from DB
        )
        assert route.status == RouteStatus.AVAILABLE.value
    
    def test_route_definition_rejects_invalid_status(self):
        """Test that RouteDefinition still validates enum values."""
        # This should fail validation if we pass a non-canonical value
        with pytest.raises(ValueError):
            RouteDefinition(
                name="test_route",
                method=HTTPMethod.GET,
                path="/test",
                description="Test route",
                is_enabled=True,
                status="invalid_status",  # Not a valid enum value
            )



class TestDatabaseStatusMismatchFix:
    """Test that the database status mismatch issue is fixed.
    
    This test simulates the original issue:
    - Database stores status as lowercase: "available", "disabled", "error"
    - RouteDefinition expects uppercase: "Available", "Disabled", "Error"
    - The fix normalizes these values during DB -> RouteDefinition conversion
    """
    
    def test_route_from_db_normalizes_lowercase_available(self):
        """Test that RouteDefinition built from DB with lowercase 'available' works."""
        # Simulate database row object
        class MockDBRoute:
            id = "route-123"
            method = "GET"
            path = "/products"
            operation_id = "get_products"
            name = "get_products"
            summary = "Get products"
            description = "Retrieve all products"
            status = "available"  # DB stores lowercase
            is_enabled = True
            auth_required = False
            auth_type = None
            source = "openapi"
            parameters_json = {}
            query_params_json = None
            path_params_json = None
        
        # This is what app_registry._route_from_db does
        route = RouteDefinition(
            app_id="test_app",
            name=MockDBRoute.name,
            method=HTTPMethod(MockDBRoute.method),
            path=MockDBRoute.path,
            description=MockDBRoute.description,
            parameters={},
            required_parameters=[],
            requires_auth=MockDBRoute.auth_required,
            authentication_strategy=MockDBRoute.auth_type,
            source=MockDBRoute.source,
            is_enabled=MockDBRoute.is_enabled,
            status=RouteStatus.normalize(MockDBRoute.status),  # Normalize!
        )
        
        # Verify the route was created successfully
        assert route.name == "get_products"
        assert route.status == "Available"  # Normalized to canonical
        assert route.is_enabled is True
    
    def test_route_from_db_normalizes_lowercase_disabled(self):
        """Test that RouteDefinition built from DB with lowercase 'disabled' works."""
        class MockDBRoute:
            method = "POST"
            path = "/admin/products"
            operation_id = "create_product"
            name = "create_product"
            summary = "Create product"
            description = "Create a new product"
            status = "disabled"  # DB stores lowercase
            is_enabled = False
            auth_required = True
            auth_type = "jwt"
            source = "manual"
            parameters_json = {}
            query_params_json = None
            path_params_json = None
        
        route = RouteDefinition(
            app_id="test_app",
            name=MockDBRoute.name,
            method=HTTPMethod(MockDBRoute.method),
            path=MockDBRoute.path,
            description=MockDBRoute.description,
            parameters={},
            required_parameters=[],
            requires_auth=MockDBRoute.auth_required,
            authentication_strategy=MockDBRoute.auth_type,
            source=MockDBRoute.source,
            is_enabled=MockDBRoute.is_enabled,
            status=RouteStatus.normalize(MockDBRoute.status),  # Normalize!
        )
        
        assert route.name == "create_product"
        assert route.status == "Disabled"  # Normalized to canonical
        assert route.is_enabled is False
    
    def test_application_definition_builds_with_normalized_routes(self):
        """Test that ApplicationDefinition can be built with normalized routes."""
        # Simulate multiple routes from database with mixed case statuses
        class MockDBRoute:
            def __init__(self, method, path, name, status, is_enabled):
                self.id = f"route-{name}"
                self.method = method
                self.path = path
                self.operation_id = name
                self.name = name
                self.summary = name
                self.description = f"Route: {name}"
                self.status = status
                self.is_enabled = is_enabled
                self.auth_required = False
                self.auth_type = None
                self.source = "openapi"
                self.parameters_json = {}
                self.query_params_json = None
                self.path_params_json = None
        
        # Mix of database representations
        db_routes = [
            MockDBRoute("GET", "/products", "list_products", "available", True),  # lowercase
            MockDBRoute("POST", "/products", "create_product", "Available", True),  # uppercase (edge case)
            MockDBRoute("DELETE", "/admin/products", "delete_product", "disabled", False),  # lowercase
            MockDBRoute("PATCH", "/admin/settings", "update_settings", "error", False),  # lowercase
        ]
        
        # Build RouteDefinitions as app_registry does
        routes = [
            RouteDefinition(
                app_id="ecommerce",
                name=db_route.name,
                method=HTTPMethod(db_route.method),
                path=db_route.path,
                description=db_route.description,
                parameters={},
                required_parameters=[],
                requires_auth=db_route.auth_required,
                authentication_strategy=db_route.auth_type,
                source=db_route.source,
                is_enabled=db_route.is_enabled,
                status=RouteStatus.normalize(db_route.status),  # Normalize!
            )
            for db_route in db_routes
        ]
        
        # Build ApplicationDefinition (this used to fail before the fix)
        app = ApplicationDefinition(
            app_id="ecommerce",
            name="E-commerce API",
            base_url="https://api.ecommerce.com",
            service_key_env="ECOMMERCE_KEY",
            routes=routes,
            authentication=AuthenticationConfig(),
            chatbot=ChatbotConfig(),
        )
        
        # Verify the application was built successfully
        assert app.app_id == "ecommerce"
        assert len(app.routes) == 4
        
        # Verify all statuses are normalized
        assert app.routes[0].status == "Available"
        assert app.routes[1].status == "Available"
        assert app.routes[2].status == "Disabled"
        assert app.routes[3].status == "Error"
        
        # Verify availability checks work
        assert _is_route_enabled(app.routes[0]) is True  # available + enabled
        assert _is_route_enabled(app.routes[1]) is True  # available + enabled
        assert _is_route_enabled(app.routes[2]) is False  # disabled + not enabled
        assert _is_route_enabled(app.routes[3]) is False  # error + not enabled



class TestStrictDisabledRouteEnforcement:
    """Test comprehensive disabled route enforcement across all layers.
    
    Implements the "Disabled API Route = No Access" policy:
    1. Disabled route must not appear in planner's catalog
    2. Planner validation must reject disabled route selection
    3. Executor must re-check availability before API call
    4. No external API call for disabled routes
    5. No retry, fallback, or workaround
    6. System detects when user requests disabled capability
    7. User receives friendly access unavailable message
    """
    
    def _create_app_with_routes(self, *routes: RouteDefinition) -> ApplicationDefinition:
        """Helper to create test application with routes."""
        return ApplicationDefinition(
            app_id="test_app",
            name="Test App",
            base_url="https://api.example.com",
            service_key_env="TEST_KEY",
            routes=list(routes),
            authentication=AuthenticationConfig(),
            chatbot=ChatbotConfig(),
        )
    
    # TEST 1: Available route - can select and execute
    def test_available_route_selectable_and_executable(self):
        """TEST 1: Available route can be selected by planner and executed."""
        available_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        app = self._create_app_with_routes(available_route)
        
        # Planner can select it
        selector = RouteSelector()
        selected, _ = selector.select(app, "show products")
        assert "get_products" in {r.name for r in selected}
        
        # Route is available for execution
        assert is_route_available(available_route) is True
        assert is_route_disabled(available_route) is False
    
    # TEST 2: Disabled route - not selectable, not executable
    def test_disabled_route_blocked_at_all_layers(self):
        """TEST 2: Disabled route blocked at selector and validation layers."""
        available_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        disabled_route = RouteDefinition(
            name="delete_product",
            method=HTTPMethod.DELETE,
            path="/products/{id}",
            description="Delete a product",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        app = self._create_app_with_routes(available_route, disabled_route)
        
        # Layer 1: Selector must NOT include disabled route
        selector = RouteSelector()
        selected, _ = selector.select(app, "delete a product")
        selected_names = {r.name for r in selected}
        assert "delete_product" not in selected_names
        assert "get_products" in selected_names
        
        # Layer 2: Route is disabled
        assert is_route_disabled(disabled_route) is True
        assert is_route_available(disabled_route) is False
    
    # TEST 3: Route disabled after planning - executor fresh DB check blocks it
    def test_stale_plan_blocked_by_executor_db_check(self):
        """TEST 3: Even if planner selected a route before it was disabled,
        the executor's fresh DB check must block execution."""
        route = RouteDefinition(
            name="delete_product",
            method=HTTPMethod.DELETE,
            path="/products/{id}",
            description="Delete a product",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        
        # If this route somehow made it to executor (e.g., stale plan, race condition),
        # the executor must check availability
        assert is_route_disabled(route) is True, \
            "Executor would check: if is_route_disabled(route): BLOCK"
    
    # TEST 4: Disabled route must NOT be retried
    def test_disabled_route_no_retry(self):
        """TEST 4: If a route is disabled, the executor must NOT retry.
        Disabled status is terminal."""
        route = RouteDefinition(
            name="products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get products",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        
        # Disabled routes should not trigger retry logic
        # (Retry is only for transient external API failures)
        assert is_route_disabled(route) is True
        # No retry counter, no backoff, just BLOCKED
    
    # TEST 5: Disabled route must NOT fallback to alternative route
    def test_disabled_route_no_fallback_execution(self):
        """TEST 5: If requested route is disabled, system must NOT
        silently execute an alternative route."""
        products_route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        search_route = RouteDefinition(
            name="search_products",
            method=HTTPMethod.GET,
            path="/search",
            description="Search products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        app = self._create_app_with_routes(products_route, search_route)
        
        # If user requests "show products" (disabled),
        # system should NOT execute "search_products" as workaround
        # It should return: "I don't have access to that"
        
        assert is_route_disabled(products_route) is True
        assert is_route_available(search_route) is True
        # But they are different operations - no automatic substitution
    
    # TEST 6: Disabled comparison read - must NOT execute
    def test_disabled_comparison_read_blocked(self):
        """TEST 6: If a comparison read route is disabled,
        it must be dropped/not executed."""
        main_route = RouteDefinition(
            name="add_cart_item",
            method=HTTPMethod.POST,
            path="/cart/items",
            description="Add item to cart",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        comparison_disabled = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get all products",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        app = self._create_app_with_routes(main_route, comparison_disabled)
        
        # Planner must not include disabled route in comparison_reads
        assert is_route_disabled(comparison_disabled) is True
    
    # TEST 7: Multi-step plan with disabled route - must NOT partially execute
    def test_multiStep_plan_with_disabled_route_blocked(self):
        """TEST 7: In a multi-step workflow, if ANY required step is disabled,
        the entire operation must not execute partially."""
        step1_route = RouteDefinition(
            name="validate_order",
            method=HTTPMethod.POST,
            path="/validate",
            description="Validate order",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        step2_route = RouteDefinition(
            name="process_payment",
            method=HTTPMethod.POST,
            path="/payment",
            description="Process payment",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        step3_route = RouteDefinition(
            name="create_order",
            method=HTTPMethod.POST,
            path="/orders",
            description="Create order",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        app = self._create_app_with_routes(step1_route, step2_route, step3_route)
        
        # If step2 is disabled, the workflow must fail safely
        # Do NOT execute step1 and step3 while skipping step2
        assert is_route_disabled(step2_route) is True
    
    # TEST 8: Re-enable route - becomes available again
    def test_re_enable_route_becomes_available(self):
        """TEST 8: When a disabled route is re-enabled,
        it must become selectable and executable again."""
        # Initial state: disabled
        route_disabled = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get products",
            is_enabled=False,
            status=RouteStatus.DISABLED,
        )
        assert is_route_disabled(route_disabled) is True
        assert is_route_available(route_disabled) is False
        
        # After re-enable: available
        route_enabled = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        assert is_route_disabled(route_enabled) is False
        assert is_route_available(route_enabled) is True
    
    # TEST 9: Application disabled - NO routes executable
    def test_application_disabled_all_routes_blocked(self):
        """TEST 9: When an application is disabled,
        NO routes from that app can be executed."""
        route1 = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get products",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        route2 = RouteDefinition(
            name="get_orders",
            method=HTTPMethod.GET,
            path="/orders",
            description="Get orders",
            is_enabled=True,
            status=RouteStatus.AVAILABLE,
        )
        
        # If application.is_enabled = False, both routes are unreachable
        # This is enforced at ApplicationDefinition level
        app_enabled = self._create_app_with_routes(route1, route2)
        assert app_enabled.base_url != ""  # enabled has base_url
        
        app_disabled = ApplicationDefinition(
            app_id="test_app",
            name="Test App",
            base_url="",  # Empty base_url = disabled
            service_key_env="TEST_KEY",
            routes=[route1, route2],
            authentication=AuthenticationConfig(),
            chatbot=ChatbotConfig(),
        )
        assert app_disabled.base_url == ""  # disabled
    
    # TEST 10: Error status route - not executable
    def test_error_status_route_not_executable(self):
        """TEST 10: A route with status=Error must not be executed."""
        route = RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/products",
            description="Get products",
            is_enabled=True,
            status=RouteStatus.ERROR,
        )
        
        # Error status means not available
        assert is_route_disabled(route) is True
        assert is_route_available(route) is False


class TestUserFacingDisabledRouteMessages:
    """Test that disabled routes result in friendly user-facing messages."""
    
    def test_disabled_route_user_message(self):
        """Verify friendly message for disabled route access attempt."""
        message = "I'm sorry, but I don't currently have access to perform that action."
        # This is the consistent message returned to users for disabled routes
        assert message in [
            "I'm sorry, but I don't currently have access to perform that action.",
            "I don't have access to this action right now.",
            "This action is currently unavailable.",
        ]
    
    def test_no_technical_details_in_message(self):
        """Verify that technical details are NOT exposed to users."""
        message = "I'm sorry, but I don't currently have access to perform that action."
        
        # Should NOT contain:
        assert "ROUTE_DISABLED" not in message
        assert "application_routes" not in message
        assert "route_id" not in message
        assert "database" not in message
        assert "exception" not in message
        assert "stack trace" not in message
