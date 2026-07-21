// Guest access (Phase 4.6). Signs in as the shared, pre-provisioned guest
// Supabase account entirely SERVER-SIDE, so the guest credentials
// (GUEST_EMAIL / GUEST_PASSWORD, server-only env) never reach the browser.
// The guest is a normal Supabase user (role "user") — per-user ownership
// isolation applies exactly as for any account; there is no auth bypass.
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

function guestConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY &&
      process.env.GUEST_EMAIL &&
      process.env.GUEST_PASSWORD,
  );
}

// Lets the login page show the button only when guest access is available,
// without exposing whether/what the credentials are.
export async function GET() {
  return NextResponse.json({ enabled: guestConfigured() });
}

export async function POST() {
  if (!guestConfigured()) {
    return NextResponse.json({ error: "guest access is not configured" }, { status: 503 });
  }
  const store = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => store.getAll(),
        setAll: (list) =>
          list.forEach(({ name, value, options }) => store.set(name, value, options)),
      },
    },
  );
  const { data, error } = await supabase.auth.signInWithPassword({
    email: process.env.GUEST_EMAIL!,
    password: process.env.GUEST_PASSWORD!,
  });
  if (error) {
    // Generic message: never leak whether the account exists or why it failed.
    return NextResponse.json({ error: "guest sign-in failed" }, { status: 401 });
  }
  // Phase 7: wipe the shared guest workspace so each session starts clean.
  // Blocks so the dashboard loads clean; non-fatal if the backend can't be reached.
  const token = data.session?.access_token;
  const backend = process.env.BACKEND_URL?.replace(/\/$/, "");
  if (token && backend) {
    try {
      await fetch(`${backend}/guest/reset`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      /* ignore — the guest is already signed in */
    }
  }
  return NextResponse.json({ ok: true });
}
