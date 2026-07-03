"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface Wallet { currency: string; balance: number; account_number: string | null; iban: string | null; }
interface Beneficiary { id: number; nickname: string; type: string; value: string; }
interface RecipientInfo { exists: boolean; display_name: string | null; kyc_approved: boolean; }

type Step = "account" | "type" | "recipient" | "amount" | "confirm" | "receipt";
type TransferType = "mobile" | "iban" | "own" | "bank";
type Tab = "mobile" | "iban";

export default function TransferPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("account");
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null);
  const [transferType, setTransferType] = useState<TransferType | null>(null);
  const [tab, setTab] = useState<Tab>("mobile");
  const [phone, setPhone] = useState("");
  const [iban, setIban] = useState("");
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [search, setSearch] = useState("");
  const [recipient, setRecipient] = useState<RecipientInfo | null>(null);
  const [recipientValue, setRecipientValue] = useState("");
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.get("/accounts/balance").then((r) => {
      const b = r.data.balances ?? [];
      setWallets(b);
      if (b.length > 0) setSelectedWallet(b[0]);
    }).catch(() => {});
    api.get("/beneficiaries").then((r) => setBeneficiaries(r.data ?? [])).catch(() => {});
  }, []);

  const validateRecipient = async () => {
    setValidating(true); setError(""); setRecipient(null);
    const val = tab === "mobile" ? `+961${phone.replace(/^0/, "")}` : iban;
    const param = tab === "mobile" ? `phone=${encodeURIComponent(val)}` : `iban=${encodeURIComponent(val)}`;
    try {
      const r = await api.get(`/accounts/validate-recipient?${param}`);
      setRecipient(r.data);
      setRecipientValue(val);
      if (!r.data.exists) setError("Recipient not found in NeoBank.");
      else if (!r.data.kyc_approved) setError("Recipient has not completed KYC.");
    } catch { setError("Could not validate recipient."); }
    finally { setValidating(false); }
  };

  const handleSubmit = async () => {
    if (!selectedWallet || !recipientValue || !amount) return;
    setLoading(true); setError("");
    try {
      const endpoint = tab === "mobile" ? "/transfer/neo/mobile" : "/transfer/neo/iban";
      const body = tab === "mobile"
        ? { phone: recipientValue, amount: parseFloat(amount), currency: selectedWallet.currency }
        : { iban: recipientValue, amount: parseFloat(amount), currency: selectedWallet.currency };
      const r = await api.post(endpoint, body);
      setReceipt(r.data);
      setStep("receipt");
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Transfer failed.";
      setError(msg);
    } finally { setLoading(false); }
  };

  const balance = selectedWallet?.balance ?? 0;
  const amountNum = parseFloat(amount) || 0;
  const insufficient = amountNum > balance;

  const filteredBeneficiaries = beneficiaries.filter((b) =>
    (tab === "mobile" ? b.type === "mobile" : b.type === "iban") &&
    (b.nickname.toLowerCase().includes(search.toLowerCase()) || b.value.includes(search))
  );

  const Header = ({ title }: { title: string }) => (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
      <button onClick={() => step === "account" ? router.back() : setStep(step === "type" ? "account" : step === "recipient" ? "type" : step === "amount" ? "recipient" : step === "confirm" ? "amount" : "account")}
        style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </button>
      <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>{title}</h2>
    </div>
  );

  const Wrap = ({ children }: { children: React.ReactNode }) => (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>{children}</div>
  );

  if (step === "account") return (
    <Wrap>
      <Header title="Transfer Money" />
      <p style={{ color: "#aaa", fontSize: "13px", marginBottom: "12px" }}>From Account</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "24px" }}>
        {wallets.map((w) => (
          <button key={w.currency} onClick={() => setSelectedWallet(w)}
            style={{ backgroundColor: "#fff", border: `2px solid ${selectedWallet?.currency === w.currency ? "#00C853" : "#F0F0F0"}`, borderRadius: "16px", padding: "16px", textAlign: "left", cursor: "pointer" }}>
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
      <button onClick={() => setStep("type")} disabled={!selectedWallet}
        style={{ width: "100%", backgroundColor: selectedWallet ? "#00C853" : "#E5E7EB", color: selectedWallet ? "#fff" : "#999", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: selectedWallet ? "pointer" : "not-allowed" }}>
        Next
      </button>
    </Wrap>
  );

  if (step === "type") return (
    <Wrap>
      <Header title="Transfer Type" />
      <p style={{ color: "#aaa", fontSize: "13px", marginBottom: "12px" }}>Select which transfer you'd like to do</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {[
          { type: "mobile" as TransferType, label: "Within Neo", sub: "Via Mobile Number or IBAN", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" stroke="#333" strokeWidth="2" strokeLinecap="round"/></svg> },
          { type: "own" as TransferType, label: "To my other accounts", sub: "Between your accounts", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" stroke="#333" strokeWidth="2" strokeLinecap="round"/></svg> },
          { type: "bank" as TransferType, label: "To Bank", sub: "Coming soon", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M3 21h18M3 10h18M5 6l7-3 7 3M4 10v11M8 10v11M12 10v11M16 10v11M20 10v11" stroke="#ccc" strokeWidth="2" strokeLinecap="round"/></svg> },
        ].map(({ type, label, sub, icon }) => (
          <button key={type} onClick={() => { if (type === "bank") return; setTransferType(type); setStep("recipient"); }}
            style={{ backgroundColor: "#fff", border: `2px solid ${transferType === type ? "#00C853" : "#F0F0F0"}`, borderRadius: "16px", padding: "16px", textAlign: "left", cursor: type === "bank" ? "not-allowed" : "pointer", opacity: type === "bank" ? 0.5 : 1, display: "flex", alignItems: "center", gap: "14px" }}>
            {icon}
            <div>
              <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{label}</p>
              <p style={{ fontSize: "12px", color: "#aaa" }}>{sub}</p>
            </div>
          </button>
        ))}
      </div>
    </Wrap>
  );

  if (step === "recipient") return (
    <Wrap>
      <Header title="Transfer to?" />
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        {(["mobile", "iban"] as Tab[]).map((t) => (
          <button key={t} onClick={() => { setTab(t); setRecipient(null); setError(""); setPhone(""); setIban(""); }}
            style={{ flex: 1, padding: "10px", borderRadius: "12px", border: "none", backgroundColor: tab === t ? "#00C853" : "#F0F0F0", color: tab === t ? "#fff" : "#666", fontWeight: "600", fontSize: "13px", cursor: "pointer" }}>
            {t === "mobile" ? "Mobile Number" : "IBAN"}
          </button>
        ))}
      </div>

      {tab === "mobile" ? (
        <div style={{ marginBottom: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", gap: "10px", backgroundColor: "#fff" }}>
            <span style={{ fontSize: "13px", color: "#666", whiteSpace: "nowrap" }}>🇱🇧 +961</span>
            <div style={{ width: "1px", height: "16px", backgroundColor: "#E5E7EB" }} />
            <input type="tel" placeholder="70 123 456" value={phone} onChange={(e) => { setPhone(e.target.value); setRecipient(null); setError(""); }}
              style={{ flex: 1, border: "none", outline: "none", fontSize: "14px", color: "#000", backgroundColor: "transparent" }} />
          </div>
        </div>
      ) : (
        <div style={{ marginBottom: "16px" }}>
          <input type="text" placeholder="LB00 0000 0000 0000 0000 0000 00" value={iban} onChange={(e) => { setIban(e.target.value); setRecipient(null); setError(""); }}
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
        </div>
      )}

      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      {recipient?.exists && recipient.kyc_approved && (
        <div style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "12px", padding: "12px 16px", marginBottom: "16px" }}>
          <p style={{ color: "#166534", fontSize: "13px", fontWeight: "600" }}>✓ Sending to: {recipient.display_name}</p>
        </div>
      )}

      <button onClick={validateRecipient} disabled={validating || (tab === "mobile" ? phone.length < 7 : iban.length < 10)}
        style={{ width: "100%", backgroundColor: "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer", marginBottom: "20px" }}>
        {validating ? "Checking..." : "Validate"}
      </button>

      {recipient?.exists && recipient.kyc_approved && (
        <button onClick={() => setStep("amount")}
          style={{ width: "100%", backgroundColor: "#000", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
          Next
        </button>
      )}

      {filteredBeneficiaries.length > 0 && (
        <div style={{ marginTop: "20px" }}>
          <input placeholder="Search saved beneficiaries..." value={search} onChange={(e) => setSearch(e.target.value)}
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box", marginBottom: "12px" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {filteredBeneficiaries.map((b) => (
              <button key={b.id} onClick={() => { tab === "mobile" ? setPhone(b.value.replace("+961", "")) : setIban(b.value); setRecipient(null); setError(""); }}
                style={{ backgroundColor: "#fff", border: "1px solid #F0F0F0", borderRadius: "14px", padding: "12px 16px", textAlign: "left", cursor: "pointer" }}>
                <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{b.nickname}</p>
                <p style={{ fontSize: "12px", color: "#aaa" }}>{b.value}</p>
              </button>
            ))}
          </div>
        </div>
      )}
    </Wrap>
  );

  if (step === "amount") return (
    <Wrap>
      <Header title="Enter Amount" />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <p style={{ color: "#aaa", fontSize: "12px", marginBottom: "4px" }}>Sending to</p>
        <p style={{ fontSize: "15px", fontWeight: "600", color: "#000" }}>{recipient?.display_name ?? recipientValue}</p>
      </div>
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <p style={{ color: "#aaa", fontSize: "12px", marginBottom: "8px" }}>Amount ({selectedWallet?.currency})</p>
        <input type="number" placeholder="0.00" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }}
          style={{ width: "100%", border: "none", outline: "none", fontSize: "32px", fontWeight: "800", color: insufficient ? "#EF4444" : "#000", backgroundColor: "transparent", boxSizing: "border-box" }} />
        <p style={{ color: insufficient ? "#EF4444" : "#aaa", fontSize: "13px", marginTop: "8px" }}>
          Available: {selectedWallet?.currency === "USD" ? `$${balance.toFixed(2)}` : `${balance.toLocaleString()} ل.ل`}
        </p>
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={() => setStep("confirm")} disabled={!amount || insufficient || amountNum <= 0}
        style={{ width: "100%", backgroundColor: !amount || insufficient || amountNum <= 0 ? "#E5E7EB" : "#00C853", color: !amount || insufficient || amountNum <= 0 ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: !amount || insufficient || amountNum <= 0 ? "not-allowed" : "pointer" }}>
        Next
      </button>
    </Wrap>
  );

  if (step === "confirm") return (
    <Wrap>
      <Header title="Confirm Transfer" />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: "From", value: `${selectedWallet?.currency === "USD" ? "Fresh USD" : "Cash LBP"} — ${selectedWallet?.currency === "USD" ? `$${balance.toFixed(2)}` : `${balance.toLocaleString()} ل.ل`}` },
          { label: "To", value: recipient?.display_name ?? recipientValue },
          { label: "Amount", value: `${selectedWallet?.currency === "USD" ? `$${amountNum.toFixed(2)}` : `${amountNum.toLocaleString()} ل.ل`}` },
          { label: "Transfer type", value: tab === "mobile" ? "Via Mobile Number" : "Via IBAN" },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600", textAlign: "right", maxWidth: "60%" }}>{value}</p>
          </div>
        ))}
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={handleSubmit} disabled={loading}
        style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: loading ? "not-allowed" : "pointer" }}>
        {loading ? "Sending..." : "Confirm Transfer"}
      </button>
    </Wrap>
  );

  return (
    <Wrap>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", paddingTop: "40px" }}>
        <div style={{ width: "72px", height: "72px", borderRadius: "50%", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "32px" }}>✅</div>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>Transfer Sent!</h2>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "To", value: recipient?.display_name ?? recipientValue },
            { label: "Amount", value: `${selectedWallet?.currency === "USD" ? `$${amountNum.toFixed(2)}` : `${amountNum.toLocaleString()} ل.ل`}` },
            { label: "Transaction ID", value: String((receipt as { transaction_id?: unknown })?.transaction_id ?? "—") },
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
