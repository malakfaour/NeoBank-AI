"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Elements,
  CardElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import type { StripeCardElementChangeEvent } from "@stripe/stripe-js";
import api from "@/lib/axios";
import { getStripe } from "@/lib/stripe";
import KYCActionLock from "@/components/kyc/KYCActionLock";
import { useAuthStore } from "@/store/authStore";
import { ArrowRight, CheckCircle2, WalletCards } from "lucide-react";
import { usePreferences } from "@/components/providers/AppPreferences";

interface Wallet { id?: number; currency: string; balance: number; account_number: string | null; iban: string | null; }
type Step = "account" | "card" | "confirm" | "receipt";

const WALLET_LABELS: Record<string, string> = { USD: "Fresh USD", LBP: "Cash LBP", USDT: "USDT" };
const walletLabel = (currency?: string) => (currency && WALLET_LABELS[currency]) || currency || "";
const formatAmount = (currency: string | undefined, value: number) => {
  if (currency === "USD") return `$${value.toFixed(2)}`;
  if (currency === "LBP") return `${value.toLocaleString()} LBP`;
  return `${value.toLocaleString()} ${currency ?? ""}`;
};

const Wrap = ({ children }: { children: React.ReactNode }) => (
  <div className="bank-feature-page add-money-page" style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>{children}</div>
);

const Header = ({ title, onBack }: { title: string; onBack: () => void }) => (
  <div className="transfer-page-header" style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
    <button className="transfer-back-button" onClick={onBack}
      style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>{title}</h2>
  </div>
);

const cardElementOptions = {
  style: {
    base: {
      fontSize: "14px",
      color: "#000",
      "::placeholder": { color: "#999" },
    },
    invalid: { color: "#EF4444" },
  },
};

