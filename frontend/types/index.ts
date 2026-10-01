export type AppStatus = "Active" | "Inactive" | "Testing";
export type ApiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type RouteStatus = "Available" | "Disabled" | "Error";
export type LogLevel = "INFO" | "SUCCESS" | "WARNING" | "ERROR";

export interface ApiRoute {
  id: string;
  method: ApiMethod;
  endpoint: string;
  name?: string;
  operationId?: string;
  description: string;
  authRequired: boolean;
  authType?: string;
  source?: "openapi" | "manual" | string;
  status: RouteStatus;
  updatedAt?: string;
  contentType?: string;
  headers?: Record<string, unknown>;
  queryParams?: Record<string, unknown>;
  pathParams?: Record<string, unknown>;
  requestBody?: Record<string, unknown>;
  responseSchema?: Record<string, unknown>;
}

export interface Application {
  authType?: string;
  serviceKeyConfigured?: boolean;
  id: string;
  name: string;
  appId: string;
  type: string;
  baseUrl: string;
  docsUrl: string;
  description: string;
  status: AppStatus;
  routes: number;
  totalCalls: number;
  successRate: number;
  responseTime: number;
  createdAt: string;
  updatedAt: string;
  icon: string;
  tags: string[];
  endpoints: ApiRoute[];
}

export interface ProviderModel {
  id: string;
  name: string;
}

export interface Provider {
  id: string;
  name: string;
  description: string;
  status: "Active" | "Inactive";
  models: ProviderModel[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  application: string;
  source: string;
  message: string;
  status: string;
  endpoint?: string;
  responseTime?: string;
  method?: string;
  requestId?: string;
  statusCode?: number;
  errorMessage?: string;
}

export interface SystemSettings {
  appName: string;
  defaultProvider: string;
  defaultModel: string;
  backendUrl: string;
  environment: string;
  version: string;
}
