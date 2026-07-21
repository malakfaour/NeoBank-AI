import { describe, it, expect } from "vitest";

// Phone validation regex used in login
const phoneRegex = /^\+?[0-9]{7,15}$/;

// IBAN validation regex used in transfer
const ibanRegex = /^LB[A-Za-z0-9]{26}$/;

// Amount validation
const isValidAmount = (v: string) => parseFloat(v) > 0 && !isNaN(parseFloat(v));

describe("Phone validation", () => {
  it("accepts valid Lebanese number", () => {
    expect(phoneRegex.test("71123456")).toBe(true);
  });
  it("accepts number with country code", () => {
    expect(phoneRegex.test("+96171123456")).toBe(true);
  });
  it("rejects empty string", () => {
    expect(phoneRegex.test("")).toBe(false);
  });
  it("rejects letters", () => {
    expect(phoneRegex.test("abc123")).toBe(false);
  });
});

describe("IBAN validation", () => {
  it("accepts valid LB IBAN", () => {
    expect(ibanRegex.test("LB" + "A".repeat(26))).toBe(true);
  });
  it("rejects wrong country code", () => {
    expect(ibanRegex.test("FR" + "A".repeat(26))).toBe(false);
  });
  it("rejects too short", () => {
    expect(ibanRegex.test("LB123")).toBe(false);
  });
  it("rejects empty", () => {
    expect(ibanRegex.test("")).toBe(false);
  });
});

describe("Amount validation", () => {
  it("accepts positive number", () => {
    expect(isValidAmount("100")).toBe(true);
  });
  it("accepts decimal", () => {
    expect(isValidAmount("10.50")).toBe(true);
  });
  it("rejects zero", () => {
    expect(isValidAmount("0")).toBe(false);
  });
  it("rejects negative", () => {
    expect(isValidAmount("-5")).toBe(false);
  });
  it("rejects letters", () => {
    expect(isValidAmount("abc")).toBe(false);
  });
});