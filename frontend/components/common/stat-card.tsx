import { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Tint = "violet" | "green" | "blue" | "red" | "amber";

const tintMap: Record<Tint, { icon: string; ring: string }> = {
  violet: { icon: "bg-primary/10 text-primary",                                   ring: "ring-primary/10" },
  green:  { icon: "bg-[hsl(var(--success-bg))] text-success",                     ring: "ring-success/10" },
  blue:   { icon: "bg-[hsl(var(--info-bg))] text-[hsl(var(--info))]",             ring: "ring-[hsl(var(--info))]/10" },
  red:    { icon: "bg-[hsl(var(--destructive-bg))] text-destructive",             ring: "ring-destructive/10" },
  amber:  { icon: "bg-[hsl(var(--warning-bg))] text-warning",                     ring: "ring-warning/10" },
};

export function StatCard({
  label,
  value,
  icon: Icon,
  tint = "violet",
  className,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tint?: Tint;
  className?: string;
}) {
  const t = tintMap[tint];
  return (
    <Card className={cn(
      "p-5 transition-shadow duration-200 hover:shadow-md",
      className
    )}>
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-bold text-foreground">{value}</p>
        </div>
        <div className={cn(
          "grid h-10 w-10 shrink-0 place-items-center rounded-lg ring-4",
          t.icon, t.ring
        )}>
          <Icon className="h-4.5 w-4.5" strokeWidth={2} />
        </div>
      </div>
    </Card>
  );
}
