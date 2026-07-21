import { type HTMLAttributes } from "react";
import { cn } from "@/lib/ui";

export type CardVariant = "default" | "elevated" | "glass";

const CARD_VARIANTS: Record<CardVariant, string> = {
  default: "border border-line bg-surface shadow-xs",
  elevated: "border border-line bg-surface shadow-md",
  glass: "glass shadow-md",
};

/** Bordered surface panel. `elevated` lifts it; `glass` is a translucent blur. */
export function Card({
  className,
  variant = "default",
  ...props
}: HTMLAttributes<HTMLDivElement> & { variant?: CardVariant }) {
  return <div className={cn("rounded-xl", CARD_VARIANTS[variant], className)} {...props} />;
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 border-b border-line px-4 py-3",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-sm font-semibold text-ink", className)} {...props} />;
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />;
}
