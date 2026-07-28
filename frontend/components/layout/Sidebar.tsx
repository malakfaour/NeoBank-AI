"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logoutSession } from "@/lib/logoutSession";
import { useAuthStore } from "@/store/authStore";
import Image from "next/image";
const links = [
  { href: "/dashboard", label: "Dashboard", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H5a1 1 0 01-1-1V9.5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/transfer", label: "Transfer", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/exchange", label: "Exchange", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/transactions", label: "Transactions", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg> },
  { href: "/profile", label: "Profile", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
];

const adminLink = { href: "/admin/kyc", label: "KYC Review", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> };
const fraudAdminLink = { href: "/admin/flagged-transactions", label: "Flagged Transactions", svg: <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 9v4m0 4h.01M10.29 3.86l-8.18 14.18A2 2 0 004 21h16a2 2 0 001.89-2.96L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> };

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const role = useAuthStore((s) => s.user?.role);
  const visibleLinks = role === "admin" || role === "compliance_officer" ? [...links, adminLink, fraudAdminLink] : links;

  return (
    <aside style={{ position: "fixed", left: 0, top: 0, height: "100%", width: "240px", backgroundColor: "#fff", borderRight: "1px solid #F0F0F0", padding: "24px 16px", flexDirection: "column", zIndex: 20 }}
      className="lg-sidebar">
      <div style={{ marginBottom: "32px", paddingLeft: "8px" }}>
      <Image
  src="/logo.svg"
  alt="NeoBank Lebanon"
  width={140}
  height={55}
/> </div>
      <nav style={{ display: "flex", flexDirection: "column", gap: "4px", flex: 1 }}>
        {visibleLinks.map(({ href, label, svg }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href} style={{
              display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", borderRadius: "14px",
              fontSize: "14px", fontWeight: "600", textDecoration: "none",
              backgroundColor: active ? "#F0FDF4" : "transparent",
              color: active ? "#00C853" : "#666",
            }}>
              {svg}
              {label}
            </Link>
          );
        })}
      </nav>
      <button onClick={async () => { await logoutSession(); router.replace("/login"); }}
        style={{ display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", borderRadius: "14px", border: "none", backgroundColor: "transparent", fontSize: "14px", fontWeight: "600", color: "#aaa", cursor: "pointer" }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h6a2 2 0 012 2v1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>Sign out
      </button>
    </aside>
  );
}




