/**
 * AI Provider API client
 */
import { apiRequest } from "./client";

export interface AIProviderModel {
  id: string;
  name: string;
}

export interface AIProvider {
  id: string;
  name: string;
  provider_key: string;
  description?: string;
  icon?: string;
  is_enabled: boolean;
  status: "Active" | "Inactive";
  models: AIProviderModel[];
  credential_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface CreateProviderPayload {
  name: string;
  provider_key: string;
  description?: string;
  icon?: string;
  is_enabled?: boolean;
}

export interface UpdateProviderPayload {
  name?: string;
  description?: string;
  icon?: string;
  is_enabled?: boolean;
}

function normalizeProvider(provider: Omit<AIProvider, "status" | "models"> & Partial<AIProvider>): AIProvider {
  return {
    ...provider,
    status: provider.is_enabled ? "Active" : "Inactive",
    models: provider.models ?? [],
  };
}

async function aiRequest<T>(adminPath: string, init?: RequestInit, retryAlias = true): Promise<T> {
  try {
    return await apiRequest<T>(`/api/v1/admin/ai${adminPath}`, init, true);
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (!retryAlias || !message.toLowerCase().includes("method not allowed")) throw error;
    return apiRequest<T>(`/api/v1/ai${adminPath}`, init, true);
  }
}

export async function getProviders(): Promise<AIProvider[]> {
  const providers = await aiRequest<Array<Omit<AIProvider, "status" | "models"> & Partial<AIProvider>>>("/providers");
  return providers.map(normalizeProvider);
}

export async function getProvider(id: string): Promise<AIProvider> {
  const provider = await aiRequest<Omit<AIProvider, "status" | "models"> & Partial<AIProvider>>(`/providers/${id}`);
  return normalizeProvider(provider);
}

export async function createProvider(
  payload: CreateProviderPayload
): Promise<AIProvider> {
  return aiRequest<AIProvider>("/providers", {
    method: "POST",
    body: JSON.stringify(payload),
  }, false);
}

export async function updateProvider(
  id: string,
  payload: UpdateProviderPayload
): Promise<AIProvider> {
  return aiRequest<AIProvider>(`/providers/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteProvider(id: string): Promise<{ success: boolean }> {
  return aiRequest<{ success: boolean }>(`/providers/${id}`, {
    method: "DELETE",
  });
}
