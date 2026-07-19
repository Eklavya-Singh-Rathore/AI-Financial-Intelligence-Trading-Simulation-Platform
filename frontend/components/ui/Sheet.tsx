"use client";

import { X } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/ui";

type Side = "right" | "left" | "bottom";

type Props = {
  open: boolean;
  onClose: () => void;
  side?: Side;
  title?: ReactNode;
  className?: string;
  children: ReactNode;
};

const SIDE_POS: Record<Side, string> = {
  right: "right-0 top-0 h-full w-[min(24rem,92vw)] border-l motion-safe:animate-slide-in-right",
  left: "left-0 top-0 h-full w-[min(24rem,92vw)] border-r",
  bottom:
    "bottom-0 inset-x-0 max-h-[85vh] rounded-t-xl border-t motion-safe:animate-slide-in-bottom",
};

/** Slide-over panel. Portaled to <body> to escape overflow/stacking contexts;
 *  closes on Escape and backdrop click; locks body scroll while open. */
export function Sheet({ open, onClose, side = "right", title, className, children }: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/40 motion-safe:animate-fade-in"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "absolute flex flex-col border-line bg-surface shadow-md",
          SIDE_POS[side],
          className,
        )}
      >
        {title !== undefined && (
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div className="text-sm font-semibold text-ink">{title}</div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1 text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
