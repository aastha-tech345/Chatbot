"""
Tests for OpenAPI discovery and route conversion.

Tests cover:
1. Successful OpenAPI fetching and parsing
2. HTTP failure handling
3. Invalid JSON handling
4. Path parameter discovery
5. Query parameter discovery
6. Request body schema discovery
7. operationId handling and generation
8. Visibility and authentication inference
9. Multiple applications with independent discovery
10. Dynamic route registration in ApplicationRegistry
"""

from __future__ import annotations

import asyncio
import json
import sys
from unittest import mock

import httpx
import pytest

sys.path.insert(0, "chatbot/backend")

from app.app_registry import ApplicationRegistry
from app.models import ApplicationDefinition, HTTPMethod, RouteDefinition
from app.openapi_discovery import (
    OpenAPIDiscovery,
    _extract_operation_visibility,
    _extract_parameter_info,
    _generate_operation_id,
    discover_openapi_routes,
)


class TestOperationIdGeneration:
    """Test operation ID generation from method and path."""

    def test_generate_from_simple_path(self):
        """Generate operation ID from simple path."""
        operation_id = _generate_operation_id("get", "/api/v1/products")
        assert operation_id == "get_api_v1_products"

    def test_generate_from_path_with_parameters(self):
        """Generate operation ID from path with path parameters."""
        operation_id = _generate_operation_id("get", "/api/v1/products/{slug}")
        assert operation_id == "get_api_v1_products_slug"

    def test_generate_from_nested_path(self):
        """Generate operation ID from nested path."""
        operation_id = _generate_operation_id("post", "/api/v1/cart/items")
        assert operation_id == "post_api_v1_cart_items"

    def test_generate_removes_consecutive_underscores(self):
        """Generated IDs don't have consecutive underscores."""
        operation_id = _generate_operation_id("put", "/api/v1/orders/{order_id}/items/{item_id}")
        assert "__" not in operation_id

    def test_generate_handles_hyphens(self):
        """Hyphens in paths are converted to underscores."""
        operation_id = _generate_operation_id("get", "/api/v1/orders/unread-count")
        assert operation_id == "get_api_v1_orders_unread_count"


class TestParameterExtraction:
    """Test parameter extraction from OpenAPI definitions."""

    def test_extract_path_parameters(self):
        """Extract path parameters from OpenAPI parameter list."""
        parameters = [
            {"name": "product_id", "in": "path", "description": "Product ID", "required": True}
        ]
        params_dict, required = _extract_parameter_info(parameters, None)
        assert "product_id" in params_dict
        assert "product_id" in required

    def test_extract_query_parameters(self):
        """Extract query parameters from OpenAPI parameter list."""
        parameters = [
            {"name": "q", "in": "query", "description": "Search query"},
            {"name": "sort", "in": "query", "description": "Sort order"},
        ]
        params_dict, required = _extract_parameter_info(parameters, None)
        assert "q" in params_dict
        assert "sort" in params_dict
        assert len(required) == 0  # Query params typically not required

    def test_extract_request_body_parameters(self):
        """Extract parameters from JSON request body schema."""
        request_body = {
            "content": {
                "application/json": {
                    "schema": {
                        "properties": {
                            "product_id": {"description": "Product ID"},
                            "quantity": {"description": "Quantity"},
                        },
                        "required": ["product_id", "quantity"],
                    }
                }
            }
        }
        params_dict, required = _extract_parameter_info(None, request_body)
        assert "product_id" in params_dict
        assert "quantity" in params_dict
        assert set(required) == {"product_id", "quantity"}

    def test_extract_combined_parameters(self):
        """Extract both query and body parameters."""
        parameters = [
            {"name": "limit", "in": "query", "description": "Limit results"},
        ]
        request_body = {
            "content": {
                "application/json": {
                    "schema": {
                        "properties": {
                            "name": {"description": "Item name"},
                        },
                        "required": ["name"],
                    }
                }
            }
        }
        params_dict, required = _extract_parameter_info(parameters, request_body)
        assert "limit" in params_dict
        assert "name" in params_dict
        assert "name" in required

    def test_skip_header_parameters(self):
        """Header parameters are skipped."""
        parameters = [
            {"name": "X-API-Key", "in": "header", "description": "API Key"},
        ]
        params_dict, required = _extract_parameter_info(parameters, None)
        assert "X-API-Key" not in params_dict


