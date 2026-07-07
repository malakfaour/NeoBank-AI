"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import api from "@/lib/axios";

interface MarketStatus { is_open: boolean; reason?: string; }
interface ForecastPoint { date: string; predicted_rate: number; }
type Step = "form" | "passcode" | "confirm" | "receipt";

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

export default function ExchangePage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("form");
  const [fromCurrency, setFromCurrency] = useState("USD");
  const [toCurrency, setToCurrency] = useState("LBP");
  const [amount, setAmount] = useState("");
  const [convertedAmount, setConvertedAmount] = useState<number | null>(null);
  const [rate, setRate] = useState<number | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [forecast, setForecast] = useState<ForecastPoint[]>([]);
  const [passcode, setPasscode] = useState("");
  const [actionToken, setActionToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [converting, setConverting] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<{ exchange_id: string; converted_amount: number } | null>(null);

  useEffect(() => {
    api.get("/exchange/market-status").then((r) => setMarketStatus(r.data)).catch(() => {});
    api.get("/exchange/forecast").then((r) => setForecast(r.data.predictions ?? [])).catch(() => {});
    api.get("/exchange/rates").then((r) => {
      const rates: { base_currency: string; target_currency: string; rate: number }[] = r.data;
      const r1 = rates.find((x) => x.base_currency === "USD" && x.target_currency === "LBP");
      if (r1) setRate(r1.rate);
    }).catch(() => {});
  }, []);

  const swap = () => {
    setFromCurrency(toCurrency);
    setToCurrency(fromCurrency);
    setConvertedAmount(null);
    setAmount("");
  };

  const handlePreview = async () => {
    if (!amount || parseFloat(amount) <= 0) return;
    setConverting(true);
    setError("");
    try {
      const res = await api.get(`/exchange/convert?amount=${amount}&from_currency=${fromCurrency}&to_currency=${toCurrency}`);
      setConvertedAmount(res.data.converted_amount);
      setRate(res.data.rate);
      setStep("passcode");
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string | { message?: string } } } })?.response?.data?.detail;
      const msg = typeof detail === "object" ? detail?.message : detail;
      setError(msg ?? "Preview failed.");
    } finally { setConverting(false); }
  };

  const handlePasscode = async () => {
    if (passcode.length < 6) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/auth/passcode/verify", { passcode });
      setActionToken(res.data.action_token);
      setStep("confirm");
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Incorrect passcode.";
      setError(typeof msg === "string" ? msg : "Incorrect passcode.");
    } finally { setLoading(false); }
  };

  const handleExecute = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/exchange/execute",
        { from_currency: fromCurrency, to_currency: toCurrency, amount: parseFloat(amount) },
        { headers: { "X-Action-Token": actionToken } }
      );
      setReceipt({ exchange_id: res.data.exchange_id, converted_amount: res.data.converted_amount });
      setStep("receipt");
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string | { message?: string } } } })?.response?.data?.detail;
      const msg = typeof detail === "object" ? detail?.message : detail;
      setError(msg ?? "Exchange failed.");
    } finally { setLoading(false); }
  };

  const goBack = () => {
    if (step === "form") router.back();
    else if (step === "passcode") setStep("form");
    else if (step === "confirm") setStep("passcode");
  };

  const marketClosed = marketStatus && !marketStatus.is_open;

  if (step === "form") return (
    <Wrap>
      <Header title="Exchange" onBack={goBack} />

      {marketClosed && (
        <div style={{ backgroundColor: "#FFFBEB", border: "1px solid #FCD34D", borderRadius: "14px", padding: "12px 16px", marginBottom: "16px" }}>
          <p style={{ fontSize: "13px", fontWeight: "600", color: "#92400E" }}>⏰ Market closed — trading hours are Mon–Fri 08:00–17:00 Beirut time</p>
        </div>
      )}

      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>Convert</p>

        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
          <div style={{ flex: 1, backgroundColor: "#F5F5F5", borderRadius: "14px", padding: "12px 16px" }}>
            <p style={{ fontSize: "11px", color: "#aaa", marginBottom: "4px" }}>From</p>
            <p style={{ fontSize: "16px", fontWeight: "700", color: "#00C853" }}>{fromCurrency}</p>
          </div>
          <button onClick={swap} style={{ width: "40px", height: "40px", borderRadius: "50%", backgroundColor: "#00C853", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <div style={{ flex: 1, backgroundColor: "#F5F5F5", borderRadius: "14px", padding: "12px 16px" }}>
            <p style={{ fontSize: "11px", color: "#aaa", marginBottom: "4px" }}>To</p>
            <p style={{ fontSize: "16px", fontWeight: "700", color: "#000" }}>{toCurrency}</p>
          </div>
        </div>

        <input type="number" placeholder="0.00" value={amount} onChange={(e) => { setAmount(e.target.value); setConvertedAmount(null); }}
          style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "24px", fontWeight: "800", outline: "none", boxSizing: "border-box", color: "#000" }} />

        {rate && <p style={{ color: "#aaa", fontSize: "12px", marginTop: "8px" }}>Rate: 1 {fromCurrency} = {Number(rate).toLocaleString()} {toCurrency}</p>}

        <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
          {["25", "50", "100", "200"].map((q) => (
            <button key={q} onClick={() => setAmount(q)}
              style={{ flex: 1, padding: "6px", borderRadius: "8px", border: "1px solid #E5E7EB", backgroundColor: amount === q ? "#00C853" : "#fff", color: amount === q ? "#fff" : "#333", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}>
              {q}
            </button>
          ))}
        </div>
      </div>

      {forecast.length > 0 && (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
          <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "12px" }}>7-Day USD/LBP Forecast</p>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={forecast}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => String(v).slice(5)} />
              <YAxis tick={{ fontSize: 10 }} width={60} />
              <Tooltip formatter={(v) => (typeof v === "number" ? v.toLocaleString() : String(v))} />
              <Line type="monotone" dataKey="predicted_rate" stroke="#00C853" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}

      <button onClick={handlePreview} disabled={!amount || parseFloat(amount) <= 0 || converting || !!marketClosed}
        style={{ width: "100%", backgroundColor: !amount || !!marketClosed ? "#E5E7EB" : "#00C853", color: !amount || !!marketClosed ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: !amount || !!marketClosed ? "not-allowed" : "pointer" }}>
        {converting ? "Getting rate..." : marketClosed ? "Market Closed" : "Preview Exchange"}
      </button>
    </Wrap>
  );

  if (step === "passcode") return (
    <Wrap>
      <Header title="Confirm Identity" onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        {[
          { label: "From", value: `${amount} ${fromCurrency}` },
          { label: "To", value: `${Number(convertedAmount).toLocaleString()} ${toCurrency}` },
          { label: "Rate", value: `1 ${fromCurrency} = ${Number(rate).toLocaleString()} ${toCurrency}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>Enter your passcode to confirm</label>
        <input type="password" placeholder="••••••" maxLength={6} value={passcode} onChange={(e) => { setPasscode(e.target.value.replace(/\D/g, "")); setError(""); }}
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
      <Header title="Confirm Exchange" onBack={goBack} />
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: "You send", value: `${amount} ${fromCurrency}` },
          { label: "You receive", value: `${Number(convertedAmount).toLocaleString()} ${toCurrency}` },
          { label: "Rate", value: `1 ${fromCurrency} = ${Number(rate).toLocaleString()} ${toCurrency}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      {error && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error}</p>}
      <button onClick={handleExecute} disabled={loading}
        style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: loading ? "not-allowed" : "pointer" }}>
        {loading ? "Executing..." : "Confirm Exchange"}
      </button>
    </Wrap>
  );

  return (
    <Wrap>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", paddingTop: "40px" }}>
        <div style={{ width: "72px", height: "72px", borderRadius: "50%", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "32px" }}>✅</div>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>Exchange Complete!</h2>
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "Sent", value: `${amount} ${fromCurrency}` },
            { label: "Received", value: `${Number(receipt?.converted_amount).toLocaleString()} ${toCurrency}` },
            { label: "Exchange ID", value: String(receipt?.exchange_id ?? "—").slice(0, 8) + "..." },
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