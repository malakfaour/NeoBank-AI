"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
  const router = useRouter();
  const { setUser, setToken } = useAuthStore();
  const [form, setForm] = useState({ phone: "", passcode: "" });
  const [errors, setErrors] = useState<{ phone?: string; passcode?: string; general?: string }>({});
  const [loading, setLoading] = useState(false);

  const validate = () => {
    const e: typeof errors = {};
    if (!form.phone.trim()) e.phone = "Phone number is required.";
    else if (!/^\+?[0-9]{7,15}$/.test(form.phone.trim())) e.phone = "Enter a valid phone number.";
    if (!form.passcode) e.passcode = "Passcode is required.";
    else if (form.passcode.length < 4) e.passcode = "Passcode must be at least 4 digits.";
    return e;
  };

  const handleSubmit = async () => {
    const e = validate();
    if (Object.keys(e).length) { setErrors(e); return; }
    setErrors({});
    setLoading(true);
    try {
      const res = await api.post("/auth/login", { phone: form.phone.trim(), passcode: form.passcode });
      setToken(res.data.access_token);
      setUser(res.data.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Invalid phone or passcode.";
      setErrors({ general: message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div style={{ marginBottom: "32px", textAlign: "center" }}>
        <div style={{ fontSize: "32px", fontWeight: "800", color: "#000", letterSpacing: "-1px" }}>
          neo<span style={{ color: "#00C853" }}>.</span>
        </div>
        <div style={{ color: "#999", fontSize: "13px", marginTop: "4px" }}>by NeoBank Lebanon</div>
      </div>

      <div style={{ width: "100%", maxWidth: "380px", backgroundColor: "#fff", borderRadius: "24px", padding: "28px", boxShadow: "0 2px 20px rgba(0,0,0,0.08)" }}>
        <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#000", marginBottom: "4px" }}>Welcome back</h2>

        {errors.general && (
          <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px 16px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
            {errors.general}
          </div>
        )}

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Mobile number</label>
          <div style={{ display: "flex", alignItems: "center", border: `1.5px solid ${errors.phone ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", gap: "10px", backgroundColor: "#fff" }}>
            <span style={{ fontSize: "13px", color: "#666", whiteSpace: "nowrap" }}>ðŸ‡±ðŸ‡§ +961</span>
            <div style={{ width: "1px", height: "16px", backgroundColor: "#E5E7EB" }} />
            <input
              type="tel"
              placeholder="70 123 456"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              style={{ flex: 1, border: "none", outline: "none", fontSize: "14px", color: "#000", backgroundColor: "transparent" }}
            />
          </div>
          {errors.phone && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.phone}</p>}
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#333", marginBottom: "8px" }}>Passcode</label>
          <input
            type="password"
            placeholder="â€¢â€¢â€¢â€¢â€¢â€¢"
            value={form.passcode}
            onChange={(e) => setForm({ ...form, passcode: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            style={{ width: "100%", border: `1.5px solid ${errors.passcode ? "#EF4444" : "#E5E7EB"}`, borderRadius: "14px", padding: "12px 16px", fontSize: "14px", color: "#000", outline: "none", boxSizing: "border-box" }}
          />
          {errors.passcode && <p style={{ color: "#EF4444", fontSize: "12px", marginTop: "6px" }}>{errors.passcode}</p>}
        </div>

        <button
          onClick={handleSubmit}
          disabled={loading}
          style={{ width: "100%", backgroundColor: loading ? "#86EFAC" : "#00C853", color: "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </div>
    </div>
  );
}

