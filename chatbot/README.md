# Master Chatbot

This standalone service has no imports from HRM, HIS, or E-commerce. It accesses application data only through each application's authenticated HTTP APIs. Applications and their allowed routes are deployment configuration in `config/applications.json`, not Python adapters.

```bash
cd chatbot/backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; source ../.env; set +a
.venv/bin/uvicorn app.main:app --reload --port 9000
```

The HIS backend must call it through `master_chatbot_client` from a thin authenticated `/api/chat` route. Configure `MASTER_CHATBOT_URL=http://localhost:9000/api/v1`, `MASTER_CHATBOT_APP_ID=his`, and `MASTER_CHATBOT_SERVICE_KEY` to match `HIS_MASTER_CHATBOT_SERVICE_KEY`. The browser calls only HIS `/api/chat`.

```python
# HIS backend: use its existing auth dependency and forward the incoming token.
@router.post("/api/chat")
async def chat(payload: ChatPayload, request: Request, current_user=Depends(get_current_active_user)):
    token = request.headers.get("Authorization", "")
    response = await MasterChatbotClient.from_env().achat(
        message=payload.message, user_jwt_token=token,
        conversation_id=payload.conversation_id, session_id=payload.session_id,
        request_id=payload.request_id,
    )
    return response.__dict__
```

## Conversational shopping

The ecommerce registry now includes customer cart updates, saved-address creation
and editing, return/refund requests, refund status, whole-order cancellation, and
purchased-item status filtering. ShopNest owns authentication, authorization and
eligibility checks. Stock searches accept `availability=in_stock|out_of_stock`;
ordered products use `list_order_items` with a status such as `delivered`.
Refund requests do not approve or transfer money. Cancellation uses the shop's
existing whole-order cancellation service, not individual-item cancellation.

Required write fields are checked before execution. Recent turns and API records
provide context for follow-up answers. Additional comparison queries may only use
registered GET routes. Passwords are handled directly by the widget's host login
callback and never enter this workflow.

Conversation context and successful request deduplication are currently in-memory,
scoped by application, authenticated principal and conversation, with a 30-minute
TTL and 1,000-conversation cap. Run a single service worker for this implementation;
a shared store, distributed locking and application-level idempotency are required
before scaling mutations across workers. A failed or uncertain write is not retried
automatically by the workflow; users are asked to check status.

Restart Master Chatbot after changing its registry, and restart ShopNest's API after
route changes. Build the widget with `npm run build --prefix master_chatbot_widget`.
