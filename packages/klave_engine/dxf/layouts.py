"""Paper space and external references: what a DXF says about *how the
sheet is printed* and *what it borrows from other files*.

Layouts carry viewports — printed windows onto model space with a scale —
plus any title-block text or attributes drawn in paper space. External
references (xrefs) are blocks whose content lives in another file; when that
file is in the project the reference is embedded in place, so the block
explodes like any other. When it is not, the gap is reported, never hidden.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from ezdxf import xref as ezdxf_xref
from pydantic import BaseModel, Field

from klave_engine.dxf.entities import ParseWarning

MAX_PAPER_TEXTS = 40
MAX_ATTRIBUTES = 40

# $INSUNITS → millimetres per drawing unit, for a "1:N" estimate.
_UNIT_MM = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}


class ViewportInfo(BaseModel):
    center: tuple[float, float]
    width: float
    height: float
    view_center: tuple[float, float]
    view_height: float
    scale_factor: float  # model units per paper unit
    scale_label: str | None = None  # "≈ 1:200" when the drawing unit is known
    model_bbox: tuple[float, float, float, float]


class LayoutInfo(BaseModel):
    name: str
    viewports: list[ViewportInfo] = Field(default_factory=list)
    texts: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)


class XrefInfo(BaseModel):
    name: str
    path: str
    resolved_path: str | None = None
    status: Literal["embedded", "missing", "failed"]


def _is_overall_viewport(viewport: Any) -> bool:
    """The first viewport of a layout is the paper itself, not a window."""
    d = viewport.dxf
    same_center = (
        abs(d.center.x - d.view_center_point.x) < 1e-6
        and abs(d.center.y - d.view_center_point.y) < 1e-6
    )
    return bool(same_center and abs(d.height - d.view_height) < 1e-6)


def read_layouts(doc: Any, insunits: int | None) -> list[LayoutInfo]:
    unit_mm = _UNIT_MM.get(insunits or 0)
    layouts: list[LayoutInfo] = []
    for layout in doc.layouts:
        if layout.name == "Model":
            continue
        info = LayoutInfo(name=layout.name)
        for entity in layout:
            kind = entity.dxftype()
            if kind == "VIEWPORT":
                if _is_overall_viewport(entity) or entity.dxf.height <= 0:
                    continue
                d = entity.dxf
                scale = d.view_height / d.height
                half_h = d.view_height / 2.0
                half_w = half_h * (d.width / d.height)
                label = None
                if unit_mm:
                    ratio = scale * unit_mm
                    if 5 <= ratio <= 5000:
                        label = f"≈ 1:{round(ratio)}"
                info.viewports.append(
                    ViewportInfo(
                        center=(float(d.center.x), float(d.center.y)),
                        width=float(d.width),
                        height=float(d.height),
                        view_center=(float(d.view_center_point.x), float(d.view_center_point.y)),
                        view_height=float(d.view_height),
                        scale_factor=round(scale, 6),
                        scale_label=label,
                        model_bbox=(
                            float(d.view_center_point.x - half_w),
                            float(d.view_center_point.y - half_h),
                            float(d.view_center_point.x + half_w),
                            float(d.view_center_point.y + half_h),
                        ),
                    )
                )
            elif kind in ("TEXT", "MTEXT") and len(info.texts) < MAX_PAPER_TEXTS:
                text = entity.plain_text() if kind == "MTEXT" else str(entity.dxf.text)
                text = " ".join(text.split())
                if text:
                    info.texts.append(text[:120])
            elif kind == "INSERT" and len(info.attributes) < MAX_ATTRIBUTES:
                for attrib in entity.attribs:
                    tag = str(attrib.dxf.tag).strip()
                    value = " ".join(str(attrib.dxf.text).split())
                    if tag and value and tag not in info.attributes:
                        info.attributes[tag] = value[:120]
        if info.viewports or info.texts or info.attributes:
            layouts.append(info)  # an empty paper space says nothing worth listing
    return layouts


def _slug_key(stem: str) -> str:
    """La subida slugifica los nombres («00 XREF L.04» → 00_xref_l_04): para
    casar un xref con su archivo, solo cuentan las letras y los números."""
    return re.sub(r"[^a-z0-9]+", "", stem.lower())


def _find_sibling(stem: str, search_dirs: Iterable[Path]) -> Path | None:
    wanted = _slug_key(stem)
    if not wanted:
        return None
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.rglob("*.dxf")):
            if _slug_key(candidate.stem) == wanted:
                return candidate
    return None


def resolve_xrefs(
    doc: Any, dxf_path: Path, source_file: str
) -> tuple[list[XrefInfo], list[ParseWarning]]:
    """Embed every external reference whose file is in the project; report the
    rest. Must run before model space is walked so embedded blocks explode."""
    xrefs: list[XrefInfo] = []
    warnings: list[ParseWarning] = []
    # La hoja puede vivir en drawings/ o en converted/<dir>/: el abuelo
    # cubre ambos (rglob baja a los subdirectorios), y el caso drawings
    # conserva su ruta explícita a converted/.
    search_dirs = [
        dxf_path.parent,
        dxf_path.parent.parent,
        dxf_path.parent.parent / "converted",
    ]
    for block in list(doc.blocks):
        try:
            is_xref = bool(block.block_record.is_xref)
        except AttributeError:
            # LibreDWG can emit a block record without its BLOCK entity;
            # nothing to resolve there, and the sheet must still load.
            warnings.append(
                ParseWarning(
                    warning_type="block_record_incomplete",
                    message=f"Bloque {block.name!r} sin definición completa; se omite como xref",
                    entity_type="BLOCK",
                    handle="",
                    layer="",
                    source_file=source_file,
                )
            )
            continue
        if not is_xref:
            continue
        xref_path = str(block.block.dxf.get("xref_path", "") or "")
        stem = Path(xref_path).stem or block.name
        found = _find_sibling(stem, search_dirs)
        if found is None:
            xrefs.append(XrefInfo(name=block.name, path=xref_path, status="missing"))
            warnings.append(
                ParseWarning(
                    warning_type="xref_missing",
                    message=(
                        f"Referencia externa «{block.name}» ({xref_path or 'sin ruta'}) no está "
                        "en el proyecto; súbela como hoja adicional para leer su contenido."
                    ),
                    entity_type="XREF",
                    source_file=source_file,
                )
            )
            continue
        # ezdxf valida la ruta declarada del bloque antes de consultar el
        # load_fn: se reescribe a la resuelta o el embed muere en un
        # FileNotFoundError aunque el archivo esté en el proyecto.
        try:
            block.block.dxf.xref_path = str(found)
        except Exception:
            pass

        def load_resolved(_filename: str | Path, path: Path = found) -> Any:
            # La escalera completa, no solo la lectura estricta: el xref
            # suele venir de una conversión mínima con sus propias mañas.
            from klave_engine.dxf.loader import load_dxf

            return load_dxf(path).doc

        try:
            ezdxf_xref.embed(block, load_fn=load_resolved)
        except Exception as exc:  # ezdxf raises a family of loader errors
            xrefs.append(
                XrefInfo(name=block.name, path=xref_path, resolved_path=str(found), status="failed")
            )
            warnings.append(
                ParseWarning(
                    warning_type="xref_failed",
                    message=f"No se pudo incorporar la referencia externa «{block.name}»: {exc}",
                    entity_type="XREF",
                    source_file=source_file,
                )
            )
            continue
        xrefs.append(
            XrefInfo(name=block.name, path=xref_path, resolved_path=str(found), status="embedded")
        )
        warnings.append(
            ParseWarning(
                warning_type="xref_embedded",
                message=f"Referencia externa «{block.name}» incorporada desde {found.name}.",
                entity_type="XREF",
                source_file=source_file,
            )
        )
    return xrefs, warnings
