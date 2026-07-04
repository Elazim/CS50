"use client";

import { use, useCallback, useEffect, useState } from "react";
import { Check, GitMerge, Split, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { CitationChip } from "@/components/citation-chip";
import { cn } from "@/lib/utils";
import {
  useKnowledgeMutations,
  useReviewItems,
  type ReviewItemView,
} from "@/lib/knowledge";

/** The triage cockpit (docs/07 §4.1): j/k to move, c to accept, x to reject. */
export default function ReviewQueuePage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const { data: items, isLoading } = useReviewItems(orgId, projectId);
  const { reviewEntity, resolveItem } = useKnowledgeMutations(orgId, projectId);
  const [cursor, setCursor] = useState(0);

  const selected: ReviewItemView | undefined = items?.[cursor];

  const accept = useCallback(() => {
    if (!selected) return;
    if (selected.kind === "merge_proposal") {
      resolveItem.mutate({ itemId: selected.id, action: "merge" });
    } else if (selected.subject) {
      reviewEntity.mutate({ entityId: selected.subject.id, action: "confirm" });
    }
  }, [selected, resolveItem, reviewEntity]);

  const reject = useCallback(() => {
    if (!selected) return;
    if (selected.kind === "merge_proposal") {
      resolveItem.mutate({ itemId: selected.id, action: "keep_separate" });
    } else if (selected.subject) {
      reviewEntity.mutate({ entityId: selected.subject.id, action: "reject" });
    }
  }, [selected, resolveItem, reviewEntity]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement) return;
      if (event.key === "j") setCursor((c) => Math.min(c + 1, (items?.length ?? 1) - 1));
      if (event.key === "k") setCursor((c) => Math.max(c - 1, 0));
      if (event.key === "c") accept();
      if (event.key === "x") reject();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, accept, reject]);

  if (isLoading) return <p className="text-muted">Loading queue…</p>;
  if (!items || items.length === 0) {
    return (
      <EmptyState
        title="Queue is clear"
        description="Run extraction after uploading documents, or enjoy the silence — every open question has been answered."
      />
    );
  }
  const safeCursor = Math.min(cursor, items.length - 1);
  const current = items[safeCursor];

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(280px,1fr)_minmax(360px,1.4fr)]">
      <ol className="max-h-[70vh] overflow-y-auto rounded-md border border-border">
        {items.map((item, index) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => setCursor(index)}
              className={cn(
                "flex w-full flex-col gap-1 border-b border-border/60 px-3 py-2.5 text-left transition-colors",
                index === safeCursor ? "bg-ai-tint" : "hover:bg-surface-raised",
              )}
            >
              <span className="flex items-center gap-2">
                <Badge tone={item.kind === "merge_proposal" ? "info" : "warning"}>
                  {item.kind === "merge_proposal" ? "merge?" : "verify"}
                </Badge>
                {item.subject ? (
                  <span className="text-xs text-faint">{item.subject.type}</span>
                ) : null}
              </span>
              <span className="line-clamp-2 text-sm">{item.question}</span>
            </button>
          </li>
        ))}
      </ol>

      <div className="rounded-md border border-border bg-surface p-4">
        <p className="text-sm font-medium leading-relaxed">{current.question}</p>

        {current.subject ? (
          <div className="mt-3 rounded-md border border-border/60 bg-surface-raised p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{current.subject.name}</span>
              <Badge tone="neutral">{current.subject.type}</Badge>
              <Badge
                tone={
                  current.subject.confidence === "high"
                    ? "success"
                    : current.subject.confidence === "medium"
                      ? "warning"
                      : "danger"
                }
              >
                {current.subject.confidence}
              </Badge>
              {current.subject.attrs?.taxonomy ? (
                <Badge tone="danger">{String(current.subject.attrs.taxonomy)}</Badge>
              ) : null}
            </div>
            <div className="mt-3 flex flex-col gap-2">
              {current.subject.evidence.map((evidence, index) => (
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
        ) : null}

        <div className="mt-4 flex items-center gap-2">
          {current.kind === "merge_proposal" ? (
            <>
              <Button size="sm" onClick={accept}>
                <GitMerge size={13} /> Merge <kbd className="ml-1 text-xs opacity-60">c</kbd>
              </Button>
              <Button size="sm" variant="secondary" onClick={reject}>
                <Split size={13} /> Keep separate
                <kbd className="ml-1 text-xs opacity-60">x</kbd>
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" onClick={accept}>
                <Check size={13} /> Confirm <kbd className="ml-1 text-xs opacity-60">c</kbd>
              </Button>
              <Button size="sm" variant="danger" onClick={reject}>
                <X size={13} /> Reject <kbd className="ml-1 text-xs opacity-60">x</kbd>
              </Button>
            </>
          )}
          <span className="ml-auto text-xs text-faint">
            {safeCursor + 1} of {items.length} · j/k to navigate
          </span>
        </div>
      </div>
    </div>
  );
}
