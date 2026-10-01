# Disabled Routes Implementation Guide

## Overview

The Master Chatbot now enforces disabled route blocking at multiple layers to ensure that routes marked as disabled in the App Registry can never be executed by the chatbot.

## Architecture

### Two-Layer Protection

**Layer 1: Route Planner (Prevention)**
- Route selector filters out disabled routes before sending to LLM
- LLM never sees disabled routes as executable options
- Located in: `app/route_selector.py`

**Layer 2: API Executor (Enforcement)**
- Before executing any route, executor performs fresh database availability check
- Even if a stale plan somehow contains a disabled route, it will be blocked
- Located in: `app/api_client.py`

## Flow Diagram

```
User Message
    ↓
Route Selector.select()
    ├─ Filter admin routes
    ├─ Filter disabled routes (is_enabled=False OR status="Disabled")
    ├─ Score by relevance
    └─ Return only enabled routes to LLM
    ↓
LLM Planner (receives only enabled routes)
    ├─ Never sees disabled routes
    ├─ Generates plan
    └─ Returns route_name + parameters
    ↓
API Executor.execute()
    ├─ Route availability check:
    │  ├─ Check route.is_enabled
    │  ├─ Check route.status == "Available"
    │  └─ If disabled → raise ROUTE_DISABLED error
    │
    ├─ If enabled → proceed with execution
    ├─ Authenticate user if required
    ├─ Forward user token
    └─ Return response
    ↓
Response rendered to user
```

## Implementation Details

### 1. RouteStatus Enum (models.py)

```python
class RouteStatus(str, Enum):
    AVAILABLE = "Available"
    DISABLED = "Disabled"
    ERROR = "Error"

class RouteErrorCode(str, Enum):
    ROUTE_AVAILABLE = "ROUTE_AVAILABLE"
    ROUTE_DISABLED = "ROUTE_DISABLED"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    # ... other codes
```

### 2. RouteDefinition Model (models.py)

Added fields to track route state:

```python
class RouteDefinition(BaseModel):
    # ... existing fields ...
    is_enabled: bool = True
    status: RouteStatus = RouteStatus.AVAILABLE
```

### 3. Route Selection Filtering (route_selector.py)

```python
def _is_route_enabled(route: RouteDefinition) -> bool:
    """Return True if route is enabled and available for use."""
    return route.is_enabled and route.status == "Available"

# In select() method:
customer_routes = [
    r for r in all_routes 
    if not _is_admin_route(r) and _is_route_enabled(r)
]
```

### 4. Route Availability Check (api_client.py)

```python
async def execute(
    self,
    *,
    application: ApplicationDefinition,
    route: RouteDefinition,
    parameters: dict[str, Any],
    authorization: str | None,
    request_id: str,
) -> Any:
    # ─────────────────────────────────────────────────────────────────────
    # Route availability check (Layer 2 of protection against disabled routes)
    # ─────────────────────────────────────────────────────────────────────
    if not route.is_enabled or route.status == "Disabled":
        logger.warning(
            "[ROUTE_GUARD] application=%s route=%s status=%s is_enabled=%s action=blocked",
            application.app_id, route.name, route.status, route.is_enabled
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ROUTE_DISABLED",
        )
    # ... rest of execution ...
```

### 5. Database Mapping (app_registry.py)

```python
def _route_from_db(self, app_id: str, route: Any) -> RouteDefinition:
    # ... existing code ...
    return RouteDefinition(
        # ... existing fields ...
        is_enabled=bool(getattr(route, "is_enabled", True)),
        status=getattr(route, "status", "Available") or "Available",
    )
```

## Error Responses

### When a Disabled Route is Encountered

**HTTP Response:**
```
Status: 400 Bad Request
Body: {
    "detail": "ROUTE_DISABLED"
}
```

**Workflow Response to User:**
```
Chatbot: "I'm sorry, but I don't currently have access to perform that action."
```

### Logging

```
[ROUTE_GUARD] application=ecommerce route=POST /api/v1/admin/brands status=Disabled is_enabled=False action=blocked
```

