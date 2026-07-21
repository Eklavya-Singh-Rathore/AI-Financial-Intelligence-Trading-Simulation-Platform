"use client";

import { type ButtonHTMLAttributes, type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/ui";

type Props = {
  /** Trigger content (rendered inside a button). */
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "end";
  /** Open below (default) or above the trigger — use "top" for footer menus. */
  side?: "top" | "bottom";
  triggerClassName?: string;
  className?: string;
  label?: string;
};

/** Click-toggled menu with outside-click + Escape close. No dependency. */
export function DropdownMenu({
  trigger,
  children,
  align = "end",
  side = "bottom",
  triggerClassName,
  className,
  label,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className={cn("inline-flex", triggerClassName)}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          onClick={() => setOpen(false)}
          className={cn(
            "absolute z-50 min-w-44 rounded-xl border border-line bg-surface p-1 shadow-lg animate-scale-in",
            side === "top" ? "bottom-full mb-1.5 origin-bottom" : "top-full mt-1.5 origin-top",
            align === "end" ? "right-0" : "left-0",
            className,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/** A single menu row. Renders a button by default. */
export function DropdownItem({
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      role="menuitem"
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-ink-2",
        "transition-colors hover:bg-surface-2 hover:text-ink motion-reduce:transition-none",
        className,
      )}
      {...props}
    />
  );
}
