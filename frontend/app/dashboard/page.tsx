"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, Bot, MessageSquare, Plus, Route,
  ShieldCheck, Sparkles, ArrowRight, Clock,
} from "lucide-react";
import WithLayout from "@/components/layout/with-layout";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { IllustrationNoApps } from "@/components/ui/illustrations";
import { getApplications } from "@/lib/api/applications";
import { getLogs } from "@/lib/api/logs";

const QUICK_ACTIONS = [
  { label: "Register New App",      href: "/app-registry/new", icon: Plus },
  { label: "Test Chatbot",          href: "/chat",             icon: MessageSquare },
  { label: "Configure AI Provider", href: "/ai-provider",      icon: Sparkles },
  { label: "View Logs",             href: "/logs",             icon: Activity },
] as const;

export default function DashboardPage() {
  const { data: result, isLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: () => getApplications(),
  });

  const { data: logsData } = useQuery({
    queryKey: ["recent-activity"],
    queryFn: () => getLogs({ pageSize: 5 }),
  });

  const data = result?.items ?? [];
  const active      = data.filter((a) => a.status === "Active").length;
  const totalRoutes = data.reduce((n, a) => n + a.routes, 0);
  const recentActivity = logsData?.items ?? [];

  const formatActivityMessage = (log: any) => {
    if (log.endpoint) {
      return `${log.method} ${log.endpoint} - ${log.status}`;
    }
    return log.message || "System activity";
  };

  const formatActivityTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return "just now";
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return "recently";
    }
  };

  return (
    <WithLayout>
      <PageHeader
        title="Dashboard"
        subtitle="Overview of your Master Chatbot system"
        action={
          <Button asChild>
            <Link href="/app-registry/new">
              <Plus className="h-4 w-4" /> Add Application
            </Link>
          </Button>
        }
      />

      {/* Stat cards */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-[88px]" />)}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Total Applications"  value={result?.total ?? data.length} icon={Bot}           tint="violet" />
          <StatCard label="Active Applications" value={active || 0}           icon={ShieldCheck}   tint="green"  />
          <StatCard label="Total API Routes"    value={totalRoutes || 0}     icon={Route}         tint="blue"   />
          <StatCard label="Requests Today"      value={logsData?.total || 0} icon={MessageSquare} tint="amber"  />
        </div>
      )}

      {/* Main grid */}
      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_300px]">

        {/* Application overview table */}
        <Card>
          <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
            <h2 className="text-sm font-semibold text-foreground">Application Overview</h2>
            <Button variant="ghost" size="sm" asChild className="gap-1 text-muted-foreground hover:text-foreground">
              <Link href="/app-registry">View All <ArrowRight className="h-3.5 w-3.5" /></Link>
            </Button>
          </div>

          {isLoading ? (
            <div className="space-y-2 p-4">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}
            </div>
          ) : data.length === 0 ? (
            <div className="flex flex-col items-center py-10">
              <IllustrationNoApps className="h-28 w-auto mb-3" />
              <p className="text-sm text-muted-foreground">No applications registered yet.</p>
              <Button asChild size="sm" className="mt-4">
                <Link href="/app-registry/new">Register Application</Link>
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table w-full min-w-[440px]">
                <thead>
                  <tr>
                    <th>Application</th>
                    <th>Status</th>
                    <th>Routes</th>
                    <th>Last Activity</th>
                  </tr>
                </thead>
                <tbody>
                  {data.slice(0, 6).map((app) => (
                    <tr key={app.id}>
                      <td>
                        <div className="flex items-center gap-2.5">
                          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary/10">
                            <Bot className="h-3.5 w-3.5 text-primary" />
                          </div>
                          <Link href={`/app-registry/${app.id}`}
                            className="font-medium text-foreground hover:text-primary transition-colors">
                            {app.name}
                          </Link>
                        </div>
                      </td>
                      <td><StatusBadge status={app.status} /></td>
                      <td className="text-muted-foreground">{app.routes}</td>
                      <td className="text-xs text-muted-foreground">{app.updatedAt.split(" ")[0]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Right column */}
        <div className="flex flex-col gap-5">

          {/* Recent activity */}
          <Card>
            <div className="border-b border-border px-5 py-3.5">
              <h2 className="text-sm font-semibold text-foreground">Recent Activity</h2>
            </div>
            <div className="divide-y divide-border">
              {recentActivity.length > 0 ? (
                recentActivity.map((log) => (
                  <div key={log.id} className="flex items-start gap-3 px-4 py-3">
                    <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-muted">
                      <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-foreground leading-tight truncate">{formatActivityMessage(log)}</p>
                      <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />{formatActivityTime(log.timestamp)}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="px-4 py-6 text-center">
                  <p className="text-sm text-muted-foreground">No recent activity</p>
                </div>
              )}
            </div>
          </Card>

          {/* Quick actions */}
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">Quick Actions</h2>
            <div className="grid gap-1.5">
              {QUICK_ACTIONS.map(({ label, href, icon: Icon }) => (
                <Link key={label} href={href}
                  className="group flex items-center justify-between rounded-md border border-border px-3 py-2.5 text-sm font-medium text-foreground transition-all hover:border-primary/30 hover:bg-primary/5 hover:text-primary">
                  <span className="flex items-center gap-2.5">
                    <Icon className="h-3.5 w-3.5 text-primary" />
                    {label}
                  </span>
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </WithLayout>
  );
}
