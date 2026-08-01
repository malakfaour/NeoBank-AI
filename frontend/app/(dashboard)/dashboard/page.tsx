"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CarFront, CircleDollarSign, Clapperboard, Copy, FileText, Plus, ReceiptText, Utensils } from "lucide-react";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import { usePreferences } from "@/components/providers/AppPreferences";

interface Wallet {
  currency: string; balance: number;
  account_number: string | null; iban: string | null;
}
interface Transaction {
  id: number;
  type: string;
  exchange_leg?: "debit" | "credit" | null;
  amount: number;
  currency: string;
  counterparty_name: string | null;
  category: string | null;
  status: string;
  created_at: string;
}
interface ExchangeRateApiItem {
  base_currency: string; target_currency: string;
  rate: string | number; provider: string; last_updated_at: string | null;
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
  const timestamp = new Date(dateStr).getTime();

  if (Number.isNaN(timestamp)) return "";

  // Prevent future or timezone-shifted timestamps from displaying negative time.
  const diff = Math.max(
    0,
    Math.floor((Date.now() - timestamp) / 1000)
  );

  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

type TransactionDirection = "credit" | "debit" | "neutral";

function getTransactionDirection(
  transaction: Transaction
): TransactionDirection {
  if (transaction.type === "exchange") {
    if (transaction.exchange_leg === "credit") return "credit";
    if (transaction.exchange_leg === "debit") return "debit";

    // Historical exchange rows may not contain exchange_leg.
    return "neutral";
  }

  return transaction.type === "receive" ? "credit" : "debit";
}

function getTransactionTitle(transaction: Transaction): string {
  if (transaction.counterparty_name) {
    return transaction.counterparty_name;
  }

  if (transaction.type === "exchange") {
    if (transaction.exchange_leg === "credit") return "Exchange credit";
    if (transaction.exchange_leg === "debit") return "Exchange debit";
    return "Exchange";
  }

  return transaction.type === "send" ? "Sent" : "Received";
}

const categoryIcons: Record<string, React.ReactNode> = {
  Food: <Utensils size={18} />,
  Transport: <CarFront size={18} />,
  Bills: <ReceiptText size={18} />,
  Entertainment: <Clapperboard size={18} />,
  Transfer: <ArrowUpRight size={18} />,
  TopUp: <Plus size={18} />,
  Exchange: <ArrowLeftRight size={18} />,
  Other: <CircleDollarSign size={18} />,
  Uncategorized: <CircleDollarSign size={18} />,
};

const categoryColors: Record<string, string> = {
  Food: "#00C853", Transport: "#2196F3", Bills: "#FF9800",
  Entertainment: "#9C27B0", Transfer: "#00C853", TopUp: "#8BC34A",
  Exchange: "#FF5722", Other: "#607D8B", Uncategorized: "#9E9E9E",
};

export default function DashboardPage() {
  const router = useRouter();
  const { t } = usePreferences();
  const user = useAuthStore((s) => s.user);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [transactionPage, setTransactionPage] = useState(1);
  const [transactionTotalPages, setTransactionTotalPages] = useState(1);
  const [exchangeRate, setExchangeRate] = useState<ExchangeRate | null>(null);
  const [rateAge, setRateAge] = useState<string>("");
  const [summary, setSummary] = useState<SummaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const currentMonth = new Date().toISOString().slice(0, 7);

  const fetchAll = useCallback(async () => {
    try {
      const [balanceRes, txRes, rateRes, summaryRes] = await Promise.allSettled([
        api.get("/accounts/balance"),
        api.get(`/transactions?page=${transactionPage}&page_size=5`),
        api.get("/exchange/rates"),
        api.get(`/transactions/summary?month=${currentMonth}`),
      ]);
      const results = [balanceRes, txRes, rateRes, summaryRes];
      let hasLoadError = results.some(
        (result) => result.status === "rejected"
      );

      if (balanceRes.status === "fulfilled") setWallets(balanceRes.value.data.balances ?? []);
      if (txRes.status === "fulfilled") {
        const transactionData = txRes.value.data;

        setTransactions(transactionData.items ?? []);
        setTransactionTotalPages(
          Math.max(1, Number(transactionData.total_pages) || 1)
        );
      }
      if (rateRes.status === "fulfilled") {
        const rates: ExchangeRateApiItem[] = Array.isArray(
          rateRes.value.data
        )
          ? rateRes.value.data
          : [];

        const usdToLbpRate = rates.find(
          (item) =>
            item.base_currency === "USD" &&
            item.target_currency === "LBP"
        );

        const numericRate = usdToLbpRate
          ? Number(usdToLbpRate.rate)
          : Number.NaN;

        if (
          usdToLbpRate &&
          Number.isFinite(numericRate)
        ) {
          setExchangeRate({
            ...usdToLbpRate,
            rate: numericRate,
          });

          setRateAge(
            usdToLbpRate.last_updated_at
              ? timeAgo(usdToLbpRate.last_updated_at)
              : ""
          );
        } else {
          setExchangeRate(null);
          setRateAge("");
          hasLoadError = true;
        }
      } else {
        setExchangeRate(null);
        setRateAge("");
      }
      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value.data.summary ?? []);
      setLoadError(hasLoadError);
    } finally {
      setLoading(false);
    }
  }, [currentMonth, transactionPage]);

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
    <main className="bank-dashboard">
      {loadError && (
        <div
          role="alert"
          style={{
            borderRadius: "16px",
            padding: "14px 16px",
            backgroundColor: "#FEF2F2",
            border: "1px solid #FECACA",
            color: "#991B1B",
            fontSize: "13px",
            fontWeight: "600",
          }}
        >
          Some dashboard data could not be loaded. Please try again.
        </div>
      )}

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

