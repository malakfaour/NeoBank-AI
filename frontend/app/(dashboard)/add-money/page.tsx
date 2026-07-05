"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface Wallet { id?: number; currency: string; balance: number; account_number: string | null; iban: string | null; }
type Step = "account" | "card" | "confirm" | "receipt";

const Wrap = ({ children }: { children: React.ReactNode }) => (
  <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>{children}</div>
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

export default function AddMoneyPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("account");
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selected, setSelected] = useState<Wallet | null>(null);
  const [card, setCard] = useState({ number: "", expiry: "", cvv: "" });
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [newBalance, setNewBalance] = useState<number | null>(null);

  useEffect(() => {
    api.get("/accounts/balance").then((r) => {
      const b = r.data.balances ?? [];
      setWallets(b);
      if (b.length > 0) setSelected(b[0]);
    }).catch(() => {});
  }, []);

  const formatCard = (val: string) =>
    val.replace(/\D/g, "").slice(0, 16).replace(/(.{4})/g, "$1 ").trim();

  const formatExpiry = (val: string) => {
    const digits = val.replace(/\D/g, "").slice(0, 4);
    return digits.length >= 3 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits;
  };

  const handleTopUp = async () => {
    if (!selected) return;
    setLoading(true);
    setError("");
    try {
      const token = `tok_test_${card.number.replace(/\s/g, "").slice(-4)}`;
      const res = await api.post("/accounts/top-up", {
        wallet_id: selected.id,
        amount: parseFloat(amount),
        card_token: token,
      });
      setNewBalance(res.data.new_balance);
      setStep("receipt");
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Top-up failed.";
      setError(msg);
    } finally { setLoading(false); }
  };

  const goBack = () => {
    if (step === "account") router.back();
    else if (step === "card") setStep("account");
    else if (step === "confirm") setStep("card");
  };

  if (step === "account") return (
    <Wrap>
      <Header title="Add Money" onBack={goBack} />
      <p style={{ color: "#aaa", fontSize: "13px", marginBottom: "12px" }}>Top up to</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "24px" }}>
        {wallets.map((w) => (
          <button key={w.currency} onClick={() => setSelected(w)}
            style={{ backgroundColor: "#fff", border: `2px solid ${selected?.currency === w.currency ? "#00C853" : "#F0F0F0"}`, borderRadius: "16px", padding: "16px", textAlign: "left", cursor: "pointer" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ backgroundColor: "#00C853", color: "#fff", fontSize: "10px", fontWeight: "700", padding: "2px 8px", borderRadius: "6px", marginRight: "8px" }}>{w.currency}</span>
                <span style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{w.currency === "USD" ? "Fresh USD" : "Cash LBP"}</span>
              </div>
              <span style={{ fontSize: "16px", fontWeight: "700", color: "#000" }}>
                {w.currency === "USD" ? `$${w.balance.toFixed(2)}` : `${w.balance.toLocaleString()} ل.ل`}
              </span>
            </div>
          </button>
        ))}
      </div>
      <button onClick={() => setStep("card")} disabled={!selected}
        style={{ width: "100%", backgroundColor: selected ? "#00C853" : "#E5E7EB", color: selected ? "#fff" : "#999", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: selected ? "pointer" : "not-allowed" }}>
        Next
      </button>
    </Wrap>
  );

  if (step === "card") return (
    <Wrap>
      <Header title="Card Details" onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Card number</label>
          <input value={card.number} onChange={(e) => setCard({ ...card, number: formatCard(e.target.value) })}
            placeholder="0000 0000 0000 0000" maxLength={19}
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
        </div>
        <div style={{ display: "flex", gap: "12px" }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Expiry</label>
            <input value={card.expiry} onChange={(e) => setCard({ ...card, expiry: formatExpiry(e.target.value) })}
              placeholder="MM/YY" maxLength={5}
              style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>CVV</label>
            <input value={card.cvv} onChange={(e) => setCard({ ...card, cvv: e.target.value.replace(/\D/g, "").slice(0, 3) })}
              placeholder="•••" maxLength={3} type="password"
              style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
          </div>
        </div>
        <div>
          <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Amount ({selected?.currency})</label>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number" placeholder="0.00"
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box" }} />
        </div>
      </div>
      <button onClick={() => setStep("confirm")} disabled={card.number.length < 19 || card.expiry.length < 5 || card.cvv.length < 3 || !amount}
        style={{ width: "100%", backgroundColor: "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
        Next
      </button>
    </Wrap>
  );

  if (step === "confirm") return (
    <Wrap>
      <Header title="Confirm Top-Up" onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: "To", value: `${selected?.currency === "USD" ? "Fresh USD" : "Cash LBP"} wallet` },
          { label: "Amount", value: `${selected?.currency === "USD" ? `$${parseFloat(amount).toFixed(2)}` : `${parseFloat(amount).toLocaleString()} ل.ل`}` },
          { label: "Card", value: `•••• ${card.number.replace(/\s/g, "").slice(-4)}` },
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
        {loading ? "Processing..." : "Confirm Top-Up"}
      </button>
    </Wrap>
  );

  return (
    <Wrap>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", paddingTop: "40px" }}>
        <div style={{ width: "72px", height: "72px", borderRadius: "50%", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "32px" }}>✅</div>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>Top-Up Successful!</h2>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "Wallet", value: `${selected?.currency === "USD" ? "Fresh USD" : "Cash LBP"}` },
            { label: "Amount added", value: `${selected?.currency === "USD" ? `$${parseFloat(amount).toFixed(2)}` : `${parseFloat(amount).toLocaleString()} ل.ل`}` },
            { label: "New balance", value: `${selected?.currency === "USD" ? `$${newBalance?.toFixed(2)}` : `${newBalance?.toLocaleString()} ل.ل`}` },
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
}