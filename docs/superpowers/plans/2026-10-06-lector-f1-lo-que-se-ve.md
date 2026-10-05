# El lector que aprende · F1 — Lo que se ve y se guarda — implementation plan

> superpowers:executing-plans, inline. Steps `- [ ]`.

**Spec:** [el lector que aprende](../specs/2026-10-04-lector-que-aprende-design.md) §3, §6, F1 in §11.

**Goal:** every Revisión decision becomes a label with what the engine knew about the element (features), reviews survive a reprocess (stable identity), the elements the rules did not take are logged as candidates, and the two missing gestures exist: «Es otro elemento…» (reassign) and the position of «Falta un elemento aquí».

**Decisions:** reassign reuses the paths that already move quantities honestly — it excludes the reading and records a manual element of the new family with the reading's measures; quantities never change by a label. Pooling and consent are F3; F1 labels stay in the project.

### Task 1 · `detection/features.py`
`FEATURES_VERSION = 1`; `Contexto` per run (grid intersections per sheet, mark repetition); `features(detection, ctx)` → size (m), section/length/area in metres, mark prefix and repetition, distance to the nearest eje intersection, layer and block tokens, rule method. Labels carry `features_version` + `features`.

### Task 2 · Reviews that survive a reprocess
`DetectionReview.element_id`; set when a review is saved; after each processing, a review whose key no longer exists is re-keyed to the detection with the same `element_id`; the rest are reported as orphan.

### Task 3 · Candidates
`detection/candidates.py`: after detection, closed polylines and block inserts on non-index sheets whose size fits a structural element and that no detection covers → `candidates.jsonl` with features and verdict «no considerado». Counted on Marina.

### Task 4 · Gestures
`POST /projects/{id}/reviews/detections/{key}/reasignar` (family, note): exclude + manual element with measures from the reading; label `reassign`. Omitted elements gain an optional `bbox` and write an `add_missed` label. Revisión row action «Es otro elemento…» with the family picker.

### Task 5 · Docs, bitácora, memory, fences, finishing menu.
