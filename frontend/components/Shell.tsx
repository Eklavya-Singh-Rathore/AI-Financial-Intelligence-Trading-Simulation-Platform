"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  CandlestickChart,
  LayoutDashboard,
  Lightbulb,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sun,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { SearchCommand, SearchTrigger } from "@/components/SearchCommand";
import { Sheet } from "@/components/ui";
import { api } from "@/lib/api";
import { isActive, pageTitle } from "@/lib/nav.mjs";
import { authConfigured, supabaseBrowser } from "@/lib/supabase";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/simulation", label: "Simulation", icon: Wallet },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/chat", label: "Chat", icon: MessageSquare },
];
const NAV_META = NAV.map(({ href, label }) => ({ href, label }));

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="h-8 w-8" />;
  const dark = resolvedTheme === "dark";
  return (
    <button
      aria-label="Toggle theme"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="rounded-md border border-line p-1.5 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

function HealthDot({ compact = false }: { compact?: boolean }) {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });
  const ok = !isError && data?.database === "ok";
  return (
    <span
      className="flex items-center gap-1.5 text-xs text-ink-2"
      title={`backend: ${ok ? "healthy" : "unreachable or degraded"}`}
    >
      <span className={clsx("h-2 w-2 shrink-0 rounded-full", ok ? "bg-gain" : "bg-loss")} />
      {!compact && (ok ? "live" : "offline")}
    </span>
  );
}

function UserBox({ collapsed = false }: { collapsed?: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => {
    if (!authConfigured()) return;
    supabaseBrowser()
      .auth.getUser()
      .then(({ data }) => setEmail(data.user?.email ?? null));
  }, []);
  if (!authConfigured() || !email) return null;
  const signOut = async () => {
    await supabaseBrowser().auth.signOut();
    router.push("/login");
    router.refresh();
  };
  if (collapsed) {
    return (
      <button
        aria-label="Sign out"
        title={`Sign out (${email})`}
        onClick={signOut}
        className="mx-auto mb-2 rounded-md p-1.5 text-ink-3 transition-colors hover:bg-surface-2 hover:text-loss"
      >
        <LogOut size={16} />
      </button>
    );
  }
  return (
    <div className="mb-3 flex items-center justify-between gap-2 border-t border-line pt-3">
      <span className="truncate text-xs text-ink-3" title={email}>
        {email}
      </span>
      <button
        aria-label="Sign out"
        onClick={signOut}
        className="shrink-0 text-ink-3 transition-colors hover:text-loss"
        title="Sign out"
      >
        <LogOut size={14} />
      </button>
    </div>
  );
}

function NavList({
  pathname,
  collapsed = false,
  onNavigate,
}: {
  pathname: string;
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={clsx(
              "flex items-center gap-2.5 rounded-md py-2 text-sm transition-colors",
              collapsed ? "justify-center px-0" : "px-3",
              active
                ? "bg-accent/10 font-medium text-accent"
                : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            <Icon size={16} className="shrink-0" />
            {!collapsed && label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <Link
      href="/"
      className="flex items-center gap-2 font-semibold text-ink"
      title="FinIntel"
    >
      <CandlestickChart size={20} className="shrink-0 text-accent" />
      {!collapsed && <span>FinIntel</span>}
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [navOpen, setNavOpen] = useState(false);

  // Restore the desktop collapse preference after mount (avoids SSR mismatch).
  useEffect(() => {
    setCollapsed(localStorage.getItem("sidebar_collapsed") === "1");
  }, []);
  // Close the mobile drawer on navigation.
  useEffect(() => setNavOpen(false), [pathname]);

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
      return next;
    });
  };

  if (pathname.startsWith("/login")) {
    return <main className="min-h-screen p-6">{children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside
        className={clsx(
          "hidden shrink-0 flex-col border-r border-line bg-surface-2 p-3 lg:flex",
          collapsed ? "w-16" : "w-56",
        )}
      >
        <div className={clsx("mb-4 flex items-center px-1", collapsed ? "justify-center" : "justify-between")}>
          <Brand collapsed={collapsed} />
        </div>
        {collapsed ? (
          <button
            type="button"
            aria-label="Search"
            onClick={() => window.dispatchEvent(new Event("finintel:open-search"))}
            className="mx-auto mb-3 rounded-md border border-line p-1.5 text-ink-3 hover:text-ink"
          >
            <Search size={16} />
          </button>
        ) : (
          <div className="mb-3">
            <SearchTrigger className="w-full justify-start" />
          </div>
        )}
        <NavList pathname={pathname} collapsed={collapsed} />
        <div className="mt-auto flex flex-col gap-2 pt-4">
          <UserBox collapsed={collapsed} />
          <div className={clsx("flex items-center gap-2", collapsed ? "flex-col" : "justify-between")}>
            <HealthDot compact={collapsed} />
            <div className={clsx("flex items-center gap-1.5", collapsed && "flex-col")}>
              <ThemeToggle />
              <button
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={collapsed ? "Expand" : "Collapse"}
                onClick={toggleCollapsed}
                className="rounded-md border border-line p-1.5 text-ink-2 transition-colors hover:bg-surface hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur lg:hidden">
          <button
            aria-label="Open menu"
            onClick={() => setNavOpen(true)}
            className="rounded-md p-1.5 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <Menu size={20} />
          </button>
          <Brand />
          <span className="truncate text-sm font-medium text-ink-2">{pageTitle(pathname, NAV_META)}</span>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              aria-label="Search"
              onClick={() => window.dispatchEvent(new Event("finintel:open-search"))}
              className="rounded-md p-1.5 text-ink-3 hover:text-ink"
            >
              <Search size={18} />
            </button>
            <HealthDot compact />
            <ThemeToggle />
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 lg:p-6">{children}</main>
      </div>

      {/* Single command-palette instance (Cmd/Ctrl-K, or the triggers above). */}
      <SearchCommand />

      {/* Mobile nav drawer */}
      <Sheet open={navOpen} onClose={() => setNavOpen(false)} side="left" title={<Brand />}>
        <div className="flex h-full flex-col p-3">
          <NavList pathname={pathname} onNavigate={() => setNavOpen(false)} />
          <div className="mt-auto border-t border-line pt-3">
            <UserBox />
          </div>
        </div>
      </Sheet>
    </div>
  );
}
