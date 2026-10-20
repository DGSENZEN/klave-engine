import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";

export type PilotState = {
  web_url: string;
  api_url: string;
  admin_email: string;
  admin_password: string;
  invited_email: string;
  saved_unprocessed_project_id: string;
  second_workspace_project_id: string;
  expected_fixture_path: string;
};

export function pilotState(): PilotState {
  const directory = process.env.PILOT_TEST_STATE_DIR;
  if (!directory) throw new Error("Missing owned pilot test state");
  return JSON.parse(readFileSync(join(directory, "state.json"), "utf8"));
}

export async function loginAdmin(page: Page) {
  const state = pilotState();
  await page.goto("/bienvenida");
  await page.getByLabel("Correo electrónico").fill(state.admin_email);
  await page.getByLabel("Contraseña", { exact: true }).fill(state.admin_password);
  await page.locator("form").getByRole("button", { name: "Entrar", exact: true }).click();
  await page.waitForURL("/");
}