class TestOperationVisibility:
    """Test visibility and authentication inference from operations."""

    def test_public_operation_from_tags(self):
        """Public operations are identified from tags."""
        operation = {"tags": ["public"]}
        visibility, requires_auth, requires_user_context = _extract_operation_visibility(operation)
        assert visibility == "public"
        assert requires_auth is False

    def test_private_operation_by_default(self):
        """Operations are private by default."""
        operation = {}
        visibility, requires_auth, requires_user_context = _extract_operation_visibility(operation)
        assert visibility == "private"
        assert requires_auth is True

    def test_no_security_makes_public(self):
        """Operations with no security requirements are public."""
        operation = {"security": []}
        visibility, requires_auth, requires_user_context = _extract_operation_visibility(operation)
        assert visibility == "public"
        assert requires_auth is False

    def test_user_context_from_path(self):
        """User context is required for user-specific endpoints."""
        operation = {"path": "/api/v1/me/profile"}
        visibility, requires_auth, requires_user_context = _extract_operation_visibility(operation)
        assert requires_user_context is True

        operation = {"path": "/api/v1/users/{id}/addresses"}
        visibility, requires_auth, requires_user_context = _extract_operation_visibility(operation)
        assert requires_user_context is True


class TestOpenAPIDiscovery:
    """Test the OpenAPIDiscovery component."""

    def test_discover_simple_operations(self):
        """Discover and convert simple OpenAPI operations."""
        openapi_schema = {
            "openapi": "3.0.0",
            "paths": {
                "/api/v1/products": {
                    "get": {
                        "operationId": "list_products",
                        "summary": "List products",
                        "description": "Get a list of all products",
                        "tags": ["public"],
                        "security": [],
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "description": "Search query",
                            }
                        ],
                    }
                },
                "/api/v1/products/{slug}": {
                    "get": {
                        "operationId": "get_product",
                        "summary": "Get product",
                        "description": "Get detailed product information",
                        "tags": ["public"],
                        "security": [],
                        "parameters": [
                            {
                                "name": "slug",
                                "in": "path",
                                "description": "Product slug",
                                "required": True,
                            }
                        ],
                    }
                },
            }
        }

        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_schema
            mock_get.return_value = mock_response

            import asyncio
            routes = asyncio.run(
                discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
            )

        assert len(routes) == 2
        
        # Check first route
        route1 = routes[0]
        assert route1.name == "list_products"
        assert route1.method == HTTPMethod.GET
        assert route1.path == "/api/v1/products"
        assert route1.visibility == "public"
        assert route1.requires_auth is False
        assert "q" in route1.parameters

        # Check second route
        route2 = routes[1]
        assert route2.name == "get_product"
        assert route2.method == HTTPMethod.GET
        assert route2.path == "/api/v1/products/{slug}"
        assert "slug" in route2.parameters
        assert "slug" in route2.required_parameters

    def test_discover_generates_operation_id_if_missing(self):
        """Generate operation ID if not provided in OpenAPI."""
        openapi_schema = {
            "openapi": "3.0.0",
            "paths": {
                "/api/v1/cart": {
                    "get": {
                        "summary": "Get cart",
                        "description": "Retrieve shopping cart",
                        "security": [{"bearer": []}],
                    }
                }
            }
        }

        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_schema
            mock_get.return_value = mock_response

            import asyncio
            routes = asyncio.run(
                discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
            )

        assert len(routes) == 1
        assert routes[0].name == "get_api_v1_cart"

    def test_discover_post_with_body(self):
        """Discover POST operations with request body schema."""
        openapi_schema = {
            "openapi": "3.0.0",
            "paths": {
                "/api/v1/cart/items": {
                    "post": {
                        "operationId": "add_to_cart",
                        "summary": "Add to cart",
                        "security": [{"bearer": []}],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "product_id": {"type": "string", "description": "Product ID"},
                                            "quantity": {"type": "integer", "description": "Quantity"},
                                        },
                                        "required": ["product_id", "quantity"],
                                    }
                                }
                            },
                        },
                    }
                }
            }
        }

        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_schema
            mock_get.return_value = mock_response

            import asyncio
            routes = asyncio.run(
                discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
            )

        assert len(routes) == 1
        route = routes[0]
        assert route.name == "add_to_cart"
        assert route.method == HTTPMethod.POST
        assert "product_id" in route.parameters
        assert "quantity" in route.parameters
        assert set(route.required_parameters) == {"product_id", "quantity"}

    def test_discover_handles_http_errors(self):
        """Handle HTTP errors during OpenAPI fetch."""
        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")

            import asyncio
            with pytest.raises(RuntimeError) as exc_info:
                asyncio.run(
                    discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
                )
            
            assert "Cannot fetch OpenAPI schema" in str(exc_info.value)

    def test_discover_handles_non_200_status(self):
        """Handle non-200 status codes."""
        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            import asyncio
            with pytest.raises(RuntimeError) as exc_info:
                asyncio.run(
                    discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
                )
            
            assert "status 404" in str(exc_info.value)

    def test_discover_handles_invalid_json(self):
        """Handle invalid JSON in OpenAPI response."""
        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response

            import asyncio
            with pytest.raises(RuntimeError) as exc_info:
                asyncio.run(
                    discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
                )
            
            assert "Invalid OpenAPI JSON" in str(exc_info.value)

    def test_discover_multiple_methods(self):
        """Discover multiple HTTP methods on same path."""
        openapi_schema = {
            "openapi": "3.0.0",
            "paths": {
                "/api/v1/cart/items/{variant_id}": {
                    "get": {
                        "operationId": "get_cart_item",
                        "summary": "Get cart item",
                        "security": [{"bearer": []}],
                    },
                    "put": {
                        "operationId": "update_cart_item",
                        "summary": "Update cart item",
                        "security": [{"bearer": []}],
                        "parameters": [
                            {
                                "name": "variant_id",
                                "in": "path",
                                "required": True,
                            }
                        ],
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "quantity": {"type": "integer"},
                                        },
                                        "required": ["quantity"],
                                    }
                                }
                            }
                        },
                    },
                }
            }
        }

        discovery = OpenAPIDiscovery()
        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_schema
            mock_get.return_value = mock_response

            import asyncio
            routes = asyncio.run(
                discovery.discover("ecommerce", "http://localhost:9001", "http://localhost:9001/api/v1/openapi.json")
            )

        assert len(routes) == 2
        methods = {route.method for route in routes}
        assert methods == {HTTPMethod.GET, HTTPMethod.PUT}


