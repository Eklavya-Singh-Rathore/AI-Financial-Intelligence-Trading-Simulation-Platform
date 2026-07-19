import { Loader2 } from "lucide-react";
import { cn } from "@/lib/ui";

/** Inline activity indicator — for buttons/actions, not full-content loading
 *  (use Skeleton for that). */
export function Spinner({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <Loader2
      size={size}
      className={cn("animate-spin motion-reduce:animate-none", className)}
      aria-hidden
    />
  );
}
