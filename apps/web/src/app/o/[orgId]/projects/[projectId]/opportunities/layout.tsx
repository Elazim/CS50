"use client";

import { use } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useOpportunityMutations } from "@/lib/opportunities";

const VIEWS = [
  { slug: "", label: "Register" },
  { slug: "roadmap", label: "Roadmap" },
] as const;

export default function OpportunitiesLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const pathname = usePathname();
  const base = `/o/${orgId}/projects/${projectId}/opportunities`;
  const { generate } = useOpportunityMutations(orgId, projectId);

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
            </Link>
          );
        })}
        <Button
          variant="secondary"
          size="sm"
          className="ml-auto"
          onClick={() => generate.mutate()}
          disabled={generate.isPending}
        >
          <Lightbulb size={13} />
          {generate.isPending ? "Generating…" : "Generate opportunities"}
        </Button>
      </div>
      {children}
    </div>
  );
}
