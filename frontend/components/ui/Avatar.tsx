import { cn } from "@/lib/ui";

type Props = {
  /** Name or email to derive initials from. */
  name?: string;
  size?: "sm" | "md";
  className?: string;
};

function initials(name?: string): string {
  if (!name) return "?";
  const base = name.split("@")[0];
  const parts = base.split(/[.\s_-]+/).filter(Boolean);
  const chars = parts.length >= 2 ? parts[0][0] + parts[1][0] : base.slice(0, 2);
  return chars.toUpperCase();
}

const SIZES = { sm: "size-7 text-[11px]", md: "size-9 text-xs" };

/** Circular initials avatar on the brand gradient. */
export function Avatar({ name, size = "md", className }: Props) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-grid select-none place-items-center rounded-full bg-grad-primary font-semibold text-on-accent",
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