class TestApplicationRegistryDynamicDiscovery:
    """Test ApplicationRegistry integration with OpenAPI discovery."""

    def test_registry_discovers_dynamic_applications(self, tmp_path):
        """Registry discovers routes for dynamic applications on load."""
        apps_json = tmp_path / "applications.json"
        apps_json.write_text(json.dumps({
            "applications": [
                {
                    "app_id": "ecommerce",
                    "name": "E-commerce",
                    "base_url": "http://localhost:9001",
                    "jwt_secret_env": "JWT_SECRET",
                    "service_key_env": "SERVICE_KEY",
                    "openapi_url": "http://localhost:9001/api/v1/openapi.json",
                    "discovery_mode": "dynamic",
                    "routes": [],
                }
            ]
        }))

        openapi_schema = {
            "openapi": "3.0.0",
            "paths": {
                "/api/v1/products": {
                    "get": {
                        "operationId": "list_products",
                        "tags": ["public"],
                        "security": [],
                    }
                }
            }
        }

        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_schema
            mock_get.return_value = mock_response

            registry = ApplicationRegistry(registry_path=apps_json)

        app = registry.get("ecommerce")
        assert len(app.routes) == 1
        assert app.routes[0].name == "list_products"

    def test_registry_preserves_static_routes(self, tmp_path):
        """Registry preserves static routes for non-dynamic applications."""
        apps_json = tmp_path / "applications.json"
        apps_json.write_text(json.dumps({
            "applications": [
                {
                    "app_id": "his",
                    "name": "HIS",
                    "base_url": "http://localhost:3333",
                    "jwt_secret_env": "JWT_SECRET",
                    "service_key_env": "SERVICE_KEY",
                    "discovery_mode": "static",
                    "routes": [
                        {
                            "name": "list_patients",
                            "method": "GET",
                            "path": "/api/v1/patients",
                            "description": "List patients",
                            "visibility": "private",
                            "requires_auth": True,
                        }
                    ],
                }
            ]
        }))

        registry = ApplicationRegistry(registry_path=apps_json)
        app = registry.get("his")
        assert len(app.routes) == 1
        assert app.routes[0].name == "list_patients"

    def test_registry_handles_discovery_failure(self, tmp_path, caplog):
        """Registry handles OpenAPI discovery failures gracefully."""
        apps_json = tmp_path / "applications.json"
        apps_json.write_text(json.dumps({
            "applications": [
                {
                    "app_id": "ecommerce",
                    "name": "E-commerce",
                    "base_url": "http://localhost:9001",
                    "jwt_secret_env": "JWT_SECRET",
                    "service_key_env": "SERVICE_KEY",
                    "openapi_url": "http://localhost:9001/api/v1/openapi.json",
                    "discovery_mode": "dynamic",
                    "routes": [],
                }
            ]
        }))

        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")

            registry = ApplicationRegistry(registry_path=apps_json)

        app = registry.get("ecommerce")
        assert len(app.routes) == 0
        assert "OpenAPI discovery failed" in caplog.text


