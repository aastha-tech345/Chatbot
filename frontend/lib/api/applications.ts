/**
 * Applications API — calls the real backend App Registry endpoints.
 */
import { API_BASE_URL, adminRequest } from "@/lib/api/client";
import { Application, ApiRoute } from "@/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

function mapBackendApp(raw: Record<string, unknown>): Application {
  const openapiUrl = String(raw.openapi_url ?? raw.api_docs_url ?? "");
  return {
    serviceKeyConfigured: Boolean(raw.service_key_configured),
    authType: String(raw.auth_type ?? "none"),
    id:           String(raw.id ?? ""),
    name:         String(raw.name ?? ""),
    appId:        String(raw.app_id ?? ""),
    type:         String(raw.application_type ?? "Web Application"),
    baseUrl:      String(raw.base_url ?? ""),
    docsUrl:      openapiUrl,
    description:  String(raw.description ?? ""),
    status:       (raw.status === "active" ? "Active"
                 : raw.status === "inactive" ? "Inactive"
                 : "Testing") as Application["status"],
    routes:       Number(raw.route_count ?? 0),
    totalCalls:   0,
    successRate:  0,
    responseTime: 0,
    createdAt:    String(raw.created_at ?? ""),
    updatedAt:    String(raw.updated_at ?? ""),
    icon:         String(raw.icon ?? ""),
    tags:         [],
    endpoints:    [],
  };
}

function mapBackendRoute(raw: Record<string, unknown>): ApiRoute {
  return {
    id:          String(raw.id ?? ""),
    method:      String(raw.method ?? "GET") as ApiRoute["method"],
    endpoint:    String(raw.path ?? ""),
    name:        raw.name ? String(raw.name) : undefined,
    operationId: raw.operation_id ? String(raw.operation_id) : undefined,
    description: String(raw.description ?? raw.summary ?? ""),
    authRequired: Boolean(raw.auth_required),
    authType:    raw.auth_type ? String(raw.auth_type) : undefined,
    source:      String(raw.source ?? "openapi"),
    status:      (raw.is_enabled ? "Available" : "Disabled") as ApiRoute["status"],
    updatedAt:   String(raw.updated_at ?? ""),
    contentType: raw.content_type ? String(raw.content_type) : undefined,
    headers:     raw.headers_json as Record<string, unknown> | undefined,
    queryParams: raw.query_params_json as Record<string, unknown> | undefined,
    pathParams:  raw.path_params_json as Record<string, unknown> | undefined,
    requestBody: raw.request_body_json as Record<string, unknown> | undefined,
    responseSchema: raw.response_schema_json as Record<string, unknown> | undefined,
  };
}

// ── CRUD ─────────────────────────────────────────────────────────────────────

