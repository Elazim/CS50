"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ScrollText, Trash2, UserPlus, Users } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

const ROLES = ["org_admin", "project_lead", "analyst", "viewer"] as const;

export default function OrgSettingsPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = use(params);
  const { data: me } = useMe();
  const myRole = me?.orgs.find((o) => o.id === orgId)?.role;
  const isAdmin = myRole === "org_admin";

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Workspace settings</h1>
        <p className="mt-1 text-sm text-muted">
          Members, roles, and the audit trail. Your role:{" "}
          <Badge tone="accent">{myRole?.replace("_", " ") ?? "…"}</Badge>
        </p>
      </div>
      <Members orgId={orgId} isAdmin={isAdmin} myUserId={me?.id} />
      {isAdmin ? <AuditLog orgId={orgId} /> : null}
    </div>
  );
}

function Members({
  orgId,
  isAdmin,
  myUserId,
}: {
  orgId: string;
  isAdmin: boolean;
  myUserId?: string;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("analyst");

  const { data: members } = useQuery({
    queryKey: ["members", orgId],
    queryFn: async () => {
      const { data, error } = await api.GET("/v1/orgs/{org_id}/members", {
        params: { path: { org_id: orgId } },
      });
      if (error) throw error;
      return data;
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["members", orgId] });

  const invite = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/v1/orgs/{org_id}/members", {
        params: { path: { org_id: orgId } },
        body: {
          email,
          role: role as (typeof ROLES)[number],
          name: null,
        },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      setEmail("");
      invalidate();
      toast("Member added — they sign in with that email");
    },
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const changeRole = useMutation({
    mutationFn: async (vars: { userId: string; role: string }) => {
      const { data, error } = await api.PATCH(
        "/v1/orgs/{org_id}/members/{user_id}",
        {
          params: { path: { org_id: orgId, user_id: vars.userId } },
          body: { role: vars.role as (typeof ROLES)[number] },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: invalidate,
    onError: (error) => toast(errorMessage(error), "error"),
  });

  const remove = useMutation({
    mutationFn: async (userId: string) => {
      const { error } = await api.DELETE("/v1/orgs/{org_id}/members/{user_id}", {
        params: { path: { org_id: orgId, user_id: userId } },
      });
      if (error) throw error;
    },
    onSuccess: invalidate,
    onError: (error) => toast(errorMessage(error), "error"),
  });

  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        <Users size={15} className="text-accent" />
        <h2 className="text-sm font-semibold">Members</h2>
      </div>
      {isAdmin ? (
        <form
          className="mb-4 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            invite.mutate();
          }}
        >
          <div className="min-w-56 flex-1">
            <label className="mb-1 block text-xs text-muted" htmlFor="invite-email">
              Email
            </label>
            <Input
              id="invite-email"
              type="email"
              required
              placeholder="colleague@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted" htmlFor="invite-role">
              Role
            </label>
            <select
              id="invite-role"
              className="h-9 rounded-md border border-border bg-surface px-2 text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={invite.isPending}>
            <UserPlus size={14} /> Add
          </Button>
        </form>
      ) : null}
      <ul className="flex flex-col">
        {(members ?? []).map((member) => (
          <li
            key={member.user_id}
            className="flex flex-wrap items-center gap-2 border-b border-border/60 py-2.5 last:border-b-0"
          >
            <span className="text-sm">{member.email}</span>
            {member.name ? (
              <span className="text-xs text-faint">{member.name}</span>
            ) : null}
            <span className="ml-auto flex items-center gap-2">
              {isAdmin && member.user_id !== myUserId ? (
                <>
                  <select
                    aria-label={`Role for ${member.email}`}
                    className="h-7 rounded-md border border-border bg-surface px-1.5 text-xs"
                    value={member.role}
                    onChange={(e) =>
                      changeRole.mutate({
                        userId: member.user_id,
                        role: e.target.value,
                      })
                    }
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r.replace("_", " ")}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove ${member.email}`}
                    onClick={() => remove.mutate(member.user_id)}
                  >
                    <Trash2 size={13} className="text-danger" />
                  </Button>
                </>
              ) : (
                <Badge tone="neutral">{member.role.replace("_", " ")}</Badge>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AuditLog({ orgId }: { orgId: string }) {
  const { data: events } = useQuery({
    queryKey: ["audit", orgId],
    queryFn: async () => {
      const { data, error } = await api.GET("/v1/orgs/{org_id}/audit", {
        params: { path: { org_id: orgId }, query: { limit: 50 } },
      });
      if (error) throw error;
      return data;
    },
  });

  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        <ScrollText size={15} className="text-accent" />
        <h2 className="text-sm font-semibold">Audit log</h2>
        <span className="text-xs text-faint">append-only, most recent first</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted">
            <th className="pb-2 font-medium">When</th>
            <th className="pb-2 font-medium">Actor</th>
            <th className="pb-2 font-medium">Action</th>
            <th className="pb-2 font-medium">Resource</th>
          </tr>
        </thead>
        <tbody>
          {(events ?? []).map((event) => (
            <tr key={event.id} className="border-b border-border/50">
              <td className="py-2 text-xs text-muted">
                {new Date(event.at).toLocaleString()}
              </td>
              <td className="py-2 text-xs">{event.actor_email ?? "system"}</td>
              <td className="py-2">
                <Badge tone="neutral">{event.action}</Badge>
              </td>
              <td className="py-2 text-xs text-faint">{event.resource_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
