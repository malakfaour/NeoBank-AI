import type { ReactNode } from "react";

export default function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main style={{ minHeight: "100vh", background: "#F5F5F5", display: "grid", placeItems: "center", padding: 20 }}>
      <div style={{ width: "100%", maxWidth: 420 }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="NeoBank Lebanon" style={{ width: 160 }} />
        </div>
        <section style={{ background: "#fff", borderRadius: 24, padding: 28, boxShadow: "0 2px 20px rgba(0,0,0,.08)" }}>
          <h1 style={{ fontSize: 22, margin: "0 0 4px", color: "#111" }}>{title}</h1>
          <p style={{ color: "#777", fontSize: 14, margin: "0 0 24px" }}>{subtitle}</p>
          {children}
        </section>
      </div>
    </main>
  );
}
