import { adminRequest, delay } from "@/lib/api/client";
import { API_BASE_URL } from "@/lib/api/client";
import { SystemSettings } from "@/types";

const settings: SystemSettings = { appName: "Master Chatbot", defaultProvider: "Groq", defaultModel: "llama-3.1-8b-instant", backendUrl: API_BASE_URL, environment: "Development", version: "1.0.0" };
export async function getSettings() { await delay(); return settings; }
export async function updateSettings(data: Partial<SystemSettings>) { await delay(); return { ...settings, ...data }; }

export async function changePassword(data: { currentPassword: string; newPassword: string }) {
  return adminRequest<{ success: boolean }>("/auth/password", {
    method: "PUT",
    body: JSON.stringify({
      current_password: data.currentPassword,
      new_password: data.newPassword,
    }),
  });
}
