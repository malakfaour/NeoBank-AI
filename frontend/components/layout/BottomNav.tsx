"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { usePreferences } from "@/components/providers/AppPreferences";
import { useAuthStore } from "@/store/authStore";

const labelKeys: Record<string, string> = { Home: "nav.home", Transfer: "nav.transfer", Exchange: "nav.exchange", History: "nav.history", Profile: "nav.profile", "KYC Review": "nav.kycReview", Risk: "nav.risk", Users: "nav.users", Ledger: "nav.ledger" };

const links = [
  { href: "/dashboard", label: "Home", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H5a1 1 0 01-1-1V9.5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/transfer", label: "Transfer", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/exchange", label: "Exchange", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/transactions", label: "History", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg> },
  { href: "/profile", label: "Profile", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
];

const adminLinks = [
  { href: "/admin/kyc", label: "KYC Review", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/admin/flagged-transactions", label: "Risk", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 9v4m0 4h.01M10.3 3.9L2.1 18A2 2 0 004 21h16a2 2 0 001.9-3L13.7 3.9a2 2 0 00-3.4 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg> },
  { href: "/admin/users", label: "Users", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8M22 21v-2a4 4 0 00-3-3.9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg> },
  { href: "/admin/transactions", label: "Ledger", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M6 3h12a2 2 0 012 2v16l-4-2-4 2-4-2-4 2V5a2 2 0 012-2zM8 8h8M8 12h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
];

export default function BottomNav() {
  const pathname = usePathname();
  const { t } = usePreferences();
  const role = useAuthStore((state) => state.user?.role);
  const visibleLinks = role === "admin" || role === "compliance_officer" ? adminLinks : links;
  return (
    <nav className="mobile-bottom-nav" style={{ position: "fixed", bottom: 0, left: 0, right: 0, backgroundColor: "var(--surface)", borderTop: "1px solid var(--line)", zIndex: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", padding: "8px 8px" }}>
        {visibleLinks.map(({ href, label, svg }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href} className={`bottom-nav-link${active ? " is-active" : ""}`} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "2px", padding: "6px 12px", borderRadius: "14px", textDecoration: "none", color: active ? "#00C853" : "#aaa" }}>
              {svg}
              <span style={{ fontSize: "10px", fontWeight: "600" }}>{t(labelKeys[label])}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
