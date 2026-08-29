"""The DXF loader: converter habits become warnings, never crashes."""

import ezdxf
import pytest
from klave_engine.conversion import libredwg
from klave_engine.dxf.loader import load_dxf, sanitize_dxf_text
from klave_engine.dxf.parser import DxfParser


def _write(tmp_path, name="t.dxf"):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (5, 0))
    doc.modelspace().add_text("K-1", height=0.2)
    path = tmp_path / name
    doc.saveas(path)
    return path, doc.modelspace().block_record.dxf.handle


def test_object_records_inside_entities_are_dropped(tmp_path):
    path, owner = _write(tmp_path)
    text = path.read_text(encoding="utf-8")
    # LibreDWG habit: an OBJECT dumped among the entities, owned by model space.
    record = f"  0\nSORTENTSTABLE\n  5\nF0B\n330\n{owner}\n100\nAcDbSortentsTable\n"
    injected = text.replace("  0\nLINE\n", record + "  0\nLINE\n", 1)
    path.write_text(injected, encoding="utf-8")
    cleaned, rejoined, dropped = sanitize_dxf_text(injected)
    assert dropped == 1 and rejoined == 0 and "SORTENTSTABLE" not in cleaned
    assert "AcDbSortentsTable" not in cleaned and cleaned.count("\nLINE\n") == 1
    # Whatever ezdxf makes of the stray object, the chain ends in a usable doc.
    loaded = load_dxf(path)
    assert loaded.doc is not None
    drawing = DxfParser().parse_file(path)
    assert any(e.text == "K-1" for e in drawing.entities)
    assert any(w.warning_type == "non_graphical_in_entities" for w in drawing.warnings)
    assert libredwg._output_is_readable(path) is True
    assert libredwg.completeness(path)["entities"] == 2


def test_embedded_newlines_are_rejoined():
    raw = "  0\nSECTION\n  2\nENTITIES\n  0\nMTEXT\n  1\nPLANTA\nBAJA\n  0\nENDSEC\n  0\nEOF\n"
    text, rejoined, dropped = sanitize_dxf_text(raw)
    assert rejoined == 1 and dropped == 0
    assert "PLANTA\\PBAJA" in text


def test_unreadable_file_raises_with_every_reason(tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_bytes(b"\x00\x01 not a dxf")
    with pytest.raises(ValueError) as info:
        load_dxf(bad)
    assert "estricto" in str(info.value) and "saneado" in str(info.value)


def test_truncated_polyline_runs_are_closed_not_dropped():
    # Antes se tiraba la corrida entera; cerrar con SEQEND conserva la
    # geometría — tirarla era perder metros reales del levantamiento.
    raw = (
        "  0\nSECTION\n  2\nENTITIES\n"
        "  0\nPOLYLINE\n  8\n0\n  0\nVERTEX\n 10\n0\n 20\n0\n  0\nVERTEX\n 10\n1\n 20\n0\n"
        "  0\nLINE\n  8\n0\n 10\n0\n 20\n0\n 11\n1\n 21\n1\n"
        "  0\nENDSEC\n"
    )
    text, _rejoined, _dropped = sanitize_dxf_text(raw)
    assert "POLYLINE" in text and "SEQEND" in text
    assert text.index("SEQEND") < text.index("\nLINE\n")
    assert "\nLINE\n" in text and text.rstrip().endswith("EOF")


def test_el_saneador_cierra_bloques_y_polilineas_sin_terminar(tmp_path):
    """LibreDWG a veces escribe BLOCK sin ENDBLK y POLYLINE sin SEQEND
    (carpintería de Marina): el saneador los cierra donde el siguiente
    registro demuestra que la secuencia terminó."""
    from io import BytesIO

    import ezdxf
    from ezdxf import recover as ezdxf_recover
    from klave_engine.dxf.loader import sanitize_dxf_text

    # Un DXF válido, roto a propósito: se le quitan ENDBLK y SEQEND.
    doc = ezdxf.new("R2010")
    block = doc.blocks.new(name="ROTO")
    block.add_line((0, 0), (1, 0))
    msp = doc.modelspace()
    msp.add_blockref("ROTO", (5, 5))
    msp.add_polyline2d([(0, 0), (3, 0), (3, 3)])  # POLYLINE + VERTEX + SEQEND
    path = tmp_path / "ok.dxf"
    doc.saveas(path)
    text = path.read_text()
    roto = "\n".join(
        line for i, line in enumerate(text.splitlines())
        if not (line.strip() in ("ENDBLK", "SEQEND")
                and text.splitlines()[i - 1].strip() == "0")
    )
    # Y sin los códigos 0 huérfanos que quedaron apuntando a nada.
    lineas = roto.splitlines()
    limpio: list[str] = []
    skip = False
    for i, line in enumerate(lineas):
        if skip:
            skip = False
            continue
        if line.strip() == "0" and i + 1 < len(lineas) and lineas[i + 1].strip() in ("", ):
            skip = True
            continue
        limpio.append(line)
    roto = "\n".join(limpio) + "\n"

    saneado, _rejoined, _dropped = sanitize_dxf_text(roto)
    doc2, _auditor = ezdxf_recover.read(BytesIO(saneado.encode("utf-8")))
    assert len(list(doc2.modelspace())) >= 2  # el insert y la polilínea siguen
    assert "ROTO" in [b.name for b in doc2.blocks if not b.name.startswith("*")]


def test_el_xref_se_encuentra_aunque_la_subida_lo_haya_slugificado(tmp_path):
    """El plano declara «00 XREF L.04 - 26.01.15»; la subida lo guardó como
    00_xref_l_04_-_26_01_15.dxf. Son el mismo archivo y deben casar."""
    from klave_engine.dxf.layouts import _find_sibling

    d = tmp_path / "converted" / "algo"
    d.mkdir(parents=True)
    (d / "00_xref_l_04_-_26_01_15.dxf").write_text("stub")
    found = _find_sibling("00 XREF L.04 - 26.01.15", [tmp_path / "converted"])
    assert found is not None and found.name == "00_xref_l_04_-_26_01_15.dxf"
    # Y lo que no es el mismo archivo, no casa.
    assert _find_sibling("01 ARQ L.04", [tmp_path / "converted"]) is None
