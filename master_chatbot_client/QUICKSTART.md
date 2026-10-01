# Master Chatbot SDK - Quick Start Guide

Get your application integrated with Master Chatbot in 5 minutes.

---

## Installation

```bash
pip install master-chatbot-client
```

---

## Configuration

### Option 1: Environment Variables

```bash
export MASTER_CHATBOT_URL=http://localhost:9000
export MASTER_CHATBOT_APP_ID=hrm
export MASTER_CHATBOT_SERVICE_KEY=your-secret-key
```

Then in your code:

```python
from master_chatbot import MasterChatbotClient

client = MasterChatbotClient.from_env()
```

### Option 2: Programmatic Configuration

```python
from master_chatbot import MasterChatbotClient, MasterChatbotConfig

config = MasterChatbotConfig(
    base_url="http://localhost:9000/api/v1",
    app_id="hrm",
    service_key="your-secret-key",
    timeout=30.0,
    retries=3,
)

client = MasterChatbotClient(config=config)
```

---

## Basic Usage

### Sync (Blocking)

```python
from master_chatbot import MasterChatbotClient

client = MasterChatbotClient.from_env()

response = client.chat(
    message="How many leaves do I have?",
    user_jwt_token="Bearer eyJ...",  # User's JWT token
)

print(response.message)
print(response.conversation_id)
print(response.intent)
```

### Async (Non-Blocking) - Recommended

```python
import asyncio
from master_chatbot import MasterChatbotClient

async def main():
    client = MasterChatbotClient.from_env()
    
    response = await client.achat(
        message="How many leaves do I have?",
        user_jwt_token="Bearer eyJ...",
    )
    
    print(response.message)
    print(response.conversation_id)
    print(response.intent)

asyncio.run(main())
```

---

## Conversation Management

### Start New Conversation

```python
response = await client.achat(
    message="Show my profile",
    user_jwt_token="Bearer token...",
    # conversation_id is omitted, so new one is created
)

conversation_id = response.conversation_id
print(f"Started conversation: {conversation_id}")
```

### Continue Existing Conversation

```python
response = await client.achat(
    message="What about my leaves?",
    user_jwt_token="Bearer token...",
    conversation_id=conversation_id,  # Reference existing
)

print(f"Continued conversation: {response.conversation_id}")
```

### Multi-Turn Conversation

```python
conversation_id = None

# Turn 1
response1 = await client.achat(
    message="Show me employees",
    user_jwt_token="Bearer token...",
)
conversation_id = response1.conversation_id
print(f"Response 1: {response1.message}")

# Turn 2
response2 = await client.achat(
    message="Filter by department",
    user_jwt_token="Bearer token...",
    conversation_id=conversation_id,
)
print(f"Response 2: {response2.message}")

# Turn 3
response3 = await client.achat(
    message="Sort by name",
    user_jwt_token="Bearer token...",
    conversation_id=conversation_id,
)
print(f"Response 3: {response3.message}")
```

---

## Error Handling

```python
from master_chatbot import MasterChatbotClient
from master_chatbot.exceptions import (
    MasterChatbotError,
    MasterChatbotAuthenticationError,
    MasterChatbotValidationError,
    MasterChatbotTimeoutError,
)

client = MasterChatbotClient.from_env()

try:
    response = await client.achat(
        message="Test message",
        user_jwt_token="Bearer token...",
    )
except MasterChatbotAuthenticationError:
    print("Authentication failed - token may be expired")
except MasterChatbotValidationError as e:
    print(f"Validation error: {e}")
except MasterChatbotTimeoutError:
    print("Request timed out")
except MasterChatbotError as e:
    print(f"Chatbot error: {e}")
```

---

## Response Structure

```python
response = await client.achat(message="...", user_jwt_token="...")

print(response.app_id)           # "hrm"
print(response.conversation_id)   # "conv-abc123"
print(response.message)           # Bot's response text
print(response.intent)            # "leave_balance", "search", etc.
print(response.data)              # Application-specific data (list)
print(response.actions)           # Available actions (list)
print(response.metadata)          # Additional metadata (dict)
```

---

## FastAPI Integration

```python
from fastapi import FastAPI, Depends, Request
from master_chatbot import MasterChatbotClient

app = FastAPI()
client = MasterChatbotClient.from_env()

@app.post("/api/chat")
async def chat(request: Request, message: str):
    # Get JWT from Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        return {"error": "No authorization"}
    
    # Get conversation ID from session/query param
    conversation_id = request.query_params.get("conversation_id")
    
    try:
        response = await client.achat(
            message=message,
            user_jwt_token=auth_header,  # Include "Bearer " prefix
            conversation_id=conversation_id,
        )
        
        return {
            "message": response.message,
            "conversation_id": response.conversation_id,
            "intent": response.intent,
            "data": response.data,
            "actions": response.actions,
        }
    except Exception as e:
        return {"error": str(e)}
```

---

## Django Integration

