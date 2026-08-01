"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AuthCard from "@/components/auth/AuthCard";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export default function KycStatusPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let active = true;
    async function check() {
      setChecking(true);
      const destination = await getPostAuthDestination();
      if (!active) return;
      setChecking(false);
      if (destination !== "/kyc/status") router.replace(destination);
    }
    void check();
    const timer = window.setInterval(check, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [router]);

  return (
    <AuthCard title="Verification pending" subtitle="We’re reviewing your identity documents.">
      <div style={{ textAlign: "center" }}>
        <div aria-hidden="true" style={{ width: 64, height: 64, borderRadius: "50%", background: "#FFFBEB", display: "grid", placeItems: "center", margin: "0 auto 16px", fontSize: 28 }}>⏳</div>
        <p style={{ color: "#666", lineHeight: 1.6 }}>You can close NeoBank safely. We’ll keep your application secure while the review is completed.</p>
        <button type="button" disabled={checking} onClick={() => void getPostAuthDestination().then((destination) => router.replace(destination))} style={{ border: 0, borderRadius: 14, padding: "12px 18px", background: "#00C853", color: "#fff", fontWeight: 700 }}>
          {checking ? "Checking…" : "Check status"}
        </button>
      </div>
    </AuthCard>
  );
}
