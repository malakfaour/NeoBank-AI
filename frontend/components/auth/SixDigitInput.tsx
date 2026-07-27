"use client";

import { useRef } from "react";

export default function SixDigitInput({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div>
      <label htmlFor="six-digit-input" style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#333", marginBottom: 10 }}>{label}</label>
      <div
        onClick={() => inputRef.current?.focus()}
        style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8, cursor: "text", position: "relative" }}
      >
        {Array.from({ length: 6 }, (_, index) => (
          <span key={index} aria-hidden="true" style={{ height: 54, borderRadius: 14, border: `2px solid ${value[index] ? "#00C853" : "#E5E7EB"}`, display: "grid", placeItems: "center", fontSize: 24 }}>
            {value[index] ? "•" : ""}
          </span>
        ))}
        <input
          ref={inputRef}
          id="six-digit-input"
          aria-label={label}
          inputMode="numeric"
          autoComplete="one-time-code"
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
          style={{ position: "absolute", opacity: 0, width: 1, height: 1 }}
        />
      </div>
    </div>
  );
}
