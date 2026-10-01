"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Eye, EyeOff, Package, Pill, ShoppingCart, Users } from "lucide-react";
import { useForm, Controller } from "react-hook-form";
import { Application } from "@/types";
import { applicationSchema, ApplicationFormValues } from "@/lib/validations/application";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { SearchableSelect } from "@/components/ui/searchable-select";

const ICONS = [
  { icon: ShoppingCart, label: "Shopping Cart" },
  { icon: Package, label: "Package" },
  { icon: Pill, label: "Pill" },
  { icon: Users, label: "Users" },
];

const APPLICATION_TYPES = [
  "Web Application",
  "REST API",
  "Internal Service",
  "External API",
];

const STATUSES = [
  "Active",
  "Inactive",
  "Testing",
];

export function ApplicationForm({
  initial,
  onSubmit,
  submitLabel = "Save Application",
}: {
  initial?: Application;
  submitLabel?: string;
  onSubmit: (values: ApplicationFormValues) => void;
}) {
  const [showServiceKey, setShowServiceKey] = useState(false);
  const {
    register,
    setError,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
    watch,
  } = useForm<ApplicationFormValues>({
    resolver: zodResolver(applicationSchema),
    defaultValues: {
      serviceKey: "",
      authType: initial?.authType || "none",
      name: initial?.name || "",
      appId: initial?.appId || "",
      description: initial?.description || "",
      type: initial?.type || "Web Application",
      baseUrl: initial?.baseUrl || "",
      docsUrl: initial?.docsUrl || "",
      status: initial?.status || "Active",
    },
    values: initial ? {
      serviceKey: "",
      authType: initial.authType || "none",
      name: initial.name || "",
      appId: initial.appId || "",
      description: initial.description || "",
      type: initial.type || "Web Application",
      baseUrl: initial.baseUrl || "",
      docsUrl: initial.docsUrl || "",
      status: initial.status || "Active",
    } : undefined,
  });

  const selectedType = watch("type");
  const selectedStatus = watch("status");

  return (
    <form onSubmit={handleSubmit((values) => {
      if (values.authType === "service_key" && !initial?.serviceKeyConfigured && !values.serviceKey?.trim()) {
        setError("serviceKey", { message: "Master Chatbot Service Key is required" });
        return;
      }
      return onSubmit(values);
    })} className="grid gap-5">
      {/* Basic info */}
      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">Basic Information</h2>
          <p className="text-xs text-muted-foreground mt-0.5">General details about your application</p>
        </div>
        <div className="grid gap-4 p-5 md:grid-cols-2">
          <Field label="Application Name *" error={errors.name?.message}>
            <Input placeholder="e.g. E-commerce" {...register("name")} />
          </Field>
          <Field label="Application Type">
            <Controller
              name="type"
              control={control}
              render={({ field }) => (
                <SearchableSelect
                  value={field.value || ""}
                  onChange={field.onChange}
                  options={APPLICATION_TYPES.map((type) => ({ value: type, label: type }))}
                  placeholder="Select application type..."
                />
              )}
            />
          </Field>
          <Field label="App ID *" error={errors.appId?.message}>
            <Input placeholder="e.g. ecommerce" {...register("appId")} />
          </Field>
          <Field label="Status">
            <Controller
              name="status"
              control={control}
              render={({ field }) => (
                <SearchableSelect
                  value={field.value || ""}
                  onChange={field.onChange}
                  options={STATUSES.map((status) => ({ value: status, label: status }))}
                  placeholder="Select status..."
                />
              )}
            />
          </Field>
          <div className="md:col-span-2">
            <Field label="Description">
              <Textarea
                placeholder="Brief description of this application"
                rows={3}
                {...register("description")}
              />
            </Field>
          </div>
        </div>
        <div className="border-t border-border px-5 py-3">
          <p className="mb-3 text-xs font-semibold text-foreground">Icon</p>
          <div className="flex gap-2">
            {ICONS.map(({ icon: Icon }, i) => (
              <button
                type="button"
                key={i}
                className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-muted text-muted-foreground hover:border-primary hover:bg-primary/10 hover:text-primary transition-colors"
                aria-label={`Icon option ${i + 1}`}
              >
                <Icon className="h-4 w-4" />
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* API config */}
      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">API Configuration</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Connection details for your application</p>
        </div>
        <div className="grid gap-4 p-5 md:grid-cols-2">
          <Field label="Base URL *" error={errors.baseUrl?.message}>
            <Input placeholder="https://api.yourapp.com" {...register("baseUrl")} />
          </Field>
          <Field label="Service authentication">
            <select className="rounded-md border border-border bg-background p-2" {...register("authType")}>
              <option value="none">Optional service key</option>
              <option value="service_key">Service key required</option>
              {initial?.authType && !["none", "service_key"].includes(initial.authType) && <option value={initial.authType}>{initial.authType}</option>}
            </select>
          </Field>
          <div className="grid gap-1.5 md:col-span-2">
            <label htmlFor="service-key" className="text-xs font-semibold">Master Chatbot Service Key</label>
            <div className="flex gap-2">
              <Input id="service-key" type={showServiceKey ? "text" : "password"} placeholder="Enter service key"
                autoComplete="new-password" aria-describedby="service-key-help" {...register("serviceKey")} />
              <Button type="button" variant="outline" aria-label={showServiceKey ? "Hide service key" : "Show service key"}
                aria-pressed={showServiceKey} onClick={() => setShowServiceKey(!showServiceKey)}>
                {showServiceKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            <p id="service-key-help" className="text-xs text-muted-foreground">Service key used by Master Chatbot to authorize requests to this application.</p>
            {initial?.serviceKeyConfigured && <p className="text-xs text-muted-foreground">Service Key: Configured. Leave blank to keep the existing key.</p>}
            {errors.serviceKey && <p className="text-xs text-destructive">{errors.serviceKey.message}</p>}
          </div>
          <Field label="OpenAPI JSON URL (optional)" error={errors.docsUrl?.message}>
            <Input placeholder="https://api.yourapp.com/api/v1/openapi.json" {...register("docsUrl")} />
          </Field>
        </div>
        <div className="border-t border-border px-5 py-4">
          <p className="text-xs text-muted-foreground">
            User authentication uses the incoming Authorization header. Chat requests also require the configured Master Chatbot Service Key.
          </p>
        </div>
      </Card>

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => history.back()}>Cancel</Button>
        <Button type="submit" disabled={isSubmitting}>{submitLabel}</Button>
      </div>
    </form>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-semibold text-foreground">{label}</span>
      {children}
      {error && <span className="text-xs text-destructive">{error}</span>}
    </label>
  );
}
