"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import type { components } from "@atc/client";

export type Opportunity = components["schemas"]["OpportunityOut"];
export type Roadmap = components["schemas"]["RoadmapOut"];
export type RoadmapItem = components["schemas"]["RoadmapItemOut"];

export function useOpportunities(orgId: string, projectId: string) {
  return useQuery({
    queryKey: ["opportunities", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/opportunities",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}

export function useRoadmap(orgId: string, projectId: string) {
  return useQuery({
    queryKey: ["roadmap", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/roadmap",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}

export function useOpportunityMutations(orgId: string, projectId: string) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["opportunities", orgId, projectId] });
    queryClient.invalidateQueries({ queryKey: ["roadmap", orgId, projectId] });
  };

  const generate = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/projects/{project_id}/opportunities/generate",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      toast("Opportunity generation started");
      let polls = 0;
      const timer = setInterval(() => {
        invalidate();
        if (++polls >= 8) clearInterval(timer);
      }, 1500);
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const review = useMutation({
    mutationFn: async (vars: { opportunityId: string; action: string }) => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/opportunities/{opportunity_id}/review",
        {
          params: {
            path: { org_id: orgId, opportunity_id: vars.opportunityId },
          },
          body: { action: vars.action, edits: null },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: invalidate,
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const patchRoi = useMutation({
    mutationFn: async (vars: {
      opportunityId: string;
      assumptions: { key: string; value: number }[];
    }) => {
      const { data, error } = await api.PATCH(
        "/v1/orgs/{org_id}/opportunities/{opportunity_id}/roi",
        {
          params: {
            path: { org_id: orgId, opportunity_id: vars.opportunityId },
          },
          body: { assumptions: vars.assumptions },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      invalidate();
      toast("Assumptions saved — figures recomputed");
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const buildRoadmap = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/v1/orgs/{org_id}/projects/{project_id}/roadmap/generate",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: invalidate,
    onError: (error) => toast(errorMessage(error), "error"),
  });

  return { generate, review, patchRoi, buildRoadmap };
}

export function money(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}
