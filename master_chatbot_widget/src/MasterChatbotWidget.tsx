import { Maximize2, Minimize2, RefreshCcw, Send, Sparkles, X, MessageCircle } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import type { MasterChatbotMessage, MasterChatbotWidgetError, MasterChatbotWidgetProps } from "./types.js";
import { RecordCards } from "./RecordCards.js";
import { AddressSelector, extractDefaultAddress } from "./AddressSelector.js";
import type { AddressRecord } from "./AddressSelector.js";

const DEFAULT_SUGGESTIONS = ["How can you help?", "Show me recent updates", "I need support"];
const makeId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

function classifyError(error: unknown): MasterChatbotWidgetError {
  const message = error instanceof Error ? error.message : "Unable to send your message.";
  const status =
    typeof error === "object" && error !== null && "status" in error
      ? (error as { status?: unknown }).status
      : undefined;
  if (status === 401) return { type: "authentication", message, retryable: false };
  if (status === 400 || status === 404 || status === 422) return { type: "validation", message, retryable: false };
  if (status === 408) return { type: "timeout", message, retryable: true };
  return { type: "network", message, retryable: true };
}

/** Multi-step return / refund / replace flow state */
type ReturnFlowStep =
  | { step: "select_option"; itemId: string; itemName: string }
  | { step: "proof"; itemId: string; itemName: string; actionType: "return" | "refund" }
  | null;

/** Address fields collected step by step */
type AddressFormField = "recipient_name" | "line1" | "city" | "state" | "postal_code";
type AddressFormState = {
  step: AddressFormField;
  recipient_name: string;
  line1: string;
  city: string;
  state: string;
  postal_code: string;
} | null;

const ADDRESS_FORM_STEPS: AddressFormField[] = ["recipient_name", "line1", "city", "state", "postal_code"];
const ADDRESS_FORM_PROMPTS: Record<AddressFormField, string> = {
  recipient_name: "Please enter the recipient's full name:",
  line1: "Enter the street address (line 1):",
  city: "Enter the city:",
  state: "Enter the state:",
  postal_code: "Enter the postal / ZIP code:",
};

type InteractionState = {
  selectedProducts: string[];
  selectedOrder: Record<string, unknown> | null;
  selectedOrderItem: Record<string, unknown> | null;
  pendingAction: string | null;
  pendingReason: string | null;
  replacementProduct: Record<string, unknown> | null;
  comparisonPending: boolean;
};

