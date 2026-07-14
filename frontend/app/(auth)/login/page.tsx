"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import { isBiometricEnrolled, getDeviceId, signNonce } from "@/lib/biometric";
export default function LoginPage() {
  const router = useRouter();
  const { setTokens, setUser } = useAuthStore();
  const [form, setForm] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState<{ email?: string; password?: string; general?: string }>({});
  const [loading, setLoading] = useState(false);
const [biometricAvailable] = useState(() => 
  typeof window !== "undefined" ? isBiometricEnrolled() : false
);
const [biometricLoading, setBiometricLoading] = useState(false);
  const validate = () => {
    const e: typeof errors = {};
    if (!form.email.trim()) e.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) e.email = "Enter a valid email address.";
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
      const res = await api.post("/auth/login", {
  email: form.email.trim(),
  password: form.password,
});
setTokens(res.data.access_token, res.data.refresh_token);
const userRes = await api.get("/users/me");
setUser(userRes.data);
router.push("/otp");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrors({ general: typeof detail === "string" ? detail : "Invalid email or password." });
    } finally { setLoading(false); }
  };
const handleBiometricLogin = async () => {
  setBiometricLoading(true);
  try {
    const challengeRes = await api.get("/auth/biometric/challenge");
    const nonce = challengeRes.data.nonce;
    const deviceId = getDeviceId();
    const signedNonce = await signNonce(nonce);
    const res = await api.post("/auth/biometric/login", { device_id: deviceId, signed_nonce: signedNonce });
    setTokens(res.data.access_token, res.data.refresh_token);
    const userRes = await api.get("/users/me");
    setUser(userRes.data);
    router.push("/otp");
  } catch {
    setErrors({ general: "Biometric login failed. Use email and password instead." });
  } finally { setBiometricLoading(false); }
};
  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div style={{ marginBottom: "32px", textAlign: "center" }}>
        <div style={{ fontSize: "36px", fontWeight: "800", color: "#000", letterSpacing: "-1px" }}>
          neo<span style={{ color: "#00C853" }}>.</span>
        </div>
        <div style={{ color: "#999", fontSize: "13px", marginTop: "4px" }}>by NeoBank Lebanon</div>
      </div>

      <div style={{ width: "100%", maxWidth: "380px", backgroundColor: "#fff", borderRadius: "24px", padding: "28px", boxShadow: "0 2px 20px rgba(0,0,0,0.08)" }}>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000", marginBottom: "4px" }}>Welcome back</h2>
        <p style={{ color: "#999", fontSize: "13px", marginBottom: "20px" }}>Sign in to your account</p>

        {errors.general && (
          <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px 16px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
            {errors.general}
          </div>
        )}

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Email</label>
          <input type="email" placeholder="you@example.com" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            style={{ width: "100%", border: `1.5px solid ${errors.email ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
          {errors.email && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.email}</p>}
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Password</label>
          <input type="password" placeholder="••••••" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            style={{ width: "100%", border: `1.5px solid ${errors.password ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }} />
          {errors.password && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.password}</p>}
        </div>

        <button onClick={handleSubmit} disabled={loading}
          style={{ width: "100%", backgroundColor: "#0A0A0A", color: "#00C853", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "16px", cursor: loading ? "not-allowed" : "pointer", letterSpacing: "1px" }}>
          {loading ? "Signing in..." : "LOGIN"}
        </button>
{biometricAvailable && (
  <button onClick={handleBiometricLogin} disabled={biometricLoading}
    style={{ width: "100%", backgroundColor: "#F0FDF4", color: "#00C853", fontWeight: "700", fontSize: "15px", border: "1.5px solid #00C853", borderRadius: "14px", padding: "14px", cursor: biometricLoading ? "not-allowed" : "pointer", marginTop: "12px", display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 11c0-1.1.9-2 2-2s2 .9 2 2v2m-4 0h4m-4 0v4m4-4v4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" stroke="#00C853" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
    {biometricLoading ? "Authenticating..." : "Sign in with Biometric"}
  </button>
)}
        <p style={{ textAlign: "center", color: "#999", fontSize: "13px", marginTop: "16px" }}>
          Don&apos;t have an account?{" "}
          <a href="/register" style={{ color: "#00C853", fontWeight: "600", textDecoration: "none" }}>Sign up</a>
        </p>
      </div>
    </div>
  );
}