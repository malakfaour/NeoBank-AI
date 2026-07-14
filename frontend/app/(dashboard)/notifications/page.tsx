"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface Notification {
  id: number;
  type: string;
  message: string;
  read: boolean;
  created_at: string;
}

function timeAgo(d: string) {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const typeColor: Record<string, string> = {
  KYC_APPROVED: "#00C853", KYC_FLAGGED: "#F59E0B", KYC_REJECTED: "#EF4444",
  TRANSFER: "#3B82F6", TOPUP: "#00C853", EXCHANGE: "#8B5CF6", DEFAULT: "#6B7280",
};

function NotifIcon({ type }: { type: string }) {
  const color = typeColor[type] ?? typeColor.DEFAULT;
  if (type === "TRANSFER") return <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (type === "TOPUP") return <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke={color} strokeWidth="2" strokeLinecap="round"/></svg>;
  if (type === "EXCHANGE") return <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (type.startsWith("KYC")) return <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M15 17H20L18.595 15.595A1 1 0 0118 14.879V11a6 6 0 10-12 0v3.879a1 1 0 01-.293.707L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

export default function NotificationsPage() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [prefs, setPrefs] = useState({ email: true, push: true, sms: true });
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [prefsSaved, setPrefsSaved] = useState(false);

  const togglePref = async (key: "email" | "push" | "sms") => {
    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    setPrefsLoading(true);
    try {
      await api.patch("/users/me", { notification_preferences: updated });
      setPrefsSaved(true);
      setTimeout(() => setPrefsSaved(false), 2000);
    } catch { setPrefs(prefs); }
    finally { setPrefsLoading(false); }
  };

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await api.get("/notifications");
      setNotifications(res.data.items ?? res.data ?? []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => { if (!cancelled) await fetchNotifications(); };
    load();
    api.get("/users/me").then((r) => {
      if (r.data.notification_preferences) setPrefs(r.data.notification_preferences);
    }).catch(() => {});

    const token = localStorage.getItem("access_token");
    if (token) {
      const es = new EventSource(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/notifications/stream?token=${token}`);
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type !== "ping") setNotifications((prev) => [data, ...prev]);
        } catch { /* ignore */ }
      };
      return () => { cancelled = true; es.close(); };
    }

    const interval = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [fetchNotifications]);

  const markRead = async (id: number) => {
    try {
      await api.patch(`/notifications/${id}/read`);
      setNotifications((prev) => prev.map((n) => n.id === id ? { ...n, read: true } : n));
    } catch { /* ignore */ }
  };

  const markAllRead = async () => {
    try {
      await api.patch("/notifications/read-all");
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch { /* ignore */ }
  };

  const unread = notifications.filter((n) => !n.read).length;

  const prefItems = [
    {
      key: "email" as const, label: "Email notifications", desc: "Receive updates via email",
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" stroke="#6B7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
    },
    {
      key: "push" as const, label: "Push notifications", desc: "Browser push alerts",
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M15 17H20L18.595 15.595A1 1 0 0118 14.879V11a6 6 0 10-12 0v3.879a1 1 0 01-.293.707L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" stroke="#6B7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
    },
    {
      key: "sms" as const, label: "SMS notifications", desc: "Text message alerts",
      icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" stroke="#6B7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
    },
  ];

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button onClick={() => router.back()}
            style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
          <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>Notifications</h2>
          {unread > 0 && (
            <span style={{ backgroundColor: "#EF4444", color: "#fff", fontSize: "11px", fontWeight: "700", borderRadius: "10px", padding: "2px 7px" }}>{unread}</span>
          )}
        </div>
        {unread > 0 && (
          <button onClick={markAllRead} style={{ fontSize: "13px", color: "#00C853", fontWeight: "600", background: "none", border: "none", cursor: "pointer" }}>
            Mark all read
          </button>
        )}
      </div>

      {/* Notification Preferences */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "20px", marginBottom: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <p style={{ fontSize: "14px", fontWeight: "700", color: "#000" }}>Notification Preferences</p>
          {prefsSaved && <p style={{ fontSize: "12px", color: "#00C853", fontWeight: "600" }}>Saved</p>}
          {prefsLoading && !prefsSaved && <p style={{ fontSize: "12px", color: "#aaa" }}>Saving...</p>}
        </div>
        {prefItems.map(({ key, label, icon, desc }) => (
          <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: key !== "sms" ? "1px solid #F5F5F5" : "none", padding: "12px 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div style={{ width: "36px", height: "36px", borderRadius: "10px", backgroundColor: "#F5F5F5", display: "flex", alignItems: "center", justifyContent: "center" }}>
                {icon}
              </div>
              <div>
                <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>{label}</p>
                <p style={{ fontSize: "12px", color: "#aaa" }}>{desc}</p>
              </div>
            </div>
            <button onClick={() => togglePref(key)}
              style={{ width: "48px", height: "28px", borderRadius: "14px", border: "none", backgroundColor: prefs[key] ? "#00C853" : "#E5E7EB", cursor: "pointer", position: "relative", flexShrink: 0 }}>
              <div style={{ position: "absolute", top: "3px", left: prefs[key] ? "23px" : "3px", width: "22px", height: "22px", borderRadius: "50%", backgroundColor: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.2)" }} />
            </button>
          </div>
        ))}
      </div>

      {/* Notifications list */}
      <div style={{ backgroundColor: "#fff", borderRadius: "20px", overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "32px", textAlign: "center" }}><p style={{ color: "#aaa" }}>Loading...</p></div>
        ) : notifications.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center" }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" style={{ margin: "0 auto 12px" }}><path d="M15 17H20L18.595 15.595A1 1 0 0118 14.879V11a6 6 0 10-12 0v3.879a1 1 0 01-.293.707L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" stroke="#D1D5DB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            <p style={{ color: "#aaa", fontSize: "14px" }}>No notifications yet</p>
          </div>
        ) : notifications.map((n, i) => (
          <div key={n.id} onClick={() => !n.read && markRead(n.id)}
            style={{ display: "flex", alignItems: "flex-start", gap: "12px", padding: "14px 16px", borderBottom: i < notifications.length - 1 ? "1px solid #F5F5F5" : "none", backgroundColor: n.read ? "#fff" : "#F0FDF4", cursor: n.read ? "default" : "pointer" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F5F5F5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <NotifIcon type={n.type} />
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: "14px", fontWeight: n.read ? "400" : "600", color: "#000", marginBottom: "2px" }}>{n.message}</p>
              <p style={{ fontSize: "12px", color: "#aaa" }}>{timeAgo(n.created_at)}</p>
            </div>
            {!n.read && <div style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#00C853", flexShrink: 0, marginTop: "6px" }} />}
          </div>
        ))}
      </div>
    </div>
  );
}