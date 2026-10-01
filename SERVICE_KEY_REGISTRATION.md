# Application service-key registration

Registration and editing accept a write-only `service_key`. The API Configuration form masks it by default, includes a show/hide button, and requires it when Service authentication is set to Service key required (unless an existing key is configured). Review displays only Configured / Not configured. Blank, null, and omitted edit values preserve the saved key. There is no implicit removal action.

The frontend requires an HTTPS API URL when submitting a secret. Configure `NEXT_PUBLIC_API_BASE_URL` with an HTTPS endpoint (or a relative URL behind an HTTPS reverse proxy). The secret stays in temporary form/ref memory, outside React Query mutation variables and browser storage; the ref is cleared after saving. Existing keys are never fetched or populated into the form.

## API shapes

Create: `POST /api/v1/admin/applications`

```json
{
  "name": "Example",
  "app_id": "example",
  "base_url": "https://example.invalid",
  "discovery_mode": "manual",
  "auth_type": "service_key",
  "service_key": "<secret supplied securely by the administrator>"
}
```

Rotation: `PUT /api/v1/admin/applications/{application_uuid}`

```json
{"service_key": "<replacement secret>"}
```

Create/update/GET responses retain existing application metadata and add:

```json
{
  "id": "<application UUID>",
  "app_id": "example",
  "auth_type": "service_key",
  "service_key_configured": true
}
```

`auth_type` remains the application's selected authentication setting; supplying a key always writes a credential with `auth_type = service_key`. Optional applications can omit both the key and service-key authentication. Chat authorization still requires a configured matching key; optional registration does not bypass chat authorization.

## Existing database structure

No table or column migration is needed.

```text
application_credentials
  id                       existing credential UUID (retained on rotation)
  application_id           applications.id (new application's UUID)
  auth_type                service_key
  is_active                true
  bearer_token_encrypted   Fernet ciphertext from app.crypto.encrypt
  api_key_encrypted        NULL (legacy values replaced on rotation)
```

Creation, encrypted credential upsert and audit recording share one transaction. The runtime definition is built before commit and published after commit. Updates, renaming, disabling/enabling and deletion update the current process's cache immediately. The existing registry is process-local; this change does not introduce cross-process cache coordination. Credential upsert locks the parent application on databases supporting row locks. Deletion uses the existing ORM cascade relationships, including on SQLite.

## Validation

- Backend: 11 passed across `test_application_service_keys.py`, `test_api_test_authorization.py`, and `test_admin_route_test_proxy_header.py` (two dependency deprecation warnings).
- The lifecycle test uses an isolated in-memory database and actual admin/chat HTTP handlers. It covers encryption, optional/required registration, rotation without duplicate rows, blank/null/omitted edits, safe GET responses and audit/log output, immediate cache access, correct/wrong/missing chat keys, disable/enable, renaming, validation-error redaction and credential cleanup.
- Frontend: 3 API-client tests passed with `node tests/application-service-key.test.cjs`.
- Frontend: `npm run typecheck` passed.
- `git diff --check` passed.
- No live application credentials or database were modified. Browser interaction was not manually tested.

## Files changed for this feature

Paths relative to `Master-Chatbot/chatbot/`:

- `backend/app/admin_routes.py`
- `backend/app/app_registry.py`
- `backend/app/main.py` (avoid rereading a consumed body in the safe validation handler)
- `backend/app/repositories.py`
- `backend/app/services.py`
- `backend/tests/test_application_service_keys.py`
- `frontend/app/app-registry/new/page.tsx`
- `frontend/app/app-registry/[id]/edit/page.tsx`
- `frontend/components/applications/application-form.tsx`
- `frontend/lib/api/applications.ts`
- `frontend/lib/validations/application.ts`
- `frontend/types/index.ts`
- `frontend/tests/application-service-key.test.cjs`
- `SERVICE_KEY_REGISTRATION.md`
