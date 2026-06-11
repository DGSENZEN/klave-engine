"""Layer summaries for inspection artifacts."""

from collections import defaultdict

from klave_engine.dxf.entities import NormalizedEntity


def summarize_layers(entities: list[NormalizedEntity]) -> list[dict]:
    """Per-layer entity counts and entity type breakdown, sorted by count."""
    by_layer: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entity in entities:
        by_layer[entity.layer][entity.entity_type.value] += 1
    summary = [
        {
            "layer": layer,
            "entity_count": sum(type_counts.values()),
            "entity_types": dict(sorted(type_counts.items())),
        }
        for layer, type_counts in by_layer.items()
    ]
    return sorted(summary, key=lambda item: (-item["entity_count"], item["layer"]))