      <section className="accounts-overview">
        <div className="dashboard-balance-grid">
          <article className="dashboard-balance-card dashboard-balance-card--usd">
            <div className="dashboard-balance-card__top">
              <span>{t("dashboard.freshUsd")}</span>
              <Image src="/logo.svg" alt="Neo" width={62} height={28} />
            </div>
            <div className="dashboard-balance-card__amount">
              <strong>{usdWallet ? `$${usdWallet.balance.toFixed(2)}` : "$0.00"}</strong>
              <small>{t("dashboard.available")}</small>
            </div>
            <div className="dashboard-balance-card__bottom">
              {usdWallet?.iban && <button onClick={() => copyIBAN(usdWallet.iban!)}><Copy size={14} />{copied === usdWallet.iban ? t("dashboard.copied") : t("dashboard.iban")}</button>}
              <span className="mastercard" aria-label="Mastercard"><i /><i /></span>
            </div>
          </article>

          <article className="dashboard-balance-card dashboard-balance-card--lbp">
            <div className="dashboard-balance-card__top">
              <span>{t("dashboard.cashLbp")}</span>
              <Image src="/logo.svg" alt="Neo" width={62} height={28} />
            </div>
            <div className="dashboard-balance-card__amount">
              <strong>{lbpWallet ? `${lbpWallet.balance.toLocaleString()} LBP` : "0 LBP"}</strong>
              <small>{t("dashboard.available")}</small>
            </div>
            <div className="dashboard-balance-card__bottom">
              {lbpWallet?.iban && <button onClick={() => copyIBAN(lbpWallet.iban!)}><Copy size={14} />{copied === lbpWallet.iban ? t("dashboard.copied") : t("dashboard.iban")}</button>}
              <span className="mastercard" aria-label="Mastercard"><i /><i /></span>
            </div>
          </article>
        </div>

        <div className="dashboard-actions-block">
          <div className="dashboard-section-title"><h2>{t("dashboard.actions")}</h2></div>
          <div className="quick-action-grid">
            {[
              { label: t("dashboard.add"), path: "/add-money", icon: Plus },
              { label: t("dashboard.transfer"), path: "/transfer", icon: ArrowUpRight },
              { label: t("dashboard.exchange"), path: "/exchange", icon: ArrowLeftRight },
              { label: t("dashboard.bills"), path: "/bills", icon: FileText },
            ].map(({ label, path, icon: Icon }) => <button key={path} onClick={() => router.push(path)}><span><Icon size={20} /></span><small>{label}</small></button>)}
          </div>
          <div className="exchange-strip">
            <span><ArrowDownLeft size={20} /></span>
            <div className="exchange-strip__rate"><small>USD / LBP</small><strong>{exchangeRate ? `1 USD = ${exchangeRate.rate.toLocaleString()} LBP` : "—"}</strong></div>
            <div className="exchange-strip__meta"><small>{t("dashboard.marketRate")}</small>{rateAge && <span>{t("dashboard.updated")} {rateAge}</span>}</div>
            <b><i /> {t("dashboard.live")}</b>
          </div>
        </div>
      </section>

