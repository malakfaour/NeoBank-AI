"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/dashboard", label: "Home", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H5a1 1 0 01-1-1V9.5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/transfer", label: "Transfer", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/exchange", label: "Exchange", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  { href: "/transactions", label: "History", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg> },
  { href: "/profile", label: "Profile", svg: <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg> },
];

export default function BottomNav() {
  const pathname = usePathname();
  return (
    <nav className="mobile-bottom-nav" style={{ position: "fixed", bottom: 0, left: 0, right: 0, backgroundColor: "#fff", borderTop: "1px solid #F0F0F0", zIndex: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", padding: "8px 8px" }}>
        {links.map(({ href, label, svg }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "2px", padding: "6px 12px", borderRadius: "14px", textDecoration: "none", color: active ? "#00C853" : "#aaa" }}>
              {svg}
              <span style={{ fontSize: "10px", fontWeight: "600" }}>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
