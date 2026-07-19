import { type HTMLAttributes } from "react";
import { BADGE_TONES, type Tone, cn } from "@/lib/ui";

type Props = HTMLAttributes<HTMLSpanElement> & { tone?: Tone };

/** Small tinted label for statuses, counts, and tags. */
export function Badge({ tone = "neutral", className, ...props }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        BADGE_TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
