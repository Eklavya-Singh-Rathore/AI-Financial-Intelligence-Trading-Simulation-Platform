import { forwardRef, type ButtonHTMLAttributes } from "react";
import { type ButtonSize, type ButtonVariant, buttonClasses } from "@/lib/ui";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

/** Primary interactive control. States: hover, active, focus-visible, disabled. */
export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant, size, className, type = "button", ...props },
  ref,
) {
  return (
    <button ref={ref} type={type} className={buttonClasses(variant, size, className)} {...props} />
  );
});
