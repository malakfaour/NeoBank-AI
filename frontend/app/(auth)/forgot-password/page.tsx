"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import AuthCard from "@/components/auth/AuthCard";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;

    const normalizedEmail = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError("Enter a valid email address.");
      return;
    }

    setError("");
    setLoading(true);
    try {
      await api.post("/auth/password/forgot", { email: normalizedEmail });
      sessionStorage.setItem("reset_email", normalizedEmail);
      router.replace("/verify-reset-otp");
    } catch (requestError: unknown) {
      const detail = (
        requestError as { response?: { data?: { detail?: string } } }
      ).response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "We could not send the verification code. Check your connection and try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthCard
      title="Forgot password"
      subtitle="We’ll send a password-reset verification code to your email."
    >
      <form onSubmit={handleSubmit} noValidate>
        <label style={{ display: "block", color: "#333", fontSize: 13, fontWeight: 600 }}>
          Email
          <input
            aria-label="Email"
            aria-invalid={Boolean(error)}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setError("");
            }}
            disabled={loading}
            style={{
              display: "block",
              width: "100%",
              boxSizing: "border-box",
              marginTop: 8,
              padding: 13,
              border: `1.5px solid ${error ? "#EF4444" : "#E5E7EB"}`,
              borderRadius: 14,
            }}
          />
        </label>
        {error && (
          <p role="alert" style={{ color: "#B91C1C", background: "#FEF2F2", padding: 12, borderRadius: 12 }}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          style={{
            width: "100%",
            marginTop: 18,
            padding: 14,
            border: 0,
            borderRadius: 14,
            background: loading ? "#86EFAC" : "#00C853",
            color: "#fff",
            fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Sending…" : "Send code"}
        </button>
      </form>
    </AuthCard>
  );
}
