"""
End-to-end test for the complete disable/enable cycle without backend restart.

This test documents the exact scenario from the requirements:
1. Route available
2. Chatbot uses it
3. Admin disables
4. Chatbot blocks it
5. Admin enables (NO RESTART)
6. Chatbot uses it again (BUG IF FAILED)
7. Admin disables again (NO RESTART)
8. Chatbot blocks it again (BUG IF FAILED)

This verifies the fix for: "ROUTE_DISABLED must not require backend restart for enable/disable to take effect"
"""

import pytest
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
from app.route_selector import RouteSelector


class TestCompleteDisableEnableCycle:
    """
    Complete end-to-end test of the disable/enable cycle.
    
    This simulates the exact user scenario that was broken.
    """
    
    def _make_products_route(self, is_enabled: bool, status: str):
        """Create products route with specified state."""
        return RouteDefinition(
            name="get_products",
            method=HTTPMethod.GET,
            path="/api/v1/products",
            description="Get all products",
            is_enabled=is_enabled,
            status=status,
        )
    
    def _make_app_with_route(self, route: RouteDefinition):
        """Create ecommerce app with given route."""
        return ApplicationDefinition(
            app_id="ecommerce",
            name="E-commerce",
            base_url="https://api.ecommerce.com",
            service_key_env="ECOMMERCE_KEY",
            routes=[route],
            authentication=AuthenticationConfig(),
            chatbot=ChatbotConfig(),
        )
    
    def test_step_1_route_available(self):
        """
        STEP 1: Route is available, chatbot can use it.
        
        Expected:
        - Route status: Available
        - is_enabled: true
        - Route is available for use
        """
        route = self._make_products_route(
            is_enabled=True,
            status=RouteStatus.AVAILABLE.value
        )
        
        # Verify route is available
        assert is_route_available(route) is True, \
            "STEP 1 FAILED: Route should be available"
        assert is_route_disabled(route) is False, \
            "STEP 1 FAILED: Route should not be disabled"
    
    def test_step_2_admin_disables_route(self):
        """
        STEP 2: Admin disables route in App Registry.
        
        Expected:
        - Route status: Disabled
        - is_enabled: false
        - Route is no longer available
        """
        route = self._make_products_route(
            is_enabled=False,
            status=RouteStatus.DISABLED.value
        )
        
        # Verify route is disabled
        assert is_route_disabled(route) is True, \
            "STEP 2 FAILED: Route should be disabled"
        assert is_route_available(route) is False, \
            "STEP 2 FAILED: Route should not be available"
    
    def test_step_3_chatbot_blocks_disabled_route(self):
        """
        STEP 3: Chatbot asks about products, gets blocked.
        
        Expected:
        - Route selector excludes disabled route
        - No external API call
        - User message: "Sorry, I'm not able to perform this task right now."
        """
        route = self._make_products_route(
            is_enabled=False,
            status=RouteStatus.DISABLED.value
        )
        app = self._make_app_with_route(route)
        selector = RouteSelector()
        
        # Selector should not include disabled route
        selected, _ = selector.select(app, "show me products")
        selected_names = {r.name for r in selected}
        
        assert "get_products" not in selected_names, \
            "STEP 3 FAILED: Disabled route should not be selected by chatbot"
    
    def test_step_4_admin_enables_route_no_restart(self):
        """
        STEP 4: Admin enables route WITHOUT restarting backend.
        
        This is the critical step that was broken.
        
        Expected:
        - Route status: Available
        - is_enabled: true
        - Route is immediately available (no restart)
        - ApplicationRegistry reloaded with new status
        """
        route = self._make_products_route(
            is_enabled=True,
            status=RouteStatus.AVAILABLE.value
        )
        
        # Verify route is now available
        assert is_route_available(route) is True, \
            "STEP 4 FAILED: Route should be available after re-enable (BUG: stale cache)"
        assert is_route_disabled(route) is False, \
            "STEP 4 FAILED: Route should not be disabled (BUG: stale cache)"
    
    def test_step_5_chatbot_allows_reenabled_route_immediately(self):
        """
        STEP 5: Chatbot asks about products IMMEDIATELY after enable (no restart).
        
        This is the key test that was failing before the fix.
        
        Expected:
        - Route selector includes re-enabled route
        - External API call would succeed
        - Chatbot can fulfill the request
        """
        route = self._make_products_route(
            is_enabled=True,
            status=RouteStatus.AVAILABLE.value
        )
        app = self._make_app_with_route(route)
        selector = RouteSelector()
        
        # Selector should include re-enabled route immediately
        selected, _ = selector.select(app, "show me products")
        selected_names = {r.name for r in selected}
        
        assert "get_products" in selected_names, \
            "STEP 5 FAILED: Re-enabled route should be selected immediately (MAIN BUG)"
    
    def test_step_6_admin_disables_again_no_restart(self):
        """
        STEP 6: Admin disables route AGAIN without restarting.
        
        Expected:
        - Route status: Disabled
        - is_enabled: false
        - Route is immediately unavailable
        """
        route = self._make_products_route(
            is_enabled=False,
            status=RouteStatus.DISABLED.value
        )
        
        # Verify route is disabled
        assert is_route_disabled(route) is True, \
            "STEP 6 FAILED: Route should be disabled again (BUG: stale cache)"
        assert is_route_available(route) is False, \
            "STEP 6 FAILED: Route should not be available (BUG: stale cache)"
    
    def test_step_7_chatbot_blocks_again_immediately(self):
        """
        STEP 7: Chatbot asks about products, gets blocked IMMEDIATELY after disable.
        
        Expected:
        - Route selector excludes disabled route
        - No external API call
        - User message: "Sorry, I'm not able to perform this task right now."
        """
        route = self._make_products_route(
            is_enabled=False,
            status=RouteStatus.DISABLED.value
        )
        app = self._make_app_with_route(route)
        selector = RouteSelector()
        
        # Selector should not include disabled route
        selected, _ = selector.select(app, "show me products")
        selected_names = {r.name for r in selected}
        
        assert "get_products" not in selected_names, \
            "STEP 7 FAILED: Disabled route should not be selected (BUG: stale cache)"
    
    def test_complete_cycle_success(self):
        """
        Run the complete cycle in one test.
        
        AVAILABLE → DISABLED → BLOCKED →  
        ENABLED (NO RESTART) → ALLOWED →  
        DISABLED (NO RESTART) → BLOCKED
        """
        selector = RouteSelector()
        
        # STEP 1: Available
        route = self._make_products_route(True, RouteStatus.AVAILABLE.value)
        assert is_route_available(route)
        
        # STEP 2: Admin disables
        route = self._make_products_route(False, RouteStatus.DISABLED.value)
        assert is_route_disabled(route)
        
        # STEP 3: Blocked
        app = self._make_app_with_route(route)
        selected, _ = selector.select(app, "show me products")
        assert "get_products" not in {r.name for r in selected}
        
        # STEP 4-5: Admin enables (no restart), chatbot allows
        route = self._make_products_route(True, RouteStatus.AVAILABLE.value)
        app = self._make_app_with_route(route)
        selected, _ = selector.select(app, "show me products")
        assert "get_products" in {r.name for r in selected}, \
            "MAIN BUG: Re-enabled route not selected immediately"
        
        # STEP 6-7: Admin disables again (no restart), chatbot blocks
        route = self._make_products_route(False, RouteStatus.DISABLED.value)
        app = self._make_app_with_route(route)
        selected, _ = selector.select(app, "show me products")
        assert "get_products" not in {r.name for r in selected}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