// DEVATTECH-131: this component (rather than the default export) holds all
// the actual form state and logic, because useStripe()/useElements() only
// work inside the <Elements> provider tree -- see the default export below.
function AddMoneyForm() {
  const user = useAuthStore((state) => state.user);
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const router = useRouter();
  const stripe = useStripe();
  const elements = useElements();

  const [step, setStep] = useState<Step>("account");
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selected, setSelected] = useState<Wallet | null>(null);
  const [amount, setAmount] = useState("");
  const [cardComplete, setCardComplete] = useState(false);
  const [tokenizing, setTokenizing] = useState(false);
  const [paymentMethodId, setPaymentMethodId] = useState<string | null>(null);
  const [cardLast4, setCardLast4] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [newBalance, setNewBalance] = useState<number | null>(null);
  // DEVATTECH-125: one idempotency key per user submission attempt.
  // useRef (not useState) deliberately -- this value must persist across
  // a retry of the SAME attempt (e.g. handleTopUp called again after a
  // transient error while still on the confirm step) without triggering
  // a re-render, and must NOT survive into a genuinely new attempt.
  const idempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    api.get("/accounts/balance").then((r) => {
      const b = r.data.balances ?? [];
      setWallets(b);
      if (b.length > 0) setSelected(b[0]);
      if (b.length === 0) setError("No wallets found. Please contact support.");
    }).catch(() => setError("Could not load wallets. Please try again."));
  }, []);

  const handleCardElementChange = (event: StripeCardElementChangeEvent) => {
    setCardComplete(event.complete);
    setError(event.error?.message ?? "");
  };

  // DEVATTECH-131: card data itself never reaches our backend. Stripe.js
  // tokenizes it directly in the browser and hands back a payment_method_id
  // (e.g. "pm_1Nx...") -- that's the only thing POST /accounts/top-up ever
  // sees now.
  const handleTokenizeCard = async () => {
    if (!stripe || !elements) {
      setError("Payment form is still loading. Try again in a moment.");
      return;
    }
    const cardElement = elements.getElement(CardElement);
    if (!cardElement || !cardComplete) return;

    setTokenizing(true);
    setError("");
    try {
      const { paymentMethod, error: stripeError } = await stripe.createPaymentMethod({
        type: "card",
        card: cardElement,
      });
      if (stripeError || !paymentMethod) {
        setError(stripeError?.message ?? "Card validation failed.");
        return;
      }
      setPaymentMethodId(paymentMethod.id);
      setCardLast4(paymentMethod.card?.last4 ?? "");
      setStep("confirm");
    } finally {
      setTokenizing(false);
    }
  };

 
 // Shared between the initial /accounts/top-up call and the
  // post-3DS-challenge /accounts/top-up/confirm call -- both can fail
  // with the same error shapes (card_declined, wallet_frozen, etc.).
  const applyTopUpError = (e: unknown) => {
    const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    if (detail && typeof detail === "object") {
      const d = detail as { error?: string; gateway_message?: string };
      if (d.error === "wallet_frozen") setError("Your wallet is frozen. Please contact support.");
      else if (d.error === "wallet_closed") setError("Your wallet is closed. Please contact support.");
      else if (d.error === "card_declined") setError(d.gateway_message ?? "Your card was declined.");
      else setError(JSON.stringify(d));
    } else {
      setError(typeof detail === "string" ? detail : "Top-up failed.");
    }
  };

  const handleTopUp = async () => {
    if (!selected || !paymentMethodId) return;
    setLoading(true);
    setError("");
    // DEVATTECH-125: generate the key only once per attempt -- a retry
    // (this function called again while idempotencyKeyRef.current is
    // still set, e.g. after a transient failure) reuses the same key
    // rather than generating a new one, so the backend can recognize it
    // as the same logical submission.
    if (!idempotencyKeyRef.current) {
      idempotencyKeyRef.current = crypto.randomUUID();
    }
    try {
      const res = await api.post(
        "/accounts/top-up",
        {
          wallet_id: selected.id,
          amount: parseFloat(amount),
          payment_method_id: paymentMethodId,
        },
        {
          headers: { "X-Idempotency-Key": idempotencyKeyRef.current },
        },
      );

      if (res.data.status === "requires_action") {
        // 3D Secure: the wallet has NOT been credited yet. Run the
        // challenge in-page via Stripe.js, then ask the backend to
        // verify and finalize -- the backend independently re-checks
        // with Stripe rather than trusting this client's outcome.
        if (!stripe) {
          setError("Payment form is still loading. Try again in a moment.");
          return;
        }
        const { paymentIntent, error: confirmError } = await stripe.confirmCardPayment(
          res.data.client_secret,
        );
        if (confirmError || paymentIntent?.status !== "succeeded") {
          setError(confirmError?.message ?? "Card authentication failed.");
          return;
        }

        const confirmRes = await api.post(
          "/accounts/top-up/confirm",
          {
            wallet_id: selected.id,
            amount: parseFloat(amount),
            payment_intent_id: res.data.payment_intent_id,
          },
          {
            headers: { "X-Idempotency-Key": idempotencyKeyRef.current },
          },
        );
        setNewBalance(Number(confirmRes.data.new_balance));
        idempotencyKeyRef.current = null;
        setStep("receipt");
        return;
      }

      setNewBalance(Number(res.data.new_balance));
      // Success -- this attempt is complete; a future top-up must get a
      // fresh key, not reuse this one.
      idempotencyKeyRef.current = null;
      setStep("receipt");
    } catch (e: unknown) {
      applyTopUpError(e);
    } finally { setLoading(false); }
  };
 

  const goBack = () => {
    // DEVATTECH-125: going back abandons the in-progress attempt (if
    // any) -- a later top-up must get a fresh key, not resume a stale
    // one from a submission the user backed out of.
    idempotencyKeyRef.current = null;
    if (step === "account") router.back();
    else if (step === "card") setStep("account");
    else if (step === "confirm") {
      setPaymentMethodId(null);
      setCardLast4("");
      setStep("card");
    }
  };

  if (user?.kyc_status !== "approved") return <KYCActionLock action="Top Ups" />;

  if (step === "account") return (
    <Wrap>
      <Header title={tr("Add Money", "إضافة أموال")} onBack={goBack} />
      <section className="transfer-account-panel">
        <div className="transfer-account-heading">
          <span><WalletCards size={22} /></span>
          <div><h3>{tr("Choose a wallet", "اختر المحفظة")}</h3><p>{tr("Select where you want to add funds.", "اختر المحفظة التي تريد إضافة الأموال إليها.")}</p></div>
        </div>
        <div className="transfer-wallet-grid">
        {wallets.map((w) => (
          <button className={`transfer-wallet-card${selected?.currency === w.currency ? " is-selected" : ""}`} key={w.currency} onClick={() => setSelected(w)}>
            <div className="transfer-wallet-card__top">
              <span className="transfer-wallet-currency">{w.currency}</span>
              {selected?.currency === w.currency && <CheckCircle2 size={19} />}
            </div>
            <p>{walletLabel(w.currency)}</p>
            <strong>{formatAmount(w.currency, w.balance)}</strong>
            <small>{tr("Current balance", "الرصيد الحالي")}</small>
          </button>
        ))}
        </div>
        <div className="transfer-account-footer">
          <div><small>{tr("Adding money to", "إضافة الأموال إلى")}</small><strong>{selected ? walletLabel(selected.currency) : tr("Select a wallet", "اختر محفظة")}</strong></div>
          <button className="transfer-continue-button" onClick={() => setStep("card")} disabled={!selected}>{tr("Continue", "متابعة")} <ArrowRight size={18} /></button>
        </div>
      </section>
    </Wrap>
  );

  if (step === "card") return (
    <Wrap>
      <Header title={tr("Card Details", "بيانات البطاقة")} onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>{tr("Card details", "بيانات البطاقة")}</label>
          <div style={{ border: `1.5px solid ${error ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "14px 16px" }}>
            <CardElement options={cardElementOptions} onChange={handleCardElementChange} />
          </div>
          <p style={{ color: "#aaa", fontSize: "11px", marginTop: "6px" }}>
            {tr("In test mode, use 4242 4242 4242 4242, any future expiry, any CVC.", "في وضع الاختبار، استخدم 4242 4242 4242 4242 مع أي تاريخ صلاحية ورمز CVC.")}
          </p>
        </div>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>{tr("Amount", "المبلغ")} ({selected?.currency})</label>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number" placeholder="0.00"
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
        </div>
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={handleTokenizeCard} disabled={!cardComplete || !amount || tokenizing || !stripe}
        style={{ width: "100%", backgroundColor: !cardComplete || !amount || tokenizing ? "#E5E7EB" : "#00C853", color: !cardComplete || !amount || tokenizing ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: !cardComplete || !amount || tokenizing ? "not-allowed" : "pointer" }}>
        {tokenizing ? tr("Validating card...", "جارٍ التحقق من البطاقة...") : tr("Next", "التالي")}
      </button>
    </Wrap>
  );

  if (step === "confirm") return (
    <Wrap>
      <Header title={tr("Confirm Top-Up", "تأكيد إضافة الأموال")} onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: "To", value: `${walletLabel(selected?.currency)} wallet` },
          { label: "Amount", value: formatAmount(selected?.currency, parseFloat(amount)) },
          { label: "Card", value: cardLast4 ? `Card ending in ${cardLast4}` : "Card on file" },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={handleTopUp} disabled={loading}
        style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: loading ? "not-allowed" : "pointer" }}>
        {loading ? tr("Processing...", "جارٍ تنفيذ العملية...") : tr("Confirm Top-Up", "تأكيد إضافة الأموال")}
      </button>
    </Wrap>
  );

  return (
    <Wrap>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", paddingTop: "40px" }}>
        <div className="transfer-success-icon"><CheckCircle2 size={34} /></div>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>{tr("Top-Up Successful!", "تمت إضافة الأموال بنجاح")}</h2>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "Wallet", value: walletLabel(selected?.currency) },
            { label: "Amount added", value: formatAmount(selected?.currency, parseFloat(amount)) },
            { label: "New balance", value: newBalance != null ? formatAmount(selected?.currency, newBalance) : "" },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
              <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
            </div>
          ))}
        </div>
        <button onClick={() => router.push("/dashboard")}
          style={{ width: "100%", backgroundColor: "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
          {tr("Back to Dashboard", "العودة إلى الرئيسية")}
        </button>
      </div>
    </Wrap>
  );
}

export default function AddMoneyPage() {
  return (
    <Elements stripe={getStripe()}>
      <AddMoneyForm />
    </Elements>
  );
}
