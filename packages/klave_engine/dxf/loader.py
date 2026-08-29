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
    text, orphans = _close_open_sequences("\n".join(out) + "\n")
    text = _drop_truncated_polylines(text)
    if "\nEOF\n" not in text[-40:]:
        text = text.rstrip("\n") + "\n  0\nEOF\n"
    return text, rejoined, dropped + orphans


def _close_open_sequences(text: str) -> tuple[str, int]:
    """Cierra lo que el convertidor dejó abierto y tira lo imposible.

    LibreDWG a veces escribe BLOCK sin ENDBLK y POLYLINE sin SEQEND (la
    carpintería de Marina trae ambos): cerrar conserva la geometría, y el
    cierre se inserta donde el siguiente registro demuestra que la
    secuencia terminó. También deja entidades huérfanas DENTRO de BLOCKS,
    después de un ENDBLK prematuro: sin bloque al que pertenecer no se
    pueden colocar, así que se tiran contadas — una lectura parcial
    declarada, nunca un archivo entero ilegible. Regresa (texto, huérfanos).
    """
    lines = text.split("\n")
    out: list[str] = []
    open_block = False
    # Una cadena ligada abierta: POLYLINE→VERTEX…SEQEND, o INSERT con
    # atributos→ATTRIB…SEQEND. Ambas mueren igual cuando falta el SEQEND.
    open_chain = False
    section: str | None = None
    orphans = 0
    skipping_orphan = False
    last_kind: str | None = None
    # El INSERT solo espera ATTRIBs si lo declaró (código 66 = 1).
    insert_expects_attribs = False

    def close_polyline() -> None:
        nonlocal open_chain
        if open_chain:
            out.extend(["  0", "SEQEND"])
            open_chain = False

    def close_block() -> None:
        nonlocal open_block
        close_polyline()
        if open_block:
            out.extend(["  0", "ENDBLK"])
            open_block = False

    i = 0
    while i + 1 < len(lines):
        code, value = lines[i], lines[i + 1]
        stripped = code.strip()
        if stripped == "0":
            kind = value.strip()
            # Un registro nuevo termina cualquier corrida huérfana: lo que
            # se tira es exactamente el registro huérfano y sus pares.
            skipping_orphan = False
            if kind == "SECTION":
                close_block()
                section = (
                    lines[i + 3].strip() if i + 3 < len(lines) and
                    lines[i + 2].strip() == "2" else None
                )
            elif kind == "ENDSEC":
                close_block()
                section = None
            elif kind == "BLOCK":
                close_block()
                open_block = True
            elif kind == "ENDBLK":
                close_polyline()
                open_block = False
            elif kind == "POLYLINE":
                close_polyline()
                open_chain = True
            elif kind == "ATTRIB":
                if not open_chain:
                    # Un ATTRIB sin su INSERT (el convertidor metió otra
                    # entidad a media cadena): no se puede colocar; se tira
                    # contado en vez de matar el archivo entero.
                    orphans += 1
                    skipping_orphan = True
                    i += 2
                    continue
                open_chain = True
            elif kind == "SEQEND":
                open_chain = False
            elif kind != "VERTEX":
                close_polyline()
            if (
                section == "BLOCKS"
                and not open_block
                and kind not in ("BLOCK", "ENDBLK", "ENDSEC", "SECTION")
            ):
                # Huérfana entre bloques: nadie sabe de qué bloque era.
                skipping_orphan = True
                orphans += 1
                i += 2
                continue
            if kind == "INSERT":
                insert_expects_attribs = False
            last_kind = kind
        elif skipping_orphan:
            i += 2
            continue
        elif last_kind == "INSERT" and stripped == "66":
            # El 66=1 abre la cadena desde el INSERT mismo: aunque el
            # convertidor no haya escrito ni un ATTRIB, falta su SEQEND.
            insert_expects_attribs = value.strip() == "1"
            if insert_expects_attribs:
                open_chain = True
        out.append(code)
        out.append(value)
        i += 2
    if i < len(lines):
        out.append(lines[i])
    return "\n".join(out), orphans


def _drop_truncated_polylines(text: str) -> str:
    """A legacy POLYLINE must end with SEQEND; converters sometimes cut the
    chain. Such a run cannot be parsed, so it is removed whole."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i + 1 < len(lines):
        if lines[i].strip() == "0" and lines[i + 1].strip() == "POLYLINE":
            j = i + 2
            # advance through this record and its VERTEX records
            record_type = "POLYLINE"
            while j + 1 < len(lines):
                if lines[j].strip() == "0":
                    record_type = lines[j + 1].strip()
                    if record_type not in ("VERTEX",):
                        break
                j += 2
            if record_type == "SEQEND":
                out.extend(lines[i:j])
                i = j
                continue
            i = j  # drop POLYLINE + VERTEX run lacking SEQEND
            continue
        out.append(lines[i])
        out.append(lines[i + 1])
        i += 2
    if i < len(lines):
        out.append(lines[i])
    return "\n".join(out)


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
