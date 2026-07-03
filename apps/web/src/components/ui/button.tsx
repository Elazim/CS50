import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-accent-foreground hover:bg-accent-hover",
        secondary:
          "border border-border bg-surface text-foreground hover:border-border-strong hover:bg-surface-raised",
        ghost: "text-muted hover:bg-surface-raised hover:text-foreground",
        danger: "bg-danger text-white hover:opacity-90",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        md: "h-9 px-4",
        lg: "h-10 px-5",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants>) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
