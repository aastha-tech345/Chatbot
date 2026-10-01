import { cn } from "@/lib/utils";

export type BadgeVariant = "default" | "success" | "warning" | "destructive" | "info" | "secondary";

export function Badge({
  className,
  variant = "default",
  children,
}: {
  className?: string;
  variant?: BadgeVariant;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium leading-tight",
        variant === "default" && "bg-primary/10 text-primary",
        variant === "success" && "bg-[hsl(var(--success-bg))] text-success",
        variant === "warning" && "bg-[hsl(var(--warning-bg))] text-warning",
        variant === "destructive" && "bg-[hsl(var(--destructive-bg))] text-destructive",
        variant === "info" && "bg-[hsl(var(--info-bg))] text-[hsl(var(--info))]",
        variant === "secondary" && "bg-muted text-muted-foreground",
        className
      )}
    >
      {children}
    </span>
  );
}
