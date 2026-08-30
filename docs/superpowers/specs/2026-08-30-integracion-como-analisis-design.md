# Integración como análisis — design (approved 2026-08-30)

Sub-project A of the OPUS-parity track (A: this; B: índices INPP; C: parámetros
legales versionados; D: breadth of official price sources — each gets its own
spec, worked in that order). The gap this one closes: the precio de venta is
built from six flat percentages (`IndirectsConfig`), while the reglamento —
and every evaluator working under it — expects *analyses*: an itemized
desglose de indirectos, a financiamiento derived from the flujo at a stated
tasa, and cargos adicionales with their legal basis. A percentage without an
análisis behind it is the disqualifiable document; the plantilla de campo
work (art. 45-A-XI-d) already built half the answer and this spec builds the
other half around it.

**Decisions already taken with the user (not revisitable mid-build):**

1. **Dual mode.** Flat percentages remain the anteproyecto default, stamped
   `porcentaje declarado, sin análisis`. When analyses exist, percentages
   become computed outputs. The report always states which mode produced each
   component's number.
2. **Split by nature.** Oficina central is workspace data (one office serves
   every obra; its percentage is *derived* by prorating). Campo is per-project.
   Financiamiento tasa: workspace default, per-project override.
3. **Approach 1 — resolver layer.** New `costing/indirectos.py` + a
   `resolve_integration` step. `integrate_costs` learns amounts-first;
   `CostIntegration`'s external shape (lines, sale_price, overcost_factor)
   does not change. No restructure of downstream consumers.

**Success criteria for the whole sub-project:**

- Declared mode reproduces today's `integrate_costs` output **bit-for-bit**;
  the demo baseline direct cost `157533681.21` is untouched (integration
  never feeds back into direct cost).
- In analysis mode, the formal document and the presupuesto total cannot
  disagree by a centavo: amounts are the source of truth, percentages are
  display derived from them.
- No invented number anywhere: every missing datum degrades to declared mode
  *per component*, visibly, with a finding naming exactly what is missing.

---

## 1. Data model (`costing/indirectos.py`)

New module in the house style: the legal reasoning lives in the module
docstring (as `escalatoria.py` does), article numbers cited there and nowhere
else — the RLOPSRM is legally overdue for replacement, so code never hardcodes
article numbers outside the one docstring.

**`RubroIndirecto`** — one row of a desglose:

- `concepto: str` — free text ("Renta de bodega", "Fianza de cumplimiento").
- `categoria` — enum of the reglamento's rubro families:
  `honorarios_prestaciones`, `depreciacion_mantenimiento_rentas`,
  `servicios`, `fletes_acarreos`, `gastos_oficina`, `capacitacion`,
  `seguridad_higiene`, `seguros_fianzas`, `trabajos_previos_auxiliares`.
- `importe: float` — MXN. **0 = sin capturar**: the row renders empty, is
  excluded from the total, and draws a `revisar` finding — never a zero that
  reads as free. Same convention `CargoCampo.salario_mensual` already uses.
