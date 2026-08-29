"""DXF parsing via ezdxf: open files, resolve xrefs, read layouts, normalize model space."""

from dataclasses import dataclass, field
from pathlib import Path

from klave_engine.common.errors import DxfParseError
from klave_engine.common.ids import IdGenerator
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.dxf.entities import NormalizedEntity, ParseWarning
from klave_engine.dxf.layouts import LayoutInfo, XrefInfo, read_layouts, resolve_xrefs
from klave_engine.dxf.loader import NON_GRAPHICAL_TYPES, load_dxf
from klave_engine.dxf.normalizer import normalize_entity

logger = get_logger(__name__)

MAX_CHILDREN_PER_INSERT = 20_000
MAX_EXPLODED_PER_FILE = 400_000


@dataclass
class _ExplosionBudget:
    total: int = 0
    capped: bool = False
    nesting_truncated: bool = False


@dataclass
class ParsedDrawing:
    source_file: str
    entities: list[NormalizedEntity] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    # Definición → tags de sus ATTDEF: el índice de prefabricados los lee.
    block_attdefs: dict[str, list[str]] = field(default_factory=dict)
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
            loaded = load_dxf(path)
        except ValueError as exc:
            raise DxfParseError(f"Failed to read DXF file {path}: {exc}") from exc
        doc = loaded.doc
        if loaded.method != "strict":
            detail = f"{loaded.audit_errors} audit errors, {loaded.audit_fixes} fixes applied"
            if loaded.method == "sanitized":
                detail += (
                    f"; {loaded.rejoined_lines} líneas de texto reunidas, "
                    f"{loaded.dropped_objects} objetos no geométricos retirados de ENTITIES"
                )
            recover_warnings.append(
                ParseWarning(
                    warning_type="dxf_recovered",
                    message=(
                        f"Strict DXF parsing failed; loaded in {loaded.method} mode ({detail})"
                    ),
                    source_file=path.name,
                )
            )

        drawing = ParsedDrawing(
            source_file=source_file,
            layers=[layer.dxf.name for layer in doc.layers],
            blocks=[block.name for block in doc.blocks if not block.name.startswith("*")],
            warnings=recover_warnings,
            insunits=int(doc.header.get("$INSUNITS", 0)) or None,
        )
        for block in doc.blocks:
            if block.name.startswith("*"):
                continue
            try:
                tags = [str(a.dxf.tag) for a in block.query("ATTDEF") if a.dxf.tag]
            except Exception:
                continue
            if tags:
                drawing.block_attdefs[block.name] = tags

        # External references first: an embedded xref becomes an ordinary
        # block, so its content explodes along with everything else below.
        drawing.xrefs, xref_warnings = resolve_xrefs(doc, path, source_file)
        drawing.warnings.extend(xref_warnings)
        drawing.layouts = read_layouts(doc, drawing.insunits)

        explosion = _ExplosionBudget()
        for entity in doc.modelspace():
            kind = entity.dxftype()
            if kind in NON_GRAPHICAL_TYPES:
                # A converter filed an OBJECT among the entities; it has no
                # geometry and must not stop the sheet.
                drawing.warnings.append(
                    ParseWarning(
                        warning_type="non_graphical_in_entities",
                        message=f"Objeto {kind} sin geometría encontrado entre las entidades",
                        entity_type=kind,
                        source_file=source_file,
                    )
                )
                continue
            try:
                normalized, warnings = normalize_entity(entity, source_file, self._ids)
            except Exception as exc:  # one broken entity never costs the sheet
                drawing.warnings.append(
                    ParseWarning(
                        warning_type="entity_unreadable",
                        message=f"Entidad {kind} ilegible: {type(exc).__name__}: {exc}"[:200],
                        entity_type=kind,
                        handle=str(getattr(entity.dxf, "handle", "") or "") or None,
                        source_file=source_file,
                    )
                )
                continue
            drawing.warnings.extend(warnings)
            if normalized is not None:
                drawing.entities.append(normalized)
            if kind == "INSERT":
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
        if explosion.nesting_truncated:
            drawing.warnings.append(
                ParseWarning(
                    warning_type="block_nesting_truncated",
                    message=(
                        "Hay bloques anidados a más de dos niveles; la geometría "
                        "del nivel más profundo no se leyó."
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
        if depth >= 2:
            # El corte no es silencioso: la geometría del nivel 3 no entró.
            budget.nesting_truncated = True
            return
        if budget.capped:
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
                # El INSERT anidado también es una entidad: sin normalizarlo,
                # su nombre de bloque y sus atributos se perdían para siempre
                # (y el levantamiento subcontaba símbolos empacados).
                try:
                    nested, _warnings = normalize_entity(child, source_file, self._ids)
                except Exception:
                    nested = None
                if nested is not None:
                    if nested.layer == "0":
                        nested.layer = insert_layer
                    nested.raw_handle = f"{insert_handle}#{index}"
                    nested.properties["from_block"] = block_name
                    nested.properties["parent_insert"] = insert_handle
                    nested.evidence.notes.append(f"Expandido del bloque {block_name}")
                    drawing.entities.append(nested)
                    emitted += 1
                    budget.total += 1
                self._explode_insert(child, drawing, source_file, budget, depth + 1)
                continue
            if child.dxftype() in NON_GRAPHICAL_TYPES:
                continue
            try:
                normalized, _warnings = normalize_entity(child, source_file, self._ids)
            except Exception:
                continue
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
