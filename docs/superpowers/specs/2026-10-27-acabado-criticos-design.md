# Acabado, ola 1 — lo que pierde datos, lo que no deja avanzar y lo destructivo

## Intent

The interface evaluation (`docs/ux/evaluation-klave-interfaz.md`) ranked 6 critical findings and a set of destructive actions without confirmation. Diego chose to fix those first: before any polish, nothing in Klave may silently lose saved work, strand a user at a dead end, or let one keystroke or click destroy a justified record.

## Scope

In: C1–C6, M8 (missing confirmations), M9 (Visor exclusion), and the Visor's silent review failure (M10's first item, same function as M9).
Out: everything else in the evaluation — later waves. No visual redesign. No reader changes.

## Decisions

**C1 · Conteos.** When the saved counts fail to load, the counts table becomes read-only with «Reintentar» and the warning stays until a load succeeds. A failed *live* reload keeps the counts already on screen. Saving is impossible while no load has succeeded. (The PUT still sends the whole document; with a loaded base that is safe.)

**C2 · Costo horario.** A failed load shows an error with «Reintentar» inside the dialog and disables «Guardar y aplicar». Default values appear only when the server says the equipment has no saved analysis (404 or empty), and the dialog says so: «Sin análisis guardado: valores de partida».

**C3 · Primera estimación.** New server step `POST /projects/{id}/estimaciones/primera?inicio=&fin=` creates estimación 1 from the contract catalog (`catalogo_convocante`): one line per catalog row with its clave, description, unit, contracted quantity and price; `monto_contrato` from `_monto_contrato`. 409 `sin_catalogo` when no catalog is loaded; 409 `ya_hay_estimaciones` when one exists. The empty state's main action is «Capturar la estimación 1»; without a catalog it links to «Catálogo del contrato». «Nueva estimación» appears only when an estimación exists and reports real errors via `apiMessage`. A failed list load shows the error with «Reintentar», never an endless skeleton.

**C4 · Asentar nota.** `ConfirmDialog`: «Asentar la nota N — no se podrá editar ni quitar». While the request runs the button is disabled and reads «Asentando…». Same for the opening note.

**C5 · Reprocesar y cerrar nodo.** Both ask for confirmation saying they affect everyone on the project. A project screen already open stays mounted while the project reprocesses, under a fixed notice: «Se está reprocesando. Lo que ves es la lectura anterior; se actualiza al terminar.» A node closed while someone is inside keeps their screen mounted under a notice naming who closed it; the lock card appears only on the next entry.

**C6 · Detalle de concepto con teclado.** The concept cell holds a real `<button aria-expanded aria-controls>` that opens the detail; the row keeps responding to the click. Same for group headers and VariantesSection groups.

**M8 · Confirmaciones.** `ConfirmDialog` naming the document (and amount where there is one) for: deleting an ajuste a mano; removing an omitted element; removing a matrix component (its delete icon is always visible, not hover-only); replacing a contract catalog that already has rows; granting Propietario; deleting a convenio; deleting an ajuste-de-costos request; removing a workshop mapping (states that it affects every project); bulk «Quitar revisión» above 50 rows.

**M9 · Excluir en el Visor (option A, Diego).** X opens the motivo field, focused. Enter excludes with that motivo; Esc cancels. The «Excluir» button does the same. An empty motivo cannot exclude, matching Revisión. C and Q stay single keys.

**M10 (first item) · Revisar en el Visor.** A failed confirm/exclude/clear shows an inline error in the Inspector and leaves the verdict as it was.

## Constraints

- Copy in es-MX, matching the evaluation's vocabulary: Confirmar/Excluir for elements, Quitar for reversible removal, Eliminar for permanent removal.
- Every destructive confirmation uses the existing `ConfirmDialog` (Cancel focused first).
- The keyboard review loop stays: arrows, C, Q unchanged; X only gains the motivo step.
- Lint rule: no synchronous setState in effects.

## Left to the builder

Exact wording of notices beyond the strings above; where pure logic is extracted into `lib/` to make it testable.
