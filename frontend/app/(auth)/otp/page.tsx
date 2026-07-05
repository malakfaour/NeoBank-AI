"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import api from "@/lib/axios";

export default function OTPPage() {
  const router = useRouter();
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [resent, setResent] = useState(false);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => { inputs.current[0]?.focus(); }, []);

  const handleChange = (i: number, val: string) => {
    if (!/^\d*$/.test(val)) return;
    const updated = [...digits];
    updated[i] = val.slice(-1);
    setDigits(updated);
    setError("");
    if (val && i < 5) inputs.current[i + 1]?.focus();
  };

  const handleKeyDown = (i: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) inputs.current[i - 1]?.focus();
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;
    const updated = Array(6).fill("");
    pasted.split("").forEach((c, i) => { updated[i] = c; });
    setDigits(updated);
    inputs.current[Math.min(pasted.length, 5)]?.focus();
  };

  const handleSubmit = async () => {
    const code = digits.join("");
    if (code.length < 6) { setError("Enter the full 6-digit code."); return; }
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/verify-otp", { otp: code });
      router.push("/kyc");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Invalid or expired code.";
      setError(message);
      setDigits(Array(6).fill(""));
      inputs.current[0]?.focus();
    } finally { setLoading(false); }
  };

  const handleResend = async () => {
    try {
      await api.post("/auth/resend-otp");
      setResent(true);
      setDigits(Array(6).fill(""));
      inputs.current[0]?.focus();
      setTimeout(() => setResent(false), 4000);
    } catch { setError("Could not resend. Try again."); }
  };

  const filled = digits.join("").length;

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div style={{ marginBottom: "32px", textAlign: "center" }}>
        <div style={{ fontSize: "32px", fontWeight: "800", color: "#000", letterSpacing: "-1px" }}>
          neo<span style={{ color: "#00C853" }}>.</span>
        </div>
      </div>

      <div style={{ width: "100%", maxWidth: "380px", backgroundColor: "#fff", borderRadius: "24px", padding: "28px", boxShadow: "0 2px 20px rgba(0,0,0,0.08)" }}>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000", marginBottom: "4px" }}>Verify your number</h2>
        <p style={{ color: "#999", fontSize: "14px", marginBottom: "24px" }}>Enter the 6-digit code sent to your phone.</p>

        <div style={{ display: "flex", gap: "8px", justifyContent: "space-between", marginBottom: "24px" }} onPaste={handlePaste}>
          {digits.map((d, i) => (
            <input
              key={i}
              ref={(el) => { inputs.current[i] = el; }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={d}
              onChange={(e) => handleChange(i, e.target.value)}
              onKeyDown={(e) => handleKeyDown(i, e)}
              style={{ width: "46px", height: "56px", textAlign: "center", fontSize: "22px", fontWeight: "700", color: "#000", backgroundColor: "#fff", border: `2px solid ${error ? "#EF4444" : d ? "#00C853" : "#E5E7EB"}`, borderRadius: "14px", outline: "none" }}
            />
          ))}
        </div>

        {error && <p style={{ color: "#EF4444", fontSize: "13px", textAlign: "center", marginBottom: "16px" }}>{error}</p>}
        {resent && <p style={{ color: "#00C853", fontSize: "13px", textAlign: "center", marginBottom: "16px" }}>Code resent successfully.</p>}

        <button
          onClick={handleSubmit}
          disabled={loading || filled < 6}
          style={{ width: "100%", backgroundColor: filled < 6 ? "#E5E7EB" : "#00C853", color: filled < 6 ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: filled < 6 ? "not-allowed" : "pointer" }}
        >
          {loading ? "Verifying..." : "Verify"}
        </button>

        <p style={{ textAlign: "center", color: "#999", fontSize: "13px", marginTop: "16px" }}>
          Didn&apos;t get a code?{" "}
          <button onClick={handleResend} style={{ color: "#00C853", fontWeight: "600", background: "none", border: "none", cursor: "pointer", fontSize: "13px" }}>Resend</button>
        </p>
      </div>

      <p style={{ color: "#999", fontSize: "13px", marginTop: "20px" }}>
        <Link href="/login" style={{ color: "#00C853", fontWeight: "600", textDecoration: "none" }}>← Back to sign in</Link>
      </p>
    </div>
  );
}