- `base: Literal["mensual", "unico"]` — a renta runs every month of the obra
  (multiplied by the schedule's duration in months); a fianza is paid once.

**`DesgloseCampo`** — per-project; a new field on `CostingConfig` next to
`plantilla_campo`:

- `rubros: list[RubroIndirecto]`.
- The **personal de campo line is computed, never typed**: its importe comes
  from `build_personal_tecnico` (the plantilla), rendered as one more rubro
  with fuente "plantilla de campo". In analysis mode the plantilla is *inside*
  the desglose, so the congruence check `_warn_plantilla_vs_indirectos`
  becomes structurally impossible and is skipped; in declared mode it keeps
  firing exactly as today.
- Total campo = Σ rubros (mensual × meses + únicos) + plantilla total.
  Derived pct = total / costo directo.

**`DesgloseOficinaCentral`** — workspace-level, one `workspace_settings` key:

- `rubros: list[RubroIndirecto]` — reused model, but every row is an annual
  amount: `base` is ignored here and treated as per-year.
- `volumen_anual_contratado: float` — the taller's expected annual direct-cost
  volume. Office pct = costo anual ÷ volumen anual; the obra's amount =
  pct × its costo directo. That derivation *is* the prorate, shown with its
  arithmetic on the export.
- A project may override its share only with a written reason (`motivo`,
  ≥15 chars like the export guard), stamped as an override. Overrides go to
  `criterios`, not alarms.
- `volumen_anual_contratado` of 0/None ⇒ oficina central stays declared for
  every obra, with the finding naming the missing volumen.

**`AnalisisFinanciamiento`** — inputs captured, never invented:

- `tasa_anual: float`, `indicador: str` (e.g. "TIIE 28 días"),
  `fuente: str`, `fecha_publicacion: str` (ISO date). All four required for
  analysis mode; missing any ⇒ component stays declared with a `revisar`
  finding ("sin tasa capturada — el análisis del financiamiento no puede
  calcularse").
- Workspace default + per-project override (same shape both places).
- Computation (see §2): per flujo period, egresos = direct spend + indirects
  spread over the calendar (campo mensual rubros land in their months, únicos
  in period 1, the oficina share in proportion to direct spend); ingresos =
  anticipo + estimaciones net of amortización and retención (all already
  computed by `build_financial_plan`); costo del periodo = saldo acumulado ×
  tasa del periodo, where tasa del periodo = tasa_anual / 12 on the flujo's
  monthly calendar. **A negative total is legal** (the anticipo financing the
  contractor), kept, and explained in one sentence on the sheet.

**`CargosAdicionales`** — itemized list replacing the flat
`additional_charges_pct` in analysis mode: `concepto`, `base_legal: str`
(free text, e.g. "5 al millar, inspección y vigilancia SFP"), `pct`.
Applied on the same base the current CA line uses (accumulated subtotal).

**Utilidad stays a declared percentage.** The reglamento asks that it be
stated, not derived; an ISR/PTU decomposition would be invented precision.
Recorded in `criterios` as a deliberate choice.

**`IndirectsConfig` survives untouched** as the declared-mode fallback and
the seed for the iteration (§2).

**Storage summary:** workspace pieces (`DesgloseOficinaCentral`,
financiamiento defaults) in `workspace_settings` under one key
(`integracion`); project pieces (`desglose_campo`, `financiamiento`,
`cargos_adicionales`) as new optional fields on `CostingConfig`, persisted
through the existing overrides file with its optimistic-concurrency version.

---

## 2. Resolution and pipeline

**`ResolvedComponent`**: `{code, amount: float | None, pct: float,
fuente: Literal["analisis", "declarado"], documento}` — one per integration
component (CI-C, CI-O, FI, UT, CA). `documento` carries the data the export
prints (rubro rows, prorate arithmetic, per-period financiamiento table);
exports never recompute.

**`resolve_integration(config, workspace, boq, schedule, flujo)`** returns
the five resolved components. Per component independently: analysis present
and complete ⇒ amount computed, pct derived; anything missing ⇒ declared pct
from `IndirectsConfig`, finding emitted. Mixed modes across components are
normal and expected.

**`integrate_costs` extension:** accepts the resolved form (new optional
parameter; the old `IndirectsConfig`-only call path is unchanged for callers
and tests). Amounts win; `percentage` on each `IntegrationLine` becomes
amount/base when an amount exists. `IntegrationLine` gains `fuente`.

**Pipeline order change in `report.py`:** today it runs
*integrate → schedule → flujo*. It becomes *schedule → iterate(integrate ⇄
flujo)*:

1. Seed integration with the declared pcts from `IndirectsConfig`.
2. Build the flujo from the schedule and that integration.
3. Compute financiamiento from the flujo; re-resolve; re-integrate.
4. Repeat until the grand total moves < $0.01, hard cap 10 iterations.

The perturbation factor is the financing share (~1–3 %), so convergence is
geometric; the cap is a guard, and hitting it emits a `dinero`-tier finding
carrying the residual. Declared mode short-circuits the loop entirely — one
pass, today's numbers.

**Export guard:** `format=licitacion` treats a declared-mode component as a
**bloqueante** through the existing `_guard_export` (409 `export_blocked`,
overridable with ≥15-char `motivo` stamped on the Carátula) — for the four
components where an analysis is expected (CI-C, CI-O, FI, CA). Utilidad is
declared *by design* (§1) and never blocks; blocking on it would make every
licitación export impossible. All other
exports and screens work in both modes, stamped with the mode per component.

---

## 3. API and web

**API:**

- `GET/PUT /catalog/integracion` — workspace desglose de oficina central,
  volumen anual, financiamiento defaults. One route, one settings key, same
  audit-event pattern as `/catalog/indices` (`x_actor`, event name,
  summary).
- Project level rides the existing overrides `PUT` (no new route): the new
  `CostingConfig` fields flow through recompute like every other override.
- The report JSON exposes the resolved integration (components with fuente
  and documento) so the web never re-derives anything.

**Web:**

- `CostingConfigForm.tsx` becomes the declared-mode fallback view: each of
  the six inputs shows its fuente; when an analysis backs a component the
  input renders read-only with the derived pct and a link to its editor.
- New `DesgloseCampo.tsx` on `/proyecto/[id]/parametros`, next to
  `PlantillaCampo.tsx`: rubro rows with ghost-row entry (catalog editing
  convention), categoria select, mensual/único toggle, computed personal
  line clearly marked as fed from the plantilla.
- Oficina central + tasa editors on the taller ajustes page beside the
  salario real section (workspace data lives with workspace data).
- Provenance chips follow the `VigenciaChip` pattern.

---

## 4. Honesty rules (consolidated)

- Every degradation to declared mode is per component and produces a finding
  through `hallazgos.py`'s existing three tiers — no new severity vocabulary.
- Deliberate choices (utilidad declarada, share override) go to `criterios`.
- Rubro importe 0 = sin capturar: visible gap, excluded, `revisar`.
- Negative financiamiento kept and explained, never clamped.
- Tasa without indicador+fuente+fecha is not a tasa.
- The export layer prints `documento` payloads; it never recomputes.

---

## 5. Testing

Hand-computed fixtures, not snapshots, for the arithmetic:

- Financiamiento: a known flujo and tasa with per-period saldo verified by
  hand; the negative case (large anticipo) asserting sign and the sheet
  sentence; mensual × meses + único rubro math against a known schedule
  duration; prorate derivation including the volumen=0 degradation.
- Resolver: per-component mode selection under every missing-datum
  combination; mixed modes in one report.
- Iteration: seeded vs converged totals differ then stabilize under the cap;
  declared mode runs exactly one pass.
- Regressions: declared mode equals today's `integrate_costs` output
  exactly; demo baseline direct cost `157533681.21` unchanged;
  `_warn_plantilla_vs_indirectos` fires in declared mode, absent in analysis
  mode.
- Exports: licitación workbook contains the three documents (Análisis de
  indirectos, Financiamiento, fuente column on Integración) in analysis
  mode; declared mode gets 409 `export_blocked` with the motivo override
  path; klave workbook gains only the fuente column.
- Workspace key round-trips through the existing `data_dir` fixture pattern.

---

## Out of scope (recorded so nobody "helpfully" adds them)

- Sub-projects B (índices INPP), C (parámetros legales versionados),
  D (source breadth) — separate specs, in that order.
- Utilidad decomposition (ISR/PTU).
- Multi-currency (fields exist as `"MXN"` strings; no exchange machinery).
- Financiamiento on calendario de estimaciones other than the flujo's
  monthly periods.
- Any change to direct-cost computation, matrices, or the BoQ.
