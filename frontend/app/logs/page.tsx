"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import WithLayout from "@/components/layout/with-layout";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { LogTable } from "@/components/logs/log-table";
import { getLogs } from "@/lib/api/logs";
import { LogLevel } from "@/types";
import { FilterBar, PaginationCard, TableCard } from "@/components/common/table-layout";
import { TabBorderBar, TabBorderButton } from "@/components/ui/tabs";

const TABS = ["All Logs", "Chat Logs", "API Calls", "Errors", "System"] as const;
type Tab = (typeof TABS)[number];

const TAB_LEVEL_MAP:  Record<Tab, string> = {
  "All Logs": "", "Chat Logs": "", "API Calls": "INFO", "Errors": "ERROR", "System": "INFO",
};
const TAB_SOURCE_MAP: Record<Tab, string> = {
  "All Logs": "", "Chat Logs": "Chat", "API Calls": "API Calls", "Errors": "", "System": "System",
};

const LEVEL_OPTIONS = [
  { value: "",        label: "All Levels" },
  { value: "INFO",    label: "INFO"       },
  { value: "SUCCESS", label: "SUCCESS"    },
  { value: "WARNING", label: "WARNING"    },
  { value: "ERROR",   label: "ERROR"      },
];

const PER_PAGE = 25;

export default function LogsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("All Logs");
  const [query,    setQuery]   = useState("");
  const [app,      setApp]     = useState("");
  const [date,     setDate]    = useState("");
  const [level,    setLevel]   = useState<LogLevel | "">("");
  const [page,     setPage]    = useState(1);
  const [perPage,  setPerPage] = useState(PER_PAGE);
  const serverLevel = level || TAB_LEVEL_MAP[activeTab];
  const serverSource = TAB_SOURCE_MAP[activeTab];
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["logs", page, perPage, query, app, date, serverLevel, serverSource],
    queryFn: () => getLogs({
      page,
      pageSize: perPage,
      search: query || undefined,
      applicationId: app || undefined,
      level: serverLevel || undefined,
      source: serverSource || undefined,
    }),
  });

  function clearFilters() { setQuery(""); setApp(""); setDate(""); setLevel(""); setPage(1); }

  // Build app options dynamically from data
  const appOptions = useMemo(() => [
    { value: "", label: "All Applications" },
    ...Array.from(new Set((data?.items ?? []).map((l) => l.application)))
      .sort()
      .map((a) => ({ value: a, label: a })),
  ], [data]);

  const paged = data?.items ?? [];
  const totalItems = data?.total ?? 0;
  const totalPages = Math.max(1, data?.totalPages ?? 1);

  return (
    <WithLayout>
      <PageHeader
        title="Logs & Monitoring"
        subtitle="View system logs and API activity"
        action={
          <div className="flex gap-2">
            <Button variant="outline">
              <Download className="h-4 w-4" /> Export Logs
            </Button>
            <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
            </Button>
          </div>
        }
      />

      {/* ── FILTER BAR (with tabs in the header slot) ── */}
      <FilterBar
        searchValue={query}
        onSearchChange={(v) => { setQuery(v); setPage(1); }}
        searchPlaceholder="Search logs…"
        dateValue={date}
        onDateChange={(v) => { setDate(v); setPage(1); }}
        filters={[
          {
            value:       app,
            onChange:    (v) => { setApp(v); setPage(1); },
            options:     appOptions,
            placeholder: "All Applications",
            width:       "w-48",
          },
          {
            value:       level,
            onChange:    (v) => { setLevel(v as LogLevel | ""); setPage(1); },
            options:     LEVEL_OPTIONS,
            placeholder: "All Levels",
            width:       "w-36",
          },
        ]}
        onClear={clearFilters}
        header={
          <TabBorderBar className="border-0 gap-0">
            {TABS.map((tab) => (
              <TabBorderButton
                key={tab}
                active={activeTab === tab}
                onClick={() => { setActiveTab(tab); setPage(1); }}
              >
                {tab}
              </TabBorderButton>
            ))}
          </TabBorderBar>
        }
      />

      {/* ── TABLE CARD ── */}
      <TableCard>
        <LogTable logs={paged} />
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
    </WithLayout>
  );
}
