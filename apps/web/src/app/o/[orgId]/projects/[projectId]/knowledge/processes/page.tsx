"use client";

import { use } from "react";
import Link from "next/link";
import { Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { useEntities } from "@/lib/knowledge";

export default function ProcessesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const { data: processes, isLoading } = useEntities(orgId, projectId, "process");

  if (isLoading) return <p className="text-muted">Loading processes…</p>;
  if (!processes || processes.length === 0) {
    return (
      <EmptyState
        title="No processes identified yet"
        description="Run extraction — SOPs and process documents become current-state process models."
      />
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {processes.map((process) => (
        <li key={process.id}>
          <Link
            href={`/o/${orgId}/projects/${projectId}/knowledge/processes/${process.id}`}
            className="flex items-center gap-3 rounded-md border border-border bg-surface px-4 py-3 transition-colors hover:border-border-strong hover:bg-surface-raised"
          >
            <Workflow size={16} className="text-accent" />
            <span className="font-medium">{process.name}</span>
            <Badge
              tone={process.review_state === "confirmed" ? "success" : "warning"}
            >
              {process.review_state.replace("_", " ")}
            </Badge>
          </Link>
        </li>
      ))}
    </ul>
  );
}
