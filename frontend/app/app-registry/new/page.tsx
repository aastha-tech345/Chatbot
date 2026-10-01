"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { ApplicationForm } from "@/components/applications/application-form";
import { createApplication, discoverApis } from "@/lib/api/applications";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ApiMethodBadge } from "@/components/common/badges";
import { ApplicationFormValues } from "@/lib/validations/application";
import { cn } from "@/lib/utils";
import { ApiRoute, Application } from "@/types";

const STEPS = [
  { id: 1, label: "Basic Info",    desc: "Name and type" },
  { id: 2, label: "API Config",    desc: "URLs and auth"  },
  { id: 3, label: "Discovery",     desc: "Find routes"   },
  { id: 4, label: "Review",        desc: "Confirm"       },
];

export default function NewApplicationPage() {
  const serviceKey = useRef("");
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState<ApplicationFormValues | null>(null);
  const [registeredApp, setRegisteredApp] = useState<Application | null>(null);
  const [routes, setRoutes] = useState<ApiRoute[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const router = useRouter();
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: async (values: ApplicationFormValues) => {
      const app = await createApplication({ ...values, serviceKey: serviceKey.current });
      serviceKey.current = "";
      return app;
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Unable to register application"),
    onSuccess: (app) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Application registered successfully");
      router.push(`/app-registry/${app.id}`);
    },
  });

  async function runDiscovery() {
    if (!formData) return;
    setDiscovering(true);
    try {
      const app = registeredApp ?? await createApplication({ ...formData, serviceKey: serviceKey.current });
      serviceKey.current = "";
      setRegisteredApp(app);
      if (!formData.docsUrl?.trim()) {
        setRoutes([]);
        qc.invalidateQueries({ queryKey: ["applications"] });
        toast.success("Application registered. Add APIs manually from the API Endpoints tab.");
        setStep(4);
        return;
      }
      const discovered = await discoverApis(app.id);
      setRoutes(discovered);
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["routes", app.id] });
      toast.success(`${discovered.length} endpoints discovered`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to discover APIs");
    } finally {
      setDiscovering(false);
    }
  }

  return (
    <WithLayout>
      <BackLink />
      <PageHeader title="Register New Application" subtitle="Connect a new application to your Master Chatbot" />

      {/* Step indicator */}
      <div className="mb-6 flex items-center gap-0">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex flex-1 items-center">
            <button
              onClick={() => !registeredApp && step > s.id && setStep(s.id)}
              className="flex items-center gap-2.5 group"
            >
              <div className={cn(
                "grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-bold border-2 transition-colors",
                step === s.id  ? "bg-primary border-primary text-white"
                : step > s.id  ? "bg-primary/10 border-primary text-primary"
                :                "bg-muted border-border text-muted-foreground"
              )}>
                {step > s.id ? <Check className="h-4 w-4" /> : s.id}
              </div>
              <div className="hidden sm:block">
                <p className={cn("text-xs font-semibold", step >= s.id ? "text-foreground" : "text-muted-foreground")}>{s.label}</p>
                <p className="text-2xs text-muted-foreground">{s.desc}</p>
              </div>
            </button>
            {i < STEPS.length - 1 && (
              <div className={cn("mx-2 h-px flex-1", step > s.id ? "bg-primary" : "bg-border")} />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      {step <= 2 && (
        <ApplicationForm
          submitLabel="Next: API Discovery"
          onSubmit={({ serviceKey: secret, ...values }) => { serviceKey.current = secret || ""; setKeyConfigured(Boolean(secret)); setFormData(values); setStep(3); }}
        />
      )}

      {step === 3 && (
        <Card>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">OpenAPI Discovery</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Optional. If your application does not expose OpenAPI, continue and add APIs manually after registration.</p>
          </div>
          <div className="p-5">
            <Button onClick={runDiscovery} disabled={discovering} variant="outline">
              {discovering ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {discovering ? "Discovering..." : "Discover APIs"}
            </Button>

            {!discovering && (
              <div className="mt-4 space-y-1.5">
                {[
                  "Connected to application",
                  "Fetched OpenAPI specification",
                  "Analyzed endpoint structure",
                  `${routes.length} API routes ready`,
                ].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Check className="h-3.5 w-3.5 text-success shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-5 space-y-1.5">
              {routes.map((r) => (
                <label key={r.id} className="flex items-center gap-3 rounded-md border border-border p-2.5 text-sm cursor-pointer hover:bg-muted transition-colors">
                  <input type="checkbox" defaultChecked className="h-4 w-4 accent-primary" />
                  <ApiMethodBadge method={r.method} />
                  <span className="font-mono text-xs text-foreground">{r.endpoint}</span>
                  <span className="text-xs text-muted-foreground">{r.description}</span>
                </label>
              ))}
              {!discovering && routes.length === 0 && (
                <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                  {formData?.docsUrl?.trim()
                    ? "Click Discover APIs to load routes from the OpenAPI JSON URL."
                    : "No OpenAPI URL provided. The application will use manual API registration."}
                </div>
              )}
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" disabled={Boolean(registeredApp)} onClick={() => setStep(2)}>Back</Button>
              <Button onClick={() => setStep(4)}>Review & Save</Button>
            </div>
          </div>
        </Card>
      )}

      {step === 4 && (
        <Card>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Review & Confirm</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Confirm the details before registering the application</p>
          </div>
          <div className="p-5">
            <dl className="grid gap-3 sm:grid-cols-2">
              {Object.entries({
                "Application Name":   formData?.name     || "—",
                "App ID":             formData?.appId    || "—",
                "Base URL":           formData?.baseUrl  || "—",
                "Service Key":        (registeredApp?.serviceKeyConfigured ?? keyConfigured) ? "Configured" : "Not configured",
                "Routes Discovered":  formData?.docsUrl?.trim() ? `${routes.length} endpoints` : "Manual registration",
                "Initial Status":     formData?.status || "Active",
              }).map(([k, v]) => (
                <div key={k} className="rounded-lg bg-muted p-3">
                  <dt className="text-xs text-muted-foreground">{k}</dt>
                  <dd className="mt-0.5 text-sm font-semibold text-foreground">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setStep(3)}>Back</Button>
              <Button
                onClick={() => {
                  if (registeredApp) {
                    toast.success("Application registered successfully");
                    router.push(`/app-registry/${registeredApp.id}`);
                    return;
                  }
                  if (formData) create.mutate(formData);
                }}
                disabled={create.isPending}
              >
                {create.isPending ? "Saving..." : "Register Application"}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </WithLayout>
  );
}
