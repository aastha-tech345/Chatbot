import { LogEntry } from "@/types";

export const logs: LogEntry[] = [
  { id: "l1", timestamp: "2026-09-14 12:45", level: "INFO", application: "ecommerce", source: "API Calls", message: "API route discovered: /products", status: "Success (200)", endpoint: "/products", responseTime: "120ms" },
  { id: "l2", timestamp: "2026-09-14 12:40", level: "SUCCESS", application: "chatbot", source: "Chat", message: "Conversation completed", status: "Success (200)", responseTime: "860ms" },
  { id: "l3", timestamp: "2026-09-14 12:30", level: "ERROR", application: "his", source: "API Calls", message: "Failed to fetch data: 404", status: "Failed (404)", endpoint: "/patients" },
  { id: "l4", timestamp: "2026-09-14 12:25", level: "INFO", application: "system", source: "System", message: "App registry updated", status: "Success" },
  { id: "l5", timestamp: "2026-09-14 12:20", level: "WARNING", application: "pharmacy", source: "System", message: "Rate limit reached", status: "Warning" }
];
