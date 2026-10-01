# SDK API

`MasterChatbotClient` and `AsyncMasterChatbotClient` are backend-only HTTP clients.

Both clients call `POST {MASTER_CHATBOT_URL}/api/v1/chat` with `app_id`, `message`, and optional
`conversation_id`/`session_id`. The SDK propagates a bearer user JWT plus `X-Request-Id` and
`X-Chat-Session-Id` headers. It does not send or log `MASTER_CHATBOT_SERVICE_KEY`; the current
Master Chatbot endpoint does not define a service-key header.

Use `MasterChatbotClient.chat()` in synchronous code and `await client.achat()` or
`await AsyncMasterChatbotClient.chat()` in asynchronous code. Retries are limited to timeouts,
network failures, 429, and 5xx responses, using 1 then 2 second backoff. Consumers must make
state-changing chatbot operations idempotent before enabling retries.
