"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface Wallet { id?: number; currency: string; balance: number; account_number: string | null; iban: string | null; }
interface BillHistoryItem {
  id: number; bill_type: string; bill_reference: string;
  amount: number; currency: string; status: string;
  biller_error: string | null; paid_at: string;
}

type Step = "form" | "confirm" | "receipt";

const BILL_TYPES = [
  { value: "ogero", label: "Ogero", icon: "📞", desc: "Internet & telephone" },
  { value: "edl", label: "EDL", icon: "⚡", desc: "Electricity" },
  { value: "water", label: "Water", icon: "💧", desc: "Water authority" },
  { value: "mobile_topup", label: "Mobile Top-up", icon: "📱", desc: "Recharge mobile" },
];

const Wrap = ({ children }: { children: React.ReactNode }) => (
  <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>{children}</div>
);

const Header = ({ title, onBack }: { title: string; onBack: () => void }) => (
  <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
    <button onClick={onBack}
      style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>{title}</h2>
  </div>
);

function timeAgo(d: string) {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function BillsPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("form");
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null);
  const [billType, setBillType] = useState("");
  const [reference, setReference] = useState("");
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<{ bill_payment_id: number; transaction_id: number } | null>(null);
  const [history, setHistory] = useState<BillHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    api.get("/accounts/balance").then((r) => {
      const b = r.data.balances ?? [];
      setWallets(b);
      if (b.length > 0) setSelectedWallet(b[0]);
    }).catch(() => {});
    api.get("/bills/history").then((r) => {
      setHistory(r.data.items ?? []);
    }).catch(() => {})
      .finally(() => setHistoryLoading(false));
  }, []);

  const handlePay = async () => {
    if (!selectedWallet?.id || !billType || !reference || !amount) return;
    setLoading(true); setError("");
    try {
      const res = await api.post("/bills/pay", {
        from_wallet_id: selectedWallet.id,
        bill_type: billType,
        bill_reference: reference,
        amount: parseFloat(amount),
        currency: selectedWallet.currency,
      });
      setReceipt({ bill_payment_id: res.data.bill_payment_id, transaction_id: res.data.transaction_id });
      setStep("receipt");
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      if (detail && typeof detail === "object") {
        const d = detail as { error?: string; biller_error?: string };
        if (d.error === "wallet_frozen") setError("Your wallet is frozen. Please contact support.");
        else if (d.error === "wallet_closed") setError("Your wallet is closed. Please contact support.");
        else if (d.biller_error) setError(`Payment failed: ${d.biller_error}`);
        else setError(JSON.stringify(d));
      } else {
        setError(typeof detail === "string" ? detail : "Payment failed. Please try again.");
      }
    } finally { setLoading(false); }
  };

  const selectedBill = BILL_TYPES.find((b) => b.value === billType);
  const balance = selectedWallet?.balance ?? 0;
  const amountNum = parseFloat(amount) || 0;
  const insufficient = amountNum > balance;

  const goBack = () => {
    if (step === "form") router.back();
    else setStep("form");
  };

  if (step === "confirm") return (
    <Wrap>
      <Header title="Confirm Payment" onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: "Bill type", value: `${selectedBill?.icon} ${selectedBill?.label}` },
          { label: "Reference", value: reference },
          { label: "From", value: `${selectedWallet?.currency === "USD" ? "Fresh USD" : "Cash LBP"}` },
          { label: "Amount", value: `${selectedWallet?.currency === "USD" ? `$${amountNum.toFixed(2)}` : `${amountNum.toLocaleString()} ل.ل`}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={handlePay} disabled={loading}
        style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: loading ? "not-allowed" : "pointer" }}>
        {loading ? "Processing..." : "Confirm Payment"}
      </button>
    </Wrap>
  );

  if (step === "receipt") return (
    <Wrap>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", paddingTop: "40px" }}>
        <div style={{ width: "72px", height: "72px", borderRadius: "50%", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "32px" }}>✅</div>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>Payment Successful!</h2>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "Bill", value: `${selectedBill?.icon} ${selectedBill?.label}` },
            { label: "Reference", value: reference },
            { label: "Amount", value: `${selectedWallet?.currency === "USD" ? `$${amountNum.toFixed(2)}` : `${amountNum.toLocaleString()} ل.ل`}` },
            { label: "Payment ID", value: String(receipt?.bill_payment_id ?? "—") },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
              <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
            </div>
          ))}
        </div>
        <button onClick={() => router.push("/dashboard")}
          style={{ width: "100%", backgroundColor: "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
          Back to Dashboard
        </button>
      </div>
    </Wrap>
  );

  return (
    <Wrap>
      <Header title="Pay Bills" onBack={goBack} />

      {/* Bill type selector */}
      <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Select bill type</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "20px" }}>
        {BILL_TYPES.map((b) => (
          <button key={b.value} onClick={() => setBillType(b.value)}
            style={{ backgroundColor: "#fff", border: `2px solid ${billType === b.value ? "#00C853" : "#F0F0F0"}`, borderRadius: "16px", padding: "16px", textAlign: "left", cursor: "pointer" }}>
            <p style={{ fontSize: "24px", marginBottom: "6px" }}>{b.icon}</p>
            <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{b.label}</p>
            <p style={{ fontSize: "11px", color: "#aaa" }}>{b.desc}</p>
          </button>
        ))}
      </div>

      {/* Form */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Reference number</label>
          <input value={reference} onChange={(e) => setReference(e.target.value)}
            placeholder="Enter bill reference or account number"
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
        </div>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Pay from</label>
          <div style={{ display: "flex", gap: "8px" }}>
            {wallets.map((w) => (
              <button key={w.currency} onClick={() => setSelectedWallet(w)}
                style={{ flex: 1, padding: "10px", borderRadius: "12px", border: `2px solid ${selectedWallet?.currency === w.currency ? "#00C853" : "#F0F0F0"}`, backgroundColor: "#fff", cursor: "pointer", textAlign: "left" }}>
                <p style={{ fontSize: "11px", fontWeight: "700", color: "#00C853" }}>{w.currency}</p>
                <p style={{ fontSize: "13px", fontWeight: "600", color: "#000" }}>
                  {w.currency === "USD" ? `$${w.balance.toFixed(2)}` : `${w.balance.toLocaleString()} ل.ل`}
                </p>
              </button>
            ))}
          </div>
        </div>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Amount ({selectedWallet?.currency})</label>
          <input type="number" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }}
            placeholder="0.00"
            style={{ width: "100%", border: `1.5px solid ${insufficient ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
          {insufficient && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>⚠️ Insufficient balance</p>}
        </div>
      </div>

      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}

      <button onClick={() => setStep("confirm")} disabled={!billType || !reference || !amount || insufficient || amountNum <= 0}
        style={{ width: "100%", backgroundColor: !billType || !reference || !amount || insufficient ? "#E5E7EB" : "#00C853", color: !billType || !reference || !amount || insufficient ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: !billType || !reference || !amount || insufficient ? "not-allowed" : "pointer", marginBottom: "24px" }}>
        Next
      </button>

      {/* Bill history */}
      <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Payment history</p>
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", overflow: "hidden" }}>
        {historyLoading ? (
          <div style={{ padding: "24px", textAlign: "center" }}><p style={{ color: "#aaa", fontSize: "13px" }}>Loading...</p></div>
        ) : history.length === 0 ? (
          <div style={{ padding: "24px", textAlign: "center" }}>
            <p style={{ fontSize: "24px", marginBottom: "8px" }}>🧾</p>
            <p style={{ color: "#aaa", fontSize: "13px" }}>No bill payments yet</p>
          </div>
        ) : history.map((h, i) => {
          const bill = BILL_TYPES.find((b) => b.value === h.bill_type);
          return (
            <div key={h.id} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderBottom: i < history.length - 1 ? "1px solid #F5F5F5" : "none" }}>
              <div style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: h.status === "success" ? "#F0FDF4" : "#FEF2F2", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px", flexShrink: 0 }}>
                {bill?.icon ?? "🧾"}
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>{bill?.label ?? h.bill_type}</p>
                <p style={{ fontSize: "12px", color: "#aaa" }}>{h.bill_reference} · {timeAgo(h.paid_at)}</p>
              </div>
              <div style={{ textAlign: "right" }}>
                <p style={{ fontSize: "14px", fontWeight: "700", color: h.status === "success" ? "#000" : "#EF4444" }}>
                  -{h.currency === "USD" ? `$${Number(h.amount).toFixed(2)}` : `${Number(h.amount).toLocaleString()} ل.ل`}
                </p>
                <p style={{ fontSize: "11px", color: h.status === "success" ? "#00C853" : "#EF4444", fontWeight: "600" }}>
                  {h.status === "success" ? "Paid" : "Failed"}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Wrap>
  );
}