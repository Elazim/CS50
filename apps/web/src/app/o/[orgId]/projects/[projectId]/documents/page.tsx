"use client";

import { use, useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, UploadCloud } from "lucide-react";
import { api, errorMessage, type DocumentItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";

const STATUS_TONE: Record<
  DocumentItem["status"],
  "neutral" | "success" | "warning" | "danger" | "info"
> = {
  pending_upload: "neutral",
  uploaded: "info",
  processing: "warning",
  ready: "success",
  failed: "danger",
};

export default function DocumentsPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = use(params);
  const queryClient = useQueryClient();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(0);

  const { data: documents } = useQuery({
    queryKey: ["documents", orgId, projectId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/v1/orgs/{org_id}/projects/{project_id}/documents",
        { params: { path: { org_id: orgId, project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
    // Poll while any pipeline is in flight so statuses land without a reload.
    refetchInterval: (query) =>
      query.state.data?.some((d) =>
        ["processing", "uploaded", "pending_upload"].includes(d.status),
      )
        ? 1500
        : false,
  });

  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        setUploading((n) => n + 1);
        try {
          const { data, error } = await api.POST(
            "/v1/orgs/{org_id}/projects/{project_id}/documents",
            {
              params: { path: { org_id: orgId, project_id: projectId } },
              body: {
                filename: file.name,
                mime: file.type || "application/octet-stream",
                size_bytes: file.size,
              },
            },
          );
          if (error || !data) throw new Error(errorMessage(error));

          // Browser PUTs straight to object storage; bytes never pass
          // through the API (docs/02).
          const put = await fetch(data.upload_url, {
            method: "PUT",
            headers: {
              "Content-Type": file.type || "application/octet-stream",
            },
            body: file,
          });
          if (!put.ok) throw new Error(`Storage upload failed (${put.status})`);

          const completed = await api.POST(
            "/v1/orgs/{org_id}/documents/{document_id}/complete",
            {
              params: {
                path: { org_id: orgId, document_id: data.document.id },
              },
            },
          );
          if (completed.error) throw new Error(errorMessage(completed.error));
        } catch (err) {
          toast(err instanceof Error ? err.message : "Upload failed", "error");
        } finally {
          setUploading((n) => n - 1);
          queryClient.invalidateQueries({
            queryKey: ["documents", orgId, projectId],
          });
        }
      }
    },
    [orgId, projectId, queryClient, toast],
  );

  return (
    <div className="flex flex-col gap-6">
      <button
        type="button"
        aria-label="Upload documents"
        className={cn(
          "flex w-full flex-col items-center gap-2 rounded-md border border-dashed py-10 transition-colors",
          dragging
            ? "border-accent bg-ai-tint"
            : "border-border hover:border-border-strong",
        )}
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          uploadFiles(e.dataTransfer.files);
        }}
      >
        <UploadCloud size={22} className="text-muted" />
        <p className="text-sm font-medium">
          {uploading > 0
            ? `Uploading ${uploading} file${uploading > 1 ? "s" : ""}…`
            : "Drop documents here or click to browse"}
        </p>
        <p className="text-xs text-faint">
          SOPs, process maps, policies, meeting notes — PDF, Word, Excel,
          PowerPoint
        </p>
        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </button>

      {documents && documents.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th className="pb-2 font-medium">Name</th>
              <th className="pb-2 font-medium">Size</th>
              <th className="pb-2 font-medium">Uploaded</th>
              <th className="pb-2 text-right font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id} className="border-b border-border/50">
                <td className="py-2.5">
                  <span className="flex items-center gap-2">
                    <FileText size={14} className="shrink-0 text-muted" />
                    {doc.filename}
                  </span>
                </td>
                <td className="py-2.5 font-mono text-xs text-muted">
                  {formatBytes(doc.size_bytes)}
                </td>
                <td className="py-2.5 text-xs text-muted">
                  {new Date(doc.created_at).toLocaleString()}
                </td>
                <td className="py-2.5 text-right">
                  <Badge tone={STATUS_TONE[doc.status]}>
                    {doc.status.replace("_", " ")}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState
          title="No documents yet"
          description="Everything the platform knows starts here. Upload the process documentation for this engagement."
        />
      )}
    </div>
  );
}

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}
