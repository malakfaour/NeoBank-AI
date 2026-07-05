"use client";

import { useAuthStore } from "@/store/authStore";

export default function Header() {
  const user = useAuthStore((s) => s.user);
  return (
    <header style={{ position: "sticky", top: 0, zIndex: 10, backgroundColor: "#fff", borderBottom: "1px solid #F0F0F0", padding: "12px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <p style={{ color: "#aaa", fontSize: "12px" }}>Good day,</p>
        <p style={{ color: "#000", fontSize: "14px", fontWeight: "700" }}>{user?.full_name ?? "Welcome"}</p>
      </div>
      <button style={{ position: "relative", width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F5F5F5", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <span style={{ position: "absolute", top: "6px", right: "6px", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#00C853", border: "2px solid #fff" }} />
      </button>
    </header>
  );
}