export interface PaginatedApplications {
  items: Application[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * List applications with server-side pagination, search, and filtering.
 * This is the primary function used by the App Registry page.
 */
export async function listApplicationsPaginated(options: {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  application_type?: string;
  category?: string;
  is_enabled?: boolean;
  sort_by?: string;
  sort_order?: string;
} = {}): Promise<PaginatedApplications> {
  const params = new URLSearchParams();
  params.set("page", String(options.page ?? 1));
  params.set("page_size", String(options.page_size ?? 10));
  if (options.search) params.set("search", options.search);
  if (options.status) params.set("status", options.status);
  if (options.application_type) params.set("application_type", options.application_type);
  if (options.category) params.set("category", options.category);
  if (options.is_enabled !== undefined) params.set("is_enabled", String(options.is_enabled));
  if (options.sort_by) params.set("sort_by", options.sort_by);
  if (options.sort_order) params.set("sort_order", options.sort_order);
  const raw = await adminRequest<Record<string, unknown>>(`/applications?${params.toString()}`);
  return {
    items: (raw.items as Record<string, unknown>[]).map(mapBackendApp),
    total: Number(raw.total ?? 0),
    page: Number(raw.page ?? 1),
    page_size: Number(raw.page_size ?? 10),
    total_pages: Number(raw.total_pages ?? 1),
  };
}

export async function getApplications(options?: {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  application_type?: string;
  category?: string;
  is_enabled?: boolean;
  sort_by?: string;
  sort_order?: string;
}): Promise<PaginatedApplications> {
  return listApplicationsPaginated(options);
}

export async function getApplication(id: string): Promise<Application> {
  const raw = await adminRequest<Record<string, unknown>>(`/applications/${id}`);
  return mapBackendApp(raw);
}

export async function createApplication(data: Partial<Application> & { serviceKey?: string }): Promise<Application> {
  if (data.serviceKey) requireSecureServiceKeyTransport();
  const openapiUrl = data.docsUrl?.trim() || undefined;
  const payload = {
      name:             data.name,
      app_id:           data.appId,
      description:      data.description,
      application_type: data.type?.toLowerCase().replace(/\s+/g, "_") ?? "web_application",
      base_url:         data.baseUrl,
      api_docs_url:     openapiUrl,
      openapi_url:      openapiUrl,
      discovery_mode:   openapiUrl ? "hybrid" : "manual",
      status:           (data.status ?? "Testing").toLowerCase(),
      auth_type:         data.authType ?? "none",
      service_key:       data.serviceKey || undefined,
  };
  const raw = await adminRequest<Record<string, unknown>>("/applications", {
    method: "POST",
    body:   JSON.stringify(payload),
  });
  return mapBackendApp(raw);
}

export async function updateApplication(id: string, data: Partial<Application> & { serviceKey?: string }): Promise<Application> {
  if (data.serviceKey) requireSecureServiceKeyTransport();
  const openapiUrl = data.docsUrl?.trim() || undefined;
  const payload = {
      app_id:           data.appId,
      name:             data.name,
      description:      data.description,
      base_url:         data.baseUrl,
      api_docs_url:     openapiUrl,
      openapi_url:      openapiUrl,
      discovery_mode:   openapiUrl ? "hybrid" : "manual",
      application_type: data.type?.toLowerCase().replace(/\s+/g, "_"),
      status:           data.status?.toLowerCase(),
      is_enabled:       data.status !== "Inactive",
      auth_type:        data.authType,
      service_key:      data.serviceKey || undefined,
  };
  const raw = await adminRequest<Record<string, unknown>>(`/applications/${id}`, {
    method: "PUT",
    body:   JSON.stringify(payload),
  });
  return mapBackendApp(raw);
}

export async function updateApplicationStatus(id: string, status: string): Promise<Application> {
  const payload = {
    status: status.toLowerCase(),
    is_enabled: status !== "Inactive",
  };
  const raw = await adminRequest<Record<string, unknown>>(`/applications/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return mapBackendApp(raw);
}

export async function deleteApplication(id: string): Promise<boolean> {
  await adminRequest(`/applications/${id}`, { method: "DELETE" });
  return true;
}

export async function discoverApis(applicationId?: string): Promise<ApiRoute[]> {
  if (!applicationId) return [];
  const raw = await adminRequest<{ routes?: Record<string, unknown>[]; discovered?: number }>(
      `/applications/${applicationId}/discover`,
      { method: "POST" },
  );
  return (raw.routes ?? []).map(mapBackendRoute);
}

export async function getApplicationRoutes(
  id: string,
  options?: { page?: number; pageSize?: number; q?: string; method?: string; status?: string },
): Promise<{ items: ApiRoute[]; total: number; page: number; pageSize: number }> {
  const params = new URLSearchParams();
      params.set("page", String(options?.page ?? 1));
      params.set("page_size", String(options?.pageSize ?? 25));
      if (options?.q) params.set("q", options.q);
      if (options?.method) params.set("method", options.method);
      if (options?.status) params.set("status", options.status);
  const raw = await adminRequest<Record<string, unknown>[] | {
        items: Record<string, unknown>[];
        total: number;
        page: number;
        page_size: number;
  }>(`/applications/${id}/routes?${params.toString()}`);
      if (Array.isArray(raw)) {
        const items = raw.map(mapBackendRoute);
        return { items, total: items.length, page: 1, pageSize: items.length || 25 };
      }
      return {
        items: raw.items.map(mapBackendRoute),
        total: Number(raw.total ?? 0),
        page: Number(raw.page ?? options?.page ?? 1),
        pageSize: Number(raw.page_size ?? options?.pageSize ?? 25),
      };
}

export async function updateRoute(id: string, data: Partial<ApiRoute>): Promise<ApiRoute> {
  await adminRequest(`/routes/${id}/status`, {
      method: "PUT",
      body:   JSON.stringify({ is_enabled: data.status === "Available" }),
  });
  return { id, ...data } as ApiRoute;
}

export interface ManualRouteInput {
  method: string;
  path?: string;
  operation_id?: string;
  name?: string;
  description?: string;
  auth_required?: boolean;
  auth_type?: string;
  is_enabled?: boolean;
  headers_json?: Record<string, unknown>;
  query_params_json?: Record<string, unknown>;
  path_params_json?: Record<string, unknown>;
  request_body_json?: Record<string, unknown>;
  response_schema_json?: Record<string, unknown>;
  content_type?: string;
}

export async function createManualRoute(appId: string, data: ManualRouteInput): Promise<ApiRoute> {
  const raw = await adminRequest<Record<string, unknown>>(`/applications/${appId}/routes`, {
    method: "POST",
    body: JSON.stringify(data),
  });
  return mapBackendRoute(raw);
}

export async function deleteRoute(id: string): Promise<boolean> {
  await adminRequest(`/routes/${id}`, { method: "DELETE" });
  return true;
}

export async function testRoute(
  id: string,
  data: {
    method?: string;
    headers?: Record<string, string>;
    query_params?: Record<string, string>;
    body?: unknown;
  } = {},
): Promise<{ success: boolean; status_code?: number; response_time_ms?: number; body?: unknown; error?: string; message?: string }> {
  const authorization = Object.entries(data.headers ?? {}).find(
    ([key]) => key.toLowerCase() === "authorization",
  )?.[1];
  return adminRequest(`/routes/${id}/test`, {
    method: "POST",
    headers: authorization ? { "X-API-Test-Authorization": authorization } : undefined,
    body: JSON.stringify(data),
  });
}

export async function testApplication(): Promise<{ status: string; time: string; body: object }> {
  return { status: "Not run", time: "0ms", body: {} };
}

export function isSecureServiceKeyTransport(apiBaseUrl: string, pageOrigin: string): boolean {
  const url = new URL(apiBaseUrl, pageOrigin);
  if (url.protocol === "https:") return true;

  const loopbackHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
  const page = new URL(pageOrigin);
  const isLoopbackDevelopment =
    url.protocol === "http:" &&
    loopbackHosts.has(url.hostname) &&
    loopbackHosts.has(page.hostname);
  return isLoopbackDevelopment;
}

function requireSecureServiceKeyTransport(): void {
  if (!isSecureServiceKeyTransport(API_BASE_URL, window.location.origin)) {
    throw new Error("Use an HTTPS API connection to save a service key.");
  }
}
