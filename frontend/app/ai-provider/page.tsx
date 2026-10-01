"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Edit3, MoreVertical, Plus, Power, PowerOff, TestTube, Trash2 } from "lucide-react";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AIProvider,
  createProvider,
  getProviders,
} from "@/lib/api/providers";
import {
  AIConfiguration,
  CreateConfigurationPayload,
  UpdateConfigurationPayload,
  activateConfiguration,
  deactivateConfiguration,
  createConfiguration,
  deleteConfiguration,
  getConfigurations,
  testConfiguration,
  updateConfiguration,
} from "@/lib/api/configurations";
import { cn } from "@/lib/utils";

type ProviderForm = {
  name: string;
  provider_key: string;
  description: string;
  icon: string;
  is_enabled: boolean;
};

type ConfigForm = {
  provider_id: string;
  name: string;
  api_key: string;
  model: string;
  temperature: string;
  max_tokens: string;
  top_p: string;
};

function configToForm(config: AIConfiguration): ConfigForm {
  return {
    provider_id: config.provider_id,
    name: config.name,
    api_key: "",
    model: config.model,
    temperature: String(config.temperature ?? 0.7),
    max_tokens: String(config.max_tokens ?? 2048),
    top_p: String(config.top_p ?? 0.9),
  };
}

export default function AiProviderPage() {
  const queryClient = useQueryClient();
  const [providerDialog, setProviderDialog] = useState<"create" | null>(null);
  const [providerForm, setProviderForm] = useState<ProviderForm>({
    name: "", provider_key: "", description: "", icon: "", is_enabled: true,
  });
  const [configDialog, setConfigDialog] = useState<"create" | "edit" | null>(null);
  const [configForm, setConfigForm] = useState<ConfigForm>({
    provider_id: "", name: "", api_key: "", model: "",
    temperature: "0.7", max_tokens: "2048", top_p: "0.9",
  });
  const [editingConfig, setEditingConfig] = useState<AIConfiguration | null>(null);
  const [deleteConfigTarget, setDeleteConfigTarget] = useState<AIConfiguration | null>(null);

  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: getProviders });
  const configsQuery = useQuery({ queryKey: ["ai-configurations"], queryFn: getConfigurations });
  const providers = providersQuery.data ?? [];
  const configurations = configsQuery.data ?? [];
  const activeConfig = configurations.find((c) => c.is_active);

  const providerById = useMemo(
    () => new Map(providers.map((p) => [p.id, p])),
    [providers],
  );

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["providers"] });
    queryClient.invalidateQueries({ queryKey: ["ai-configurations"] });
  };

  const createProviderMutation = useMutation({
    mutationFn: createProvider,
    onSuccess: () => { toast.success("AI provider created"); setProviderDialog(null); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  const createConfigMutation = useMutation({
    mutationFn: createConfiguration,
    onSuccess: () => { toast.success("Configuration created"); setConfigDialog(null); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  const updateConfigMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateConfigurationPayload }) =>
      updateConfiguration(id, payload),
    onSuccess: () => { toast.success("Configuration updated"); setConfigDialog(null); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  const deleteConfigMutation = useMutation({
    mutationFn: deleteConfiguration,
    onSuccess: () => { toast.success("Configuration deleted"); setDeleteConfigTarget(null); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  const testConfigMutation = useMutation({
    mutationFn: testConfiguration,
    onSuccess: (r) => { toast[r.success ? "success" : "error"](r.message); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  const activateConfigMutation = useMutation({
    mutationFn: activateConfiguration,
    onSuccess: () => { toast.success("Configuration activated"); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  const deactivateConfigMutation = useMutation({
    mutationFn: deactivateConfiguration,
    onSuccess: () => { toast.success("Configuration deactivated"); refresh(); },
    onError: (e) => toast.error(e.message),
  });

  function openEditConfig(config: AIConfiguration) {
    setEditingConfig(config);
    setConfigForm(configToForm(config));
    setConfigDialog("edit");
  }

  function submitProvider(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!providerForm.name.trim() || !providerForm.provider_key.trim()) {
      toast.error("Provider name and key are required");
      return;
    }
    createProviderMutation.mutate({
      name: providerForm.name.trim(),
      provider_key: providerForm.provider_key.trim(),
      description: providerForm.description.trim() || undefined,
      icon: providerForm.icon.trim() || undefined,
      is_enabled: providerForm.is_enabled,
    });
  }

  function submitConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!configForm.name.trim() || !configForm.model.trim()) {
      toast.error("Configuration name and model are required");
      return;
    }
    if (configDialog === "create") {
      if (!configForm.api_key.trim()) { toast.error("API key is required"); return; }
      if (!configForm.provider_id)   { toast.error("Provider is required"); return; }
      createConfigMutation.mutate({
        provider_id: configForm.provider_id,
        name: configForm.name.trim(),
        api_key: configForm.api_key.trim(),
        model: configForm.model.trim(),
        temperature: Number(configForm.temperature),
        max_tokens: Number(configForm.max_tokens),
        top_p: Number(configForm.top_p),
      });
      return;
    }
    if (!editingConfig) return;
    const payload: UpdateConfigurationPayload = {
      name: configForm.name.trim(),
      model: configForm.model.trim(),
      temperature: Number(configForm.temperature),
      max_tokens: Number(configForm.max_tokens),
      top_p: Number(configForm.top_p),
    };
    if (configForm.api_key.trim()) payload.api_key = configForm.api_key.trim();
    updateConfigMutation.mutate({ id: editingConfig.id, payload });
  }

  return (
    <WithLayout>
      <PageHeader
        title="AI Provider"
        subtitle="Manage AI providers and encrypted runtime configurations"
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => {
              setProviderForm({ name: "", provider_key: "", description: "", icon: "", is_enabled: true });
              setProviderDialog("create");
            }}>
              <Plus className="h-4 w-4" />
              Add AI Provider
            </Button>
            <Button onClick={() => {
              setEditingConfig(null);
              setConfigForm({ provider_id: providers[0]?.id ?? "", name: "", api_key: "", model: "", temperature: "0.7", max_tokens: "2048", top_p: "0.9" });
              setConfigDialog("create");
            }}>
              <Plus className="h-4 w-4" />
              Add AI Configuration
            </Button>
          </div>
        }
      />

      <div className="space-y-5">
        {/* ── Current Active Configuration ── */}
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-foreground">Current Active Configuration</h2>
            {activeConfig && <Badge variant="default">Active</Badge>}
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <SummaryItem
              label="Provider"
              value={activeConfig ? providerById.get(activeConfig.provider_id)?.name ?? "Unknown" : "No active provider"}
            />
            <SummaryItem label="Configuration" value={activeConfig?.name ?? "No active configuration"} />
            <SummaryItem label="Model"         value={activeConfig?.model ?? "No model selected"} />
            <SummaryItem label="API Key"       value={activeConfig?.api_key_masked ?? "No key configured"} mono />
          </div>
          {activeConfig && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => testConfigMutation.mutate(activeConfig.id)}
                disabled={testConfigMutation.isPending}
              >
                <TestTube className="h-3.5 w-3.5" />
                {testConfigMutation.isPending ? "Testing..." : "Test Connection"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => deactivateConfigMutation.mutate(activeConfig.id)}
                disabled={deactivateConfigMutation.isPending}
                className="text-amber-600 hover:text-amber-700 dark:text-amber-500"
              >
                <PowerOff className="h-3.5 w-3.5" />
                {deactivateConfigMutation.isPending ? "Deactivating..." : "Deactivate"}
              </Button>
              <Button size="sm" onClick={() => openEditConfig(activeConfig)}>
                <Edit3 className="h-3.5 w-3.5" />
                Edit Active
              </Button>
            </div>
          )}
        </Card>

        {/* ── AI Configurations table ── */}
        <Card>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">AI Configurations</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Encrypted credentials and model settings
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="border-b border-border text-xs text-muted-foreground">
                <tr>
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Provider</th>
                  <th className="px-5 py-3 font-medium">Model</th>
                  <th className="px-5 py-3 font-medium">API Key</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {configurations.map((config) => (
                  <tr key={config.id} className="hover:bg-muted/40 transition-colors">
                    <td className="px-5 py-3 font-medium text-foreground">{config.name}</td>
                    <td className="px-5 py-3 text-muted-foreground">
                      {providerById.get(config.provider_id)?.name ?? "Unknown"}
                    </td>
                    <td className="px-5 py-3 text-muted-foreground">{config.model}</td>
                    <td className="px-5 py-3 font-mono text-xs text-muted-foreground">
                      {config.api_key_masked || "********"}
                    </td>
                    <td className="px-5 py-3">
                      {config.is_active
                        ? <Badge variant="default">Active</Badge>
                        : <Badge variant="secondary">Inactive</Badge>}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Test"
                          title="Test Connection"
                          onClick={() => testConfigMutation.mutate(config.id)}
                          disabled={testConfigMutation.isPending}
                        >
                          <TestTube className="h-3.5 w-3.5" />
                        </Button>
                        {config.is_active ? (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="Deactivate"
                            title="Deactivate"
                            onClick={() => deactivateConfigMutation.mutate(config.id)}
                            disabled={deactivateConfigMutation.isPending}
                            className="text-amber-500 hover:bg-amber-500/10 hover:text-amber-600"
                          >
                            <PowerOff className="h-3.5 w-3.5" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="Activate"
                            title="Activate"
                            onClick={() => activateConfigMutation.mutate(config.id)}
                            disabled={activateConfigMutation.isPending}
                            className="text-muted-foreground hover:text-primary"
                          >
                            <Power className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="Actions"
                              title="Actions"
                              className="text-muted-foreground hover:text-foreground"
                            >
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-32">
                            <DropdownMenuItem
                              onClick={() => openEditConfig(config)}
                              className="cursor-pointer gap-2"
                            >
                              <Edit3 className="h-3.5 w-3.5 text-muted-foreground" />
                              <span>Edit</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => setDeleteConfigTarget(config)}
                              className="cursor-pointer gap-2 text-destructive focus:bg-destructive/10 focus:text-destructive"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              <span>Delete</span>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </td>
                  </tr>
                ))}
                {!configurations.length && (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-sm text-muted-foreground">
                      No AI configurations found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* ── Edit/Create Configuration dialog ── */}
      <Dialog
        open={configDialog === "edit" || configDialog === "create"}
        title={configDialog === "create" ? "Add AI Configuration" : `Edit AI Configuration (${editingConfig?.api_key_masked || "masked"})`}
        onClose={() => setConfigDialog(null)}
      >
        <form className="space-y-4" onSubmit={submitConfig}>
          <Field label="Provider">
            <Select
              value={configForm.provider_id}
              onChange={(e) => setConfigForm((f) => ({ ...f, provider_id: e.target.value }))}
              disabled={configDialog === "edit"}
            >
              <option value="" disabled>Select provider</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Configuration Name">
            <Input
              value={configForm.name}
              onChange={(e) => setConfigForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </Field>
          <Field label={configDialog === "edit" ? "API Key (leave blank to keep existing)" : "API Key"}>
            <Input
              type="password"
              value={configForm.api_key}
              onChange={(e) => setConfigForm((f) => ({ ...f, api_key: e.target.value }))}
              placeholder={configDialog === "edit" ? "Leave blank to keep existing key" : ""}
              required={configDialog === "create"}
            />
          </Field>
          <Field label="Model">
            <Input
              value={configForm.model}
              onChange={(e) => setConfigForm((f) => ({ ...f, model: e.target.value }))}
              required
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Temperature">
              <Input type="number" min={0} max={2} step={0.1}
                value={configForm.temperature}
                onChange={(e) => setConfigForm((f) => ({ ...f, temperature: e.target.value }))} />
            </Field>
            <Field label="Max Tokens">
              <Input type="number" min={1} step={1}
                value={configForm.max_tokens}
                onChange={(e) => setConfigForm((f) => ({ ...f, max_tokens: e.target.value }))} />
            </Field>
            <Field label="Top P">
              <Input type="number" min={0} max={1} step={0.1}
                value={configForm.top_p}
                onChange={(e) => setConfigForm((f) => ({ ...f, top_p: e.target.value }))} />
            </Field>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setConfigDialog(null)}>Cancel</Button>
            <Button type="submit" disabled={updateConfigMutation.isPending || createConfigMutation.isPending}>
              <CheckCircle className="h-3.5 w-3.5" />
              {(updateConfigMutation.isPending || createConfigMutation.isPending) ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* ── Add AI Provider dialog ── */}
      <Dialog
        open={providerDialog === "create"}
        title="Add AI Provider"
        onClose={() => setProviderDialog(null)}
      >
        <form className="space-y-4" onSubmit={submitProvider}>
          <Field label="Provider Name">
            <Input value={providerForm.name} onChange={(e) => setProviderForm((f) => ({ ...f, name: e.target.value }))} required />
          </Field>
          <Field label="Provider Key">
            <Input value={providerForm.provider_key} onChange={(e) => setProviderForm((f) => ({ ...f, provider_key: e.target.value }))} required />
          </Field>
          <Field label="Description">
            <Input value={providerForm.description} onChange={(e) => setProviderForm((f) => ({ ...f, description: e.target.value }))} />
          </Field>
          <label className="flex items-center gap-2.5">
            <input type="checkbox" checked={providerForm.is_enabled} onChange={(e) => setProviderForm((f) => ({ ...f, is_enabled: e.target.checked }))} className="h-4 w-4 accent-primary" />
            <span className="text-sm text-foreground">Enabled</span>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setProviderDialog(null)}>Cancel</Button>
            <Button type="submit" disabled={createProviderMutation.isPending}>
              <CheckCircle className="h-3.5 w-3.5" />
              {createProviderMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* ── Delete Configuration dialog ── */}
      <Dialog
        open={Boolean(deleteConfigTarget)}
        title="Delete Configuration?"
        onClose={() => setDeleteConfigTarget(null)}
      >
        <p className="text-sm text-muted-foreground">
          Delete <strong>{deleteConfigTarget?.name}</strong>? The stored encrypted key will be removed.
        </p>
        {deleteConfigTarget?.is_active && (
          <p className="mt-2 text-xs font-medium text-amber-500">
            Note: This configuration is currently active. Please deactivate it before deleting.
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setDeleteConfigTarget(null)}>Cancel</Button>
          <Button
            variant="destructive"
            disabled={deleteConfigMutation.isPending || deleteConfigTarget?.is_active}
            onClick={() => deleteConfigTarget && deleteConfigMutation.mutate(deleteConfigTarget.id)}
          >
            Delete
          </Button>
        </div>
      </Dialog>
    </WithLayout>
  );
}

function SummaryItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg bg-muted p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("mt-1 truncate text-sm font-semibold text-foreground", mono && "font-mono")}>
        {value}
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-semibold text-foreground">{label}</span>
      {children}
    </label>
  );
}
