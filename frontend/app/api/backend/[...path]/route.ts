// Authenticated proxy to the FastAPI backend. The browser calls same-origin
// /api/backend/*; this handler forwards to BACKEND_URL adding X-API-Key from
// the server environment - the key never reaches the client.
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const API_KEY = process.env.BACKEND_API_KEY ?? "";

async function proxy(req: NextRequest, path: string[]): Promise<NextResponse> {
  const url = new URL(`${BACKEND_URL}/${path.join("/")}`);
  url.search = req.nextUrl.search;

  const headers: Record<string, string> = {};
  const contentType = req.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  const idem = req.headers.get("idempotency-key");
  if (idem) headers["idempotency-key"] = idem;
  if (API_KEY) headers["x-api-key"] = API_KEY;

  const body =
    req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(url, { method: req.method, headers, body, cache: "no-store" });
  } catch {
    return NextResponse.json(
      { detail: "backend unreachable - is uvicorn running on port 8000?" },
      { status: 502 },
    );
  }
  const text = await upstream.text();
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
