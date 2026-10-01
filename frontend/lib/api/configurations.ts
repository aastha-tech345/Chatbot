/**
 * AI Configuration (Credential) API client
 */
import { apiRequest } from "./client";

export interface AIConfiguration {
  id: string;
  provider_id: string;
  name: string;
  model: string;
  is_active: boolean;
  api_key_masked: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  last_tested_at?: string;
  last_test_status?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CreateConfigurationPayload {
  provider_id: string;
  name: string;
  api_key: string;
  model: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
}

export interface UpdateConfigurationPayload {
  name?: string;
  api_key?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
}

export async function getConfigurations(): Promise<AIConfiguration[]> {
  return apiRequest<AIConfiguration[]>(
    "/api/v1/admin/ai/credentials",
    {},
    true
  );
}

export async function getConfiguration(id: string): Promise<AIConfiguration> {
  return apiRequest<AIConfiguration>(
    `/api/v1/admin/ai/credentials/${id}`,
    {},
    true
  );
}

export async function createConfiguration(
  payload: CreateConfigurationPayload
): Promise<AIConfiguration> {
  return apiRequest<AIConfiguration>("/api/v1/admin/ai/credentials", {
    method: "POST",
    body: JSON.stringify(payload),
  }, true);
}

export async function updateConfiguration(
  id: string,
  payload: UpdateConfigurationPayload
): Promise<AIConfiguration> {
  return apiRequest<AIConfiguration>(`/api/v1/admin/ai/credentials/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, true);
}

export async function deleteConfiguration(
  id: string
): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/api/v1/admin/ai/credentials/${id}`, {
    method: "DELETE",
  }, true);
}

export async function testConfiguration(
  id: string
): Promise<{ success: boolean; message: string }> {
  return apiRequest<{ success: boolean; message: string }>(
    `/api/v1/admin/ai/credentials/${id}/test`,
    { method: "POST" },
    true
  );
}

export async function activateConfiguration(
  id: string
): Promise<AIConfiguration> {
  return apiRequest<AIConfiguration>(
    `/api/v1/admin/ai/credentials/${id}/activate`,
    { method: "POST" },
    true
  );
}

export async function deactivateConfiguration(
  id: string
): Promise<AIConfiguration> {
  return apiRequest<AIConfiguration>(
    `/api/v1/admin/ai/credentials/${id}/deactivate`,
    { method: "POST" },
    true
  );
}
