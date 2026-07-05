"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileSpreadsheet,
  FileText,
  History,
  Presentation,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { api, API_URL, errorMessage } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type { components } from "@atc/client";

type Deliverable = components["schemas"]["DeliverableOut"];
type Version = components["schemas"]["VersionOut"];

const TYPES: {
  key: components["schemas"]["DeliverableType"];
  label: string;
  description: string;
  icon: typeof FileText;
}[] = [
  {
    key: "executive_summary",
    label: "Executive summary",
    description:
      "The board-ready deck: findings, top opportunities, modeled savings, roadmap — every claim cited in the speaker notes.",
    icon: Presentation,
  },
  {
    key: "current_state_assessment",
    label: "Current-state assessment",
    description:
      "BRD-style document: actors, systems, each process with its steps and pain points, business rules — with a source appendix.",
    icon: FileText,
  },
  {
    key: "opportunity_register",
    label: "Opportunity register",
    description:
      "The working backlog as a spreadsheet: scores, ROI figures, full assumption sheets, and citations.",
    icon: FileSpreadsheet,
  },
  {
    key: "roadmap_deck",
    label: "Roadmap deck",
    description:
      "Horizon-lane deck of sequenced initiatives with quick wins flagged.",
    icon: Presentation,
  },
];

const FORMAT_LABEL: Record<string, string> = {
  pptx: "PowerPoint",
  docx: "Word",
  xlsx: "Excel",
  md: "Markdown",
};

export default function DeliverablesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [historyFor, setHistoryFor] = useState<string | null>(null);

  const { data: deliverables } = useQuery({
    queryKey: ["deliverables", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/deliverables",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });

  const generate = useMutation({
    mutationFn: async (type: components["schemas"]["DeliverableType"]) => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/projects/{project_id}/deliverables",
        {
          params: { path: { org_id: orgId, project_id: projectId } },
          body: { type },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      toast("Generating — a new version appears when rendering finishes");
      let polls = 0;
      const timer = setInterval(() => {
        queryClient.invalidateQueries({
          queryKey: ["deliverables", orgId, projectId],
        });
        queryClient.invalidateQueries({ queryKey: ["versions"] });
        if (++polls >= 8) clearInterval(timer);
      }, 1500);
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const byType = new Map((deliverables ?? []).map((d) => [d.type, d]));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {TYPES.map((type) => {
        const deliverable = byType.get(type.key);
        const Icon = type.icon;
        return (
          <Card key={type.key} className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Icon size={16} className="text-accent" />
              <h2 className="text-sm font-semibold">{type.label}</h2>
              {deliverable && deliverable.latest_version > 0 ? (
                <Badge tone="success">v{deliverable.latest_version}</Badge>
              ) : (
                <Badge tone="neutral">not generated</Badge>
              )}
            </div>
            <p className="text-sm leading-relaxed text-muted">{type.description}</p>
            <div className="mt-auto flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={() => generate.mutate(type.key)}
                disabled={generate.isPending}
              >
                <RefreshCw size={13} />
                {deliverable && deliverable.latest_version > 0
                  ? "Regenerate"
                  : "Generate"}
              </Button>
              {deliverable && deliverable.latest_version > 0 ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setHistoryFor(historyFor === deliverable.id ? null : deliverable.id)
                  }
                >
                  <History size={13} /> Versions
                </Button>
              ) : null}
            </div>
            {deliverable && historyFor === deliverable.id ? (
              <VersionHistory
                orgId={orgId}
                projectId={projectId}
                deliverable={deliverable}
              />
            ) : deliverable && deliverable.latest_version > 0 ? (
              <LatestDownloads
                orgId={orgId}
                projectId={projectId}
                deliverable={deliverable}
              />
            ) : null}
          </Card>
        );
      })}
    </div>
  );
}

function useVersions(orgId: string, deliverableId: string) {
  return useQuery({
    queryKey: ["versions", orgId, deliverableId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/deliverables/{deliverable_id}/versions",
        { params: { path: { org_id: orgId, deliverable_id: deliverableId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}

function FeedbackButtons({
  orgId,
  projectId,
  version,
}: {
  orgId: string;
  projectId: string;
  version: Version;
}) {
  const toast = useToast();
  const [sent, setSent] = useState<number | null>(null);
  const submit = useMutation({
    mutationFn: async (rating: number) => {
      const { error } = await api.POST("/v1/orgs/{org_id}/feedback", {
        params: { path: { org_id: orgId } },
        body: {
          project_id: projectId,
          subject_type: "deliverable_version",
          subject_id: version.id,
          rating,
          comment: null,
        },
      });
      if (error) throw error;
      return rating;
    },
    onSuccess: (rating) => {
      setSent(rating);
      toast("Thanks — feedback recorded");
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });
  return (
    <span className="inline-flex gap-0.5">
      <button
        type="button"
        aria-label="Good deliverable"
        disabled={sent !== null}
        onClick={() => submit.mutate(1)}
        className={sent === 1 ? "text-success" : "text-faint hover:text-success"}
      >
        <ThumbsUp size={12} />
      </button>
      <button
        type="button"
        aria-label="Needs work"
        disabled={sent !== null}
        onClick={() => submit.mutate(-1)}
        className={sent === -1 ? "text-danger" : "text-faint hover:text-danger"}
      >
        <ThumbsDown size={12} />
      </button>
    </span>
  );
}

function DownloadRow({ orgId, version }: { orgId: string; version: Version }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {version.formats.map((format) => (
        <a
          key={format}
          href={`${API_URL}/v1/orgs/${orgId}/deliverable-versions/${version.id}/download?format=${format}`}
          className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted transition-colors hover:border-accent hover:text-accent"
        >
          {FORMAT_LABEL[format] ?? format}
        </a>
      ))}
    </span>
  );
}

function LatestDownloads({
  orgId,
  projectId,
  deliverable,
}: {
  orgId: string;
  projectId: string;
  deliverable: Deliverable;
}) {
  const { data: versions } = useVersions(orgId, deliverable.id);
  const latest = versions?.[0];
  if (!latest) return null;
  return (
    <div className="flex items-center gap-2 border-t border-border/60 pt-3">
      <DownloadRow orgId={orgId} version={latest} />
      <FeedbackButtons orgId={orgId} projectId={projectId} version={latest} />
      <span className="ml-auto text-xs text-faint">
        {latest.citation_count} sources · model {latest.review_coverage} reviewed
      </span>
    </div>
  );
}

function VersionHistory({
  orgId,
  projectId,
  deliverable,
}: {
  orgId: string;
  projectId: string;
  deliverable: Deliverable;
}) {
  const { data: versions } = useVersions(orgId, deliverable.id);
  if (!versions) return <p className="text-xs text-muted">Loading versions…</p>;
  return (
    <ol className="flex flex-col gap-2 border-t border-border/60 pt-3">
      {versions.map((version) => (
        <li key={version.id} className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={version.version === deliverable.latest_version ? "accent" : "neutral"}>
            v{version.version}
          </Badge>
          <span className="text-faint">
            {new Date(version.created_at).toLocaleString()} ·{" "}
            {version.citation_count} sources · {version.review_coverage} reviewed
          </span>
          <span className="ml-auto flex items-center gap-2">
            <DownloadRow orgId={orgId} version={version} />
            <FeedbackButtons orgId={orgId} projectId={projectId} version={version} />
          </span>
        </li>
      ))}
    </ol>
  );
}
