import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "@/app/(auth)/forgot-password/page";
import api from "@/lib/axios";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

describe("forgot password page", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    sessionStorage.clear();
  });

  it("submits the registered email and redirects after success", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: { message: "If an account exists, a code was sent." },
    });
    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: " Person@Example.com " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/auth/password/forgot", {
        email: "person@example.com",
      });
      expect(sessionStorage.getItem("reset_email")).toBe("person@example.com");
      expect(replaceMock).toHaveBeenCalledWith("/verify-reset-otp");
    });
  });

  it("shows backend errors and does not redirect", async () => {
    vi.spyOn(api, "post").mockRejectedValue({
      response: { data: { detail: "Email service unavailable" } },
    });
    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "person@example.com" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Send code" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email service unavailable"
    );
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
