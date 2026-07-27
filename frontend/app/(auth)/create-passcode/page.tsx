"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import SixDigitInput from "@/components/auth/SixDigitInput";
import { isWeakPasscode } from "@/lib/authValidation";
import { useAuthStore } from "@/store/authStore";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export default function CreatePasscodePage() {
  const router = useRouter();
  const [first, setFirst] = useState("");
  const [confirm, setConfirm] = useState("");
  const [step, setStep] = useState<"create" | "confirm">("create");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function continueFlow() {
    if (step === "create") {
      if (first.length !== 6 || isWeakPasscode(first)) return setError("Choose a less predictable 6-digit passcode.");
      setError(""); setStep("confirm"); return;
    }
    if (confirm !== first) return setError("Passcodes do not match.");
    setLoading(true);
    try {
      await api.post("/auth/passcode/set", { passcode: first });
      useAuthStore.getState().setSessionState(useAuthStore.getState().user!, true);
      useAuthStore.getState().unlock();
      router.replace(await getPostAuthDestination());
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save passcode.");
    } finally { setLoading(false); }
  }
  const value = step === "create" ? first : confirm;
  return <AuthCard title={step === "create" ? "Create app passcode" : "Confirm passcode"} subtitle="This 6-digit passcode unlocks NeoBank on this device. It does not replace your account password.">
    <SixDigitInput label={step === "create" ? "Enter passcode" : "Enter it again"} value={value} onChange={step === "create" ? setFirst : setConfirm} />
    {error && <p role="alert" style={{ color: "#B91C1C", textAlign: "center" }}>{error}</p>}
    <button type="button" disabled={loading || value.length !== 6} onClick={continueFlow} style={{ width: "100%", marginTop: 24, padding: 14, border: 0, borderRadius: 14, background: value.length === 6 ? "#00C853" : "#E5E7EB", color: value.length === 6 ? "#fff" : "#777", fontWeight: 700 }}>{loading ? "Saving…" : step === "create" ? "Continue" : "Create passcode"}</button>
  </AuthCard>;
}
