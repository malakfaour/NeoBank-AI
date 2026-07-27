"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface Transaction {
  id: number;
  type: string;
  amount: number;
  currency: string;
  category: string;
  status: string;
  created_at: string;
  sender_id: number;
  receiver_id: number;
}

interface TransactionAuditLogItem {
  id: number;
  action: string;
  actor_id: number | null;
  timestamp: string;
  metadata: Record<string, unknown> | null;
}

interface TransactionDetail {
  id: number;
  sender_id: number;
  receiver_id: number;
  type: string;
  amount: number;
  currency: string;
  counterparty_name: string | null;
  category: string | null;
  fraud_score: number | null;
  rule_triggered: string | null;
  status: string;
  flagged: boolean;
  created_at: string;
  audit_logs: TransactionAuditLogItem[];
}

function timeAgo(d: string) {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

const categoryColor: Record<string, string> = {
  Transfer: "#3B82F6", Exchange: "#8B5CF6", Bills: "#F59E0B",
  TopUp: "#00C853", Reversal: "#EF4444", Default: "#6B7280",
};

// Human-readable explanations for each fraud_rules.py rule name, shown in
// the flagged-transaction detail view (Section 13, item 89 -- a flagged
// transaction previously showed only the bare word "flagged" with no
// explanation and wasn't even clickable).
const RULE_EXPLANATIONS: Record<string, string> = {
  excessive_amount_vs_average:
    "This amount is much larger than your typical transfers over the last 30 days.",
  rapid_multi_recipient:
    "Several transfers were sent to different recipients in a short window of time.",
  new_recipient_high_amount:
    "A relatively large amount was sent to a recipient you haven&apos;t sent to before.",
};

function ruleExplanation(ruleName: string | null): string {
  if (ruleName && RULE_EXPLANATIONS[ruleName]) return RULE_EXPLANATIONS[ruleName];
  // Flagged with no specific rule name -- e.g. an ML score crossed the
  // threshold, or fraud scoring itself failed and the transaction was
  // conservatively flagged for manual review as a safe default.
  return "This transaction has been flagged for manual review by our fraud detection system.";
}

function TxIcon({ category }: { category: string }) {
  const color = categoryColor[category] ?? categoryColor.Default;
  if (category === "Transfer") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (category === "Exchange") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (category === "Bills") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (category === "TopUp") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke={color} strokeWidth="2" strokeLinecap="round"/></svg>;
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function TransactionDetailModal({ transactionId, onClose }: { transactionId: number; onClose: () => void }) {
  const [detail, setDetail] = useState<TransactionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get(`/transactions/${transactionId}`)
      .then((res) => { if (!cancelled) setDetail(res.data); })
      .catch(() => { if (!cancelled) setError("Could not load transaction details."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [transactionId]);

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px", zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", maxWidth: "420px", maxHeight: "85vh", overflowY: "auto" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: "700", color: "#000" }}>Transaction Details</h3>
          <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer", fontSize: "18px", color: "#999" }}>✕</button>
        </div>

        {loading && <p style={{ color: "#aaa", fontSize: "14px" }}>Loading...</p>}
        {error && <p style={{ color: "#EF4444", fontSize: "14px" }}>{error}</p>}

        {detail && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {detail.flagged && (
              <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "14px", padding: "14px" }}>
                <p style={{ fontSize: "13px", fontWeight: "700", color: "#DC2626", marginBottom: "6px" }}>⚠️ Flagged for review</p>
                <p style={{ fontSize: "13px", color: "#7F1D1D" }}>{ruleExplanation(detail.rule_triggered)}</p>
                <p style={{ fontSize: "12px", color: "#991B1B", marginTop: "8px" }}>
                  This transaction already completed -- funds were transferred normally. Flagging means it&apos;s
                  been sent to our compliance team for review, not that it was blocked.
                </p>
              </div>
            )}

            {[
              { label: "Amount", value: `${detail.amount.toLocaleString()} ${detail.currency}` },
              { label: "Category", value: detail.category ?? "—" },
              { label: "Counterparty", value: detail.counterparty_name ?? "—" },
              { label: "Status", value: detail.status },
              { label: "Date", value: new Date(detail.created_at).toLocaleString() },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
                <p style={{ color: "#aaa", fontSize: "13px" }}>{label}</p>
                <p style={{ color: "#000", fontSize: "13px", fontWeight: "600", textTransform: "capitalize" }}>{value}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function TransactionsPage() {
  const router = useRouter();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("all");
  const [selectedTxId, setSelectedTxId] = useState<number | null>(null);
  const pageSize = 20;


useEffect(() => {
  let cancelled = false;
  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (filter !== "all") params.append("category", filter);
      const res = await api.get(`/transactions?${params}`);
      if (!cancelled) {
        setTransactions(res.data.items ?? res.data ?? []);
        setTotal(res.data.total ?? 0);
      }
    } catch { /* ignore */ }
    finally { if (!cancelled) setLoading(false); }
  };
  load();
  return () => { cancelled = true; };
}, [page, filter]);
  const filters = ["all", "Transfer", "Exchange", "Bills", "TopUp"];
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
        <button onClick={() => router.back()}
          style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>Transactions</h2>
        {total > 0 && <span style={{ fontSize: "12px", color: "#aaa" }}>{total} total</span>}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", overflowX: "auto", paddingBottom: "4px" }}>
        {filters.map((f) => (
          <button key={f} onClick={() => { setFilter(f); setPage(1); }}
            style={{ padding: "6px 14px", borderRadius: "20px", border: "none", backgroundColor: filter === f ? "#00C853" : "#fff", color: filter === f ? "#fff" : "#333", fontSize: "13px", fontWeight: "600", cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>
            {f === "all" ? "All" : f}
          </button>
        ))}
      </div>

      {/* List */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", overflow: "hidden", marginBottom: "16px" }}>
        {loading ? (
          <div style={{ padding: "32px", textAlign: "center" }}><p style={{ color: "#aaa" }}>Loading...</p></div>
        ) : transactions.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>No transactions found</p>
          </div>
        ) : transactions.map((tx, i) => (
          <div key={tx.id} onClick={() => setSelectedTxId(tx.id)}
            style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderBottom: i < transactions.length - 1 ? "1px solid #F5F5F5" : "none", cursor: "pointer" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F5F5F5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <TxIcon category={tx.category} />
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{tx.category}</p>
              <p style={{ fontSize: "12px", color: "#aaa" }}>{timeAgo(tx.created_at)}</p>
            </div>
            <div style={{ textAlign: "right" }}>
              <p style={{ fontSize: "14px", fontWeight: "700", color: tx.category === "TopUp" ? "#00C853" : "#000" }}>
                {tx.category === "TopUp" ? "+" : "-"}{Number(tx.amount).toLocaleString()} {tx.currency}
              </p>
              <span style={{ fontSize: "11px", color: tx.status === "completed" ? "#00C853" : tx.status === "pending" ? "#F59E0B" : "#EF4444", fontWeight: "600" }}>
                {tx.status}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "12px" }}>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            style={{ padding: "8px 16px", borderRadius: "10px", border: "1px solid #E5E7EB", backgroundColor: page === 1 ? "#F5F5F5" : "#fff", color: page === 1 ? "#aaa" : "#000", cursor: page === 1 ? "not-allowed" : "pointer", fontSize: "13px", fontWeight: "600" }}>
            Previous
          </button>
          <p style={{ fontSize: "13px", color: "#aaa" }}>{page} / {totalPages}</p>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            style={{ padding: "8px 16px", borderRadius: "10px", border: "1px solid #E5E7EB", backgroundColor: page === totalPages ? "#F5F5F5" : "#fff", color: page === totalPages ? "#aaa" : "#000", cursor: page === totalPages ? "not-allowed" : "pointer", fontSize: "13px", fontWeight: "600" }}>
            Next
          </button>
        </div>
      )}

      {selectedTxId !== null && (
        <TransactionDetailModal transactionId={selectedTxId} onClose={() => setSelectedTxId(null)} />
      )}
    </div>
  );
}
