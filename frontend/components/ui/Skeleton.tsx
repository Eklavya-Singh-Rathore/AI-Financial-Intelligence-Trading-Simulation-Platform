import { type HTMLAttributes } from "react";
import { cn } from "@/lib/ui";

/** Content placeholder for loading states (product register: skeletons, not spinners). */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-surface-2 motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
}

/** A few stacked skeleton lines — common table/list loading shape. */
export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}
