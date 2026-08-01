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
import { usePreferences } from "@/components/providers/AppPreferences";

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
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const billLabel = (value: string, fallback: string) => value === "ogero" ? tr("Ogero", "أوجيرو") : value === "edl" ? tr("EDL", "كهرباء لبنان") : value === "water" ? tr("Water", "المياه") : value === "mobile_topup" ? tr("Mobile Top-up", "تعبئة الهاتف") : fallback;
  const billDescription = (value: string, fallback: string) => value === "ogero" ? tr("Internet & telephone", "الإنترنت والهاتف") : value === "edl" ? tr("Electricity", "فاتورة الكهرباء") : value === "water" ? tr("Water authority", "مؤسسة المياه") : value === "mobile_topup" ? tr("Recharge mobile", "إعادة تعبئة الرصيد") : fallback;
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
      <Header title={tr("Confirm Payment", "تأكيد الدفع")} onBack={goBack} />
      <section className="bill-summary-panel">
        <div className="bill-summary-heading"><span><ReceiptText size={22} /></span><div><h3>{tr("Review your payment", "مراجعة عملية الدفع")}</h3><p>{tr("Check the bill details before confirming.", "تحقق من تفاصيل الفاتورة قبل التأكيد.")}</p></div></div>
        <div className="bill-summary-rows">
          {[
            { label: tr("Bill type", "نوع الفاتورة"), value: selectedBill ? billLabel(selectedBill.value, selectedBill.label) : "" },
            { label: tr("Reference", "رقم المرجع"), value: reference },
            { label: tr("From", "من حساب"), value: selectedWallet?.currency === "USD" ? tr("Fresh USD", "دولار أميركي") : tr("Cash LBP", "ليرة لبنانية") },
            { label: tr("Amount", "المبلغ"), value: formatAmount(selectedWallet?.currency, amountNum) },
          ].map(({ label, value }) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
        {error && <p className="bill-error"><AlertTriangle size={16} />{error}</p>}
        <button className="bill-primary-button" onClick={handlePay} disabled={loading}>
          {loading ? tr("Processing...", "جارٍ تنفيذ العملية...") : tr("Confirm Payment", "تأكيد الدفع")}<ArrowRight size={18} />
        </button>
      </section>
    </Wrap>
  );

  if (step === "receipt") return (
    <Wrap>
      <section className="bill-receipt-panel">
        <div className="transfer-success-icon"><CheckCircle2 size={34} /></div>
        <h2>{tr("Payment Successful", "تم دفع الفاتورة بنجاح")}</h2>
        <p>{tr("Your bill was paid securely.", "تم دفع فاتورتك بأمان.")}</p>
        <div className="bill-summary-rows">
          {[
            { label: tr("Bill", "الفاتورة"), value: selectedBill ? billLabel(selectedBill.value, selectedBill.label) : "" },
            { label: "Reference", value: reference },
            { label: "Amount", value: formatAmount(selectedWallet?.currency, amountNum) },
            { label: "Payment ID", value: String(receipt?.bill_payment_id ?? "—") },
          ].map(({ label, value }) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
        <button className="bill-primary-button" onClick={() => router.push("/dashboard")}>{tr("Back to Dashboard", "العودة إلى الرئيسية")}<ArrowRight size={18} /></button>
      </section>
    </Wrap>
  );

  return (
    <Wrap>
      <Header title={tr("Pay Bills", "دفع الفواتير")} onBack={goBack} />
      <section className="bill-payment-panel">
        <div className="bill-section-heading"><div><h3>{tr("Select bill type", "اختر نوع الفاتورة")}</h3><p>{tr("Choose the service you want to pay.", "اختر الخدمة التي تريد دفعها.")}</p></div><ReceiptText size={22} /></div>
        <div className="bill-type-grid">
          {BILL_TYPES.map(({ value, label, Icon, desc }) => (
            <button className={`bill-type-card${billType === value ? " is-selected" : ""}`} key={value} onClick={() => setBillType(value)}>
              <span><Icon size={22} /></span><strong>{billLabel(value, label)}</strong><small>{billDescription(value, desc)}</small>
              {billType === value && <CheckCircle2 className="bill-type-check" size={18} />}
            </button>
          ))}
        </div>

        <div className="bill-form-grid">
          <label className="bill-field bill-field--wide"><span>{tr("Reference number", "رقم المرجع")}</span><input value={reference} onChange={(e) => setReference(e.target.value)} placeholder={tr("Bill reference or account number", "رقم الفاتورة أو الحساب")} /></label>
          <div className="bill-field bill-field--wide"><span>{tr("Pay from", "الدفع من")}</span><div className="bill-wallet-grid">
            {wallets.map((wallet) => (
              <button className={`bill-wallet-option${selectedWallet?.currency === wallet.currency ? " is-selected" : ""}`} key={wallet.currency} onClick={() => setSelectedWallet(wallet)}>
                <span>{wallet.currency}</span><div><small>{wallet.currency === "USD" ? "Fresh USD" : "Cash LBP"}</small><strong>{formatAmount(wallet.currency, wallet.balance)}</strong></div>
                {selectedWallet?.currency === wallet.currency && <CheckCircle2 size={18} />}
              </button>
            ))}
          </div></div>
          <label className="bill-field bill-field--wide"><span>{tr("Amount", "المبلغ")} ({selectedWallet?.currency})</span><input className={insufficient ? "has-error" : ""} type="number" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }} placeholder="0.00" />
            {insufficient && <small className="bill-inline-error"><AlertTriangle size={14} />{tr("Insufficient balance", "الرصيد غير كافٍ")}</small>}
          </label>
        </div>
        {error && <p className="bill-error"><AlertTriangle size={16} />{error}</p>}
        <button className="bill-primary-button" onClick={() => setStep("confirm")} disabled={cannotContinue}>{tr("Continue", "متابعة")}<ArrowRight size={18} /></button>
      </section>

      <section className="bill-history-section">
        <div className="bill-history-heading"><div><h3>{tr("Payment history", "سجل المدفوعات")}</h3><p>{tr("Your recent bill payments.", "أحدث مدفوعات الفواتير.")}</p></div><span>{history.length} {tr("payments", "دفعات")}</span></div>
        <div className="bill-history-card">
          {historyLoading ? <div className="bill-history-empty">Loading payments...</div> : history.length === 0 ? (
            <div className="bill-history-empty"><span><ReceiptText size={23} /></span><strong>{tr("No bill payments yet", "لا توجد مدفوعات بعد")}</strong><p>{tr("Your completed payments will appear here.", "ستظهر مدفوعاتك المكتملة هنا.")}</p></div>
          ) : history.map((item) => {
            const bill = BILL_TYPES.find((entry) => entry.value === item.bill_type);
            const Icon = bill?.Icon ?? ReceiptText;
            return <div className="bill-history-row" key={item.id}>
              <span className="bill-history-icon"><Icon size={20} /></span>
              <div><strong>{bill ? billLabel(bill.value, bill.label) : item.bill_type}</strong><small>{item.bill_reference} · {timeAgo(item.paid_at)}</small></div>
              <div className="bill-history-amount"><strong>-{formatAmount(item.currency, Number(item.amount))}</strong><small className={item.status === "success" ? "is-paid" : "is-failed"}>{item.status === "success" ? "Paid" : "Failed"}</small></div>
            </div>;
          })}
        </div>
      </section>
    </Wrap>
  );
}
