import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

export type KycOnboardingState =
  | "not_submitted"
  | "pending"
  | "rejected"
  | "approved";

export interface AuthRoutingState {
  authenticated: boolean;
  email_verified: boolean;
  passcode_is_set: boolean;
  app_unlocked: boolean;
  kyc_onboarding_state: KycOnboardingState;
}

export function resolvePostAuthDestination(state: AuthRoutingState): string {
  if (!state.authenticated) return "/login";
  if (!state.email_verified) return "/verify-registration-otp";
  if (!state.passcode_is_set) return "/create-passcode";
  if (!state.app_unlocked) return "/unlock";
  if (state.kyc_onboarding_state === "approved") return "/dashboard";
  if (state.kyc_onboarding_state === "pending") return "/kyc/status";
  return "/kyc";
}

export async function getPostAuthDestination(): Promise<string> {
  try {
    const response = await api.get("/auth/status");
    const data = response.data;
    useAuthStore.getState().setSessionState(data.user, data.passcode_is_set);
    return resolvePostAuthDestination({
      authenticated: data.authenticated === true,
      email_verified: data.email_verified === true,
      passcode_is_set: data.passcode_is_set === true,
      app_unlocked:
        typeof window !== "undefined" &&
        sessionStorage.getItem("app_unlocked") === "true",
      kyc_onboarding_state: data.kyc_onboarding_state,
    });
  } catch {
    return "/login";
  }
}
