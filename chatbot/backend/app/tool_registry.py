from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from .api_client import ApplicationAPIClient
from .models import ApplicationDefinition, RouteDefinition


class DynamicToolRegistry:
    """Creates LangChain tools from application-supplied route contracts."""

    def __init__(self, api_client: ApplicationAPIClient) -> None:
        self.api_client = api_client

    def build(self, *, application: ApplicationDefinition, authorization: str | None, request_id: str) -> dict[str, StructuredTool]:
        return {route.name: self._tool_for(application, route, authorization, request_id) for route in application.routes}

    def _tool_for(self, application: ApplicationDefinition, route: RouteDefinition, authorization: str | None, request_id: str) -> StructuredTool:
        fields = {name: (Any | None, Field(default=None, description=description)) for name, description in route.parameters.items()}
        args_schema = create_model(f"{application.app_id}_{route.name}_args", **fields)

        async def invoke(**parameters: Any) -> Any:
            return await self.api_client.execute(application=application, route=route, parameters=parameters, authorization=authorization, request_id=request_id)

        return StructuredTool.from_function(coroutine=invoke, name=f"{application.app_id}_{route.name}", description=route.description, args_schema=args_schema)
