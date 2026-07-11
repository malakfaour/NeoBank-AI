"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface Session {
  session_id: string;
  device_name: string | null;
  ip_address: string | null;
  last_seen: string;
  is_active: boolean;
}

function timeAgo(d: string) {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function deviceIcon(name: string | null): string {
  if (!name) return "💻";
  const n = name.toLowerCase();
  if (n.includes("mobile") || n.includes("android") || n.includes("iphone")) return "📱";
  if (n.includes("tablet") || n.includes("ipad")) return "📲";
  return "💻";
}

export default function DevicesPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await api.get("/auth/sessions");
      setSessions(Array.isArray(res.data) ? res.data : []);
    } catch {
      setError("Could not load devices. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

 useEffect(() => {
  let cancelled = false;
  const load = async () => { if (!cancelled) await fetchSessions(); };
  load();
  return () => { cancelled = true; };
}, [fetchSessions]);

  const handleRemove = async (session_id: string) => {
    setRemoving(session_id);
    try {
      await api.delete(`/auth/sessions/${session_id}`);
      setSessions((prev) => prev.filter((s) => s.session_id !== session_id));
      setConfirmId(null);
    } catch {
      setError("Could not remove device. Please try again.");
    } finally {
      setRemoving(null); }
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F5", padding: "20px", paddingBottom: "80px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
        <button onClick={() => router.back()}
          style={{ width: "36px", height: "36px", borderRadius: "12px", border: "1px solid #E5E7EB", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M12 19l-7-7 7-7" stroke="#333" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#000" }}>Active Devices</h2>
      </div>

      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "12px", padding: "12px 16px", color: "#DC2626", fontSize: "13px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center" }}>
          <p style={{ color: "#aaa", fontSize: "14px" }}>Loading devices...</p>
        </div>
      ) : sessions.length === 0 ? (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", padding: "32px", textAlign: "center" }}>
          <p style={{ fontSize: "32px", marginBottom: "12px" }}>📱</p>
          <p style={{ color: "#aaa", fontSize: "14px" }}>No active sessions found</p>
        </div>
      ) : (
        <div style={{ backgroundColor: "#fff", borderRadius: "20px", overflow: "hidden" }}>
          <p style={{ color: "#aaa", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px", padding: "16px 16px 8px" }}>
            {sessions.length} active {sessions.length === 1 ? "session" : "sessions"}
          </p>
          {sessions.map((s, i) => (
            <div key={s.session_id} style={{ display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", borderBottom: i < sessions.length - 1 ? "1px solid #F5F5F5" : "none" }}>
              <div style={{ width: "44px", height: "44px", borderRadius: "14px", backgroundColor: "#F0FDF4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "20px", flexShrink: 0 }}>
                {deviceIcon(s.device_name)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: "14px", fontWeight: "600", color: "#000", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {s.device_name ?? "Unknown Device"}
                </p>
                <p style={{ fontSize: "12px", color: "#aaa", marginTop: "2px" }}>
                  {s.ip_address ?? "Unknown IP"} · {timeAgo(s.last_seen)}
                </p>
              </div>
              <button onClick={() => setConfirmId(s.session_id)}
                style={{ fontSize: "12px", fontWeight: "600", color: "#EF4444", background: "none", border: "1px solid #FECACA", borderRadius: "8px", padding: "4px 10px", cursor: "pointer", flexShrink: 0 }}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <p style={{ color: "#aaa", fontSize: "12px", textAlign: "center", marginTop: "16px" }}>
        Removing a device will log it out immediately.
      </p>

      {/* Confirm modal */}
      {confirmId && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", zIndex: 100, display: "flex", alignItems: "flex-end" }}
          onClick={(e) => { if (e.target === e.currentTarget) setConfirmId(null); }}>
          <div style={{ backgroundColor: "#fff", borderRadius: "24px 24px 0 0", padding: "24px", width: "100%", boxSizing: "border-box" }}>
            <h3 style={{ fontSize: "16px", fontWeight: "700", color: "#000", marginBottom: "8px" }}>Remove device?</h3>
            <p style={{ fontSize: "14px", color: "#666", marginBottom: "20px" }}>This will immediately log out the session on that device.</p>
            <div style={{ display: "flex", gap: "12px" }}>
              <button onClick={() => setConfirmId(null)}
                style={{ flex: 1, padding: "14px", borderRadius: "14px", border: "1.5px solid #E5E7EB", backgroundColor: "#fff", fontSize: "14px", fontWeight: "600", cursor: "pointer", color: "#333" }}>
                Cancel
              </button>
              <button onClick={() => handleRemove(confirmId)} disabled={!!removing}
                style={{ flex: 1, padding: "14px", borderRadius: "14px", border: "none", backgroundColor: removing ? "#FECACA" : "#EF4444", color: "#fff", fontSize: "14px", fontWeight: "700", cursor: removing ? "not-allowed" : "pointer" }}>
                {removing ? "Removing..." : "Remove"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}