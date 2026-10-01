/**
 * Logs API — reads persisted backend API request logs.
 */
import { adminRequest } from "@/lib/api/client";
import { LogEntry } from "@/types";

export interface LogQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  applicationId?: string;
  level?: string;
  status?: string;
  method?: string;
  source?: string;
}

export interface PaginatedLogs {
  items: LogEntry[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

function mapLog(raw: Record<string, unknown>): LogEntry {
  const statusCode = Number(raw.status_code ?? 0);
  const statusStr = String(
    raw.status ??
      (statusCode >= 400
        ? `Failed (${statusCode})`
        : statusCode > 0
          ? `Success (${statusCode})`
          : "Recorded")
  );
  return {
    id:           String(raw.id ?? ""),
    timestamp:    String(raw.created_at ?? "").replace("T", " ").slice(0, 19),
    level:        String(raw.level ?? "INFO") as LogEntry["level"],
    application:  String(raw.application_id ?? "system"),
    source:       String(raw.source ?? "System"),
    message:      String(raw.message ?? ""),
    status:       statusStr,
    endpoint:     raw.endpoint ? String(raw.endpoint) : undefined,
    responseTime: raw.response_time_ms ? `${raw.response_time_ms}ms` : undefined,
    method:       raw.method ? String(raw.method) : undefined,
    requestId:    raw.request_id ? String(raw.request_id) : undefined,
    statusCode:   raw.status_code ? Number(raw.status_code) : undefined,
    errorMessage: raw.error_message ? String(raw.error_message) : undefined,
  };
}

function logsQuery(options: LogQuery = {}): string {
  const params = new URLSearchParams();
  params.set("page", String(options.page ?? 1));
  params.set("page_size", String(options.pageSize ?? 25));
  if (options.search) params.set("search", options.search);
  if (options.applicationId) params.set("application_id", options.applicationId);
  if (options.level) params.set("level", options.level);
  if (options.status) params.set("status", options.status);
  if (options.method) params.set("method", options.method);
  if (options.source) params.set("source", options.source);
  return `?${params.toString()}`;
}

export async function getLogs(options: LogQuery = {}): Promise<PaginatedLogs> {
  const raw = await adminRequest<Record<string, unknown>>(`/logs${logsQuery(options)}`);
  return {
    items: ((raw.items as Record<string, unknown>[]) ?? []).map(mapLog),
    total: Number(raw.total ?? 0),
    page: Number(raw.page ?? options.page ?? 1),
    pageSize: Number(raw.page_size ?? options.pageSize ?? 25),
    totalPages: Number(raw.total_pages ?? 1),
  };
}

export async function getApplicationLogs(id: string, options: Omit<LogQuery, "applicationId"> = {}): Promise<LogEntry[]> {
  const params = new URLSearchParams();
  params.set("page_size", String(options.pageSize ?? 100));
  if (options.level) params.set("level", options.level);
  const raw = await adminRequest<Record<string, unknown>[]>(`/applications/${id}/logs?${params.toString()}`);
  return raw.map(mapLog);
}
