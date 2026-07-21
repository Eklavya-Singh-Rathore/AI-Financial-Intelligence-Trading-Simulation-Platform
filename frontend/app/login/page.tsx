"use client";

import {
  ArrowRight,
  BarChart3,
  Bot,
  Eye,
  EyeOff,
  FileText,
  Github,
  Lock,
  Mail,
  PieChart,
  TrendingUp,
  User,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, CardBody, Input } from "@/components/ui";
import { cn } from "@/lib/ui";
import { authConfigured, supabaseBrowser } from "@/lib/supabase";

const REPO_URL =
  "https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform";

const TONE_CHIP: Record<string, string> = {
  accent: "bg-accent/10 text-accent",
  gain: "bg-gain/10 text-gain",
  "accent-2": "bg-accent-2/10 text-accent-2",
};

const FEATURES = [
  {
    icon: TrendingUp,
    tone: "accent",
    title: "Market Forecasting",
    desc: "High-accuracy, deep-learning based price predictions and trend analysis.",
  },
  {
    icon: Bot,
    tone: "gain",
    title: "Agent Simulation",
    desc: "Backtest and refine algorithmic trading agents in a safe environment.",
  },
  {
    icon: PieChart,
    tone: "accent-2",
    title: "Portfolio Optimization",
    desc: "Real-time risk assessment and automated asset rebalancing.",
  },
  {
    icon: FileText,
    tone: "accent",
    title: "Holistic Consensus",
    desc: "Combine technical, fundamental, and news signals for smarter decisions.",
  },
] as const;

