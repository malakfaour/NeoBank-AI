"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { usePreferences } from "@/components/providers/AppPreferences";

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

function timeAgo(d: string, locale: "en" | "ar") {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return locale === "ar" ? `منذ ${diff} ث` : `${diff}s ago`;
  if (diff < 3600) return locale === "ar" ? `منذ ${Math.floor(diff / 60)} د` : `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return locale === "ar" ? `منذ ${Math.floor(diff / 3600)} س` : `${Math.floor(diff / 3600)}h ago`;
  return new Date(d).toLocaleDateString(locale === "ar" ? "ar-LB" : "en-GB", { day: "numeric", month: "short" });
}

const transactionIconColor = "#00D66F";

function TxIcon({ category }: { category: string }) {
  const color = transactionIconColor;
  if (category === "Transfer") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (category === "Exchange") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (category === "Bills") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (category === "TopUp") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke={color} strokeWidth="2" strokeLinecap="round"/></svg>;
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

export default function TransactionsPage() {
  const router = useRouter();
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("all");
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
    <div className="bank-feature-page transactions-page" style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
        <button onClick={() => router.back()}
          style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>{tr("Transactions", "المعاملات")}</h2>
        {total > 0 && <span style={{ fontSize: "12px", color: "#aaa" }}>{total} {tr("total", "معاملة")}</span>}
      </div>

      {/* Filters */}
      <div className="transaction-filters" style={{ display: "flex", gap: "8px", marginBottom: "16px", overflowX: "auto", paddingBottom: "4px" }}>
        {filters.map((f) => (
          <button key={f} onClick={() => { setFilter(f); setPage(1); }}
            style={{ padding: "9px 18px", borderRadius: "20px", border: filter === f ? "1px solid #26372E" : "1px solid transparent", backgroundColor: filter === f ? "#111713" : "#fff", color: filter === f ? "#00D66F" : "#333", fontSize: "13px", fontWeight: "700", cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>
            {f === "all" ? tr("All", "الكل") : f === "Transfer" ? tr("Transfer", "تحويل") : f === "Exchange" ? tr("Exchange", "تحويل عملات") : f === "Bills" ? tr("Bills", "فواتير") : tr("Top Up", "إضافة أموال")}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="feature-list-card" style={{ backgroundColor: "#fff", borderRadius: "20px", overflow: "hidden", marginBottom: "16px" }}>
        {loading ? (
          <div style={{ padding: "32px", textAlign: "center" }}><p style={{ color: "#aaa" }}>{tr("Loading...", "جارٍ التحميل...")}</p></div>
        ) : transactions.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{tr("No transactions found", "لا توجد معاملات")}</p>
          </div>
        ) : transactions.map((tx, i) => (
          <div className="feature-transaction-row" key={tx.id} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderBottom: i < transactions.length - 1 ? "1px solid #F5F5F5" : "none" }}>
            <div className="feature-transaction-icon" style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F5F5F5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <TxIcon category={tx.category} />
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{tx.category === "Transfer" ? tr("Transfer", "تحويل") : tx.category === "Exchange" ? tr("Exchange", "تحويل عملات") : tx.category === "Bills" ? tr("Bills", "فواتير") : tx.category === "TopUp" ? tr("Top Up", "إضافة أموال") : tr("Other", "أخرى")}</p>
              <p style={{ fontSize: "12px", color: "#aaa" }}>{timeAgo(tx.created_at, locale)}</p>
            </div>
            <div style={{ textAlign: "right" }}>
              <p style={{ fontSize: "14px", fontWeight: "700", color: tx.category === "TopUp" ? "#00C853" : "#000" }}>
                {tx.category === "TopUp" ? "+" : "-"}{Number(tx.amount).toLocaleString()} {tx.currency}
              </p>
              <span style={{ fontSize: "11px", color: tx.status === "completed" ? "#00C853" : tx.status === "pending" ? "#F59E0B" : "#EF4444", fontWeight: "600" }}>
                {tx.status === "completed" ? tr("Completed", "مكتملة") : tx.status === "pending" ? tr("Pending", "قيد المعالجة") : tr("Failed", "فشلت")}
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
            {tr("Previous", "السابق")}
          </button>
          <p style={{ fontSize: "13px", color: "#aaa" }}>{page} / {totalPages}</p>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            style={{ padding: "8px 16px", borderRadius: "10px", border: "1px solid #E5E7EB", backgroundColor: page === totalPages ? "#F5F5F5" : "#fff", color: page === totalPages ? "#aaa" : "#000", cursor: page === totalPages ? "not-allowed" : "pointer", fontSize: "13px", fontWeight: "600" }}>
            {tr("Next", "التالي")}
          </button>
        </div>
      )}
    </div>
  );
}
