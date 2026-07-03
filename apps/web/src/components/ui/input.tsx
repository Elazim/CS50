import { cn } from "@/lib/utils";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-border bg-surface px-3 text-sm text-foreground",
        "placeholder:text-faint focus:border-accent",
        className,
      )}
      {...props}
    />
  );
}
