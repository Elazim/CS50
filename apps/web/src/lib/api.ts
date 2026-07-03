import createClient from "openapi-fetch";
import type { paths, components } from "@atc/client";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({
  baseUrl: API_URL,
  credentials: "include",
});

export type Me = components["schemas"]["MeResponse"];
export type OrgSummary = components["schemas"]["OrgSummary"];
export type Project = components["schemas"]["ProjectOut"];
export type DocumentItem = components["schemas"]["DocumentListItem"];
export type PipelineRun = components["schemas"]["RunOut"];

export function errorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    typeof (error as { error: { message?: string } }).error?.message === "string"
  ) {
    return (error as { error: { message: string } }).error.message;
  }
  return "Something went wrong";
}
