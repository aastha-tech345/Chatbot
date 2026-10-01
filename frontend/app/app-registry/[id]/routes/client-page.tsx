"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { ApiMethodBadge } from "@/components/common/badges";
import { StatusBadge } from "@/components/common/status-badge";
import { createManualRoute, deleteRoute, discoverApis, getApplicationRoutes, testRoute, updateRoute } from "@/lib/api/applications";
import { AppTabBar, useAppRegistryId } from "../app-tabs";
import { FilterBar, PaginationCard, TableCard } from "@/components/common/table-layout";
import { ApiMethod } from "@/types";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";

const PER_PAGE = 10;

const METHOD_OPTIONS = [
  { value: "",        label: "All Methods" },
  { value: "GET",     label: "GET"         },
  { value: "POST",    label: "POST"        },
  { value: "PUT",     label: "PUT"         },
  { value: "PATCH",   label: "PATCH"       },
  { value: "DELETE",  label: "DELETE"      },
];

const STATUS_OPTIONS = [
  { value: "",           label: "All Status"  },
  { value: "Available",  label: "Available"   },
  { value: "Disabled",   label: "Disabled"    },
  { value: "Error",      label: "Error"       },
];

export default function RoutesPage() {
  const id = useAppRegistryId();
  const qc = useQueryClient();

  const [query,      setQuery]      = useState("");
  const [method,     setMethod]     = useState<ApiMethod | "">("");
  const [routeStatus, setRouteStatus] = useState("");
  const [page,       setPage]       = useState(1);
  const [perPage,    setPerPage]    = useState(PER_PAGE);
  const [showAdd, setShowAdd] = useState(false);
  const [manual, setManual] = useState({
    name: "",
    method: "GET",
    path: "",
    description: "",
    operationId: "",
    authType: "none",
    contentType: "application/json",
    headers: "",
    queryParams: "",
    pathParams: "",
    requestBody: "",
    responseSchema: "",
  });
  const { data, isFetching } = useQuery({
    queryKey: ["routes", id, page, perPage, query, method, routeStatus],
    queryFn: () => getApplicationRoutes(id, {
      page,
      pageSize: perPage,
      q: query,
      method,
      status: routeStatus,
    }),
  });

  const rediscover = useMutation({
    mutationFn: () => discoverApis(id),
    onSuccess: (routes) => {
      setPage(1);
      qc.invalidateQueries({ queryKey: ["routes", id] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success(`${routes.length} endpoints discovered`);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Unable to rediscover APIs");
    },
  });

  const addManual = useMutation({
    mutationFn: () => createManualRoute(id, {
      name: manual.name || undefined,
      method: manual.method,
      path: manual.path,
      description: manual.description,
      operation_id: manual.operationId || undefined,
      auth_required: manual.authType !== "none",
      auth_type: manual.authType === "none" ? undefined : manual.authType,
      content_type: manual.contentType || undefined,
      headers_json: parseOptionalJson(manual.headers, "Headers"),
      query_params_json: parseOptionalJson(manual.queryParams, "Query parameters"),
      path_params_json: parseOptionalJson(manual.pathParams, "Path parameters"),
      request_body_json: parseOptionalJson(manual.requestBody, "Request body"),
      response_schema_json: parseOptionalJson(manual.responseSchema, "Response schema"),
    }),
    onSuccess: () => {
      setShowAdd(false);
      setManual({ name: "", method: "GET", path: "", description: "", operationId: "", authType: "none", contentType: "application/json", headers: "", queryParams: "", pathParams: "", requestBody: "", responseSchema: "" });
      qc.invalidateQueries({ queryKey: ["routes", id] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Manual API endpoint added");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Unable to add endpoint"),
  });

  const routeAction = useMutation({
    mutationFn: async ({ action, route }: { action: "test" | "delete" | "toggle"; route: any }) => {
      if (action === "test") return testRoute(route.id);
      if (action === "delete") return deleteRoute(route.id);
      return updateRoute(route.id, { status: route.status === "Available" ? "Disabled" : "Available" });
    },
    onSuccess: (result, vars) => {
      qc.invalidateQueries({ queryKey: ["routes", id] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      if (vars.action === "test" && result && typeof result === "object" && "status_code" in result) {
        toast.success(`Test returned HTTP ${result.status_code ?? "unknown"}`);
      } else {
        toast.success("Route updated");
      }
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Route action failed"),
  });

  function clearFilters() { setQuery(""); setMethod(""); setRouteStatus(""); setPage(1); }

  const paged = data?.items ?? [];
  const totalItems = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / perPage));

  return (
    <WithLayout>
      <BackLink />
      <PageHeader
        title="API Endpoints"
        subtitle="Manage and view discovered API endpoints"
        action={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setShowAdd((v) => !v)}>
              <Plus className="h-4 w-4" /> Add API Endpoint
            </Button>
            <Button variant="outline" onClick={() => rediscover.mutate()} disabled={rediscover.isPending}>
              <RefreshCw className={rediscover.isPending ? "h-4 w-4 animate-spin" : "h-4 w-4"} /> Rediscover APIs
            </Button>
          </div>
        }
      />

      <AppTabBar id={id} active="routes" />

      {showAdd && (
        <Card className="mt-5 p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="API Name"><Input value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} placeholder="list_customers" /></Field>
            <Field label="Method"><Select value={manual.method} onChange={(e) => setManual({ ...manual, method: e.target.value })}>{METHOD_OPTIONS.slice(1).map((m) => <option key={m.value}>{m.value}</option>)}</Select></Field>
            <Field label="Path"><Input value={manual.path} onChange={(e) => setManual({ ...manual, path: e.target.value })} placeholder="/api/customers" /></Field>
            <Field label="Operation ID"><Input value={manual.operationId} onChange={(e) => setManual({ ...manual, operationId: e.target.value })} placeholder="get_customers" /></Field>
            <Field label="Authentication"><Select value={manual.authType} onChange={(e) => setManual({ ...manual, authType: e.target.value })}><option value="none">None</option><option value="api_key">API Key</option><option value="bearer">Bearer Token</option><option value="basic">Basic Auth</option><option value="oauth2">OAuth2</option></Select></Field>
            <Field label="Content Type"><Input value={manual.contentType} onChange={(e) => setManual({ ...manual, contentType: e.target.value })} /></Field>
            <div className="md:col-span-2"><Field label="Description"><Textarea rows={2} value={manual.description} onChange={(e) => setManual({ ...manual, description: e.target.value })} /></Field></div>
            <Field label="Headers JSON"><Textarea rows={4} value={manual.headers} onChange={(e) => setManual({ ...manual, headers: e.target.value })} placeholder={'{"X-Tenant-ID":"tenant-123"}'} /></Field>
            <Field label="Query Params JSON"><Textarea rows={4} value={manual.queryParams} onChange={(e) => setManual({ ...manual, queryParams: e.target.value })} placeholder={'{"limit":{"value":20,"required":false}}'} /></Field>
            <Field label="Path Params JSON"><Textarea rows={4} value={manual.pathParams} onChange={(e) => setManual({ ...manual, pathParams: e.target.value })} placeholder={'{"customer_id":{"type":"string","required":true}}'} /></Field>
            <Field label="Request Body JSON"><Textarea rows={4} value={manual.requestBody} onChange={(e) => setManual({ ...manual, requestBody: e.target.value })} placeholder={'{"name":"John"}'} /></Field>
            <div className="md:col-span-2"><Field label="Response Schema JSON"><Textarea rows={4} value={manual.responseSchema} onChange={(e) => setManual({ ...manual, responseSchema: e.target.value })} /></Field></div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={() => addManual.mutate()} disabled={addManual.isPending}>Save Endpoint</Button>
          </div>
        </Card>
      )}

      <div className="mt-5">
        {/* ── FILTER BAR ── */}
        <FilterBar
          searchValue={query}
          onSearchChange={(v) => { setQuery(v); setPage(1); }}
          searchPlaceholder="Search endpoints…"
          filters={[
            {
              value:       method,
              onChange:    (v) => { setMethod(v as ApiMethod | ""); setPage(1); },
              options:     METHOD_OPTIONS,
              placeholder: "All Methods",
              width:       "w-36",
            },
            {
              value:       routeStatus,
              onChange:    (v) => { setRouteStatus(v); setPage(1); },
              options:     STATUS_OPTIONS,
              placeholder: "All Status",
              width:       "w-36",
            },
          ]}
          onClear={clearFilters}
        />

        {/* ── TABLE CARD ── */}
        <TableCard>
          <div className="overflow-x-auto">
            <table className="data-table w-full min-w-[640px]">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Endpoint</th>
                  <th>Source</th>
                  <th>Description</th>
                  <th>Auth Required</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((r) => (
                  <tr key={r.id}>
                    <td><ApiMethodBadge method={r.method} /></td>
                    <td className="font-mono text-xs text-foreground">{r.endpoint}</td>
                    <td className="text-muted-foreground">{r.source === "manual" ? "Manual" : "OpenAPI"}</td>
                    <td className="text-muted-foreground">{r.description}</td>
                    <td className="text-muted-foreground">{r.authRequired ? (r.authType || "Yes") : "No"}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => routeAction.mutate({ action: "test", route: r })}><Zap className="h-3.5 w-3.5" /> Test</Button>
                        <Button variant="ghost" size="sm" onClick={() => routeAction.mutate({ action: "toggle", route: r })}>{r.status === "Available" ? "Disable" : "Enable"}</Button>
                        {r.source === "manual" && <Button variant="ghost" size="sm" onClick={() => routeAction.mutate({ action: "delete", route: r })}><Trash2 className="h-3.5 w-3.5" /></Button>}
                      </div>
                    </td>
                  </tr>
                ))}
                {paged.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                      {isFetching ? "Loading endpoints..." : "No endpoints found."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </TableCard>

        {/* ── PAGINATION CARD ── */}
        <PaginationCard
          page={page}
          total={totalPages}
          totalItems={totalItems}
          perPage={perPage}
          onPageChange={(p) => setPage(p)}
          onPerPageChange={(n) => { setPerPage(n); setPage(1); }}
        />
      </div>
    </WithLayout>
  );
}

function parseOptionalJson(value: string, label: string): Record<string, unknown> | undefined {
  if (!value.trim()) return undefined;
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    return parsed;
  } catch {
    throw new Error(`${label} must be valid JSON object.`);
  }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="grid gap-1.5"><span className="text-xs font-semibold text-foreground">{label}</span>{children}</label>;
}
