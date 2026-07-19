"use client";

import { CandlestickChart } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, CardBody, Input } from "@/components/ui";
import { authConfigured, supabaseBrowser } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="mx-auto mt-20 w-full max-w-sm">
      <div className="mb-6 flex items-center justify-center gap-2 text-lg font-semibold">
        <CandlestickChart size={22} className="text-accent" />
        FinIntel
      </div>
      <Card>
        <CardBody>
          <form onSubmit={submit} className="space-y-3">
            <h1 className="text-base font-medium">
              {mode === "signin" ? "Sign in" : "Create your account"}
            </h1>
            <Input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email"
            />
            <Input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="password (min 8 chars)"
            />
            {error && <p className="text-sm text-loss">{error}</p>}
            {notice && <p className="text-sm text-gain">{notice}</p>}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "…" : mode === "signin" ? "Sign in" : "Sign up"}
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
      <p className="mt-4 text-center text-xs text-ink-3">
        Decision-support research only — no real trading.
      </p>
    </div>
  );
}
