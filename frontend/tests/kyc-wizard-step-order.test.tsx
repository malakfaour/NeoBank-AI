import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  push: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock("@/lib/axios", () => ({
  default: {
    get: mocks.get,
    post: mocks.post,
    put: mocks.put,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: (selector: (state: object) => unknown) => selector({
    user: { id: 1, kyc_status: "pending" },
    setUser: mocks.setUser,
  }),
}));

vi.mock("@/components/kyc/SelfieCapture", () => ({
  default: ({
    capturedSelfie,
    hasSavedSelfie,
    onCapture,
  }: {
    capturedSelfie?: File;
    hasSavedSelfie?: boolean;
    onCapture: (file: File) => void;
  }) => (
    <div aria-label="Mock selfie capture">
      <span>
        {capturedSelfie || hasSavedSelfie
          ? "Captured selfie retained"
          : "Live selfie camera"}
      </span>
      <button
        type="button"
        onClick={() => onCapture(
          new File(["selfie"], "selfie.jpg", { type: "image/jpeg" }),
        )}
      >
        Capture test selfie
      </button>
    </div>
  ),
}));

import KYCPage, { getKycResumeStep } from "@/app/(onboarding)/kyc/page";

describe("KYC wizard step order", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue({
      data: {
        workflow_status: "in_progress",
        current_step: 5,
        profile_data: {
          first_name: "Rana",
          fathers_name: "Karim",
          mothers_name: "Maya",
          last_name: "Haddad",
          date_of_birth: "1995-02-10",
          place_of_birth: "Beirut",
          gender: "female",
          marital_status: "single",
          nationality: "Lebanese",
          country_of_residence: "Lebanon",
          governorate: "Beirut",
          district: "Beirut",
          city: "Beirut",
          street: "Hamra",
          building: "10",
          residential_address: "Hamra Street, Building 10",
          occupation: "unemployed",
          source_of_funds: "savings",
          annual_income_usd: "12000",
          identification_type: "national_id",
          identification_number: "12345678",
          record_number: "42",
          register_place: "Beirut",
          id_expiry_date: "2030-01-01",
        },
        has_front_id: false,
        has_back_id: false,
        has_selfie: false,
        rejection_reason: null,
      },
    });
    mocks.post.mockResolvedValue({ data: {} });
    mocks.put.mockResolvedValue({ data: {} });
  });

  it("separates selfie Step 5 from identification Step 6 and preserves both", async () => {
    render(<KYCPage />);

    expect(await screen.findByText("STEP 5 OF 6")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Selfie verification" })).toBeInTheDocument();
    expect(screen.getByLabelText("Mock selfie capture")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Identification number/)).not.toBeInTheDocument();
    expect(screen.queryByText("Front ID image *")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Capture test selfie" }));
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      "/kyc/selfie",
      expect.any(FormData),
      { headers: { "Content-Type": "multipart/form-data" } },
    ));
    expect(mocks.put).toHaveBeenCalledWith(
      "/kyc/profile",
      expect.objectContaining({ current_step: 6 }),
    );

    expect(await screen.findByText("STEP 6 OF 6")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Identification and document upload" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Identification number/)).toHaveValue("12345678");
    expect(screen.getByText("Front ID image *")).toBeInTheDocument();
    expect(screen.getByText("Back ID image *")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mock selfie capture")).not.toBeInTheDocument();
    expect(screen.queryByText("Live selfie camera")).not.toBeInTheDocument();

    const fileInputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
    expect(fileInputs).toHaveLength(2);
    fireEvent.change(fileInputs[0], {
      target: { files: [new File(["front"], "front.jpg", { type: "image/jpeg" })] },
    });
    fireEvent.change(fileInputs[1], {
      target: { files: [new File(["back"], "back.jpg", { type: "image/jpeg" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByText("STEP 5 OF 6")).toBeInTheDocument();
    expect(screen.getByText("Captured selfie retained")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    expect(await screen.findByText("STEP 6 OF 6")).toBeInTheDocument();
    expect(screen.getByLabelText(/Identification number/)).toHaveValue("12345678");

    fireEvent.click(screen.getByLabelText("I accept the terms and conditions."));
    fireEvent.click(screen.getByLabelText("I confirm that the information is correct."));
    fireEvent.click(screen.getByLabelText("I consent to identity and compliance processing."));
    fireEvent.click(screen.getByRole("button", { name: "Submit for review" }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      "/kyc/upload",
      expect.any(FormData),
      { headers: { "Content-Type": "multipart/form-data" } },
    ));
    expect(mocks.put).toHaveBeenCalledWith(
      "/kyc/profile",
      expect.objectContaining({ current_step: 6 }),
    );
  });

  it("maps saved data to the first incomplete step in the final order", () => {
    const response = {
      workflow_status: "in_progress" as const,
      current_step: 6,
      profile_data: {},
      has_front_id: false,
      has_back_id: false,
      has_selfie: false,
      rejection_reason: null,
    };
    expect(getKycResumeStep(response)).toBe(1);

    Object.assign(response.profile_data, {
      first_name: "Rana", fathers_name: "Karim", mothers_name: "Maya",
      last_name: "Haddad", date_of_birth: "1995-02-10",
      place_of_birth: "Beirut", gender: "female", marital_status: "single",
      nationality: "Lebanese",
    });
    expect(getKycResumeStep(response)).toBe(2);

    Object.assign(response.profile_data, {
      country_of_residence: "Lebanon", governorate: "Beirut",
      district: "Beirut", city: "Beirut", street: "Hamra", building: "10",
      residential_address: "Hamra Street",
    });
    expect(getKycResumeStep(response)).toBe(3);

    Object.assign(response.profile_data, { occupation: "unemployed" });
    expect(getKycResumeStep(response)).toBe(4);

    Object.assign(response.profile_data, {
      source_of_funds: "savings", annual_income_usd: "12000",
    });
    expect(getKycResumeStep(response)).toBe(5);

    response.has_selfie = true;
    expect(getKycResumeStep(response)).toBe(6);
  });
});
