"use client";

import { useState } from "react";
import api from "@/lib/axios";

interface ChatMessage { role: "user" | "bot"; text: string; }
interface PendingAction { type?: string; method?: string; recipient?: string; amount?: string; currency?: string; }

export default function ChatWidget() {
  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [chatLoading, setChatLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [showPasscode, setShowPasscode] = useState(false);
  const [passcode, setPasscode] = useState("");
  const [passcodeLoading, setPasscodeLoading] = useState(false);
  const [passcodeError, setPasscodeError] = useState("");

  const sendMessage = async (text: string, actionToken?: string) => {
    if (!text.trim()) return;
    if (!actionToken) {
      setMessages((prev) => [...prev, { role: "user", text }]);
    }
    setInput("");
    setChatLoading(true);
    try {
      const headers: Record<string, string> = {};
      if (actionToken) headers["X-Action-Token"] = actionToken;
      const res = await api.post("/chatbot/message", { session_id: sessionId, message: text }, { headers });
      const reply = res.data.reply ?? "...";
      setMessages((prev) => [...prev, { role: "bot", text: reply }]);
      if (res.data.confirmation_required && res.data.pending_action) {
        setPendingAction(res.data.pending_action);
      } else {
        setPendingAction(null);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "Sorry, something went wrong." }]);
    } finally { setChatLoading(false); }
  };

  const handleConfirmClick = () => {
    setShowPasscode(true);
    setPasscode("");
    setPasscodeError("");
  };

  const handlePasscodeSubmit = async () => {
    if (passcode.length < 6) return;
    setPasscodeLoading(true);
    setPasscodeError("");
    try {
      const res = await api.post("/auth/passcode/verify", { passcode });
      const actionToken = res.data.action_token;
      setShowPasscode(false);
      setPendingAction(null);
      setMessages((prev) => [...prev, { role: "user", text: "confirm" }]);
      await sendMessage("confirm", actionToken);
    } catch {
      setPasscodeError("Incorrect passcode. Try again.");
    } finally { setPasscodeLoading(false); }
  };

  const handleCancel = async () => {
    setPendingAction(null);
    setShowPasscode(false);
    setMessages((prev) => [...prev, { role: "user", text: "cancel" }]);
    await sendMessage("cancel");
  };

  return (
    <>
      {/* Floating button */}
      <button onClick={() => setChatOpen(true)}
        style={{ position: "fixed", bottom: "90px", right: "20px", width: "56px", height: "56px", borderRadius: "50%", backgroundColor: "#00C853", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 16px rgba(0,200,83,0.4)", zIndex: 50 }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>

      {chatOpen && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", zIndex: 100, display: "flex", alignItems: "flex-end" }}>
          <div style={{ backgroundColor: "#fff", borderRadius: "24px 24px 0 0", width: "100%", height: "70vh", display: "flex", flexDirection: "column", boxSizing: "border-box" }}>

            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 20px 12px", borderBottom: "1px solid #F5F5F5" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "50%", backgroundColor: "#00C853", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </div>
                <div>
                  <p style={{ fontSize: "14px", fontWeight: "700", color: "#000" }}>Neo Assistant</p>
                  <p style={{ fontSize: "11px", color: "#00C853" }}>● Online</p>
                </div>
              </div>
              <button onClick={() => setChatOpen(false)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "20px", color: "#aaa" }}>✕</button>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
              {messages.length === 0 && (
                <div style={{ textAlign: "center", marginTop: "40px" }}>
                  <p style={{ fontSize: "14px", color: "#aaa" }}>Hi! How can I help you today?</p>
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
                  <div style={{ maxWidth: "75%", backgroundColor: m.role === "user" ? "#00C853" : "#F5F5F5", color: m.role === "user" ? "#fff" : "#000", borderRadius: m.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px", padding: "10px 14px", fontSize: "14px" }}>
                    {m.text}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div style={{ display: "flex", justifyContent: "flex-start" }}>
                  <div style={{ backgroundColor: "#F5F5F5", borderRadius: "18px 18px 18px 4px", padding: "10px 14px" }}>
                    <p style={{ color: "#aaa", fontSize: "14px" }}>Typing...</p>
                  </div>
                </div>
              )}

              {/* Confirm card */}
              {pendingAction && !showPasscode && (
                <div style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "16px", padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                  <p style={{ fontSize: "14px", fontWeight: "700", color: "#000" }}>🏦 Confirm Transfer</p>
                  {pendingAction.recipient && <p style={{ fontSize: "13px", color: "#555" }}>To: {pendingAction.recipient}</p>}
                  {pendingAction.amount && pendingAction.currency && (
                    <p style={{ fontSize: "13px", color: "#555" }}>Amount: {pendingAction.amount} {pendingAction.currency}</p>
                  )}
                  <p style={{ fontSize: "11px", color: "#aaa" }}>⏱ Expires in 5 minutes</p>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button onClick={handleConfirmClick} style={{ flex: 1, backgroundColor: "#00C853", color: "#fff", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "700", cursor: "pointer", fontSize: "13px" }}>
                      Confirm
                    </button>
                    <button onClick={handleCancel} style={{ flex: 1, backgroundColor: "#F5F5F5", color: "#333", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "600", cursor: "pointer", fontSize: "13px" }}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Passcode sheet */}
              {showPasscode && (
                <div style={{ backgroundColor: "#fff", border: "1.5px solid #E5E7EB", borderRadius: "16px", padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                  <p style={{ fontSize: "14px", fontWeight: "700", color: "#000" }}>🔐 Enter Passcode</p>
                  <p style={{ fontSize: "12px", color: "#aaa" }}>Verify your identity to complete the transfer</p>
                  <input type="password" placeholder="••••••" maxLength={6} value={passcode}
                    onChange={(e) => { setPasscode(e.target.value.replace(/\D/g, "")); setPasscodeError(""); }}
                    style={{ width: "100%", border: "1.5px solid #E5E7EB", borderRadius: "12px", padding: "10px 14px", fontSize: "20px", letterSpacing: "8px", outline: "none", boxSizing: "border-box", textAlign: "center" }} />
                  {passcodeError && <p style={{ color: "#EF4444", fontSize: "12px" }}>{passcodeError}</p>}
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button onClick={handlePasscodeSubmit} disabled={passcode.length < 6 || passcodeLoading}
                      style={{ flex: 1, backgroundColor: passcode.length < 6 ? "#E5E7EB" : "#00C853", color: passcode.length < 6 ? "#999" : "#fff", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "700", cursor: passcode.length < 6 ? "not-allowed" : "pointer", fontSize: "13px" }}>
                      {passcodeLoading ? "Verifying..." : "Verify"}
                    </button>
                    <button onClick={() => { setShowPasscode(false); setPasscode(""); }} style={{ flex: 1, backgroundColor: "#F5F5F5", color: "#333", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "600", cursor: "pointer", fontSize: "13px" }}>
                      Back
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Quick action chips */}
            {messages.length === 0 && (
              <div style={{ padding: "0 16px 12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
                {[
                  { label: "💰 My Balance", msg: "What is my current balance?" },
                  { label: "📋 Last Transactions", msg: "Show me my last transactions" },
                  { label: "💱 Exchange Rate", msg: "What is the current USD to LBP exchange rate?" },
                ].map(({ label, msg }) => (
                  <button key={label} onClick={() => sendMessage(msg)}
                    style={{ padding: "8px 14px", borderRadius: "20px", border: "1.5px solid #00C853", backgroundColor: "#F0FDF4", color: "#00C853", fontSize: "12px", fontWeight: "600", cursor: "pointer", whiteSpace: "nowrap" }}>
                    {label}
                  </button>
                ))}
              </div>
            )}

            {/* Input */}
            <div style={{ padding: "12px 16px", borderTop: "1px solid #F5F5F5", display: "flex", gap: "10px", alignItems: "center" }}>
              <input value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !chatLoading && sendMessage(input)}
                placeholder="Type a message..."
                style={{ flex: 1, border: "1.5px solid #E5E7EB", borderRadius: "14px", padding: "10px 14px", fontSize: "14px", outline: "none" }} />
              <button onClick={() => sendMessage(input)} disabled={!input.trim() || chatLoading}
                style={{ width: "40px", height: "40px", borderRadius: "50%", backgroundColor: input.trim() ? "#00C853" : "#E5E7EB", border: "none", cursor: input.trim() ? "pointer" : "not-allowed", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke={input.trim() ? "#fff" : "#999"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}