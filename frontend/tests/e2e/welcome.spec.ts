import { test, expect } from "@playwright/test";

test("welcome page loads with logo and buttons", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("img[alt='NeoBank Lebanon']")).toBeVisible();
  await expect(page.getByText("LOGIN")).toBeVisible();
  await expect(page.getByText("SIGN UP")).toBeVisible();
});

test("login page has mobile and passcode fields", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByPlaceholder("71 123 456")).toBeVisible();
  await expect(page.getByPlaceholder("••••••")).toBeVisible();
  await expect(page.getByText("LOGIN")).toBeVisible();
});

test("register page has all fields", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByPlaceholder("Lana Nasserdine")).toBeVisible();
  await expect(page.getByPlaceholder("you@example.com")).toBeVisible();
 await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
});