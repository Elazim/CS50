"use client";

import { use } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

// Tabs beyond Documents ship in later milestones; they are visible but
// disabled so the product's shape is legible from M0 (docs/06).
const TABS = [
  { slug: "", label: "Overview", enabled: true },
  { slug: "documents", label: "Documents", enabled: true },
  { slug: "search", label: "Search", enabled: true },
  { slug: "knowledge", label: "Knowledge", enabled: true },
  { slug: "opportunities", label: "Opportunities", enabled: true },
  { slug: "deliverables", label: "Deliverables", enabled: true },
] as const;

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const pathname = usePathname();
  const base = `/o/${orgId}/projects/${projectId}`;

  const { data: project } = useQuery({
    queryKey: ["project", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-1 text-xs text-faint">
        <Link href={`/o/${orgId}`} className="hover:text-muted">
          Projects
        </Link>{" "}
        /
      </div>
      <h1 className="text-xl font-semibold tracking-tight">
        {project?.name ?? "…"}
      </h1>
      <nav className="mt-5 flex gap-1 border-b border-border" aria-label="Project sections">
        {TABS.map((tab) => {
          const href = tab.slug ? `${base}/${tab.slug}` : base;
          const active =
            tab.slug === ""
              ? pathname === base
              : pathname.startsWith(`${base}/${tab.slug}`);
          if (!tab.enabled) {
            return (
              <span
                key={tab.label}
                className="flex cursor-not-allowed items-center gap-1.5 px-3 py-2 text-sm text-faint"
                title="Coming in a later milestone"
              >
                {tab.label}
                <Badge tone="neutral">soon</Badge>
              </span>
            );
          }
          return (
            <Link
              key={tab.label}
              href={href}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-sm transition-colors",
                active
                  ? "border-accent font-medium text-foreground"
                  : "border-transparent text-muted hover:text-foreground",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      <div className="py-6">{children}</div>
    </div>
  );
}
