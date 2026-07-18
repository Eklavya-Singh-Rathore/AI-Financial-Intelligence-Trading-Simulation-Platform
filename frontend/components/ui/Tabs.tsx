import { cn } from "@/lib/ui";

export type TabItem = { value: string; label: string; count?: number };

type Props = {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
};

/** Underline tab strip. Horizontal-scrolls when it overflows (many watchlists). */
export function Tabs({ items, value, onValueChange, className }: Props) {
  return (
    <div className={cn("flex gap-1 overflow-x-auto border-b border-line", className)} role="tablist">
      {items.map((it) => {
        const active = it.value === value;
        return (
          <button
            key={it.value}
            role="tab"
            aria-selected={active}
            onClick={() => onValueChange(it.value)}
            className={cn(
              "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "border-accent text-accent"
                : "border-transparent text-ink-2 hover:text-ink",
            )}
          >
            {it.label}
            {it.count !== undefined && (
              <span className="tabular ml-1.5 text-xs text-ink-3">{it.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
