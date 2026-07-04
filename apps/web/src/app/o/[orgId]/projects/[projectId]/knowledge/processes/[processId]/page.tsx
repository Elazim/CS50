"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Download, Hand, Split, Workflow } from "lucide-react";
import { api, API_URL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CitationChip } from "@/components/citation-chip";
import type { ProcessGraph } from "@/lib/knowledge";

const COL_WIDTH = 240;

/** Swimlane canvas (docs/07 §4.2): lanes by actor, columns by sequence,
 * pain-point markers, evidence panel on select. Read-mode rendering is
 * deterministic — drawing the graph is not an AI job (docs/03 §5). */
export default function ProcessCanvasPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; processId: string }>;
}) {
  const { orgId, projectId, processId } = use(params);
  const [selected, setSelected] = useState<string | null>(null);

  const { data: graph, isLoading } = useQuery<ProcessGraph>({
    queryKey: ["process-graph", orgId, processId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/processes/{process_id}/graph",
        { params: { path: { org_id: orgId, process_id: processId } } },
      );
      if (error) throw error;
      return data;
    },
  });

  if (isLoading || !graph) return <p className="text-muted">Loading process…</p>;

  const lanes = graph.lanes.length ? graph.lanes : ["Unassigned"];
  const maxOrder = Math.max(...graph.nodes.map((n) => n.order), 0);
  const selectedNode = graph.nodes.find((n) => n.id === selected);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/o/${orgId}/projects/${projectId}/knowledge/processes`}
          className="inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
        >
          <ArrowLeft size={12} /> Processes
        </Link>
        <h2 className="text-base font-semibold tracking-tight">{graph.process.name}</h2>
        <Badge tone="neutral">{graph.nodes.length} steps</Badge>
        <a
          className="ml-auto"
          href={`${API_URL}/v1/orgs/${orgId}/processes/${processId}/bpmn`}
        >
          <Button variant="secondary" size="sm">
            <Download size={13} /> Export BPMN 2.0
          </Button>
        </a>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <div style={{ minWidth: 160 + (maxOrder + 1) * COL_WIDTH }}>
          {lanes.map((lane) => (
            <div
              key={lane}
              className="flex border-b border-border/60 last:border-b-0"
            >
              <div className="flex w-40 shrink-0 items-center border-r border-border/60 bg-surface-raised px-3 py-6 text-xs font-medium text-muted">
                {lane}
              </div>
              <div
                className="relative grid flex-1 gap-3 px-3 py-4"
                style={{
                  gridTemplateColumns: `repeat(${maxOrder + 1}, ${COL_WIDTH - 20}px)`,
                }}
              >
                {graph.nodes
                  .filter((node) => node.lane === lane)
                  .map((node) => (
                    <button
                      key={node.id}
                      type="button"
                      onClick={() =>
                        setSelected(selected === node.id ? null : node.id)
                      }
                      style={{ gridColumnStart: node.order + 1 }}
                      className={cn(
                        "flex flex-col gap-1 rounded-md border p-2.5 text-left text-xs transition-colors",
                        node.review_state === "ai_generated"
                          ? "border-dashed border-border-strong bg-ai-tint/60"
                          : "border-border bg-surface",
                        selected === node.id && "ring-2 ring-accent",
                      )}
                    >
                      <span className="flex items-center gap-1.5 text-faint">
                        {node.step_type === "manual" ? (
                          <Hand size={11} />
                        ) : node.step_type === "decision" ? (
                          <Split size={11} />
                        ) : (
                          <Workflow size={11} />
                        )}
                        {node.step_type}
                        {node.pain_points.length > 0 ? (
                          <span className="ml-auto inline-flex items-center gap-0.5 text-danger">
                            <AlertTriangle size={11} />
                            {node.pain_points.length}
                          </span>
                        ) : null}
                      </span>
                      <span className="line-clamp-3 leading-snug text-foreground/90">
                        {node.name}
                      </span>
                    </button>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {selectedNode ? (
        <div className="rounded-md border border-border bg-surface p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{selectedNode.name}</span>
            <Badge tone="neutral">{selectedNode.step_type}</Badge>
            <Badge
              tone={selectedNode.review_state === "confirmed" ? "success" : "warning"}
            >
              {selectedNode.review_state.replace("_", " ")}
            </Badge>
          </div>
          {selectedNode.pain_points.length > 0 ? (
            <div className="mt-3 flex flex-col gap-1">
              {selectedNode.pain_points.map((pain) => (
                <p
                  key={String(pain.id)}
                  className="flex items-start gap-2 text-sm text-danger"
                >
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  <span>
                    {String(pain.name)}
                    {pain.taxonomy ? (
                      <Badge tone="danger" className="ml-2">
                        {String(pain.taxonomy)}
                      </Badge>
                    ) : null}
                  </span>
                </p>
              ))}
            </div>
          ) : null}
          <div className="mt-3 flex flex-col gap-2">
            {selectedNode.evidence.map((evidence, index) => (
              <div key={index} className="border-l-2 border-accent/50 pl-3">
                {evidence.quote ? (
                  <p className="text-sm italic text-muted">“{evidence.quote}”</p>
                ) : null}
                <div className="mt-1">
                  <CitationChip
                    href={`/o/${orgId}/projects/${projectId}/documents/${evidence.document_id}#el-${evidence.element_id}`}
                    filename={evidence.filename ?? "source"}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-faint">
          Select a step to see its evidence and pain points. Dashed steps are
          AI-generated and awaiting review.
        </p>
      )}
    </div>
  );
}
