import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/ui";
import { inputClasses } from "@/lib/ui";

/** Native select styled to match Input (consistent form-control vocabulary). */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return (
      <select ref={ref} className={cn(inputClasses, "cursor-pointer pr-8", className)} {...props} />
    );
  },
);
