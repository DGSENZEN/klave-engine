"""Confidence model: log-odds evidence fusion properties."""

from klave_engine.detection.confidence import (
    NEAR_GRID,
    SEMANTIC_LAYER,
    ConfidenceModel,
    model_for,
    score_batch,
)


def test_bounded_and_monotone() -> None:
    model = ConfidenceModel(prior_logit=-0.85, weights={SEMANTIC_LAYER: 1.6, NEAR_GRID: 1.0})
    none = model.score({})
    one = model.score({SEMANTIC_LAYER: 1.0})
    two = model.score({SEMANTIC_LAYER: 1.0, NEAR_GRID: 1.0})
    # Strictly increasing with corroborating evidence, always in (0, 1).
    assert 0.0 < none < one < two < 1.0


def test_prior_recovers_sigmoid_of_logit() -> None:
    model = ConfidenceModel(prior_logit=0.0, weights={})
    assert abs(model.score({}) - 0.5) < 1e-9


def test_explain_reports_signed_contributions() -> None:
    model = ConfidenceModel(prior_logit=0.0, weights={SEMANTIC_LAYER: 1.6})
    notes = model.explain({SEMANTIC_LAYER: 1.0})
    assert notes and "+1.60" in notes[0]


def test_score_batch_matches_scalar() -> None:
    model = model_for("wall")
    rows = [{SEMANTIC_LAYER: 1.0}, {}, {SEMANTIC_LAYER: 1.0, "geometría plausible": 1.0}]
    batch = score_batch(model, rows)
    for row, b in zip(rows, batch, strict=True):
        assert abs(model.score(row) - float(b)) < 1e-9


def test_default_models_lift_semantic_layer_above_base() -> None:
    # The point of the redesign: a wall on a wall-named layer is no longer
    # capped low — it clears 0.75, where the old additive model maxed at 0.70.
    wall = model_for("wall")
    assert wall.score({"geometría plausible": 1.0}) < 0.6  # lone geometry stays low
    assert wall.score({SEMANTIC_LAYER: 1.0, "geometría plausible": 1.0}) > 0.75
