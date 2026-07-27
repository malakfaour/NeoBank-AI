"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getStartupDestination } from "@/lib/startupSession";

const STARTUP_PATHS = new Set(["/", "/login"]);

export default function StartupSessionGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [checkedPath, setCheckedPath] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!STARTUP_PATHS.has(pathname)) {
      return;
    }
    void getStartupDestination(localStorage).then((destination) => {
      if (!active) return;
      if (destination !== pathname) {
        router.replace(destination);
        return;
      }
      setCheckedPath(pathname);
    });
    return () => { active = false; };
  }, [pathname, router]);

  if (STARTUP_PATHS.has(pathname) && checkedPath !== pathname) {
    return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#F5F5F5", color: "#555" }}>Restoring your secure session…</main>;
  }
  return children;
}
