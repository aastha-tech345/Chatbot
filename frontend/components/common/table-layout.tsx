"use client";
import { useRef, useState, useEffect } from "react";
import { ChevronLeft, ChevronRight, Search, X, ChevronDown, Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/* ─────────────────────────────────────────────────────────
   SearchableSelect
   A native-feeling combobox: click to open, type to filter,
   click an option to select. Keyboard-accessible.
───────────────────────────────────────────────────────── */
export interface SelectOption {
  value: string;
  label: string;
}

export function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = "Select…",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
}) {
  const [open,  setOpen]  = useState(false);
  const [query, setQuery] = useState("");
  const ref    = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const filtered = query
    ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
    : options;

  const selected = options.find((o) => o.value === value);

  function select(v: string) {
    onChange(v);
    setOpen(false);
    setQuery("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { setOpen(false); setQuery(""); }
    if (e.key === "Enter" && filtered.length === 1) select(filtered[0].value);
  }

  return (
    <div ref={ref} className={cn("relative", className)}>
      {/* Trigger */}
      <button
        type="button"
        onClick={() => { setOpen(!open); setTimeout(() => inputRef.current?.focus(), 10); }}
        className={cn(
          "flex h-9 w-full items-center justify-between rounded-md border border-border bg-card px-3 text-sm text-foreground",
          "transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          open && "border-primary ring-2 ring-primary/15"
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={cn(selected?.value ? "text-foreground" : "text-muted-foreground")}>
          {selected?.value ? selected.label : placeholder}
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="dropdown-enter absolute left-0 top-full z-50 mt-1 w-full min-w-[160px] rounded-md border border-border bg-card shadow-md">
          {/* Search inside dropdown */}
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search…"
                className="h-7 w-full rounded-sm bg-muted pl-7 pr-2 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:bg-background"
              />
            </div>
          </div>

          {/* Options */}
          <ul role="listbox" className="max-h-48 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-xs text-muted-foreground">No results</li>
            ) : (
              filtered.map((o) => (
                <li
                  key={o.value}
                  role="option"
                  aria-selected={o.value === value}
                  onClick={() => select(o.value)}
                  className={cn(
                    "flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition-colors",
                    o.value === value
                      ? "bg-primary/10 text-primary"
                      : "text-foreground hover:bg-muted"
                  )}
                >
                  {o.label}
                  {o.value === value && <Check className="h-3.5 w-3.5 shrink-0" />}
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   FilterBar
   Common search-card component used by every table page.

   Layout:
     LEFT  → search field (flex-1, ~col-4) + optional date field
     RIGHT → one or more SearchableSelect dropdowns

   Clear Filters button appears ONLY when at least one filter
   has a non-empty value.
───────────────────────────────────────────────────────── */
export interface FilterBarFilter {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  /** approximate width, e.g. "w-44" */
  width?: string;
}

export function FilterBar({
  searchValue,
  onSearchChange,
  searchPlaceholder,
  dateValue,
  onDateChange,
  filters,
  onClear,
  /** extra row content rendered above the filter row (e.g. tab bar) */
  header,
  className,
}: {
  searchValue?: string;
  onSearchChange?: (v: string) => void;
  searchPlaceholder?: string;
  dateValue?: string;
  onDateChange?: (v: string) => void;
  filters?: FilterBarFilter[];
  onClear?: () => void;
  header?: React.ReactNode;
  className?: string;
}) {
  // Show clear only when something is actually set
  const isDirty =
    (searchValue ?? "") !== "" ||
    (dateValue   ?? "") !== "" ||
    (filters ?? []).some((f) => f.value !== "");

  return (
    <Card className={cn("mb-4 transition-shadow duration-200", className)}>
      {/* Optional header row (e.g. tabs) */}
      {header && (
        <div className="border-b border-border px-4 pt-3 pb-0">
          {header}
        </div>
      )}

      {/* Filter row */}
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:flex-wrap sm:items-center">

        {/* LEFT — search + date */}
        <div className="flex flex-1 flex-wrap items-center gap-3 sm:flex-nowrap">
          {onSearchChange !== undefined && (
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchValue ?? ""}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder={searchPlaceholder ?? "Search…"}
                className="pl-9"
              />
            </div>
          )}

          {onDateChange !== undefined && (
            <Input
              type="date"
              value={dateValue ?? ""}
              onChange={(e) => onDateChange(e.target.value)}
              className="w-40 shrink-0"
              aria-label="Filter by date"
            />
          )}
        </div>

        {/* RIGHT — dropdowns + clear */}
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {(filters ?? []).map((f, i) => (
            <SearchableSelect
              key={i}
              value={f.value}
              onChange={f.onChange}
              options={f.options}
              placeholder={f.placeholder ?? "All"}
              className={f.width ?? "w-44"}
            />
          ))}

          {/* Clear — only shown when dirty */}
          {isDirty && onClear && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClear}
              className="gap-1 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────
   Legacy wrappers — kept so existing imports don't break
───────────────────────────────────────────────────────── */
export function FilterCard({
  children,
  onClear,
  className,
}: {
  children: React.ReactNode;
  onClear?: () => void;
  className?: string;
}) {
  return (
    <Card className={cn("mb-4 p-4 transition-shadow duration-200", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        {children}
        {onClear && (
          <Button variant="ghost" size="sm" onClick={onClear}
            className="shrink-0 gap-1 text-muted-foreground hover:text-foreground">
            <X className="h-3.5 w-3.5" /> Clear
          </Button>
        )}
      </div>
    </Card>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder = "Search…",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative w-full sm:max-w-xs", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder} className="pl-9" />
    </div>
  );
}

export function FilterSelect({
  value, onChange, className, children,
}: React.SelectHTMLAttributes<HTMLSelectElement> & { children: React.ReactNode }) {
  return (
    <Select value={value} onChange={onChange} className={cn("min-w-[140px]", className)}>
      {children}
    </Select>
  );
}

/* ─────────────────────────────────────────────────────────
   TableCard
───────────────────────────────────────────────────────── */
export function TableCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <Card className={cn("mb-4 overflow-hidden transition-shadow duration-200 hover:shadow-md", className)}>
      {children}
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────
   PaginationCard
───────────────────────────────────────────────────────── */
const PER_PAGE_OPTIONS = [5, 10, 25, 50];

export function PaginationCard({
  page, total, totalItems, perPage, onPageChange, onPerPageChange,
}: {
  page: number;
  total: number;
  totalItems: number;
  perPage: number;
  onPageChange: (p: number) => void;
  onPerPageChange?: (n: number) => void;
}) {
  const from = totalItems === 0 ? 0 : (page - 1) * perPage + 1;
  const to   = Math.min(page * perPage, totalItems);

  return (
    <Card className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>Rows per page</span>
        {onPerPageChange ? (
          <Select value={String(perPage)}
            onChange={(e) => { onPerPageChange(Number(e.target.value)); onPageChange(1); }}
            className="h-7 w-16 text-xs">
            {PER_PAGE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        ) : (
          <span className="font-medium text-foreground">{perPage}</span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground">
          {totalItems === 0 ? "No results" : `${from}–${to} of ${totalItems}`}
        </span>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" disabled={page <= 1}
            onClick={() => onPageChange(page - 1)} aria-label="Previous page">
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="min-w-[80px] text-center text-xs text-muted-foreground">
            Page {page} of {total || 1}
          </span>
          <Button variant="outline" size="icon-sm" disabled={page >= total}
            onClick={() => onPageChange(page + 1)} aria-label="Next page">
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </Card>
  );
}
