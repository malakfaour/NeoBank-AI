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

const typeIcon: Record<string, string> = {
  KYC_APPROVED: "✅", KYC_FLAGGED: "⚠️", KYC_REJECTED: "❌",
  TRANSFER: "💸", TOPUP: "➕", EXCHANGE: "💱", DEFAULT: "🔔",
};

export default function NotificationsPage() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

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

  // SSE real-time stream
  const token = localStorage.getItem("access_token");
  if (token) {
    const es = new EventSource(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/notifications/stream?token=${token}`);
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type !== "ping") {
          setNotifications((prev) => [data, ...prev]);
        }
      } catch { /* ignore parse errors */ }
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

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button onClick={() => router.back()}
            style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
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

      <div style={{ backgroundColor: "#fff", borderRadius: "20px", overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "32px", textAlign: "center" }}><p style={{ color: "#aaa" }}>Loading...</p></div>
        ) : notifications.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center" }}><p style={{ color: "#aaa", fontSize: "14px" }}>No notifications yet</p></div>
        ) : notifications.map((n, i) => (
          <div key={n.id} onClick={() => !n.read && markRead(n.id)}
            style={{ display: "flex", alignItems: "flex-start", gap: "12px", padding: "14px 16px", borderBottom: i < notifications.length - 1 ? "1px solid #F5F5F5" : "none", backgroundColor: n.read ? "#fff" : "#F0FDF4", cursor: n.read ? "default" : "pointer" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "12px", backgroundColor: "#F5F5F5", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px", flexShrink: 0 }}>
              {typeIcon[n.type] ?? typeIcon.DEFAULT}
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