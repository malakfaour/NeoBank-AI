export const passwordRules = [
  { label: "At least 8 characters", test: (value: string) => value.length >= 8 },
  { label: "One uppercase letter", test: (value: string) => /[A-Z]/.test(value) },
  { label: "One lowercase letter", test: (value: string) => /[a-z]/.test(value) },
  { label: "One number", test: (value: string) => /\d/.test(value) },
  { label: "One special character", test: (value: string) => /[^A-Za-z0-9]/.test(value) },
];

export function passwordError(value: string): string | undefined {
  return passwordRules.every((rule) => rule.test(value))
    ? undefined
    : "Password does not meet all requirements.";
}

export function normalizeLebanesePhone(value: string): string | null {
  let digits = value.replace(/\D/g, "");
  if (digits.startsWith("00961")) digits = digits.slice(5);
  else if (digits.startsWith("961")) digits = digits.slice(3);
  digits = digits.replace(/^0/, "");
  return /^(?:3\d{6}|(?:70|71|76|78|79|81)\d{6})$/.test(digits)
    ? `+961${digits}`
    : null;
}

export function isWeakPasscode(value: string): boolean {
  return /^(\d)\1{5}$/.test(value) || value === "123456" || value === "654321";
}
