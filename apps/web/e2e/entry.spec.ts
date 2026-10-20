import { test, expect } from "@playwright/test";
import { loginAdmin, pilotState } from "./fixtures";

test("an unavailable invitation offers retry rather than declaring it invalid", async ({ page }) => {
  await page.route("**/auth/invitations/by-token/synthetic", (route) =>
    route.fulfill({ status: 503, json: { detail: { message: "Unavailable" } } }));
  await page.goto("/invitacion?token=synthetic");
  await expect(page.getByRole("button", { name: "Reintentar" })).toBeVisible();
  await expect(page.getByText("No encontramos esta invitación.")).not.toBeVisible();
  await page.unroute("**/auth/invitations/by-token/synthetic");
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByText(/Pide a tu administrador que la genere de nuevo/)).toBeVisible();
});

test("expired concurrent requests return to the saved project after sign-in", async ({ page, context }) => {
  await loginAdmin(page);
  const path = "/proyecto/" + pilotState().saved_unprocessed_project_id;
  await page.goto(path);
  await expect(page.getByRole("button", { name: "Procesar ahora" })).toBeVisible();
  await context.clearCookies();
  await page.reload();
  await expect(page).toHaveURL(/bienvenida.*reason=session_expired/);
  await expect(page.getByText(/Tu sesión terminó/)).toBeVisible();
  await page.getByLabel("Correo electrónico").fill(pilotState().admin_email);
  await page.getByLabel("Contraseña", { exact: true }).fill(pilotState().admin_password);
  await page.locator("form").getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(path + "$"));
  await expect(page.getByRole("button", { name: "Procesar ahora" })).toBeVisible();
});
