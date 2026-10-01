"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { getApplications } from "@/lib/api/applications";

export function BackendSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  const { data: appsData } = useQuery({
    queryKey: ["applications"],
    queryFn: () => getApplications({ page_size: 100 }),
    enabled: query.length > 0,
  });

  const results = appsData?.items
    ?.filter((app) =>
      app.name.toLowerCase().includes(query.toLowerCase()) ||
      app.appId.toLowerCase().includes(query.toLowerCase())
    )
    .slice(0, 8) ?? [];

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (appId: string) => {
    router.push(`/app-registry/${appId}`);
    setQuery("");
    setOpen(false);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setQuery("");
  };

  return (
    <div className="relative flex-1 max-w-md" ref={searchRef}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          placeholder="Search applications..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          className="w-full rounded-lg border border-border bg-muted px-3 py-2 pl-9 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {query && (
          <button
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Dropdown results */}
      {open && query.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 rounded-lg border border-border bg-card shadow-lg z-50">
          {results.length > 0 ? (
            <div className="max-h-64 overflow-y-auto">
              {results.map((app) => (
                <button
                  key={app.id}
                  onClick={() => handleSelect(app.id)}
                  className="w-full text-left px-4 py-2.5 hover:bg-muted transition-colors border-b border-border last:border-b-0 flex items-center justify-between"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{app.name}</p>
                    <p className="text-xs text-muted-foreground">{app.appId}</p>
                  </div>
                  <span className="text-xs px-2 py-1 rounded-md bg-primary/10 text-primary">
                    {app.routes || 0} routes
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="px-4 py-6 text-center">
              <p className="text-sm text-muted-foreground">No applications found</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
