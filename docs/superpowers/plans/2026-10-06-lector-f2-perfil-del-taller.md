# El lector que aprende · F2 — El perfil del taller — implementation plan

> superpowers:executing-plans, inline. Steps `- [ ]`.

**Spec:** [el lector que aprende](../specs/2026-10-04-lector-que-aprende-design.md) §4 tier 2, F2 in §11.

**Goal:** the office's own conventions, learned from its reviews: the block it uses for a castillo, the layer whose elements it always excludes. The second project from the same office starts with fewer dudas and fewer missed elements.

**Rules:**
- Learned per taller (the workspace catálogo), from F1 labels, updated the moment a review is saved. Nothing pools (that is F3).
- An entry is **firme** with ≥ 3 decisions in favour and none against.
- A firm positive entry (block → family) acts like a rule for that taller: an unclaimed candidate drawn with that block enters the reading with method `perfil_del_taller`, its reason, and the usual exclusion path. F2 applies it only to families counted by piece (castillo, columna, pilote): a learned block cannot supply a length or an area.
- A firm negative entry (this type on this layer or block is excluded) never removes anything: it raises a duda in Revisión with the reason.
- Everything the profile does is said: a warning line per run and the profile listed in the catálogo.

### Task 1 · Store and learning
`perfil_taller` table; `costing/perfil.py` `aprender(store, labels, candidates)` (confirm / exclude / reassign / add_missed); called from the review endpoints after labels are written. Candidates gain their raw block name (local file).

### Task 2 · Application
`aplicar_perfil(detections, candidates, perfil, factor)` in the pipeline before detections are written: positive entries add detections, negative ones set `perfil_duda`; Revisión shows it as a duda; run warning.

### Task 3 · Seeing the profile
`GET /catalog/perfil` and a small section in the catálogo («Lo que tu taller enseñó»), with «Olvidar» per entry.

### Task 4 · Docs, bitácora, memory, fences, finishing menu.
