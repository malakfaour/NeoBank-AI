import { describe, expect, it } from "vitest";
import {
  isWeakPasscode,
  normalizeLebanesePhone,
  passwordError,
} from "@/lib/authValidation";

describe("authentication validation", () => {
  it("normalizes Lebanese mobile numbers", () => {
    expect(normalizeLebanesePhone("70 123 456")).toBe("+96170123456");
    expect(normalizeLebanesePhone("+961 71 123 456")).toBe("+96171123456");
  });

  it("requires a strong registration password", () => {
    expect(passwordError("short")).toBeTruthy();
    expect(passwordError("StrongPass1!")).toBeUndefined();
  });

  it("rejects obvious passcodes", () => {
    expect(isWeakPasscode("111111")).toBe(true);
    expect(isWeakPasscode("123456")).toBe(true);
    expect(isWeakPasscode("294806")).toBe(false);
  });
});
