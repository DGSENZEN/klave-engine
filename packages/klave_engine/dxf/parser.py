"""DXF parsing via ezdxf: open files, resolve xrefs, read layouts, normalize model space."""

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
from klave_engine.dxf.layouts import LayoutInfo, XrefInfo, read_layouts, resolve_xrefs
from klave_engine.dxf.normalizer import normalize_entity

logger = get_logger(__name__)

MAX_CHILDREN_PER_INSERT = 300
MAX_EXPLODED_PER_FILE = 15_000


@dataclass
class _ExplosionBudget:
    total: int = 0
    capped: bool = False


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
    layouts: list[LayoutInfo] = field(default_factory=list)
    xrefs: list[XrefInfo] = field(default_factory=list)


class DxfParser:
    """Parses DXF files into normalized entities, sharing one entity ID namespace."""

    def __init__(self, ids: IdGenerator | None = None) -> None:
        self._ids = ids or IdGenerator("ent")

    def parse_file(self, path: Path, source_file: str | None = None) -> ParsedDrawing:
        if not path.exists():
            raise DxfParseError(f"DXF file does not exist: {path}")
        source_file = source_file or path.name
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
            source_file=source_file,
            layers=[layer.dxf.name for layer in doc.layers],
            blocks=[block.name for block in doc.blocks if not block.name.startswith("*")],
            warnings=recover_warnings,
            insunits=int(doc.header.get("$INSUNITS", 0)) or None,
        )

        # External references first: an embedded xref becomes an ordinary
        # block, so its content explodes along with everything else below.
        drawing.xrefs, xref_warnings = resolve_xrefs(doc, path, source_file)
        drawing.warnings.extend(xref_warnings)
        drawing.layouts = read_layouts(doc, drawing.insunits)

        explosion = _ExplosionBudget()
        for entity in doc.modelspace():
            normalized, warnings = normalize_entity(entity, source_file, self._ids)
            drawing.warnings.extend(warnings)
            if normalized is not None:
                drawing.entities.append(normalized)
            if entity.dxftype() == "INSERT":
                self._explode_insert(entity, drawing, source_file, explosion, depth=0)
        if explosion.capped:
            drawing.warnings.append(
                ParseWarning(
                    warning_type="block_explosion_capped",
                    message=(
                        "Algunos bloques tienen demasiadas entidades internas; "
                        f"se conservaron {explosion.total} y se omitió el resto."
                    ),
                    source_file=source_file,
                )
            )

        log_stage(
            logger,
            "dxf_parse_completed",
            input_path=path,
            entity_count=len(drawing.entities),
            warning_count=len(drawing.warnings),
            layer_count=len(drawing.layers),
        )
        return drawing

    def parse_files(
        self, paths: list[Path], source_files: list[str] | None = None
    ) -> list[ParsedDrawing]:
        if source_files is not None and len(paths) != len(source_files):
            raise ValueError("paths and source_files must have the same length")
        return [
            self.parse_file(path, source_file=source_files[index] if source_files else None)
            for index, path in enumerate(paths)
        ]

    def _explode_insert(
        self,
        insert: object,
        drawing: ParsedDrawing,
        source_file: str,
        budget: "_ExplosionBudget",
        depth: int,
    ) -> None:
        """Expand a block reference's geometry into normalized entities.

        Real drawings hide meaningful geometry (castillo symbols, column
        marks, section fills) inside block definitions; without explosion the
        pipeline only ever sees the INSERT's bounding box. Children keep the
        block as provenance, adopt the insert's layer when they sit on layer
        "0" (standard CAD by-block convention), and are budget-capped so a
        pathological block cannot flood the entity space.
        """
        if depth >= 2 or budget.capped:
            return
        insert_layer = str(insert.dxf.layer)  # type: ignore[attr-defined]
        insert_handle = str(insert.dxf.handle)  # type: ignore[attr-defined]
        block_name = str(insert.dxf.name)  # type: ignore[attr-defined]
        emitted = 0
        try:
            children = list(insert.virtual_entities())  # type: ignore[attr-defined]
        except Exception:
            drawing.warnings.append(
                ParseWarning(
                    warning_type="block_explosion_failed",
                    message=f"No se pudo expandir el bloque {block_name}",
                    entity_type="INSERT",
                    handle=insert_handle,
                    layer=insert_layer,
                    source_file=source_file,
                )
            )
            return
        for index, child in enumerate(children):
            if emitted >= MAX_CHILDREN_PER_INSERT or budget.total >= MAX_EXPLODED_PER_FILE:
                budget.capped = True
                return
            if child.dxftype() == "INSERT":
                self._explode_insert(child, drawing, source_file, budget, depth + 1)
                continue
            normalized, _warnings = normalize_entity(child, source_file, self._ids)
            if normalized is None:
                continue
            if normalized.layer == "0":
                normalized.layer = insert_layer
            normalized.raw_handle = f"{insert_handle}#{index}"
            normalized.block_name = block_name
            normalized.properties["from_block"] = block_name
            normalized.properties["parent_insert"] = insert_handle
            normalized.evidence.notes.append(f"Expandido del bloque {block_name}")
            drawing.entities.append(normalized)
            emitted += 1
            budget.total += 1

    def _load_with_recovery(self, path: Path):
        try:
            doc, auditor = ezdxf_recover.readfile(str(path))
            method = "recovery mode"
        except (DXFStructureError, UnicodeDecodeError):
            try:
                raw_bytes = path.read_bytes()
                # Mexican office drawings frequently carry cp1252 accents; try
                # strict UTF-8 first and fall back before replacing bytes.
                try:
                    raw = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        raw = raw_bytes.decode("cp1252")
                    except UnicodeDecodeError:
                        raw = raw_bytes.decode("utf-8", errors="replace")
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
