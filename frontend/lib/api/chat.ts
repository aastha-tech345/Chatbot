import { delay } from "@/lib/api/client";

export async function sendMessage(data: { message: string; application: string }) {
  await delay(700);
  return { id: crypto.randomUUID(), role: "assistant" as const, content: data.message.toLowerCase().includes("product") ? "Here are the available products:" : "I checked the connected applications and found a matching workflow." };
}
export async function getConversations() { await delay(); return []; }
export async function getConversation() { await delay(); return null; }
