import { test, expect } from "@playwright/test";
import { join } from "node:path";
import { loginAdmin, pilotState } from "./fixtures";

test("a saved upload waiting for processing opens without a second upload", async ({ page }) => {
  await loginAdmin(page);
  let uploads = 0;
  await page.route("**/projects/upload", (route) => {
    uploads++;
    return route.fulfill({ status: 429, json: { detail: {
      error_type: "processing_queue_full",
      project_id: pilotState().saved_unprocessed_project_id,
      message: "La cola está llena.",
    } } });
  });
  await page.locator('input[type="file"]').setInputFiles(join(__dirname, "fixtures/structural-meters.dxf"));
  await page.getByLabel(/Nombre del proyecto/).fill("Pilot upload");
  await page.getByRole("button", { name: "Crear y procesar" }).click();
  await expect(page).toHaveURL(new RegExp(pilotState().saved_unprocessed_project_id));
  await expect(page.getByText(/Tus planos se guardaron/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Procesar ahora" })).toBeVisible();
  expect(uploads).toBe(1);
});
