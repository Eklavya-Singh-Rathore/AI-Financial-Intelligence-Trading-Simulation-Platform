// Design-system class helpers (Phase 6). Variant maps live here (pure, tree-
// shakeable) so components stay thin and the vocabulary is consistent.
import clsx, { type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

// Shared focus ring — every interactive control uses the same one.
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 " +
  "focus-visible:ring-offset-1 focus-visible:ring-offset-surface";

export type ButtonVariant = "primary" | "outline" | "ghost" | "subtle" | "danger";
export type ButtonSize = "sm" | "md" | "icon" | "icon-sm";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap " +
  "transition-colors duration-150 motion-reduce:transition-none " +
  "disabled:pointer-events-none disabled:opacity-50 " +
  focusRing;

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:brightness-110 active:brightness-95",
  outline: "border border-line bg-surface text-ink hover:bg-surface-2 active:bg-line/40",
  ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink active:bg-line/40",
  subtle: "bg-surface-2 text-ink hover:bg-line/50 active:bg-line/70",
  danger: "bg-loss text-white hover:brightness-110 active:brightness-95",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
  icon: "h-9 w-9",
  "icon-sm": "h-8 w-8",
};

export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  extra?: ClassValue,
): string {
  return cn(BUTTON_BASE, BUTTON_VARIANTS[variant], BUTTON_SIZES[size], extra);
}

export type Tone = "neutral" | "accent" | "gain" | "loss" | "warn";

// Soft tinted badges (used for statuses, counts, tags).
export const BADGE_TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-ink-2 border-line",
  accent: "bg-accent/10 text-accent border-accent/20",
  gain: "bg-gain/10 text-gain border-gain/20",
  loss: "bg-loss/10 text-loss border-loss/20",
  warn: "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
};

export const inputClasses =
  "h-9 w-full rounded-md border border-line bg-surface px-3 text-sm text-ink " +
  "placeholder:text-ink-3 transition-colors duration-150 motion-reduce:transition-none " +
  "hover:border-ink-3/60 disabled:cursor-not-allowed disabled:opacity-50 " +
  focusRing;
