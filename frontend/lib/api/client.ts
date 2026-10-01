/**
 * API client with admin JWT token support.
 *
 * Token is stored in sessionStorage (same key used by auth.ts).
 * Never logs or echoes token values.
 */

function resolveApiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configuredUrl) return configuredUrl.replace(/\/$/, "");
  // The shared production domain routes /chatbot/ to Master Chatbot.
  return process.env.NODE_ENV === "development" ? "http://localhost:9000" : "/chatbot";
}

export const API_BASE_URL = resolveApiBaseUrl();

// ── Token storage (client-side only) ────────────────────────────────────────

const TOKEN_KEY = "mc_access_token";
const REFRESH_KEY = "mc_refresh_token";
const SESSION_KEY = "mc_admin_auth";

export function setAccessToken(token: string): void {
  if (typeof window !== "undefined") sessionStorage.setItem(TOKEN_KEY, token);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function clearAccessToken(): void {
  if (typeof window !== "undefined") sessionStorage.removeItem(TOKEN_KEY);
}

function clearAuthSession(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
  sessionStorage.removeItem(SESSION_KEY);
}

async function refreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const refreshToken = sessionStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return null;

  const response = await fetch(`${API_BASE_URL}/api/v1/admin/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearAuthSession();
    return null;
  }

  const body = await response.json().catch(() => ({}));
  const accessToken = typeof body?.access_token === "string" ? body.access_token : null;
  if (!accessToken) {
    clearAuthSession();
    return null;
  }

  setAccessToken(accessToken);
  return accessToken;
}

// ── Core request helper ──────────────────────────────────────────────────────

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
  withAuth = false,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (withAuth) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const requestInit = {
    ...init,
    headers,
  };

  let response = await fetch(`${API_BASE_URL}${path}`, requestInit);

  if (response.status === 401 && withAuth) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: { ...headers, Authorization: `Bearer ${refreshedToken}` },
      });
    } else {
      clearAuthSession();
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

/** Admin-authenticated request to /api/v1/admin/... */
export async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  return apiRequest<T>(`/api/v1/admin${path}`, init, true);
}

export const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));
