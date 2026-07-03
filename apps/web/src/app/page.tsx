"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMe } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const { data: me, isLoading } = useMe();

  useEffect(() => {
    if (isLoading) return;
    if (me && me.orgs.length > 0) {
      router.replace(`/o/${me.orgs[0].id}`);
    } else {
      router.replace("/sign-in");
    }
  }, [me, isLoading, router]);

  return (
    <div className="flex h-screen items-center justify-center text-muted">
      Loading…
    </div>
  );
}
