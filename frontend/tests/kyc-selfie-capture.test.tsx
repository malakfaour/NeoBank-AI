import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SelfieCapture from "@/components/kyc/SelfieCapture";
import {
  buildKycSelfieForm,
  buildKycUploadForm,
  type KYCDocumentType,
} from "@/app/(onboarding)/kyc/page";

describe("KYC selfie camera capture", () => {
  const stop = vi.fn();
  const getUserMedia = vi.fn();

  beforeEach(() => {
    vi.restoreAllMocks();
    stop.mockReset();
    getUserMedia.mockReset();
    getUserMedia.mockResolvedValue({
      getTracks: () => [{ stop }],
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    Object.defineProperties(URL, {
      createObjectURL: {
        configurable: true,
        value: vi.fn(() => "blob:selfie-preview"),
      },
      revokeObjectURL: {
        configurable: true,
        value: vi.fn(),
      },
    });
  });

  it("opens the user-facing camera and never renders a selfie file input", async () => {
    render(
      <SelfieCapture onCapture={vi.fn()} onRetake={vi.fn()} />,
    );

    await waitFor(() => expect(getUserMedia).toHaveBeenCalledWith({
      video: {
        facingMode: "user",
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    }));
    const preview = screen.getByLabelText("Live camera preview");
    expect(preview).toHaveStyle({ objectFit: "contain" });
    expect(preview.parentElement).toHaveStyle({ aspectRatio: "4 / 3" });
    expect(await screen.findByTestId("selfie-face-guide")).toHaveStyle({
      height: "65%",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
    });
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument();
  });

  it("captures a JPEG, previews it, and supports retaking", async () => {
    const onCapture = vi.fn();
    const onRetake = vi.fn();
    const { rerender } = render(
      <SelfieCapture onCapture={onCapture} onRetake={onRetake} />,
    );
    const video = await screen.findByLabelText("Live camera preview");
    Object.defineProperties(video, {
      videoWidth: { configurable: true, value: 640 },
      videoHeight: { configurable: true, value: 480 },
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
      (callback) => callback(new Blob(["jpeg"], { type: "image/jpeg" })),
    );

    fireEvent.loadedMetadata(video);
    fireEvent.click(await screen.findByRole("button", { name: "Capture selfie" }));

    await waitFor(() => expect(onCapture).toHaveBeenCalledTimes(1));
    const selfie = onCapture.mock.calls[0][0] as File;
    expect(selfie.name).toBe("selfie.jpg");
    expect(selfie.type).toBe("image/jpeg");

    rerender(
      <SelfieCapture
        capturedSelfie={selfie}
        onCapture={onCapture}
        onRetake={onRetake}
      />,
    );
    expect(await screen.findByAltText("Captured selfie preview")).toHaveAttribute(
      "src",
      "blob:selfie-preview",
    );

    fireEvent.click(screen.getByRole("button", { name: "Retake selfie" }));
    expect(onRetake).toHaveBeenCalledOnce();
  });

  it("submits the captured selfie with the existing multipart field", () => {
    const selfie = new File(["selfie"], "selfie.jpg", { type: "image/jpeg" });
    const form = buildKycSelfieForm(selfie);

    expect(form.get("selfie")).toBe(selfie);
  });

  it("keeps identification document multipart field names unchanged", () => {
    const front = new File(["front"], "front.jpg", { type: "image/jpeg" });
    const back = new File(["back"], "back.jpg", { type: "image/jpeg" });

    const form = buildKycUploadForm(
      { front, back },
      "national_id" satisfies KYCDocumentType,
    );

    expect(form.get("id_photo")).toBe(front);
    expect(form.get("back_id_photo")).toBe(back);
    expect(form.get("selfie")).toBeNull();
    expect(form.get("submit_for_review")).toBe("false");
  });

  it("shows a saved-selfie state without requesting the camera", async () => {
    render(
      <SelfieCapture
        hasSavedSelfie
        onCapture={vi.fn()}
        onRetake={vi.fn()}
      />,
    );

    expect(screen.getByText("Selfie already captured securely")).toBeInTheDocument();
    await act(async () => {});
    expect(getUserMedia).not.toHaveBeenCalled();
  });
});