class TestDynamicToolGeneration:
    """Test that discovered routes generate proper LangChain tools."""

    def test_discovered_routes_create_tools(self, tmp_path):
        """Discovered routes can be converted to LangChain tools."""
        from app.api_client import ApplicationAPIClient
        from app.tool_registry import DynamicToolRegistry

        apps_json = tmp_path / "applications.json"
        apps_json.write_text(json.dumps({
            "applications": [
                {
                    "app_id": "ecommerce",
                    "name": "E-commerce",
                    "base_url": "http://localhost:9001",
                    "jwt_secret_env": "JWT_SECRET",
                    "service_key_env": "SERVICE_KEY",
                    "openapi_url": "http://localhost:9001/api/v1/openapi.json",
                    "discovery_mode": "dynamic",
                    "routes": [],
                }
            ]
        }))

        openapi_schema = {
            "openapi": "3.0.0",
            "paths": {
                "/api/v1/products": {
                    "get": {
                        "operationId": "list_products",
                        "summary": "List products",
                        "tags": ["public"],
                        "security": [],
                        "parameters": [
                            {"name": "q", "in": "query", "description": "Search query"}
                        ],
                    }
                }
            }
        }

        with mock.patch("httpx.AsyncClient.get") as mock_get:
            mock_response = mock.AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_schema
            mock_get.return_value = mock_response

            registry = ApplicationRegistry(registry_path=apps_json)

        app = registry.get("ecommerce")
        api_client = ApplicationAPIClient()
        tool_registry = DynamicToolRegistry(api_client)
        tools = tool_registry.build(application=app, authorization=None, request_id="test")

        assert "ecommerce_list_products" in tools
        tool = tools["ecommerce_list_products"]
        assert tool.name == "ecommerce_list_products"
        assert tool.description == "List products"
