# Detection Rules

All detectors are deterministic, independently testable, configurable
(`DetectorSuiteConfig`, overridable via `KLAVE_DETECTOR_CONFIG_PATH` JSON), and
return `DetectorOutput` (detections + graph nodes/edges + warnings). Confidence
is additive from a base score plus bonuses, clamped and rounded.

## Text patterns (`text_patterns.py`)

| Category | Default patterns |
|---|---|
| column_tag | `^C-?\d{1,3}$`, `^COL-?\d{1,3}$`, `^K\d{1,3}$` |
| beam_tag | `^B-?\d{1,3}$`, `^G-?\d{1,3}$`, `^TB-?\d{1,3}$` |
| detail_reference | `^(\d{1,3}|[A-Z])\s*/\s*([A-Z]{1,2}-?\d{2,4})$` |
| grid_label | `^[A-Z]{1,2}$`, `^\d{1,2}$` |
| sheet_reference | `^[A-Z]{1,2}-?\d{2,4}$` |
| section_marker | `^[A-Z]-[A-Z]$` |

## Grid detector

Candidates: axis-aligned lines (±2°) at least 50% of the drawing extent along
their axis. Labels: grid-label text near line endpoints (radius = 5% of extent
diagonal). Confidence 0.9 labeled / 0.6 unlabeled. Intersections of
horizontal × vertical candidates become `grid_intersection` nodes labeled
`H/V` (e.g. `B/1`).

## Column detector

Column-tag text starts at 0.5; +0.2 grid intersection within 40 units;
+0.2 marker geometry (circle/insert/small closed polyline) within 20 units;
+0.1 layer hint (`COL`); clamped at 0.95.

## Footing detector

Closed polylines, area in [100, 50000], rectangularity ≥ 0.75. Base 0.4;
+0.2 layer hint (`FOOT|FOUND|FDN`); +0.2 column tag within 50 units;
+0.1 rectangularity ≥ 0.9.

## Beam detector

Beam-tag text, base 0.5; +0.2 open linework ≥ 50 units within 30 units
(nearest wins; its length becomes `estimated_span_length`); +0.1 layer hint.

## Slab detector

Hatches (base 0.5) and closed polylines (base 0.4) with area ≥ 10000;
+0.2 layer hint (`SLAB|DECK`).

## Wall detector

Pairs of parallel lines (±2°) each ≥ 100 units, gap ≤ 25 units, projected
overlap ≥ 50% of the shorter line. Base 0.5; +0.2 layer hint (`WALL`).
Each line participates in at most one wall.

## Detail reference detector

Detail-reference text, confidence 0.85. The target sheet is checked against
the project manifest sheet numbers (dash-insensitive); `resolved` is recorded
in properties and drives the `unresolved_detail_reference` risk rule.

## Risk rules

unresolved_detail_reference (high), column_tag_without_grid (medium),
footing_without_column (medium), duplicate_column_tag > 100 units apart
(medium), low_confidence_detection_in_takeoff < 0.7 (low),
unknown_drawing_units (low), unknown_layer_entities > 50% (low),
empty_drawing_after_parsing (high).
