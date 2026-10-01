# Master Chatbot Client SDK

A lightweight Python SDK for integrating with the **Master Chatbot Service** - a centralized multi-application AI assistant platform.

## Features

- ✅ **Simple API** - Just a few lines to integrate
- ✅ **Async Support** - Works with FastAPI and other async frameworks
- ✅ **Secure** - Never exposes service credentials to frontend
- ✅ **Error Handling** - Clean exception hierarchy
- ✅ **Retries** - Automatic retry with exponential backoff
- ✅ **Logging** - Built-in request/response logging
- ✅ **Type Safe** - Full type hints for IDE support

## Installation

```bash
pip install master-chatbot-client
```

## Quick Start

### Basic Usage (Async)

```python
from master_chatbot import MasterChatbotClient

# Initialize from environment variables
client = MasterChatbotClient.from_env()

# Send a message
response = await client.achat(
    message="Show my profile",
    user_jwt_token=user_jwt,  # JWT from user authentication
    conversation_id=conversation_id,  # Optional, for conversation continuation
)

print(response.message)  # Bot's response
print(response.intent)   # Detected intent
print(response.data)     # Structured data
```

### Synchronous Usage

```python
# Synchronous version
response = client.chat(
    message="Show my profile",
    user_jwt_token=user_jwt,
)
```

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from master_chatbot import MasterChatbotClient

app = FastAPI()
client = MasterChatbotClient.from_env()

@app.post("/chatbot")
async def handle_chatbot_message(
    message: str,
    current_user: User = Depends(get_current_user),
):
    """Handle chatbot message from frontend."""
    
    # Generate JWT for authenticated user
    user_jwt = generate_user_jwt(current_user)
    
    # Send to Master Chatbot
    response = await client.achat(
        message=message,
        user_jwt_token=user_jwt,
    )
    
    return response
```

## Configuration

### Environment Variables

```bash
# Required
export MASTER_CHATBOT_URL=https://chatbot.example.com
export MASTER_CHATBOT_APP_ID=hrm
export MASTER_CHATBOT_SERVICE_KEY=secure_key_here

# Optional
export MASTER_CHATBOT_TIMEOUT=30
export MASTER_CHATBOT_RETRIES=3
export MASTER_CHATBOT_LOG_LEVEL=INFO
```

### Programmatic Configuration

```python
from master_chatbot import MasterChatbotClient
from master_chatbot.config import MasterChatbotConfig

config = MasterChatbotConfig(
    base_url="https://chatbot.example.com/api/v1",
    app_id="hrm",
    service_key="secure_key_here",
    timeout=30,
    retries=3,
)

client = MasterChatbotClient(config)
```

## Error Handling

```python
from master_chatbot import (
    MasterChatbotClient,
    MasterChatbotAuthenticationError,
    MasterChatbotAuthorizationError,
    MasterChatbotValidationError,
    MasterChatbotTimeoutError,
    MasterChatbotRateLimitError,
    MasterChatbotServiceUnavailableError,
)

client = MasterChatbotClient.from_env()

try:
    response = await client.achat(
        message="Show my profile",
        user_jwt_token=user_jwt,
    )
    
except MasterChatbotAuthenticationError:
    # User JWT invalid or expired
    print("Please re-authenticate")
    
except MasterChatbotAuthorizationError:
    # User lacks permission
    print("Access denied")
    
except MasterChatbotValidationError as e:
    # Invalid request
    print(f"Invalid request: {e}")
    
except MasterChatbotTimeoutError:
    # Request took too long
    print("Request timed out, try again")
    
except MasterChatbotRateLimitError:
    # Rate limited
    print("Too many requests, please wait")
    
except MasterChatbotServiceUnavailableError:
    # Service down
    print("Service temporarily unavailable")
```

## Request Context

### Conversation Continuation

```python
# Start new conversation
response1 = await client.achat(
    message="Show my leave balance",
    user_jwt_token=user_jwt,
)
conversation_id = response1.conversation_id

# Continue in same conversation
response2 = await client.achat(
    message="What about medical leave?",
    user_jwt_token=user_jwt,
    conversation_id=conversation_id,  # Continue context
)
```

### Session Tracking

```python
import uuid

session_id = str(uuid.uuid4())

# All messages in same session
response = await client.achat(
    message="Show my profile",
    user_jwt_token=user_jwt,
    session_id=session_id,
)
```

### Request Tracing

```python
import uuid

request_id = str(uuid.uuid4())

response = await client.achat(
    message="Show my attendance",
    user_jwt_token=user_jwt,
    request_id=request_id,  # For tracing across services
)
```

## Response Structure

```python
response = await client.achat(
    message="How many leaves do I have?",
    user_jwt_token=user_jwt,
)

# Response attributes
print(response.success)           # bool: True if successful
print(response.app_id)            # str: "hrm"
print(response.conversation_id)   # str: Conversation UUID
print(response.message)           # str: Bot's response
print(response.intent)            # str: Detected intent (e.g., "leave.get_balance")
print(response.data)              # list[dict]: Structured data
print(response.actions)           # list[dict]: Available actions
print(response.metadata)          # dict: Additional metadata
```

## Security

### Never Do This ❌

```python
# WRONG: Don't pass service key to frontend
@app.get("/config")
def get_config():
    return {
        "service_key": os.getenv("MASTER_CHATBOT_SERVICE_KEY"),  # WRONG!
    }

# WRONG: Don't trust frontend user_id
response = await client.achat(
    message=message,
    user_jwt_token=request.headers.get("X-User-Id"),  # WRONG!
)

# WRONG: Don't pass frontend to chatbot directly
@app.post("/chatbot")
async def chatbot(message: str):
    # Missing authentication!
    response = await client.achat(message=message, user_jwt_token=???)
```

### Do This Instead ✅

```python
# RIGHT: Service key only in backend
# MASTER_CHATBOT_SERVICE_KEY stored as environment variable

# RIGHT: Generate JWT on backend
@app.post("/chatbot")
async def chatbot(message: str, current_user: User = Depends(auth)):
    user_jwt = generate_user_jwt(current_user)
    response = await client.achat(
        message=message,
        user_jwt_token=user_jwt,
    )
    return response
```

## Logging

Enable debug logging to see request/response details:

```python
import logging

logging.getLogger("master_chatbot").setLevel(logging.DEBUG)

# Logs will include:
# - Request details (without sensitive data)
# - Retry attempts
# - Response latency
# - Error messages
```

## Application IDs

Configure your app using different `app_id` values:

```bash
# HRM Application
export MASTER_CHATBOT_APP_ID=hrm

# Healthcare Application
export MASTER_CHATBOT_APP_ID=healthcare

# Finance Application
export MASTER_CHATBOT_APP_ID=finance

# E-commerce Application
export MASTER_CHATBOT_APP_ID=ecommerce
```

The Master Chatbot uses `app_id` to route requests to the correct adapter and tools.

## Architecture

```
Your Application
    ↓
MasterChatbotClient (this SDK)
    ↓
Master Chatbot API (POST /api/v1/chat)
    ↓
LangGraph Orchestration
    ↓
Application-Specific Tools
    ↓
Your Application APIs / Database
```

## Contributing

Contributions welcome! Please submit pull requests or open issues on GitHub.

## License

MIT License - see LICENSE file for details

## Support

For issues or questions:
- GitHub Issues: https://github.com/example/master-chatbot-client/issues
- Documentation: https://master-chatbot-client.readthedocs.io
- Email: team@example.com

## Changelog

### v1.0.0 (2026-09-03)
- Initial release
- Sync and async support
- Full error handling
- Retry logic
- Logging support
