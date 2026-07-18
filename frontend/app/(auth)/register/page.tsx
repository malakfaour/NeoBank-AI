"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import api from "@/lib/axios";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "" });
  const [errors, setErrors] = useState<{ full_name?: string; email?: string; phone?: string; password?: string; general?: string }>({});
  const [loading, setLoading] = useState(false);

  const validate = () => {
    const e: typeof errors = {};
    if (!form.full_name.trim()) e.full_name = "Full name is required.";
    if (!form.email.trim()) e.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) e.email = "Enter a valid email.";
    if (!form.phone.trim()) e.phone = "Phone number is required.";
    else if (!/^[0-9]{7,8}$/.test(form.phone.trim().replace(/\s/g, ""))) e.phone = "Enter a valid Lebanese number (e.g. 70 123 456).";
    if (!form.password) e.password = "Password is required.";
    else if (form.password.length < 6) e.password = "Password must be at least 6 characters.";
    return e;
  };

  const handleSubmit = async () => {
    const e = validate();
    if (Object.keys(e).length) { setErrors(e); return; }
    setErrors({});
    setLoading(true);
    try {
      await api.post("/auth/register", {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: `+961${form.phone.trim().replace(/\s/g, "")}`,
        password: form.password,
      });
      router.push("/login");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrors({ general: typeof detail === "string" ? detail : "Registration failed. Please try again." });
    } finally { setLoading(false); }
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div style={{ marginBottom: "32px", textAlign: "center" }}>
      <img src="/logo.svg" alt="NeoBank Lebanon" style={{ width: "160px", height: "auto" }} />    </div>

      <div style={{ width: "100%", maxWidth: "380px", backgroundColor: "#fff", borderRadius: "24px", padding: "28px", boxShadow: "0 2px 20px rgba(0,0,0,0.08)" }}>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000", marginBottom: "4px" }}>Create account</h2>
        <p style={{ color: "#999", fontSize: "13px", marginBottom: "20px" }}>Join NeoBank Lebanon today</p>

        {errors.general && (
          <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px 16px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
            {errors.general}
          </div>
        )}

        {/* Full name */}
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Full name</label>
          <input type="text" placeholder="Lana Nasserdine" value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            style={{ width: "100%", border: `1.5px solid ${errors.full_name ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
          {errors.full_name && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.full_name}</p>}
        </div>

        {/* Email */}
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Email</label>
          <input type="email" placeholder="you@example.com" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            style={{ width: "100%", border: `1.5px solid ${errors.email ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
          {errors.email && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.email}</p>}
        </div>

        {/* Phone */}
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Mobile number</label>
          <div style={{ display: "flex", alignItems: "center", border: `1.5px solid ${errors.phone ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", gap: "10px", backgroundColor: "#fff" }}>
            <span style={{ fontSize: "13px", color: "#666", whiteSpace: "nowrap" }}>🇱🇧 +961</span>
            <div style={{ width: "1px", height: "16px", backgroundColor: "#E5E7EB" }} />
            <input type="tel" placeholder="70 123 456" value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              style={{ flex: 1, border: "none", outline: "none", fontSize: "14px", color: "#000", backgroundColor: "transparent" }} />
          </div>
          {errors.phone && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.phone}</p>}
        </div>

        {/* Password */}
        <div style={{ marginBottom: "24px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Password</label>
          <input type="password" placeholder="••••••" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            style={{ width: "100%", border: `1.5px solid ${errors.password ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
          {errors.password && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.password}</p>}
        </div>

        <button onClick={handleSubmit} disabled={loading}
          style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: loading ? "not-allowed" : "pointer" }}>
          {loading ? "Creating account..." : "Create account"}
        </button>

        <p style={{ textAlign: "center", color: "#999", fontSize: "13px", marginTop: "16px" }}>
          Already have an account?{" "}
          <Link href="/login" style={{ color: "#00C853", fontWeight: "600", textDecoration: "none" }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}