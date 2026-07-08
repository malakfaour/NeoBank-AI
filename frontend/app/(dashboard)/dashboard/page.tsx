"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

interface Wallet {
  currency: string; balance: number;
  account_number: string | null; iban: string | null;
}
interface Transaction {
  id: number; type: "send" | "receive"; amount: number;
  currency: string; counterparty_name: string | null;
  category: string | null; status: string; created_at: string;
}
interface ExchangeRate {
  base_currency: string; target_currency: string;
  rate: number; provider: string; last_updated_at: string | null;
}
interface SummaryItem {
  category: string | null; currency: string;
  total_amount: number; transaction_count: number;
}

function timeAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const categoryIcons: Record<string, string> = {
  Food: "🍽️", Transport: "🚗", Bills: "🧾", Entertainment: "🎬",
  Transfer: "💸", TopUp: "➕", Exchange: "💱", Other: "📦", Uncategorized: "❓",
};

const categoryColors: Record<string, string> = {
  Food: "#00C853", Transport: "#2196F3", Bills: "#FF9800",
  Entertainment: "#9C27B0", Transfer: "#00BCD4", TopUp: "#8BC34A",
  Exchange: "#FF5722", Other: "#607D8B", Uncategorized: "#9E9E9E",
};

const pageStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: "20px",
  backgroundColor: "#F5F5F5", minHeight: "100vh",
  padding: "20px", paddingBottom: "80px",
};

