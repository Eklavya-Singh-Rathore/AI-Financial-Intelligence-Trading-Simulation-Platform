"use client";

import { CandlestickChart, Eye, EyeOff, Lock, Mail, Shield, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, CardBody, Input } from "@/components/ui";
import { authConfigured, supabaseBrowser } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [guestEnabled, setGuestEnabled] = useState(false);
  const [guestBusy, setGuestBusy] = useState(false);

  // Ask the server whether a guest account is configured (keeps the credentials
  // server-side). Only then do we show the "Continue as Guest" button.
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

  const continueAsGuest = async () => {
    setGuestBusy(true);
    setError(null);
    setNotice(null);
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

  if (!authConfigured()) {
    return (
      <div className="mx-auto mt-24 max-w-sm text-center text-sm text-ink-2">
        Supabase auth is not configured (NEXT_PUBLIC_SUPABASE_URL /
        NEXT_PUBLIC_SUPABASE_ANON_KEY). Local development runs open.
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const supabase = supabaseBrowser();
    try {
      if (mode === "signup") {
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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      {/* Ambient brand glow */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute left-1/2 top-1/4 size-[34rem] -translate-x-1/2 rounded-full bg-accent/15 blur-[120px]" />
        <div className="absolute bottom-0 right-1/5 size-[26rem] rounded-full bg-accent-2/10 blur-[120px]" />
      </div>

      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <span className="grid size-12 place-items-center rounded-2xl bg-grad-primary text-on-accent shadow-glow">
            <CandlestickChart size={26} />
          </span>
          <div>
            <div className="text-2xl font-semibold text-ink">FinIntel</div>
            <div className="text-sm text-ink-3">AI Financial Intelligence Platform</div>
          </div>
        </div>

        <Card variant="elevated" className="rounded-2xl">
          <CardBody className="p-6">
            <form onSubmit={submit} className="space-y-4">
              <div>
                <h1 className="text-lg font-semibold text-ink">
                  {mode === "signin" ? "Welcome back" : "Create your account"}
                </h1>
                <p className="text-sm text-ink-3">
                  {mode === "signin" ? "Sign in to access your dashboard" : "Start exploring the platform"}
                </p>
              </div>

              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink-2">Email</span>
                <div className="relative">
                  <Mail size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                  <Input
                    type="email"
                    required
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
                {busy ? "…" : (
                  <>
                    <Shield size={16} /> {mode === "signin" ? "Sign in" : "Sign up"}
                  </>
                )}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
                className="w-full"
              >
                {mode === "signin" ? "No account? Sign up" : "Have an account? Sign in"}
              </Button>

              {guestEnabled && (
                <>
                  <div className="flex items-center gap-2 pt-1 text-[10px] uppercase tracking-wide text-ink-3">
                    <span className="h-px flex-1 bg-line" />
                    or
                    <span className="h-px flex-1 bg-line" />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={continueAsGuest}
                    disabled={guestBusy || busy}
                    className="w-full"
                  >
                    {guestBusy ? "…" : "Continue as Guest"}
                  </Button>
                </>
              )}
            </form>
          </CardBody>
        </Card>

        <p className="mt-5 flex items-center justify-center gap-1.5 text-center text-xs text-ink-3">
          <ShieldCheck size={13} /> Decision-support research only — no real trading.
        </p>
      </div>
    </div>
  );
}
