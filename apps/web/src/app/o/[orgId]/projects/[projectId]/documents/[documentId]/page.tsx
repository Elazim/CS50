"use client";

import { use, useEffect, useRef } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { components } from "@atc/client";

type Element = components["schemas"]["ElementOut"];

export default function DocumentViewerPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; documentId: string }>;
}) {
  const { orgId, projectId, documentId } = use(params);

  const { data, isLoading } = useQuery({
    queryKey: ["document", orgId, documentId],
    queryFn: async () => {
      const { data, error } = await api.GET("/v1/orgs/{org_id}/documents/{document_id}", {
        params: {
          path: { org_id: orgId, document_id: documentId },
          query: { limit: 1000 },
        },
      });
      if (error) throw error;
      return data;
    },
  });

  // Deep-link highlight: /documents/{id}#el-{elementId} (citation chips).
  const highlighted = useRef<string | null>(null);
  useEffect(() => {
    if (!data || typeof window === "undefined") return;
    const hash = window.location.hash;
    if (hash.startsWith("#el-")) {
      highlighted.current = hash.slice(4);
      document.getElementById(hash.slice(1))?.scrollIntoView({ block: "center" });
    }
  }, [data]);

  if (isLoading || !data) {
    return <p className="text-muted">Loading document…</p>;
  }

  const piiCounts = data.pii_summary?.counts as Record<string, number> | undefined;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href={`/o/${orgId}/projects/${projectId}/documents`}
          className="mb-3 inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
        >
          <ArrowLeft size={12} /> All documents
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold tracking-tight">
            {data.document.filename}
          </h2>
          {data.doc_class ? <Badge tone="accent">{data.doc_class}</Badge> : null}
          <Badge tone={data.document.status === "ready" ? "success" : "warning"}>
            {data.document.status}
          </Badge>
          {piiCounts && Object.keys(piiCounts).length > 0 ? (
            <Badge tone="warning">
              <ShieldAlert size={11} />
              PII: {Object.entries(piiCounts)
                .map(([type, count]) => `${count} ${type}`)
                .join(", ")}
            </Badge>
          ) : null}
          <span className="ml-auto font-mono text-xs text-faint">
            {data.element_count} elements
          </span>
        </div>
      </div>

      <article className="rounded-md border border-border bg-surface px-6 py-5">
        {data.elements.map((element) => (
          <ElementView
            key={element.id}
            element={element}
            highlighted={highlighted.current === element.id}
          />
        ))}
      </article>
    </div>
  );
}

function ElementView({
  element,
  highlighted,
}: {
  element: Element;
  highlighted: boolean;
}) {
  const base = cn(
    "scroll-mt-24 rounded px-2 py-1 -mx-2",
    highlighted && "bg-ai-tint ring-1 ring-accent",
  );

  if (element.kind === "heading") {
    const depth = element.section_path.length;
    return (
      <h3
        id={`el-${element.id}`}
        className={cn(
          base,
          "mt-5 mb-2 font-semibold tracking-tight first:mt-0",
          depth <= 1 ? "text-base" : "text-sm",
        )}
      >
        {element.text}
      </h3>
    );
  }

  if (element.kind === "table" && element.table_json) {
    const rows = (element.table_json as { rows: string[][] }).rows ?? [];
    return (
      <div id={`el-${element.id}`} className={cn(base, "my-3 overflow-x-auto")}>
        <table className="w-full border-collapse text-xs">
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={i === 0 ? "bg-surface-raised font-medium" : ""}>
                {row.map((cell, j) => (
                  <td key={j} className="border border-border px-2 py-1.5 align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (element.kind === "list_item") {
    return (
      <p id={`el-${element.id}`} className={cn(base, "my-0.5 pl-4 text-sm leading-relaxed")}>
        <span className="mr-2 text-faint">•</span>
        {element.text}
      </p>
    );
  }

  return (
    <p
      id={`el-${element.id}`}
      className={cn(
        base,
        "my-2 text-sm leading-relaxed",
        element.kind === "note" && "border-l-2 border-border pl-3 text-muted italic",
      )}
    >
      {element.text}
      {element.pii_types.length > 0 ? (
        <span className="ml-2 align-middle">
          <Badge tone="warning">PII: {element.pii_types.join(", ")}</Badge>
        </span>
      ) : null}
    </p>
  );
}
