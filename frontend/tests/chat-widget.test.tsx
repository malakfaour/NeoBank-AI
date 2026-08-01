import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/lib/axios", () => ({
  default: {
    get: mocks.get,
    post: mocks.post,
    delete: mocks.delete,
  },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: (selector: (state: object) => unknown) => selector({
    user: { id: 27, kyc_status: "pending" },
  }),
}));

import ChatWidget, {
  getChatSessionStorageKey,
} from "@/components/chat/ChatWidget";

function axiosFailure(status: number) {
  return {
    isAxiosError: true,
    response: { status, data: { detail: "Chat session belongs to another user" } },
  };
}

describe("ChatWidget history", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    Object.defineProperty(crypto, "randomUUID", {
      configurable: true,
      value: vi.fn(() => "fresh-user-session"),
    });
  });

  it("scopes persisted sessions to the authenticated user", () => {
    expect(getChatSessionStorageKey(27)).toBe("chatbot_session_id:27");
    expect(getChatSessionStorageKey(28)).toBe("chatbot_session_id:28");
  });

  it("rotates a forbidden stale session without throwing an uncaught error", async () => {
    localStorage.setItem(getChatSessionStorageKey(27), "foreign-session");
    mocks.get
      .mockRejectedValueOnce(axiosFailure(403))
      .mockRejectedValueOnce(axiosFailure(404));
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(<ChatWidget />);

    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
    expect(mocks.get).toHaveBeenNthCalledWith(1, "/chatbot/history", {
      params: { session_id: "foreign-session" },
    });
    expect(mocks.get).toHaveBeenNthCalledWith(2, "/chatbot/history", {
      params: { session_id: "fresh-user-session" },
    });
    expect(localStorage.getItem(getChatSessionStorageKey(27))).toBe(
      "fresh-user-session",
    );
    expect(consoleError).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("How can Neo AI help?")).toBeInTheDocument();
  });
});
