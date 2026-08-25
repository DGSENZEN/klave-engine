# Confianza del número — design (approved 2026-08-25)

Round 1 of two. Fixes the five audit findings that make Klave's output
contradict its own doctrine, and opens the measurement loop that every later
accuracy claim depends on. Round 2 (separate spec) is the discipline
expansion: catalog breadth per partida, published-price adoption, and wiring
the quantities the engine already reads.

**Ordering principle:** a firm can put this on a real bid. What a client sees
gets fixed first; polish last.

**Success criterion for the whole round: not one peso moves.** Every change
here is presentation, grouping, or dates. `test_gold_money` passing unchanged
is the guard on the entire round — a stronger check than any assertion added
inside it.

Verified rather than assumed: `indirectos_campo` is a percentage of direct
cost (`report.py:337`), not a function of schedule duration, so §2 cannot move
the total. The plantilla de campo is *checked against* that figure
(`_warn_plantilla_vs_indirectos`) and does not drive it. A changed plazo may
therefore change a congruence **warning** — never an amount. Any peso that
moves in this round is a bug in this round.

---

## Findings this round closes

| # | Finding | Where it shows |
|---|---|---|
| 1 | Project list shows money the presupuesto refuses to show | `workspace.py:137` |
| 2 | Programa schedules formwork and steel *after* their own pour | `schedule.py`, catalog `sequence_order` |
| 3 | 19 identical findings bury the one that differs | `hallazgos.py` |
| 4 | "100% en lecturas firmes" is carried by the 0.70 threshold | presupuesto header |
| 5 | List rows lead with the number Klave least stands behind | `app/page.tsx:730` |
| 6 | Nothing has ever been measured against human truth | `evals/` |

Finding "five trades counted, none priceable" moves to Round 2 — adopting
published prices *is* the discipline work.

---

## Decisions

### 1. One authority for how a number may be shown

Today the doctrine rule is re-derived per surface at three levels of rigor:
`MoneyGate.tsx:23` joins report + reviews correctly across six pages,
`exports.py` checks `boq.units_reliable` alone at four sites, and
`workspace.py:137` checks nothing. The newest surface got the weakest version;
`copilot.py:202,223` reads `grand_total` with no gate at all.

**The rule moves into the engine and is resolved server-side.**

New module `packages/klave_engine/costing/presentation.py` — pure, no I/O:

```
MoneyBasis                 # serialized into cost_report.json
  units_reliable   bool
  unit / source / confidence
  reasons          list[str]
  confidence_bands {alta, media, en_el_limite}   money-weighted

resolve_money_state(basis, verification) -> "ok" | "unverified" | "blocked"
```

**The split is forced by an existing decision.** `set_verification`
(`reviews.py:431`) documents that sign-offs change no numbers and deliberately
skip the recompute. A full verdict baked into `cost_report.json` would
therefore go stale the moment someone confirms units — reading *unverified*
forever. So the artifact carries only what the engine read (`MoneyBasis`,
stable for the life of a run); the human half (`units_confirmed_at`) stays in
reviews; the resolver joins them at read time.

| Site | Change |
|---|---|
| `report.py:generate_cost_report` | writes `money_basis` into `CostReport` |
| `workspace.py:_project_entry` | resolves; `grand_total: None` when blocked, `money_state` on the row |
| cost-report route | enriches response with resolved `money_state` |
| `exports.py` ×4 | bare `units_reliable` checks become the resolver |
| `copilot.py:202,223` | ungated `grand_total` reads get the same gate |
| `MoneyGate.tsx` | `moneyGate()` **deleted**; renders `costs.money_state` |

Six web pages change only their import. The client stops deriving the verdict.

**Legacy runs, no reprocess.** Absent `money_basis` resolves to `blocked`,
reason *"corrida anterior sin veredicto de unidades"*. Torre Reforma's
$768,759,055 row is fixed without touching the run.

**Finding 4 rides in the same payload.** `confidence_bands` replaces the
single pass rate. On Marina today: ~76% alta, ~24% en el límite — the $758,276
sitting exactly on 0.70 stops being rounded up into "100% firme".

### 2. The programa

**2a — Derived concepts have no place in the sequence.** `ACE-*`,
`EST-008..011`, `CIM-006/009` are created by `apply_steel` / `apply_formwork`
and never appear in `build_default_catalog`, so they carry no `sequence_order`
against the pour they serve and sort to the tail of the phase. Measured on
Marina: cimbra de columnas starts **213 days after** the columns are poured;
cimbra de trabes 221 days after. The programa is physically impossible in the
way a professional notices first, and it cites RLOPSRM art. 224.

Fix: re-space hand-authored orders by 10 (`0, 10, 20…`); derived-concept
builders claim `parent − 2` (cimbra) and `parent − 1` (acero). Integers stay
comparable; no floats.

**2b — Hard edges only where they are real.** Formwork→pour and steel→pour for
the same element become `FS(0)`. Everything else stays SS-with-lag: traslape
between trades is correct construction modeling and the existing design intent
is right. FS is already handled in the backward pass (`schedule.py:272`) and
free float (`:293`); only the forward pass needs a branch —
`cursor = max(cursor, pred.end_day + lag)`.

**2c — Dedupe links** by `(predecessor, kind)`, keeping the larger lag. 13 of
30 activities currently carry the same predecessor twice, because the
step-anchor branch (`:176`) and the crew branch (`:189`) both fire when the
anchor and the crew tail are the same concept.

