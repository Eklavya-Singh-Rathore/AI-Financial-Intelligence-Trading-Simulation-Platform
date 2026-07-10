"use client";

import { CandlestickChart } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authConfigured, supabaseBrowser } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
      <form onSubmit={submit} className="space-y-3 rounded-lg border border-line p-5">
        <h1 className="text-base font-medium">
          {mode === "signin" ? "Sign in" : "Create your account"}
        </h1>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email"
          className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <input
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password (min 8 chars)"
          className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        />
        {error && <p className="text-sm text-loss">{error}</p>}
        {notice && <p className="text-sm text-gain">{notice}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>
        <button
          type="button"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          className="w-full text-center text-xs text-ink-2 hover:text-ink"
        >
          {mode === "signin" ? "No account? Sign up" : "Have an account? Sign in"}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-ink-3">
        Decision-support research only — no real trading.
      </p>
    </div>
  );
}
