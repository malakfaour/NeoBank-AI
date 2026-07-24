import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { redirectToLogin } from "@/lib/authNavigation";
import { useAuthStore } from "@/store/authStore";

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

const api = axios.create({
  baseURL: (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

let refreshPromise: Promise<string | null> | null = null;

function readToken(key: "access_token" | "refresh_token"): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return localStorage.getItem(key);
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = readToken("refresh_token");

  if (!refreshToken) {
    return null;
  }

  const response = await axios.post(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/auth/refresh`,
    { refresh_token: refreshToken },
    {
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  const { access_token, refresh_token } = response.data ?? {};

  if (!access_token || !refresh_token) {
    return null;
  }

  useAuthStore.getState().setTokens(access_token, refresh_token);
  return access_token;
}

function logoutAndRedirect() {
  useAuthStore.getState().logout();
  redirectToLogin();
}

api.interceptors.request.use((config) => {
  const token = readToken("access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined;
    const status = error.response?.status;

    if (!originalRequest || status !== 401) {
      return Promise.reject(error);
    }

    // Never attempt token refresh recursively for authentication endpoints.
    if (
      originalRequest.url?.includes("/auth/login") ||
      originalRequest.url?.includes("/auth/refresh")
    ) {
      return Promise.reject(error);
    }

    // The request was already retried with a refreshed token and still failed.
    if (originalRequest._retry) {
      logoutAndRedirect();
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null;
      });

      const newAccessToken = await refreshPromise;

      if (!newAccessToken) {
        logoutAndRedirect();
        return Promise.reject(error);
      }

      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      return api(originalRequest);
    } catch (refreshError) {
      logoutAndRedirect();
      return Promise.reject(refreshError);
    }
  }
);

export default api;
