"use client";

// Route-level error fallback: any uncaught render error in a page shows this
// recoverable card (inside the app shell) instead of Next.js's blank
// "Application error" screen.
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { Button } from "@/components/ui";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("route render failed:", error);
  }, [error]);

  return (
    <div className="flex min-h-[50vh] items-center justify-center p-6">
      <div className="w-full max-w-md rounded-lg border border-line bg-surface p-6 text-center">
        <span className="mx-auto mb-3 grid size-10 place-items-center rounded-full bg-warn/10 text-warn">
          <AlertTriangle size={18} />
        </span>
        <h2 className="text-base font-semibold text-ink">Something went wrong</h2>
        <p className="mt-1 text-sm text-ink-2">
          This page hit an unexpected error. Your data is safe — try again, or
          head back to the dashboard.
        </p>
        {error.digest && (
          <p className="mt-1 text-[11px] text-ink-3 tabular">ref: {error.digest}</p>
        )}
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button size="sm" onClick={reset}>
            Try again
          </Button>
          <Link
            href="/"
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Go to dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
