"""Evidence packets: every derived fact must say where it came from."""

from pydantic import BaseModel, Field

from klave_engine.geometry.bbox import BBox


class EvidencePacket(BaseModel):
    source: str
    method: str
    entity_ids: list[str] = Field(default_factory=list)
    bbox: BBox | None = None
    confidence: float = 1.0
    notes: list[str] = Field(default_factory=list)
