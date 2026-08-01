"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { ArrowLeft, ArrowRight, ArrowUpDown, CheckCircle2, TriangleAlert } from "lucide-react";
import api from "@/lib/axios";
import KYCActionLock from "@/components/kyc/KYCActionLock";
import { useAuthStore } from "@/store/authStore";
import { usePreferences } from "@/components/providers/AppPreferences";

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
  <div className="bank-feature-page exchange-page">{children}</div>
);

const Header = ({ title, onBack }: { title: string; onBack: () => void }) => (
  <div className="transfer-page-header">
    <button className="transfer-back-button" onClick={onBack} aria-label="Go back"><ArrowLeft size={18} /></button>
    <h2>{title}</h2>
  </div>
);

export default function ExchangePage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const { t } = usePreferences();
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

  if (user?.kyc_status !== "approved") return <KYCActionLock action="Currency Exchange" />;

  if (step === "form") return (
    <Wrap>
      <Header title={t("exchange.title")} onBack={goBack} />

      <section className="exchange-hero">
        <div><span>{t("exchange.eyebrow")}</span><h1>{t("exchange.hero")}</h1><p>{t("exchange.heroBody")}</p></div>
        <div className={`exchange-market-state${marketClosed ? " is-closed" : ""}`}><i />{marketClosed ? t("exchange.marketClosed") : t("exchange.marketOpen")}</div>
      </section>

      {marketClosed && (
        <div className="exchange-market-banner" style={{ backgroundColor: "#FFFBEB", border: "1px solid #FCD34D", borderRadius: "14px", padding: "12px 16px", marginBottom: "16px" }}>
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
    {t("exchange.marketClosed")} — {t("exchange.marketHours")}
  </span>
</div> </div>
      )}

      <div className="exchange-converter-card" style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <div className="exchange-panel-heading"><div><span>{t("exchange.convertFunds")}</span><h3>{t("exchange.choose")}</h3></div><ArrowUpDown size={21} /></div>
        <div className="exchange-pair" style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
          <div className="exchange-currency-box" style={{ flex: 1, backgroundColor: "#F5F5F5", borderRadius: "14px", padding: "12px 16px" }}>
            <p style={{ fontSize: "11px", color: "#aaa", marginBottom: "4px" }}>{t("exchange.from")}</p>
            <p style={{ fontSize: "16px", fontWeight: "700", color: "#00C853" }}>{fromCurrency}</p>
          </div>
          <button className="exchange-swap-button" onClick={swap} style={{ width: "48px", height: "48px", borderRadius: "15px", backgroundColor: "#111713", color: "#00D66F", border: "1px solid #26372E", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 10px 24px rgba(7,24,14,.14)" }}>
            <ArrowUpDown size={20} />
          </button>
          <div className="exchange-currency-box" style={{ flex: 1, backgroundColor: "#F5F5F5", borderRadius: "14px", padding: "12px 16px" }}>
            <p style={{ fontSize: "11px", color: "#aaa", marginBottom: "4px" }}>{t("exchange.to")}</p>
            <p style={{ fontSize: "16px", fontWeight: "700", color: "#000" }}>{toCurrency}</p>
          </div>
        </div>

        <input className="exchange-amount-input" type="number" placeholder="0.00" value={amount} onChange={(e) => { setAmount(e.target.value); setConvertedAmount(null); }}
          style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "24px", fontWeight: "800", outline: "none", boxSizing: "border-box", color: "#000" }} />

        {marketRate !== null && <p className="exchange-current-rate" style={{ color: "#aaa", fontSize: "12px", marginTop: "8px" }}><span><i />{t("exchange.rate")}</span><strong>1 {fromCurrency} = {marketRate.toLocaleString()} {toCurrency}</strong></p>}

        <div className="exchange-quick-values" style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
          {["25", "50", "100", "200"].map((q) => (
            <button className={amount === q ? "is-selected" : ""} key={q} onClick={() => setAmount(q)}
              style={{ flex: 1, padding: "9px", borderRadius: "10px", border: amount === q ? "1px solid #26372E" : "1px solid #E5E7EB", backgroundColor: amount === q ? "#111713" : "#fff", color: amount === q ? "#00D66F" : "#333", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>
              {q}
            </button>
          ))}
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="exchange-chart-card" style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
            <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              {t("exchange.history")}
            </p>
            {isStale && <p className="exchange-stale" style={{ fontSize: "11px", color: "#F59E0B", fontWeight: "600" }}><TriangleAlert size={14} />{t("exchange.stale")}</p>}
          </div>
          <p style={{ fontSize: "10px", color: "#aaa", marginBottom: "10px", fontStyle: "italic" }}>
            {t("exchange.forecastNotice")}
          </p>
          <div style={{ display: "flex", gap: "16px", marginBottom: "8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div style={{ width: "12px", height: "2px", backgroundColor: "#3B82F6" }} />
              <p style={{ fontSize: "11px", color: "#aaa" }}>{t("exchange.historical")}</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div style={{ width: "12px", height: "2px", backgroundColor: "#00C853" }} />
              <p style={{ fontSize: "11px", color: "#aaa" }}>{t("exchange.forecast")}</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={chartData}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => String(v).slice(5)} />
              <YAxis tick={{ fontSize: 10 }} width={60} domain={["auto", "auto"]} />
              <Tooltip formatter={(v) => (typeof v === "number" ? v.toLocaleString() : String(v))} />
              <Line type="monotone" dataKey="historical" stroke="#092c22" strokeWidth={2} dot={false} name="Historical" connectNulls={false} />
              <Line type="monotone" dataKey="forecast" stroke="#00C853" strokeWidth={2} dot={false} strokeDasharray="5 5" name="Forecast" connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {(error || rateAvailabilityError) && <p className="exchange-error" style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}><TriangleAlert size={16} />{error || rateAvailabilityError}</p>}

      <button className="exchange-primary-button" onClick={handlePreview} disabled={!amount || parseFloat(amount) <= 0 || converting || !!marketClosed || marketRate === null}
        style={{ width: "100%", backgroundColor: !amount || !!marketClosed || marketRate === null ? "#E5E7EB" : "#111713", color: !amount || !!marketClosed || marketRate === null ? "#999" : "#00D66F", fontWeight: "800", fontSize: "15px", border: !amount || !!marketClosed || marketRate === null ? "none" : "1px solid #26372E", borderRadius: "14px", padding: "15px", cursor: !amount || !!marketClosed || marketRate === null ? "not-allowed" : "pointer" }}>
        {converting ? t("exchange.loadingRate") : marketClosed ? t("exchange.marketClosed") : t("exchange.preview")}<ArrowRight size={18} />
      </button>
    </Wrap>
  );

  if (step === "passcode") return (
    <Wrap>
      <Header title={t("exchange.confirmIdentity")} onBack={goBack} />
      <div className="exchange-flow-summary" style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        {[
          { label: t("exchange.from"), value: `${amount} ${fromCurrency}` },
          { label: t("exchange.to"), value: `${Number(convertedAmount).toLocaleString()} ${toCurrency}` },
          { label: t("exchange.rate"), value: `1 ${fromCurrency} = ${Number(rate).toLocaleString()} ${toCurrency}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      <div className="exchange-passcode-card" style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <label style={{ fontSize: "13px", fontWeight: "600", color: "#333", display: "block", marginBottom: "8px" }}>{t("exchange.enterPasscode")}</label>
        <input type="password" placeholder="••••••" maxLength={6} value={passcode} onChange={(e) => { setPasscode(e.target.value.replace(/\D/g, "")); setError(""); }}
          style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "20px", letterSpacing: "8px", outline: "none", boxSizing: "border-box" }} />
      </div>
      {error && <p className="exchange-error" style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}><TriangleAlert size={16} />{error}</p>}
      <button className="exchange-primary-button" onClick={handlePasscode} disabled={passcode.length < 6 || loading}
        style={{ width: "100%", backgroundColor: passcode.length < 6 ? "#E5E7EB" : "#111713", color: passcode.length < 6 ? "#999" : "#00D66F", fontWeight: "800", fontSize: "15px", border: passcode.length < 6 ? "none" : "1px solid #26372E", borderRadius: "14px", padding: "15px", cursor: passcode.length < 6 ? "not-allowed" : "pointer" }}>
        {loading ? t("exchange.verifying") : t("exchange.continue")}<ArrowRight size={18} />
      </button>
    </Wrap>
  );

  if (step === "confirm") return (
    <Wrap>
      <Header title={t("exchange.confirm")} onBack={goBack} />
      <div className="exchange-flow-summary" style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", marginBottom: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
        {[
          { label: t("exchange.sent"), value: `${amount} ${fromCurrency}` },
          { label: t("exchange.received"), value: `${Number(convertedAmount).toLocaleString()} ${toCurrency}` },
          { label: t("exchange.rate"), value: `1 ${fromCurrency} = ${Number(rate).toLocaleString()} ${toCurrency}` },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
            <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
            <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
          </div>
        ))}
      </div>
      {error && <p className="exchange-error" style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}><TriangleAlert size={16} />{error}</p>}
      <button className="exchange-primary-button" onClick={handleExecute} disabled={loading}
        style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#111713", color: loading ? "#166534" : "#00D66F", fontWeight: "800", fontSize: "15px", border: loading ? "none" : "1px solid #26372E", borderRadius: "14px", padding: "15px", cursor: loading ? "not-allowed" : "pointer" }}>
        {loading ? t("exchange.executing") : t("exchange.confirm")}<ArrowRight size={18} />
      </button>
    </Wrap>
  );

  return (
    <Wrap>
      <div className="exchange-receipt-panel" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "16px", paddingTop: "40px" }}>
        <div className="transfer-success-icon"><CheckCircle2 size={34} /></div>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000" }}>{t("exchange.complete")}</h2>
        <div className="exchange-flow-summary" style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "24px", width: "100%", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: t("exchange.sent"), value: `${amount} ${fromCurrency}` },
            { label: t("exchange.received"), value: `${Number(receipt?.converted_amount).toLocaleString()} ${toCurrency}` },
            { label: t("exchange.id"), value: String(receipt?.exchange_id ?? "—").slice(0, 8) + "..." },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
              <p style={{ color: "#aaa", fontSize: "14px" }}>{label}</p>
              <p style={{ color: "#000", fontSize: "14px", fontWeight: "600" }}>{value}</p>
            </div>
          ))}
        </div>
        <button className="exchange-primary-button" onClick={() => router.push("/dashboard")}
          style={{ width: "100%", backgroundColor: "#111713", color: "#00D66F", fontWeight: "800", fontSize: "15px", border: "1px solid #26372E", borderRadius: "14px", padding: "15px", cursor: "pointer", boxShadow: "0 10px 24px rgba(7,24,14,.14)" }}>
          {t("common.backDashboard")}<ArrowRight size={18} />
        </button>
      </div>
    </Wrap>
  );
}
