"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import { generateKeyPair, savePrivateKey, clearBiometricKey, getDeviceId, isBiometricEnrolled } from "@/lib/biometric";
interface UserMe {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  kyc_status: "pending" | "approved" | "flagged" | "rejected";
  avatar_url?: string | null;
}

const Wrap = ({ children }: { children: React.ReactNode }) => (
  <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>{children}</div>
);

export default function ProfilePage() {
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);
  const [user, setLocalUser] = useState<UserMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
const [biometric, setBiometric] = useState(() => 
  typeof window !== "undefined" ? isBiometricEnrolled() : false
);
const [biometricLoading, setBiometricLoading] = useState(false);
const [biometricError, setBiometricError] = useState("");
  // Sheet states
  const [sheet, setSheet] = useState<"none" | "email" | "phone" | "passcode">("none");
  const [sheetVal, setSheetVal] = useState("");
  const [sheetOtp, setSheetOtp] = useState("");
  const [sheetCurrent, setSheetCurrent] = useState("");
  const [sheetNew, setSheetNew] = useState("");
  const [sheetLoading, setSheetLoading] = useState(false);
  const [sheetError, setSheetError] = useState("");

useEffect(() => {
  api.get("/users/me").then((r) => {
      setLocalUser(r.data);
      setUser(r.data);
    }).catch(() => setError("Failed to load profile."))
      .finally(() => setLoading(false));
  }, [setUser]);
const handleBiometricToggle = async () => {
  setBiometricLoading(true);
  
  setBiometricError("");
  try {
    if (biometric) {
      clearBiometricKey();
      setBiometric(false);
      setSuccess("Biometric login disabled.");
    } else {
      const { privateKeyHex, publicKeyPem } = await generateKeyPair();
      const deviceId = getDeviceId();
      await api.post("/auth/biometric/enroll", { device_id: deviceId, public_key: publicKeyPem });
      savePrivateKey(privateKeyHex);
      setBiometric(true);
      setSuccess("Biometric login enabled!");
    }
  } catch {
    setBiometricError("Could not set up biometric. Try again.");
  } finally { setBiometricLoading(false); }
};

  const handleAvatarUpload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api.post("/users/me/avatar", form, { headers: { "Content-Type": "multipart/form-data" } });
      setLocalUser(res.data);
      setUser(res.data);
      setSuccess("Avatar updated!");
      setTimeout(() => setSuccess(""), 3000);
    } catch { setError("Avatar upload failed."); }
  };

  const handleEmailChange = async () => {
    setSheetLoading(true); setSheetError("");
    try {
      const res = await api.patch("/users/me/email", { email: sheetVal, otp_code: sheetOtp });
      setLocalUser(res.data); setUser(res.data);
      setSheet("none"); setSheetVal(""); setSheetOtp("");
      setSuccess("Email updated!"); setTimeout(() => setSuccess(""), 3000);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed.";
      setSheetError(typeof msg === "string" ? msg : "Failed.");
    } finally { setSheetLoading(false); }
  };

  const handlePhoneChange = async () => {
    setSheetLoading(true); setSheetError("");
    try {
      const res = await api.patch("/users/me/phone", { phone: sheetVal, otp_code: sheetOtp });
      setLocalUser(res.data); setUser(res.data);
      setSheet("none"); setSheetVal(""); setSheetOtp("");
      setSuccess("Phone updated!"); setTimeout(() => setSuccess(""), 3000);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed.";
      setSheetError(typeof msg === "string" ? msg : "Failed.");
    } finally { setSheetLoading(false); }
  };

  const handlePasscodeChange = async () => {
    setSheetLoading(true); setSheetError("");
    try {
      await api.post("/auth/passcode/change", {
        current_passcode: sheetCurrent,
        new_passcode: sheetNew,
        otp_code: sheetOtp,
      });
      setSheet("none"); setSheetCurrent(""); setSheetNew(""); setSheetOtp("");
      setSuccess("Passcode changed!"); setTimeout(() => setSuccess(""), 3000);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed.";
      setSheetError(typeof msg === "string" ? msg : "Failed.");
    } finally { setSheetLoading(false); }
  };

  const openSheet = (s: "email" | "phone" | "passcode") => {
    setSheet(s); setSheetVal(""); setSheetOtp("");
    setSheetCurrent(""); setSheetNew(""); setSheetError("");
  };

  const initials = user?.full_name?.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase() ?? "?";

  if (loading) return (
    <Wrap>
      <div style={{ display: "flex", justifyContent: "center", paddingTop: "80px" }}>
        <p style={{ color: "#aaa" }}>Loading...</p>
      </div>
    </Wrap>
  );

  return (
    <Wrap>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
        <button onClick={() => router.back()}
          style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>My Profile</h2>
      </div>

      {error && <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px 16px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>{error}</div>}
      {success && <div style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "12px", padding: "12px 16px", color: "#166534", fontSize: "13px", marginBottom: "16px" }}>✓ {success}</div>}

      {/* Avatar */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: "24px" }}>
        <button onClick={() => fileRef.current?.click()}
          style={{ width: "80px", height: "80px", borderRadius: "50%", backgroundColor: "#00C853", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", position: "relative" }}>
          {user?.avatar_url
            ? <img src={user.avatar_url} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <span style={{ fontSize: "24px", fontWeight: "700", color: "#fff" }}>{initials}</span>
          }
        </button>
        <p style={{ fontSize: "12px", color: "#aaa", marginTop: "8px" }}>Tap to change photo</p>
        <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAvatarUpload(f); }} />
        <p style={{ fontSize: "18px", fontWeight: "700", color: "#000", marginTop: "12px" }}>{user?.full_name}</p>
      </div>

      {/* KYC banner */}
      {user?.kyc_status && user.kyc_status !== "approved" && (
        <div style={{ borderRadius: "16px", padding: "14px 16px", backgroundColor: user.kyc_status === "pending" ? "#FFFBEB" : "#FEF2F2", border: `1px solid ${user.kyc_status === "pending" ? "#FCD34D" : "#FECACA"}`, display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
          <p style={{ fontSize: "13px", fontWeight: "700", color: user.kyc_status === "pending" ? "#92400E" : "#991B1B" }}>
            {user.kyc_status === "pending" ? "⏳ Identity verification pending" : "⚠️ KYC flagged or rejected"}
          </p>
          {(user.kyc_status === "flagged" || user.kyc_status === "rejected") && (
            <button onClick={() => router.push("/kyc")}
              style={{ fontSize: "12px", fontWeight: "600", color: "#991B1B", background: "none", border: "1px solid #FECACA", borderRadius: "8px", padding: "4px 10px", cursor: "pointer" }}>
              Re-upload
            </button>
          )}
        </div>
      )}

      {/* Personal Details */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", marginBottom: "16px", overflow: "hidden" }}>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", padding: "16px 16px 8px" }}>Personal Details</p>
        {[
          { label: "Full name", value: user?.full_name ?? "—" },
          { label: "Email", value: user?.email ?? "—", action: () => openSheet("email") },
          { label: "Phone", value: user?.phone ?? "—", action: () => openSheet("phone") },
        ].map(({ label, value, action }, i, arr) => (
          <div key={label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: i < arr.length - 1 ? "1px solid #F5F5F5" : "none" }}>
            <div>
              <p style={{ fontSize: "12px", color: "#aaa" }}>{label}</p>
              <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>{value}</p>
            </div>
            {action && (
              <button onClick={action} style={{ fontSize: "13px", color: "#00C853", fontWeight: "600", background: "none", border: "none", cursor: "pointer" }}>Change</button>
            )}
          </div>
        ))}
      </div>

      {/* Security */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", marginBottom: "16px", overflow: "hidden" }}>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", padding: "16px 16px 8px" }}>Security</p>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: "1px solid #F5F5F5" }}>
          <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>Change Passcode</p>
          <button onClick={() => openSheet("passcode")} style={{ fontSize: "13px", color: "#00C853", fontWeight: "600", background: "none", border: "none", cursor: "pointer" }}>Change</button>
        </div>
       <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px" }}>
  <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>Device-Bound Login</p>
  <button onClick={handleBiometricToggle} disabled={biometricLoading}
    style={{ width: "44px", height: "24px", borderRadius: "12px", border: "none", backgroundColor: biometric ? "#00C853" : "#E5E7EB", cursor: "pointer", position: "relative", transition: "background-color 0.2s" }}>
    <span style={{ position: "absolute", top: "2px", left: biometric ? "22px" : "2px", width: "20px", height: "20px", borderRadius: "50%", backgroundColor: "#fff", transition: "left 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.2)" }} />
  </button>
