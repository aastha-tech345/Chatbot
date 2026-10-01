import type { ReactNode } from "react";

export interface MasterChatbotWidgetResponse {
  message: string;
  conversation_id: string;
  intent?: string | null;
  data?: Array<Record<string, unknown>>;
  actions?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
}

export interface MasterChatbotMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  data?: Array<Record<string, unknown>>;
  actions?: Array<Record<string, unknown>>;
  intent?: string | null;
  metadata?: Record<string, unknown>;
}

export interface MasterChatbotWidgetError {
  type: "authentication" | "validation" | "service_error" | "timeout" | "network";
  message: string;
  retryable: boolean;
}

export interface MasterChatbotWidgetProps {
  appId: string;
  onSendMessage: (
    message: string,
    conversationId?: string,
    sessionId?: string,
    requestId?: string,
  ) => Promise<MasterChatbotWidgetResponse>;
  /** Host performs login and saves the session before resolving. */
  onLogin?: (credentials: { email: string; password: string }) => Promise<void>;
  isAuthenticated?: boolean;
  /** Clears private conversation data when the signed-in account changes. */
  accountId?: string;
  title?: string;
  placeholder?: string;
  avatar?: string;
  logo?: string;
  welcomeMessage?: string;
  suggestions?: string[];
  theme?: "light" | "dark";
  width?: string | number;
  height?: string | number;
  maxMessages?: number;
  ariaLabel?: string;
  initialMessages?: MasterChatbotMessage[];
  onError?: (error: MasterChatbotWidgetError) => void;
  onConversationStart?: (conversationId: string) => void;
  onConversationEnd?: () => void;
  onMessageReceived?: (message: MasterChatbotMessage) => void;
  renderMessage?: (message: MasterChatbotMessage) => ReactNode;
}
