// Authenticated proxy to the FastAPI backend. The browser calls same-origin
// /api/backend/*; this handler forwards the signed-in user's Supabase access
// token as a Bearer header (Phase 4), falling back to the server-side
// X-API-Key for local development. Credentials never reach the client.
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

// Forecast, backtest and chat are single synchronous calls that may ride out
// a Render cold start (~1 min) plus Hugging Face Space inference/wake-up.
// 300s is the Hobby-plan ceiling with Fluid compute enabled.
export const maxDuration = 300;

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const API_KEY = process.env.BACKEND_API_KEY ?? "";

async function userAccessToken(): Promise<string | null> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) return null;
  const store = await cookies();
  const supabase = createServerClient(url, anon, {
    cookies: { getAll: () => store.getAll(), setAll: () => {} },
  });
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

async function proxy(req: NextRequest, path: string[]): Promise<NextResponse> {
  const url = new URL(`${BACKEND_URL}/${path.join("/")}`);
  url.search = req.nextUrl.search;

  const headers: Record<string, string> = {};
  const contentType = req.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  const idem = req.headers.get("idempotency-key");
  if (idem) headers["idempotency-key"] = idem;

  const token = await userAccessToken();
  if (token) {
    headers["authorization"] = `Bearer ${token}`;
  } else if (API_KEY) {
    headers["x-api-key"] = API_KEY; // local-dev fallback only
  }

  const body =
    req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(url, { method: req.method, headers, body, cache: "no-store" });
  } catch {
    return NextResponse.json(
      { detail: "backend unreachable - check BACKEND_URL / backend status" },
      { status: 502 },
    );
  }
  // 204/205/304 are null-body statuses: passing any body (even "") to the
  // Response constructor throws a TypeError, which surfaces as a 500. DELETE
  // endpoints return 204, so forward those with a null body.
  const nullBody = upstream.status === 204 || upstream.status === 205 || upstream.status === 304;
  const text = nullBody ? null : await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
