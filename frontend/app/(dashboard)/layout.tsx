import type { Metadata } from "next";
import type { ReactNode } from "react";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import BottomNav from "@/components/layout/BottomNav";

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <Sidebar />
      <div className="dashboard-main">
        <Header />
        {children}
      </div>
      <BottomNav />
    </>
  );
}
