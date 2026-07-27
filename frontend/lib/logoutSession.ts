import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

export async function logoutSession(): Promise<void> {
  const accessToken = typeof window === "undefined" ? null : localStorage.getItem("access_token");
  const refreshToken = typeof window === "undefined" ? null : localStorage.getItem("refresh_token");
  try {
    if (accessToken && refreshToken) {
      await api.post("/auth/logout", {
        access_token: accessToken,
        refresh_token: refreshToken,
      });
    }
  } finally {
    useAuthStore.getState().logout();
  }
}
