"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
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
  approved: { bg: "#F0FDF4", fg: "#00A844" },
  rejected: { bg: "#FEF2F2", fg: "#DC2626" },
};

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "flagged", label: "Flagged" },
  { value: "rejected", label: "Rejected" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
];

const STAT_CARDS: { value: string; label: string; accent: string }[] = [
  { value: "needs_review", label: "Needs review", accent: "#0F172A" },
  { value: "flagged", label: "Flagged", accent: "#B45309" },
  { value: "pending", label: "Pending", accent: "#2563EB" },
  { value: "approved", label: "Approved", accent: "#00A844" },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

function formatScore(score: number | null): string {
  if (score === null || score === undefined) return "—";
  return `${Math.round(score * 100)}%`;
}

function scoreTone(score: number | null): string {
  if (score === null || score === undefined) return "#9CA3AF";
  if (score >= 0.8) return "#00A844";
  if (score >= 0.5) return "#B45309";
  return "#DC2626";
}

const card: React.CSSProperties = {
  backgroundColor: "#fff",
  border: "1px solid #EEF1F4",
  borderRadius: "16px",
};

export default function AdminKycQueuePage() {
  const adminName = useAuthStore((s) => s.user?.full_name);
  const [items, setItems] = useState<QueueItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("needs_review");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingOnId, setActingOnId] = useState<number | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [counts, setCounts] = useState<Record<string, number | null>>({
    needs_review: null, flagged: null, pending: null, approved: null,
  });

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

  const fetchCounts = useCallback(async () => {
    const entries = await Promise.all(
      STAT_CARDS.map(async ({ value }) => {
        try {
          const res = await api.get("/admin/kyc/queue", { params: { status: value, page_size: 1 } });
          return [value, res.data.total ?? 0] as const;
        } catch {
          return [value, null] as const;
        }
      })
    );
    setCounts(Object.fromEntries(entries));
  }, []);

  // fetchQueue's only setState calls are inside its try/catch/finally, all
  // of which run after `await api.get(...)` has already settled (success
  // or throw) -- no state update here is actually synchronous within this
  // effect's commit. This mirrors dashboard/page.tsx's fetchAll, which the
  // rule doesn't flag; its static analysis appears to key off the presence
  // of an explicit catch block rather than true reachability.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchQueue(); }, [fetchQueue]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchCounts(); }, [fetchCounts]);

  const approve = async (id: number) => {
    setActingOnId(id);
    try {
      await api.patch(`/admin/kyc/${id}/approve`);
      setItems((prev) => prev.filter((i) => i.id !== id));
      fetchCounts();
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
      fetchCounts();
    } catch { setError("Reject failed."); }
    finally { setActingOnId(null); }
  };

  if (forbidden) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#F7F8FA", padding: "20px" }}>
        <div style={{ ...card, padding: "32px", textAlign: "center", maxWidth: "420px", margin: "80px auto" }}>
          <p style={{ fontWeight: "700", color: "#000", marginBottom: "8px" }}>Compliance access required</p>
          <p style={{ color: "#999", fontSize: "13px" }}>Your account needs the compliance_officer or admin role to review KYC submissions.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F7F8FA", padding: "24px 28px 80px" }}>
      {/* Console header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "24px", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <p style={{ color: "#9CA3AF", fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: "4px" }}>Compliance console</p>
          <h1 style={{ fontSize: "22px", fontWeight: "800", color: "#0F172A", margin: 0 }}>KYC review queue</h1>
          <p style={{ color: "#6B7280", fontSize: "13px", marginTop: "4px" }}>Verify submitted identity documents and resolve pending applications.</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", backgroundColor: "#fff", border: "1px solid #EEF1F4", borderRadius: "999px", padding: "6px 14px 6px 6px" }}>
          <div style={{ width: "28px", height: "28px", borderRadius: "50%", backgroundColor: "#0F172A", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", fontWeight: "700" }}>
            {initials(adminName ?? "Admin")}
          </div>
          <span style={{ fontSize: "12px", fontWeight: "700", color: "#0F172A" }}>{adminName ?? "Admin"}</span>
          <span style={{ fontSize: "10px", fontWeight: "700", color: "#00A844", backgroundColor: "#F0FDF4", borderRadius: "999px", padding: "2px 8px" }}>STAFF</span>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px", marginBottom: "24px" }}>
        {STAT_CARDS.map(({ value, label, accent }) => (
          <button
            key={value}
            onClick={() => { setLoading(true); setStatusFilter(value); }}
            style={{
              ...card,
              textAlign: "left",
              padding: "16px 18px",
              cursor: "pointer",
              borderColor: statusFilter === value ? accent : "#EEF1F4",
              boxShadow: statusFilter === value ? `0 0 0 1.5px ${accent}` : "none",
            }}
          >
            <p style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "8px" }}>{label}</p>
            <p style={{ fontSize: "26px", fontWeight: "800", color: accent }}>
              {counts[value] === null ? <span style={{ display: "inline-block", width: "36px", height: "22px", borderRadius: "6px", backgroundColor: "#F3F4F6" }} /> : counts[value]}
            </p>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", overflowX: "auto" }}>
        {STATUS_FILTERS.map((f) => (
          <button key={f.value} onClick={() => { setLoading(true); setStatusFilter(f.value); }}
            style={{ padding: "8px 16px", borderRadius: "999px", border: `1.5px solid ${statusFilter === f.value ? "#0F172A" : "#E5E7EB"}`, backgroundColor: statusFilter === f.value ? "#0F172A" : "#fff", color: statusFilter === f.value ? "#fff" : "#666", fontSize: "13px", fontWeight: "600", cursor: "pointer", whiteSpace: "nowrap" }}>
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {/* Queue table */}
      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "2.2fr 1.2fr 1fr 1fr 1fr 1.6fr", gap: "12px", padding: "12px 20px", borderBottom: "1px solid #EEF1F4", backgroundColor: "#FAFBFC" }}>
          {["Applicant", "Document", "Submitted", "Match", "Liveness", "Status"].map((h) => (
            <p key={h} style={{ fontSize: "11px", fontWeight: "700", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.4px" }}>{h}</p>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: "48px", textAlign: "center" }}><p style={{ color: "#aaa" }}>Loading…</p></div>
        ) : items.length === 0 ? (
          <div style={{ padding: "48px", textAlign: "center" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>Nothing in this queue.</p>
          </div>
        ) : (
          items.map((item) => (
            <div key={item.id} style={{ borderBottom: "1px solid #F3F4F6" }}>
              <div style={{ display: "grid", gridTemplateColumns: "2.2fr 1.2fr 1fr 1fr 1fr 1.6fr", gap: "12px", padding: "14px 20px", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                  <div style={{ width: "34px", height: "34px", borderRadius: "50%", backgroundColor: "#EEF2FF", color: "#3730A3", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "12px", fontWeight: "700", flexShrink: 0 }}>
                    {initials(item.full_name)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <p style={{ fontWeight: "700", color: "#0F172A", fontSize: "13px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.full_name}</p>
                    <p style={{ fontSize: "11px", color: "#9CA3AF" }}>User #{item.user_id}</p>
                  </div>
                </div>
                <p style={{ fontSize: "12px", color: "#4B5563", textTransform: "capitalize" }}>{item.document_type?.replaceAll("_", " ") ?? "—"}</p>
                <p style={{ fontSize: "12px", color: "#4B5563" }}>{new Date(item.created_at).toLocaleDateString()}</p>
                <p style={{ fontSize: "12px", fontWeight: "700", color: scoreTone(item.match_score) }}>{formatScore(item.match_score)}</p>
                <p style={{ fontSize: "12px", fontWeight: "700", color: scoreTone(item.liveness_score) }}>{formatScore(item.liveness_score)}</p>
                <span style={{ fontSize: "11px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: STATUS_BADGE_COLORS[item.status].bg, color: STATUS_BADGE_COLORS[item.status].fg, width: "fit-content" }}>
                  {item.status}
                </span>
              </div>

              <div style={{ padding: "0 20px 20px" }}>
                <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                  <div style={{ display: "flex", gap: "12px" }}>
                    {item.selfie_presigned_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.selfie_presigned_url} alt="Selfie" style={{ width: "110px", height: "140px", objectFit: "cover", borderRadius: "12px", border: "1px solid #E5E7EB" }} />
                    ) : (
                      <div style={{ width: "110px", height: "140px", borderRadius: "12px", border: "1px dashed #E5E7EB", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", color: "#9CA3AF", textAlign: "center", padding: "8px" }}>No selfie</div>
                    )}
                    {item.id_photo_presigned_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.id_photo_presigned_url} alt="ID document" style={{ width: "180px", height: "140px", objectFit: "cover", borderRadius: "12px", border: "1px solid #E5E7EB" }} />
                    ) : (
                      <div style={{ width: "180px", height: "140px", borderRadius: "12px", border: "1px dashed #E5E7EB", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", color: "#9CA3AF" }}>No ID document</div>
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: "220px" }}>
                    <p style={{ fontSize: "12px", color: "#6B7280", lineHeight: 1.8 }}>
                      <strong style={{ color: "#0F172A" }}>Submitted:</strong> {new Date(item.created_at).toLocaleString()}<br />
                      {item.reviewed_at && <>
                        <strong style={{ color: "#0F172A" }}>Reviewed:</strong> {new Date(item.reviewed_at).toLocaleString()}<br />
                      </>}
                      {item.rejection_reason && <>
                        <strong style={{ color: "#0F172A" }}>Reason:</strong> {item.rejection_reason}
                      </>}
                    </p>
                    <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
                      <button onClick={() => reject(item.id)} disabled={actingOnId === item.id}
                        style={{ padding: "10px 18px", borderRadius: "12px", border: "1.5px solid #FECACA", backgroundColor: "#fff", color: "#DC2626", fontSize: "13px", fontWeight: "700", cursor: actingOnId === item.id ? "not-allowed" : "pointer" }}>
                        Reject
                      </button>
                      <button onClick={() => approve(item.id)} disabled={actingOnId === item.id}
                        style={{ padding: "10px 18px", borderRadius: "12px", border: "none", backgroundColor: "#00A844", color: "#fff", fontSize: "13px", fontWeight: "700", cursor: actingOnId === item.id ? "not-allowed" : "pointer" }}>
                        {actingOnId === item.id ? "Working…" : "Approve"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
