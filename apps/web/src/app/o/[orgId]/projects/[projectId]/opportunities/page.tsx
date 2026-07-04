"use client";

import { use, useState } from "react";
import { Check, ChevronDown, ChevronRight, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { CitationChip } from "@/components/citation-chip";
import { cn } from "@/lib/utils";
import {
  money,
  useOpportunities,
  useOpportunityMutations,
  type Opportunity,
} from "@/lib/opportunities";

function ScorePips({ label, value, invert }: { label: string; value: number; invert?: boolean }) {
  // invert: high is bad (complexity, risk)
  const tone = invert
    ? value >= 4 ? "text-danger" : value >= 3 ? "text-warning" : "text-success"
    : value >= 4 ? "text-success" : value >= 3 ? "text-warning" : "text-muted";
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted">
      {label}
      <span className={cn("font-mono font-semibold", tone)}>{value}</span>
    </span>
  );
}

export default function OpportunityRegisterPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const { data: opportunities, isLoading } = useOpportunities(orgId, projectId);

  if (isLoading) return <p className="text-muted">Loading opportunities…</p>;
  if (!opportunities || opportunities.length === 0) {
    return (
      <EmptyState
        title="No opportunities yet"
        description="Build and review the knowledge model first, then generate opportunities — each one binds to documented pain points."
      />
    );
  }
  return (
    <ol className="flex flex-col gap-3">
      {opportunities.map((opportunity) => (
        <OpportunityCard
          key={opportunity.id}
          orgId={orgId}
          projectId={projectId}
          opportunity={opportunity}
        />
      ))}
    </ol>
  );
}

function OpportunityCard({
  orgId,
  projectId,
  opportunity,
}: {
  orgId: string;
  projectId: string;
  opportunity: Opportunity;
}) {
  const [open, setOpen] = useState(false);
  const { review } = useOpportunityMutations(orgId, projectId);

  return (
    <li className="rounded-md border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 text-left text-sm font-medium hover:text-accent"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {opportunity.title}
        </button>
        <Badge tone="accent">{opportunity.taxonomy_type.replace(/_/g, " ")}</Badge>
        <Badge
          tone={
            opportunity.review_state === "confirmed"
              ? "success"
              : opportunity.review_state === "rejected"
                ? "danger"
                : "warning"
          }
        >
          {opportunity.review_state.replace("_", " ")}
        </Badge>
        <span className="ml-auto flex items-center gap-3">
          <ScorePips label="impact" value={opportunity.impact_score} />
          <ScorePips label="complexity" value={opportunity.complexity_score} invert />
          <ScorePips label="risk" value={opportunity.risk_score} invert />
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted">
        {opportunity.roi ? (
          <>
            <span>
              Net annual:{" "}
              <span className="font-mono text-foreground">
                {money(opportunity.roi.computed.net_annual_savings as number)}
              </span>
            </span>
            <span>
              Payback:{" "}
              <span className="font-mono text-foreground">
                {opportunity.roi.computed.payback_months
                  ? `${opportunity.roi.computed.payback_months} mo`
                  : "—"}
              </span>
            </span>
          </>
        ) : null}
        {opportunity.process_name ? (
          <span className="text-xs text-faint">in {opportunity.process_name}</span>
        ) : null}
      </div>

      {open ? (
        <div className="mt-3 flex flex-col gap-4 border-t border-border/60 pt-3">
          <p className="text-sm leading-relaxed text-muted">{opportunity.rationale}</p>
          <div className="text-sm leading-relaxed whitespace-pre-line">
            {opportunity.description}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {opportunity.evidence.map((evidence, index) => (
              <CitationChip
                key={index}
                href={`/o/${orgId}/projects/${projectId}/documents/${evidence.document_id}#el-${evidence.element_id}`}
                filename={evidence.filename ?? "source"}
              />
            ))}
          </div>
          {opportunity.roi ? (
            <AssumptionSheet
              orgId={orgId}
              projectId={projectId}
              opportunity={opportunity}
            />
          ) : null}
          {opportunity.review_state === "ai_generated" ? (
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() =>
                  review.mutate({ opportunityId: opportunity.id, action: "confirm" })
                }
              >
                <Check size={13} /> Confirm
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() =>
                  review.mutate({ opportunityId: opportunity.id, action: "reject" })
                }
              >
                <X size={13} /> Reject
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function AssumptionSheet({
  orgId,
  projectId,
  opportunity,
}: {
  orgId: string;
  projectId: string;
  opportunity: Opportunity;
}) {
  const { patchRoi } = useOpportunityMutations(orgId, projectId);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const roi = opportunity.roi!;

  const dirty = Object.keys(draft).length > 0;

  return (
    <div className="rounded-md border border-border/60 bg-surface-raised p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-medium uppercase tracking-wide text-muted">
          ROI assumption sheet · v{roi.version}
        </h4>
        {dirty ? (
          <Button
            size="sm"
            onClick={() => {
              patchRoi.mutate({
                opportunityId: opportunity.id,
                assumptions: Object.entries(draft).map(([key, value]) => ({
                  key,
                  value: Number(value),
                })),
              });
              setDraft({});
            }}
            disabled={patchRoi.isPending}
          >
            Save & recompute
          </Button>
        ) : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {roi.assumptions.map((assumption) => {
          const a = assumption as {
            key: string; label: string; value: number; unit: string; source: string;
          };
          return (
            <label key={a.key} className="flex flex-col gap-1 text-xs text-muted">
              <span className="flex items-center gap-1.5">
                {a.label}
                <Badge tone={a.source === "estimate" ? "warning" : "success"}>
                  {a.source === "estimate" ? "estimate" : "analyst"}
                </Badge>
              </span>
              <span className="flex items-center gap-2">
                <Input
                  className="h-8 font-mono"
                  inputMode="decimal"
                  value={draft[a.key] ?? String(a.value)}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, [a.key]: e.target.value }))
                  }
                />
                <span className="shrink-0 text-faint">{a.unit}</span>
              </span>
            </label>
          );
        })}
      </div>
      <div className="mt-3 grid gap-2 border-t border-border/60 pt-3 sm:grid-cols-3">
        <Figure label="Annual hours saved" value={String(roi.computed.annual_hours_saved ?? "—")} />
        <Figure label="FTE equivalent" value={String(roi.computed.fte_equivalent ?? "—")} />
        <Figure label="Gross annual savings" value={money(roi.computed.gross_annual_savings as number)} />
        <Figure label="Net annual savings" value={money(roi.computed.net_annual_savings as number)} />
        <Figure
          label="Payback"
          value={roi.computed.payback_months ? `${roi.computed.payback_months} months` : "—"}
        />
        <Figure label="3-year net" value={money(roi.computed.three_year_net as number)} />
      </div>
      <p className="mt-2 text-xs text-faint">
        Figures are computed from the assumptions above — edit and save to see
        them move. Estimates await your judgment.
      </p>
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-faint">{label}</p>
      <p className="font-mono text-sm font-semibold">{value}</p>
    </div>
  );
}
