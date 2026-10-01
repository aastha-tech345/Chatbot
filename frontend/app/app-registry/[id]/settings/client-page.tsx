"use client";
import { useState } from "react";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AppTabBar, useAppRegistryId } from "../app-tabs";

const SIDE_TABS = ["General", "Authentication", "Rate Limiting", "Webhooks", "Advanced"];

export default function AppSettingsPage() {
  const id = useAppRegistryId();
  const [tab, setTab] = useState("General");

  return (
    <WithLayout>
      <BackLink />
      <PageHeader
        title="Application Settings"
        subtitle="Advanced configuration for this application"
      />

      <AppTabBar id={id} active="settings" />

      <div className="mt-5 grid gap-5 lg:grid-cols-[200px_1fr]">
        <Card className="h-fit p-2">
          <nav className="space-y-0.5">
            {SIDE_TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`w-full rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                  tab === t
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </nav>
        </Card>

        <Card>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">{tab} Settings</h2>
          </div>
          <div className="grid gap-4 p-5 md:grid-cols-2">
            <label className="grid gap-1.5">
              <span className="text-xs font-semibold text-foreground">Application Name</span>
              <Input defaultValue="E-commerce" />
            </label>
            <label className="grid gap-1.5">
              <span className="text-xs font-semibold text-foreground">Timeout (seconds)</span>
              <Input type="number" defaultValue={30} />
            </label>
            <label className="grid gap-1.5">
              <span className="text-xs font-semibold text-foreground">Max Retries</span>
              <Input type="number" defaultValue={3} />
            </label>
            <label className="flex items-center gap-2.5">
              <input type="checkbox" defaultChecked className="h-4 w-4 accent-primary" />
              <span className="text-sm font-medium text-foreground">Enable Caching</span>
            </label>
            <div className="md:col-span-2">
              <label className="grid gap-1.5">
                <span className="text-xs font-semibold text-foreground">Default Headers (JSON)</span>
                <Textarea
                  className="font-mono text-xs"
                  rows={5}
                  defaultValue={'{\n  "Content-Type": "application/json",\n  "Accept": "application/json"\n}'}
                />
              </label>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
            <Button variant="outline">Cancel</Button>
            <Button onClick={() => toast.success("Settings saved")}>Save Settings</Button>
          </div>
        </Card>
      </div>
    </WithLayout>
  );
}
