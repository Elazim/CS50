"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { api, API_URL, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

const DEV_AUTH =
  (process.env.NEXT_PUBLIC_AUTH_MODE ?? "dev") === "dev";

export default function SignInPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function devSignIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { data, error } = await api.POST("/v1/auth/dev-login", {
      body: { email, name: name || null },
    });
    setBusy(false);
    if (error || !data) {
      toast(errorMessage(error), "error");
      return;
    }
    queryClient.setQueryData(["me"], data);
    router.push(`/o/${data.orgs[0].id}`);
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-lg font-semibold tracking-tight">
            AI Transformation Copilot
          </h1>
          <p className="mt-1 text-sm text-muted">
            Evidence-linked process intelligence
          </p>
        </div>
        <Card>
          {DEV_AUTH ? (
            <form onSubmit={devSignIn} className="flex flex-col gap-3">
              <label className="text-xs font-medium text-muted" htmlFor="email">
                Email
              </label>
              <Input
                id="email"
                type="email"
                required
                autoFocus
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <label className="text-xs font-medium text-muted" htmlFor="name">
                Name (optional)
              </label>
              <Input
                id="name"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Button type="submit" disabled={busy} className="mt-2">
                {busy ? "Signing in…" : "Continue"}
              </Button>
              <p className="text-center text-xs text-faint">
                Development sign-in — no password required
              </p>
            </form>
          ) : (
            <Button
              className="w-full"
              onClick={() => {
                window.location.href = `${API_URL}/v1/auth/workos/login`;
              }}
            >
              Continue with SSO
            </Button>
          )}
        </Card>
      </div>
    </main>
  );
}
