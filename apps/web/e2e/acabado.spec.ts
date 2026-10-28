import { test, expect, type Page } from "@playwright/test";
import { loginAdmin, pilotState } from "./fixtures";

// Ola 1 del acabado: nada pierde lo guardado, nada deja sin salida y nada
// destructivo pasa con un clic. Cada prueba trabaja sobre la obra de ejemplo
// de la cuenta de administración, procesada y con todos los nodos abiertos.

test.describe.configure({ mode: "serial" });

const NODOS = ["planos", "revision", "catalogo", "presupuesto", "programa", "contrato"];

async function obraLista(page: Page): Promise<string> {
  const state = pilotState();
  await loginAdmin(page);
  const demo = await page.request.post(state.api_url + "/projects/demo", { data: {} });
  expect(demo.ok(), await demo.text()).toBeTruthy();
  const { project_id: id } = await demo.json();
  await expect
    .poll(
      async () => (await (await page.request.get(`${state.api_url}/projects/${id}/status`)).json()).state,
      { timeout: 120_000 },
    )
    .toBe("processed");
  for (const nodo of NODOS) {
    const r = await page.request.put(`${state.api_url}/projects/${id}/gates/${nodo}`, {
      data: { approved: true },
    });
    // Sólo algunos nodos tienen candado; los demás contestan unknown_gate.
    const texto = await r.text();
    expect(r.ok() || texto.includes("unknown_gate"), texto).toBeTruthy();
  }
  return id;
}

async function notas(page: Page, id: string): Promise<number> {
  const r = await page.request.get(`${pilotState().api_url}/projects/${id}/bitacora`);
  return (await r.json()).notas.length;
}

test("asentar una nota pide confirmación y un doble clic asienta una sola", async ({ page }) => {
  test.setTimeout(180_000);
  const id = await obraLista(page);
  await page.goto(`/proyecto/${id}/bitacora`);
  const antes = await notas(page, id);

  if (antes === 0) {
    await page.getByRole("button", { name: "Abrir la bitácora" }).first().click();
  } else {
    await page.getByRole("button", { name: "Asentar nota" }).first().click();
  }
  await page.getByPlaceholder("Ing. Nombre Apellido").fill("Ing. Prueba");
  await page.getByPlaceholder("Residente de obra").fill("Residente de obra");
  await page.locator("textarea").fill("Nota de prueba del acabado.");
  await page.getByRole("button", { name: "Asentar nota" }).last().dblclick();

  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toContainText("no se podrá editar ni quitar");
  await dialogo.getByRole("button", { name: "Asentar", exact: true }).dblclick();

  await expect.poll(() => notas(page, id)).toBe(antes + 1);
  await page.waitForTimeout(1500);
  expect(await notas(page, id)).toBe(antes + 1);
});
