"use client";

import { use } from "react";
import { CalendarRange, Link2, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import {
  money,
  useOpportunityMutations,
  useRoadmap,
  type RoadmapItem,
} from "@/lib/opportunities";

const HORIZONS: { key: "30" | "90" | "180" | "365"; label: string }[] = [
  { key: "30", label: "First 30 days" },
  { key: "90", label: "90 days" },
  { key: "180", label: "6 months" },
  { key: "365", label: "12 months" },
];

export default function RoadmapPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const { data: roadmap, isLoading } = useRoadmap(orgId, projectId);
  const { buildRoadmap } = useOpportunityMutations(orgId, projectId);

  const isEmpty =
    !roadmap ||
    HORIZONS.every((horizon) => (roadmap.horizons[horizon.key] ?? []).length === 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">
          Horizons follow the scoring rules: quick wins first, dependencies
          sequenced (integration before the automation that relies on it).
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => buildRoadmap.mutate()}
          disabled={buildRoadmap.isPending}
        >
          <CalendarRange size={13} />
          {buildRoadmap.isPending ? "Sequencing…" : "Generate roadmap"}
        </Button>
      </div>

      {isLoading ? (
        <p className="text-muted">Loading roadmap…</p>
      ) : isEmpty ? (
        <EmptyState
          title="No roadmap yet"
          description="Generate opportunities from the knowledge model, then sequence them here."
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-4">
          {HORIZONS.map((horizon) => (
            <div key={horizon.key} className="flex flex-col gap-2">
              <h3 className="border-b border-border pb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
                {horizon.label}
              </h3>
              {(roadmap!.horizons[horizon.key] ?? []).map((item) => (
                <RoadmapCard key={item.id} item={item} />
              ))}
              {(roadmap!.horizons[horizon.key] ?? []).length === 0 ? (
                <p className="text-xs text-faint">—</p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RoadmapCard({ item }: { item: RoadmapItem }) {
  const opportunity = item.opportunity;
  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <p className="text-sm font-medium leading-snug">
        {opportunity?.title ?? "Opportunity"}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {item.quick_win ? (
          <Badge tone="success">
            <Zap size={10} /> quick win
          </Badge>
        ) : null}
        {opportunity ? (
          <Badge tone="neutral">
            i{opportunity.impact_score}/c{opportunity.complexity_score}/r
            {opportunity.risk_score}
          </Badge>
        ) : null}
        {item.depends_on.length > 0 ? (
          <Badge tone="info">
            <Link2 size={10} /> after prerequisite
          </Badge>
        ) : null}
      </div>
      {opportunity?.roi?.computed?.net_annual_savings != null ? (
        <p className="mt-1.5 text-xs text-muted">
          Net annual{" "}
          <span className="font-mono text-foreground">
            {money(opportunity.roi.computed.net_annual_savings as number)}
          </span>
        </p>
      ) : null}
    </div>
  );
}
