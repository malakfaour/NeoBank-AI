import type { ReactNode } from "react";
import type { Metadata } from "next";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import BottomNav from "@/components/layout/BottomNav";
import ChatWidget from "@/components/chat/ChatWidget";

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
      <ChatWidget />
    </>
  );
}