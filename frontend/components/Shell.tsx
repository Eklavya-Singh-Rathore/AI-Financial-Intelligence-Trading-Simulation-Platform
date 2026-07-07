"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, CandlestickChart, LayoutDashboard, MessageSquare, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/chat", label: "Chat", icon: MessageSquare },
];

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
      className="rounded-md border border-line p-1.5 text-ink-2 hover:text-ink"
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

function HealthDot() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });
  const ok = !isError && data?.database === "ok";
  return (
    <span className="flex items-center gap-1.5 text-xs text-ink-2" title={`backend: ${ok ? "healthy" : "unreachable or degraded"}`}>
      <span className={clsx("h-2 w-2 rounded-full", ok ? "bg-gain" : "bg-loss")} />
      {ok ? "live" : "offline"}
    </span>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-52 shrink-0 flex-col border-r border-line bg-surface-2 p-4">
        <Link href="/" className="mb-6 flex items-center gap-2 font-semibold">
          <CandlestickChart size={20} className="text-accent" />
          <span>FinIntel</span>
        </Link>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  active ? "bg-accent/10 font-medium text-accent" : "text-ink-2 hover:text-ink",
                )}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex items-center justify-between pt-4">
          <HealthDot />
          <ThemeToggle />
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6">{children}</main>
    </div>
  );
}
