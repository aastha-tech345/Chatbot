import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
        {subtitle && (
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export function BackLink({ children = "Back" }: { children?: React.ReactNode }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="mb-4 -ml-1 gap-1 text-muted-foreground"
      onClick={() => history.back()}
    >
      <ChevronLeft className="h-3.5 w-3.5" />
      {children}
    </Button>
  );
}
