"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface FlaggedTransactionItem {
  id: number;
  sender_id: number;
  sender_name: string;
  sender_email: string;
  amount: string;
  currency: string;
  fraud_score: number | null;
  scoring_model: string | null;
  status: string;
  created_at: string;
}

export default function AdminFlaggedTransactionsPage() {
  const router = useRouter();
  const [items, setItems] = useState<FlaggedTransactionItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingOnId, setActingOnId] = useState<number | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const fetchQueue = useCallback(async () => {
    try {
      const res = await api.get("/admin/flagged-transactions", { params: { page, page_size: 20 } });
      setItems(res.data.items ?? []);
      setTotalPages(res.data.total_pages ?? 1);
      setError("");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError("Failed to load the flagged transactions queue.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  // Same pattern as admin/kyc/page.tsx's fetchQueue -- see that file's
  // comment for why this suppression is needed.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const resolve = async (id: number, resolution: "legitimate" | "confirmed_fraud") => {
    if (resolution === "confirmed_fraud") {
      const confirmed = window.confirm(
        "This will reverse the transaction and credit the sender's wallet back. This cannot be undone. Continue?"
      );
      if (!confirmed) return;
    }
    setActingOnId(id);
    try {
      await api.post(`/admin/transactions/${id}/resolve-flag`, { resolution });
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Resolving this flag failed.");
    } finally {
      setActingOnId(null);
    }
  };

  if (forbidden) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center", maxWidth: "420px", margin: "80px auto" }}>
          <p style={{ fontWeight: "700", color: "#000", marginBottom: "8px" }}>Compliance access required</p>
          <p style={{ color: "#999", fontSize: "13px" }}>Your account needs the compliance_officer or admin role to review flagged transactions.</p>
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
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>Flagged transactions</h2>
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
          <p style={{ color: "#aaa", fontSize: "14px" }}>Nothing flagged right now.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {items.map((item) => (
            <div key={item.id} style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                <div>
                  <p style={{ fontWeight: "700", color: "#000" }}>{item.sender_name}</p>
                  <p style={{ fontSize: "12px", color: "#999" }}>{item.sender_email} &middot; Transaction #{item.id}</p>
                </div>
                <span style={{ fontSize: "12px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: "#FFFBEB", color: "#B45309" }}>
                  {item.status}
                </span>
              </div>

              <div style={{ fontSize: "13px", color: "#666", marginBottom: "16px", lineHeight: 1.7 }}>
                <div>Amount: {Number(item.amount).toLocaleString()} {item.currency}</div>
                <div>Fraud score: {item.fraud_score !== null ? item.fraud_score.toFixed(4) : "—"} ({item.scoring_model ?? "unknown model"})</div>
                <div>Flagged: {new Date(item.created_at).toLocaleString()}</div>
              </div>

              <div style={{ display: "flex", gap: "12px" }}>
                <button onClick={() => resolve(item.id, "legitimate")} disabled={actingOnId === item.id}
                  style={{ flex: 1, padding: "12px", borderRadius: "14px", border: "1.5px solid #E5E7EB", backgroundColor: "#fff", color: "#333", fontSize: "14px", fontWeight: "700", cursor: actingOnId === item.id ? "not-allowed" : "pointer" }}>
                  Mark Legitimate
                </button>
                <button onClick={() => resolve(item.id, "confirmed_fraud")} disabled={actingOnId === item.id}
                  style={{ flex: 1, padding: "12px", borderRadius: "14px", border: "none", backgroundColor: "#DC2626", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: actingOnId === item.id ? "not-allowed" : "pointer" }}>
                  {actingOnId === item.id ? "Working..." : "Confirm Fraud & Reverse"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "12px", marginTop: "20px" }}>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
            style={{ padding: "8px 16px", borderRadius: "10px", border: "1px solid #E5E7EB", backgroundColor: page === 1 ? "#F5F5F5" : "#fff", color: page === 1 ? "#aaa" : "#000", cursor: page === 1 ? "not-allowed" : "pointer", fontSize: "13px", fontWeight: "600" }}>
            Previous
          </button>
          <p style={{ fontSize: "13px", color: "#aaa" }}>{page} / {totalPages}</p>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            style={{ padding: "8px 16px", borderRadius: "10px", border: "1px solid #E5E7EB", backgroundColor: page === totalPages ? "#F5F5F5" : "#fff", color: page === totalPages ? "#aaa" : "#000", cursor: page === totalPages ? "not-allowed" : "pointer", fontSize: "13px", fontWeight: "600" }}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
