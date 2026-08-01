"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import PasswordInput from "@/components/auth/PasswordInput";
import { normalizeLebanesePhone, passwordError, passwordRules } from "@/lib/authValidation";
import { usePreferences } from "@/components/providers/AppPreferences";

export default function RegisterPage() {
  const router = useRouter();
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "", confirm: "", accepted: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    const phone = normalizeLebanesePhone(form.phone);
    if (!form.full_name.trim()) next.full_name = "Full name is required.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) next.email = "Enter a valid email.";
    if (!phone) next.phone = "Enter a valid Lebanese mobile number.";
    const passwordMessage = passwordError(form.password);
    if (passwordMessage) next.password = passwordMessage;
    if (form.password !== form.confirm) next.confirm = "Passwords do not match.";
    if (!form.accepted) next.accepted = "You must accept the Terms and Privacy Policy.";
    if (Object.keys(next).length) return setErrors(next);
    setLoading(true);
    setErrors({});
    try {
      await api.post("/auth/register", { full_name: form.full_name.trim(), email: form.email.trim().toLowerCase(), phone, password: form.password });
      sessionStorage.setItem("verification_email", form.email.trim().toLowerCase());
      router.replace("/verify-registration-otp");
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      if ((error as { response?: { status?: number } }).response?.status === 503) {
        sessionStorage.setItem("verification_email", form.email.trim().toLowerCase());
        sessionStorage.setItem("verification_delivery_error", typeof detail === "string" ? detail : "Email delivery failed.");
        router.replace("/verify-registration-otp");
      } else {
        setErrors({ general: typeof detail === "string" ? detail : "Registration failed. Please try again." });
      }
    } finally { setLoading(false); }
  }

  const field = (name: "full_name" | "email" | "phone", label: string, type = "text") => (
    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#333", marginBottom: 16 }}>
      {label}
      <input type={type} value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })} autoComplete={name === "email" ? "email" : name === "full_name" ? "name" : "tel"} style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 8, border: `1.5px solid ${errors[name] ? "#EF4444" : "#E5E7EB"}`, borderRadius: 14, padding: "12px 16px", outline: 0 }} />
      {errors[name] && <span style={{ display: "block", color: "#EF4444", fontSize: 12, marginTop: 6 }}>{errors[name]}</span>}
    </label>
  );

  return (
    <AuthCard title={tr("Create account", "إنشاء حساب")} subtitle={tr("Join NeoBank Lebanon today", "انضم إلى نيو بنك لبنان اليوم") }>
      <form onSubmit={submit} noValidate>
        {errors.general && <p role="alert" style={{ color: "#B91C1C", background: "#FEF2F2", padding: 12, borderRadius: 12 }}>{errors.general}</p>}
        {field("full_name", tr("Full name", "الاسم الكامل"))}
        {field("email", tr("Email", "البريد الإلكتروني"), "email")}
        {field("phone", tr("Mobile number (+961)", "رقم الهاتف (+961)"), "tel")}
        <PasswordInput label={tr("Password", "كلمة المرور")} value={form.password} onChange={(password) => setForm({ ...form, password })} autoComplete="new-password" error={errors.password} />
        <ul style={{ margin: "-8px 0 16px", paddingLeft: 20, fontSize: 12, color: "#666" }}>
          {passwordRules.map((rule, index) => <li key={rule.label} style={{ color: rule.test(form.password) ? "#00A844" : "#777" }}>{locale === "ar" ? ["8 أحرف على الأقل", "حرف كبير واحد", "حرف صغير واحد", "رقم واحد", "رمز خاص واحد"][index] ?? rule.label : rule.label}</li>)}
        </ul>
        <PasswordInput label={tr("Confirm password", "تأكيد كلمة المرور")} value={form.confirm} onChange={(confirm) => setForm({ ...form, confirm })} autoComplete="new-password" error={errors.confirm} />
        <label style={{ display: "flex", gap: 10, fontSize: 13, color: "#555", marginBottom: 18 }}>
          <input type="checkbox" checked={form.accepted} onChange={(e) => setForm({ ...form, accepted: e.target.checked })} />
          <span>{tr("I agree to the Terms and Privacy Policy.", "أوافق على الشروط وسياسة الخصوصية.")}{errors.accepted && <span style={{ display: "block", color: "#EF4444" }}>{errors.accepted}</span>}</span>
        </label>
        <button type="submit" disabled={loading} style={{ width: "100%", background: loading ? "#86EFAC" : "#00C853", color: "#fff", border: 0, borderRadius: 14, padding: 14, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer" }}>{loading ? tr("Creating account...", "جارٍ إنشاء الحساب...") : tr("Create account", "إنشاء حساب")}</button>
      </form>
      <p style={{ textAlign: "center", fontSize: 13, color: "#777" }}>{tr("Already have an account?", "لديك حساب بالفعل؟")} <Link href="/login" style={{ color: "#00A844" }}>{tr("Sign in", "تسجيل الدخول")}</Link></p>
    </AuthCard>
  );
}
