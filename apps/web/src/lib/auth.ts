"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, type Me } from "@/lib/api";

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      const { data, response } = await api.GET("/v1/auth/me");
      if (response.status === 401) return null;
      return data ?? null;
    },
  });
}

export function useSignOut() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return async () => {
    await api.POST("/v1/auth/logout");
    queryClient.clear();
    router.push("/sign-in");
  };
}
