import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { redirectToLoginMock } = vi.hoisted(() => ({
  redirectToLoginMock: vi.fn(),
}));

vi.mock("@/lib/authNavigation", () => ({
  redirectToLogin: redirectToLoginMock,
}));

import api from "@/lib/axios";
import { useAuthStore } from "@/store/authStore";

const originalAdapter = api.defaults.adapter;

function createResponse<T>(
  config: InternalAxiosRequestConfig,
  status: number,
  data: T
): AxiosResponse<T> {
  return {
    config,
    data,
    headers: new AxiosHeaders(),
    status,
    statusText: status === 200 ? "OK" : "Unauthorized",
  };
}

function createUnauthorizedError(
  config: InternalAxiosRequestConfig
): AxiosError {
  return new AxiosError(
    "Unauthorized",
    AxiosError.ERR_BAD_REQUEST,
    config,
    undefined,
    createResponse(config, 401, { detail: "Unauthorized" })
  );
}

function setAuthenticatedState() {
  localStorage.setItem("access_token", "old-access-token");
  localStorage.setItem("refresh_token", "valid-refresh-token");

  useAuthStore.setState({
    user: {
      id: "1",
      full_name: "Test User",
      email: "test@example.com",
      phone: "71123456",
      kyc_status: "approved",
    },
    accessToken: "old-access-token",
    refreshToken: "valid-refresh-token",
    isAuthenticated: true,
  });
}

describe("Axios authentication interceptors", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    redirectToLoginMock.mockReset();
    localStorage.clear();

    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
  });

  it("attaches the access token to authenticated requests", async () => {
    localStorage.setItem("access_token", "access-token-123");

    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) =>
      createResponse(config, 200, { ok: true })
    );

    api.defaults.adapter = adapter;

    await api.get("/accounts/balance");

    expect(adapter).toHaveBeenCalledTimes(1);

    const requestConfig = adapter.mock.calls[0][0];

    expect(requestConfig.headers.get("Authorization")).toBe(
      "Bearer access-token-123"
    );
  });

  it("refreshes the token after the first 401 and retries the request", async () => {
    setAuthenticatedState();

    const refreshSpy = vi.spyOn(axios, "post").mockResolvedValue({
      data: {
        access_token: "new-access-token",
        refresh_token: "new-refresh-token",
      },
    });

    let requestCount = 0;

    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      requestCount += 1;

      if (requestCount === 1) {
        throw createUnauthorizedError(config);
      }

      return createResponse(config, 200, { ok: true });
    });

    api.defaults.adapter = adapter;

    const response = await api.get("/accounts/balance");

    expect(response.data).toEqual({ ok: true });
    expect(adapter).toHaveBeenCalledTimes(2);
    expect(refreshSpy).toHaveBeenCalledTimes(1);

    expect(refreshSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/refresh"),
      {
        refresh_token: "valid-refresh-token",
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    const retriedConfig = adapter.mock.calls[1][0];

    expect(retriedConfig.headers.get("Authorization")).toBe(
      "Bearer new-access-token"
    );

    expect(localStorage.getItem("access_token")).toBe("new-access-token");
    expect(localStorage.getItem("refresh_token")).toBe("new-refresh-token");

    expect(useAuthStore.getState().accessToken).toBe("new-access-token");
    expect(useAuthStore.getState().refreshToken).toBe("new-refresh-token");
    expect(redirectToLoginMock).not.toHaveBeenCalled();
  });

  it("logs out and redirects when the retried request also returns 401", async () => {
    setAuthenticatedState();

    const refreshSpy = vi.spyOn(axios, "post").mockResolvedValue({
      data: {
        access_token: "new-access-token",
        refresh_token: "new-refresh-token",
      },
    });

    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      throw createUnauthorizedError(config);
    });

    api.defaults.adapter = adapter;

    await expect(api.get("/accounts/balance")).rejects.toMatchObject({
      response: {
        status: 401,
      },
    });

    expect(adapter).toHaveBeenCalledTimes(2);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(redirectToLoginMock).toHaveBeenCalledTimes(1);

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("logs out and redirects when token refresh fails", async () => {
    setAuthenticatedState();

    const refreshSpy = vi
      .spyOn(axios, "post")
      .mockRejectedValue(new Error("Refresh service unavailable"));

    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      throw createUnauthorizedError(config);
    });

    api.defaults.adapter = adapter;

    await expect(api.get("/accounts/balance")).rejects.toThrow(
      "Refresh service unavailable"
    );

    expect(adapter).toHaveBeenCalledTimes(1);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(redirectToLoginMock).toHaveBeenCalledTimes(1);

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("does not attempt refresh recursively for authentication endpoints", async () => {
    setAuthenticatedState();

    const refreshSpy = vi.spyOn(axios, "post");

    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      throw createUnauthorizedError(config);
    });

    api.defaults.adapter = adapter;

    await expect(
      api.post("/auth/login", {
        email: "test@example.com",
        password: "password",
      })
    ).rejects.toMatchObject({
      response: {
        status: 401,
      },
    });

    expect(adapter).toHaveBeenCalledTimes(1);
    expect(refreshSpy).not.toHaveBeenCalled();
    expect(redirectToLoginMock).not.toHaveBeenCalled();
  });
});
