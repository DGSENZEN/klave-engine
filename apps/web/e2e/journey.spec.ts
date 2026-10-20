import { test, expect } from "@playwright/test";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { loginAdmin, pilotState } from "./fixtures";

test("an invited customer reviews, prices and downloads an actual workbook", async ({ page: admin, browser }, info) => {
  const state = pilotState();
  await loginAdmin(admin);
  await admin.goto("/equipo");
  await admin.getByRole("button", { name: "Invitar", exact: true }).click();
  const dialog = admin.getByRole("dialog");
  await dialog.getByPlaceholder("correo@taller.mx").fill(state.invited_email);
  await dialog.getByRole("button", { name: "Invitar", exact: true }).click();
  const invitation = await dialog.locator("code").textContent();
  expect(invitation).toBeTruthy();
  const context = await browser.newContext();
  try {
    const customer = await context.newPage();
    await customer.goto(invitation!.trim());
    await customer.getByLabel("Nombre y apellido").fill("Pilot customer");
    await customer.getByLabel("Contraseña", { exact: true }).fill("Synthetic-customer-123!");
    await customer.getByLabel("Repite la contraseña").fill("Synthetic-customer-123!");
    await customer.getByRole("button", { name: "Crear cuenta y entrar" }).click();
    await customer.waitForURL("/");
    await customer.locator('input[type="file"]').setInputFiles(join(__dirname, "fixtures/structural-meters.dxf"));
    await customer.getByLabel("Nombre del proyecto").fill("Pilot real journey");
    await customer.getByRole("button", { name: "Crear y procesar" }).click();
    await customer.waitForURL(/\/proyecto\/[^/]+$/);
    const id = new URL(customer.url()).pathname.split("/")[2];
    await expect.poll(async () => {
      const response = await customer.request.get(state.api_url + "/projects/" + id + "/status");
      return (await response.json()).state;
    }, { timeout: 60_000 }).toBe("processed");
    await customer.goto("/proyecto/" + id + "/resumen");
    await expect(customer.getByText("Ruta de verificación", { exact: true })).toBeVisible();
    await customer.getByRole("link", { name: "Ir al plano", exact: true }).click();
    await expect(customer.locator("canvas").first()).toBeVisible();
    await customer.goto("/proyecto/" + id + "/resumen");
    for (let step = 0; step < 3; step++) {
      await customer.getByRole("button", { name: "Marcar como verificado", exact: true }).first().click();
      if (step < 2) {
        await expect(customer.getByRole("button", { name: "Deshacer", exact: true })).toHaveCount(step + 1);
      }
    }
    await expect(customer.getByText("Verificado", { exact: true }).first()).toBeVisible();
    await customer.reload();
    await expect(customer.getByText("Verificado", { exact: true }).first()).toBeVisible();
    await customer.goto("/proyecto/" + id + "/presupuesto");
    await customer.getByRole("row").filter({ hasText: "EST-016" }).first().click();
    await customer.getByRole("button", { name: "elegir de mi catálogo", exact: true }).click();
    await customer.getByLabel("Buscar concepto del taller").fill("PILOT-SLAB");
    const reference = customer.getByRole("listitem").filter({ hasText: "PILOT-SLAB" });
    await reference.getByRole("button", { name: "Usar esta clave" }).click();
    await expect(customer.getByRole("row").filter({ hasText: "PILOT-SLAB" }).first()).toContainText("1,000");
    await customer.reload();
    await expect(customer.getByRole("row").filter({ hasText: "PILOT-SLAB" }).first()).toContainText("1,000");
    await customer.getByRole("button", { name: "Exportar", exact: true }).click();
    const download = customer.waitForEvent("download", { timeout: 15_000 });
    void download.catch(() => {});
    const response = customer.waitForResponse((result) => result.url().includes("/export/presupuesto.xlsx"));
    await customer.getByRole("button", { name: "Excel completo (Klave)", exact: true }).click();
    const exported = await response;
    expect(exported.ok(), await exported.text()).toBeTruthy();
    const file = await download;
    const path = info.outputPath("pilot-budget.xlsx");
    await file.saveAs(path);
    execFileSync(join(__dirname, "../../../.venv/bin/python"), [
      join(__dirname, "check_workbook.py"), path, state.expected_fixture_path,
    ]);
    const denied = await customer.request.get(state.api_url + "/projects/" + state.second_workspace_project_id);
    expect([403, 404]).toContain(denied.status());
  } finally {
    await context.close();
  }
});
