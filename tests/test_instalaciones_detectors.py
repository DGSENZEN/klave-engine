"""Los dos detectores de instalaciones: cada símbolo un elemento, cada sistema
sus metros. Lo que la tabla no reconoce no se pierde, y nada se cuenta dos veces.
"""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.detection.fixture_detector import detect_fixtures
from klave_engine.detection.results import DetectionType
from klave_engine.detection.run_detector import RunDetectorConfig, detect_runs
from klave_engine.detection.taxonomy import Family, classify_family, enrich_detections
from klave_engine.dxf.parser import DxfParser


def _entities(tmp_path, name, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # metros
    build(doc)
    path = tmp_path / name
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _familias(output) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for d in output.detections:
        key = d.properties["fixture_family"]
        conteo[key] = conteo.get(key, 0) + 1
    return conteo


# ----------------------------------------------------------- muebles ------


def test_cada_simbolo_reconocido_es_un_elemento(tmp_path):
    def build(doc):
        for name in ("W.C.", "LAVABO", "CONTACTO-DOBLE", "DIFUSOR-12"):
            doc.blocks.new(name=name).add_circle((0, 0), 0.15)
        msp = doc.modelspace()
        msp.add_blockref("W.C.", (1, 1), dxfattribs={"layer": "IH-MUEBLES"})
        msp.add_blockref("LAVABO", (2, 1), dxfattribs={"layer": "IH-MUEBLES"})
        msp.add_blockref("LAVABO", (3, 1), dxfattribs={"layer": "IH-MUEBLES"})
        msp.add_blockref("CONTACTO-DOBLE", (5, 1), dxfattribs={"layer": "IE-FUERZA"})
        msp.add_blockref("DIFUSOR-12", (8, 1), dxfattribs={"layer": "AA-DIFUSORES"})

    salida = detect_fixtures(_entities(tmp_path, "m.dxf", build), None, IdGenerator("d"), 1.0)
    assert _familias(salida) == {"wc": 1, "lavabo": 2, "contacto": 1, "difusor": 1}
    assert all(d.detection_type == DetectionType.fixture for d in salida.detections)
    wc = next(d for d in salida.detections if d.properties["fixture_family"] == "wc")
    assert wc.properties["discipline"] == "hidrosanitaria"
    assert "W.C." in wc.evidence.notes[0]
    assert wc.confidence > 0.5


def test_el_aparato_de_la_hoja_no_es_obra(tmp_path):
    """Cajetín, norte y simbología son el papel, no lo que se construye."""
    def build(doc):
        for name in ("PIE DE PLANO 1 125", "N", "SIMBOLOGIA", "W.C."):
            doc.blocks.new(name=name).add_circle((0, 0), 0.1)
        msp = doc.modelspace()
        msp.add_blockref("PIE DE PLANO 1 125", (40, 0), dxfattribs={"layer": "PIE DE PLANO"})
        msp.add_blockref("N", (0, 20), dxfattribs={"layer": "UBICA"})
        msp.add_blockref("SIMBOLOGIA", (5, 5), dxfattribs={"layer": "SIMBOLOG"})
        msp.add_blockref("W.C.", (1, 1), dxfattribs={"layer": "IH"})

    salida = detect_fixtures(_entities(tmp_path, "a.dxf", build), None, IdGenerator("d"), 1.0)
    assert _familias(salida) == {"wc": 1}


def test_lo_que_la_tabla_no_reconoce_se_dice_y_no_se_inventa(tmp_path):
    def build(doc):
        doc.blocks.new(name="FT4YNF060").add_circle((0, 0), 0.2)
        doc.modelspace().add_blockref("FT4YNF060", (1, 1), dxfattribs={"layer": "AA-EQUIPOS"})

    salida = detect_fixtures(_entities(tmp_path, "x.dxf", build), None, IdGenerator("d"), 1.0)
    assert salida.detections == []
    assert any("FT4YNF060" in w for w in salida.warnings)
    assert any("levantamiento" in w for w in salida.warnings)


def test_un_bloque_que_ya_se_llevo_otro_detector_no_se_cuenta_de_nuevo(tmp_path):
    """Un mismo bloque no puede ser un castillo y un contacto."""
    def build(doc):
        doc.blocks.new(name="CONTACTO").add_circle((0, 0), 0.1)
        doc.modelspace().add_blockref("CONTACTO", (1, 1), dxfattribs={"layer": "IE"})

    entities = _entities(tmp_path, "c.dxf", build)
    inserts = [e.entity_id for e in entities if e.block_name]
    sin_reclamar = detect_fixtures(entities, None, IdGenerator("d"), 1.0)
    assert len(sin_reclamar.detections) == 1
    reclamado = detect_fixtures(entities, None, IdGenerator("d"), 1.0, set(inserts))
    assert reclamado.detections == []


def test_un_simbolo_del_tamano_de_un_detalle_no_es_una_pieza_en_planta(tmp_path):
    def build(doc):
        doc.blocks.new(name="W.C.").add_line((0, 0), (9, 9))  # 9 m: es un despiece
        doc.modelspace().add_blockref("W.C.", (0, 0), dxfattribs={"layer": "IH"})

    salida = detect_fixtures(_entities(tmp_path, "g.dxf", build), None, IdGenerator("d"), 1.0)
    assert salida.detections == []


# ---------------------------------------------------------- corridas ------


def test_un_sistema_es_una_corrida_con_sus_metros(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_line((10, 0), (10, 6), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_line((0, 2), (8, 2), dxfattribs={"layer": "00-SANITARIA"})

    salida = detect_runs(_entities(tmp_path, "r.dxf", build), None, IdGenerator("d"), 1.0, [])
    por_capa = {d.label: d for d in salida.detections}
    assert set(por_capa) == {"P-04IH-CPIP", "00-SANITARIA"}
    fria = por_capa["P-04IH-CPIP"]
    assert fria.properties["length_m"] == 16.0
    assert fria.properties["run_family"] == "agua_fria"
    assert fria.properties["discipline"] == "hidraulica"
    assert fria.properties["segments"] == 2
    # La regla de cantidad lee unidades de dibujo, no metros ya convertidos.
    assert fria.properties["estimated_length"] == 16.0
    assert fria.detection_type == DetectionType.pipe_run


def test_el_fondo_arquitectonico_no_es_tuberia(tmp_path):
    """En la hoja de aire conviven el ducto y los muros del dibujo de fondo."""
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (20, 0), dxfattribs={"layer": "AireDucto"})
        msp.add_line((0, 5), (40, 5), dxfattribs={"layer": "MUROS2"})
        msp.add_line((0, 7), (40, 7), dxfattribs={"layer": "PLAFONES"})
        msp.add_line((0, 9), (40, 9), dxfattribs={"layer": "COLUMNA"})

    salida = detect_runs(_entities(tmp_path, "f.dxf", build), None, IdGenerator("d"), 1.0, [])
    assert [d.label for d in salida.detections] == ["AireDucto"]


def test_sin_unidades_confiables_no_se_emite_ninguna_corrida(tmp_path):
    """Unos metros que en realidad son milímetros costarían mil veces de más,
    y ese error no se nota."""
    def build(doc):
        doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "GAS"})

    entities = _entities(tmp_path, "u.dxf", build)
    assert detect_runs(entities, None, IdGenerator("d"), None, []).detections == []
    assert detect_runs(entities, None, IdGenerator("d"), 1.0, []).detections


