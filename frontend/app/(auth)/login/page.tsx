"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import PasswordInput from "@/components/auth/PasswordInput";
import { useAuthStore } from "@/store/authStore";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";
import { usePreferences } from "@/components/providers/AppPreferences";

export default function LoginPage() {
  const router = useRouter();
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim() || !password) return setError(tr("Email and password are required.", "البريد الإلكتروني وكلمة المرور مطلوبان."));
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
        setError(tr("Invalid email or password.", "البريد الإلكتروني أو كلمة المرور غير صحيحة."));
      }
    } finally { setLoading(false); }
  }

  return (
    <AuthCard title={tr("Welcome back", "أهلاً بعودتك")} subtitle={tr("Sign in with your account password", "سجّل الدخول باستخدام كلمة مرور حسابك") }>
      <form onSubmit={submit} noValidate>
        {error && <p role="alert" style={{ color: "#B91C1C", background: "#FEF2F2", padding: 12, borderRadius: 12 }}>{error}</p>}
        <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#333", marginBottom: 16 }}>
          {tr("Email", "البريد الإلكتروني")}
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 8, border: "1.5px solid #E5E7EB", borderRadius: 14, padding: "12px 16px", outline: 0 }} />
        </label>
        <PasswordInput label={tr("Password", "كلمة المرور")} value={password} onChange={setPassword} autoComplete="current-password" />
        <div style={{ textAlign: locale === "ar" ? "left" : "right", margin: "-6px 0 18px" }}><Link href="/forgot-password" style={{ color: "#00A844", fontSize: 13 }}>{tr("Forgot password?", "نسيت كلمة المرور؟")}</Link></div>
        <button type="submit" disabled={loading} style={{ width: "100%", background: "#111", color: "#00C853", border: 0, borderRadius: 14, padding: 15, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer" }}>{loading ? tr("Signing in...", "جارٍ تسجيل الدخول...") : tr("LOGIN", "تسجيل الدخول")}</button>
      </form>
      <p style={{ textAlign: "center", color: "#777", fontSize: 13 }}>{tr("Don't have an account?", "ليس لديك حساب؟")} <Link href="/register" style={{ color: "#00A844" }}>{tr("Create account", "إنشاء حساب")}</Link></p>
    </AuthCard>
  );
}
