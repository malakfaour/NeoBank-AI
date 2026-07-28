"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

type KYCRecordStatus = "pending" | "approved" | "flagged" | "rejected";

interface QueueItem {
  id: number;
  user_id: number;
  full_name: string;
  status: KYCRecordStatus;
  created_at: string;
  match_score: number | null;
  liveness_score: number | null;
  rejection_reason: string | null;
  reviewed_at: string | null;
  reviewed_by: number | null;
  selfie_presigned_url: string | null;
  id_photo_presigned_url: string | null;
  document_type: string | null;
}

const STATUS_BADGE_COLORS: Record<KYCRecordStatus, { bg: string; fg: string }> = {
  pending: { bg: "#FFFBEB", fg: "#B45309" },
  flagged: { bg: "#FFFBEB", fg: "#B45309" },
  approved: { bg: "#F0FDF4", fg: "#00C853" },
  rejected: { bg: "#FEF2F2", fg: "#DC2626" },
};

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "flagged", label: "Flagged" },
  { value: "rejected", label: "Rejected" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
];

export default function AdminKycQueuePage() {
  const router = useRouter();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("needs_review");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingOnId, setActingOnId] = useState<number | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const fetchQueue = useCallback(async () => {
    try {
      const res = await api.get("/admin/kyc/queue", { params: { status: statusFilter } });
      setItems(res.data.items ?? []);
      setError("");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError("Failed to load KYC queue.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  // fetchQueue's only setState calls are inside its try/catch/finally, all
  // of which run after `await api.get(...)` has already settled (success
  // or throw) -- no state update here is actually synchronous within this
  // effect's commit. This mirrors dashboard/page.tsx's fetchAll, which the
  // rule doesn't flag; its static analysis appears to key off the presence
  // of an explicit catch block rather than true reachability.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const approve = async (id: number) => {
    setActingOnId(id);
    try {
      await api.patch(`/admin/kyc/${id}/approve`);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch { setError("Approve failed."); }
    finally { setActingOnId(null); }
  };

  const reject = async (id: number) => {
    const reason = window.prompt("Rejection reason:");
    if (!reason) return;
    setActingOnId(id);
    try {
      await api.patch(`/admin/kyc/${id}/reject`, { rejection_reason: reason });
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch { setError("Reject failed."); }
    finally { setActingOnId(null); }
  };

  if (forbidden) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center", maxWidth: "420px", margin: "80px auto" }}>
          <p style={{ fontWeight: "700", color: "#000", marginBottom: "8px" }}>Compliance access required</p>
          <p style={{ color: "#999", fontSize: "13px" }}>Your account needs the compliance_officer or admin role to review KYC submissions.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
        <button onClick={() => router.back()}
          style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>KYC review queue</h2>
      </div>

      <div style={{ display: "flex", gap: "8px", marginBottom: "20px", overflowX: "auto" }}>
        {STATUS_FILTERS.map((f) => (
          <button key={f.value} onClick={() => { setLoading(true); setStatusFilter(f.value); }}
            style={{ padding: "8px 16px", borderRadius: "999px", border: `1.5px solid ${statusFilter === f.value ? "#00C853" : "#E5E7EB"}`, backgroundColor: statusFilter === f.value ? "#F0FDF4" : "#fff", color: statusFilter === f.value ? "#00C853" : "#666", fontSize: "13px", fontWeight: "600", cursor: "pointer", whiteSpace: "nowrap" }}>
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: "32px", textAlign: "center" }}><p style={{ color: "#aaa" }}>Loading...</p></div>
      ) : items.length === 0 ? (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center" }}>
          <p style={{ color: "#aaa", fontSize: "14px" }}>Nothing in this queue.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {items.map((item) => (
            <div key={item.id} style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                <div>
                  <p style={{ fontWeight: "700", color: "#000" }}>{item.full_name}</p>
                  <p style={{ fontSize: "12px", color: "#999" }}>User #{item.user_id} &middot; {item.document_type ?? "unknown document"}</p>
                </div>
                <span style={{ fontSize: "12px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: STATUS_BADGE_COLORS[item.status].bg, color: STATUS_BADGE_COLORS[item.status].fg }}>
                  {item.status}
                </span>
              </div>

              <div style={{ display: "flex", gap: "12px", marginBottom: "12px" }}>
                {item.selfie_presigned_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.selfie_presigned_url} alt="Selfie" style={{ width: "100px", height: "130px", objectFit: "cover", borderRadius: "12px" }} />
                )}
                {item.id_photo_presigned_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.id_photo_presigned_url} alt="ID document" style={{ width: "160px", height: "130px", objectFit: "cover", borderRadius: "12px" }} />
                )}
              </div>

              <div style={{ fontSize: "13px", color: "#666", marginBottom: "16px", lineHeight: 1.7 }}>
                <div>Submitted: {new Date(item.created_at).toLocaleString()}</div>
                {item.rejection_reason && <div>Reason: {item.rejection_reason}</div>}
              </div>

              <div style={{ display: "flex", gap: "12px" }}>
                <button onClick={() => reject(item.id)} disabled={actingOnId === item.id}
                  style={{ flex: 1, padding: "12px", borderRadius: "14px", border: "1.5px solid #FECACA", backgroundColor: "#fff", color: "#DC2626", fontSize: "14px", fontWeight: "700", cursor: actingOnId === item.id ? "not-allowed" : "pointer" }}>
                  Reject
                </button>
                <button onClick={() => approve(item.id)} disabled={actingOnId === item.id}
                  style={{ flex: 1, padding: "12px", borderRadius: "14px", border: "none", backgroundColor: "#00C853", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: actingOnId === item.id ? "not-allowed" : "pointer" }}>
                  {actingOnId === item.id ? "Working..." : "Approve"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
