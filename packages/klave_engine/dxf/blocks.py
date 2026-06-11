"""Block usage summaries for inspection artifacts."""

from collections import Counter

from klave_engine.dxf.entities import EntityType, NormalizedEntity


def summarize_blocks(entities: list[NormalizedEntity]) -> list[dict]:
    """Counts of block inserts by block name."""
    counts = Counter(
        entity.block_name
        for entity in entities
        if entity.entity_type == EntityType.insert and entity.block_name
    )
    return [
        {"block_name": name, "insert_count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
