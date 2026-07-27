"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";
import SixDigitInput from "@/components/auth/SixDigitInput";
import { useAuthStore } from "@/store/authStore";
import { getPostAuthDestination } from "@/lib/postAuthNavigation";
import { logoutSession } from "@/lib/logoutSession";

export default function UnlockPage() {
  const router = useRouter();
  const store = useAuthStore();
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function unlock() {
    setLoading(true);
    try {
      await api.post("/auth/passcode/verify", { passcode });
      store.unlock();
      router.replace(await getPostAuthDestination());
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not verify passcode.");
      setPasscode("");
    } finally { setLoading(false); }
  }
  async function anotherAccount() { await logoutSession(); router.replace("/login"); }
  return <AuthCard title={`Welcome back${store.user?.full_name ? `, ${store.user.full_name.split(" ")[0]}` : ""}`} subtitle="Enter your app passcode to unlock NeoBank.">
    <SixDigitInput label="App passcode" value={passcode} onChange={setPasscode} />
    {error && <p role="alert" style={{ color: "#B91C1C", textAlign: "center" }}>{error}</p>}
    <button type="button" disabled={loading || passcode.length !== 6} onClick={unlock} style={{ width: "100%", marginTop: 24, padding: 14, border: 0, borderRadius: 14, background: "#00C853", color: "#fff", fontWeight: 700 }}>{loading ? "Unlocking…" : "Unlock"}</button>
    <p style={{ textAlign: "center" }}><Link href="/forgot-passcode" style={{ color: "#00A844", fontSize: 13 }}>Forgot passcode?</Link></p>
    <button type="button" onClick={anotherAccount} style={{ display: "block", margin: "0 auto", border: 0, background: "none", color: "#666", cursor: "pointer" }}>Log in with another account</button>
  </AuthCard>;
}
