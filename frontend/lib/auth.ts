/**
 * Admin authentication — calls the real backend /api/v1/admin/auth/login.
 *
 * Falls back to env-var credentials only when NEXT_PUBLIC_USE_AUTH_FALLBACK=true.
 *
 * SECURITY:
 * - Access token stored in sessionStorage only (never localStorage, never cookies).
 * - Token is never logged or echoed in error messages.
 * - Refresh token stored separately and only used for /auth/refresh.
 */

import { apiRequest, setAccessToken, getAccessToken, clearAccessToken } from "@/lib/api/client";

const SESSION_KEY    = "mc_admin_auth";
const REFRESH_KEY    = "mc_refresh_token";

// Fallback credentials for when backend is not available
const FALLBACK_EMAIL    = process.env.NEXT_PUBLIC_ADMIN_EMAIL    ?? "admin@master-chatbot.local";
const FALLBACK_PASSWORD = process.env.NEXT_PUBLIC_ADMIN_PASSWORD ?? "Admin@123";
const USE_AUTH_FALLBACK = process.env.NEXT_PUBLIC_USE_AUTH_FALLBACK === "true";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AuthUser {
  id?: string;
  email: string;
  name: string;
  role?: string;
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  if (sessionStorage.getItem(SESSION_KEY) !== "1") return false;
  if (USE_AUTH_FALLBACK) return true;
  return Boolean(getAccessToken() || sessionStorage.getItem(REFRESH_KEY));
}

export async function login(payload: LoginPayload): Promise<AuthUser> {
  if (!USE_AUTH_FALLBACK) {
    try {
      const result = await apiRequest<{
        access_token: string;
        refresh_token?: string;
        user: { id: string; email: string; full_name: string; role: string };
      }>("/api/v1/admin/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: payload.email, password: payload.password }),
      });

      setAccessToken(result.access_token);
      if (result.refresh_token && typeof window !== "undefined") {
        sessionStorage.setItem(REFRESH_KEY, result.refresh_token);
      }
      sessionStorage.setItem(SESSION_KEY, "1");

      return {
        id:    result.user.id,
        email: result.user.email,
        name:  result.user.full_name,
        role:  result.user.role,
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed.";
      // Never expose token or internal details in the thrown message
      throw new Error(msg.includes("401") || msg.toLowerCase().includes("invalid")
        ? "Invalid email or password."
        : msg.includes("connect") || msg.includes("fetch") || msg.includes("Failed to fetch")
          ? "Unable to connect to server. Please try again."
          : msg);
    }
  }

  // Fallback: env-var based auth (no backend)
  await new Promise((r) => setTimeout(r, 500));
  if (
    payload.email.trim().toLowerCase() !== FALLBACK_EMAIL.toLowerCase() ||
    payload.password !== FALLBACK_PASSWORD
  ) {
    throw new Error("Invalid email or password.");
  }
  sessionStorage.setItem(SESSION_KEY, "1");
  return { email: FALLBACK_EMAIL, name: "Aastha" };
}

export function logout(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(SESSION_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
  clearAccessToken();
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(REFRESH_KEY);
}
