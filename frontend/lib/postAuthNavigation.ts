import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

export type KycOnboardingState =
  | "not_submitted"
  | "pending"
  | "rejected"
  | "flagged"
  | "approved";

export type UserRole = "customer" | "compliance_officer" | "admin";

export interface AuthRoutingState {
  authenticated: boolean;
  email_verified: boolean;
  passcode_is_set: boolean;
  app_unlocked: boolean;
  kyc_onboarding_state: KycOnboardingState;
  role: UserRole;
}

export function resolvePostAuthDestination(state: AuthRoutingState): string {
  if (!state.authenticated) return "/login";
  if (!state.email_verified) return "/verify-registration-otp";
  if (!state.passcode_is_set) return "/create-passcode";
  if (!state.app_unlocked) return "/unlock";
  // Staff accounts review other users' KYC - they land on the admin console,
  // not the customer dashboard (which they have no wallets/transactions for).
  if (state.role === "admin" || state.role === "compliance_officer") return "/admin/kyc";
  // Customers must complete the wizard at least once before touching the dashboard.
  if (state.kyc_onboarding_state === "not_submitted") return "/kyc";
  // Once submitted (pending/flagged/rejected/approved), the dashboard is reachable -
  // KYCActionLock gates the individual money-moving actions until approval.
  return "/dashboard";
}

export async function getPostAuthDestination(): Promise<string> {
  try {
    const response = await api.get("/auth/status");
    const data = response.data;
    useAuthStore.getState().setSessionState(
      { ...data.user, kyc_onboarding_state: data.kyc_onboarding_state },
      data.passcode_is_set,
    );
    return resolvePostAuthDestination({
      authenticated: data.authenticated === true,
      email_verified: data.email_verified === true,
      passcode_is_set: data.passcode_is_set === true,
      app_unlocked:
        typeof window !== "undefined" &&
        sessionStorage.getItem("app_unlocked") === "true",
      kyc_onboarding_state: data.kyc_onboarding_state,
      role: data.user?.role ?? "customer",
    });
  } catch {
    return "/login";
  }
}