def test_un_resto_de_dibujo_no_es_una_red(tmp_path):
    def build(doc):
        doc.modelspace().add_line((0, 0), (0.5, 0), dxfattribs={"layer": "GAS"})

    salida = detect_runs(_entities(tmp_path, "n.dxf", build), None, IdGenerator("d"), 1.0, [])
    assert salida.detections == []
    assert any("simbología" in w for w in salida.warnings)


def test_cada_marco_de_hoja_tiene_su_propia_corrida(tmp_path):
    """Los metros de agua fría de la planta baja y los de la azotea son dos
    partidas de trabajo, no una."""
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((1, 1), (11, 1), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_line((101, 1), (121, 1), dxfattribs={"layer": "P-04IH-CPIP"})

    marcos = [(0.0, 0.0, 50.0, 50.0), (100.0, 0.0, 150.0, 50.0)]
    salida = detect_runs(
        _entities(tmp_path, "v.dxf", build), None, IdGenerator("d"), 1.0, marcos
    )
    assert sorted(d.properties["length_m"] for d in salida.detections) == [10.0, 20.0]


def test_el_retorno_de_una_alberca_no_es_retorno_de_agua_caliente(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "SEB - Retorno Filtrado"})
        msp.add_line((0, 2), (10, 2), dxfattribs={"layer": "P-04IH-RPIP"})

    salida = detect_runs(_entities(tmp_path, "s.dxf", build), None, IdGenerator("d"), 1.0, [])
    assert [d.label for d in salida.detections] == ["P-04IH-RPIP"]


