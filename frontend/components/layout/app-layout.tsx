"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import type { CSSProperties } from "react";
import {
  Activity, Bell, Bot, ChevronDown, LayoutDashboard, MessageSquare,
  Moon, Puzzle, Settings, SlidersHorizontal, Sun, X,
  Menu, PanelLeftClose, PanelLeftOpen, LogOut, User
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { BackendSearch } from "@/components/common/backend-search";
import { API_BASE_URL } from "@/lib/api/client";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  // { href: "/chat",      label: "Chat",       icon: MessageSquare },
  { href: "/app-registry", label: "App Registry", icon: Puzzle },
  { href: "/ai-provider",  label: "AI Provider",  icon: Bot },
  { href: "/logs",         label: "Logs & Monitoring", icon: Activity },
  { href: "/settings",     label: "Settings",     icon: SlidersHorizontal },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />

      {/* Overlay for mobile */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Main area */}
      <div className={cn(
        "flex flex-1 flex-col transition-[margin] duration-200 min-w-0",
        collapsed ? "lg:ml-[60px]" : "lg:ml-[240px]"
      )}
      style={{ "--app-sidebar-width": collapsed ? "60px" : "240px" } as CSSProperties}>
        <TopHeader
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed(!collapsed)}
          onOpenMobile={() => setMobileOpen(true)}
        />
        <main className="flex-1 px-5 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl page-fade">{children}</div>
        </main>
      </div>
    </div>
  );
}

/* ──────────────── Sidebar ──────────────── */
function Sidebar({ collapsed, mobileOpen, onCloseMobile }: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const pathname = usePathname();

  return (
    <aside className={cn(
      "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-card transition-[width] duration-200",
      collapsed ? "w-[60px]" : "w-[240px]",
      // mobile: hidden by default, shown as drawer
      mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
    )}>
      {/* Logo */}
      <div className={cn(
        "flex h-14 shrink-0 items-center border-b border-border",
        collapsed ? "justify-center px-0" : "gap-2.5 px-4"
      )}>
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary">
          <Bot className="h-4 w-4 text-white" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-foreground leading-tight">Master Chatbot</div>
            <div className="truncate text-2xs text-muted-foreground leading-tight">AI Assistant</div>
          </div>
        )}
        {mobileOpen && (
          <Button variant="ghost" size="icon-sm" className="ml-auto lg:hidden" onClick={onCloseMobile}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "nav-item",
                active && "nav-item-active",
                collapsed && "justify-center px-0"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      {!collapsed && (
        <div className="shrink-0 px-4 py-4 border-t border-border">
          <div className="rounded-md bg-[hsl(var(--primary-light))] px-3 py-3">
            <p className="text-xs font-semibold text-primary">Need Help?</p>
            <p className="mt-0.5 text-2xs text-primary/70">
              View docs for API discovery, providers &amp; routing.
            </p>
            <Link href="/settings" className="mt-2 inline-block text-2xs font-semibold text-primary underline underline-offset-2">
              View Documentation
            </Link>
          </div>
        </div>
      )}
    </aside>
  );
}

/* ──────────────── Top Header ──────────────── */
function TopHeader({ collapsed, onToggleCollapse, onOpenMobile }: {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenMobile: () => void;
}) {
  const { theme, setTheme } = useTheme();
  const { user, logout } = useAuth();
  const router = useRouter();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  // Poll backend health
  useEffect(() => {
    const apiBase = API_BASE_URL;
    if (!apiBase) { setBackendOk(null); return; }
    let mounted = true;
    async function check() {
      try {
        const res = await fetch(`${apiBase}/health`, { cache: "no-store" });
        if (mounted) setBackendOk(res.ok);
      } catch {
        if (mounted) setBackendOk(false);
      }
    }
    check();
    const id = setInterval(check, 30_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  function handleLogout() {
    setUserMenuOpen(false);
    logout();
    router.replace("/login");
  }

  const initials = (user?.name ?? "A").charAt(0).toUpperCase();
  const displayName = user?.name ?? "Admin";

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4 sm:px-6">
      {/* Left */}
      <div className="flex items-center gap-3 flex-1">
        <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={onOpenMobile} aria-label="Open menu">
          <Menu className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" className="hidden lg:inline-flex" onClick={onToggleCollapse} aria-label="Toggle sidebar">
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </Button>

        {/* Backend search */}
        <div className="hidden md:flex flex-1 max-w-md">
          <BackendSearch />
        </div>

        {/* Backend status — dynamic */}
        {/* <div className="hidden items-center gap-1.5 rounded-md border border-border bg-secondary px-2.5 py-1 sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            {backendOk === false ? "Backend Disconnected" : "Backend Connected"}
          </span>
        </div> */}
      </div>

      {/* Right */}
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon-sm" aria-label="Toggle theme"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Notifications">
          <Bell className="h-4 w-4" />
        </Button>

        {/* User dropdown */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted transition-colors"
            aria-haspopup="true"
            aria-expanded={userMenuOpen}
          >
            <div className="grid h-7 w-7 place-items-center rounded-full bg-primary text-xs font-bold text-white">
              {initials}
            </div>
            <span className="hidden text-sm font-medium text-foreground sm:block">{displayName}</span>
            <ChevronDown className="hidden h-3.5 w-3.5 text-muted-foreground sm:block" />
          </button>

          {userMenuOpen && (
            <div className="dropdown-enter absolute right-0 top-full mt-1.5 w-44 rounded-lg border border-border bg-card shadow-md z-50">
              <div className="px-3 py-2.5 border-b border-border">
                <p className="text-xs font-semibold text-foreground">{displayName}</p>
                <p className="text-2xs text-muted-foreground">Administrator</p>
              </div>
              <div className="py-1">
                <Link href="/settings" onClick={() => setUserMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors">
                  <User className="h-3.5 w-3.5 text-muted-foreground" /> Profile
                </Link>
                <Link href="/settings" onClick={() => setUserMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors">
                  <Settings className="h-3.5 w-3.5 text-muted-foreground" /> Settings
                </Link>
              </div>
              <div className="border-t border-border py-1">
                <button
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-muted transition-colors"
                >
                  <LogOut className="h-3.5 w-3.5" /> Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
