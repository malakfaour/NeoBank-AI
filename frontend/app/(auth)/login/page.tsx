"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import PasswordInput from "@/components/auth/PasswordInput";
import { useAuthStore } from "@/store/authStore";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim() || !password) return setError("Email and password are required.");
    setLoading(true);
    setError("");
    try {
      const response = await api.post("/auth/login", { email: email.trim().toLowerCase(), password });
      const store = useAuthStore.getState();
      store.setTokens(response.data.access_token, response.data.refresh_token);
      store.setSessionState(response.data.user, response.data.passcode_is_set);
      store.unlock();
      router.replace(await getPostAuthDestination());
    } catch (requestError: unknown) {
      const status = (requestError as { response?: { status?: number } }).response?.status;
      if (status === 403) {
        sessionStorage.setItem("verification_email", email.trim().toLowerCase());
        router.replace("/verify-registration-otp");
      } else {
        setError("Invalid email or password.");
      }
    } finally { setLoading(false); }
  }

  return (
    <AuthCard title="Welcome back" subtitle="Sign in with your account password">
      <form onSubmit={submit} noValidate>
        {error && <p role="alert" style={{ color: "#B91C1C", background: "#FEF2F2", padding: 12, borderRadius: 12 }}>{error}</p>}
        <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#333", marginBottom: 16 }}>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 8, border: "1.5px solid #E5E7EB", borderRadius: 14, padding: "12px 16px", outline: 0 }} />
        </label>
        <PasswordInput label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
        <div style={{ textAlign: "right", margin: "-6px 0 18px" }}><Link href="/forgot-password" style={{ color: "#00A844", fontSize: 13 }}>Forgot password?</Link></div>
        <button type="submit" disabled={loading} style={{ width: "100%", background: "#111", color: "#00C853", border: 0, borderRadius: 14, padding: 15, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer" }}>{loading ? "Signing in…" : "LOGIN"}</button>
      </form>
      <p style={{ textAlign: "center", color: "#777", fontSize: 13 }}>Don&apos;t have an account? <Link href="/register" style={{ color: "#00A844" }}>Create account</Link></p>
    </AuthCard>
  );
}
