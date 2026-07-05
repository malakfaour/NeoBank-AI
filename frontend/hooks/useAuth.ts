import { useAuthStore } from "@/store/authStore";
import api from "@/lib/axios";

export function useAuth() {
  const { user, isAuthenticated, setUser, setTokens, logout } = useAuthStore();

  const login = async (phone: string, passcode: string) => {
    const res = await api.post("/auth/login", { phone, passcode });
    const { access_token, refresh_token, user } = res.data;
    if (access_token && refresh_token) {
      setTokens(access_token, refresh_token);
    } else if (access_token) {
      useAuthStore.getState().setToken(access_token);
    }
    if (user) {
      setUser(user);
    }
    return user;
  };

  return { user, isAuthenticated, login, logout };
}