# --------------------------------------------------------- taxonomía ------


def test_un_mueble_y_una_salida_no_son_lo_mismo(tmp_path):
    """Un W.C. se instala; un contacto se prepara. Se presupuestan distinto."""
    def build(doc):
        for name in ("W.C.", "CONTACTO"):
            doc.blocks.new(name=name).add_circle((0, 0), 0.1)
        msp = doc.modelspace()
        msp.add_blockref("W.C.", (1, 1), dxfattribs={"layer": "IH"})
        msp.add_blockref("CONTACTO", (3, 1), dxfattribs={"layer": "IE"})

    salida = detect_fixtures(_entities(tmp_path, "t.dxf", build), None, IdGenerator("d"), 1.0)
    por_familia = {d.properties["fixture_family"]: classify_family(d) for d in salida.detections}
    assert por_familia == {"wc": Family.mueble, "contacto": Family.salida}


def test_las_corridas_reciben_nombre_estable_y_descripcion(tmp_path):
    def build(doc):
        doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "00-SANITARIA"})

    salida = detect_runs(_entities(tmp_path, "d.dxf", build), None, IdGenerator("d"), 1.0, [])
    enrich_detections(salida.detections, 1.0)
    d = salida.detections[0]
    assert d.family == Family.corrida.value
    assert d.display_label.startswith("COR-")
    assert d.description


def test_la_longitud_minima_es_configurable(tmp_path):
    def build(doc):
        doc.modelspace().add_line((0, 0), (2, 0), dxfattribs={"layer": "GAS"})

    entities = _entities(tmp_path, "cfg.dxf", build)
    assert detect_runs(entities, None, IdGenerator("d"), 1.0, []).detections == []
    laxo = RunDetectorConfig(min_length_m=1.0)
    assert detect_runs(entities, laxo, IdGenerator("d"), 1.0, []).detections


# ------------------------------------------- el marco de una hoja MEP ------


def test_un_marco_sin_titulo_en_hoja_de_instalaciones_es_planta():
    """En los planos de instalaciones el cajetín rara vez repite «PLANTA»: la
    clave de la hoja ya dice de qué es. Tratarlo como excluido afirma que es un
    detalle, y entonces sus salidas desaparecen del presupuesto sin ruido."""
    from klave_engine.detection.frames import SheetFrame
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.detection.views import ViewKind, segment_views

    frames = [
        SheetFrame(
            frame_id="f0", bbox=(0, 0, 100, 70), source_file="02-05_sanitario_l_04.dxf",
            code="SAN-01", title="", kind="unknown", level_key=None, text_count=10,
        ),
        SheetFrame(
            frame_id="f1", bbox=(200, 0, 300, 70), source_file="02-05_sanitario_l_04.dxf",
            code="SAN-02", title="", kind="unknown", level_key=None, text_count=10,
        ),
    ]
    salida = make_detection(
        "d1", DetectionType.fixture, "DESCSAN1", (10, 10, 10.4, 10.4), 0.8, ["e1"],
        "block_symbol", [], {"fixture_family": "salida_sanitaria"},
        "02-05_sanitario_l_04.dxf",
    )
    seg = segment_views([], [salida], frames)
    vistas = {v.view_id: v for v in seg.views}
    assert seg.is_segmented
    assert vistas["f0"].kind == ViewKind.plan
    # No es planta de estructura: no entra a alturas de entrepiso ni a los
    # alcances de columnas y muros.
    assert vistas["f0"].structural is False
    assert seg.assignment["d1"] == "f0"


