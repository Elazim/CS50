"use client";

import { use, useState } from "react";
import { Check, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { CitationChip } from "@/components/citation-chip";
import { cn } from "@/lib/utils";
import { useEntities, useKnowledgeMutations } from "@/lib/knowledge";

const TYPES = [
  { key: undefined, label: "All" },
  { key: "actor", label: "Actors" },
  { key: "system", label: "Systems" },
  { key: "process", label: "Processes" },
  { key: "process_step", label: "Steps" },
  { key: "business_rule", label: "Rules" },
  { key: "pain_point", label: "Pain points" },
] as const;

const STATE_TONE = {
  ai_generated: "warning",
  confirmed: "success",
  edited: "info",
  rejected: "danger",
} as const;

export default function EntitiesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const [type, setType] = useState<string | undefined>(undefined);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data: entities, isLoading } = useEntities(orgId, projectId, type);
  const { reviewEntity } = useKnowledgeMutations(orgId, projectId);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5">
        {TYPES.map((t) => (
          <button
            key={t.label}
            type="button"
            onClick={() => setType(t.key)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs transition-colors",
              type === t.key
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-muted hover:border-border-strong",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-muted">Loading entities…</p>
      ) : !entities || entities.length === 0 ? (
        <EmptyState
          title="No entities yet"
          description="Upload documents, then run extraction to build the knowledge model."
        />
      ) : (
        <ul className="flex flex-col gap-1.5">
          {entities.map((entity) => (
            <li
              key={entity.id}
              className="rounded-md border border-border bg-surface px-4 py-2.5"
            >
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="text-left text-sm font-medium hover:text-accent"
                  onClick={() =>
                    setExpanded(expanded === entity.id ? null : entity.id)
                  }
                >
                  {entity.name}
                </button>
                <Badge tone="neutral">{entity.type.replace("_", " ")}</Badge>
                <Badge tone={STATE_TONE[entity.review_state]}>
                  {entity.review_state.replace("_", " ")}
                </Badge>
                {entity.novel ? <Badge tone="info">novel</Badge> : null}
                {entity.attrs?.taxonomy ? (
                  <Badge tone="danger">{String(entity.attrs.taxonomy)}</Badge>
                ) : null}
                {entity.review_state === "ai_generated" ? (
                  <span className="ml-auto flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label="Confirm"
                      onClick={() =>
                        reviewEntity.mutate({ entityId: entity.id, action: "confirm" })
                      }
                    >
                      <Check size={13} className="text-success" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label="Reject"
                      onClick={() =>
                        reviewEntity.mutate({ entityId: entity.id, action: "reject" })
                      }
                    >
                      <X size={13} className="text-danger" />
                    </Button>
                  </span>
                ) : null}
              </div>
              {expanded === entity.id ? (
                <div className="mt-2 flex flex-col gap-2 border-t border-border/60 pt-2">
                  {entity.evidence.map((evidence, index) => (
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
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
