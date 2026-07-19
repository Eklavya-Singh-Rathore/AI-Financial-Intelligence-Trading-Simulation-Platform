import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/ui";
import { inputClasses } from "@/lib/ui";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(inputClasses, className)} {...props} />;
  },
);
