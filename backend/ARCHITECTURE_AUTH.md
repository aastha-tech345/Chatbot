# Authentication Architecture

## Principle

**User access tokens are request-scoped and MUST NOT be stored as application credentials.**

The Master Chatbot receives the user's authorization header in each incoming request and uses it to execute the appropriate API routes. The user token remains in memory for the duration of that request and is never persisted.

## Request Flow

```
1. User makes a chatbot request:
   POST /api/v1/chat
   Authorization: Bearer <user-access-token>
   {
     "app_id": "ecommerce",
     "message": "Show my cart"
   }

2. Master Chatbot receives the request and extracts:
   - Authorization header (request-scoped user token)
   - Message and app_id from body

3. Master resolves the application from the database:
   applications table → ApplicationDefinition

4. Master loads application routes from the database:
   application_routes table → List[RouteDefinition]

5. Planner selects the best route:
   → route.protected = True if auth_required or requires_user_context
   → route.authentication_strategy indicates token type

6. API Executor receives:
   - application: ApplicationDefinition (from DB)
   - route: RouteDefinition (from DB)
   - authorization: str (request-scoped user token from Authorization header)
   - parameters: dict (from planner)

7. API Executor builds request headers:
   if route.protected and authorization:
       headers["Authorization"] = authorization

8. API Executor forwards request to Ecommerce API:
   GET /api/cart
   Authorization: Bearer <user-access-token>
   (Same token as from step 1)

9. Ecommerce API validates the JWT using its own secret
   (Master does NOT need the Ecommerce JWT secret)

10. Response flows back to user
```

## Storage Boundaries

### ✅ Store in Database (application_credentials table)

- Application-level service credentials (Master ↔ Ecommerce integration)
- API keys for the application itself
- OAuth2 refresh tokens issued to the application (not to users)
- Service-to-service authentication tokens

Example:
```
auth_type: "service_key"
bearer_token_encrypted: "<Master-to-Ecommerce service credential>"
```

### ❌ NEVER Store

- User access tokens
- User JWT tokens
- User refresh tokens
- User session tokens
- Authorization headers from incoming requests
- Ecommerce JWT secrets
- Ecommerce JWT algorithms

These remain **request-scoped** only.

## Code Points

### API Client (api_client.py)

```python
async def execute(
    self,
    *,
    application: ApplicationDefinition,
    route: RouteDefinition,
    parameters: dict[str, Any],
    authorization: str | None,  # ← Request-scoped user token
    request_id: str,
) -> Any:
    if route.protected and not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")

    headers: dict[str, str] = {"X-Request-Id": request_id}
    if route.protected and authorization:
        headers["Authorization"] = authorization  # ← Forward user token
    
    # Make request to application
    response = await client.request(
        route.method.value,
        target_url,
        headers=headers,
        # ... other params
    )
```

**Key point:** No bearer token lookup from application_credentials. Authorization comes from the incoming request only.

### Workflow (workflow.py)

```python
async def _execute(self, state: ChatState) -> ChatState:
    # ...
    tools = self.tool_registry.build(
        application=application,
        authorization=state.get("authorization"),  # ← From incoming request
        request_id=state["request_id"],
    )
```

**Key point:** Authorization is sourced from the ChatState, which gets it from the HTTP Authorization header in main.py.

### Route Definition (models.py)

```python
class RouteDefinition(BaseModel):
    requires_auth: bool = True
    requires_user_context: bool = False
    allowed_roles: list[str] = []
    authentication_strategy: str | None = None  # "bearer", "api_key", etc.
    
    @property
    def protected(self) -> bool:
        return (
            self.visibility != "public" or
            self.requires_auth or
            self.requires_user_context or
            bool(self.allowed_roles)
        )
```

**Key point:** Routes track auth requirements as metadata. Execution uses the request-scoped token.

## Frontend (Application Form)

The application registration form collects:

✅ Required:
- Application Name
- App ID
- Base URL
- OpenAPI URL (optional)

✅ Optional (for application-level service credentials):
- Authentication Type (if the application requires Master-to-App auth)
- API Key (if applicable)
- Service Key (if applicable)

❌ Never ask for:
- Bearer Token (user tokens are request-scoped)
- User API Keys
- User credentials
- User session tokens

## Environment Variables

Master reads from its own environment:

```bash
# Master's own config
SERVICE_KEY_ENV=<Master service key for inter-service auth>
JWT_SECRET_ENV=<Master's JWT secret for admin tokens>

# Each registered application provides:
BASE_URL=https://api.ecommerce.com
OPENAPI_URL=https://api.ecommerce.com/openapi.json

# Ecommerce keeps its own secrets (NOT shared with Master):
ECOMMERCE_JWT_SECRET=<only needed by Ecommerce>
ECOMMERCE_JWT_ALGORITHM=HS256  (only needed by Ecommerce)
```

## Logging

**✅ Safe to log:**
```
[API] app=ecommerce operation=get_cart method=GET path=/api/cart request_started
[API] app=ecommerce operation=get_cart method=GET path=/api/cart response_status=200 success=true
```

**❌ Never log:**
```
Authorization: Bearer <token>  (contains user token)
api_key_value                  (contains credential)
jwt_secret                     (contains secret)
bearer_token                   (contains token)
```

## Testing

To verify correct architecture:

1. Register Ecommerce without any Bearer Token
2. Call POST /api/v1/chat with Authorization header
3. Verify workflow receives authorization from incoming request
4. Verify API executor forwards the user token to the target application
5. Verify no tokens are stored in application_credentials
6. Verify logs don't contain token values

## Migration Notes

If Bearer Token fields exist in previous code:

1. Frontend: Remove Bearer Token input from application form ✅ Done
2. Backend: ApplicationCreateRequest never accepted bearer_token ✅ Already correct
3. API Client: Don't look up bearer tokens from application_credentials ✅ Done
4. Workflow: Pass authorization from incoming request state ✅ Already correct

All changes maintain backward compatibility while preventing user token storage.
