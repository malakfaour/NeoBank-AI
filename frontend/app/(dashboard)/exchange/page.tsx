"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import api from "@/lib/axios";

interface MarketStatus {
  market_open: boolean;
  timezone: string;
  current_time: string;
  opens_at: string;
  closes_at: string;
}
interface HistoryPoint { date: string; rate: number; provider: string; }
interface ForecastPoint { date: string; predicted_rate: number; }
interface ExchangeRateItem {
  base_currency: string;
  target_currency: string;
  rate: string | number;
  provider: string;
  last_updated_at: string | null;
}
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
  const [rates, setRates] = useState<ExchangeRateItem[]>([]);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [forecast, setForecast] = useState<ForecastPoint[]>([]);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [passcode, setPasscode] = useState("");
  const [actionToken, setActionToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [converting, setConverting] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<{ exchange_id: string; converted_amount: number } | null>(null);

  useEffect(() => {
    api.get("/exchange/market-status").then((r) => setMarketStatus(r.data)).catch(() => {});
    api.get("/exchange/rates/history?days=30").then((r) => setHistory(r.data ?? [])).catch(() => {});
    api.get("/exchange/forecast").then((r) => setForecast(r.data.predictions ?? [])).catch(() => {});
    api.get("/exchange/rates").then((r) => {
      const data: ExchangeRateItem[] = Array.isArray(r.data) ? r.data : [];
      setRates(data);
      setError("");
    }).catch(() => {
      setRates([]);
      setError("Could not load exchange rates. Please try again.");
    });
  }, []);

  const selectedRate = rates.find(
    (item) => item.base_currency === fromCurrency && item.target_currency === toCurrency
  ) ?? null;

  const numericMarketRate = selectedRate ? Number(selectedRate.rate) : Number.NaN;
  const marketRate = Number.isFinite(numericMarketRate) ? numericMarketRate : null;

  const selectedRateUpdatedAt = selectedRate?.last_updated_at
    ? new Date(selectedRate.last_updated_at).getTime()
    : Number.NaN;

  const marketCurrentTime = marketStatus?.current_time
    ? new Date(marketStatus.current_time).getTime()
    : Number.NaN;

  const isStale =
    Number.isFinite(selectedRateUpdatedAt) &&
    Number.isFinite(marketCurrentTime) &&
    marketCurrentTime - selectedRateUpdatedAt > 5 * 60 * 1000;

  const rateAvailabilityError =
    rates.length > 0 && marketRate === null
      ? `Exchange pair ${fromCurrency} → ${toCurrency} is unavailable.`
      : "";

  const swap = () => {
    setFromCurrency(toCurrency);
    setToCurrency(fromCurrency);
    setConvertedAmount(null);
    setRate(null);
    setAmount("");
    setError("");
  };

  const handlePreview = async () => {
    if (!amount || parseFloat(amount) <= 0 || marketRate === null) return;
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

  const marketClosed = marketStatus !== null && !marketStatus.market_open;

  const chartData = [
    ...history.map((h) => ({ date: h.date, historical: h.rate })),
    ...forecast.map((f) => ({ date: f.date, forecast: f.predicted_rate })),
  ].sort((a, b) => a.date.localeCompare(b.date));

  if (step === "form") return (
    <Wrap>
      <Header title="Exchange" onBack={goBack} />

      {marketClosed && (
        <div style={{ backgroundColor: "#FFFBEB", border: "1px solid #FCD34D", borderRadius: "14px", padding: "12px 16px", marginBottom: "16px" }}>
         <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
  >
    <circle
      cx="12"
      cy="12"
      r="9"
      stroke="#B45309"
      strokeWidth="2"
    />
    <path
      d="M12 7V12L15 14"
      stroke="#B45309"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>

  <span>
    Market closed — trading hours are Mon–Fri 08:00–17:00 Beirut time
  </span>
</div> </div>
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

        {marketRate !== null && <p style={{ color: "#aaa", fontSize: "12px", marginTop: "8px" }}>Rate: 1 {fromCurrency} = {marketRate.toLocaleString()} {toCurrency}</p>}

        <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
          {["25", "50", "100", "200"].map((q) => (
            <button key={q} onClick={() => setAmount(q)}
              style={{ flex: 1, padding: "6px", borderRadius: "8px", border: "1px solid #E5E7EB", backgroundColor: amount === q ? "#00C853" : "#fff", color: amount === q ? "#fff" : "#333", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}>
              {q}
            </button>
          ))}
        </div>
      </div>

      {chartData.length > 0 && (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
            <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              USD/LBP Rate History + Forecast
            </p>
            {isStale && <p style={{ fontSize: "11px", color: "#F59E0B", fontWeight: "600" }}>⚠ Stale data</p>}
          </div>
          <p style={{ fontSize: "10px", color: "#aaa", marginBottom: "10px", fontStyle: "italic" }}>
            Forecast is indicative only and not guaranteed.
          </p>
          <div style={{ display: "flex", gap: "16px", marginBottom: "8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div style={{ width: "12px", height: "2px", backgroundColor: "#3B82F6" }} />
              <p style={{ fontSize: "11px", color: "#aaa" }}>Historical</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div style={{ width: "12px", height: "2px", backgroundColor: "#00C853" }} />
              <p style={{ fontSize: "11px", color: "#aaa" }}>Forecast</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={chartData}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => String(v).slice(5)} />
              <YAxis tick={{ fontSize: 10 }} width={60} domain={["auto", "auto"]} />
              <Tooltip formatter={(v) => (typeof v === "number" ? v.toLocaleString() : String(v))} />
              <Line type="monotone" dataKey="historical" stroke="#3B82F6" strokeWidth={2} dot={false} name="Historical" connectNulls={false} />
              <Line type="monotone" dataKey="forecast" stroke="#00C853" strokeWidth={2} dot={false} strokeDasharray="5 5" name="Forecast" connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {(error || rateAvailabilityError) && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{error || rateAvailabilityError}</p>}

      <button onClick={handlePreview} disabled={!amount || parseFloat(amount) <= 0 || converting || !!marketClosed || marketRate === null}
        style={{ width: "100%", backgroundColor: !amount || !!marketClosed || marketRate === null ? "#E5E7EB" : "#00C853", color: !amount || !!marketClosed || marketRate === null ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: !amount || !!marketClosed || marketRate === null ? "not-allowed" : "pointer" }}>
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