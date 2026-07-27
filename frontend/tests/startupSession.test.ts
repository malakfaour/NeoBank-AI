import { beforeEach, describe, expect, it, vi } from "vitest";
import { getStartupDestination, hasStoredAccountSession } from "@/lib/startupSession";

describe("remembered account session startup", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("reopens with remembered tokens but a locked app", async () => {
    localStorage.setItem("access_token", "stored-access");
    localStorage.setItem("refresh_token", "stored-refresh");
    const resolve = vi.fn().mockResolvedValue("/unlock");
    expect(await getStartupDestination(localStorage, resolve)).toBe("/unlock");
    expect(resolve).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem("app_unlocked")).toBeNull();
  });

  it("keeps the account session across a page refresh", () => {
    localStorage.setItem("refresh_token", "stored-refresh");
    expect(hasStoredAccountSession(localStorage)).toBe(true);
  });

  it("uses login only when no stored account session exists", async () => {
    const resolve = vi.fn();
    expect(await getStartupDestination(localStorage, resolve)).toBe("/login");
    expect(resolve).not.toHaveBeenCalled();
  });
});
