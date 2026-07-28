import type { ReactNode } from "react";
import DashboardAuthGate from "@/components/auth/DashboardAuthGate";

export default function OnboardingLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <DashboardAuthGate>{children}</DashboardAuthGate>;
}
