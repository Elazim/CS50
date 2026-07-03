"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

export default function ProjectsPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = use(params);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects", orgId],
    queryFn: async () => {
      const { data, error } = await api.GET("/v1/orgs/{org_id}/projects", {
        params: { path: { org_id: orgId } },
      });
      if (error) throw error;
      return data;
    },
  });

  const createProject = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/v1/orgs/{org_id}/projects", {
        params: { path: { org_id: orgId } },
        body: { name, industry_pack: "insurance-claims" },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      setName("");
      setCreating(false);
      queryClient.invalidateQueries({ queryKey: ["projects", orgId] });
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted">
            Each project is an engagement: its documents, knowledge model, and
            deliverables.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={15} /> New project
        </Button>
      </div>

      {creating ? (
        <Card className="mb-6">
          <form
            className="flex items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              createProject.mutate();
            }}
          >
            <div className="flex-1">
              <label className="mb-1.5 block text-xs font-medium text-muted">
                Project name
              </label>
              <Input
                autoFocus
                required
                placeholder="e.g. Claims Intake Assessment"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={createProject.isPending}>
              Create
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreating(false)}
            >
              Cancel
            </Button>
          </form>
        </Card>
      ) : null}

      {isLoading ? (
        <p className="text-muted">Loading projects…</p>
      ) : projects && projects.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {projects.map((project) => (
            <li key={project.id}>
              <Link
                href={`/o/${orgId}/projects/${project.id}`}
                className="flex items-center gap-3 rounded-md border border-border bg-surface px-4 py-3 transition-colors hover:border-border-strong hover:bg-surface-raised"
              >
                <FolderKanban size={16} className="text-accent" />
                <div className="flex-1">
                  <p className="font-medium">{project.name}</p>
                  <p className="text-xs text-faint">
                    {project.industry_pack} · created{" "}
                    {new Date(project.created_at).toLocaleDateString()}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="No projects yet"
          description="Create a project, then upload its SOPs, process docs, and policies to start building the knowledge model."
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} /> New project
            </Button>
          }
        />
      )}
    </div>
  );
}
