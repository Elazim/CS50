"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, Settings } from "lucide-react";
import { useMe, useSignOut } from "@/lib/auth";
import { Button } from "@/components/ui/button";

export default function OrgLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = use(params);
  const router = useRouter();
  const { data: me, isLoading } = useMe();
  const signOut = useSignOut();

  useEffect(() => {
    if (!isLoading && !me) router.replace("/sign-in");
  }, [me, isLoading, router]);

  if (isLoading || !me) {
    return (
      <div className="flex h-screen items-center justify-center text-muted">
        Loading…
      </div>
    );
  }

  const org = me.orgs.find((o) => o.id === orgId);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-3">
          <Link href={`/o/${orgId}`} className="text-sm font-semibold">
            AI Transformation Copilot
          </Link>
          <span className="text-faint">/</span>
          <span className="text-sm text-muted">{org?.name ?? "Workspace"}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-faint">{me.email}</span>
          <Link href={`/o/${orgId}/settings`} aria-label="Workspace settings">
            <Button variant="ghost" size="sm">
              <Settings size={14} />
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={signOut} aria-label="Sign out">
            <LogOut size={14} />
          </Button>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
