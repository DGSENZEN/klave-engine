# Ronda Albañilería y Sustrato · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The arch base becomes a first-class *substrate* route whose geometry never feeds money; albañilería gets its deep suite (tabique walls with vano deduction, from its now-embedded base); acabado marks match locales within their own frame.

**Architecture (measured):** The spike's embed made the xref sheet route as estructural (unknown-name default) — 136 of its walls now exist as detections and some leak into EST-004 (253.7 m² from 31 sources). Fix at two levels: an `arquitectura` route (names XREF/ARQ) whose suite detects walls+rooms **stamped `substrate: true`**, and a single guard in boq that excludes substrate detections from every money rule. Albañilería's suite runs the wall detector on its sheets (walls stamped `wall_kind: "tabique"`) feeding a new unpriced ALB-001 m² concept with the A4 vano deduction; EST-004 must not double-take them (verify its filter). Mark↔local: median distance is 16 m because most frames have no locales — matching is same-frame nearest within 2 m; far marks stay per-clave counts (current fallback).

**Fences:** existing 7 gold fixtures untouched (none has substrate/albañilería walls); new `albanileria-mini`; full suite + lint; Marina completo acceptance (EST-004 shrinks by the leaked walls — measured and declared, not gold-fenced).

**Branch:** `git checkout -b ronda-albanileria`.

---

### Task 1: La ruta `arquitectura` — sustrato, no dinero

- vocab: `DisciplineSuite("arquitectura", _r(r"\bXREF\b|\bARQ\b|ARQUITEC"), structural=False)` inserted BEFORE estructural (order matters; "ARQ" must not collide with existing hints — check `guess_discipline` table tests).
- `disciplines/arquitectura.py::detect`: walls + rooms + fixtures/runs/openings trio; every wall/room detection gets `properties["substrate"] = True` and an evidence note («fondo arquitectónico: geometría de referencia, no partida»).
- boq guard: in `generate_bill_of_quantities`, filter `matched_plan`-eligible detections: any with `properties.get("substrate")` never feeds a rule (one place, before rule matching).
- Tests: routing row for "00 XREF L.04.dwg" → arquitectura; a substrate wall detection produces NO EST-004 line; the wall still exists as a detection (visor keeps it).

- [ ] failing tests → implement → PASS → gold untouched → commit `feat(detección): el fondo arquitectónico es sustrato — se ve, ancla locales, y jamás cobra (ruta arquitectura)`.

### Task 2: La suite de albañilería — el tabique con su descuento

- `disciplines/albanileria.py::detect`: wall detector on its sheets (config.wall) with detections stamped `wall_kind: "tabique"` (unless the layer says CONCRETO — respect the concrete hints), plus rooms (anchored optional) and the trio. Wire `_DETECTORS["albanileria"]`.
- Concept ALB-001 «Muro de tabique rojo recocido 14 cm, junteado con mortero» M2, `phase="Albañilería"`, rule `detection_type=wall, kind=AREA?` — walls quantify via WALL_AREA semantics: mirror EST-004's rule EXACTLY (read it first) but with `property_filter={"wall_kind": ["tabique"]}` and `opening_deduction` on (A4). Verify EST-004's filter excludes tabique (add `wall_kind` exclusion if its filter is open — measured decision at implementation).
- Store seed v23 (`_sync_builtin_concepts(("ALB-001",))`), unpriced (no APU template).
- Tests: albañilería-named sheet through the suite yields tabique walls; boq gives ALB-001 with vano deduction and EST-004 does NOT take them.

- [ ] failing tests → implement → PASS → gold untouched → commit `feat(detección): albañilería lee sus muros de tabique — con su vano descontado y sin precio inventado (ALB-001)`.

### Task 3: La marca casa con su local, en su marco

- `disciplines/acabados.py`: matching per frame — a mark matches the nearest room whose frame is its own, by polygon/bbox distance ≤ 2.0 m (meters via factor); strict containment first, tolerance second; cross-frame never.
- Test: two frames, room only in frame A; mark inside room A (matches), mark 1 m outside room A same frame (matches by tolerance), mark in frame B (stays loose, counted).

- [ ] failing test → implement → PASS → gold untouched (acabados-mini has no locales) → commit `feat(detección): la marca de acabado casa con su local dentro de su marco — cerca de veras, nunca de otro marco`.

### Task 4: Gold, aceptación y cierre

- [ ] `gold_albanileria_mini` from the two converted albañilería DXFs + the converted xref DXF (so the base embeds in-fixture); pipeline; expect tabique walls > 0; capture `--id albanileria-mini --fresh`; eval < 30 s PASS.
- [ ] Marina completo rerun + acceptance: xref-sheet walls no longer in EST-004 (declare the delta from 253.7 m²), ALB-001 present with meters, stability (ejes 593, ancladas ≥ 173), acabados m² per clave preserved or better.
- [ ] Full suite + lint; audit note «Ronda albañilería y sustrato»; suites-spec rows (albañilería cerrada, arquitectura §9 implementada); tick plan; docs commit; finishing-a-development-branch.

## Out of scope

- Cadenas/cerramientos por tag (CE-n/CR-n) — next albañilería round with real tagged data.
- Cancelería m² (still anchorless on Marina) and the legend/simbología reader.
