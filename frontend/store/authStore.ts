import { create } from "zustand";
import { devtools } from "zustand/middleware";

interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  kyc_status: "pending" | "approved" | "flagged" | "rejected";
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  setUser: (user: User) => void;
  setToken: (token: string) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  devtools(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
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
      logout: () => {
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
        }
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false }, false, "logout");
      },
    }),
    { name: "AuthStore", enabled: process.env.NODE_ENV === "development" }
  )
);
