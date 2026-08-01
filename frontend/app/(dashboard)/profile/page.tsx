"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Camera, Check, Copy } from "lucide-react";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import { usePreferences } from "@/components/providers/AppPreferences";
import { generateKeyPair, savePrivateKey, clearBiometricKey, getDeviceId, isBiometricEnrolled } from "@/lib/biometric";
interface UserMe {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  kyc_status: "pending" | "approved" | "flagged" | "rejected";
  avatar_url?: string | null;
}
interface Wallet {
  currency: string;
  balance: number;
  account_number: string | null;
  iban: string | null;
}
interface KYCProfile {
  workflow_status: string;
  profile_data: Record<string, string | number | null>;
  has_front_id: boolean;
  has_back_id: boolean;
  has_selfie: boolean;
}

const Wrap = ({ children }: { children: React.ReactNode }) => (
  <div className="bank-feature-page profile-page" style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>{children}</div>
);

export default function ProfilePage() {
  const router = useRouter();
  const { locale } = usePreferences();
  const tr = (en: string, ar: string) => locale === "ar" ? ar : en;
  const setUser = useAuthStore((s) => s.setUser);
  const [user, setLocalUser] = useState<UserMe | null>(null);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [copiedIban, setCopiedIban] = useState<string | null>(null);
  const [copiedAccountNumber, setCopiedAccountNumber] = useState<string | null>(null);
  const [kycProfile, setKycProfile] = useState<KYCProfile | null>(null);
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
  const [sheet, setSheet] = useState<"none" | "name" | "email" | "phone" | "passcode">("none");
  const [sheetVal, setSheetVal] = useState("");
  const [sheetOtp, setSheetOtp] = useState("");
  const [sheetCurrent, setSheetCurrent] = useState("");
  const [sheetNew, setSheetNew] = useState("");
  const [sheetLoading, setSheetLoading] = useState(false);
  const [sheetError, setSheetError] = useState("");
  const [sheetNotice, setSheetNotice] = useState("");
  const [sheetOtpSent, setSheetOtpSent] = useState(false);
  const [otpCooldown, setOtpCooldown] = useState(0);
const [statementMonth, setStatementMonth] = useState("");
const [statementFormat, setStatementFormat] = useState<"csv" | "pdf">("pdf");
const [statementLoading, setStatementLoading] = useState(false);
const [statementError, setStatementError] = useState("");
useEffect(() => {
  api.get("/users/me").then((r) => {
      setLocalUser(r.data);
      setUser(r.data);
    }).catch(() => setError("Failed to load profile."))
      .finally(() => setLoading(false));
  api.get("/kyc/profile").then((response) => setKycProfile(response.data)).catch(() => undefined);
  api.get("/accounts/balance")
    .then((response) => setWallets(response.data?.balances ?? []))
    .catch(() => undefined);
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
    setError("");
    const form = new FormData();
    form.append("avatar", file);
    try {
      const res = await api.post("/users/me/avatar", form, {
       headers: {
    "Content-Type": "multipart/form-data",
  },
});
      setLocalUser(res.data);
      setUser(res.data);
      setSuccess("Avatar updated!");
      setTimeout(() => setSuccess(""), 3000);
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Avatar upload failed.");
    }
  };

  useEffect(() => {
    if (otpCooldown <= 0) return;

    const timer = window.setInterval(() => {
      setOtpCooldown((value) => {
        if (value <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return value - 1;
      });
    }, 1000);

    return () => window.clearInterval(timer);
  }, [otpCooldown]);

  const handleNameChange = async () => {
    const fullName = sheetVal.trim();
    if (!fullName) return;

    setSheetLoading(true);
    setSheetError("");
    try {
      const res = await api.patch("/users/me", { full_name: fullName });
      setLocalUser(res.data);
      setUser(res.data);
      setSheet("none");
      setSheetVal("");
      setSuccess("Name updated!");
      setTimeout(() => setSuccess(""), 3000);
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setSheetError(typeof detail === "string" ? detail : "Failed to update name.");
    } finally {
      setSheetLoading(false);
    }
  };

  const handleSendProfileOtp = async () => {
    if (sheet !== "email" && sheet !== "phone" && sheet !== "passcode") return;

    setSheetLoading(true);
    setSheetError("");
    setSheetNotice("");
    try {
    if (sheet === "passcode") {
  if (!user?.id) {
    throw new Error("User ID missing");
  }

  await api.post("/auth/send-otp", {
    user_id: String(user.id),
  });

} else {
  await api.post(`/users/me/${sheet}/otp`);
}
      setSheetOtp("");
      setSheetOtpSent(true);
      setOtpCooldown(30);
      setSheetNotice(`Verification code sent to ${user?.email ?? "your current email"}.`);
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setSheetError(
  typeof detail === "string"
    ? detail
    : requestError instanceof Error
    ? requestError.message
    : "Could not send verification code."
);
    } finally {
      setSheetLoading(false);
    }
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

  const openSheet = (s: "name" | "email" | "phone" | "passcode") => {
    setSheet(s);
    setSheetVal(s === "name" ? user?.full_name ?? "" : "");
    setSheetOtp("");
    setSheetCurrent("");
    setSheetNew("");
    setSheetError("");
    setSheetNotice("");
    setSheetOtpSent(false);
    setOtpCooldown(0);
  };
const handleDownloadStatement = async () => {
  if (!statementMonth) return;
  setStatementLoading(true);
  setStatementError("");
  try {
    const res = await api.get(`/transactions/statement?month=${statementMonth}&format=${statementFormat}`);
    window.open(res.data.presigned_url, "_blank");
  } catch {
    setStatementError("Could not generate statement. Try again.");
  } finally { setStatementLoading(false); }
};
  const walletLabel = (currency: string) => {
    if (currency === "USD") return "Fresh USD";
    if (currency === "LBP") return "Cash LBP";
    return currency;
  };

  const maskIban = (iban: string) => {
    const maskedLength = Math.max(iban.length - 8, 0);
    const maskedGroups = Array.from(
      { length: Math.ceil(maskedLength / 4) },
      (_, index) =>
        "*".repeat(Math.min(4, maskedLength - index * 4)),
    ).join(" ");

    return `${iban.slice(0, 4)} ${maskedGroups} ${iban.slice(-4)}`.trim();
  };

  const handleCopyIban = async (iban: string) => {
    try {
      await navigator.clipboard.writeText(iban);
      setCopiedIban(iban);
      setTimeout(() => setCopiedIban(null), 2000);
    } catch {
      setError("Could not copy IBAN.");
    }
  };

  const maskAccountNumber = (accountNumber: string) =>
    maskIban(accountNumber);

  const handleCopyAccountNumber = async (accountNumber: string) => {
    try {
      await navigator.clipboard.writeText(accountNumber);
      setCopiedAccountNumber(accountNumber);
      setTimeout(() => setCopiedAccountNumber(null), 2000);
    } catch {
      setError("Could not copy account number.");
    }
  };

  const initials = user?.full_name?.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase() ?? "?";

  if (loading) return (
    <Wrap>
      <div style={{ display: "flex", justifyContent: "center", paddingTop: "80px" }}>
        <p style={{ color: "#aaa" }}>{tr("Loading...", "جارٍ التحميل...")}</p>
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
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>{tr("My Profile", "ملفي الشخصي")}</h2>
      </div>

      {error && <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px 16px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>{error}</div>}
      {success && <div style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "12px", padding: "12px 16px", color: "#166534", fontSize: "13px", marginBottom: "16px" }}>✓ {success}</div>}

      {/* Avatar */}
      <div className="profile-identity">
        <button onClick={() => fileRef.current?.click()}
          className="profile-avatar" style={{ width: "80px", height: "80px", borderRadius: "50%", backgroundColor: "#00C853", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", position: "relative" }}>
          {user?.avatar_url
            ? <img src={user.avatar_url} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <span style={{ fontSize: "24px", fontWeight: "700", color: "#fff" }}>{initials}</span>
          }
          <span className="profile-avatar__edit"><Camera size={14} /></span>
        </button>
        <p className="profile-photo-hint" style={{ fontSize: "12px", color: "#aaa", marginTop: "8px" }}>{tr("Tap to change photo", "اضغط لتغيير الصورة")}</p>
        <input ref={fileRef} type="file" accept="image/jpeg,image/png" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAvatarUpload(f); e.currentTarget.value = ""; }} />
        <p className="profile-identity__name" style={{ fontSize: "18px", fontWeight: "700", color: "#000", marginTop: "12px" }}>{user?.full_name}</p>
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
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", padding: "16px 16px 8px" }}>{tr("Personal Details", "المعلومات الشخصية")}</p>
        {[
          { label: tr("Full name", "الاسم الكامل"), value: user?.full_name ?? "—", action: () => openSheet("name") },
          { label: tr("Email", "البريد الإلكتروني"), value: user?.email ?? "—", action: () => openSheet("email") },
          { label: tr("Phone", "رقم الهاتف"), value: user?.phone ?? "—", action: () => openSheet("phone") },
        ].map(({ label, value, action }, i, arr) => (
          <div key={label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: i < arr.length - 1 ? "1px solid #F5F5F5" : "none" }}>
            <div>
              <p style={{ fontSize: "12px", color: "#aaa" }}>{label}</p>
              <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>{value}</p>
            </div>
            {action && (
              <button onClick={action} style={{ fontSize: "13px", color: "#00C853", fontWeight: "600", background: "none", border: "none", cursor: "pointer" }}>{tr("Change", "تعديل")}</button>
            )}
          </div>
        ))}
      </div>

      {/* Account Details */}
      {wallets.some(
        (wallet) => wallet.account_number || wallet.iban,
      ) && (
        <div
          style={{
            backgroundColor: "#fff",
            borderRadius: "20px",
            marginBottom: "16px",
            overflow: "hidden",
          }}
        >
          <p
            style={{
              color: "#aaa",
              fontSize: "11px",
              fontWeight: "700",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              padding: "16px 16px 8px",
            }}
          >
            {tr("Account details", "تفاصيل الحسابات")}
          </p>

          {wallets
            .filter(
              (wallet) => wallet.account_number || wallet.iban,
            )
            .map((wallet, index, availableWallets) => (
              <div
                className="profile-wallet-row"
                key={wallet.currency}
                style={{
                  padding: "14px 16px",
                  borderBottom:
                    index < availableWallets.length - 1
                      ? "1px solid #F5F5F5"
                      : "none",
                }}
              >
                <div className="profile-wallet-summary">
                  <span>{wallet.currency}</span>
                  <strong>{walletLabel(wallet.currency)}</strong>
                </div>
                <div className="profile-wallet-identifiers">
                  {wallet.account_number && <div><small>{tr("Account number", "رقم الحساب")}</small><p title={wallet.account_number}>{maskAccountNumber(wallet.account_number)}</p></div>}
                  {wallet.iban && <div><small>{tr("IBAN", "الآيبان")}</small><p title={wallet.iban}>{maskIban(wallet.iban)}</p></div>}
                </div>
                <div className="profile-copy-group">
                  {wallet.account_number && (
                    <button type="button" onClick={() => handleCopyAccountNumber(wallet.account_number!)} aria-label={`Copy ${walletLabel(wallet.currency)} account number`}>
                      {copiedAccountNumber === wallet.account_number ? <Check size={15} /> : <Copy size={15} />}
                      <span>{copiedAccountNumber === wallet.account_number ? tr("Copied", "تم النسخ") : tr("Account", "الحساب")}</span>
                    </button>
                  )}
                  {wallet.iban && (
                    <button type="button" onClick={() => handleCopyIban(wallet.iban!)} aria-label={`Copy ${walletLabel(wallet.currency)} IBAN`}>
                      {copiedIban === wallet.iban ? <Check size={15} /> : <Copy size={15} />}
                      <span>{copiedIban === wallet.iban ? tr("Copied", "تم النسخ") : tr("IBAN", "الآيبان")}</span>
                    </button>
                  )}
                </div>
              </div>
            ))}
        </div>
      )}

      {kycProfile && (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", marginBottom: "16px", padding: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <div>
              <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase" }}>{tr("Identity & compliance", "الهوية والامتثال")}</p>
              <p style={{ fontWeight: "700", textTransform: "capitalize" }}>{kycProfile.workflow_status.replaceAll("_", " ")}</p>
            </div>
            {kycProfile.workflow_status !== "approved" && (
              <button onClick={() => router.push("/kyc")} style={{ border: "1px solid #BBF7D0", background: "#F0FDF4", color: "#15803D", borderRadius: "10px", padding: "7px 11px", fontWeight: "700", cursor: "pointer" }}>
                {tr("Edit", "تعديل")}
              </button>
            )}
          </div>
          {[
            ["Identification", kycProfile.profile_data.identification_type, kycProfile.profile_data.identification_number],
            ["Residence", kycProfile.profile_data.city, kycProfile.profile_data.country_of_residence],
            ["Employment", kycProfile.profile_data.occupation, kycProfile.profile_data.employer_name],
            ["Financial", kycProfile.profile_data.source_of_funds, kycProfile.profile_data.annual_income_usd ? `${kycProfile.profile_data.annual_income_usd} USD annual income` : null],
            ["Documents", kycProfile.has_front_id && kycProfile.has_back_id && kycProfile.has_selfie ? "Uploaded securely" : "Incomplete", null],
          ].map(([title, first, second]) => (
            <div key={String(title)} style={{ padding: "11px 0", borderTop: "1px solid #F5F5F5" }}>
              <p style={{ fontSize: "12px", color: "#999" }}>{title}</p>
              <p style={{ fontSize: "14px", color: "#222", textTransform: "capitalize" }}>{[first, second].filter(Boolean).join(" · ") || "Not provided"}</p>
            </div>
          ))}
        </div>
      )}

      {/* Security */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", marginBottom: "16px", overflow: "hidden" }}>
        <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", padding: "16px 16px 8px" }}>{tr("Security", "الأمان")}</p>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: "1px solid #F5F5F5" }}>
          <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>{tr("Change Passcode", "تغيير رمز المرور")}</p>
          <button onClick={() => openSheet("passcode")} style={{ fontSize: "13px", color: "#00C853", fontWeight: "600", background: "none", border: "none", cursor: "pointer" }}>{tr("Change", "تغيير")}</button>
        </div>
       <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px" }}>
  <p style={{ fontSize: "14px", fontWeight: "500", color: "#000" }}>{tr("Device-Bound Login", "تسجيل الدخول المرتبط بالجهاز")}</p>
  <button onClick={handleBiometricToggle} disabled={biometricLoading}
    style={{ width: "44px", height: "24px", borderRadius: "12px", border: "none", backgroundColor: biometric ? "#00C853" : "#E5E7EB", cursor: "pointer", position: "relative", transition: "background-color 0.2s" }}>
    <span style={{ position: "absolute", top: "2px", left: biometric ? "22px" : "2px", width: "20px", height: "20px", borderRadius: "50%", backgroundColor: "#fff", transition: "left 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.2)" }} />
  </button>
</div>
        {biometricError && <p style={{ color: "#EF4444", fontSize: "12px", padding: "0 16px 12px" }}>{biometricError}</p>}
      </div>
{/* Account Statement */}
<div style={{ backgroundColor: "#fff", borderRadius: "20px", marginBottom: "16px", overflow: "hidden" }}>
  <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", padding: "16px 16px 8px" }}>{tr("Account Statement", "كشف الحساب")}</p>
  <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
    <div style={{ display: "flex", gap: "8px" }}>
      <input type="month" value={statementMonth} onChange={(e) => setStatementMonth(e.target.value)}
        style={{ flex: 1, border: "1.5px solid #E5E7EB", borderRadius: "12px", padding: "10px 12px", fontSize: "14px", outline: "none" }} />
      <select value={statementFormat} onChange={(e) => setStatementFormat(e.target.value as "csv" | "pdf")}
        style={{ border: "1.5px solid #E5E7EB", borderRadius: "12px", padding: "10px 12px", fontSize: "14px", outline: "none", backgroundColor: "#fff" }}>
        <option value="pdf">PDF</option>
        <option value="csv">CSV</option>
      </select>
    </div>
    {statementError && <p style={{ color: "#EF4444", fontSize: "12px" }}>{statementError}</p>}
    <button onClick={handleDownloadStatement} disabled={!statementMonth || statementLoading}
      style={{ width: "100%", backgroundColor: !statementMonth ? "#E5E7EB" : "#111713", color: !statementMonth ? "#999" : "#00D66F", fontWeight: "800", fontSize: "14px", border: !statementMonth ? "none" : "1px solid #26372E", borderRadius: "12px", padding: "14px", cursor: !statementMonth ? "not-allowed" : "pointer", boxShadow: statementMonth ? "0 10px 24px rgba(7,24,14,.14)" : "none" }}>
      {statementLoading ? tr("Generating...", "جارٍ التجهيز...") : tr("Download Statement", "تنزيل كشف الحساب")}
    </button>
  </div>
</div>
      {/* Sheet overlay */}
      {sheet !== "none" && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", zIndex: 100, display: "flex", alignItems: "flex-end" }}
          onClick={(e) => { if (e.target === e.currentTarget) setSheet("none"); }}>
          <div style={{ backgroundColor: "#fff", borderRadius: "24px 24px 0 0", padding: "24px", width: "100%", boxSizing: "border-box" }}>
            <h3 style={{ fontSize: "16px", fontWeight: "700", color: "#000", marginBottom: "20px" }}>
              {sheet === "name" ? tr("Change Name", "تعديل الاسم") : sheet === "email" ? tr("Change Email", "تعديل البريد الإلكتروني") : sheet === "phone" ? tr("Change Mobile", "تعديل رقم الهاتف") : tr("Change Passcode", "تغيير رمز المرور")}
            </h3>

            {sheetError && <p style={{ color: "#EF4444", fontSize: "13px", marginBottom: "12px" }}>{sheetError}</p>}
            {sheetNotice && <p style={{ color: "#166534", fontSize: "13px", marginBottom: "12px" }}>{sheetNotice}</p>}

            {sheet === "name" && (
              <>
                <input value={sheetVal} onChange={(e) => setSheetVal(e.target.value)}
                  placeholder={tr("Full name", "الاسم الكامل")}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "16px" }} />
                <button onClick={handleNameChange}
                  disabled={!sheetVal.trim() || sheetLoading}
                  style={{ width: "100%", backgroundColor: !sheetVal.trim() ? "#E5E7EB" : "#00C853", color: !sheetVal.trim() ? "#999" : "#fff", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "14px", cursor: "pointer" }}>
                  {sheetLoading ? tr("Saving...", "جارٍ الحفظ...") : tr("Save Name", "حفظ الاسم")}
                </button>
              </>
            )}

            {(sheet === "email" || sheet === "phone") && (
              <>
                <input value={sheetVal} onChange={(e) => setSheetVal(e.target.value)}
                  placeholder={sheet === "email" ? tr("New email address", "البريد الإلكتروني الجديد") : tr("New phone number", "رقم الهاتف الجديد")}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "12px" }} />

                <button onClick={handleSendProfileOtp}
                  disabled={!sheetVal || sheetLoading || otpCooldown > 0}
                  style={{ width: "100%", backgroundColor: otpCooldown > 0 ? "#E5E7EB" : "#fff", color: otpCooldown > 0 ? "#999" : "#00C853", border: "1.5px solid #00C853", fontWeight: "700", fontSize: "14px", borderRadius: "14px", padding: "12px", cursor: !sheetVal || otpCooldown > 0 ? "not-allowed" : "pointer", marginBottom: "12px" }}>
                  {otpCooldown > 0
                    ? tr(`Resend code in ${otpCooldown}s`, `إعادة إرسال الرمز خلال ${otpCooldown} ث`)
                    : sheetOtpSent
                      ? tr("Resend verification code", "إعادة إرسال رمز التحقق")
                      : tr("Send verification code", "إرسال رمز التحقق")}
                </button>

                <input value={sheetOtp} onChange={(e) => setSheetOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder={tr("6-digit OTP code", "رمز التحقق المكوّن من 6 أرقام")} maxLength={6} disabled={!sheetOtpSent}
                  style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "12px 16px", fontSize: "14px", outline: "none", boxSizing: "border-box", marginBottom: "16px", backgroundColor: sheetOtpSent ? "#fff" : "#F9FAFB" }} />

                <button onClick={sheet === "email" ? handleEmailChange : handlePhoneChange}
                  disabled={!sheetVal || !sheetOtpSent || sheetOtp.length < 6 || sheetLoading}
                  style={{ width: "100%", backgroundColor: !sheetVal || !sheetOtpSent || sheetOtp.length < 6 ? "#E5E7EB" : "#111713", color: !sheetVal || !sheetOtpSent || sheetOtp.length < 6 ? "#999" : "#00D66F", fontWeight: "800", fontSize: "15px", border: !sheetVal || !sheetOtpSent || sheetOtp.length < 6 ? "none" : "1px solid #26372E", borderRadius: "14px", padding: "15px", cursor: !sheetVal || !sheetOtpSent || sheetOtp.length < 6 || sheetLoading ? "not-allowed" : "pointer" }}>
                  {sheetLoading ? tr("Saving...", "جارٍ الحفظ...") : tr("Save", "حفظ")}
                </button>
              </>
            )}

            {sheet === "passcode" && (
  <>
    <input
      type="password"
      value={sheetCurrent}
      onChange={(e) =>
        setSheetCurrent(e.target.value.replace(/\D/g, "").slice(0, 6))
      }
      placeholder={tr("Current passcode", "رمز المرور الحالي")}
      maxLength={6}
      style={{
        width: "100%",
        border: "1.5px solid #E5E7EB",
        borderRadius: "14px",
        padding: "12px 16px",
        fontSize: "14px",
        outline: "none",
        boxSizing: "border-box",
        marginBottom: "12px",
      }}
    />

    <input
      type="password"
      value={sheetNew}
      onChange={(e) =>
        setSheetNew(e.target.value.replace(/\D/g, "").slice(0, 6))
      }
      placeholder={tr("New passcode", "رمز المرور الجديد")}
      maxLength={6}
      style={{
        width: "100%",
        border: "1.5px solid #E5E7EB",
        borderRadius: "14px",
        padding: "12px 16px",
        fontSize: "14px",
        outline: "none",
        boxSizing: "border-box",
        marginBottom: "12px",
      }}
    />

    <button
      onClick={handleSendProfileOtp}
      disabled={sheetLoading || otpCooldown > 0}
      style={{
        width: "100%",
        backgroundColor: otpCooldown > 0 ? "#E5E7EB" : "#fff",
        color: otpCooldown > 0 ? "#999" : "#00C853",
        border: "1.5px solid #00C853",
        fontWeight: "700",
        fontSize: "14px",
        borderRadius: "14px",
        padding: "12px",
        cursor: "pointer",
        marginBottom: "12px",
      }}
    >
      {otpCooldown > 0
        ? tr(`Resend OTP in ${otpCooldown}s`, `إعادة إرسال الرمز خلال ${otpCooldown} ث`)
        : sheetOtpSent
        ? tr("Resend OTP", "إعادة إرسال الرمز")
        : tr("Send OTP", "إرسال الرمز")}
    </button>

    <input
      value={sheetOtp}
      onChange={(e) =>
        setSheetOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
      }
      placeholder={tr("6-digit OTP code", "رمز التحقق المكوّن من 6 أرقام")}
      maxLength={6}
      disabled={!sheetOtpSent}
      style={{
        width: "100%",
        border: "1.5px solid #E5E7EB",
        borderRadius: "14px",
        padding: "12px 16px",
        fontSize: "14px",
        outline: "none",
        boxSizing: "border-box",
        marginBottom: "16px",
      }}
    />

    <button
      onClick={handlePasscodeChange}
      disabled={
        sheetCurrent.length < 6 ||
        sheetNew.length < 6 ||
        sheetOtp.length < 6 ||
        sheetLoading
      }
      style={{
        width: "100%",
        backgroundColor:
          sheetCurrent.length < 6 ||
          sheetNew.length < 6 ||
          sheetOtp.length < 6
            ? "#E5E7EB"
            : "#00C853",
        color:
          sheetCurrent.length < 6 ||
          sheetNew.length < 6 ||
          sheetOtp.length < 6
            ? "#999"
            : "#fff",
        fontWeight: "700",
        fontSize: "15px",
        border: "none",
        borderRadius: "14px",
        padding: "14px",
      }}
    >
      {sheetLoading ? tr("Saving...", "جارٍ الحفظ...") : tr("Change Passcode", "تغيير رمز المرور")}
    </button>
  </>
)}
            
          </div>
        </div>
      )}
    </Wrap>
  );
}
