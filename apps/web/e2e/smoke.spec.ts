import { test, expect } from "@playwright/test";
import { pilotState } from "./fixtures";

test("welcome is served by the production build and real API", async ({ page }) => {
  const state = pilotState();
  const response = page.waitForResponse(state.api_url + "/auth/session");
  await page.goto("/bienvenida");
  expect((await response).status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Taller|Klave/);
  await expect(page.getByRole("button", { name: /Entrar/ }).first()).toBeVisible();
});
