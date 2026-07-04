"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import type { components } from "@atc/client";

export type Entity = components["schemas"]["EntityOut"];
export type ReviewItemView = components["schemas"]["ReviewItemOut"];
export type ProcessGraph = components["schemas"]["ProcessGraphOut"];

export function useEntities(orgId: string, projectId: string, type?: string) {
  return useQuery({
    queryKey: ["entities", orgId, projectId, type ?? "all"],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/entities",
        {
          params: {
            path: { org_id: orgId, project_id: projectId },
            query: type ? { type, limit: 500 } : { limit: 500 },
          },
        },
      );
      if (error) throw error;
      return data;
    },
  });
}

export function useKnowledgeSummary(orgId: string, projectId: string) {
  return useQuery({
    queryKey: ["knowledge-summary", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/knowledge/summary",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}

export function useReviewItems(orgId: string, projectId: string) {
  return useQuery({
    queryKey: ["review-items", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/review-items",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}

export function useKnowledgeMutations(orgId: string, projectId: string) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["entities", orgId, projectId] });
    queryClient.invalidateQueries({ queryKey: ["review-items", orgId, projectId] });
    queryClient.invalidateQueries({ queryKey: ["knowledge-summary", orgId, projectId] });
  };

  const reviewEntity = useMutation({
    mutationFn: async (vars: {
      entityId: string;
      action: string;
      edits?: Record<string, unknown>;
    }) => {
      const { data, error } = await api.POST("/v1/orgs/{org_id}/entities/{entity_id}/review", {
        params: { path: { org_id: orgId, entity_id: vars.entityId } },
        body: { action: vars.action, edits: vars.edits ?? null },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: invalidate,
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const resolveItem = useMutation({
    mutationFn: async (vars: { itemId: string; action: string }) => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/review-items/{item_id}/resolve",
        {
          params: { path: { org_id: orgId, item_id: vars.itemId } },
          body: { action: vars.action },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: invalidate,
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const extract = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/projects/{project_id}/knowledge/extract",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      toast("Extraction started — the model refreshes when it finishes");
      // Poll the summary a few times while the pipeline runs.
      let polls = 0;
      const timer = setInterval(() => {
        invalidate();
        if (++polls >= 10) clearInterval(timer);
      }, 1500);
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  return { reviewEntity, resolveItem, extract };
}
