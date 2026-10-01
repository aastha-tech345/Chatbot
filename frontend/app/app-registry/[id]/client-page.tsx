"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, FileJson, Pencil, Play, Trash2, Bot } from "lucide-react";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/common/status-badge";
import { StatCard } from "@/components/common/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { deleteApplication, getApplication } from "@/lib/api/applications";
import { APP_TABS, AppTabBar, useAppRegistryId } from "./app-tabs";

export default function ApplicationDetailsPage() {
  const id = useAppRegistryId();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: app, isLoading } = useQuery({ queryKey: ["application", id], queryFn: () => getApplication(id) });
  const deleteMutation = useMutation({
    mutationFn: () => deleteApplication(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Application deleted");
      router.push("/app-registry");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Could not delete application"),
  });

  if (isLoading) return (
    <WithLayout>
      <BackLink />
      <div className="space-y-4">
        <Skeleton className="h-12 w-64" />
        <div className="grid gap-4 sm:grid-cols-4">{[1,2,3,4].map((i) => <Skeleton key={i} className="h-24" />)}</div>
        <Skeleton className="h-64" />
      </div>
    </WithLayout>
  );

  if (!app) return <WithLayout><BackLink /><Card className="p-6 text-muted-foreground">Application not found.</Card></WithLayout>;

  return (
    <WithLayout>
      <BackLink />
      <PageHeader
        title={app.name}
        subtitle={app.description}
        action={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={`/app-registry/${id}/edit`}><Pencil className="h-4 w-4" /> Edit</Link>
            </Button>
            <Button asChild>
              <Link href={`/app-registry/${id}/test`}><Play className="h-4 w-4" /> Test in Chat</Link>
            </Button>
          </div>
        }
      />

      <AppTabBar id={id} active="overview" />

      <div className="mt-5 grid gap-4 sm:grid-cols-4">
        <StatCard label="API Routes"      value={app.routes}               icon={FileJson}  tint="violet" />
        <StatCard label="Total API Calls" value="1.2K"                     icon={Activity}  tint="green"  />
        <StatCard label="Success Rate"    value={`${app.successRate}%`}    icon={Activity}  tint="blue"   />
        <StatCard label="Avg Response"    value={`${app.responseTime}ms`}  icon={Activity}  tint="amber"  />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_320px]">
        <Card>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Application Information</h2>
          </div>
          <div className="divide-y divide-border px-5">
            {Object.entries({
              Name:        app.name,
              "App ID":    app.appId,
              Type:        app.type,
              Description: app.description,
              "Base URL":  app.baseUrl,
              "Docs URL":  app.docsUrl,
              Status:      app.status,
              "Created":   app.createdAt,
              "Updated":   app.updatedAt,
            }).map(([k, v]) => (
              <div key={k} className="grid grid-cols-[140px_1fr] items-center py-3 text-sm">
                <span className="text-muted-foreground">{k}</span>
                <span className="text-foreground">
                  {k === "Status" ? <StatusBadge status={String(v)} /> : String(v)}
                </span>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">Quick Actions</h2>
            <div className="space-y-2">
              {([
                ["View API Documentation",   app.docsUrl                       ],
                ["Test Application",         `/app-registry/${id}/test`        ],
                ["Update Configuration",     `/app-registry/${id}/edit`        ],
                ["View Logs",                `/app-registry/${id}/logs`        ],
              ] as [string, string][]).map(([label, href]) => (
                <Button key={label} asChild variant="outline" className="w-full justify-start text-sm" size="sm">
                  <Link href={href}>{label}</Link>
                </Button>
              ))}
            </div>
          </Card>
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-destructive">Danger Zone</h2>
            <Button
              variant="destructive"
              className="w-full justify-start"
              size="sm"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (window.confirm("Delete this application from the registry?")) {
                  deleteMutation.mutate();
                }
              }}
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete Application
            </Button>
          </Card>
        </div>
      </div>
    </WithLayout>
  );
}
