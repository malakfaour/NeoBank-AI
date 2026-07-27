"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import PasswordInput from "@/components/auth/PasswordInput";
import SixDigitInput from "@/components/auth/SixDigitInput";
import { isWeakPasscode } from "@/lib/authValidation";
import { useAuthStore } from "@/store/authStore";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export default function ForgotPasscodePage() {
  const router = useRouter(); const [password, setPassword] = useState(""); const [token, setToken] = useState(""); const [passcode, setPasscode] = useState(""); const [confirm, setConfirm] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  async function reauthenticate() { setLoading(true); try { const r = await api.post("/auth/passcode/reset/reauthenticate", { password }); setToken(r.data.reset_token); setError(""); } catch { setError("Invalid account password."); } finally { setLoading(false); } }
  async function reset() { if (isWeakPasscode(passcode)) return setError("Choose a less predictable passcode."); if (passcode !== confirm) return setError("Passcodes do not match."); setLoading(true); try { await api.post("/auth/passcode/reset", { reset_token: token, passcode }); useAuthStore.getState().unlock(); router.replace(await getPostAuthDestination()); } catch { setError("Reset authorization expired. Verify your password again."); setToken(""); } finally { setLoading(false); } }
  return <AuthCard title="Reset app passcode" subtitle={token ? "Create and confirm a new 6-digit passcode." : "Confirm your identity with your account password."}>{!token ? <><PasswordInput label="Account password" value={password} onChange={setPassword} autoComplete="current-password" /><button type="button" disabled={loading || !password} onClick={reauthenticate} style={{ width: "100%", padding: 14, border: 0, borderRadius: 14, background: "#00C853", color: "#fff" }}>Verify identity</button></> : <><SixDigitInput label="New passcode" value={passcode} onChange={setPasscode} /><div style={{ height: 18 }} /><SixDigitInput label="Confirm passcode" value={confirm} onChange={setConfirm} /><button type="button" disabled={loading || passcode.length !== 6 || confirm.length !== 6} onClick={reset} style={{ width: "100%", marginTop: 20, padding: 14, border: 0, borderRadius: 14, background: "#00C853", color: "#fff" }}>Reset passcode</button></>}{error && <p role="alert" style={{ color: "#B91C1C" }}>{error}</p>}</AuthCard>;
}
