"use client";

import { use, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { CitationChip } from "@/components/citation-chip";

export default function SearchPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const toast = useToast();
  const [query, setQuery] = useState("");

  const search = useMutation({
    mutationFn: async (q: string) => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/projects/{project_id}/search",
        {
          params: { path: { org_id: orgId, project_id: projectId } },
          body: { query: q, top_k: 8 },
        },
      );
      if (error) throw error;
      return data;
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const results = search.data;

  return (
    <div className="flex flex-col gap-5">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim().length >= 2) search.mutate(query.trim());
        }}
      >
        <Input
          autoFocus
          placeholder='Ask the project corpus — e.g. "how are claims assigned to adjusters"'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search query"
        />
        <Button type="submit" disabled={search.isPending}>
          <Search size={15} />
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>

      {results === undefined ? (
        <EmptyState
          title="Semantic search over everything uploaded"
          description="Hybrid retrieval: meaning and exact wording both count. Every hit cites its source passage."
        />
      ) : results.length === 0 ? (
        <EmptyState
          title="No matches"
          description="Try different wording, or check that documents have finished processing."
        />
      ) : (
        <ol className="flex flex-col gap-3">
          {results.map((hit) => (
            <li
              key={hit.chunk_id}
              className="rounded-md border border-border bg-surface p-4"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <CitationChip
                  href={`/o/${orgId}/projects/${projectId}/documents/${hit.document_id}${
                    hit.element_ids[0] ? `#el-${hit.element_ids[0]}` : ""
                  }`}
                  filename={hit.filename}
                  detail={
                    hit.section_path.length
                      ? hit.section_path.join(" › ")
                      : hit.pages.length
                        ? `p. ${hit.pages.join(", ")}`
                        : undefined
                  }
                />
                {hit.doc_class ? <Badge tone="accent">{hit.doc_class}</Badge> : null}
                <span className="ml-auto font-mono text-xs text-faint">
                  {hit.score.toFixed(4)}
                </span>
              </div>
              <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90">
                {hit.text.length > 700 ? `${hit.text.slice(0, 700)}…` : hit.text}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
