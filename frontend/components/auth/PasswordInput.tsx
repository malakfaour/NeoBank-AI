"use client";

import { useState } from "react";

export default function PasswordInput({
  label,
  value,
  onChange,
  autoComplete,
  error,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "new-password" | "current-password";
  error?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <label style={{ display: "block", marginBottom: 16, color: "#333", fontSize: 13, fontWeight: 600 }}>
      {label}
      <span style={{ display: "flex", marginTop: 8, border: `1.5px solid ${error ? "#EF4444" : "#E5E7EB"}`, borderRadius: 14 }}>
        <input
          aria-invalid={Boolean(error)}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          style={{ flex: 1, minWidth: 0, border: 0, outline: 0, padding: "12px 16px", borderRadius: 14, fontSize: 14 }}
        />
        <button
          type="button"
          aria-label={visible ? "Hide password" : "Show password"}
          onClick={() => setVisible((current) => !current)}
          style={{ border: 0, background: "transparent", cursor: "pointer", padding: "0 14px", color: "#555" }}
        >
          {visible ? "Hide" : "Show"}
        </button>
      </span>
      {error && <span style={{ display: "block", color: "#EF4444", fontSize: 12, marginTop: 6 }}>{error}</span>}
    </label>
  );
}
