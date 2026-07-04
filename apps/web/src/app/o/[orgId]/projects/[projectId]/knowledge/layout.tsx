"use client";

import { use } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useKnowledgeMutations, useKnowledgeSummary } from "@/lib/knowledge";

const VIEWS = [
  { slug: "", label: "Review queue" },
  { slug: "entities", label: "Entities" },
  { slug: "processes", label: "Processes" },
] as const;

export default function KnowledgeLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const pathname = usePathname();
  const base = `/o/${orgId}/projects/${projectId}/knowledge`;
  const { data: summary } = useKnowledgeSummary(orgId, projectId);
  const { extract } = useKnowledgeMutations(orgId, projectId);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-1">
        {VIEWS.map((view) => {
          const href = view.slug ? `${base}/${view.slug}` : base;
          const active =
            view.slug === ""
              ? pathname === base
              : pathname.startsWith(`${base}/${view.slug}`);
          return (
            <Link
              key={view.label}
              href={href}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm transition-colors",
                active
                  ? "bg-surface-raised font-medium text-foreground"
                  : "text-muted hover:text-foreground",
              )}
            >
              {view.label}
              {view.slug === "" && summary?.open_review_items ? (
                <span className="ml-1.5 rounded-full bg-accent/20 px-1.5 text-xs text-accent">
                  {summary.open_review_items}
                </span>
              ) : null}
            </Link>
          );
        })}
        <Button
          variant="secondary"
          size="sm"
          className="ml-auto"
          onClick={() => extract.mutate()}
          disabled={extract.isPending}
        >
          <Sparkles size={13} />
          {extract.isPending ? "Extracting…" : "Run extraction"}
        </Button>
      </div>
      {children}
    </div>
  );
}
