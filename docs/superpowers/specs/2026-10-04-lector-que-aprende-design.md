# El lector que aprende · rules + model + per-office profiles, fed by Revisión — design

**Date:** 2026-10-04 · **Status:** approved in brainstorming, pending Diego's review of this text
**Parent:** `2026-09-16-producto-v1-cuantificacion-design.md` §2.1, §2.6, §10 (this is the "reader spec" that one deferred)

## 0. The problem, in one sentence

The engine reads obra negra with rules — layer names, block names, text patterns, geometry thresholds — which is why the gold is perfect on our drawings and why it will stumble on an office that names layers differently, draws castillos with another block, or writes «COL», «C-1» or nothing. Generalizing means learning what does not change between offices (geometry, repetition, position relative to the grid, nearby text) and adapting fast to what does (that office's names).

**Product metric, the only one that decides:** minutes of review per sheet for a new office, falling from its first project to its third. Every model metric below is a proxy for this.

## 1. Decisions taken (brainstorming 2026-09-16 → 2026-10-04)

| # | decision |
|---|---|
| 1 | **Drawings leave the server only by explicit switch.** Local by default (rules, small model, profiles). A hosted large model for the long tail is a per-project switch the engineer turns on; it sends crops plus nearby text, never whole sheets, cached by block signature. |
| 2 | **Labels pool across workspaces, opt-out per workspace.** What pools: feature vector, verdicts, layer-name tokens, mark tokens, block signature hash. What never pools: coordinates, crops, raw text beyond tokens, file names, project names. Enough to learn conventions, not enough to rebuild a sheet. |
| 3 | **The model can doubt the rules, never override them.** A strong disagreement becomes a duda in Revisión with both opinions; the person's decision is a label that scores rule against model. Nothing changes silently. |
| 4 | **The model never produces a quantity.** It names elements (family or "not an element"); the geometry engine measures. |
| 5 | **No confidence is stamped anywhere** (doctrine). Uncertainty becomes a duda in the queue. |
| 6 | **Core approach: a small tabular model over features the rules already compute** (approach A). A graph model over the drawing graph (approach B) is designed for, not built — the label schema and feature store keep what B would need. Vision-for-everything (approach C) is rejected: slow, costly, opaque. |

## 2. What exists and what's missing (read from the code 2026-10-04)

**Exists:** per-run `normalized_entities.json` (77,925 on Marina), `drawing_graph.json`, `detections.json` (1,183 on Marina: beam_tag 386, column_tag 359, fixture 136, wall 85, footing 64, slab_region 55, pipe_run 35, grid_line 23, pile 23, opening 10, grid_intersection 7) with `source_entities`, `evidence`, `family`, `mark`; `detection_reviews.json` with `DetectionReview.status ∈ {confirmed, excluded}` keyed by `display_label or detection_id`; the prefab index (definitions and instances); hallazgos that cross-check the drawing; inventory mappings (block/layer → concept, typed by hand).

**Missing, and blocking:**
- **A stable element identity.** Review keys are labels or run-scoped ids; a reprocess or a new revision loses the link. (The v1 revision diff needs the same identity.)
- **A reassign verdict.** Today a person can confirm or exclude; they cannot say "this is a castillo, not a column" or "this is a footing you missed". The most informative label doesn't exist.
- **The rejected candidates.** Rules emit only what they accept. The closed polyline that was almost a column, the block nobody recognized, never reach Revisión or a log — so a model has nothing to classify and a person nothing to correct.
- **Features as data.** Every detector computes area, aspect, repetition, distance to grid, nearby text… and throws it away after thresholding.

## 3. The element and its features

### 3.1 Candidates

A new detection stage `detection/candidates.py` emits, per sheet, every entity group a detector *considered*: closed polylines and blocks within the size range of any structural family, hatched regions, repeated block instances, parallel line pairs. Each candidate carries the detector's verdict (accepted as family X, rejected with reason, or not considered by any rule). Written to `candidates.jsonl` per run. Accepted candidates are the existing detections; nothing about current detection output changes (gold stays byte-stable).

### 3.2 Stable `element_id`

`element_id = hash(project_id, sheet_key, family_or_shape_class, quantized centroid in frame coordinates, block signature or geometry hash)`. Quantization at 5 cm in drawing units converted to meters, frame-relative so a sheet moved in model space keeps its ids. Reprocessing the same file yields the same ids; a revision yields the same id for an unchanged element. Reviews migrate from `display_label` keys to `element_id` with a backward-compatible read of old keys.

### 3.3 Features (`detection/features.py`)

Per candidate, numeric and categorical, all already computed somewhere by a detector:

- **Shape:** area (m²), bbox w/h (m), aspect, closedness, vertex count, rectangularity, hatch present, hatch pattern token.
- **Repetition:** instances of the same block signature on the sheet and in the project; instances of the same geometry hash.
- **Context:** distance to nearest grid intersection (m), on-grid flag, distance to nearest wall pair and beam line, inside a slab region, overlap with another candidate.
- **Text:** tokens within a radius scaled to the frame (mark patterns like `K-1`, `C-3`, `Z-2`; section `30x40`; f'c), distance to nearest mark text, leader present.
- **Names:** layer-name tokens (split on separators, accents folded), block-name tokens, sheet discipline from the registry, sheet title tokens.
- **Rule trace:** which detectors considered it, each one's verdict and the threshold that decided.

Features are versioned (`FEATURES_VERSION`); a label records the version it was computed with.

## 4. The four tiers, in order

1. **Rules** (today's detectors). Verdicts unchanged. Their accepted output is a weak label; their rejected candidates are unlabeled data.
2. **Per-office profile** (`workspace_profiles` in the users/workspace db). Learned mappings for that office: layer token → family, block signature → family, mark pattern → family, with the count of reviews that support each. Applied before the model; a profile entry with ≥ 3 supporting reviews and no contradicting ones acts like a rule for that workspace. Built from the first reviewed project; updated the moment a review is saved. This is the hand-typed inventory mapping, learned.
3. **Small model** (gradient-boosted trees over §3.3 features, one multiclass head: structural families + `no_es_elemento`). Trained on pooled labels; scored per candidate. Runs locally, milliseconds per sheet. Calibrated per workspace by a thin layer refit on that workspace's labels once it has ≥ 50.
4. **Hosted large model** — only when the project switch is on, only for candidates tiers 1–3 left unnamed or in disagreement. Input: a rasterized crop around the candidate (frame-scaled), nearby text tokens, the sheet title, and 6–10 labeled examples from the pool with the closest features. Output: a family or `no_es_elemento` plus a one-line reason. Cached by block signature / geometry hash per workspace so a shape is asked once. Its answers are proposals, never final; they enter Revisión as dudas and their resolutions are labels (which is how they get distilled into tier 3).

**Self-checks** run over the combined result and raise dudas, never edits: columns on grid intersections; footings under columns; marks on the plan present in the schedule and vice versa; section in the schedule vs section measured; slab panels closing. These exist as hallazgos; here they also mark which elements to doubt.

## 5. Disagreement → duda

For each candidate the combiner holds up to four opinions (rule, profile, model, hosted). Outcomes:

| situation | result |
|---|---|
| rule accepts, model agrees or abstains | detection, as today |
| rule accepts, model strongly says another family or `no_es_elemento` | detection kept **and** a duda «el lector duda: ¿columna o castillo?» with both reasons |
| rule rejects or never considered, profile or model names a family | **proposed** element: shown in the visor dashed, not counted in quantities until confirmed |
| nobody names it, hosted switch on | sent to tier 4; its answer becomes a proposed element |

"Strongly" is a margin on the model's class probabilities, tuned per family on held-out workspaces so the duda rate stays under a budget (target ≤ 5 dudas per sheet on a new office). The probability itself is never shown. A proposed element is counted only when a person confirms it — quantities move by human decision only.

## 6. The label

Every Revisión action appends one record to `labels.jsonl` (per project, in `processed/`):

```json
{"label_id": "…", "element_id": "…", "run_id": "…", "sheet_key": "…",
 "features_version": 3, "features": {…}, "layer_tokens": ["est","col"],
 "mark_tokens": ["K-1"], "block_sig": "…", "geometry_hash": "…",
 "proposals": {"rule": "column", "profile": null, "model": "castillo", "hosted": null},
 "model_version": "m-2026-10-12", "verdict": "castillo",
 "action": "reassign", "actor": "…", "at": "…", "workspace_id": "…"}
```

**Actions captured:** confirm, exclude, reassign (new), add-missed (new: the person draws or picks entities the engine missed and names the family), mapping correction (from v1 §2.2), measurement override. Revisión gains the two missing gestures — «Es otro elemento…» (reassign, with the family picker) and «Falta un elemento aquí» (add-missed, selecting entities in the visor) — inside the existing inspector and selection bar, no new header buttons.

**Pooling:** a nightly export copies each opted-in workspace's new labels to the global store with coordinates, crops, raw text and names removed (decision 2). Consent: workspace terms line + a setting under Configuración del taller, on by default, off removes future exports and a "borrar mis aportaciones" action deletes past ones from the pool. Pooled records keep `workspace_id` as an opaque hash for leave-one-workspace-out evaluation.

## 7. The loop

- **Profiles** update synchronously on review save.
- **Small model** retrains as an offline job (`klave-engine train-reader`, also a nightly scheduled job when the pool grew by ≥ 200 labels). Evaluation is **leave-one-workspace-out**: train on all workspaces but one, test on it, for each. **Promotion rule:** a new version replaces the current one only if, for every workspace with ≥ 30 labels, per-family precision does not drop by more than 1 point and the duda budget holds; otherwise it's kept as a candidate with its report.
- **Versioning:** `models/reader/<version>/` holds the model, the features version, the training manifest (label counts per workspace and family, never content) and the evaluation report. The active version is a pointer; rollback is a pointer change. Every proposal records the version that made it.
- **Distillation:** hosted answers confirmed by people become labels like any other; the small model learns them, so the hosted switch costs less over time.

## 8. What we measure

| metric | where | target |
|---|---|---|
| minutes of review per sheet, new office, project 1 → 3 | Revisión session timing per sheet | falls each project; ≤ 50 % of project 1 by project 3 |
| precision / recall per family, held-out workspace | eval report | precision ≥ rule-only baseline on every family; recall up |
| dudas per sheet | run summary | ≤ 5 on a new office |
| rule vs model score per detector | resolved disagreements | the ranked list of rules to fix — reviewed each round |
| hosted cost per project | tier-4 log | reported, capped per workspace |
| gold | `make eval-gold` | unchanged: proposals never count until confirmed |

## 9. Honesty rules

- A quantity moves only by a person's decision; proposed elements are dashed and uncounted.
- No probability, score or "confidence" on any screen or export.
- Every duda says, in words, who doubts and why («la regla dice columna por la capa EST-COL; el lector dice castillo: sección 15×15 dentro de un muro»).
- The hosted switch shows, per project, how many crops left the server.
- A workspace that opts out still gets the global model; it simply stops feeding it.

## 10. Testing

- Candidates: Marina and prueba-1 emit candidates; accepted ⊆ candidates; detections byte-identical to before (gold green).
- `element_id`: stable across two reprocesses of the same file; stable for unchanged elements across an edited copy (shared fixture with the v1 revision diff).
- Features: golden values for a handful of known elements per fixture.
- Labels: each Revisión action writes exactly one record; pooled export strips the forbidden fields (test asserts their absence).
- Profiles: three reviews of a block on project 1 make it a profile rule on project 2.
- Model: the training script runs on fixtures; leave-one-out report produced; promotion rule refuses a deliberately worse model.
- Combiner: each row of the §5 table as a test.
- Hosted tier: behind an interface with a fake provider in tests; cache hit on second ask; switch off → zero calls.

## 11. Phasing (one plan each)

| round | delivers | depends on | gate |
|---|---|---|---|
| **S0 · Spikes** (throwaway) | (a) leave-one-project-out classifier on our three sets with features computed ad hoc; (b) vector-PDF → entity stream on one Marina sheet | — | a written result: do features carry across drawings? does PDF reach the parser? Result recorded in this spec §12 |
| **F1 · Lo que se ve y se guarda** | §3.1 candidates, §3.2 element_id + review migration, §3.3 features, §6 labels with reassign and add-missed in Revisión | — | gold byte-stable; every action writes a label; ids stable |
| **F2 · El perfil del taller** | §4 tier 2, learned from reviews, replacing hand-typed mappings as the default | F1 | the three-reviews test; a second project from the same office shows fewer dudas |
| **F3 · El modelo y la duda** | §4 tier 3, §5 combiner, proposed elements in the visor, §7 training + leave-one-out + promotion, pooling export + consent setting | F1, labels from ≥ 2 workspaces | precision ≥ baseline on held-out; duda budget |
| **F4 · La cola larga** | §4 tier 4 behind the switch, cache, distillation | F3 | cost reported; switch off = zero calls |
| **F5 · El grafo** (later) | approach B over `drawing_graph.json` when the pool has ≥ 20 workspaces | F3 | beats F3 on leave-one-workspace-out |

F1 ships with v1 R1 (it's the v1 §2.6 label hook, done properly) so the first pilot already produces labels. F2–F4 follow the pilot and the first foreign plan sets.

## 12. Spike results

### S0(a) · Do the F1 features carry across drawings? (2026-10-06)

**Setup (throwaway, not committed).** The three real sets were reprocessed in scratch copies with the current motor (profile off, history off): Marina estructural (952 structural detections, 1,064 candidates), PRUEBA-1 (390 / 210), S-101 cimentación (24 / 0). Labels were the *rules'* verdicts, not people's: an accepted detection's family (trabe/contratrabe/dala/cerramiento merged as `viga`) and, for the element-vs-not task, the candidates as weak `no_es_elemento`. The model was gradient-boosted trees (scikit-learn `HistGradientBoostingClassifier`, defaults) over the seven features detections and candidates share: width, height, aspect, area, distance to the nearest grid crossing, block repetition, and layer/block tokens. Each set was held out in turn, trained on the other two.

| task · features | held out Marina | held out PRUEBA-1 | held out S-101 |
|---|---|---|---|
| family · geometry | 0.69 (majority 0.35) | 0.85 (0.11) | 0.25 (n = 24) |
| family · names only | 0.35 | 0.66 | 0.12 |
| family · all | 0.69, macro-F1 0.54 | 0.83, macro-F1 0.62 | 0.50 |
| element vs not · geometry | 0.86 | 0.93 | — |
| element vs not · names only | 0.44 | 0.68 | — |
| element vs not · all | 0.86 (P 0.83 / R 0.89) | 0.94 (P 0.98 / R 0.93) | — |

Restricting positives to the candidates' size window (0.08–3 m), to rule out "big means element", leaves element-vs-not unchanged (0.87 / 0.94).

**What it says.**
1. **Geometry carries; names don't.** Layer and block tokens alone are at or below the majority baseline on a drawing the model hasn't seen, and add nothing on top of geometry. Each office names its own way. That confirms the tier split: names belong in the per-office profile (F2, built), and the pooled model should lean on shape and context.
2. **Element vs not transfers well** (0.86–0.94 on an unseen drawing). This is the useful part for F3: ranking the candidates nobody claimed, so proposals are mostly real elements.
3. **Family doesn't yet transfer for the hard pairs.** Castillo vs columna (Marina castillo recall 0.41, columna 0.04), pilote (0.00: the shared features have no circle/entity type), and viga in PRUEBA-1 (recall 0.12). Before F3 trains a family head, the shared features need the entity type and closedness (candidates have them, detections don't), the mark prefix for both sides, and "inside a wall pair" (§3.3 context) — that last one is what separates a castillo from a columna.
4. **The labels are the rules' own verdicts.** This measures whether the features can reproduce the rules on a new drawing, not whether the model beats them; that needs people's labels from at least two offices, which is F3's gate and still unmet.

**Consequence for F3.** Ship element-vs-not first, as proposals («el lector cree que aquí hay un elemento») with geometry features, and hold the family head until the features above exist and labels from a second office arrive. Names stay per-office.


### S0(b) · Vector PDF → entity stream — blocked (2026-10-06)

No plotted plano PDF exists locally (`data/sources` holds price tabulators only). A round-trip made here (DXF → our own PDF → back) would only test our own exporter, not what an office receives: AutoCAD's «DWG To PDF» output flattens blocks into paths, may drop layers unless plotted as a layered PDF, and may turn text into glyph outlines. The spike needs one real plotted sheet, ideally a Marina structural sheet plotted from AutoCAD, with and without layers. Owed by Diego.

## 13. Out of scope

- Any model that measures quantities, reads dimensions into numbers, or edits geometry.
- Scanned/raster plans (vision OCR of whole sheets). Vector PDF is a spike; raster is a later track.
- Training on drawings from workspaces that opted out.
- Fine-tuning a large model. Distillation into the small model is the path.
- Public academic CAD datasets in shipped models (research licenses); allowed in offline experiments only.
- Synthetic DXF generation — worth an experiment after F3 if per-family recall is data-starved; not planned.
