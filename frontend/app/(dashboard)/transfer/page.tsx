"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import KYCActionLock from "@/components/kyc/KYCActionLock";
import { useAuthStore } from "@/store/authStore";

interface Wallet { currency: string; balance: number; account_number: string | null; iban: string | null; }
interface Beneficiary { id: number; nickname: string; type: string; value: string; }
interface RecipientInfo { exists: boolean; display_name: string | null; kyc_approved: boolean; }

const OWN_ACCOUNT_CURRENCIES = new Set(["USD", "LBP"]);

function walletLabel(currency: string) {
  if (currency === "USD") return "Fresh USD";
  if (currency === "LBP") return "Cash LBP";
  return currency;
}

function formatMoney(value: number, currency: string) {
  if (currency === "USD") return `$${value.toFixed(2)}`;
  if (currency === "LBP") {
    return `${value.toLocaleString()} LBP`;
  }
  return `${value.toLocaleString()} ${currency}`;
}

type Step = "account" | "type" | "recipient" | "amount" | "passcode" | "confirm" | "receipt";
type TransferType = "mobile" | "iban" | "own" | "bank";
type Tab = "mobile" | "iban";

function Header({
  title, step, setStep, router,
}: {
  title: string; step: Step;
  setStep: (s: Step) => void;
  router: ReturnType<typeof useRouter>;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
      <button onClick={() => step === "account" ? router.back() : setStep(
        step === "type" ? "account" :
        step === "recipient" ? "type" :
        step === "amount" ? "recipient" :
        step === "passcode" ? "amount" :
        step === "confirm" ? "passcode" : "account"
      )}
        style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </button>
      <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>{title}</h2>
    </div>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px" }}>{children}</div>;
}

export default function TransferPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const [step, setStep] = useState<Step>("account");
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null);
  const [selectedDestinationWallet, setSelectedDestinationWallet] =
    useState<Wallet | null>(null);
  const [transferType, setTransferType] = useState<TransferType | null>(null);
  const [tab, setTab] = useState<Tab>("mobile");
  const [phone, setPhone] = useState("");
  const [iban, setIban] = useState("");
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [search, setSearch] = useState("");
  const [recipient, setRecipient] = useState<RecipientInfo | null>(null);
  const [recipientValue, setRecipientValue] = useState("");
  const [amount, setAmount] = useState("");
  const [passcode, setPasscode] = useState("");
  const [actionToken, setActionToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<Record<string, unknown> | null>(null);
  const [savedRecipient, setSavedRecipient] = useState(false);
  const [saveNickname, setSaveNickname] = useState("");
  const [skipSave, setSkipSave] = useState(false);

  useEffect(() => {
    api.get("/accounts/balance").then((r) => {
      const b = r.data.balances ?? [];
      setWallets(b);
      if (b.length > 0) setSelectedWallet(b[0]);
    }).catch(() => {});
    api.get("/beneficiaries").then((r) => {
  const data = r.data;
  setBeneficiaries(Array.isArray(data) ? data : data?.items ?? []);
}).catch(() => {});
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

  const handlePasscode = async () => {
    if (passcode.length < 6) return;
    setLoading(true); setError("");
    try {
      const res = await api.post("/auth/passcode/verify", { passcode });
      setActionToken(res.data.action_token);
      setStep("confirm");
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Incorrect passcode.";
      setError(typeof msg === "string" ? msg : "Incorrect passcode.");
    } finally { setLoading(false); }
  };

  const handleSubmit = async () => {
    if (!selectedWallet || !amount) return;
    if (transferType === "own" && !selectedDestinationWallet) return;
    if (transferType !== "own" && !recipientValue) return;

    setLoading(true);
    setError("");

    try {
      if (transferType === "own") {
        const response = await api.post(
          "/exchange/execute",
          {
            from_currency: selectedWallet.currency,
            to_currency: selectedDestinationWallet!.currency,
            amount: parseFloat(amount),
          },
          {
            headers: {
              "X-Action-Token": actionToken,
            },
          }
        );

        setReceipt(response.data);
      } else {
        const endpoint =
          tab === "mobile"
            ? "/transfer/neo/mobile"
            : "/transfer/neo/iban";

        const body =
          tab === "mobile"
            ? {
                receiver_phone: recipientValue,
                amount: parseFloat(amount),
                currency: selectedWallet.currency,
              }
            : {
                receiver_iban: recipientValue,
                amount: parseFloat(amount),
                currency: selectedWallet.currency,
              };

        const idempotencyKey =
          `${Date.now()}-${Math.random().toString(36).slice(2)}`;

        const response = await api.post(endpoint, body, {
          headers: {
            "X-Idempotency-Key": idempotencyKey,
            "X-Action-Token": actionToken,
          },
        });

        setReceipt(response.data);
      }

      setStep("receipt");
    } catch (e: unknown) {
      const detail = (
        e as {
          response?: {
            data?: {
              detail?: unknown;
            };
          };
        }
      )?.response?.data?.detail;

      if (detail && typeof detail === "object") {
        const parsed = detail as {
          error?: string;
          message?: string;
          available?: string;
          requested?: string;
          remaining?: string;
        };

        if (parsed.error === "insufficient_balance") {
          setError(
            `Insufficient balance. Available: ${parsed.available}, requested: ${parsed.requested}`
          );
        } else if (parsed.error === "daily_limit_exceeded") {
          setError(
            `Daily transfer limit reached. Remaining today: $${parsed.remaining}`
          );
        } else if (parsed.error === "wallet_frozen") {
          setError("Your wallet is frozen. Please contact support.");
        } else if (parsed.error === "wallet_closed") {
          setError("Your wallet is closed. Please contact support.");
        } else if (parsed.error === "receiver_not_found") {
          setError("Recipient not found in NeoBank.");
        } else if (parsed.error === "receiver_kyc_not_approved") {
          setError("Recipient has not completed KYC verification.");
        } else {
          setError(parsed.message ?? JSON.stringify(parsed));
        }
      } else {
        setError(
          typeof detail === "string"
            ? detail
            : transferType === "own"
              ? "Own-account transfer failed."
              : "Transfer failed."
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const balance = selectedWallet?.balance ?? 0;
  const amountNum = parseFloat(amount) || 0;
  const insufficient = amountNum > balance;

  const ownAccountOptions =
    selectedWallet &&
    OWN_ACCOUNT_CURRENCIES.has(selectedWallet.currency)
      ? wallets.filter(
          (wallet) =>
            wallet.currency !== selectedWallet.currency &&
            OWN_ACCOUNT_CURRENCIES.has(wallet.currency)
        )
      : [];

  const destinationLabel =
    transferType === "own"
      ? selectedDestinationWallet
        ? `${walletLabel(selectedDestinationWallet.currency)} account`
        : "Destination account"
      : recipient?.display_name ?? recipientValue;

  const tabBeneficiaries = beneficiaries.filter((beneficiary) =>
    tab === "mobile"
      ? beneficiary.type === "mobile"
      : beneficiary.type === "iban",
  );

  const normalizedSearch = search.trim().toLowerCase();

  const filteredBeneficiaries = tabBeneficiaries.filter(
    (beneficiary) =>
      beneficiary.nickname
        .toLowerCase()
        .includes(normalizedSearch) ||
      beneficiary.value
        .toLowerCase()
        .includes(normalizedSearch),
  );

  if (user?.kyc_status !== "approved") return <KYCActionLock action="Transfers" />;

  if (step === "account") return (
    <Wrap>
      <Header title="Transfer Money" step={step} setStep={setStep} router={router} />
      <p style={{ color: "#aaa", fontSize: "13px", marginBottom: "12px" }}>From Account</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "24px" }}>
        {wallets.length === 0 && (
          <div style={{ padding: "32px", textAlign: "center", backgroundColor: "#fff", borderRadius: "16px" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>No wallets found. Add money first.</p>
          </div>
        )}
        {wallets.map((w) => (
          <button key={w.currency} onClick={() => {
              setSelectedWallet(w);
              setSelectedDestinationWallet(null);
              setError("");
            }}
            style={{ backgroundColor: "#fff", border: `2px solid ${selectedWallet?.currency === w.currency ? "#00C853" : "#F0F0F0"}`, borderRadius: "16px", padding: "16px", textAlign: "left", cursor: "pointer" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ backgroundColor: "#00C853", color: "#fff", fontSize: "10px", fontWeight: "700", padding: "2px 8px", borderRadius: "6px", marginRight: "8px" }}>{w.currency}</span>
                <span style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{walletLabel(w.currency)}</span>
              </div>
              <span style={{ fontSize: "16px", fontWeight: "700", color: "#000" }}>
                {formatMoney(w.balance, w.currency)}
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
      <Header title="Transfer Type" step={step} setStep={setStep} router={router} />
      <p style={{ color: "#aaa", fontSize: "13px", marginBottom: "12px" }}>Select which transfer you&apos;d like to do</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {[
          { type: "mobile" as TransferType, label: "Within Neo", sub: "Via Mobile Number or IBAN", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" stroke="#333" strokeWidth="2" strokeLinecap="round"/></svg> },
          { type: "own" as TransferType, label: "To my other accounts", sub: "Between your accounts", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" stroke="#333" strokeWidth="2" strokeLinecap="round"/></svg> },
          { type: "bank" as TransferType, label: "To Bank", sub: "Coming soon", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M3 21h18M3 10h18M5 6l7-3 7 3M4 10v11M8 10v11M12 10v11M16 10v11M20 10v11" stroke="#ccc" strokeWidth="2" strokeLinecap="round"/></svg> },
        ].map(({ type, label, sub, icon }) => (
          <button key={type} onClick={() => {
              if (type === "bank") return;

              setTransferType(type);
              setRecipient(null);
              setRecipientValue("");
              setSelectedDestinationWallet(null);
              setError("");
              setStep("recipient");
            }}
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


  if (step === "recipient" && transferType === "own") return (
    <Wrap>
      <Header
        title="Select Destination Account"
        step={step}
        setStep={setStep}
        router={router}
      />

      <p style={{
        color: "#aaa",
        fontSize: "13px",
        marginBottom: "12px",
      }}>
        Choose one of your other accounts
      </p>

      {ownAccountOptions.length === 0 ? (
        <div style={{
          backgroundColor: "#fff",
          borderRadius: "16px",
          padding: "24px",
          marginBottom: "16px",
        }}>
          <p style={{ color: "#666", fontSize: "14px" }}>
            No supported destination account is available.
          </p>
        </div>
      ) : (
        <div style={{ marginBottom: "20px" }}>
          <select
            aria-label="Destination account"
            value={selectedDestinationWallet?.currency ?? ""}
            onChange={(event) => {
              const wallet =
                ownAccountOptions.find(
                  (item) => item.currency === event.target.value
                ) ?? null;

              setSelectedDestinationWallet(wallet);
              setError("");
            }}
            style={{
              width: "100%",
              border: "1.5px solid #E5E7EB",
              borderRadius: "14px",
              padding: "14px 16px",
              fontSize: "14px",
              color: "#000",
              backgroundColor: "#fff",
              outline: "none",
            }}
          >
            <option value="" disabled>
              Select an account
            </option>

            {ownAccountOptions.map((wallet) => (
              <option
                key={wallet.currency}
                value={wallet.currency}
              >
                {walletLabel(wallet.currency)} -{" "}
                {formatMoney(wallet.balance, wallet.currency)}
              </option>
            ))}
          </select>

          {selectedDestinationWallet && (
            <div style={{
              backgroundColor: "#F0FDF4",
              border: "1px solid #BBF7D0",
              borderRadius: "12px",
              padding: "12px 16px",
              marginTop: "12px",
            }}>
              <p style={{
                color: "#166534",
                fontSize: "13px",
                fontWeight: "600",
              }}>
                To: {walletLabel(selectedDestinationWallet.currency)}
              </p>

              <p style={{
                color: "#166534",
                fontSize: "12px",
                marginTop: "4px",
              }}>
                Current balance:{" "}
                {formatMoney(
                  selectedDestinationWallet.balance,
                  selectedDestinationWallet.currency
                )}
              </p>
            </div>
          )}
        </div>
      )}

      {error && (
        <p style={{
          color: "#EF4444",
          fontSize: "13px",
          marginBottom: "12px",
        }}>
          {error}
        </p>
      )}

      <button
        onClick={() => setStep("amount")}
        disabled={!selectedDestinationWallet}
        style={{
          width: "100%",
          backgroundColor: selectedDestinationWallet
            ? "#00C853"
            : "#E5E7EB",
          color: selectedDestinationWallet ? "#fff" : "#999",
          fontWeight: "700",
          fontSize: "15px",
          border: "none",
          borderRadius: "14px",
          padding: "14px",
          cursor: selectedDestinationWallet
            ? "pointer"
            : "not-allowed",
        }}
      >
        Next
      </button>
    </Wrap>
  );

  if (step === "recipient") return (
    <Wrap>
      <Header title="Transfer to?" step={step} setStep={setStep} router={router} />
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
        {(["mobile", "iban"] as Tab[]).map((t) => (
          <button key={t} onClick={() => {
            setTab(t);
            setSearch("");
            setRecipient(null);
            setError("");
            setPhone("");
            setIban("");
          }}
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
          <input type="text" placeholder="LB00 0000 0000 0000 0000 00" value={iban} onChange={(e) => { setIban(e.target.value); setRecipient(null); setError(""); }}
            style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
        </div>
      )}
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      {recipient?.exists && recipient.kyc_approved && (
        <div style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "12px", padding: "12px 16px", marginBottom: "16px" }}>
          <p style={{ color: "#166534", fontSize: "13px", fontWeight: "600" }}>✓ Sending to: {recipient.display_name}</p>
        </div>
      )}
      <button onClick={validateRecipient} disabled={validating || (tab === "mobile" ? phone.length < 7 : !/^LB[A-Za-z0-9]{22}$/.test(iban.replace(/\s/g, "")))}
        style={{ width: "100%", backgroundColor: "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer", marginBottom: "20px" }}>
        {validating ? "Checking..." : "Validate"}
      </button>
      {recipient?.exists && recipient.kyc_approved && (
        <button onClick={() => setStep("amount")}
          style={{ width: "100%", backgroundColor: "#000", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
          Next
        </button>
      )}
      {tabBeneficiaries.length > 0 && (
        <div style={{ marginTop: "20px" }}>
          <input
            type="search"
            placeholder="Search saved beneficiaries..."
            aria-label="Search saved beneficiaries"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{
              width: "100%",
              border: "1.5px solid #E5E7EB",
              borderRadius: "14px",
              padding: "12px 16px",
              fontSize: "14px",
              color: "#000",
              outline: "none",
              boxSizing: "border-box",
              marginBottom: "12px",
            }}
          />

          {filteredBeneficiaries.length === 0 ? (
            <div
              style={{
                backgroundColor: "#fff",
                border: "1px solid #F0F0F0",
                borderRadius: "14px",
                padding: "20px",
                textAlign: "center",
              }}
            >
              <p
                style={{
                  color: "#888",
                  fontSize: "13px",
                  margin: 0,
                }}
              >
                No saved beneficiaries match your search.
              </p>
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "8px",
              }}
            >
              {filteredBeneficiaries.map((beneficiary) => (
                <button
                  type="button"
                  key={beneficiary.id}
                  onClick={() => {
                    if (tab === "mobile") {
                      setPhone(
                        beneficiary.value.replace("+961", ""),
                      );
                    } else {
                      setIban(beneficiary.value);
                    }

                    setSearch("");
                    setRecipient(null);
                    setError("");
                  }}
                  style={{
                    backgroundColor: "#fff",
                    border: "1px solid #F0F0F0",
                    borderRadius: "14px",
                    padding: "12px 16px",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <p
                    style={{
                      fontSize: "14px",
                      fontWeight: "600",
                      color: "#000",
                    }}
                  >
                    {beneficiary.nickname}
                  </p>
                  <p
                    style={{
                      fontSize: "12px",
                      color: "#aaa",
                    }}
                  >
                    {beneficiary.value}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </Wrap>
  );

  if (step === "amount") return (
    <Wrap>
      <Header title="Enter Amount" step={step} setStep={setStep} router={router} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <p style={{ color: "#aaa", fontSize: "12px", marginBottom: "4px" }}>Sending to</p>
        <p style={{ fontSize: "15px", fontWeight: "600", color: "#000" }}>{destinationLabel}</p>
      </div>
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <p style={{ color: "#aaa", fontSize: "12px", marginBottom: "8px" }}>Amount ({selectedWallet?.currency})</p>
        <input type="number" placeholder="0.00" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }}
          style={{ width: "100%", border: "none", outline: "none", fontSize: "32px", fontWeight: "800", color: insufficient ? "#EF4444" : "#000", backgroundColor: "transparent", boxSizing: "border-box" }} />
        <p style={{ color: insufficient ? "#EF4444" : "#aaa", fontSize: "13px", marginTop: "8px" }}>
          Available: {formatMoney(balance, selectedWallet?.currency ?? "")}
        </p>
        {insufficient && <p style={{ color: "#EF4444", fontSize: "13px", marginTop: "4px", fontWeight: "600" }}>⚠️ Amount exceeds available balance</p>}
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={() => setStep("passcode")} disabled={!amount || insufficient || amountNum <= 0}
        style={{ width: "100%", backgroundColor: !amount || insufficient || amountNum <= 0 ? "#E5E7EB" : "#00C853", color: !amount || insufficient || amountNum <= 0 ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: !amount || insufficient || amountNum <= 0 ? "not-allowed" : "pointer" }}>
        Next
      </button>
    </Wrap>
  );

  if (step === "passcode") return (
    <Wrap>
      <Header title="Confirm Identity" step={step} setStep={setStep} router={router} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        {[
          { label: "To", value: destinationLabel },
          { label: "Amount", value: formatMoney(amountNum, selectedWallet?.currency ?? "") },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Enter your passcode to continue</label>
        <input type="password" placeholder="••••••" maxLength={6} value={passcode}
          onChange={(e) => { setPasscode(e.target.value.replace(/\D/g, "")); setError(""); }}
          style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "20px", letterSpacing: "8px", outline: "none", boxSizing: "border-box" }} />
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={handlePasscode} disabled={passcode.length < 6 || loading}
        style={{ width: "100%", backgroundColor: passcode.length < 6 ? "#E5E7EB" : "#00C853", color: passcode.length < 6 ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: passcode.length < 6 ? "not-allowed" : "pointer" }}>
        {loading ? "Verifying..." : "Continue"}
      </button>
    </Wrap>
  );

  if (step === "confirm") return (
    <Wrap>
      <Header title="Confirm Transfer" step={step} setStep={setStep} router={router} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: "From account", value: walletLabel(selectedWallet?.currency ?? "") },
          { label: "Available balance", value: formatMoney(balance, selectedWallet?.currency ?? "") },
          { label: "To", value: destinationLabel },
          { label: "Amount", value: formatMoney(amountNum, selectedWallet?.currency ?? "") },
          {
             label: "Transfer type",
             value:
               transferType === "own"
                 ? "Between my accounts"
                 : tab === "mobile"
                   ? "Via Mobile Number"
                   : "Via IBAN",
           },
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
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>
          {transferType === "own"
            ? "Transfer Completed!"
            : "Transfer Sent!"}
        </h2>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "To", value: destinationLabel },
            { label: "Amount", value: formatMoney(amountNum, selectedWallet?.currency ?? "") },
            {
              label:
                transferType === "own"
                  ? "Exchange ID"
                  : "Transaction ID",
              value: String(
                (receipt as { transaction_id?: unknown })
                  ?.transaction_id ??
                (receipt as { exchange_id?: unknown })
                  ?.exchange_id ??
                "-"
              ),
            },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
              <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
            </div>
          ))}
        </div>
        {!beneficiaries.some((beneficiary) => beneficiary.value === recipientValue) && !skipSave && (
          <div style={{ backgroundColor: "#fff", borderRadius: "16px", padding: "16px", width: "100%", boxSizing: "border-box" }}>
            {savedRecipient ? (
              <p style={{ color: "#166534", fontSize: "14px", fontWeight: "600", margin: 0 }}>
                Recipient saved successfully.
              </p>
            ) : (
              <>
                <p style={{ color: "#000", fontSize: "14px", fontWeight: "600", margin: "0 0 12px" }}>
                  Save {recipient?.display_name ?? recipientValue} as a beneficiary?
                </p>
                {saveNickname && (
                  <input
                    value={saveNickname}
                    onChange={(event) => {
                      setSaveNickname(event.target.value);
                      setError("");
                    }}
                    placeholder="Nickname"
                    style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "12px", padding: "11px 14px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box", marginBottom: "10px" }}
                  />
                )}
                {error && <p style={{ color: "#EF4444", fontSize: "13px", margin: "0 0 10px" }}>{error}</p>}
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={async () => {
                      if (!saveNickname) {
                        setSaveNickname(recipient?.display_name ?? recipientValue);
                        return;
                      }

                      setLoading(true);
                      setError("");
                      try {
                        await api.post("/beneficiaries", {
                          nickname: saveNickname.trim(),
                          type: tab === "mobile" ? "mobile" : "iban",
                          value: recipientValue,
                        });
                        setSavedRecipient(true);
                      } catch (requestError: unknown) {
                        const detail = (requestError as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
                        setError(typeof detail === "string" ? detail : "Could not save recipient.");
                      } finally {
                        setLoading(false);
                      }
                    }}
                    style={{ flex: 1, backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", border: "none", borderRadius: "10px", padding: "10px", fontSize: "13px", fontWeight: "700", cursor: loading ? "not-allowed" : "pointer" }}
                  >
                    {loading ? "Saving..." : "Save"}
                  </button>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => setSkipSave(true)}
                    style={{ flex: 1, backgroundColor: "#E5E7EB", color: "#555", border: "none", borderRadius: "10px", padding: "10px", fontSize: "13px", fontWeight: "700", cursor: loading ? "not-allowed" : "pointer" }}
                  >
                    Skip
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        <button onClick={() => router.push("/dashboard")}
          style={{ width: "100%", backgroundColor: "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
          Back to Dashboard
        </button>
      </div>
    </Wrap>
  );
}
