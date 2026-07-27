"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import SixDigitInput from "@/components/auth/SixDigitInput";

export default function VerifyResetOtpPage() {
  const router = useRouter(); const [code, setCode] = useState(""); const [error, setError] = useState(""); const [cooldown, setCooldown] = useState(30); const [loading, setLoading] = useState(false);
  useEffect(() => { if (!cooldown) return; const timer = setInterval(() => setCooldown(v => Math.max(0, v - 1)), 1000); return () => clearInterval(timer); }, [cooldown]);
  async function verify() { const email = sessionStorage.getItem("reset_email"); if (!email) return router.replace("/forgot-password"); setLoading(true); try { const r = await api.post("/auth/password/verify-otp", { email, code }); sessionStorage.setItem("password_reset_token", r.data.reset_token); router.replace("/reset-password"); } catch { setError("Invalid or expired code."); setCode(""); } finally { setLoading(false); } }
  async function resend() { const email = sessionStorage.getItem("reset_email"); if (email) await api.post("/auth/password/forgot", { email }); setCooldown(30); }
  return <AuthCard title="Verify code" subtitle="Enter the 6-digit code sent to your email."><SixDigitInput label="Verification code" value={code} onChange={setCode} />{error && <p role="alert" style={{ color: "#B91C1C" }}>{error}</p>}<button disabled={loading || code.length !== 6} onClick={verify} style={{ width: "100%", marginTop: 20, padding: 14, border: 0, borderRadius: 14, background: "#00C853", color: "#fff" }}>Verify</button><button disabled={cooldown > 0} onClick={resend} style={{ display: "block", margin: "16px auto 0", border: 0, background: "none", color: "#00A844" }}>{cooldown ? `Resend in ${cooldown}s` : "Resend code"}</button></AuthCard>;
}
