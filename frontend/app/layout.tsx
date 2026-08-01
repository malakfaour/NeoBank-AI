import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import StartupSessionGate from "@/components/auth/StartupSessionGate";
import { AppPreferences } from "@/components/providers/AppPreferences";

export const metadata: Metadata = {
  title: "NeoBank Lebanon",
  description: "NeoBank Lebanon frontend application",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body><AppPreferences><StartupSessionGate>{children}</StartupSessionGate></AppPreferences></body>
    </html>
  );
}