## Database Schema

### application_routes table

```sql
CREATE TABLE application_routes (
    ...
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(20) NOT NULL DEFAULT 'Available',  -- 'Available', 'Disabled', 'Error'
    ...
);

CREATE INDEX ix_app_routes_is_enabled ON application_routes(is_enabled);
CREATE INDEX ix_app_routes_status ON application_routes(status);
```

### Disabling a Route

```sql
UPDATE application_routes
SET is_enabled = FALSE, status = 'Disabled'
WHERE application_id = '...' AND method = 'POST' AND path = '/api/v1/admin/brands';
```

### Re-enabling a Route

```sql
UPDATE application_routes
SET is_enabled = TRUE, status = 'Available'
WHERE application_id = '...' AND method = 'POST' AND path = '/api/v1/admin/brands';
```

## Frontend Integration

The App Registry UI should display:
- ✅ Available (green badge)
- ❌ Disabled (red/orange badge)
- ⚠️  Error (yellow badge)

Users can toggle `is_enabled` for any route, which takes effect immediately without requiring app restart.

## Testing Scenarios

### Test 1: Disabled Route Blocked by Selector

```
1. Route: POST /api/v1/admin/brands, status=Disabled
2. User: "Create a new brand"
3. Route selector: Does not include this route in LLM options
4. LLM: Selects a different route or clarifies
5. Result: Brand creation never attempted
```

### Test 2: Disabled Route Blocked by Executor

```
1. Route: POST /api/v1/admin/brands, status=Disabled
2. Stale cache contains this route
3. LLM selects it (assuming cached data)
4. API Executor fresh DB check: route.is_enabled = FALSE
5. Executor: Raises ROUTE_DISABLED error
6. Result: External API never called
```

### Test 3: Enabled Route Executes Normally

```
1. Route: POST /api/v1/admin/brands, status=Available, is_enabled=True
2. User: "Create a new brand"
3. Route selector: Includes this route
4. LLM: Selects this route
5. Executor: Checks availability ✓, executes
6. Result: Brand created via external API
```

### Test 4: User Sees Friendly Message

```
1. User: "Create a new brand"
2. Required route (POST /api/v1/admin/brands) is disabled
3. Workflow: Detects ROUTE_DISABLED error
4. Response to user: "I'm sorry, but I don't have access to create brands."
5. Result: No technical details exposed
```

## Backward Compatibility

- Existing routes default to `is_enabled=True, status='Available'`
- No changes required to existing working routes
- Disabled route filtering is automatic and invisible to users
- Error code "ROUTE_DISABLED" is internal; users see friendly messages

## Performance Notes

- Route filtering happens at selection time (low cost)
- Executor check is one database query or in-memory enum check (negligible)
- No significant performance impact
- Disabled routes never reach external APIs

## Migration Path

1. Deploy this code to a staging environment
2. Test with existing applications (routes will be enabled by default)
3. Verify that enabling/disabling routes works as expected
4. Deploy to production
5. Start using the disable feature for admin routes in App Registry UI

## Troubleshooting

### Route is disabled but still being used

Check:
1. Did you deploy the latest code?
2. Is the route status in the database actually "Disabled"?
3. Is the route selector reading from the database?
4. Try clearing any route caches

### User cannot access a route that should be enabled

Check:
1. Verify `is_enabled = TRUE` in database
2. Verify `status = 'Available'` in database
3. Check if it's an admin route (filtered by prefix)
4. Check logs for [ROUTE_GUARD] messages

### Error: "ROUTE_DISABLED" in response

This is expected behavior. The chatbot detected that the user's request required a disabled route and blocked the execution. This error should be caught by the response handler and converted to a friendly user message.

## Future Enhancements

1. **Gradual rollout**: Support deploying routes in "Beta" status before full availability
2. **Rate limiting**: Integrate with disabled routes to enforce resource limits
3. **Scheduled disabling**: Automatically disable routes at specific times
4. **User-level permissions**: Disable routes for specific user types
5. **Audit trail**: Track who disabled routes and when
