import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "NeoBank Lebanon", template: "%s | NeoBank Lebanon" },
  description: "AI-powered digital banking for Lebanon. Manage your USD and LBP accounts, send money, exchange currency, and more.",
  keywords: ["neobank", "lebanon", "banking", "fintech", "USD", "LBP"],
  viewport: "width=device-width, initial-scale=1",
  robots: "index, follow",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0, backgroundColor: "#F5F5F5" }}>
        {children}
      </body>
    </html>
  );
}