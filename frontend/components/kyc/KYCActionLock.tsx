"use client";

import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

export default function KYCActionLock({ action }: { action: string }) {
  const router = useRouter();
  const status = useAuthStore((state) => state.user?.kyc_status);
  const workflow = useAuthStore((state) => state.user?.kyc_onboarding_state);
  const message = workflow === "pending"
    ? "Your identity verification is under review. Transfers, Currency Exchange, and Top Ups will be available after approval."
    : status === "rejected" || workflow === "rejected"
      ? "Your identity verification needs attention. Review and update the required information."
      : "Complete your profile and identity verification to unlock Transfers, Currency Exchange, and Top Ups.";

  return (
    <main style={{ minHeight: "70vh", display: "grid", placeItems: "center", padding: 20 }}>
      <section style={{ maxWidth: 480, padding: 28, borderRadius: 24, background: "#fff", textAlign: "center", border: "1px solid #E5E7EB" }}>
        <div style={{ fontSize: 42 }}>🔒</div>
        <h2 style={{ margin: "10px 0" }}>{action} is locked</h2>
        <p style={{ color: "#666", lineHeight: 1.6 }}>{message}</p>
        <button onClick={() => router.push("/kyc")} style={{ marginTop: 18, width: "100%", padding: 13, border: 0, borderRadius: 12, background: "#00C853", color: "#fff", fontWeight: 700, cursor: "pointer" }}>
          {status === "rejected" ? "Review verification" : "Complete Profile"}
        </button>
      </section>
    </main>
  );
}
