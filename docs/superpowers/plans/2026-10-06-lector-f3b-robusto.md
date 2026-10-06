# Lector F3b · El lector robusto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** the reader stops teaching itself that misses are not elements, never goes silent on a project it trained on, refuses to run blind (no units, wrong feature version), keeps a live record of how often people accept it (and pauses itself for an office that keeps rejecting it), is judged against a people-checked set, and retrains with one command that gathers every project's decisions.

**Spec:** `docs/superpowers/specs/2026-10-04-lector-que-aprende-design.md` §7, §8, §12.

## Global constraints

- Quantities move only by a person; no score on any screen; proposals stay uncounted.
- Model files: thresholds, counts and opaque project hashes only.
- A project in the training set is scored by a model trained without it (out-of-fold), never by the full model.
- Unreviewed candidates are *unknown*, not *no*: weight 0.3. Human decisions weight 5; rule-accepted detections weight 1.
- No proposals without confirmed units, or when the candidates' features version differs from the model's; each refusal is one warning line.
- Promotion requires: per-project held-out precision not more than 1 point below the active model's, and on every people-checked set (`evals/lector/*.json`) precision not more than 1 point and recall not more than 2 points below. People-checked projects never enter training.
- Pause: an office with ≥ 20 decisions since its last resume and acceptance < 30 % gets no proposals; said in the run warning and in the catálogo, with «Reanudar».

### Task 1: training that doesn't punish misses + out-of-fold
- `entrenar.ejemplos(proyecto) -> list[(vector, y, peso)]`, reading artifacts from the active run (`processed/active_run.json`) and labels from `processed/`.
- Labels on candidates (`confirm_proposal`/`reject_proposal`) replace the candidate's weak row (by proposal key).
- `exportar` writes `{"completo": modelo, "pliegues": {hash: modelo}, "features_version": 1}`; `Modelo.para(project_id)` returns the fold model when the project trained it.
- Smaller trees (`max_iter=120, max_leaf_nodes=15`).

### Task 2: guards
- Pipeline: no proposals when `units.to_meters()` is None or features version mismatch; warning per case.

### Task 3: people-checked set + live record + pause
- `GET /projects/{id}/propuestas?todas=1`: every in-window candidate on structural plan views (no threshold, no cap), for checking.
- `lector/oro.py`: `capturar(proyecto, nombre)` writes `evals/lector/<nombre>.json` from the project's proposal labels (key, features, verdict, project hash); `evaluar(modelo, oro) -> {precision, recall}`.
- Store table `lector_decisiones (version, key, accion, at)`; written on confirm/reject; `aceptacion(desde)`; setting `lector_reanudado`.
- `GET /catalog/lector` (version, decisions, accepted, paused) and `POST /catalog/lector/reanudar` (admin); catálogo panel «El lector».

### Task 4: one command
- `klave train-reader [--promover]`: every project under the data dir with candidates, minus people-checked ones; prints the report; promotion as above.

### Task 5: docs, bitácora, memory, fences, finishing menu.
