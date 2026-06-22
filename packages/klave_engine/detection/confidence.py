"""Confidence as log-odds evidence fusion (Naive-Bayes / logistic form).

Every detector expresses its result as a set of **evidence features** (layer
match, geometry fit, proximity, corroboration…). Confidence is then::

    confidence = sigmoid( prior_logit + Σ weightᵢ · featureᵢ )

Each weight is a log-likelihood-ratio: how much that signal multiplies the odds
the candidate is a real structural element. This is the exact functional form
of logistic regression, so the hand-set weights here are simply priors — once
labeled drawings exist, the same model is *fitted* with no code change. The
sigmoid bounds the result in (0, 1) naturally, removing the hard ceilings that
the old additive scheme imposed, and every feature's contribution is reportable
so each score is explainable.
"""

import numpy as np
from pydantic import BaseModel, Field

# Evidence feature names (shared vocabulary across detectors).
TEXT_PATTERN = "patrón de texto"
SEMANTIC_LAYER = "capa semántica"
MARKER = "geometría marcadora"
NEAR_GRID = "cerca de eje"
GEOM_PLAUSIBLE = "geometría plausible"
HIGH_RECT = "alta rectangularidad"
NEAR_COLUMN = "cerca de columna"
NEAR_LINE = "cerca de linework"
IS_HATCH = "es hatch"
GRID_LABEL = "etiqueta de eje"
LARGE_AREA = "área grande"
BLOCK_SEMANTICS = "semántica de bloque"
DIMENSION_MATCH = "cota concordante"


class ConfidenceModel(BaseModel):
    """Log-odds model: prior + weighted evidence through a sigmoid."""

    prior_logit: float = 0.0
    weights: dict[str, float] = Field(default_factory=dict)

    def score(self, features: dict[str, float]) -> float:
        logit = self.prior_logit + sum(
            self.weights.get(name, 0.0) * value for name, value in features.items()
        )
        return float(1.0 / (1.0 + np.exp(-logit)))

    def explain(self, features: dict[str, float]) -> list[str]:
        """Human-readable per-feature contributions (log-odds units)."""
        notes: list[str] = []
        for name, value in features.items():
            contribution = self.weights.get(name, 0.0) * value
            if abs(contribution) >= 1e-6:
                sign = "+" if contribution >= 0 else "−"
                notes.append(f"{name}: {sign}{abs(contribution):.2f}")
        return notes


def score_batch(model: ConfidenceModel, rows: list[dict[str, float]]) -> np.ndarray:
    """Vectorized scoring of many candidates: (N×F) features · (F) weights → sigmoid."""
    if not rows:
        return np.empty(0)
    keys = list(model.weights.keys())
    matrix = np.array([[row.get(k, 0.0) for k in keys] for row in rows], dtype=float)
    weights = np.array([model.weights[k] for k in keys], dtype=float)
    logits = model.prior_logit + matrix @ weights
    return 1.0 / (1.0 + np.exp(-logits))


# --- Default models per detection type -----------------------------------------
# prior_logit encodes how telling the *candidate gate* already is (e.g. a text
# that matches the column-tag regex is decent evidence on its own); weights are
# log-LRs (≈ ln of an odds multiplier): ~0.7 weak, ~1.0 medium, ~1.6 strong.

DEFAULT_MODELS: dict[str, ConfidenceModel] = {
    "grid_line": ConfidenceModel(
        prior_logit=0.40,  # a long axis-aligned line ≈ 0.60 on its own
        weights={GRID_LABEL: 1.80, SEMANTIC_LAYER: 0.60},
    ),
    "column_tag": ConfidenceModel(
        prior_logit=0.40,  # matched a column-tag pattern ≈ 0.60
        weights={NEAR_GRID: 1.30, MARKER: 1.10, SEMANTIC_LAYER: 1.20,
                 DIMENSION_MATCH: 0.80},
    ),
    "footing": ConfidenceModel(
        prior_logit=-0.85,  # a bare closed rectangle ≈ 0.30
        weights={SEMANTIC_LAYER: 1.60, NEAR_COLUMN: 1.20, HIGH_RECT: 0.70,
                 DIMENSION_MATCH: 1.00},
    ),
    "beam_tag": ConfidenceModel(
        prior_logit=0.20,  # matched a beam-tag pattern ≈ 0.55
        weights={NEAR_LINE: 1.00, SEMANTIC_LAYER: 1.00},
    ),
    "slab_region": ConfidenceModel(
        prior_logit=-0.85,
        weights={IS_HATCH: 0.80, SEMANTIC_LAYER: 1.50, LARGE_AREA: 0.40,
                 DIMENSION_MATCH: 1.00},
    ),
    "wall": ConfidenceModel(
        prior_logit=-0.85,  # a lone parallel-line pair ≈ 0.30
        weights={SEMANTIC_LAYER: 1.60, GEOM_PLAUSIBLE: 0.60, DIMENSION_MATCH: 1.00},
    ),
}


def model_for(detection_type: str) -> ConfidenceModel:
    return DEFAULT_MODELS.get(detection_type, ConfidenceModel(prior_logit=0.0))
