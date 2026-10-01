import { ApiMethod } from "@/types";
import { cn } from "@/lib/utils";

const METHOD_STYLES: Record<ApiMethod, string> = {
  GET:    "bg-[hsl(var(--info-bg))] text-[hsl(var(--info))]",
  POST:   "bg-[hsl(var(--success-bg))] text-success",
  PUT:    "bg-[hsl(var(--warning-bg))] text-warning",
  PATCH:  "bg-primary/10 text-primary",
  DELETE: "bg-[hsl(var(--destructive-bg))] text-destructive",
};

export function ApiMethodBadge({ method }: { method: ApiMethod }) {
  return (
    <span className={cn("inline-flex min-w-[46px] items-center justify-center rounded-md px-2 py-0.5 text-xs font-bold uppercase tracking-wide", METHOD_STYLES[method])}>
      {method}
    </span>
  );
}