</div>
        {biometricError && <p style={{ color: "#EF4444", fontSize: "12px", padding: "0 16px 12px" }}>{biometricError}</p>}
      </div>

      {/* Sheet overlay */}
      {sheet !== "none" && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", zIndex: 100, display: "flex", alignItems: "flex-end" }}
          onClick={(e) => { if (e.target === e.currentTarget) setSheet("none"); }}>
          <div style={{ backgroundColor: "#fff", borderRadius: "24px 24px 0 0", padding: "24px", width: "100%", boxSizing: "border-box" }}>
            <h3 style={{ fontSize: "16px", fontWeight: "700", color: "#000", marginBottom: "20px" }}>
              {sheet === "email" ? "Change Email" : sheet === "phone" ? "Change Mobile" : "Change Passcode"}
            </h3>

            {sheetError && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{sheetError}</p>}

            {(sheet === "email" || sheet === "phone") && (
              <>
                <input value={sheetVal} onChange={(e) => setSheetVal(e.target.value)}
                  placeholder={sheet === "email" ? "New email address" : "New phone number"}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "12px" }} />
                <input value={sheetOtp} onChange={(e) => setSheetOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="6-digit OTP code" maxLength={6}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "16px" }} />
                <button onClick={sheet === "email" ? handleEmailChange : handlePhoneChange}
                  disabled={!sheetVal || sheetOtp.length < 6 || sheetLoading}
                  style={{ width: "100%", backgroundColor: !sheetVal || sheetOtp.length < 6 ? "#E5E7EB" : "#00C853", color: !sheetVal || sheetOtp.length < 6 ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
                  {sheetLoading ? "Saving..." : "Save"}
                </button>
              </>
            )}

            {sheet === "passcode" && (
              <>
                <input type="password" value={sheetCurrent} onChange={(e) => setSheetCurrent(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="Current passcode" maxLength={6}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "12px" }} />
                <input type="password" value={sheetNew} onChange={(e) => setSheetNew(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="New passcode" maxLength={6}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "12px" }} />
                <input value={sheetOtp} onChange={(e) => setSheetOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="6-digit OTP code" maxLength={6}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "16px" }} />
                <button onClick={handlePasscodeChange}
                  disabled={sheetCurrent.length < 6 || sheetNew.length < 6 || sheetOtp.length < 6 || sheetLoading}
                  style={{ width: "100%", backgroundColor: sheetCurrent.length < 6 || sheetNew.length < 6 || sheetOtp.length < 6 ? "#E5E7EB" : "#00C853", color: sheetCurrent.length < 6 || sheetNew.length < 6 || sheetOtp.length < 6 ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
                  {sheetLoading ? "Saving..." : "Change Passcode"}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </Wrap>
  );
}
