"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";

export default function ProjectOverviewPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);

  const { data: documents } = useQuery({
    queryKey: ["documents", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/documents",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });

  const total = documents?.length ?? 0;
  const ready = documents?.filter((d) => d.status === "ready").length ?? 0;
  const processing =
    documents?.filter((d) => d.status === "processing").length ?? 0;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card>
        <div className="flex items-center gap-2 text-muted">
          <FileText size={15} />
          <h2 className="text-sm font-medium">Documents</h2>
        </div>
        <p className="mt-3 font-mono text-2xl font-semibold">
          {total}
          <span className="ml-2 text-sm font-normal text-muted">
            {ready} processed{processing > 0 ? ` · ${processing} processing` : ""}
          </span>
        </p>
        <Link
          href={`/o/${orgId}/projects/${projectId}/documents`}
          className="mt-4 inline-flex items-center gap-1 text-sm text-accent hover:underline"
        >
          Upload documents <ArrowRight size={13} />
        </Link>
      </Card>
      <Card>
        <h2 className="text-sm font-medium text-muted">Next up</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Once documents are processed, the knowledge model — processes,
          actors, systems, pain points with evidence — lands here in the next
          milestone.
        </p>
      </Card>
    </div>
  );
}
