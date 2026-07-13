"use client";

import { useRouter } from "next/navigation";
import NeoLogo from "@/components/NeoLogo";

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
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Green arc background top right */}
      <div style={{
        position: "absolute", top: "-80px", right: "-80px",
        width: "220px", height: "220px", borderRadius: "50%",
        border: "40px solid #00C853", opacity: 0.15,
      }} />

      {/* Logo + tagline */}
      <div style={{ textAlign: "center", marginTop: "60px" }}>
        <p style={{ fontSize: "13px", color: "#999", marginBottom: "16px", letterSpacing: "0.5px" }}>WELCOME TO</p>
        <NeoLogo size={40} />
        <p style={{ fontSize: "13px", color: "#666", marginTop: "10px" }}>by NeoBank Lebanon</p>
      </div>

      {/* Buttons */}
      <div style={{ width: "100%", maxWidth: "340px", display: "flex", flexDirection: "column", gap: "12px" }}>
        <p style={{ textAlign: "center", color: "#999", fontSize: "13px", marginBottom: "4px" }}>Already a neo user?</p>

        <button onClick={() => router.push("/login")}
          style={{ width: "100%", backgroundColor: "#0A0A0A", color: "#00C853", fontWeight: "700", fontSize: "15px", border: "none", borderRadius: "14px", padding: "16px", cursor: "pointer", letterSpacing: "1px" }}>
          LOGIN
        </button>

        <div style={{ height: "1px", backgroundColor: "#E0E0E0", margin: "8px 0" }} />

        <p style={{ textAlign: "center", color: "#999", fontSize: "12px" }}>Are you a new customer?</p>

        <button onClick={() => router.push("/register")}
          style={{ width: "100%", backgroundColor: "transparent", color: "#333", fontWeight: "600", fontSize: "14px", border: "1.5px solid #D0D0D0", borderRadius: "14px", padding: "16px", cursor: "pointer" }}>
          SIGN UP
        </button>
      </div>
    </div>
  );
}