```python
from django.http import JsonResponse
from django.views import View
from master_chatbot import MasterChatbotClient
import asyncio

client = MasterChatbotClient.from_env()

class ChatView(View):
    async def post(self, request):
        # Get JWT from Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        message = request.POST.get("message")
        conversation_id = request.GET.get("conversation_id")
        
        if not auth_header or not message:
            return JsonResponse({"error": "Missing parameters"}, status=400)
        
        try:
            response = await client.achat(
                message=message,
                user_jwt_token=auth_header,
                conversation_id=conversation_id,
            )
            
            return JsonResponse({
                "message": response.message,
                "conversation_id": response.conversation_id,
                "intent": response.intent,
                "data": response.data,
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
```

---

## Configuration Options

```python
# All optional (defaults shown)
config = MasterChatbotConfig(
    base_url="http://localhost:9000/api/v1",  # Required
    app_id="hrm",                              # Required
    service_key="your-key",                    # Required
    timeout=30.0,                              # Default: 30 seconds
    retries=3,                                 # Default: 3 attempts
    log_level="INFO",                          # Default: INFO
    verify_ssl=True,                           # Default: True
)
```

---

## Context Propagation

```python
response = await client.achat(
    message="Test message",
    user_jwt_token="Bearer token...",
    conversation_id="conv-123",      # For conversation history
    session_id="sess-456",           # For request grouping
    request_id="req-789",            # For tracing
)

# These are automatically included in HTTP headers
# And available to Master Chatbot for logging/debugging
```

---

## Common Issues

### Issue: ModuleNotFoundError: No module named 'master_chatbot'

**Solution**: Install the package
```bash
pip install master-chatbot-client
```

### Issue: MasterChatbotAuthenticationError (401)

**Solution**: Check JWT token is valid
```python
# Ensure token is from user's auth context
user_jwt = get_user_jwt_from_request(request)
response = await client.achat(
    message="test",
    user_jwt_token=user_jwt,  # Must be valid JWT
)
```

### Issue: MasterChatbotConfigError

**Solution**: Verify environment variables
```bash
echo $MASTER_CHATBOT_URL
echo $MASTER_CHATBOT_APP_ID
echo $MASTER_CHATBOT_SERVICE_KEY
```

### Issue: MasterChatbotTimeoutError

**Solution**: Increase timeout or check connection
```python
config = MasterChatbotConfig(
    base_url="...",
    app_id="...",
    service_key="...",
    timeout=60.0,  # Increase from default 30
)
```

---

## API Reference

### MasterChatbotClient

```python
class MasterChatbotClient:
    def __init__(config: MasterChatbotConfig | None = None)
    @classmethod
    def from_env() -> MasterChatbotClient
    
    async def achat(
        message: str,
        user_jwt_token: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> ChatResponse
    
    def chat(
        message: str,
        user_jwt_token: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> ChatResponse
```

### ChatResponse

```python
class ChatResponse:
    app_id: str
    conversation_id: str
    message: str
    intent: str
    data: list
    actions: list
    metadata: dict
```

### Exceptions

```python
MasterChatbotError
├── MasterChatbotConfigError
├── MasterChatbotAuthenticationError
├── MasterChatbotAuthorizationError
├── MasterChatbotValidationError
├── MasterChatbotTimeoutError
├── MasterChatbotRateLimitError
└── MasterChatbotServiceUnavailableError
```

---

## Best Practices

1. **Always use `from_env()`**
   ```python
   client = MasterChatbotClient.from_env()
   ```

2. **Use async/await**
   ```python
   response = await client.achat(...)  # ✅ Preferred
   response = client.chat(...)          # ❌ Only if needed
   ```

3. **Handle all exceptions**
   ```python
   try:
       response = await client.achat(...)
   except MasterChatbotError as e:
       logger.error(f"Chat error: {e}")
   ```

4. **Preserve conversation IDs**
   ```python
   conversation_id = response.conversation_id
   # Use for follow-up requests
   ```

5. **Pass JWT from auth context**
   ```python
   # ✅ From HTTP Authorization header
   jwt = request.headers.get("Authorization")
   
   # ❌ Do NOT invent JWT from frontend
   ```

6. **Log important events**
   ```python
   logger.info(f"Chat: {response.conversation_id}")
   logger.info(f"Intent: {response.intent}")
   ```

---

## Next Steps

- Read [SDK Design](../MASTER_CHATBOT_SDK_DESIGN.md) for architecture details
- Read [Integration Guide](../MASTER_CHATBOT_SDK_INTEGRATION_GUIDE.md) for advanced patterns
- See [Example App](../examples/hrm_chatbot_integration.py) for full integration
- Run tests: `pytest master_chatbot_client/tests/`

---

## Support

For issues or questions:
1. Check the [Integration Guide](../MASTER_CHATBOT_SDK_INTEGRATION_GUIDE.md)
2. Review [Test Report](../MASTER_CHATBOT_SDK_TEST_REPORT.md) for examples
3. Check examples in `examples/` directory
4. Review test files in `tests/` for patterns

---

**Master Chatbot SDK v1.0**  
Ready for production use ✅
