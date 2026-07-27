import { create } from "zustand";
import { devtools } from "zustand/middleware";

export interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  kyc_status: "pending" | "approved" | "flagged" | "rejected";
  role?: "customer" | "compliance_officer" | "admin";
  email_verified?: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  passcodeIsSet: boolean | null;
  isUnlocked: boolean;
  setUser: (user: User) => void;
  setToken: (token: string) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setSessionState: (user: User, passcodeIsSet: boolean) => void;
  unlock: () => void;
  lock: () => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  devtools(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      passcodeIsSet: null,
      isUnlocked: false,
      setUser: (user) => set({ user, isAuthenticated: true }, false, "setUser"),
      setToken: (token) => {
        if (typeof window !== "undefined") {
          localStorage.setItem("access_token", token);
        }
        set({ accessToken: token, isAuthenticated: true }, false, "setToken");
      },
      setTokens: (accessToken, refreshToken) => {
        if (typeof window !== "undefined") {
          localStorage.setItem("access_token", accessToken);
          localStorage.setItem("refresh_token", refreshToken);
        }
        set({ accessToken, refreshToken, isAuthenticated: true }, false, "setTokens");
      },
      setSessionState: (user, passcodeIsSet) =>
        set({ user, passcodeIsSet, isAuthenticated: true }, false, "setSessionState"),
      unlock: () => {
        if (typeof window !== "undefined") sessionStorage.setItem("app_unlocked", "true");
        set({ isUnlocked: true }, false, "unlock");
      },
      lock: () => {
        if (typeof window !== "undefined") sessionStorage.removeItem("app_unlocked");
        set({ isUnlocked: false }, false, "lock");
      },
      logout: () => {
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          sessionStorage.removeItem("app_unlocked");
        }
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, passcodeIsSet: null, isUnlocked: false }, false, "logout");
      },
    }),
    { name: "AuthStore", enabled: process.env.NODE_ENV === "development" }
  )
);
