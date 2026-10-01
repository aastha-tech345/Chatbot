"use client";
import { useState } from "react";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Send, Trash2, Plus, X } from "lucide-react";
import { testRoute, getApplicationRoutes } from "@/lib/api/applications";
import { AppTabBar, useAppRegistryId } from "../app-tabs";
import { useQuery } from "@tanstack/react-query";

interface HeaderParam {
  id: string;
  key: string;
  value: string;
}

interface QueryParam {
  id: string;
  key: string;
  value: string;
}

const HEADER_OPTIONS = [
  "Authorization",
  "Accept",
  "Content-Type",
  "X-API-Key",
  "X-Request-Id",
  "X-Master-Chatbot-Service-Key",
];

const BODY_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function normalizeAuthorization(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.toLowerCase().startsWith("bearer ") ? trimmed : `Bearer ${trimmed}`;
}

function buildRequestHeaders(headers: HeaderParam[]): Record<string, string> {
  return headers.reduce<Record<string, string>>((acc, header) => {
    const key = header.key.trim();
    const value = header.value.trim();
    if (!key || !value) return acc;
    acc[key] = key.toLowerCase() === "authorization" ? normalizeAuthorization(value) : value;
    return acc;
  }, {});
}

export default function TestApplicationPage() {
  const id = useAppRegistryId();
  const [method, setMethod] = useState("GET");
  const [endpoint, setEndpoint] = useState("/");
  const [headers, setHeaders] = useState<HeaderParam[]>([]);
  const [queryParams, setQueryParams] = useState<QueryParam[]>([]);
  const [body, setBody] = useState('{\n  "key": "value"\n}');
  const [response, setResponse] = useState<{ status: number; time: string; body: unknown } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRoute, setSelectedRoute] = useState<string>("");

  const { data: routes } = useQuery({
    queryKey: ["routes", id],
    queryFn: () => getApplicationRoutes(id),
  });

  const handleAddHeader = () => {
    setHeaders([...headers, { id: Date.now().toString(), key: "Authorization", value: "" }]);
  };

  const handleRemoveHeader = (headerId: string) => {
    setHeaders(headers.filter((h) => h.id !== headerId));
  };

  const handleAddQueryParam = () => {
    setQueryParams([...queryParams, { id: Date.now().toString(), key: "", value: "" }]);
  };

  const handleRemoveQueryParam = (paramId: string) => {
    setQueryParams(queryParams.filter((p) => p.id !== paramId));
  };

  const handleClear = () => {
    setMethod("GET");
    setEndpoint("/");
    setHeaders([]);
    setQueryParams([]);
    setBody('{\n  "key": "value"\n}');
    setResponse(null);
    setSelectedRoute("");
  };

  const handleSendRequest = async () => {
    if (!endpoint.trim()) {
      toast.error("Please enter an endpoint");
      return;
    }

    setIsLoading(true);
    try {
      if (selectedRoute) {
        const selectedRouteConfig = routes?.items?.find((route) => route.id === selectedRoute);
        const requestHeaders = buildRequestHeaders(headers);
        const hasAuthorizationHeader = Object.keys(requestHeaders).some((key) => key.toLowerCase() === "authorization");
        console.info("[API_TEST] authorization_header_present=%s", hasAuthorizationHeader);
        if (selectedRouteConfig?.authRequired && !hasAuthorizationHeader) {
          toast.error("Authorization header is required for this endpoint.");
          setResponse({
            status: 401,
            time: "0ms",
            body: { detail: "Authorization header is required for this endpoint." },
          });
          return;
        }
        const requestQueryParams = queryParams.reduce<Record<string, string>>((acc, param) => {
          const key = param.key.trim();
          const value = param.value.trim();
          if (key) acc[key] = value;
          return acc;
        }, {});
        let requestBody: unknown;
        if (BODY_METHODS.has(method) && body.trim()) {
          try {
            requestBody = JSON.parse(body);
          } catch {
            toast.error("Body must be valid JSON");
            return;
          }
        }

        const result = await testRoute(selectedRoute, {
          method,
          headers: requestHeaders,
          query_params: requestQueryParams,
          body: requestBody,
        });
        setResponse({
          status: result.status_code || 200,
          time: `${result.response_time_ms || 0}ms`,
          body: Object.prototype.hasOwnProperty.call(result, "body") ? result.body : result,
        });
      } else {
        toast.error("Please select a route to test");
      }
    } catch (error) {
      toast.error("Failed to send request");
      setResponse({
        status: 500,
        time: "0ms",
        body: { error: String(error) },
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <WithLayout>
      <BackLink />
      <PageHeader
        title="Test Application"
        subtitle="Test API endpoints and inspect responses"
      />

      <AppTabBar id={id} active="test" />

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_420px]">
        {/* Request builder */}
        <Card>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Request Builder</h2>
          </div>
          <div className="p-5 space-y-4">
            {/* Select route */}
            <div>
              <label className="text-xs font-semibold text-foreground block mb-2">Select Route</label>
              <Select value={selectedRoute} onChange={(e) => {
                const route = routes?.items?.find((r) => r.id === e.target.value);
                if (route) {
                  setSelectedRoute(route.id);
                  setMethod(route.method);
                  setEndpoint(route.endpoint);
                }
              }}>
                <option value="">Choose a route...</option>
                {routes?.items?.map((route) => (
                  <option key={route.id} value={route.id}>
                    {route.method} {route.endpoint}
                  </option>
                ))}
              </Select>
            </div>

            {/* Method and endpoint */}
            <div className="flex gap-2">
              <Select value={method} onChange={(e) => setMethod(e.target.value)} className="w-28">
                <option>GET</option>
                <option>POST</option>
                <option>PUT</option>
                <option>DELETE</option>
                <option>PATCH</option>
              </Select>
              <Input
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                placeholder="/api/endpoint"
                className="flex-1"
              />
              <Button onClick={handleSendRequest} disabled={isLoading}>
                <Send className="h-4 w-4" /> {isLoading ? "Sending..." : "Send"}
              </Button>
            </div>

            {/* Headers */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold text-foreground">Headers</label>
                <Button size="sm" variant="ghost" onClick={handleAddHeader} className="h-6 gap-1">
                  <Plus className="h-3 w-3" /> Add
                </Button>
              </div>
              <div className="space-y-2">
                {headers.map((header) => (
                  <div key={header.id} className="flex gap-2">
                    <Select
                      value={header.key}
                      onChange={(e) => setHeaders(headers.map((h) => h.id === header.id ? { ...h, key: e.target.value } : h))}
                      className="flex-1"
                    >
                      <option value="">Select header</option>
                      {HEADER_OPTIONS.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                    <Input
                      placeholder="Value"
                      value={header.value}
                      onChange={(e) => setHeaders(headers.map((h) => h.id === header.id ? { ...h, value: e.target.value } : h))}
                      className="flex-1"
                    />
                    <Button size="sm" variant="ghost" onClick={() => handleRemoveHeader(header.id)}>
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            {/* Query Params */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold text-foreground">Query Parameters</label>
                <Button size="sm" variant="ghost" onClick={handleAddQueryParam} className="h-6 gap-1">
                  <Plus className="h-3 w-3" /> Add
                </Button>
              </div>
              <div className="space-y-2">
                {queryParams.map((param) => (
                  <div key={param.id} className="flex gap-2">
                    <Input
                      placeholder="Key"
                      value={param.key}
                      onChange={(e) => setQueryParams(queryParams.map((p) => p.id === param.id ? { ...p, key: e.target.value } : p))}
                      className="flex-1"
                    />
                    <Input
                      placeholder="Value"
                      value={param.value}
                      onChange={(e) => setQueryParams(queryParams.map((p) => p.id === param.id ? { ...p, value: e.target.value } : p))}
                      className="flex-1"
                    />
                    <Button size="sm" variant="ghost" onClick={() => handleRemoveQueryParam(param.id)}>
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            {/* Body */}
            <div>
              <label className="text-xs font-semibold text-foreground block mb-2">Body (JSON)</label>
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={!BODY_METHODS.has(method)}
                className="font-mono text-xs"
                rows={5}
              />
              {!BODY_METHODS.has(method) && (
                <p className="mt-1 text-xs text-muted-foreground">Body is not sent with {method} requests.</p>
              )}
            </div>

            <Button variant="outline" size="sm" onClick={handleClear} className="w-full">
              <Trash2 className="h-3.5 w-3.5" /> Clear All
            </Button>
          </div>
        </Card>

        {/* Response */}
        <Card>
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Response</h2>
            {response && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  response.status >= 200 && response.status < 300
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {response.status}
              </span>
            )}
          </div>
          <div className="p-5">
            {response && <p className="mb-3 text-xs text-muted-foreground">Response time: {response.time}</p>}
            <pre className="overflow-auto rounded-lg bg-gray-950 p-4 text-xs text-gray-100 min-h-[300px]">
              {response ? JSON.stringify(response.body, null, 2) : "Send a request to see response..."}
            </pre>
            {isLoading && <p className="mt-3 text-xs text-muted-foreground">Sending request...</p>}
          </div>
        </Card>
      </div>
    </WithLayout>
  );
}