export default function LandingPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<"signin" | "signup" | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [guestEnabled, setGuestEnabled] = useState(false);
  const [guestBusy, setGuestBusy] = useState(false);

  // Only show "Continue as Guest" when the server has guest credentials.
  useEffect(() => {
    let active = true;
    fetch("/api/guest")
      .then((r) => r.json())
      .then((d) => active && setGuestEnabled(Boolean(d?.enabled)))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  // Close the auth modal on Escape.
  useEffect(() => {
    if (!authMode) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setAuthMode(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [authMode]);

  const openAuth = (mode: "signin" | "signup") => {
    setError(null);
    setNotice(null);
    setAuthMode(mode);
  };

  const continueAsGuest = async () => {
    setGuestBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/guest", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error ?? "guest sign-in failed");
      }
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGuestBusy(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const supabase = supabaseBrowser();
    try {
      if (authMode === "signup") {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          setNotice("Check your inbox to confirm your email, then sign in.");
          return;
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Ambient brand glow */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute left-1/2 top-0 size-[42rem] -translate-x-1/2 rounded-full bg-accent/10 blur-[130px]" />
        <div className="absolute bottom-0 right-0 size-[30rem] rounded-full bg-accent-2/10 blur-[130px]" />
      </div>

      {/* Header */}
      <header className="flex items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl bg-grad-primary text-on-accent shadow-sm">
            <BarChart3 size={18} />
          </span>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-ink">FinIntel</div>
            <div className="text-[11px] text-ink-3">AI Financial Intelligence</div>
          </div>
        </div>
        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer noopener"
          aria-label="Open the GitHub repository"
          className="grid size-10 place-items-center rounded-xl border border-line text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
        >
          <Github size={18} />
        </a>
      </header>

      {/* Hero */}
      <main className="mx-auto max-w-4xl px-6 pb-20 text-center">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-line bg-surface-2/60 px-4 py-1.5 text-[11px] font-semibold tracking-[0.12em] text-accent">
          AI-POWERED · DATA-DRIVEN · ACTIONABLE
        </div>
        <h1 className="text-4xl font-bold leading-[1.08] tracking-tight text-ink sm:text-6xl">
          FinIntel: AI-Powered
          <br />
          <span className="text-accent">Financial Intelligence.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-ink-2 sm:text-lg">
          Advanced AI agents and multi-model analytics working together to deliver market
          insights, forecast with precision, and optimize your portfolio — all in one
          intelligent platform.
        </p>

        {/* Feature panel */}
        <div className="mt-10 grid gap-6 rounded-2xl border border-line bg-surface/40 p-6 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div key={f.title} className="text-center">
              <span
                className={cn(
                  "mx-auto mb-3 grid size-12 place-items-center rounded-full",
                  TONE_CHIP[f.tone],
                )}
              >
                <f.icon size={22} />
              </span>
              <div className="font-semibold text-ink">{f.title}</div>
              <p className="mt-1 text-sm leading-snug text-ink-3">{f.desc}</p>
            </div>
          ))}
        </div>

        {/* CTAs */}
        <div className="mx-auto mt-10 flex max-w-lg flex-col items-center gap-4">
          <div className="grid w-full gap-4 sm:grid-cols-2">
            <div>
              <Button variant="gradient" className="h-11 w-full" onClick={() => openAuth("signin")}>
                Sign In <ArrowRight size={16} />
              </Button>
              <p className="mt-1.5 text-xs text-ink-3">Access your dashboard</p>
            </div>
            <div>
              <Button variant="outline" className="h-11 w-full" onClick={() => openAuth("signup")}>
                Sign Up <ArrowRight size={16} />
              </Button>
              <p className="mt-1.5 text-xs text-ink-3">Create your account</p>
            </div>
          </div>

          {guestEnabled && (
            <>
              <div className="flex w-full items-center gap-3 text-[10px] uppercase tracking-wide text-ink-3">
                <span className="h-px flex-1 bg-line" />
                or
                <span className="h-px flex-1 bg-line" />
              </div>
              <button
                type="button"
                onClick={continueAsGuest}
                disabled={guestBusy}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-accent transition-colors hover:text-accent-2 disabled:opacity-60"
              >
                <User size={15} /> {guestBusy ? "Starting…" : "Continue as Guest"}
              </button>
              <p className="text-xs text-ink-3">Explore the platform without an account</p>
            </>
          )}

          {error && !authMode && <p className="text-sm text-loss">{error}</p>}
        </div>
      </main>

      {/* Auth modal (inline reveal) */}
      {authMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="Close"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setAuthMode(null)}
          />
          <Card variant="elevated" className="relative z-10 w-full max-w-sm animate-scale-in rounded-2xl">
            <CardBody className="p-6">
              <button
                type="button"
                aria-label="Close"
                onClick={() => setAuthMode(null)}
                className="absolute right-3 top-3 rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <X size={16} />
              </button>
              {!authConfigured() ? (
                <p className="text-sm text-ink-2">
                  Supabase auth is not configured (NEXT_PUBLIC_SUPABASE_URL /
                  NEXT_PUBLIC_SUPABASE_ANON_KEY). Local development runs open.
                </p>
              ) : (
                <form onSubmit={submit} className="space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold text-ink">
                      {authMode === "signin" ? "Welcome back" : "Create your account"}
                    </h2>
                    <p className="text-sm text-ink-3">
                      {authMode === "signin"
                        ? "Sign in to access your dashboard"
                        : "Start exploring the platform"}
                    </p>
                  </div>

                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-ink-2">Email</span>
                    <div className="relative">
                      <Mail size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                      <Input
                        type="email"
                        required
                        autoFocus
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="Enter your email"
                        className="pl-9"
                      />
                    </div>
                  </label>

                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-ink-2">Password</span>
                    <div className="relative">
                      <Lock size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                      <Input
                        type={showPw ? "text" : "password"}
                        required
                        minLength={8}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Enter your password"
                        className="pl-9 pr-9"
                      />
                      <button
                        type="button"
                        aria-label={showPw ? "Hide password" : "Show password"}
                        onClick={() => setShowPw((v) => !v)}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-3 transition-colors hover:text-ink"
                      >
                        {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </label>

                  {error && <p className="text-sm text-loss">{error}</p>}
                  {notice && <p className="text-sm text-gain">{notice}</p>}

                  <Button type="submit" variant="gradient" disabled={busy} className="h-11 w-full">
                    {busy ? "…" : authMode === "signin" ? "Sign in" : "Sign up"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setAuthMode(authMode === "signin" ? "signup" : "signin");
                      setError(null);
                      setNotice(null);
                    }}
                    className="w-full"
                  >
                    {authMode === "signin"
                      ? "No account? Sign up"
                      : "Have an account? Sign in"}
                  </Button>
                </form>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      <p className="pb-6 text-center text-xs text-ink-3">
        Decision-support research only — no real trading.
      </p>
    </div>
  );
}