      {/* Spending chart */}
      <div className="dashboard-card spending-card" style={{ backgroundColor: "var(--surface)", borderRadius: "20px", border: "1px solid var(--line)", padding: "20px" }}>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>
          {t("dashboard.spending")} — {currentMonth}
        </p>
        {chartData.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "24px 0", gap: "8px" }}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
  <path
    d="M4 19V5M4 19H20M8 16V10M12 16V7M16 16V12"
    stroke="#00C853"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
  />
</svg>
            <p style={{ color: "#aaa", fontSize: "13px" }}>{t("dashboard.noSpending")}</p>
            <p style={{ color: "#ccc", fontSize: "12px" }}>{t("dashboard.makeTransaction")}</p>
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <defs>
                  <linearGradient id="neo-spend-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#062c21" />
                    <stop offset="52%" stopColor="#008f4d" />
                    <stop offset="100%" stopColor="#00d66f" />
                  </linearGradient>
                </defs>
                <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={50}>
                  {chartData.map((entry) => (
                    <Cell key={entry.name} fill={entry.name === "Transfer" ? "url(#neo-spend-gradient)" : (categoryColors[entry.name] ?? "#9E9E9E")} />
                  ))}
                </Pie>
              <Tooltip formatter={(v) => (typeof v === "number" ? v.toLocaleString() : String(v))} />
                <Legend iconType="circle" iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "8px" }}>
              {chartData.map((entry) => (
                <div key={entry.name} style={{ display: "flex", alignItems: "center", gap: "6px", backgroundColor: "#F5F5F5", borderRadius: "20px", padding: "4px 10px" }}>
                  <span style={{ fontSize: "12px" }}>{categoryIcons[entry.name] ?? "□"}</span>
                  <span style={{ fontSize: "12px", fontWeight: "600", color: "#333" }}>{entry.name}</span>
                  <span style={{ fontSize: "11px", color: "#aaa" }}>({entry.count})</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Recent transactions */}
      <section className="transactions-section">
        <div className="dashboard-section-title"><h2>{t("dashboard.recent")}</h2><button onClick={() => router.push("/transactions")}>{t("dashboard.view")} <ArrowUpRight size={15} /></button></div>
        <div className="transaction-list">
          {transactions.length === 0 ? (
            <div style={{ padding: "32px", textAlign: "center" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>{t("dashboard.noTransactions")}</p>
            </div>
          ) : transactions.map((tx) => {
            const cat = tx.category ?? "Uncategorized";
            const direction = getTransactionDirection(tx);
            const amountPrefix =
              direction === "credit"
                ? "+"
                : direction === "debit"
                  ? "-"
                  : "";
            const amountValue = Number(tx.amount);
            const displayAmount = Number.isFinite(amountValue) ? String(amountValue) : String(tx.amount);

            return (
              <div key={tx.id} className="transaction-row">
                <div className="transaction-row__icon">
                  {categoryIcons[cat] ?? <CircleDollarSign size={18} />}
                </div>
                <div className="transaction-row__details">
                  <p>
                    {getTransactionTitle(tx)}
                  </p>
                  <div className="transaction-row__meta">
                    <span>{timeAgo(tx.created_at)}</span><i /> <span>{cat}</span>
                  </div>
                </div>
                <p className={`transaction-row__amount${direction === "credit" ? " is-credit" : ""}`}>
                  {amountPrefix}{displayAmount} {tx.currency}
                  <small>{tx.status}</small>
                </p>
              </div>
            );
          })}

          {transactionTotalPages > 1 && (
            <div className="transaction-pagination">
              <button
                type="button"
                aria-label="Previous transaction page"
                disabled={transactionPage === 1}
                onClick={() =>
                  setTransactionPage((page) => Math.max(1, page - 1))
                }
                className="transaction-pagination__button"
              >
                Previous
              </button>

              <span className="transaction-pagination__page">
                Page {transactionPage} of {transactionTotalPages}
              </span>

              <button
                type="button"
                aria-label="Next transaction page"
                disabled={transactionPage >= transactionTotalPages}
                onClick={() =>
                  setTransactionPage((page) =>
                    Math.min(transactionTotalPages, page + 1)
                  )
                }
                className="transaction-pagination__button"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </section>

    </main>
  );
}
