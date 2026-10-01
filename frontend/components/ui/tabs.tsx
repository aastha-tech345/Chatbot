"use client";
import { cn } from "@/lib/utils";

export function TabBar({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("flex items-center gap-0.5 rounded-lg bg-muted p-1", className)}>
      {children}
    </div>
  );
}

export function TabButton({ active, children, onClick, className }: { active?: boolean; children: React.ReactNode; onClick?: () => void; className?: string }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "h-8 rounded-md px-3.5 text-xs font-medium transition-all",
        active
          ? "bg-card text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}

export function TabBorderBar({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("flex items-center border-b border-border gap-1", className)}>
      {children}
    </div>
  );
}

export function TabBorderButton({ active, children, onClick, className }: { active?: boolean; children: React.ReactNode; onClick?: () => void; className?: string }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "relative h-10 px-4 text-sm font-medium transition-colors -mb-px",
        active
          ? "text-primary border-b-2 border-primary"
          : "text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}
