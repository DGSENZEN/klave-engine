"""DXF parsing via ezdxf: open files, extract modelspace, normalize entities."""

import io
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import recover as ezdxf_recover
from ezdxf.lldxf.const import DXFStructureError

from klave_engine.common.errors import DxfParseError
from klave_engine.common.ids import IdGenerator
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.dxf.entities import NormalizedEntity, ParseWarning
from klave_engine.dxf.normalizer import normalize_entity

logger = get_logger(__name__)


def _sanitize_dxf_text(raw: str) -> str:
    """Repair DXF text where string values contain literal newlines.

    ASCII DXF strictly alternates group-code lines and value lines. Some
    converters (e.g. LibreDWG) write MTEXT values with embedded newlines,
    which desynchronizes the tag stream. Any line found where a group code
    is expected but is not an integer is rejoined to the previous value
    using the MTEXT line break ``\\P``.
    """
    out: list[str] = []
    expecting_code = True
    for line in raw.splitlines():
        if expecting_code:
            try:
                int(line.strip())
            except ValueError:
                if out:
                    out[-1] += "\\P" + line
                continue
            out.append(line)
            expecting_code = False
        else:
            out.append(line)
            expecting_code = True
    return "\n".join(out) + "\n"


@dataclass
class ParsedDrawing:
    source_file: str
    entities: list[NormalizedEntity] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    insunits: int | None = None


class DxfParser:
    """Parses DXF files into normalized entities, sharing one entity ID namespace."""

    def __init__(self, ids: IdGenerator | None = None) -> None:
        self._ids = ids or IdGenerator("ent")

    def parse_file(self, path: Path) -> ParsedDrawing:
        if not path.exists():
            raise DxfParseError(f"DXF file does not exist: {path}")
        recover_warnings: list[ParseWarning] = []
        try:
            doc = ezdxf.readfile(str(path))
        except (DXFStructureError, UnicodeDecodeError):
            # Real-world DXF (especially converter output) is often slightly
            # malformed; retry with ezdxf's recover loader, then with a
            # sanitized copy, before giving up.
            doc, warning = self._load_with_recovery(path)
            recover_warnings.append(warning)
        except OSError as exc:
            raise DxfParseError(f"Failed to read DXF file {path}: {exc}") from exc

        drawing = ParsedDrawing(
            source_file=path.name,
            layers=[layer.dxf.name for layer in doc.layers],
            blocks=[block.name for block in doc.blocks if not block.name.startswith("*")],
            warnings=recover_warnings,
            insunits=int(doc.header.get("$INSUNITS", 0)) or None,
        )

        for entity in doc.modelspace():
            normalized, warnings = normalize_entity(entity, path.name, self._ids)
            drawing.warnings.extend(warnings)
            if normalized is not None:
                drawing.entities.append(normalized)

        log_stage(
            logger,
            "dxf_parse_completed",
            input_path=path,
            entity_count=len(drawing.entities),
            warning_count=len(drawing.warnings),
            layer_count=len(drawing.layers),
        )
        return drawing

    def parse_files(self, paths: list[Path]) -> list[ParsedDrawing]:
        return [self.parse_file(path) for path in paths]

    def _load_with_recovery(self, path: Path):
        try:
            doc, auditor = ezdxf_recover.readfile(str(path))
            method = "recovery mode"
        except (DXFStructureError, UnicodeDecodeError):
            try:
                raw = path.read_bytes().decode("utf-8", errors="replace")
                stream = io.BytesIO(_sanitize_dxf_text(raw).encode("utf-8"))
                doc, auditor = ezdxf_recover.read(stream)
                method = "sanitized recovery mode (embedded newlines rejoined)"
            except (DXFStructureError, OSError, UnicodeDecodeError) as exc:
                raise DxfParseError(f"Failed to read DXF file {path}: {exc}") from exc
        except OSError as exc:
            raise DxfParseError(f"Failed to read DXF file {path}: {exc}") from exc
        warning = ParseWarning(
            warning_type="dxf_recovered",
            message=(
                f"Strict DXF parsing failed; loaded in {method} "
                f"({len(auditor.errors)} audit errors, "
                f"{len(auditor.fixes)} fixes applied)"
            ),
            source_file=path.name,
        )
        return doc, warning
