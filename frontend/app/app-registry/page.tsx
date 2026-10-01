"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle, Plus, Route, XCircle } from "lucide-react";
import { useState, useEffect, useCallback, useMemo } from "react";
import WithLayout from "@/components/layout/with-layout";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/common/stat-card";
import { ApplicationTable } from "@/components/applications/application-table";
import { deleteApplication, listApplicationsPaginated } from "@/lib/api/applications";
import { EmptyState } from "@/components/common/empty-error";
import { FilterBar, PaginationCard, TableCard } from "@/components/common/table-layout";
import { toast } from "sonner";

const PER_PAGE = 10;

const STATUS_OPTIONS = [
  { value: "",           label: "All Status"  },
  { value: "Active",     label: "Active"      },
  { value: "Inactive",   label: "Inactive"    },
  { value: "Testing",    label: "Testing"     },
];

export default function RegistryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();

  // Read from URL query params
  const page = parseInt(searchParams.get("page") || "1");
  const pageSize = parseInt(searchParams.get("page_size") || String(PER_PAGE));
  const search = searchParams.get("search") || "";
  const status = searchParams.get("status") || "";

  // Local state for debouncing
  const [searchInput, setSearchInput] = useState(search);
  const [debouncedSearch, setDebouncedSearch] = useState(search);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Sync URL when filters change
  const updateUrl = useCallback((p: number, ps: number, s: string, st: string) => {
    const params = new URLSearchParams();
    if (p > 1) params.set("page", String(p));
    if (ps !== PER_PAGE) params.set("page_size", String(ps));
    if (s) params.set("search", s);
    if (st) params.set("status", st);
    
    const query = params.toString();
    router.push(query ? `/app-registry?${query}` : "/app-registry");
  }, [router]);

  // Fetch data with server-side filtering
  const { data: result, isLoading, error } = useQuery({
    queryKey: ["applications", page, pageSize, debouncedSearch, status],
    queryFn: () => listApplicationsPaginated({
      page,
      page_size: pageSize,
      search: debouncedSearch,
      status: status || undefined,
    }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteApplication,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Application deleted");
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to delete application");
    },
  });

  function handleSearchChange(v: string) {
    setSearchInput(v);
  }

  function handleStatusChange(v: string) {
    updateUrl(1, pageSize, debouncedSearch, v);
  }

  function handlePageChange(p: number) {
    updateUrl(p, pageSize, debouncedSearch, status);
  }

  function handlePageSizeChange(ps: number) {
    updateUrl(1, ps, debouncedSearch, status);
  }

  function clearFilters() {
    setSearchInput("");
    setDebouncedSearch("");
    updateUrl(1, PER_PAGE, "", "");
  }

  // Debounced search triggers URL update
  useEffect(() => {
    if (debouncedSearch !== search || (debouncedSearch === "" && search !== "")) {
      updateUrl(1, pageSize, debouncedSearch, status);
    }
  }, [debouncedSearch]);

  const items = result?.items || [];
  const total = result?.total || 0;
  const totalPages = result?.total_pages || 1;

  const isLoaded = !isLoading;

  return (
    <WithLayout>
      <PageHeader
        title="App Registry"
        subtitle="Manage connected applications and their API integrations"
        action={
          <Button asChild>
            <Link href="/app-registry/new">
              <Plus className="h-4 w-4" /> Register Application
            </Link>
          </Button>
        }
      />

      {/* Stat cards — show loading skeleton or actual stats */}
      <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isLoading ? (
          <>
            <div className="h-24 bg-muted rounded-lg animate-pulse" />
            <div className="h-24 bg-muted rounded-lg animate-pulse" />
            <div className="h-24 bg-muted rounded-lg animate-pulse" />
            <div className="h-24 bg-muted rounded-lg animate-pulse" />
          </>
        ) : (
          <>
            <StatCard label="Total Apps"      value={total}        icon={Bot}         tint="violet" />
            <StatCard label="Active"          value={result?.items?.filter((a) => a.status === "Active").length || 0} icon={CheckCircle} tint="green"  />
            <StatCard label="Inactive"        value={result?.items?.filter((a) => a.status === "Inactive").length || 0} icon={XCircle}     tint="red"    />
            <StatCard label="Total Endpoints" value={result?.items?.reduce((n, a) => n + a.routes, 0) || 0}             icon={Route}       tint="blue"   />
          </>
        )}
      </div>

      {/* ── FILTER BAR ── */}
      <FilterBar
        searchValue={searchInput}
        onSearchChange={handleSearchChange}
        searchPlaceholder="Search by application name or ID…"
        filters={[
          {
            value:       status,
            onChange:    (v) => handleStatusChange(v as string),
            options:     STATUS_OPTIONS,
            placeholder: "All Status",
            width:       "w-44",
          },
        ]}
        onClear={clearFilters}
      />

      {/* ── TABLE CARD ── */}
      {error && (
        <EmptyState
          title="Error loading applications"
          description={error instanceof Error ? error.message : "An unknown error occurred"}
          variant="apps"
        />
      )}
      {isLoaded && total === 0 && !search && !status ? (
        <EmptyState
          title="No applications registered yet"
          description="Register your first application to get started with the Master Chatbot."
          variant="apps"
          action={<Button asChild><Link href="/app-registry/new">Register Application</Link></Button>}
        />
      ) : isLoaded && items.length === 0 ? (
        <EmptyState
          title="No applications found"
          description="Try adjusting your search or filters"
          variant="apps"
        />
      ) : (
        <>
          <TableCard>
            <ApplicationTable apps={items} onDelete={(id) => deleteMutation.mutate(id)} loading={isLoading} />
          </TableCard>

          {/* ── PAGINATION CARD ── */}
          <PaginationCard
            page={page}
            total={totalPages}
            totalItems={total}
            perPage={pageSize}
            onPageChange={handlePageChange}
            onPerPageChange={handlePageSizeChange}
          />
        </>
      )}
    </WithLayout>
  );
}
