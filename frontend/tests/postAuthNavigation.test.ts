import { describe, expect, it } from "vitest";
import { resolvePostAuthDestination } from "@/lib/postAuthNavigation";

const complete = {
  authenticated: true,
  email_verified: true,
  passcode_is_set: true,
  app_unlocked: true,
  kyc_onboarding_state: "approved" as const,
  role: "customer" as const,
};

describe("post-authentication routing", () => {
  it("applies authentication gates in order", () => {
    expect(resolvePostAuthDestination({ ...complete, authenticated: false })).toBe("/login");
    expect(resolvePostAuthDestination({ ...complete, email_verified: false })).toBe("/verify-registration-otp");
    expect(resolvePostAuthDestination({ ...complete, passcode_is_set: false })).toBe("/create-passcode");
    expect(resolvePostAuthDestination({ ...complete, app_unlocked: false })).toBe("/unlock");
  });

  it("routes KYC states without allowing dashboard bypass", () => {
    expect(resolvePostAuthDestination({ ...complete, kyc_onboarding_state: "not_submitted" })).toBe("/kyc");
    expect(resolvePostAuthDestination({ ...complete, kyc_onboarding_state: "pending" })).toBe("/kyc/status");
    expect(resolvePostAuthDestination({ ...complete, kyc_onboarding_state: "rejected" })).toBe("/kyc");
    expect(resolvePostAuthDestination({ ...complete, kyc_onboarding_state: "flagged" })).toBe("/kyc");
    expect(resolvePostAuthDestination(complete)).toBe("/dashboard");
  });

  it("lets staff roles reach the dashboard without completing customer KYC", () => {
    expect(resolvePostAuthDestination({ ...complete, kyc_onboarding_state: "not_submitted", role: "compliance_officer" })).toBe("/dashboard");
    expect(resolvePostAuthDestination({ ...complete, kyc_onboarding_state: "rejected", role: "admin" })).toBe("/dashboard");
  });
});
