"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

interface Wallet {
  currency: string;
  balance: number;
}

interface Transaction {
  id: number;
  type: "send" | "receive";
  amount: number;
  currency: string;
  counterparty_name: string | null;
  category: string | null;
  status: string;
  created_at: string;
}

interface ExchangeRate {
  base_currency: string;
  target_currency: string;
  rate: number;
  provider: string;
  last_updated_at: string | null;
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
  Transfer: "💸", TopUp: "➕", Exchange: "💱", Other: "📦",
};

export default function DashboardPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [exchangeRates, setExchangeRates] = useState<ExchangeRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchAll = useCallback(async () => {
    if (!user) return;
    try {
      const [balanceRes, txRes, rateRes] = await Promise.allSettled([
        api.get(`/accounts/balance?user_id=${user.id}`),
        api.get("/transactions?page_size=5"),
        api.get("/exchange/rates"),
      ]);

      if (balanceRes.status === "fulfilled") {
        setWallets(balanceRes.value.data.balances);
      }
      if (txRes.status === "fulfilled") {
        setTransactions(txRes.value.data.items);
      }
      if (rateRes.status === "fulfilled") {
        setExchangeRates(rateRes.value.data);
      }
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const usdWallet = wallets.find((w) => w.currency === "USD");
  const lbpWallet = wallets.find((w) => w.currency === "LBP");
  const usdLbpRate = exchangeRates.find(
    (r) => r.base_currency === "USD" && r.target_currency === "LBP"
  );

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "60vh" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ width: "32px", height: "32px", borderRadius: "50%", border: "3px solid #00C853", borderTopColor: "transparent", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
          <p style={{ color: "#aaa", fontSize: "13px" }}>Loading...</p>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", backgroundColor: "#F5F5F5", minHeight: "100vh", padding: "20px", paddingBottom: "80px" }}>

      {/* KYC banner */}
      {user?.kyc_status && user.kyc_status !== "approved" && (
        <div style={{ borderRadius: "16px", padding: "14px 16px", backgroundColor: user.kyc_status === "pending" ? "#FFFBEB" : "#FEF2F2", border: `1px solid ${user.kyc_status === "pending" ? "#FCD34D" : "#FECACA"}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <p style={{ fontSize: "13px", fontWeight: "700", color: user.kyc_status === "pending" ? "#92400E" : "#991B1B" }}>
              {user.kyc_status === "pending" ? "⏳ Identity verification pending" : "❌ KYC verification failed"}
            </p>
            <p style={{ fontSize: "12px", color: "#666", marginTop: "2px" }}>
              {user.kyc_status === "pending" ? "We're reviewing your documents." : "Please re-upload your documents."}
            </p>
          </div>
          {user.kyc_status !== "pending" && (
            <button onClick={() => router.push("/kyc")}
              style={{ fontSize: "12px", fontWeight: "700", color: "#00C853", background: "none", border: "none", cursor: "pointer", whiteSpace: "nowrap" }}>
              Re-upload →
            </button>
          )}
        </div>
      )}

      {/* Balance cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        <div style={{ borderRadius: "20px", backgroundColor: "#00C853", padding: "20px" }}>
          <p style={{ color: "rgba(255,255,255,0.8)", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Fresh USD</p>
          <p style={{ color: "#fff", fontSize: "26px", fontWeight: "800" }}>
            ${usdWallet ? usdWallet.balance.toFixed(2) : "0.00"}
          </p>
          <p style={{ color: "rgba(255,255,255,0.7)", fontSize: "11px", marginTop: "4px" }}>Available balance</p>
        </div>
        <div style={{ borderRadius: "20px", backgroundColor: "#fff", border: "1px solid #F0F0F0", padding: "20px" }}>
          <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Cash LBP</p>
          <p style={{ color: "#000", fontSize: "26px", fontWeight: "800" }}>
            {lbpWallet ? lbpWallet.balance.toLocaleString() : "0"} ل.ل
          </p>
          <p style={{ color: "#aaa", fontSize: "11px", marginTop: "4px" }}>Available balance</p>
        </div>
      </div>

      {/* Exchange rate widget */}
      {usdLbpRate && (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", border: "1px solid #F0F0F0", padding: "16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px" }}>Exchange Rate</p>
            <p style={{ color: "#000", fontSize: "16px", fontWeight: "700", marginTop: "4px" }}>
              1 USD = {Number(usdLbpRate.rate).toLocaleString()} LBP
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <span style={{ fontSize: "11px", color: "#aaa" }}>
              Refreshed {timeAgo(lastRefresh.toISOString())}
            </span>
            <br />
            <span style={{ fontSize: "11px", color: usdLbpRate.provider === "stub" ? "#F59E0B" : "#00C853", fontWeight: "600" }}>
              {usdLbpRate.provider === "stub" ? "● Stub" : "● Live"}
            </span>
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Quick actions</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
          {[
            { label: "Transfer", path: "/transfer", svg: <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="#00C853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
            { label: "Add Money", path: "/add-money", svg: <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#00C853" strokeWidth="2" strokeLinecap="round"/></svg> },
            { label: "Exchange", path: "/exchange", svg: <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke="#00C853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
          ].map(({ label, path, svg }) => (
            <button key={label} onClick={() => router.push(path)}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px", backgroundColor: "#fff", border: "1px solid #F0F0F0", borderRadius: "20px", padding: "16px 8px", cursor: "pointer" }}>
              {svg}
              <span style={{ color: "#333", fontSize: "11px", fontWeight: "600" }}>{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Recent transactions */}
      <div>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Recent transactions</p>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", border: "1px solid #F0F0F0", overflow: "hidden" }}>
          {transactions.length === 0 ? (
            <div style={{ padding: "32px", textAlign: "center" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>No transactions yet</p>
            </div>
          ) : (
            transactions.map((tx, i) => (
              <div key={tx.id} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderBottom: i < transactions.length - 1 ? "1px solid #F5F5F5" : "none" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px", flexShrink: 0 }}>
                  {categoryIcons[tx.category ?? "Other"] ?? "📦"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ color: "#000", fontSize: "14px", fontWeight: "500", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {tx.counterparty_name ?? (tx.type === "send" ? "Sent" : "Received")}
                  </p>
                  <p style={{ color: "#aaa", fontSize: "12px" }}>{timeAgo(tx.created_at)}</p>
                </div>
                <p style={{ fontSize: "14px", fontWeight: "700", color: tx.type === "receive" ? "#00C853" : "#000", flexShrink: 0 }}>
                  {tx.type === "receive" ? "+" : "-"}{tx.amount} {tx.currency}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}