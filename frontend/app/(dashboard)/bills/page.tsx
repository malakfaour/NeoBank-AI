"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Droplets,
  Phone,
  ReceiptText,
  Smartphone,
  Zap,
} from "lucide-react";
import api from "@/lib/axios";

interface Wallet { id?: number; currency: string; balance: number; account_number: string | null; iban: string | null; }
interface BillHistoryItem {
  id: number; bill_type: string; bill_reference: string;
  amount: number; currency: string; status: string;
  biller_error: string | null; paid_at: string;
}

type Step = "form" | "confirm" | "receipt";

const BILL_TYPES = [
  { value: "ogero", label: "Ogero", Icon: Phone, desc: "Internet & telephone" },
  { value: "edl", label: "EDL", Icon: Zap, desc: "Electricity" },
  { value: "water", label: "Water", Icon: Droplets, desc: "Water authority" },
  { value: "mobile_topup", label: "Mobile Top-up", Icon: Smartphone, desc: "Recharge mobile" },
];

const Wrap = ({ children }: { children: React.ReactNode }) => (
  <div className="bank-feature-page bills-page">{children}</div>
);

const Header = ({ title, onBack }: { title: string; onBack: () => void }) => (
  <div className="transfer-page-header">
    <button className="transfer-back-button" onClick={onBack} aria-label="Go back"><ArrowLeft size={18} /></button>
    <h2>{title}</h2>
  </div>
);

function timeAgo(d: string) {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatAmount(currency: string | undefined, value: number) {
  return currency === "USD" ? `$${value.toFixed(2)}` : `${value.toLocaleString()} LBP`;
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
      const balances = r.data.balances ?? [];
      setWallets(balances);
      if (balances.length > 0) setSelectedWallet(balances[0]);
    }).catch(() => {});
    api.get("/bills/history").then((r) => setHistory(r.data.items ?? []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false));
  }, []);

  const handlePay = async () => {
    if (!selectedWallet?.id || !billType || !reference || !amount) return;
    setLoading(true);
    setError("");
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
      } else setError(typeof detail === "string" ? detail : "Payment failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const selectedBill = BILL_TYPES.find((bill) => bill.value === billType);
  const balance = selectedWallet?.balance ?? 0;
  const amountNum = parseFloat(amount) || 0;
  const insufficient = amountNum > balance;
  const cannotContinue = !billType || !reference || !amount || insufficient || amountNum <= 0;

  const goBack = () => {
    if (step === "form") router.back();
    else setStep("form");
  };

  if (step === "confirm") return (
    <Wrap>
      <Header title="Confirm Payment" onBack={goBack} />
      <section className="bill-summary-panel">
        <div className="bill-summary-heading"><span><ReceiptText size={22} /></span><div><h3>Review your payment</h3><p>Check the bill details before confirming.</p></div></div>
        <div className="bill-summary-rows">
          {[
            { label: "Bill type", value: selectedBill?.label ?? "" },
            { label: "Reference", value: reference },
            { label: "From", value: selectedWallet?.currency === "USD" ? "Fresh USD" : "Cash LBP" },
            { label: "Amount", value: formatAmount(selectedWallet?.currency, amountNum) },
          ].map(({ label, value }) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
        {error && <p className="bill-error"><AlertTriangle size={16} />{error}</p>}
        <button className="bill-primary-button" onClick={handlePay} disabled={loading}>
          {loading ? "Processing..." : "Confirm Payment"}<ArrowRight size={18} />
        </button>
      </section>
    </Wrap>
  );

  if (step === "receipt") return (
    <Wrap>
      <section className="bill-receipt-panel">
        <div className="transfer-success-icon"><CheckCircle2 size={34} /></div>
        <h2>Payment Successful</h2>
        <p>Your bill was paid securely.</p>
        <div className="bill-summary-rows">
          {[
            { label: "Bill", value: selectedBill?.label ?? "" },
            { label: "Reference", value: reference },
            { label: "Amount", value: formatAmount(selectedWallet?.currency, amountNum) },
            { label: "Payment ID", value: String(receipt?.bill_payment_id ?? "—") },
          ].map(({ label, value }) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
        <button className="bill-primary-button" onClick={() => router.push("/dashboard")}>Back to Dashboard<ArrowRight size={18} /></button>
      </section>
    </Wrap>
  );

  return (
    <Wrap>
      <Header title="Pay Bills" onBack={goBack} />
      <section className="bill-payment-panel">
        <div className="bill-section-heading"><div><h3>Select bill type</h3><p>Choose the service you want to pay.</p></div><ReceiptText size={22} /></div>
        <div className="bill-type-grid">
          {BILL_TYPES.map(({ value, label, Icon, desc }) => (
            <button className={`bill-type-card${billType === value ? " is-selected" : ""}`} key={value} onClick={() => setBillType(value)}>
              <span><Icon size={22} /></span><strong>{label}</strong><small>{desc}</small>
              {billType === value && <CheckCircle2 className="bill-type-check" size={18} />}
            </button>
          ))}
        </div>

        <div className="bill-form-grid">
          <label className="bill-field bill-field--wide"><span>Reference number</span><input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Bill reference or account number" /></label>
          <div className="bill-field bill-field--wide"><span>Pay from</span><div className="bill-wallet-grid">
            {wallets.map((wallet) => (
              <button className={`bill-wallet-option${selectedWallet?.currency === wallet.currency ? " is-selected" : ""}`} key={wallet.currency} onClick={() => setSelectedWallet(wallet)}>
                <span>{wallet.currency}</span><div><small>{wallet.currency === "USD" ? "Fresh USD" : "Cash LBP"}</small><strong>{formatAmount(wallet.currency, wallet.balance)}</strong></div>
                {selectedWallet?.currency === wallet.currency && <CheckCircle2 size={18} />}
              </button>
            ))}
          </div></div>
          <label className="bill-field bill-field--wide"><span>Amount ({selectedWallet?.currency})</span><input className={insufficient ? "has-error" : ""} type="number" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }} placeholder="0.00" />
            {insufficient && <small className="bill-inline-error"><AlertTriangle size={14} />Insufficient balance</small>}
          </label>
        </div>
        {error && <p className="bill-error"><AlertTriangle size={16} />{error}</p>}
        <button className="bill-primary-button" onClick={() => setStep("confirm")} disabled={cannotContinue}>Continue<ArrowRight size={18} /></button>
      </section>

      <section className="bill-history-section">
        <div className="bill-history-heading"><div><h3>Payment history</h3><p>Your recent bill payments.</p></div><span>{history.length} payments</span></div>
        <div className="bill-history-card">
          {historyLoading ? <div className="bill-history-empty">Loading payments...</div> : history.length === 0 ? (
            <div className="bill-history-empty"><span><ReceiptText size={23} /></span><strong>No bill payments yet</strong><p>Your completed payments will appear here.</p></div>
          ) : history.map((item) => {
            const bill = BILL_TYPES.find((entry) => entry.value === item.bill_type);
            const Icon = bill?.Icon ?? ReceiptText;
            return <div className="bill-history-row" key={item.id}>
              <span className="bill-history-icon"><Icon size={20} /></span>
              <div><strong>{bill?.label ?? item.bill_type}</strong><small>{item.bill_reference} · {timeAgo(item.paid_at)}</small></div>
              <div className="bill-history-amount"><strong>-{formatAmount(item.currency, Number(item.amount))}</strong><small className={item.status === "success" ? "is-paid" : "is-failed"}>{item.status === "success" ? "Paid" : "Failed"}</small></div>
            </div>;
          })}
        </div>
      </section>
    </Wrap>
  );
}
