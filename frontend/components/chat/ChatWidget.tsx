"use client";

import { useState } from "react";
import api from "@/lib/axios";

interface ChatMessage { role: "user" | "bot"; text: string; }
interface ConfirmCard { amount?: string; recipient?: string; }

export default function ChatWidget() {
  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [chatLoading, setChatLoading] = useState(false);
  const [confirmCard, setConfirmCard] = useState<ConfirmCard | null>(null);

  const sendMessage = async (text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setChatLoading(true);
    setConfirmCard(null);
    try {
      const res = await api.post("/chatbot/message", { session_id: sessionId, message: text });
      const reply = res.data.reply ?? res.data.message ?? "...";
      setMessages((prev) => [...prev, { role: "bot", text: reply }]);
      if (res.data.confirmation_required) {
        setConfirmCard({ amount: res.data.amount, recipient: res.data.recipient });
      }
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "Sorry, something went wrong." }]);
    } finally { setChatLoading(false); }
  };

  const handleConfirm = () => { setConfirmCard(null); sendMessage("confirm"); };
  const handleCancel = () => { setConfirmCard(null); setMessages((prev) => [...prev, { role: "bot", text: "Action cancelled." }]); };

  return (
    <>
      {/* Floating button */}
      <button onClick={() => setChatOpen(true)}
        style={{ position: "fixed", bottom: "90px", right: "20px", width: "56px", height: "56px", borderRadius: "50%", backgroundColor: "#00C853", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 16px rgba(0,200,83,0.4)", zIndex: 50 }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>

      {/* Chat panel */}
      {chatOpen && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", zIndex: 100, display: "flex", alignItems: "flex-end" }}>
          <div style={{ backgroundColor: "#fff", borderRadius: "24px 24px 0 0", width: "100%", height: "70vh", display: "flex", flexDirection: "column", boxSizing: "border-box" }}>
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
              {confirmCard && (
                <div style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "16px", padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                  <p style={{ fontSize: "14px", fontWeight: "600", color: "#000" }}>Confirm action?</p>
                  {confirmCard.recipient && <p style={{ fontSize: "13px", color: "#555" }}>To: {confirmCard.recipient}</p>}
                  {confirmCard.amount && <p style={{ fontSize: "13px", color: "#555" }}>Amount: {confirmCard.amount}</p>}
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button onClick={handleConfirm} style={{ flex: 1, backgroundColor: "#00C853", color: "#fff", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "700", cursor: "pointer" }}>Confirm</button>
                    <button onClick={handleCancel} style={{ flex: 1, backgroundColor: "#F5F5F5", color: "#333", border: "none", borderRadius: "10px", padding: "10px", fontWeight: "600", cursor: "pointer" }}>Cancel</button>
                  </div>
                </div>
              )}
            </div>

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