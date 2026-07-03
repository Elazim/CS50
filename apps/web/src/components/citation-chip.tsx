import Link from "next/link";
import { FileText } from "lucide-react";

/** The signature component (docs/07): every AI-derived or retrieved
 * statement links back to its exact source location. */
export function CitationChip({
  href,
  filename,
  detail,
}: {
  href: string;
  filename: string;
  detail?: string;
}) {
  return (
    <Link
      href={href}
      className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface-raised px-2.5 py-1 text-xs text-muted transition-colors hover:border-accent hover:text-foreground"
      title={detail ? `${filename} — ${detail}` : filename}
    >
      <FileText size={11} className="shrink-0 text-accent" />
      <span className="truncate">{filename}</span>
      {detail ? <span className="shrink-0 text-faint">· {detail}</span> : null}
    </Link>
  );
}
