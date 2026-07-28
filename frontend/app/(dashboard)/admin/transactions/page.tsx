"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface AdminTransactionItem {
  id: number;
  sender_id: number;
  sender_name: string;
  receiver_id: number;
  receiver_name: string;
  amount: string;
  currency: string;
  category: string | null;
  status: string;
  created_at: string;
}

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "flagged", label: "Flagged" },
  { value: "failed", label: "Failed" },
  { value: "reversed", label: "Reversed" },
];

const STATUS_BADGE_COLORS: Record<string, { bg: string; fg: string }> = {
  pending: { bg: "#FFFBEB", fg: "#B45309" },
  completed: { bg: "#F0FDF4", fg: "#00C853" },
  flagged: { bg: "#FFFBEB", fg: "#B45309" },
  failed: { bg: "#FEF2F2", fg: "#DC2626" },
  reversed: { bg: "#F3F4F6", fg: "#374151" },
};

export default function AdminTransactionsPage() {
  const router = useRouter();
  const [items, setItems] = useState<AdminTransactionItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const fetchTransactions = useCallback(async () => {
    try {
      const res = await api.get("/admin/transactions", {
        params: {
          page,
          page_size: 20,
          status: statusFilter || undefined,
          q: query || undefined,
        },
      });
      setItems(res.data.items ?? []);
      setTotalPages(res.data.total_pages ?? 1);
      setError("");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else setError("Failed to load transactions.");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, query]);

  // Same pattern as admin/kyc/page.tsx's fetchQueue -- see that file's
  // comment for why this suppression is needed.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setLoading(true);
    setQuery(searchInput);
  };

  if (forbidden) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center", maxWidth: "420px", margin: "80px auto" }}>
          <p style={{ fontWeight: "700", color: "#000", marginBottom: "8px" }}>Compliance access required</p>
          <p style={{ color: "#999", fontSize: "13px" }}>Your account needs the compliance_officer or admin role to view all transactions.</p>
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
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>All transactions</h2>
      </div>

      <form onSubmit={submitSearch} style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search sender/receiver name or email"
          style={{ flex: 1, padding: "12px 16px", borderRadius: "14px", border: "1.5px solid #E5E7EB", fontSize: "14px", backgroundColor: "#fff" }}
        />
        <button type="submit"
          style={{ padding: "12px 20px", borderRadius: "14px", border: "none", backgroundColor: "#00C853", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: "pointer" }}>
          Search
        </button>
      </form>

      <div style={{ display: "flex", gap: "8px", marginBottom: "20px", overflowX: "auto" }}>
        {STATUS_FILTERS.map((f) => (
          <button key={f.value} onClick={() => { setLoading(true); setPage(1); setStatusFilter(f.value); }}
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
          <p style={{ color: "#aaa", fontSize: "14px" }}>No transactions found.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {items.map((item) => (
            <div key={item.id} style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                <div>
                  <p style={{ fontWeight: "700", color: "#000" }}>{item.sender_name} &rarr; {item.receiver_name}</p>
                  <p style={{ fontSize: "12px", color: "#999" }}>Transaction #{item.id} &middot; {item.category ?? "Uncategorized"}</p>
                </div>
                <span style={{ fontSize: "12px", fontWeight: "700", padding: "4px 10px", borderRadius: "999px", backgroundColor: STATUS_BADGE_COLORS[item.status]?.bg ?? "#F3F4F6", color: STATUS_BADGE_COLORS[item.status]?.fg ?? "#374151" }}>
                  {item.status}
                </span>
              </div>

              <div style={{ fontSize: "13px", color: "#666", lineHeight: 1.7 }}>
                <div>Amount: {Number(item.amount).toLocaleString()} {item.currency}</div>
                <div>Created: {new Date(item.created_at).toLocaleString()}</div>
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
