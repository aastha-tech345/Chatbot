"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { LogTable } from "@/components/logs/log-table";
import { getApplicationLogs } from "@/lib/api/logs";
import { AppTabBar, useAppRegistryId } from "../app-tabs";
import { FilterBar, PaginationCard, TableCard } from "@/components/common/table-layout";
import { LogLevel } from "@/types";

const PER_PAGE = 25;

const LEVEL_OPTIONS = [
  { value: "",        label: "All Levels" },
  { value: "INFO",    label: "INFO"       },
  { value: "SUCCESS", label: "SUCCESS"    },
  { value: "WARNING", label: "WARNING"    },
  { value: "ERROR",   label: "ERROR"      },
];

export default function AppLogsPage() {
  const id = useAppRegistryId();
  const [query,   setQuery]   = useState("");
  const [date,    setDate]    = useState("");
  const [level,   setLevel]   = useState<LogLevel | "">("");
  const [page,    setPage]    = useState(1);
  const [perPage, setPerPage] = useState(PER_PAGE);
  const { data = [], refetch, isFetching } = useQuery({
    queryKey: ["app-logs", id, level],
    queryFn: () => getApplicationLogs(id, { pageSize: 500, level: level || undefined }),
  });

  function clearFilters() { setQuery(""); setDate(""); setLevel(""); setPage(1); }

  const filtered = useMemo(
    () =>
      data.filter((log) => {
        if (date  && !log.timestamp.startsWith(date)) return false;
        if (query) {
          const q = query.toLowerCase();
          if (
            !log.message.toLowerCase().includes(q) &&
            !log.source.toLowerCase().includes(q)
          ) return false;
        }
        return true;
      }),
    [data, query, date, level]
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const paged      = filtered.slice((page - 1) * perPage, page * perPage);

  return (
    <WithLayout>
      <BackLink />
      <PageHeader
        title="Application Logs"
        subtitle="View conversation and API activity for this application"
        action={
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </Button>
        }
      />

      <AppTabBar id={id} active="logs" />

      <div className="mt-5">
        {/* ── FILTER BAR ── */}
        <FilterBar
          searchValue={query}
          onSearchChange={(v) => { setQuery(v); setPage(1); }}
          searchPlaceholder="Search messages or source…"
          dateValue={date}
          onDateChange={(v) => { setDate(v); setPage(1); }}
          filters={[
            {
              value:       level,
              onChange:    (v) => { setLevel(v as LogLevel | ""); setPage(1); },
              options:     LEVEL_OPTIONS,
              placeholder: "All Levels",
              width:       "w-36",
            },
          ]}
          onClear={clearFilters}
        />

        {/* ── TABLE CARD ── */}
        <TableCard>
          <LogTable logs={paged} />
        </TableCard>

        {/* ── PAGINATION CARD ── */}
        <PaginationCard
          page={page}
          total={totalPages}
          totalItems={filtered.length}
          perPage={perPage}
          onPageChange={(p) => setPage(p)}
          onPerPageChange={(n) => { setPerPage(n); setPage(1); }}
        />
      </div>
    </WithLayout>
  );
}
