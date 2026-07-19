import { type LucideIcon } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "@/lib/ui";

type Props = {
  icon?: LucideIcon;
  title: string;
  /** Teach the interface — say what this area does and how to start. */
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
};

export function EmptyState({ icon: Icon, title, description, action, className }: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
    >
      {Icon && <Icon size={24} className="text-ink-3" aria-hidden />}
      <div className="text-sm font-medium text-ink">{title}</div>
      {description && <p className="max-w-sm text-xs leading-relaxed text-ink-3">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
