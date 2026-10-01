# Master Chatbot React Widget

Reusable UI for separate React applications. It does not call the Master Chatbot API directly;
your application backend authenticates the user and implements `onSendMessage`.

```bash
npm install ../master_chatbot_widget
```

```tsx
import { MasterChatbotWidget } from "@master-chatbot/react";

<MasterChatbotWidget
  appId="ecommerce"
  title="Shopping Assistant"
  onSendMessage={async (message, conversation_id, session_id, request_id) => {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id, session_id, request_id }),
    });
    if (!response.ok) throw Object.assign(new Error("Chat request failed"), { status: response.status });
    return response.json();
  }}
/>
```

Assistant responses with `data` automatically display record cards, including nested
pagination envelopes such as `[{ total: 11, patients: [...] }]`. Forward the complete
API response from `onSendMessage`, including `data`; do not return only `message`.
Cards support product images/prices, patient photos/names, and generic record fields.
View details expands locally; Show more reveals additional records already returned
by the API (it does not fetch another page). Currency formatting uses the record's
`currency` or `currency_code` when supplied. Custom `renderMessage` still overrides
the default renderer and now receives `data` and `actions` too.

After changing this package, run `npm run build` and update/restart consuming apps
that installed a copied local package. Import `@master-chatbot/react/styles.css`
in the host application. Run card checks with `node --test tests/record-cards.test.mjs`
after building.

### Conversational sign-in

Provide `isAuthenticated`, `accountId`, and `onLogin` to enable sign-in within the
normal chat composer. The bot asks Yes/No, then Email ID or User ID, then password.
The password uses the same composer in masked mode. Only a fixed bullet placeholder
appears in the transcript; credentials are never passed to `onSendMessage` or
`onMessageReceived`. The host callback must authenticate and save its session before
resolving. A 401 error from `onSendMessage` must retain its numeric `status` property;
this triggers the expired-session prompt and resumes the pending task after login.

```tsx
isAuthenticated={!!user}
accountId={user?.id}
onLogin={async ({ email, password }) => {
  // `email` contains the email address or User ID entered by the user.
  const result = await authService.login(email, password);
  setUser(result.user, result);
}}
```

`accountId` clears private chat state on logout/account changes. Login state and
credentials are never persisted. Product cards use `metadata.capabilities` to show
supported actions, and comparison can be selected on cards or requested in chat.
