import { AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import {
  IllustrationNoApps,
  IllustrationNoLogs,
  IllustrationNoResults,
  IllustrationError,
} from "@/components/ui/illustrations";

type EmptyVariant = "default" | "apps" | "logs" | "search" | "error-state";

const ILLUSTRATIONS: Record<EmptyVariant, React.FC<{ className?: string }>> = {
  default:     IllustrationNoResults,
  apps:        IllustrationNoApps,
  logs:        IllustrationNoLogs,
  search:      IllustrationNoResults,
  "error-state": IllustrationError,
};

export function EmptyState({
  title,
  description,
  action,
  variant = "default",
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  variant?: EmptyVariant;
}) {
  const Illustration = ILLUSTRATIONS[variant];
  return (
    <Card className="flex flex-col items-center justify-center py-14 px-6 text-center page-fade">
      <Illustration className="mb-4 h-28 w-auto" />
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-xs text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </Card>
  );
}

export function ErrorState({ message }: { message?: string }) {
  return (
    <Card className="flex items-center gap-3 p-5 border-destructive/30">
      <div className="grid h-9 w-9 place-items-center rounded-lg bg-[hsl(var(--destructive-bg))]">
        <AlertCircle className="h-4 w-4 text-destructive" />
      </div>
      <span className="text-sm text-destructive">{message || "Something went wrong"}</span>
    </Card>
  );
}

const PER_PAGE_OPTIONS = [5, 10, 25, 50];

export function Pagination({
  page,
  setPage,
  total,
  totalItems,
  perPage = 5,
  onPerPageChange,
}: {
  page: number;
  total: number;
  setPage: (page: number) => void;
  totalItems?: number;
  perPage?: number;
  onPerPageChange?: (n: number) => void;
}) {
  const from = totalItems ? (page - 1) * perPage + 1 : null;
  const to   = totalItems ? Math.min(page * perPage, totalItems) : null;

  return (
    <div className="flex items-center justify-between pt-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {onPerPageChange && (
          <>
            <span>Rows per page</span>
            <Select
              value={String(perPage)}
              onChange={(e) => { onPerPageChange(Number(e.target.value)); setPage(1); }}
              className="h-7 w-16 text-xs"
            >
              {PER_PAGE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          </>
        )}
        {from !== null && to !== null ? (
          <span>{from}–{to} of {totalItems}</span>
        ) : (
          <span>Page {page} of {total}</span>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" disabled={page === 1}
          onClick={() => setPage(page - 1)} aria-label="Previous page">
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>
        <span className="min-w-[28px] text-center text-xs font-medium text-foreground">{page}</span>
        <Button variant="outline" size="icon-sm" disabled={page >= total}
          onClick={() => setPage(page + 1)} aria-label="Next page">
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
