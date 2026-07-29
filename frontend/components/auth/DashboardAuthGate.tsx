"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

// Groups every route this gate can resolve to into a "section" so a resolved
// destination of e.g. "/admin/kyc" doesn't bounce the user off "/admin/users" -
// any page within the same section as the resolved destination is allowed.
function sectionOf(path: string): string {
  if (path.startsWith("/admin")) return "/admin";
  if (path === "/kyc") return "/kyc";
  return "/dashboard";
}

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
        if (sectionOf(destination) !== sectionOf(pathname)) return router.replace(destination);
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
