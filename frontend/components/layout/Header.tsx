"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

export default function Header() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await api.get("/users/me");
        if (!cancelled) setUnreadCount(res.data.unread_count ?? 0);
      } catch { /* ignore */ }
    };
    load();
    const interval = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  return (
    <header style={{ position: "sticky", top: 0, zIndex: 10, backgroundColor: "#fff", borderBottom: "1px solid #F0F0F0", padding: "12px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <p style={{ color: "#aaa", fontSize: "12px" }}>Good day,</p>
        <p style={{ color: "#000", fontSize: "14px", fontWeight: "700" }}>{user?.full_name ?? "Welcome"}</p>
      </div>
      <button onClick={() => router.push("/notifications")}
        style={{ position: "relative", width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F5F5F5", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        {unreadCount > 0 && (
          <span style={{ position: "absolute", top: "-4px", right: "-4px", minWidth: "18px", height: "18px", borderRadius: "9px", backgroundColor: "#EF4444", color: "#fff", fontSize: "10px", fontWeight: "700", display: "flex", alignItems: "center", justifyContent: "center", padding: "0 4px", border: "2px solid #fff", boxSizing: "border-box" }}>
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
    </header>
  );
}