def test_un_marco_que_dice_detalle_sigue_excluido_en_cualquier_hoja():
    from klave_engine.detection.frames import SheetFrame
    from klave_engine.detection.views import ViewKind, segment_views

    frames = [
        SheetFrame(
            frame_id="f0", bbox=(0, 0, 100, 70), source_file="02-05_sanitario_l_04.dxf",
            code="SAN-01", title="", kind="unknown", level_key=None, text_count=10,
        ),
        SheetFrame(
            frame_id="f1", bbox=(200, 0, 300, 70), source_file="02-05_sanitario_l_04.dxf",
            code="SAN-09", title="DETALLE DE REGISTRO", kind="excluded", level_key=None,
            text_count=10,
        ),
    ]
    vistas = {v.view_id: v for v in segment_views([], [], frames).views}
    assert vistas["f0"].kind == ViewKind.plan
    assert vistas["f1"].kind == ViewKind.excluded


def test_en_hoja_estructural_un_marco_sin_titulo_no_se_asume_planta():
    """La prudencia de siempre: en estructura, un marco cuyo cajetín no se pudo
    leer no empieza a alimentar cantidades por su cuenta."""
    from klave_engine.detection.frames import SheetFrame
    from klave_engine.detection.views import ViewKind, segment_views

    frames = [
        SheetFrame(
            frame_id="f0", bbox=(0, 0, 100, 70), source_file="S-01_estructural.dxf",
            code="S-01", title="PLANTA DE CIMENTACIÓN", kind="plan",
            level_key="cimentacion", text_count=10,
        ),
        SheetFrame(
            frame_id="f1", bbox=(200, 0, 300, 70), source_file="S-01_estructural.dxf",
            code="S-02", title="PLANTA DE AZOTEA", kind="plan", level_key="azotea",
            text_count=10,
        ),
        SheetFrame(
            frame_id="f2", bbox=(400, 0, 500, 70), source_file="S-01_estructural.dxf",
            code="S-03", title="", kind="unknown", level_key=None, text_count=10,
        ),
    ]
    vistas = {v.view_id: v for v in segment_views([], [], frames).views}
    assert vistas["f0"].kind == ViewKind.plan
    assert vistas["f2"].kind == ViewKind.excluded


# ------------------------------------------ diámetro leído del plano -------


def _spec(tmp_path, name, build):
    salida = detect_runs(_entities(tmp_path, name, build), None, IdGenerator("d"), 1.0, [])
    return {d.properties["run_family"]: d.properties["spec"] for d in salida.detections}


def test_el_diametro_se_lee_del_rotulo_pegado_al_trazo(tmp_path):
    """«Tubería de agua fría» no se puede cotizar contra ninguna publicación:
    nadie publica precio de una tubería sin diámetro."""
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_text('AF-1/2"%%C', dxfattribs={"layer": "TEXTOS", "height": 0.2}).set_placement(
            (6, 0.5)
        )
    assert _spec(tmp_path, "d.dxf", build)["agua_fria"] == 'AF-1/2"Ø'


def test_un_rotulo_lejos_del_trazo_no_es_de_esta_corrida(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "GAS"})
        msp.add_text('19 MM', dxfattribs={"layer": "TEXTOS", "height": 0.2}).set_placement(
            (6, 40)
        )
    assert _spec(tmp_path, "l.dxf", build)["gas"] == ""


def test_el_rotulo_que_nombra_otro_sistema_no_es_de_esta_corrida(tmp_path):
    """Agua fría, caliente y retorno corren paralelas dentro del mismo muro,
    así que un rótulo cae a un metro de las tres. Lo que las distingue es lo
    que el rótulo dice, no dónde está."""
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "P-04IH-CPIP"})
        msp.add_line((0, 0.1), (12, 0.1), dxfattribs={"layer": "P-04IH-HPIP"})
        msp.add_text('AF-1/2"%%C', dxfattribs={"layer": "T", "height": 0.2}).set_placement(
            (6, 0.4)
        )
    specs = _spec(tmp_path, "s.dxf", build)
    assert specs["agua_fria"] == 'AF-1/2"Ø'
    assert specs["agua_caliente"] == ""


