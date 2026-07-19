import { type HTMLAttributes, type ThHTMLAttributes, type TdHTMLAttributes } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/ui";

/** Scroll container + table. Wrap in Table so wide data never breaks the page. */
export function Table({
  className,
  minWidth,
  ...props
}: HTMLAttributes<HTMLTableElement> & { minWidth?: string }) {
  return (
    <div className="overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-sm", className)}
        style={minWidth ? { minWidth } : undefined}
        {...props}
      />
    </div>
  );
}

export function Thead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn("border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-3", className)}
      {...props}
    />
  );
}

export function Tbody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-line", className)} {...props} />;
}

export function Tr({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors hover:bg-surface-2/60", className)} {...props} />;
}

type ThProps = ThHTMLAttributes<HTMLTableCellElement> & {
  numeric?: boolean;
  sortable?: boolean;
  sortDir?: "asc" | "desc" | null;
  onSort?: () => void;
};

export function Th({ numeric, sortable, sortDir, onSort, className, children, ...props }: ThProps) {
  const Icon = sortDir === "asc" ? ChevronUp : sortDir === "desc" ? ChevronDown : ChevronsUpDown;
  return (
    <th
      className={cn("px-2.5 py-2 font-medium", numeric && "text-right", className)}
      aria-sort={sortDir === "asc" ? "ascending" : sortDir === "desc" ? "descending" : undefined}
      {...props}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onSort}
          className={cn(
            "inline-flex items-center gap-1 hover:text-ink",
            numeric && "flex-row-reverse",
            sortDir && "text-ink",
          )}
        >
          {children}
          <Icon size={12} className={cn(!sortDir && "opacity-40")} />
        </button>
      ) : (
        children
      )}
    </th>
  );
}

export function Td({
  numeric,
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      className={cn("px-2.5 py-2 text-ink-2", numeric && "tabular text-right text-ink", className)}
      {...props}
    />
  );
}