export default function DashboardPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [exchangeRate, setExchangeRate] = useState<ExchangeRate | null>(null);
  const [rateAge, setRateAge] = useState<string>("");
  const [summary, setSummary] = useState<SummaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);

  const currentMonth = new Date().toISOString().slice(0, 7);

  const fetchAll = useCallback(async () => {
    try {
      const [balanceRes, txRes, rateRes, summaryRes] = await Promise.allSettled([
        api.get("/accounts/balance"),
        api.get("/transactions?page_size=5"),
        api.get("/exchange/rates"),
        api.get(`/transactions/summary?month=${currentMonth}`),
      ]);
      if (balanceRes.status === "fulfilled") setWallets(balanceRes.value.data.balances ?? []);
      if (txRes.status === "fulfilled") setTransactions(txRes.value.data.items ?? []);
      if (rateRes.status === "fulfilled") {
        const rates: ExchangeRate[] = rateRes.value.data;
        const r = Array.isArray(rates)
          ? rates.find((x) => x.base_currency === "USD" && x.target_currency === "LBP") ?? null
          : null;
        setExchangeRate(r);
        if (r?.last_updated_at) setRateAge(timeAgo(r.last_updated_at));
      }
      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value.data.summary ?? []);
    } finally {
      setLoading(false);
    }
  }, [currentMonth]);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const copyIBAN = (iban: string) => {
    navigator.clipboard.writeText(iban).then(() => {
      setCopied(iban);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  // Aggregate summary by category (combine currencies for chart display)
  const chartData = Object.values(
    summary.reduce((acc, item) => {
      const cat = item.category ?? "Uncategorized";
      if (!acc[cat]) acc[cat] = { name: cat, value: 0, count: 0 };
      acc[cat].value += Number(item.total_amount);
      acc[cat].count += item.transaction_count;
      return acc;
    }, {} as Record<string, { name: string; value: number; count: number }>)
  );

  const usdWallet = wallets.find((w) => w.currency === "USD");
  const lbpWallet = wallets.find((w) => w.currency === "LBP");

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", backgroundColor: "#F5F5F5" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: "36px", height: "36px", borderRadius: "50%", border: "3px solid #00C853", borderTopColor: "transparent", margin: "0 auto 12px" }} className="spinner" />
        <p style={{ color: "#aaa", fontSize: "13px" }}>Loading your dashboard...</p>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}.spinner{animation:spin 0.8s linear infinite}`}</style>
    </div>
  );

  return (
    <div style={pageStyle}>

      {/* KYC banner */}
      {user?.kyc_status && user.kyc_status !== "approved" && (
        <div style={{ borderRadius: "16px", padding: "14px 16px", backgroundColor: user.kyc_status === "pending" ? "#FFFBEB" : "#FEF2F2", border: `1px solid ${user.kyc_status === "pending" ? "#FCD34D" : "#FECACA"}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ fontSize: "13px", fontWeight: "700", color: user.kyc_status === "pending" ? "#92400E" : "#991B1B" }}>
            {user.kyc_status === "pending" ? "⏳ Identity verification pending" : "⚠️ KYC flagged or rejected"}
          </p>
          {(user.kyc_status === "flagged" || user.kyc_status === "rejected") && (
            <button onClick={() => router.push("/kyc")} style={{ fontSize: "12px", fontWeight: "600", color: "#991B1B", background: "none", border: "1px solid #FECACA", borderRadius: "8px", padding: "4px 10px", cursor: "pointer" }}>
              Re-upload
            </button>
          )}
        </div>
      )}

      {/* Balance cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        {[usdWallet, lbpWallet].map((w) => !w ? null : (
          <div key={w.currency} style={{ borderRadius: "20px", padding: "20px", backgroundColor: w.currency === "USD" ? "#00C853" : "#fff", border: w.currency === "LBP" ? "1px solid #F0F0F0" : "none" }}>
            <p style={{ fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", color: w.currency === "USD" ? "rgba(255,255,255,0.8)" : "#aaa", marginBottom: "6px" }}>
              {w.currency === "USD" ? "Fresh USD" : "Cash LBP"}
            </p>
            <p style={{ fontSize: "24px", fontWeight: "800", color: w.currency === "USD" ? "#fff" : "#000", marginBottom: "4px" }}>
              {w.currency === "USD" ? `$${w.balance.toFixed(2)}` : `${w.balance.toLocaleString()} ل.ل`}
            </p>
            <p style={{ fontSize: "11px", color: w.currency === "USD" ? "rgba(255,255,255,0.7)" : "#aaa", marginBottom: "8px" }}>Available balance</p>
            {w.iban && (
              <button onClick={() => copyIBAN(w.iban!)} style={{ fontSize: "11px", color: w.currency === "USD" ? "rgba(255,255,255,0.9)" : "#666", background: "none", border: `1px solid ${w.currency === "USD" ? "rgba(255,255,255,0.4)" : "#E5E7EB"}`, borderRadius: "8px", padding: "4px 10px", cursor: "pointer" }}>
                {copied === w.iban ? "✓ Copied!" : `Copy IBAN`}
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Exchange rate */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", border: "1px solid #F0F0F0", padding: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "4px" }}>Exchange rate</p>
            <p style={{ fontSize: "16px", fontWeight: "700", color: "#000" }}>
              {exchangeRate ? `1 USD = ${exchangeRate.rate.toLocaleString()} LBP` : "—"}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            {rateAge && <p style={{ color: "#aaa", fontSize: "11px" }}>Refreshed {rateAge}</p>}
            <p style={{ color: "#00C853", fontSize: "11px", fontWeight: "600" }}>● Live</p>
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Quick actions</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
          {[
            { label: "Transfer", path: "/transfer", svg: <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="#00C853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
            { label: "Add Money", path: "/add-money", svg: <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#00C853" strokeWidth="2" strokeLinecap="round"/></svg> },
            { label: "Exchange", path: "/exchange", svg: <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke="#00C853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
          ].map(({ label, path, svg }) => (
            <button key={label} onClick={() => router.push(path)} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px", backgroundColor: "#fff", border: "1px solid #F0F0F0", borderRadius: "20px", padding: "16px 8px", cursor: "pointer" }}>
              {svg}
              <span style={{ color: "#333", fontSize: "11px", fontWeight: "600" }}>{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Spending chart */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", border: "1px solid #F0F0F0", padding: "16px" }}>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>
          Spending by category — {currentMonth}
        </p>
        {chartData.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "24px 0", gap: "8px" }}>
            <span style={{ fontSize: "32px" }}>📊</span>
            <p style={{ color: "#aaa", fontSize: "13px" }}>No spending data yet this month</p>
            <p style={{ color: "#ccc", fontSize: "12px" }}>Make a transaction to see your breakdown</p>
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={50}>
                  {chartData.map((entry) => (
                    <Cell key={entry.name} fill={categoryColors[entry.name] ?? "#9E9E9E"} />
                  ))}
                </Pie>
              <Tooltip formatter={(v) => (typeof v === "number" ? v.toLocaleString() : String(v))} />
                <Legend iconType="circle" iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "8px" }}>
              {chartData.map((entry) => (
                <div key={entry.name} style={{ display: "flex", alignItems: "center", gap: "6px", backgroundColor: "#F5F5F5", borderRadius: "20px", padding: "4px 10px" }}>
                  <span style={{ fontSize: "12px" }}>{categoryIcons[entry.name] ?? "📦"}</span>
                  <span style={{ fontSize: "12px", fontWeight: "600", color: "#333" }}>{entry.name}</span>
                  <span style={{ fontSize: "11px", color: "#aaa" }}>({entry.count})</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Recent transactions */}
      <div>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Recent transactions</p>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", border: "1px solid #F0F0F0", overflow: "hidden" }}>
          {transactions.length === 0 ? (
            <div style={{ padding: "32px", textAlign: "center" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>No transactions yet</p>
            </div>
          ) : transactions.map((tx, i) => {
            const cat = tx.category ?? "Uncategorized";
            return (
              <div key={tx.id} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderBottom: i < transactions.length - 1 ? "1px solid #F5F5F5" : "none" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px", flexShrink: 0 }}>
                  {categoryIcons[cat] ?? "📦"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ color: "#000", fontSize: "14px", fontWeight: "500", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {tx.counterparty_name ?? (tx.type === "send" ? "Sent" : "Received")}
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "2px" }}>
                    <p style={{ color: "#aaa", fontSize: "12px" }}>{timeAgo(tx.created_at)}</p>
                    <span style={{ fontSize: "10px", fontWeight: "600", color: categoryColors[cat] ?? "#9E9E9E", backgroundColor: `${categoryColors[cat] ?? "#9E9E9E"}18`, borderRadius: "6px", padding: "1px 6px" }}>
                      {cat}
                    </span>
                  </div>
                </div>
                <p style={{ fontSize: "14px", fontWeight: "700", color: tx.type === "receive" ? "#00C853" : "#000", flexShrink: 0 }}>
                  {tx.type === "receive" ? "+" : "-"}{tx.amount} {tx.currency}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}