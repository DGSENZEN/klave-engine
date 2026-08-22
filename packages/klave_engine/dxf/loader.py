"""One way to open a DXF, shared by the parser and the conversion probe.

Real DXF — especially converter output — is slightly wrong in predictable
ways: MTEXT values with literal newlines that desynchronize the tag stream,
OBJECT records (SORTENTSTABLE, dictionaries) dumped into the ENTITIES
section, cp1252 accents. The chain is strict → recover → sanitized copy,
and every failure mode is caught, because an exception type nobody
anticipated must become "unreadable", not a crash in the middle of a run.
"""

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import recover as ezdxf_recover

# DXF OBJECT types a converter may misfile among entities. They carry no
# geometry; dropping them from ENTITIES loses nothing the engine reads.
NON_GRAPHICAL_TYPES = {
    "SORTENTSTABLE", "DICTIONARY", "ACDBDICTIONARYWDFLT", "XRECORD", "LAYOUT",
    "PLOTSETTINGS", "MLEADERSTYLE", "TABLESTYLE", "ACDBPLACEHOLDER", "DICTIONARYVAR",
    "SCALE", "MATERIAL", "VISUALSTYLE", "FIELD", "GROUP", "IDBUFFER", "IMAGEDEF",
    "IMAGEDEF_REACTOR", "RASTERVARIABLES", "SPATIAL_FILTER", "WIPEOUTVARIABLES",
    "LIGHTLIST", "ACAD_PROXY_OBJECT", "MLINESTYLE", "VBA_PROJECT", "DATATABLE",
    "GEODATA", "SUNSTUDY", "TABLECONTENT", "CELLSTYLEMAP", "DBCOLOR", "SECTIONVIEWSTYLE",
    "DETAILVIEWSTYLE", "ACDBNAVISWORKSMODELDEF", "PERSUBENTMGR", "DIMASSOC",
}


@dataclass
class LoadedDxf:
    doc: Any
    method: str  # strict | recovery | sanitized
    audit_errors: int = 0
    audit_fixes: int = 0
    dropped_objects: int = 0
    rejoined_lines: int = 0
    notes: list[str] = field(default_factory=list)


def sanitize_dxf_text(raw: str) -> tuple[str, int, int]:
    """Repair the two converter habits that break ezdxf.

    1. String values with literal newlines: any line found where a group
       code is expected but is not an integer is rejoined to the previous
       value with the MTEXT break ``\\P``.
    2. OBJECT records inside ENTITIES: dropped whole.
    Returns (text, rejoined_lines, dropped_objects)."""
    out: list[str] = []
    expecting_code = True
    rejoined = 0
    dropped = 0
    in_entities = False
    skipping = False
    pending_code: str | None = None
    for line in raw.splitlines():
        if expecting_code:
            stripped = line.strip()
            try:
                int(stripped)
            except ValueError:
                if out:
                    out[-1] += "\\P" + line
                    rejoined += 1
                continue
            pending_code = stripped
            expecting_code = False
            continue
        # value line for pending_code
        code, value = pending_code or "", line
        expecting_code = True
        if code == "0":
            kind = value.strip()
            if kind == "SECTION":
                skipping = False
                in_entities = False
                out.extend([code, value])
                continue
            if kind == "ENDSEC":
                skipping = False
                in_entities = False
                out.extend([code, value])
                continue
            if in_entities and kind in NON_GRAPHICAL_TYPES:
                skipping = True
                dropped += 1
                continue
            skipping = False
        elif code == "2" and out and out[-2:] == ["0", "SECTION"] and value.strip() == "ENTITIES":
            in_entities = True
        if skipping:
            continue
        out.extend([code, value])
    return "\n".join(out) + "\n", rejoined, dropped


def _decode(raw_bytes: bytes) -> str:
    # Mexican office drawings frequently carry cp1252 accents; try strict
    # UTF-8 first and fall back before replacing bytes.
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw_bytes.decode("cp1252")
        except UnicodeDecodeError:
            return raw_bytes.decode("utf-8", errors="replace")


def load_dxf(path: Path) -> LoadedDxf:
    """Open a DXF by any honest means, or raise ``ValueError`` with the reasons."""
    failures: list[str] = []
    try:
        return LoadedDxf(doc=ezdxf.readfile(str(path)), method="strict")
    except Exception as exc:  # any ezdxf error family, plus decoding
        failures.append(f"estricto: {type(exc).__name__}: {str(exc)[:120]}")
    try:
        doc, auditor = ezdxf_recover.readfile(str(path))
        return LoadedDxf(
            doc=doc, method="recovery",
            audit_errors=len(auditor.errors), audit_fixes=len(auditor.fixes),
        )
    except Exception as exc:
        failures.append(f"recuperación: {type(exc).__name__}: {str(exc)[:120]}")
    try:
        text, rejoined, dropped = sanitize_dxf_text(_decode(path.read_bytes()))
        doc, auditor = ezdxf_recover.read(io.BytesIO(text.encode("utf-8")))
        return LoadedDxf(
            doc=doc, method="sanitized",
            audit_errors=len(auditor.errors), audit_fixes=len(auditor.fixes),
            dropped_objects=dropped, rejoined_lines=rejoined,
        )
    except Exception as exc:
        failures.append(f"saneado: {type(exc).__name__}: {str(exc)[:120]}")
    raise ValueError("; ".join(failures))
