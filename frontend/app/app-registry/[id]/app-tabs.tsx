"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export const APP_TABS = [
  { id: "overview",      label: "Overview",        href: (id: string) => `/app-registry/${id}` },
  { id: "routes",        label: "API Routes",       href: (id: string) => `/app-registry/${id}/routes` },
  { id: "configuration", label: "Configuration",    href: (id: string) => `/app-registry/${id}/configuration` },
  { id: "logs",          label: "Logs",             href: (id: string) => `/app-registry/${id}/logs` },
  { id: "test",          label: "Test",             href: (id: string) => `/app-registry/${id}/test` },
  { id: "settings",      label: "Settings",         href: (id: string) => `/app-registry/${id}/settings` },
] as const;

export type AppTabId = (typeof APP_TABS)[number]["id"];

export function useAppRegistryId() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const registryIndex = segments.indexOf("app-registry");
  return decodeURIComponent(segments[registryIndex + 1] ?? "");
}

export function AppTabBar({ id, active }: { id: string; active: AppTabId }) {
  return (
    <div className="flex items-center gap-0.5 overflow-x-auto border-b border-border pb-0">
      {APP_TABS.map((tab) => (
        <Link
          key={tab.id}
          href={tab.href(id)}
          className={cn(
            "shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
            active === tab.id
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
