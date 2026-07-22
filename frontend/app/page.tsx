"use client";

import { useRouter } from "next/navigation";

export default function WelcomePage() {
  const router = useRouter();

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: "#F0F0F0",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "60px 24px 48px",
    }}>
      {/* Logo */}
      <div style={{ marginTop: "80px", textAlign: "center" }}>
        <p style={{ fontSize: "12px", color: "#999", marginBottom: "16px", letterSpacing: "2px", textTransform: "uppercase" }}>Welcome to</p>
<img src="/logo.svg" alt="NeoBank Lebanon" style={{ width: "200px", height: "auto" }} />
      </div>

      {/* Buttons */}
      <div style={{ width: "100%", maxWidth: "340px", display: "flex", flexDirection: "column", gap: "12px" }}>
        <p style={{ textAlign: "center", color: "#888", fontSize: "13px", marginBottom: "4px" }}>Already a neo user?</p>

        <button onClick={() => router.push("/login")}
          style={{ width: "100%", backgroundColor: "#0A0A0A", color: "#00C853", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "18px", cursor: "pointer", letterSpacing: "2px" }}>
          LOGIN
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: "12px", margin: "4px 0" }}>
          <div style={{ flex: 1, height: "1px", backgroundColor: "#D0D0D0" }} />
          <p style={{ color: "#999", fontSize: "12px" }}>Are you a new customer?</p>
          <div style={{ flex: 1, height: "1px", backgroundColor: "#D0D0D0" }} />
        </div>

        <button onClick={() => router.push("/register")}
          style={{ width: "100%", backgroundColor: "#fff", color: "#333", fontWeight: "600", fontSize: "14px", border: "1.5px solid #D0D0D0", borderRadius: "14px", padding: "18px", cursor: "pointer", letterSpacing: "1px" }}>
          SIGN UP
        </button>
      </div>
    </div>
  );
}