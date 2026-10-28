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

// La obra de ejemplo es de la cuenta de administración y la comparten las
// demás pruebas (el recorrido espera sus candados cerrados): al terminar se
// deja como nueva.
test.afterAll(async ({ browser }) => {
  const page = await browser.newPage();
  try {
    const state = pilotState();
    await loginAdmin(page);
    const demo = await page.request.post(state.api_url + "/projects/demo", { data: {} });
    const { project_id: id } = await demo.json();
    const r = await page.request.post(`${state.api_url}/projects/${id}/demo/reiniciar`, { data: {} });
    expect(r.ok(), await r.text()).toBeTruthy();
  } finally {
    await page.close();
  }
});

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

test("reprocesar pide confirmación y deja la pantalla abierta con el aviso", async ({ page }) => {
  test.setTimeout(240_000);
  const state = pilotState();
  const id = await obraLista(page);

  // Desde Inicio, el menú del proyecto pregunta antes de reprocesar.
  await page.goto("/");
  await page.getByRole("button", { name: /^Opciones de Obra de ejemplo/ }).first().click();
  await page.getByRole("button", { name: /Reprocesar/ }).click();
  const dialogo = page.getByRole("alertdialog");
  await expect(dialogo).toContainText("vuelve a leer los planos para todos");
  await dialogo.getByRole("button", { name: "Cancelar", exact: true }).click();
  await expect(dialogo).toHaveCount(0);

  // Alguien más reprocesa mientras esta persona está en el Resumen: la
  // pantalla se queda, con el aviso, y vuelve sola al terminar.
  await page.goto(`/proyecto/${id}/resumen`);
  await expect(page.getByRole("heading", { name: "Resumen del proyecto" })).toBeVisible();
  const r = await page.request.post(`${state.api_url}/projects/${id}/process`, { data: {} });
  expect(r.ok(), await r.text()).toBeTruthy();
  await expect(page.getByText("Se está reprocesando. Lo que ves es la lectura anterior")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Resumen del proyecto" })).toBeVisible();
  await expect(page.getByText("Se está reprocesando.")).toHaveCount(0, { timeout: 120_000 });
});

test("el detalle de un concepto se abre con el teclado", async ({ page }) => {
  test.setTimeout(180_000);
  const id = await obraLista(page);
  await page.goto(`/proyecto/${id}/presupuesto`);
  const abrir = page.locator('button[aria-controls^="detalle-concepto-"]').first();
  await expect(abrir).toHaveAttribute("aria-expanded", "false", { timeout: 30_000 });
  await abrir.focus();
  await page.keyboard.press("Enter");
  await expect(abrir).toHaveAttribute("aria-expanded", "true");
  const detalle = page.locator(`#${await abrir.getAttribute("aria-controls")}`);
  await expect(detalle).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(abrir).toHaveAttribute("aria-expanded", "false");
});

test("X en el visor pide el motivo y Enter excluye con él", async ({ page }) => {
  test.setTimeout(180_000);
  const id = await obraLista(page);
  await page.goto(`/proyecto/${id}/plano`);
  const lienzo = page.locator('[data-tour="visor.lienzo"] canvas').first();
  await expect(lienzo).toBeVisible({ timeout: 30_000 });
  await lienzo.click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("ArrowRight");

  await page.keyboard.press("x");
  const motivo = page.getByLabel("Motivo de la exclusión");
  await expect(motivo).toBeFocused();
  // Sin motivo no se excluye.
  await page.keyboard.press("Enter");
  await expect(page.getByText("Escribe el motivo para excluir.")).toBeVisible();
  await motivo.fill("Duplicado del eje A");
  await page.keyboard.press("Enter");

  await expect
    .poll(async () => {
      const r = await page.request.get(`${pilotState().api_url}/projects/${id}/reviews`);
      const det = (await r.json()).detections ?? {};
      return Object.values(det).some(
        (d) => (d as { status?: string; note?: string }).status === "excluded" &&
          (d as { note?: string }).note === "Duplicado del eje A",
      );
    })
    .toBe(true);
});

test("la primera estimación sale del catálogo del contrato", async ({ page }) => {
  test.setTimeout(180_000);
  const id = await obraLista(page);

  await page.goto(`/proyecto/${id}/contrato`);
  await expect(page.getByRole("heading", { name: "Catálogo del contrato" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "catalogo-contrato.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Clave,Descripción,Unidad,Cantidad\nCON-001,Concreto en zapatas,m3,12.5\nCON-002,Acero de refuerzo,kg,850\n",
    ),
  });
  // Si ya había catálogo (una corrida anterior), reemplazarlo pide confirmación.
  const reemplazo = page.getByRole("alertdialog");
  if (await reemplazo.isVisible().catch(() => false)) {
    await reemplazo.getByRole("button", { name: "Reemplazar catálogo" }).click();
  }
  await expect(page.getByText("CON-002").first()).toBeVisible({ timeout: 30_000 });

  await page.goto(`/proyecto/${id}/estimaciones`);
  await page.getByRole("button", { name: "Capturar la estimación 1" }).click();
  await expect(page.getByText("CON-001").first()).toBeVisible();
  await expect(page.getByText("CON-002").first()).toBeVisible();
});