export function MasterChatbotWidget({
  appId,
  onSendMessage,
  title = "Assistant",
  placeholder = "Ask a question...",
  avatar,
  logo,
  welcomeMessage = "I can help answer questions and guide you through this application.",
  suggestions = DEFAULT_SUGGESTIONS,
  maxMessages = 100,
  ariaLabel = "Master Chatbot",
  initialMessages = [],
  onLogin,
  isAuthenticated,
  accountId,
  onError,
  onConversationStart,
  onConversationEnd,
  onMessageReceived,
  renderMessage,
}: MasterChatbotWidgetProps) {
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState(false);
  const [messages, setMessages] = useState<MasterChatbotMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<MasterChatbotWidgetError | null>(null);
  const [conversationId, setConversationId] = useState<string>();
  const [lastMessage, setLastMessage] = useState<string>();
  const [loginStep, setLoginStep] = useState<"confirm" | "identifier" | "password" | "busy" | null>(null);
  const [returnFlow, setReturnFlow] = useState<ReturnFlowStep>(null);
  const [addressList, setAddressList] = useState<AddressRecord[] | null>(null);
  const [addressForm, setAddressForm] = useState<AddressFormState>(null);
  const [interactionState, setInteractionState] = useState<InteractionState>({
    selectedProducts: [],
    selectedOrder: null,
    selectedOrderItem: null,
    pendingAction: null,
    pendingReason: null,
    replacementProduct: null,
    comparisonPending: false,
  });

  const loginOpen = loginStep !== null;
  const loginIdentifier = useRef("");
  const pendingMessage = useRef<string | undefined>(undefined);
  const sessionId = useRef(makeId());
  const scrollTarget = useRef<HTMLDivElement>(null);
  const previousAccount = useRef(accountId);
  const previousApp = useRef(appId);
  const generation = useRef(0);
  const storageKey = `master-chatbot-ui-state:${appId}`;

  useEffect(() => {
    if (
      previousApp.current !== appId ||
      (previousAccount.current && previousAccount.current !== accountId)
    ) {
      generation.current += 1;
      setMessages([]);
      setInput("");
      loginIdentifier.current = "";
      setConversationId(undefined);
      setError(null);
      setLoginStep(null);
      setReturnFlow(null);
      setAddressList(null);
      setAddressForm(null);
      pendingMessage.current = undefined;
      sessionId.current = makeId();
    }
    previousAccount.current = accountId;
    previousApp.current = appId;
  }, [accountId, appId]);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null") as {
        open?: boolean;
        full?: boolean;
      } | null;
      if (saved) {
        setOpen(saved.open === true);
        setFull(saved.full === true);
      }
    } catch {
      /* ignore invalid saved UI state */
    }
  }, [storageKey]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify({ open, full }));
  }, [storageKey, open, full]);

  useEffect(() => {
    scrollTarget.current?.scrollIntoView({ block: "end" });
  }, [messages, isLoading, open, loginStep, returnFlow, addressForm]);

  const appendLocal = (role: "user" | "assistant", content: string) => {
    setMessages((current) =>
      [
        ...current,
        { id: makeId(), role, content, timestamp: new Date(), metadata: { local_auth: true } },
      ].slice(-maxMessages),
    );
  };

  const beginLogin = (expired = false) => {
    setInput("");
    setError(null);
    loginIdentifier.current = "";
    setLoginStep("confirm");
    appendLocal(
      "assistant",
      expired
        ? "Your session has expired. You need to log in to continue. Would you like to sign in?"
        : "You need to log in to continue. Would you like to sign in?",
    );
  };

  const answerLogin = async (value: string) => {
    if (!onLogin || loginStep === "busy") return;
    setInput("");
    if (loginStep === "confirm") {
      if (/^(yes|y|haan|ha)$/i.test(value.trim())) {
        appendLocal("user", "Yes");
        appendLocal("assistant", "Enter your Email ID or User ID.");
        setLoginStep("identifier");
      } else if (/^(no|n|nahi|cancel)$/i.test(value.trim())) {
        appendLocal("user", "No");
        appendLocal("assistant", "Okay. You can sign in whenever you're ready.");
        pendingMessage.current = undefined;
        setLoginStep(null);
      } else {
        appendLocal("assistant", "Please select Yes or No.");
      }
      return;
    }
    if (loginStep === "identifier") {
      const identifier = value.trim();
      if (!identifier || identifier.length > 254 || /\s/.test(identifier)) {
        appendLocal("assistant", "Please enter a valid Email ID or User ID.");
        return;
      }
      loginIdentifier.current = identifier;
      appendLocal("user", identifier);
      appendLocal("assistant", "Enter your password.");
      setLoginStep("password");
      return;
    }
    if (loginStep === "password") {
      if (!value) return;
      appendLocal("user", "••••••••");
      setLoginStep("busy");
      const authGeneration = generation.current;
      try {
        await onLogin({ email: loginIdentifier.current, password: value });
        if (authGeneration !== generation.current) return;
        loginIdentifier.current = "";
        setLoginStep(null);
        appendLocal("assistant", "You're signed in successfully.");
        const pending = pendingMessage.current;
        pendingMessage.current = undefined;
        if (pending) void send(pending, true, false);
      } catch {
        if (authGeneration !== generation.current) return;
        appendLocal("assistant", "Login failed. Please enter your Email ID or User ID again.");
        loginIdentifier.current = "";
        setLoginStep("identifier");
      }
    }
  };

  /** Intercept internal signals emitted by RecordCards for flow selection */
  const handleCardMessage = (value: string): boolean => {
    // __return_refund_select__ item_id=<id> name=<encoded>
    if (value.startsWith("__return_refund_select__")) {
      const idMatch = value.match(/item_id=([^\s]+)/);
      const nameMatch = value.match(/name=([^\s]+)/);
      if (!idMatch) return true;
      const itemId = idMatch[1];
      const itemName = nameMatch ? decodeURIComponent(nameMatch[1]) : "this item";
      setReturnFlow({ step: "select_option", itemId, itemName });
      appendLocal("user", `Selected: ${itemName}`);
      appendLocal("assistant", `What would you like to do with "${itemName}"?`);
      return true;
    }
    return false;
  };

  const handleReturnOption = async (option: "refund" | "return" | "replace") => {
    if (!returnFlow || returnFlow.step !== "select_option") return;
    const { itemId, itemName } = returnFlow;
    appendLocal("user", option.charAt(0).toUpperCase() + option.slice(1));

    if (option === "replace") {
      setReturnFlow(null);
      setInteractionState((current) => ({ ...current, pendingAction: "replacement", selectedOrderItem: { id: itemId }, replacementProduct: null }));
      void send(`find similar products for ${itemName}`, false, false);
      return;
    }

    setReturnFlow({ step: "proof", itemId, itemName, actionType: option });
    appendLocal(
      "assistant",
      `Please tell me the reason for ${option === "return" ? "returning this product" : "requesting a refund"}.`,
    );
  };

  const handleCardAction = (action: {
    type: "cancel" | "return" | "refund" | "replacement";
    order_id?: string;
    order_item_id?: string;
    product_id?: string;
  }) => {
    setInteractionState((current) => ({
      ...current,
      selectedOrder: action.order_id ? { order_id: action.order_id } : current.selectedOrder,
      selectedOrderItem: action.order_item_id ? { order_item_id: action.order_item_id } : current.selectedOrderItem,
      pendingAction: action.type,
      pendingReason: null,
      comparisonPending: false,
    }));

    if (action.type === "cancel") {
      if (isAuthenticated === false && onLogin) {
        pendingMessage.current = `cancel order_id ${action.order_id ?? ""}`.trim();
        beginLogin();
        return;
      }
      void sendWithTicket(`cancel order_id ${action.order_id ?? ""}`.trim(), "cancel");
      return;
    }

    if (action.type === "replacement") {
      const label = action.product_id ?? action.order_item_id ?? "this product";
      setReturnFlow(null);
      setInteractionState((current) => ({ ...current, pendingAction: "replacement" }));
      void sendWithTicket(`find similar products for ${label}`, "replacement");
      return;
    }

    if (action.type === "return" || action.type === "refund") {
      const itemId = action.order_item_id ?? action.product_id ?? "";
      const itemName = "this item";
      setReturnFlow({ step: "proof", itemId, itemName, actionType: action.type });
      appendLocal("assistant", `Please tell me the reason for ${action.type === "return" ? "returning this product" : "requesting a refund"}.`);
    }
  };

  const handleProofSubmit = () => {
    if (!returnFlow || returnFlow.step !== "proof" || !input.trim()) return;
    const { itemId, itemName, actionType } = returnFlow;
    const proofText = input.trim();
    setReturnFlow(null);
    appendLocal("user", proofText);
    void sendWithTicket(
      `Submit ${actionType} request for order item ${itemId} (${itemName}). Reason and proof: ${proofText}`,
      actionType,
    );
    setInput("");
  };

  /** Send a message and, on success, extract a ticket/request ID from the response and display it. */
  const sendWithTicket = async (value: string, actionType: "return" | "refund" | "replacement" | "cancel" | "add_address" | "update_address") => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    const requestGeneration = generation.current;
    setError(null);
    setIsLoading(true);
    try {
      const response = await onSendMessage(trimmed, conversationId, sessionId.current, makeId());
      if (requestGeneration !== generation.current) return;

      // Extract ticket/request ID from response data
      const responseData = response.data;
      let ticketId: string | undefined;
      const dataObj =
        Array.isArray(responseData) && responseData.length > 0 ? responseData[0]
        : isRecord(responseData) ? responseData
        : null;
      if (isRecord(dataObj)) {
        const raw =
          dataObj.ticket_id ?? dataObj.request_id ?? dataObj.reference_id ??
          dataObj.return_id ?? dataObj.refund_id ?? dataObj.replacement_id ??
          dataObj.id;
        if (raw != null) ticketId = String(raw);
      }

      const successMessages: Record<string, string> = {
        cancel:         "Your order has been cancelled successfully. ✅",
        return:         "Your return request has been submitted successfully. ✅",
        refund:         "Your refund request has been submitted successfully. ✅",
        replacement:    "Your replacement request has been submitted successfully. ✅",
        add_address:    "Address saved successfully. ✅",
        update_address: "Address updated successfully. ✅",
      };
      const ticketLine = ticketId ? ` Reference ID: ${ticketId}` : "";
      const successMsg = (successMessages[actionType] ?? `Your ${actionType} request has been submitted successfully. ✅`) + ticketLine;

      const assistantMessage: MasterChatbotMessage = {
        id: makeId(),
        role: "assistant",
        content: successMsg,
        timestamp: new Date(),
        intent: response.intent,
        // suppress data so no card is rendered for action confirmations
        metadata: { ...response.metadata, presentation: "text" },
        data: undefined,
        actions: response.actions,
      };
      setMessages((current) => [...current, assistantMessage].slice(-maxMessages));
      if (!conversationId) onConversationStart?.(response.conversation_id);
      setConversationId(response.conversation_id);
      onMessageReceived?.(assistantMessage);
    } catch (caughtError) {
      if (requestGeneration !== generation.current) return;
      const widgetError = classifyError(caughtError);
      if (widgetError.type === "authentication" && onLogin) {
        pendingMessage.current = trimmed;
        beginLogin(true);
      } else {
        setError(widgetError);
        onError?.(widgetError);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const send = async (value: string, afterLogin = false, echo = true) => {
    const trimmed = value.trim();
    if (!trimmed || isLoading || (loginOpen && !afterLogin)) return;

    // Handle internal card signals
    if (handleCardMessage(trimmed)) return;

    // "Show my default/selected address" — fetch list and display only the default
    const isShowDefaultAddress = /\b(show|what|display|get|view)\b.*\b(my\s+)?(selected|default|current)\s+address\b/i.test(trimmed)
      || /\b(selected|default|current)\s+address\b/i.test(trimmed);

    // "Update/change address" without explicit field data → show radio picker UI
    const isAddressPickerRequest = /\b(update|change|edit|modify|set)\b.*\baddress\b/i.test(trimmed)
      && !/recipient_name|line1|postal_code/i.test(trimmed);

    // Add address with full field data → straight to API
    const isAddAddress = /\badd\b.*\baddress\b/i.test(trimmed) && !/update|change|edit|modify/i.test(trimmed);

    if (isShowDefaultAddress || isAddressPickerRequest) {
      if (echo) setMessages((current) => [...current, { id: makeId(), role: "user" as const, content: trimmed, timestamp: new Date() }].slice(-maxMessages));
      setInput("");
      setIsLoading(true);
      setError(null);
      try {
        const response = await onSendMessage("list my saved addresses", conversationId, sessionId.current, makeId());
        const raw = Array.isArray(response.data) ? (response.data as AddressRecord[]) : [];
        if (isShowDefaultAddress) {
          const def = extractDefaultAddress(raw);
          const content = def ? `Your default address:\n${def}` : "You have no saved addresses yet.";
          setMessages((current) => [...current, { id: makeId(), role: "assistant" as const, content, timestamp: new Date() }].slice(-maxMessages));
        } else {
          if (!raw.length) {
            setMessages((current) => [...current, { id: makeId(), role: "assistant" as const, content: "You have no saved addresses to update.", timestamp: new Date() }].slice(-maxMessages));
          } else {
            setAddressList(raw);
            setMessages((current) => [...current, { id: makeId(), role: "assistant" as const, content: "Choose your default address:", timestamp: new Date(), metadata: { presentation: "text" } }].slice(-maxMessages));
          }
        }
        if (!conversationId) onConversationStart?.(response.conversation_id);
        setConversationId(response.conversation_id);
      } catch (caughtError) {
        const widgetError = classifyError(caughtError);
        if (widgetError.type === "authentication" && onLogin) { pendingMessage.current = trimmed; beginLogin(true); }
        else { setError(widgetError); onError?.(widgetError); }
      } finally {
        setIsLoading(false);
      }
      return;
    }

    if (isAddAddress) {
      if (echo) setMessages((current) => [...current, { id: makeId(), role: "user" as const, content: trimmed, timestamp: new Date() }].slice(-maxMessages));
      setInput("");
      // Start multi-step address form instead of directly calling API
      setAddressForm({ step: "recipient_name", recipient_name: "", line1: "", city: "", state: "", postal_code: "" });
      appendLocal("assistant", ADDRESS_FORM_PROMPTS["recipient_name"]);
      return;
    }

    // Explicit login command — start login flow immediately
    if (!afterLogin && onLogin && /^(log\s?in|sign\s?in)$/i.test(trimmed)) {
      pendingMessage.current = undefined;
      appendLocal("user", trimmed);
      beginLogin();
      return;
    }

    const requestGeneration = generation.current;
    const userMessage: MasterChatbotMessage = {
      id: makeId(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
    };
    if (echo) setMessages((current) => [...current, userMessage].slice(-maxMessages));
    setInput("");
    setError(null);
    setLastMessage(trimmed);
    setIsLoading(true);
    try {
      const response = await onSendMessage(trimmed, conversationId, sessionId.current, makeId());
      if (requestGeneration !== generation.current) return;

      // Backend signals auth is required (user-specific query but not logged in)
      if (response.metadata?.auth_required && onLogin) {
        pendingMessage.current = trimmed;
        const authMeta = response.metadata?.authentication;
        const expired = isRecord(authMeta) && authMeta.expired === true;
        beginLogin(expired);
        return;
      }

      const assistantMessage: MasterChatbotMessage = {
        id: makeId(),
        role: "assistant",
        content: response.message,
        timestamp: new Date(),
        intent: response.intent,
        metadata: response.metadata,
        data: response.data,
        actions: response.actions,
      };
      setMessages((current) => [...current, assistantMessage].slice(-maxMessages));
      if (!conversationId) onConversationStart?.(response.conversation_id);
      setConversationId(response.conversation_id);
      onMessageReceived?.(assistantMessage);
    } catch (caughtError) {
      if (requestGeneration !== generation.current) return;
      const widgetError = classifyError(caughtError);
      if (widgetError.type === "authentication" && onLogin) {
        pendingMessage.current = trimmed;
        beginLogin(true);
      } else {
        setError(widgetError);
        onError?.(widgetError);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSetDefaultAddress = async (address: AddressRecord) => {
    setAddressList(null);
    const id = String(address.address_id ?? address.id ?? "");
    const name = String(address.recipient_name ?? "");
    const line1 = String(address.line1 ?? "");
    const city = String(address.city ?? "");
    const state = String(address.state ?? "");
    const postal = String(address.postal_code ?? "");
    appendLocal("user", "Set as default address");
    // Build a message the LLM planner can parse directly with all required fields
    void sendWithTicket(
      `update address address_id=${id} recipient_name="${name}" line1="${line1}" city="${city}" state="${state}" postal_code="${postal}" is_default=true`,
      "update_address",
    );
  };

  /** Handle multi-step address form input */
  const handleAddressFormStep = async (value: string) => {
    if (!addressForm) return;
    const trimmed = value.trim();
    if (!trimmed) {
      appendLocal("assistant", `Please enter a valid value. ${ADDRESS_FORM_PROMPTS[addressForm.step]}`);
      return;
    }
    appendLocal("user", trimmed);
    const updated = { ...addressForm, [addressForm.step]: trimmed };
    const currentIdx = ADDRESS_FORM_STEPS.indexOf(addressForm.step);
    const nextStep = ADDRESS_FORM_STEPS[currentIdx + 1];
    if (nextStep) {
      setAddressForm({ ...updated, step: nextStep });
      appendLocal("assistant", ADDRESS_FORM_PROMPTS[nextStep]);
    } else {
      // All fields collected — submit
      setAddressForm(null);
      void sendWithTicket(
        `add address recipient_name="${updated.recipient_name}" line1="${updated.line1}" city="${updated.city}" state="${updated.state}" postal_code="${updated.postal_code}"`,
        "add_address",
      );
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loginOpen) {
      void answerLogin(input);
    } else if (addressForm) {
      void handleAddressFormStep(input);
      setInput("");
    } else if (returnFlow?.step === "proof") {
      handleProofSubmit();
    } else {
      void send(input);
    }
  };

  const reset = () => {
    setInput("");
    loginIdentifier.current = "";
    sessionId.current = makeId();
    setLoginStep(null);
    setReturnFlow(null);
    setAddressList(null);
    setAddressForm(null);
    pendingMessage.current = undefined;
    setMessages(initialMessages);
    setConversationId(undefined);
    setError(null);
    onConversationEnd?.();
  };

  const image = logo ?? avatar;

  return (
    <div className="master-chatbot-widget">
      {!open && (
        <button
          type="button"
          className="master-chatbot-launcher"
          onClick={() => {
            setOpen(true);
          }}
          aria-label={`Open ${ariaLabel}`}
        >
          <MessageCircle size={17} /> Ask AI
        </button>
      )}
      {open && (
        <section
          className={`master-chatbot-panel${full ? " is-fullscreen" : ""}`}
          role="dialog"
          aria-label={ariaLabel}
        >
          <header className="master-chatbot-header">
            <div className="master-chatbot-avatar">
              {image ? <img src={image} alt="" /> : <Sparkles size={19} />}
            </div>
            <div className="master-chatbot-heading">
              <p className="master-chatbot-title">{title}</p>
              <p className="master-chatbot-status">Online · Here to help</p>
            </div>
            <span className="master-chatbot-online">Online</span>
            <button
              type="button"
              className="master-chatbot-icon-button"
              onClick={() => setFull((v) => !v)}
              aria-label={full ? "Exit fullscreen" : "Fullscreen"}
            >
              {full ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </button>
            <button
              type="button"
              className="master-chatbot-icon-button"
              onClick={() => { setOpen(false); setInput(""); }}
              aria-label="Close assistant"
            >
              <X size={16} />
            </button>
          </header>

          <div className="master-chatbot-messages" aria-live="polite">
            <div className="master-chatbot-welcome">
              <div className="master-chatbot-welcome-row">
                <div className="master-chatbot-welcome-mark"><Sparkles size={16} /></div>
                <div>
                  <strong>Hi, how can I help today?</strong>
                  <p>{welcomeMessage}</p>
                </div>
              </div>
            </div>

            {messages.length === 0 && !loginOpen && (
              <div className="master-chatbot-empty">
                Choose a message below, or type your question.
                <div className="master-chatbot-suggestions">
                  {suggestions.map((suggestion) => (
                    <button
                      className="master-chatbot-suggestion"
                      key={suggestion}
                      type="button"
                      onClick={() => void send(suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <div className={`master-chatbot-bubble ${message.role}`} key={message.id}>
                {renderMessage?.(message) ??
                  (message.role === "assistant" ? (
                    <RecordCards
                      message={message}
                      onSend={(value) => void send(value)}
                      disabled={isLoading || loginOpen}
                      onAction={handleCardAction}
                      selectedProductIds={interactionState.selectedProducts}
                      onProductSelection={(productId, selected) => {
                        setInteractionState((current) => ({
                          ...current,
                          selectedProducts: selected
                            ? [...new Set([...current.selectedProducts, productId])]
                            : current.selectedProducts.filter((id) => id !== productId),
                          comparisonPending: current.selectedProducts.length + (selected ? 1 : -1) >= 2,
                        }));
                      }}
                    />
                  ) : (
                    message.content
                  ))}
              </div>
            ))}

            {/* Login confirm buttons */}
            {loginStep === "confirm" && (
              <div className="master-chatbot-auth-options">
                <button type="button" onClick={() => void answerLogin("Yes")}>Yes</button>
                <button type="button" onClick={() => void answerLogin("No")}>No</button>
              </div>
            )}

            {/* Login cancel link */}
            {(loginStep === "identifier" || loginStep === "password") && (
              <button
                className="master-chatbot-auth-cancel"
                type="button"
                onClick={() => {
                  setInput("");
                  loginIdentifier.current = "";
                  pendingMessage.current = undefined;
                  setLoginStep(null);
                  appendLocal("assistant", "Sign-in cancelled.");
                }}
              >
                Cancel sign-in
              </button>
            )}

            {/* Address picker — shown after "update address" request */}
            {addressList && (
              <div className="master-chatbot-bubble assistant">
                <AddressSelector
                  addresses={addressList}
                  disabled={isLoading}
                  onSelect={handleSetDefaultAddress}
                />
              </div>
            )}

            {/* Return / refund / replace option buttons */}
            {returnFlow?.step === "select_option" && (
              <div className="master-chatbot-auth-options" role="group" aria-label="Return options">
                <button type="button" disabled={isLoading} onClick={() => void handleReturnOption("refund")}>
                  Refund
                </button>
                <button type="button" disabled={isLoading} onClick={() => void handleReturnOption("return")}>
                  Return
                </button>
                <button type="button" disabled={isLoading} onClick={() => void handleReturnOption("replace")}>
                  Replace
                </button>
              </div>
            )}

            {(isLoading || loginStep === "busy") && (
              <div className="master-chatbot-typing" aria-label="Assistant is typing">
                <span /><span /><span />
              </div>
            )}

            {error && (
              <div className="master-chatbot-error" role="alert">
                {error.message}
                {error.retryable && lastMessage && (
                  <button type="button" onClick={() => void send(lastMessage)}>Retry</button>
                )}
              </div>
            )}

            <div ref={scrollTarget} />
          </div>

          <div className="master-chatbot-footer">
            {!isLoading && !loginOpen && !returnFlow && messages.length > 0 && (
              <div className="master-chatbot-suggestions">
                {suggestions.slice(0, 4).map((suggestion) => (
                  <button
                    className="master-chatbot-suggestion"
                    key={suggestion}
                    type="button"
                    onClick={() => void send(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            <form className="master-chatbot-form" onSubmit={submit}>
              <button
                type="button"
                className="master-chatbot-icon-button master-chatbot-reset"
                onClick={reset}
                disabled={isLoading || loginStep === "busy"}
                aria-label="Reset chat"
              >
                <RefreshCcw size={15} />
              </button>
              <label htmlFor={`master-chatbot-input-${appId}`} className="sr-only">
                Message the assistant
              </label>
              <input
                key={loginStep === "password" ? "input-password" : "input-text"}
                id={`master-chatbot-input-${appId}`}
                className="master-chatbot-input"
                type={loginStep === "password" ? "password" : "text"}
                maxLength={
                  loginStep === "password" ? 128
                  : loginStep === "identifier" ? 254
                  : returnFlow?.step === "proof" ? 1000
                  : 4000
                }
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={
                  loginStep === "password" ? "Enter your password…"
                  : loginStep === "identifier" ? "Email ID or User ID…"
                  : loginStep === "confirm" ? "Select Yes or No…"
                  : addressForm ? ADDRESS_FORM_PROMPTS[addressForm.step]
                  : returnFlow?.step === "proof" ? "Describe the issue and provide proof…"
                  : placeholder
                }
                disabled={isLoading || loginStep === "busy"}
                autoComplete={
                  loginStep === "password" ? "current-password"
                  : loginStep === "identifier" ? "username"
                  : "off"
                }
              />
              <button
                type="submit"
                className="master-chatbot-send"
                disabled={!input || isLoading || loginStep === "busy"}
                aria-label="Send message"
              >
                <Send size={16} />
              </button>
            </form>
          </div>
        </section>
      )}
    </div>
  );
}
