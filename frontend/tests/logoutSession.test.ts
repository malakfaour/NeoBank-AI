import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { InternalAxiosRequestConfig } from "axios";
import api from "@/lib/axios";
import { logoutSession } from "@/lib/logoutSession";

const originalAdapter = api.defaults.adapter;

describe("explicit logout", () => {
  beforeEach(() => {
    localStorage.setItem("access_token", "access");
    localStorage.setItem("refresh_token", "refresh");
    sessionStorage.setItem("app_unlocked", "true");
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
    localStorage.clear();
    sessionStorage.clear();
  });

  it("revokes the backend session and clears remembered state", async () => {
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => ({
      config,
      data: { message: "Logged out successfully" },
      headers: {},
      status: 200,
      statusText: "OK",
    }));
    api.defaults.adapter = adapter;
    await logoutSession();
    expect(adapter.mock.calls[0][0].url).toBe("/auth/logout");
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(sessionStorage.getItem("app_unlocked")).toBeNull();
  });
});