def test_un_rotulo_de_varias_tuberias_se_reparte(tmp_path):
    """«AF-1/2"Ø AC-1/2"Ø RAC-1/2"Ø» es un rótulo para tres tuberías que van
    juntas por el muro: cada corrida se lleva su pedazo."""
    def build(doc):
        msp = doc.modelspace()
        for layer, y in (("P-04IH-CPIP", 0.0), ("P-04IH-HPIP", 0.1), ("P-04IH-RPIP", 0.2)):
            msp.add_line((0, y), (12, y), dxfattribs={"layer": layer})
        msp.add_text('AF-1/2"%%C AC-3/4"%%C RAC-1/2"%%C',
                     dxfattribs={"layer": "T", "height": 0.2}).set_placement((6, 0.5))
    specs = _spec(tmp_path, "m.dxf", build)
    assert specs["agua_fria"] == 'AF-1/2"Ø'
    assert specs["agua_caliente"] == 'AC-3/4"Ø'
    assert specs["retorno"] == 'RAC-1/2"Ø'


def test_un_diametro_imposible_para_ese_sistema_no_es_su_rotulo(tmp_path):
    """Una línea de refrigerante de 12 pulgadas no existe: ese rótulo es del
    ducto que corre al lado."""
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "AireDucto"})
        msp.add_line((0, 0.1), (12, 0.1), dxfattribs={"layer": "AireTuboCu"})
        msp.add_text('12"', dxfattribs={"layer": "T", "height": 0.2}).set_placement((6, 0.4))
    specs = _spec(tmp_path, "a.dxf", build)
    assert specs["ducto"] == '12"'
    assert specs["refrigerante"] == ""


def test_sin_rotulo_la_corrida_dice_que_le_falta_el_diametro(tmp_path):
    def build(doc):
        doc.modelspace().add_line((0, 0), (12, 0), dxfattribs={"layer": "00-SANITARIA"})
    salida = detect_runs(_entities(tmp_path, "n.dxf", build), None, IdGenerator("d"), 1.0, [])
    notas = " ".join(salida.detections[0].evidence.notes)
    assert "sin rótulo de diámetro" in notas
    assert "el precio no se puede fijar solo" in notas


def test_la_corrida_se_parte_donde_cambia_el_diametro(tmp_path):
    """Un albañal va de 2" a 4" a lo largo: son dos conceptos distintos, no
    una tubería con el diámetro del rótulo más repetido."""
    def build(doc):
        msp = doc.modelspace()
        # 10 m con rótulo de 2" y 20 m con rótulo de 4", en la misma capa.
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "00-SANITARIA"})
        msp.add_line((10, 0), (30, 0), dxfattribs={"layer": "00-SANITARIA"})
        msp.add_text('2"', height=0.3).set_placement((5, 0.5))
        msp.add_text('4"', height=0.3).set_placement((20, 0.5))

    salida = detect_runs(_entities(tmp_path, "d.dxf", build), None, IdGenerator("d"), 1.0, [])
    tramos = sorted(
        (d for d in salida.detections),
        key=lambda d: d.properties.get("length_m", 0.0),
    )
    assert len(tramos) == 2
    corto, largo = tramos
    assert corto.properties["length_m"] == 10.0 and corto.properties["diametro_mm"] == 51
    assert largo.properties["length_m"] == 20.0 and largo.properties["diametro_mm"] == 102
    assert all(t.properties["run_family"] == "sanitaria" for t in tramos)
    assert any("dos diámetros" in n or "2 diámetros" in n for t in tramos for n in t.evidence.notes)


def test_un_solo_diametro_no_parte_nada(tmp_path):
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0), (30, 0), dxfattribs={"layer": "00-SANITARIA"})
        msp.add_text('4"', height=0.3).set_placement((15, 0.5))

    salida = detect_runs(_entities(tmp_path, "u1.dxf", build), None, IdGenerator("d"), 1.0, [])
    assert len(salida.detections) == 1
    assert salida.detections[0].properties["length_m"] == 30.0
