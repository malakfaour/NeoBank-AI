"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export default function DashboardAuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    async function validate() {
      try {
        const destination = await getPostAuthDestination();
        if (!active) return;
        if (destination !== pathname) return router.replace(destination);
        setReady(true);
      } catch {
        if (active) router.replace("/login");
      }
    }
    void validate();
    return () => { active = false; };
  }, [router, pathname]);

  return ready ? children : <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>Checking your secure session…</main>;
}
