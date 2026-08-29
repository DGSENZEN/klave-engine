"""Parser coverage: curve flattening, block explosion, and its budgets."""

import ezdxf
import pytest
from klave_engine.dxf import parser as parser_module
from klave_engine.dxf.parser import DxfParser


@pytest.fixture
def dxf_path(tmp_path):
    def _write(build):
        doc = ezdxf.new("R2010")
        build(doc)
        path = tmp_path / "test.dxf"
        doc.saveas(path)
        return path

    return _write


def test_curves_flatten_into_polylines(dxf_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_spline(fit_points=[(0, 0), (2, 3), (4, 1)])
        msp.add_ellipse((10, 10), major_axis=(3, 0), ratio=0.5)
        msp.add_solid([(20, 20), (21, 20), (20, 21), (21, 21)])

    drawing = DxfParser().parse_file(dxf_path(build))
    derived = {e.properties.get("derived_from") for e in drawing.entities}
    assert derived == {"SPLINE", "ELLIPSE", "SOLID"}
    assert all(e.entity_type.value == "polyline" for e in drawing.entities)
    solid = next(e for e in drawing.entities if e.properties["derived_from"] == "SOLID")
    assert solid.is_closed and len(solid.points) >= 3
    assert not drawing.warnings


def test_block_explosion_reaches_marks_and_adopts_layer(dxf_path):
    def build(doc):
        block = doc.blocks.new(name="CASTILLO")
        block.add_line((0, 0), (1, 1))       # layer "0" → adopts insert layer
        block.add_text("K-7", height=0.2)
        msp = doc.modelspace()
        insert = msp.add_blockref("CASTILLO", (5, 5))
        insert.dxf.layer = "S-COL"

    drawing = DxfParser().parse_file(dxf_path(build))
    exploded = [e for e in drawing.entities if e.properties.get("from_block")]
    assert {e.entity_type.value for e in exploded} == {"line", "text"}
    assert all(e.layer == "S-COL" for e in exploded)
    assert any(e.text == "K-7" for e in exploded)
    assert all(e.block_name == "CASTILLO" for e in exploded)


def test_block_explosion_is_budgeted(dxf_path, monkeypatch):
    monkeypatch.setattr(parser_module, "MAX_CHILDREN_PER_INSERT", 5)

    def build(doc):
        block = doc.blocks.new(name="DENSO")
        for i in range(20):
            block.add_line((i, 0), (i, 1))
        doc.modelspace().add_blockref("DENSO", (0, 0))

    drawing = DxfParser().parse_file(dxf_path(build))
    exploded = [e for e in drawing.entities if e.properties.get("from_block")]
    assert len(exploded) == 5
    assert any(w.warning_type == "block_explosion_capped" for w in drawing.warnings)


def test_unsupported_types_warn_never_silently_drop(dxf_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_point((0, 0))
        msp.add_line((0, 0), (1, 1))

    drawing = DxfParser().parse_file(dxf_path(build))
    assert len(drawing.entities) == 1
    dropped = [w for w in drawing.warnings if w.warning_type == "unsupported_dxf_entity"]
    assert len(dropped) == 1 and dropped[0].entity_type == "POINT"


def test_layouts_viewports_and_title_block_are_read(dxf_path):
    def build(doc):
        doc.header["$INSUNITS"] = 6  # metres
        doc.modelspace().add_line((0, 0), (1, 1))
        block = doc.blocks.new(name="CAJETIN")
        block.add_attdef("TITULO", (0, 0))
        layout = doc.layouts.new("Hoja 1")
        layout.add_viewport(
            center=(100, 100), size=(200, 150), view_center_point=(50, 25), view_height=30
        )
        layout.add_text("PLANTA DE CIMENTACIÓN  ESC 1:200")
        layout.add_blockref("CAJETIN", (0, 0)).add_auto_attribs({"TITULO": "S-101"})

    drawing = DxfParser().parse_file(dxf_path(build))
    assert [layout.name for layout in drawing.layouts] == ["Hoja 1"]
    hoja = drawing.layouts[0]
    assert len(hoja.viewports) == 1  # the paper itself is not a window
    viewport = hoja.viewports[0]
    assert viewport.scale_factor == 0.2
    assert viewport.scale_label == "≈ 1:200"
    assert viewport.model_bbox == (30.0, 10.0, 70.0, 40.0)
    assert hoja.texts == ["PLANTA DE CIMENTACIÓN ESC 1:200"]
    assert hoja.attributes == {"TITULO": "S-101"}
    assert drawing.xrefs == []


def test_xref_in_project_is_embedded_and_explodes(tmp_path):
    import ezdxf.xref

    base = ezdxf.new("R2010")
    base.modelspace().add_line((0, 0), (2, 0))
    base.modelspace().add_text("K-9", height=0.2)
    base.saveas(tmp_path / "arquitectura.dxf")

    main = ezdxf.new("R2010")
    ezdxf.xref.attach(main, block_name="ARQ", filename="arquitectura.dxf", insert=(10, 10))
    main.saveas(tmp_path / "estructural.dxf")

    drawing = DxfParser().parse_file(tmp_path / "estructural.dxf")
    assert [(x.name, x.status) for x in drawing.xrefs] == [("ARQ", "embedded")]
    borrowed = [e for e in drawing.entities if e.properties.get("from_block") == "ARQ"]
    assert any(e.text == "K-9" for e in borrowed)
    assert any(w.warning_type == "xref_embedded" for w in drawing.warnings)


def test_missing_xref_is_reported_not_hidden(tmp_path):
    import ezdxf.xref

    main = ezdxf.new("R2010")
    main.modelspace().add_line((0, 0), (1, 0))
    ezdxf.xref.attach(main, block_name="TOPO", filename="topografia.dxf")
    main.saveas(tmp_path / "estructural.dxf")

    drawing = DxfParser().parse_file(tmp_path / "estructural.dxf")
    assert [(x.name, x.status) for x in drawing.xrefs] == [("TOPO", "missing")]
    missing = [w for w in drawing.warnings if w.warning_type == "xref_missing"]
    assert len(missing) == 1 and "súbela como hoja" in missing[0].message
    assert len(drawing.entities) == 2  # the line and the unresolved insert


def test_insert_anidado_conserva_su_identidad(tmp_path):
    import ezdxf
    from klave_engine.dxf.parser import DxfParser

    doc = ezdxf.new("R2010")
    inner = doc.blocks.new(name="SIMBOLO-WC")
    inner.add_line((0, 0), (1, 0))
    outer = doc.blocks.new(name="BANO-TIPO")
    outer.add_blockref("SIMBOLO-WC", (2, 2))
    doc.modelspace().add_blockref("BANO-TIPO", (10, 10))
    path = tmp_path / "anidado.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    inserts = [e for e in drawing.entities if e.entity_type.value == "insert"]
    names = sorted(e.block_name for e in inserts if e.block_name)
    # El INSERT anidado existe como entidad con su nombre — antes se perdía.
    assert names == ["BANO-TIPO", "SIMBOLO-WC"]
    nested = next(e for e in inserts if e.block_name == "SIMBOLO-WC")
    assert (nested.properties or {}).get("parent_insert")


def test_corte_de_profundidad_avisa(tmp_path):
    import ezdxf
    from klave_engine.dxf.parser import DxfParser

    doc = ezdxf.new("R2010")
    n3 = doc.blocks.new(name="NIVEL3")
    n3.add_line((0, 0), (1, 0))
    n2 = doc.blocks.new(name="NIVEL2")
    n2.add_blockref("NIVEL3", (0, 0))
    n1 = doc.blocks.new(name="NIVEL1")
    n1.add_blockref("NIVEL2", (0, 0))
    doc.modelspace().add_blockref("NIVEL1", (0, 0))
    path = tmp_path / "profundo.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    assert any(w.warning_type == "block_nesting_truncated" for w in drawing.warnings)


def test_attdef_se_lee_del_bloque(tmp_path):
    import ezdxf
    from klave_engine.dxf.parser import DxfParser

    doc = ezdxf.new("R2010")
    block = doc.blocks.new(name="NOMENCLATURA-V")
    block.add_attdef("CLAVE", (0, 0), dxfattribs={"height": 0.2})
    doc.modelspace().add_blockref("NOMENCLATURA-V", (0, 0))
    path = tmp_path / "attdef.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    assert drawing.block_attdefs.get("NOMENCLATURA-V") == ["CLAVE"]
