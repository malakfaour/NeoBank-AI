"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";
import PreferenceControls from "@/components/ui/PreferenceControls";
import { usePreferences } from "@/components/providers/AppPreferences";

export default function Header() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isStaff = user?.role === "admin" || user?.role === "compliance_officer";
  const { t } = usePreferences();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (isStaff) return;
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
  }, [isStaff]);

  return (
    <header className="dashboard-header">
      <div>
        <p>{t("header.hello")},</p>
        <strong>{user?.full_name ?? "Welcome"}</strong>
      </div>
      <div className="dashboard-header__actions">
        <PreferenceControls compact />
        {!isStaff && (
          <button className="notification-button" onClick={() => router.push("/notifications")}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {unreadCount > 0 && (
              <span style={{ position: "absolute", top: "-4px", right: "-4px", minWidth: "18px", height: "18px", borderRadius: "9px", backgroundColor: "#EF4444", color: "#fff", fontSize: "10px", fontWeight: "700", display: "flex", alignItems: "center", justifyContent: "center", padding: "0 4px", border: "2px solid #fff", boxSizing: "border-box" }}>
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>
        )}
      </div>
    </header>
  );
}
