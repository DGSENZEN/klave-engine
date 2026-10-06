# Lector F3a · «Aquí hay un elemento» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** the shapes no rule took get ranked by a small model trained on geometry; the likely ones appear dashed in the visor and in Revisión → Propuestas, uncounted until a person confirms one as a family (castillo, columna, pilote, zapata) or rejects it — and both decisions become labels.

**Architecture:** training is offline (`klave_engine.lector.entrenar`, scikit-learn in the optional `lector` group) and exports the gradient-boosted trees as JSON into `klave_engine/lector/modelos/<version>/`; the runtime scores in pure Python (`klave_engine.lector.modelo`), no new dependency. The pipeline writes `propuestas.json` after the candidates; detections and quantities are untouched (gold unchanged). Confirming goes through the existing `OmittedElement` path with the bbox's measure; rejecting writes a label. Both hide the proposal on later runs (read from `labels.jsonl`).

**Spec:** `docs/superpowers/specs/2026-10-04-lector-que-aprende-design.md` (§4 tier 3, §5 row 3, §7, §12 S0(a)).

## Global constraints

- No probability, score or confidence on any screen or export; the reason is said in words from the features.
- A proposal never counts until a person confirms it; confirmation uses the omitted-element path (`levantamiento_manual`).
- Features: geometry only (S0: names do not transfer) — `ancho_m`, `alto_m`, `proporcion`, `area_m2`, `dist_eje_m`, `repeticion_bloque`.
- Threshold chosen on leave-one-project-out predictions: lowest score with pooled precision ≥ 0.90; at most 25 proposals per sheet (highest first).
- Promotion: a new version becomes active only if, on every held-out project, its precision is not more than 1 point below the active one's.
- Model files carry thresholds and counts only — no names, coordinates or text.

### Task 1: model, training, export
- `packages/klave_engine/lector/__init__.py`, `rasgos.py` (`vector(features) -> list[float|None]`, `NOMBRES`), `modelo.py` (`Modelo.cargar(dir)`, `Modelo.activo()`, `puntuar(vector) -> float`, `umbral`, `max_por_hoja`), `entrenar.py` (dataset from processed dirs: accepted detections in the 0.08–3 m window = elemento, candidates = no; human labels override; LOPO report; export; `--promover`).
- `pyproject.toml` dependency group `lector = ["scikit-learn>=1.4"]`.
- Tests: pure-Python scoring equals scikit-learn's `predict_proba` on a fitted fixture (skipped when sklearn absent); export carries no strings beyond feature names.
- Train v1 on Marina estructural + PRUEBA-1 + S-101; commit the model.

### Task 2: pipeline + API
- `lector/propuestas.py`: `proponer(candidates, modelo, factor, ocultas) -> list[dict]` (key `pr_<sha1>` of sheet, 5 cm centroid, block; reason in words), `claves_resueltas(labels)`.
- Pipeline: after the profile, write `propuestas.json`, one warning line.
- `apps/api/routes/propuestas.py`: `GET /projects/{id}/propuestas`, `POST …/{key}/confirmar {family}` (OmittedElement from the bbox: section_cm for castillo/columna, area for zapata; label `confirm_proposal`), `POST …/{key}/descartar` (label `reject_proposal`). Both recompute like the reviews.
- `perfil.aprender` counts `confirm_proposal` with its block.
- Tests: proposals written, rejected/confirmed hidden, confirm adds an omitted element with bbox and section, gold green.

### Task 3: Revisión + visor
- Revisión tab «Propuestas» (`components/PropuestasSection.tsx`): sheet, size, reason, «Ver en el plano», family picker + «Es un elemento» / «No es elemento».
- Plano `?propuestas=1`: dashed boxes via `ghosts` + legend «no cuenta hasta confirmarla».

### Task 4: docs, bitácora, memory, fences, finishing menu.