**2d — Frentes stops being silent.** `crews_per_activity` and `frentes` both
default to 1 and nothing raises them; 393 working days for a 546 m² house is
the result. There is no honest source to derive them from — the plantilla de
campo is staffing (residente, cabo, velador), not cuadrillas, and it is empty
on every project. So: no invented default. The programa states the assumption
it is making — *"un frente, una cuadrilla por actividad"* — and puts `frentes`
beside the plazo as an editable control. Same move as `sin precio`.

### 3. Findings stop drowning their own signal

`hallazgos.py` already classifies by `Rule`. Group by rule id; emit one entry
carrying a count and its members; rank groups by summed unpriced amount.
*"19 conceptos con cantidad y sin precio"* replaces nineteen identical cards,
`SAN-003` (238 m) outranks `HID-007` (1 pza), and the one finding that differs
— *"3 elementos sin armado leído"* — stops being buried in boilerplate.

### 4. List rows lead with what is unresolved

`money_state` is already on the row from §1. Render *sin unidades* in place of
a total when blocked, and put finding counts (`1 bloqueante · 19 sin precio`)
ahead of the peso figure. The attention bar above the list already does this;
the rows contradict it.

### 5. Measurement opens

`gold.capture()` already promotes `baseline → partial → verified` from reviews
(`gold.py:305`). It has been waiting for reviews that never came: every
`detection_reviews.json` in the repo has zero decisions, and every one of the
38 money expectations across three gold files carries `source: "engine"`.

**5a — Recall counts get an input.** Per-sheet, per-family field in Revisión:
*"el motor detectó 118 castillos en E-02 — ¿cuántos hay dibujados?"*,
pre-filled from the AI sheet-read's own count where one exists, since that
comparison is already computed. The human corrects a proposal instead of
counting from zero. **Must accept families the engine never detected** — those
are the expensive ones and the whole point of the exercise.

**5b — Counts live with the project.** `processed/conteos.json`, alongside
`detection_reviews.json`. `recall_cli` reads the project store first and falls
back to `evals/conteos/` so local work is unaffected.

**5c — Gold promotion needs no code.** Reviewing Marina in the app and
re-running `make gold-capture` promotes it. The one hand step is flipping five
or six money expectations to `source: "human"` after quantifying them —
`test_gold_money.py` already proves that path and no gold file uses it.

**The ritual**, documented in `docs/evals.md`: review a project in the app →
`gold-capture` → count the gaps → `recall_cli medir`.

---

## Surfaces

**Engine:** `costing/presentation.py` (new), `costing/report.py`,
`costing/models.py` (`MoneyBasis` on `CostReport`; `sequence_order` re-spacing),
`costing/schedule.py`, `costing/steel.py`, `costing/formwork.py`,
`costing/hallazgos.py`, `costing/exports.py`, `costing/catalog_store.py`
(migration), `evals/recall_cli.py`.

**API:** `routes/workspace.py`, `routes/reports.py`, `routes/copilot.py`,
`routes/reviews.py` (conteos endpoints).

**Web:** `components/MoneyGate.tsx` (gate deleted, renderer kept),
`app/page.tsx` (rows), `app/proyecto/[id]/presupuesto/page.tsx` (bands,
grouped findings), `app/proyecto/[id]/programa/page.tsx` (frentes control),
`app/proyecto/[id]/revision/page.tsx` (conteos input), six pages' imports.

**Docs:** `docs/evals.md` (the ritual), `docs/recall.md` (counts move to the
project store), `docs/principios-de-interfaz.md` (the verdict is now one
authority, not a rule repeated per screen).

---

## Migration

One numbered migration on the catalog store, continuing the v2→v13 chain:
re-space `sequence_order` by 10 for hand-authored concepts. Idempotent and
edit-preserving like the others: the migration reads each phase's concepts in
their current `sequence_order`, then rewrites them as `rank × 10` in that same
order. Relative order is preserved exactly — including a taller's own
reordering — and re-running the migration is a no-op because the ranks are
already multiples of 10 with no gaps to reclaim. Derived concepts
(`ACE-*`, `EST-008..011`, `CIM-006/009`) are not in the table; they receive
`parent − 2` / `parent − 1` at build time, in the gaps this migration opens.

---

## Testing

| Area | Test |
|---|---|
| §1 | Table test over `(basis × verification) → state`, legacy missing-basis included. Contract test: every money-bearing endpoint ships `money_state`. |
| §2 | Invariant — no cimbra or acero activity starts after the pour it serves. Link dedupe. FS forward-pass placement. Critical-path share falls below 27/30. |
| §3 | 19 same-rule findings collapse to one entry; count correct; groups ordered by amount. |
| §4 | Blocked row renders *sin unidades*, not a total. |
| §5 | Reviews promote a captured gold entry `baseline → partial`. Conteos round-trip through the project store. |
| round | `make eval-gold` and `make eval-demo` green; **`test_gold_money` unchanged** — the round moves no money. |

---

## Out of scope (Round 2)

Discipline expansion: albañilería (2 concepts today) to a real partida,
cancelería/carpintería, acabados, muebles, impermeabilización; adopting
published prices from the CDMX tabulador and SICT costo horario already in the
sources library, each with publisher, URL, vigencia and sha256; wiring the
quantities the engine already reads (`vano` with `width_m`, `mueble` via block
mapping, azotea tableros → IMP). The "sin cantidad" list that falls out of
Round 2 becomes the detector backlog, ranked by money — which is what the
recall loop opened in §5 exists to rank.
