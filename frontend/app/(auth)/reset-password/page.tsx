"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import PasswordInput from "@/components/auth/PasswordInput";
import { passwordError, passwordRules } from "@/lib/authValidation";

export default function ResetPasswordPage() {
  const router = useRouter(); const [password, setPassword] = useState(""); const [confirm, setConfirm] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  async function submit(e: React.FormEvent) { e.preventDefault(); const validation = passwordError(password); if (validation) return setError(validation); if (password !== confirm) return setError("Passwords do not match."); const reset_token = sessionStorage.getItem("password_reset_token"); if (!reset_token) return router.replace("/forgot-password"); setLoading(true); try { await api.post("/auth/password/reset", { reset_token, new_password: password }); sessionStorage.removeItem("password_reset_token"); sessionStorage.removeItem("reset_email"); router.replace("/login"); } catch { setError("Reset authorization expired. Request a new code."); } finally { setLoading(false); } }
  return <AuthCard title="Create new password" subtitle="Choose a strong password you haven’t used before."><form onSubmit={submit}><PasswordInput label="New password" value={password} onChange={setPassword} autoComplete="new-password" /><ul style={{ fontSize: 12 }}>{passwordRules.map(r => <li key={r.label} style={{ color: r.test(password) ? "#00A844" : "#777" }}>{r.label}</li>)}</ul><PasswordInput label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />{error && <p role="alert" style={{ color: "#B91C1C" }}>{error}</p>}<button disabled={loading} style={{ width: "100%", padding: 14, border: 0, borderRadius: 14, background: "#00C853", color: "#fff", fontWeight: 700 }}>{loading ? "Resetting…" : "Reset password"}</button></form></AuthCard>;
}
