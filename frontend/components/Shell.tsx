"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  Bot,
  BriefcaseBusiness,
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
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { AssistantDock } from "@/components/assistant/AssistantDock";
import { SearchCommand, SearchTrigger } from "@/components/SearchCommand";
import { Avatar, DropdownItem, DropdownMenu, Sheet } from "@/components/ui";
import { api } from "@/lib/api";
import { isActive, pageTitle } from "@/lib/nav.mjs";
import { authConfigured, supabaseBrowser } from "@/lib/supabase";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness },
  { href: "/simulation", label: "Simulation", icon: ArrowLeftRight },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/chat", label: "Chat", icon: MessageSquare },
];
const NAV_META = NAV.map(({ href, label }) => ({ href, label }));

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="size-8" />;
  const dark = resolvedTheme === "dark";
  return (
    <button
      aria-label="Toggle theme"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="grid size-8 place-items-center rounded-lg border border-line text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
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
      <span className={clsx("size-2 shrink-0 rounded-full", ok ? "bg-gain" : "bg-loss")} />
      {!compact && (ok ? "live" : "offline")}
    </span>
  );
}

/** NSE session status + IST clock (presentational; client-side, IST has no DST). */
function MarketClock({ collapsed = false }: { collapsed?: boolean }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  if (!now) return <div className="h-8" />;
  const istMs = now.getTime() + (now.getTimezoneOffset() + 330) * 60_000;
  const ist = new Date(istMs);
  const day = ist.getUTCDay();
  const mins = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  const open = day >= 1 && day <= 5 && mins >= 555 && mins < 930; // 09:15–15:30
  const time = now.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
  const dot = (
    <span
      className={clsx(
        "size-2 shrink-0 rounded-full",
        open ? "bg-gain motion-safe:animate-pulse" : "bg-ink-3",
      )}
    />
  );
  if (collapsed) {
    return (
      <span className="mx-auto flex" title={`${open ? "Market open" : "Market closed"} · ${time} IST`}>
        {dot}
      </span>
    );
  }
  return (
    <div className="flex items-center gap-2 px-1 text-xs">
      {dot}
      <div className="min-w-0 leading-tight">
        <div className="font-medium text-ink-2">{open ? "Live Market" : "Market Closed"}</div>
        <div className="tabular text-ink-3">{time} IST · NSE</div>
      </div>
    </div>
  );
}

/** Account avatar + dropdown (email, sign-out). Null when auth isn't configured. */
function AccountMenu() {
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
  return (
    <DropdownMenu
      label="Account"
      triggerClassName="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      trigger={<Avatar name={email} size="sm" />}
    >
      <div className="border-b border-line px-2.5 py-2">
        <div className="truncate text-sm font-medium text-ink" title={email}>
          {email}
        </div>
        <div className="text-[11px] text-ink-3">Signed in</div>
      </div>
      <div className="pt-1">
        <DropdownItem onClick={signOut} className="hover:text-loss">
          <LogOut size={15} /> Sign out
        </DropdownItem>
      </div>
    </DropdownMenu>
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
            aria-current={active ? "page" : undefined}
            className={clsx(
              "relative flex items-center gap-2.5 rounded-lg py-2 text-sm transition-colors",
              collapsed ? "justify-center px-0" : "px-3",
              active
                ? "bg-accent/10 font-medium text-accent"
                : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            {active && (
              <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-accent" />
            )}
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
    <Link href="/" className="flex items-center gap-2.5" title="FinIntel">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-grad-primary text-on-accent shadow-sm">
        <CandlestickChart size={18} />
      </span>
      {!collapsed && (
        <span className="leading-tight">
          <span className="block text-sm font-semibold text-ink">FinIntel</span>
          <span className="block text-[10px] text-ink-3">AI Financial Intelligence</span>
        </span>
      )}
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
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div className={clsx("mb-5 flex items-center px-1", collapsed ? "justify-center" : "justify-start")}>
          <Brand collapsed={collapsed} />
        </div>
        <NavList pathname={pathname} collapsed={collapsed} />
        <div className="mt-auto flex flex-col gap-3 pt-4">
          <div className={clsx("rounded-lg border border-line bg-surface p-2", collapsed && "px-0")}>
            <MarketClock collapsed={collapsed} />
          </div>
          <button
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand" : "Collapse"}
            onClick={toggleCollapsed}
            className={clsx(
              "grid h-8 place-items-center rounded-lg border border-line text-ink-2 transition-colors hover:bg-surface hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
              collapsed ? "mx-auto w-8" : "w-full",
            )}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
      </aside>

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Desktop topbar */}
        <header className="sticky top-0 z-30 hidden h-14 items-center gap-4 border-b border-line bg-surface/80 px-6 backdrop-blur-xl lg:flex">
          <div className="hidden flex-1 lg:block" />
          <div className="w-full max-w-xl">
            <SearchTrigger className="w-full justify-start" />
          </div>
          <div className="flex flex-1 items-center justify-end gap-2.5">
            <HealthDot compact />
            <ThemeToggle />
            <AccountMenu />
          </div>
        </header>

        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/80 px-4 py-3 backdrop-blur-xl lg:hidden">
          <button
            aria-label="Open menu"
            onClick={() => setNavOpen(true)}
            className="rounded-lg p-1.5 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
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
              className="rounded-lg p-1.5 text-ink-3 hover:text-ink"
            >
              <Search size={18} />
            </button>
            <HealthDot compact />
            <ThemeToggle />
            <AccountMenu />
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 lg:p-6">{children}</main>
      </div>

      {/* Single command-palette instance (Cmd/Ctrl-K, or the triggers above). */}
      <SearchCommand />

      {/* Site-wide floating AI assistant (hidden on /login via its own guard). */}
      <AssistantDock />

      {/* Mobile nav drawer */}
      <Sheet open={navOpen} onClose={() => setNavOpen(false)} side="left" title={<Brand />}>
        <div className="flex h-full flex-col p-3">
          <NavList pathname={pathname} onNavigate={() => setNavOpen(false)} />
          <div className="mt-auto border-t border-line pt-3">
            <MarketClock />
          </div>
        </div>
      </Sheet>
    </div>
  );
}
