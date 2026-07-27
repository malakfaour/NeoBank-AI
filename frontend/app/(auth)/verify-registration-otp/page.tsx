"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import SixDigitInput from "@/components/auth/SixDigitInput";
import { useAuthStore } from "@/store/authStore";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export default function VerifyRegistrationOtpPage() {
  const router = useRouter(); const [code, setCode] = useState(""); const [error, setError] = useState(() => typeof window === "undefined" ? "" : sessionStorage.getItem("verification_delivery_error") ?? ""); const [loading, setLoading] = useState(false); const [cooldown, setCooldown] = useState(0);
  async function verify() { const email = sessionStorage.getItem("verification_email"); if (!email) return router.replace("/register"); setLoading(true); try { const response = await api.post("/auth/registration/verify-otp", { email, code }); const store = useAuthStore.getState(); store.setTokens(response.data.access_token, response.data.refresh_token); store.setSessionState(response.data.user, response.data.passcode_is_set); store.unlock(); sessionStorage.removeItem("verification_email"); sessionStorage.removeItem("verification_delivery_error"); router.replace(await getPostAuthDestination()); } catch { setError("Invalid or expired code."); setCode(""); } finally { setLoading(false); } }
  async function resend() { const email = sessionStorage.getItem("verification_email"); if (!email) return router.replace("/register"); setLoading(true); try { await api.post("/auth/registration/resend-otp", { email }); setError(""); setCooldown(30); const timer = window.setInterval(() => setCooldown(value => { if (value <= 1) { window.clearInterval(timer); return 0; } return value - 1; }), 1000); } catch (requestError: unknown) { const detail = (requestError as { response?: { data?: { detail?: string } } }).response?.data?.detail; setError(typeof detail === "string" ? detail : "Could not resend the verification email."); } finally { setLoading(false); } }
  return <AuthCard title="Verify your email" subtitle="Enter the 6-digit code sent to your email."><SixDigitInput label="Verification code" value={code} onChange={setCode} />{error && <p role="alert" style={{ color: "#B91C1C" }}>{error}</p>}<button type="button" disabled={loading || code.length !== 6} onClick={verify} style={{ width: "100%", marginTop: 20, padding: 14, border: 0, borderRadius: 14, background: "#00C853", color: "#fff", fontWeight: 700 }}>{loading ? "Verifying…" : "Verify"}</button><button type="button" disabled={loading || cooldown > 0} onClick={resend} style={{ display: "block", margin: "16px auto 0", border: 0, background: "none", color: "#00A844" }}>{cooldown ? `Resend in ${cooldown}s` : "Resend code"}</button></AuthCard>;
}
