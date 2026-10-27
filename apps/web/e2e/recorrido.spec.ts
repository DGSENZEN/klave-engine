import { test, expect, type Page } from "@playwright/test";
import { CAPITULOS } from "../lib/recorrido/capitulos";
import { loginAdmin, pilotState } from "./fixtures";

// El recorrido guiado completo, de punta a punta, con cada acción hecha de
// verdad: crear la obra, mover el visor, confirmar con C, verificar, mapear,
// exportar con motivo, abrir el programa y cargar la Rev B. Luego, empezar
// de cero deja el progreso vacío.

function tarjeta(page: Page) {
  return page.locator("[data-recorrido-tarjeta]");
}

async function paso(page: Page, titulo: string, timeout = 30_000) {
  await expect(tarjeta(page)).toContainText(titulo, { timeout });
}

async function siguiente(page: Page, veces = 1) {
  for (let i = 0; i < veces; i++) {
    const antes = await tarjeta(page).innerText();
    await tarjeta(page).getByRole("button", { name: /^(Siguiente|Terminar)/ }).click();
    await expect.poll(() => tarjeta(page).count().then(async (n) => (n ? tarjeta(page).innerText() : "")))
      .not.toBe(antes);
  }
}

async function siguienteCapitulo(page: Page) {
  await tarjeta(page).getByRole("button", { name: "Siguiente capítulo" }).click();
}

test("el recorrido guiado completo, y empezar de cero", async ({ page }) => {
  test.setTimeout(300_000);
  const state = pilotState();
  await loginAdmin(page);

  // 0 · Arranque
  await page.getByRole("button", { name: "Empezar", exact: true }).click();
  await paso(page, "Del plano a tu presupuesto");
  await siguiente(page);
  await tarjeta(page).getByRole("button", { name: "Crear mi obra de ejemplo" }).click();
  await page.waitForURL(/\/proyecto\/obra_de_ejemplo_/);
  await paso(page, "En tu obra", 90_000);
  const projectId = new URL(page.url()).pathname.split("/")[2];
  await siguienteCapitulo(page);

  // 1 · El tablero
  await paso(page, "El tablero de tu obra");
  await siguiente(page, 4);
  await siguienteCapitulo(page);

  // 2 · Planos
  await paso(page, "Lo primero: las unidades");
  await siguiente(page, 2);
  await paso(page, "El visor del plano");
  const lienzo = page.locator('[data-tour="visor.lienzo"] canvas').first();
  const caja = (await lienzo.boundingBox())!;
  await page.mouse.move(caja.x + caja.width / 2, caja.y + caja.height / 2);
  await page.mouse.down();
  await page.mouse.move(caja.x + caja.width / 2 + 60, caja.y + caja.height / 2 + 30, { steps: 6 });
  await page.mouse.up();
  await paso(page, "Toca un elemento");
  await lienzo.click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("ArrowRight");
  await paso(page, "La evidencia de cada lectura");
  await siguiente(page);
  await paso(page, "Confirma o excluye");
  await page.locator("body").click({ position: { x: 2, y: 2 } });
  await page.keyboard.press("c");
  await paso(page, "En tu obra");
  await siguienteCapitulo(page);

  // 3 · Revisión
  await paso(page, "Todos los elementos, en una tabla");
  await siguiente(page, 2);
  for (const titulo of ["Verifica las unidades", "Verifica los elementos", "Verifica los supuestos"]) {
    await paso(page, titulo);
    await page.getByRole("button", { name: "Marcar como verificado", exact: true }).first().click();
  }
  await paso(page, "Verificado");
  await siguiente(page);
  await siguienteCapitulo(page);

  // 4 · Catálogo
  await paso(page, "Variantes del plano");
  await siguiente(page);
  await paso(page, "Mapea una variante");
  await page.locator('[data-tour="variantes.mapear"]').first().getByRole("button", { name: "Elegir…" }).click();
  const buscador = page.getByLabel("Buscar concepto de tu catálogo");
  await buscador.fill("columnas 40");
  await buscador.press("Enter");
  await paso(page, "Klave lo recuerda");
  await siguiente(page, 3);
  await siguienteCapitulo(page);

  // 5 · Presupuesto
  await paso(page, "Lo que hay que atender");
  await siguiente(page, 2);
  await paso(page, "Abre un renglón");
  await page.locator('[data-tour="presupuesto.renglon"]').first().click();
  await paso(page, "Las variantes, con su importe");
  await siguiente(page);
  await page.locator('[data-tour="presupuesto.alplano"]').first().click();
  await paso(page, "Los elementos de esa cantidad");
  await siguiente(page, 4);
  await paso(page, "Entrega");
  await page.getByRole("button", { name: /Exportar/ }).first().click();
  await page.getByRole("button", { name: /Excel para OPUS/ }).click();
  await page.getByPlaceholder("p. ej. el cliente confirmó por correo que la losa va a f'c=250")
    .fill("Prueba de punta a punta del recorrido guiado");
  const descarga = page.waitForEvent("download");
  await page.getByRole("button", { name: "Entregar de todos modos" }).click();
  await descarga;
  await paso(page, "En tu obra");
  await siguienteCapitulo(page);

  // 6 · Programa
  await paso(page, "Abre el programa");
  await page.getByRole("button", { name: "Abrir nodo" }).click();
  await paso(page, "El plazo, en días naturales");
  await siguiente(page, 3);
  await siguienteCapitulo(page);

  // 7 · Otra revisión
  await paso(page, "Llega la Rev B");
  await tarjeta(page).getByRole("button", { name: "Cargar la Rev B de ejemplo" }).click();
  await paso(page, "Qué cambió, en pesos", 120_000);
  await siguiente(page);
  await page.locator('[data-tour="cambios.alplano"]').first().click();
  await paso(page, "La revisión sobre el dibujo");
  await siguiente(page);
  await siguienteCapitulo(page);

  // 8 · Tu obra
  await paso(page, "El recorrido sigue aquí");
  await siguiente(page, 2);
  await tarjeta(page).getByRole("button", { name: "Terminar" }).click();
  await expect(tarjeta(page)).toHaveCount(0);

  const hacer = CAPITULOS.flatMap((c) => c.pasos).filter((p) => p.tipo === "hacer").map((p) => p.id);
  // El progreso se guarda en segundo plano: el último paso puede seguir en
  // camino cuando la tarjeta se cierra.
  await expect.poll(async () => {
    const r = await (await page.request.get(state.api_url + "/auth/me/recorrido")).json();
    return hacer.filter((id) => r.pasos[id] !== "hecho");
  }).toEqual([]);

  // Empezar de cero: la obra vuelve a la Rev A y el progreso a vacío.
  await page.goto("/");
  await page.getByRole("button", { name: "Ayuda" }).click();
  await page.getByRole("button", { name: /Recorrido guiado/ }).click();
  await page.getByRole("button", { name: "Empezar de cero con la obra" }).click();
  await page.getByRole("button", { name: "Empezar de cero", exact: true }).click();
  await paso(page, "Del plano a tu presupuesto");
  await expect.poll(async () => {
    const r = await (await page.request.get(state.api_url + "/auth/me/recorrido")).json();
    return Object.keys(r.pasos).length;
  }).toBe(0);
  expect(projectId).toMatch(/^obra_de_ejemplo_/);
});
