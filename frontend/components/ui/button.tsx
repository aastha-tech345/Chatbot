"use client";
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "outline" | "ghost" | "destructive" | "secondary" | "success";
type ButtonSize = "sm" | "md" | "lg" | "icon" | "icon-sm";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({ className, variant = "default", size = "md", asChild, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:pointer-events-none disabled:opacity-50 select-none whitespace-nowrap",
        // variants
        variant === "default" && "bg-primary text-white hover:bg-primary-hover shadow-sm text-sm",
        variant === "outline" && "border border-border bg-card text-foreground hover:bg-muted text-sm",
        variant === "ghost" && "text-muted-foreground hover:bg-muted hover:text-foreground text-sm",
        variant === "destructive" && "bg-destructive text-white hover:bg-destructive/90 shadow-sm text-sm",
        variant === "secondary" && "bg-secondary text-secondary-foreground hover:bg-muted text-sm",
        variant === "success" && "bg-success text-white hover:bg-success/90 shadow-sm text-sm",
        // sizes
        size === "sm" && "h-8 px-3 text-xs",
        size === "md" && "h-9 px-4 text-sm",
        size === "lg" && "h-10 px-5 text-sm",
        size === "icon" && "h-9 w-9",
        size === "icon-sm" && "h-8 w-8",
        className
      )}
      {...props}
    />
  );
}
