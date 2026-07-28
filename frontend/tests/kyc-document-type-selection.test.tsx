import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  DocumentTypeSelection,
  type KYCDocumentType,
} from "@/app/(onboarding)/kyc/page";


describe("KYC document type selection", () => {
  it("renders all options and selects a document type", () => {
    let selected: KYCDocumentType | null = null;
    const onSelect = vi.fn((value: KYCDocumentType) => {
      selected = value;
    });
    const { rerender } = render(
      <DocumentTypeSelection
        selected={selected}
        onSelect={onSelect}
        onBack={vi.fn()}
        onContinue={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Passport" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "National ID" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Passport" }));
    expect(onSelect).toHaveBeenCalledWith("passport");

    rerender(
      <DocumentTypeSelection
        selected={selected}
        onSelect={onSelect}
        onBack={vi.fn()}
        onContinue={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Passport" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });
});
