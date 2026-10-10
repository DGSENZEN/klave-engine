"""R104: la lectura no pierde nada. Cada texto del plano con un tramo de armado
(``tramos_de_armado``: varillas, estribos, una malla, una sección, una longitud) lo toma una
lectura —que lee o cita cada tramo— o está en los rechazos. Se mira en Marina, en PRUEBA-1 (si
están los dibujos) y en cada sonda de las rondas de las tareas 7 y 8, como nota suelta, como nota
numerada y como renglón de la pila de una etiqueta."""

import re
from collections import defaultdict
from pathlib import Path

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.schedules import (
    ElementSpec,
    ScheduleInventory,
    build_schedule_inventory,
)
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.harmonize import harmonize_units
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.armado import parsear_armado, tramos_de_armado

C = TextPatternConfig()
_DATOS = Path(__file__).resolve().parents[1] / "data" / "raw"
_MARINA = _DATOS / "marina-4" / "converted" / "02 ESTRUCTURAL L.04 - 26.01.15.dxf"
_PRUEBA_1 = _DATOS / "estructural_l04" / "drawings" / "PRUEBA-1.dxf"


_LADO = r"\d+(?:\.\d+)?"
_SECCION = re.compile(rf"{_LADO}\s*[X×]\s*{_LADO}(?:\s*[X×]\s*{_LADO})?(?:\s*CMS?\.?)?")
_LONGITUD = re.compile(r"(?:L\s*=|LONG\.?|LONGITUD\b).*")


def _plano(texto: str) -> str:
    return " ".join(texto.upper().split())


def _claves(armado) -> set[tuple]:
    if armado is None:
        return set()
    return (
        {("v", g.cantidad, g.numero) for g in armado.longitudinales}
        | {("e", j.tipo, j.cantidad, j.numero) for j in armado.estribos}
        | {("p", p.numero, p.separacion_m) for p in armado.parrillas}
    )


def _leido_o_citado(tramo: str, s: ElementSpec) -> bool:
    """Si la lectura ``s`` lee el tramo o lo dice en un aviso. Independiente del lector: una
    sección se compara por sus lados; una pieza, leída sola, con lo que la lectura tiene."""
    t = _plano(tramo)
    avisos = [_plano(a) for a in s.avisos]
    citas = [_plano(c) for a in s.avisos for c in re.findall(r"«([^»]*)»", a)]
    if any(t in a for a in avisos) or any(c and c in t for c in citas):
        return True
    if _SECCION.fullmatch(t):
        lados = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", t)[:2]]
        return s.section_cm is not None and sorted(s.section_cm) == sorted(lados)
    if _LONGITUD.fullmatch(t):
        return s.length_m is not None
    solo = _claves(parsear_armado([tramo], s.family))
    return bool(solo) and solo <= _claves(s.armado)


def _perdidos(inv: ScheduleInventory, entidades: list[NormalizedEntity]) -> list[str]:
    """Cada renglón con armado que ni lee (o cita) una lectura ni está en los rechazos."""
    lecturas: dict[str, list[ElementSpec]] = defaultdict(list)
    for s in inv.specs:
        if s.source != "ia":
            for e in s.entidades:
                lecturas[e].append(s)
    rechazados: dict[str, list[str]] = defaultdict(list)
    for r in inv.rechazos:
        rechazados[r.entidad_id].append(_plano(r.texto))
    perdidos: list[str] = []
    for e in entidades:
        if not (e.is_textual and e.text):
            continue
        for linea in e.text.split("\n"):
            citar, tramos = tramos_de_armado(linea.strip())
            if not tramos or any(_plano(linea) in r for r in rechazados[e.entity_id]):
                continue
            if not lecturas[e.entity_id]:
                perdidos.append(f"{e.entity_id} «{linea.strip()}»: ni se lee ni se rechaza")
                continue
            for a, b in tramos:
                if not any(_leido_o_citado(citar[a:b], s) for s in lecturas[e.entity_id]):
                    perdidos.append(f"{e.entity_id} «{linea.strip()}»: «{citar[a:b]}» se pierde")
    return perdidos


def _dibujo(tmp_path, poner) -> list[NormalizedEntity]:
    doc = ezdxf.new("R2010")
    poner(doc.modelspace())
    doc.saveas(tmp_path / "sondas.dxf")
    return DxfParser().parse_file(tmp_path / "sondas.dxf").entities


def _texto(msp, texto: str, x: float, y: float, alto: float) -> None:
    if "\n" in texto:
        msp.add_mtext(texto.replace("\n", "\\P"), dxfattribs={"char_height": alto}).set_location(
            (x, y)
        )
    else:
        msp.add_text(texto, height=alto).set_placement((x, y))


def test_every_probe_as_a_note_is_read_or_reported(tmp_path):
    def poner(msp):
        for i, sonda in enumerate(_SONDAS):
            _texto(msp, sonda, 0.0, i * 5.0, 0.2)
            if "\n" not in sonda:
                _texto(msp, f"1.- {sonda}", 50.0, i * 5.0, 0.2)

    entidades = _dibujo(tmp_path, poner)
    assert _perdidos(build_schedule_inventory(entidades), entidades) == []


def test_every_probe_as_a_stack_line_is_read_or_reported(tmp_path):
    def poner(msp):
        for i, sonda in enumerate(s for s in _SONDAS if "\n" not in s):
            x = i * 5.0
            msp.add_text("K-1", height=0.13).set_placement(
                (x, 0.0), align=TextEntityAlignment.BOTTOM_CENTER
            )
            msp.add_text("4#3", height=0.10).set_placement((x - 0.2, 0.36))
            msp.add_text(sonda, height=0.10).set_placement((x - 0.2, 0.18))

    entidades = _dibujo(tmp_path, poner)
    assert _perdidos(build_schedule_inventory(entidades), entidades) == []


@pytest.mark.parametrize("ruta", [_MARINA, _PRUEBA_1], ids=["marina", "prueba-1"])
def test_the_reference_drawings_lose_nothing(ruta):
    if not ruta.exists():
        pytest.skip(f"sin el dibujo {ruta.name}")
    dibujo = DxfParser().parse_file(ruta)
    unidades, _ = harmonize_units([(dibujo.source_file, dibujo.insunits, dibujo.entities)])
    inv = build_schedule_inventory(
        dibujo.entities, C, unit_to_m=unidades.to_meters(), frames=detect_frames(dibujo.entities)
    )
    assert _perdidos(inv, dibujo.entities) == []


_SONDAS = [
    '"K 7" 15X20',
    '"K 7" E#3@1S',
    "(K-7) 4#3",
    "(V-4) 4#5",
    "1. 30X30 8#6",
    "1. 8#6 VER CORTE C-2",
    "1.- CASTILLOS 15X15 4#3 E#2@20",
    "1.-K 7 15X20",
    "1.-K 7 E#3@1S",
    "10#8",
    "12#6",
    "15X15",
    "15X15 NO",
    "15x15",
    "15x20",
    "15x30",
    "15x900",
    "15x900 8#5",
    "2 E#2@20",
    "2 VARILLAS #5 ANCLADA AL MURO O CADENA",
    "2 VARILLAS #5 ANCLADA AL MURO O CADENA CON ANCHORFIX 3001 DE SIKA",
    "20 x 30",
    "20x30",
    "20x30 4#5+2#4",
    "2E#3 EXT@10 CENTRO@20",
    "2E#3 VER CORTE",
    "2E#3 VER CORTE C-2",
    "2E#3@15",
    "2E#3@15 VER P-1",
    "2E#3EXT@10",
    "2E#3EXT@10 CENTRO@20",
    "2E+1G#3EXT@10 CENTRO@15",
    "2G#3@15",
    "3.- 4#3 E#2@20 VER CORTE C-2",
    "3.- CORTE K-1 Y K-2 E#3@20",
    "3.- K 7 E#3@1S",
    "3.- K-7 E#3@1S",
    "3.-K 7 15X20 4#3",
    "304 X 203 MM",
    "30X100",
    "30X40",
    "30X80",
    "30x20",
    "30x40  8#5  E#3@15",
    "30x40 8#5",
    "31x30",
    "3E#2@15",
    "3E#3EXT@10 CENTRO@20",
    "4 VAR. No. 3",
    "4 VAR. No. 3 E#2@15",
    "4 VARILLAS DEL No. 3",
    '4 VARS 3/8"',
    "4#3",
    "4#3 CORTE K-1",
    "4#3 E #2@20",
    "4#3 E#2@15",
    "4#3 E#2@15 CORTE K-1",
    "4#3 E#2@20 HASTA PLACA",
    "4#3 VER DET. K-2",
    "4#3 Y E #2@20",
    "4#3-K-7",
    "4#4",
    "4#5+2#4",
    "4#5+2#4 / 2E#3@15",
    "4#6",
    "4) #3",
    "4-#3",
    "4E#3EXT@10 CENTRO@20",
    "4V#4 E#3@20CMS CADENA DE DESPLANTE",
    "5E#3@15",
    "6 VAR #4",
    "6#4",
    "6#6",
    "6#8+6#6",
    "6#8+6#6 / 4E#3EXT@10 / CENTRO@20",
    "60×40",
    "6x6-8/8",
    "7 #3",
    "8 PZAS #6",
    "8#5",
    "8#6",
    "8#6 (o 10#6)",
    "8#6 E#3@20 VER DETALLE DE ANCLAJE",
    "8#6 | 2E#3EXT@10 | CENTRO@20",
    "8#8",
    "8#8+4#6",
    "8#8+4#6 / 2E#3EXT@10 / CENTRO@20",
    "ANCLAJE 4#4",
    "ANCLAR A LA TRABE CON 2#4",
    "ANCLAS 4 PZAS #6",
    "ANCLAS 4 VARS #6",
    'ANCLAS 4 VARS 3/4"',
    "ARMEX 15X30",
    "B-1 20X40 4#3",
    "BARRENOS PARA 4#4",
    "C-1 30X30 4#6",
    "C-1 30X30 8#6 E#3@20 PLACA BASE 35X35",
    "C-1 30X30 8#6 E#3@20 PLACA BASE 35X35 CON 4 ANCLAS #6",
    "C-1 30X30 8#6 E#3@20 PLACA BASE 35X35 CON ANCLAS 4 PZAS #6",
    "C-1 4#3 E#2@20 HASTA PLACA",
    "C-1 40X40 8#6 E#3@10 ANCLAJE 60 CM",
    "C-1 A 20 CM E#3@1S",
    "C-1 A 20X20",
    "C-1 A 20X20 8#5",
    "C-1 ANCLAS 4 VARS #6",
    "C-1 PLACA BASE 35X35 CON ANCLAS 4 PZAS #6",
    "C-1, 8 PZAS #6",
    "C-1, 8 PZAS #6 E#3@20",
    "C-1-P 4#3",
    "C-2 30X30",
    "C-2 30X30 8#6 E#3@20",
    "CADENA DE ENRASE 15x25 4#3 E#2@15",
    "CADENAS DE CERRAMIENTO 15X25 4#3 E#2@15",
    "CASTILLO E#2@20",
    "CASTILLOS 15X15 4#3",
    "CASTILLOS E#2@20",
    "CASTILLOS E#2@20 EN TODOS",
    "CASTILLOS K-1 A 3.00 M MAX 15X15 4#3 E#2@20",
    "COLUMNAS PLACA BASE 35X35 E#3@20",
    "CONTRATRABES 4#4 E#3@20 HUECOS DE HASTA 15X20",
    "CORTE A-A 4#3",
    "CORTE A-A ESC 1:20 K-1 15X20 4#3",
    "CORTE A-A K-1 15X20 4#3",
    "CORTE K-1 15X20 4#3",
    "CORTE K-1 4#3 VER DET. K-2",
    "CORTE K-1 CASTILLOS 15X20 4#3",
    "CORTE K-1 Y K-2 E#3@1S",
    "CORTE K-1 Y K-2 E#3@20",
    "CORTE No. 2 E#3@20",
    "CORTE T1-1 E#3@1S",
    "CR-1 V4 #4 E#3 @20CMS",
    "DALA 15X20 V4 #4 E#2@20",
    "DALA 15x30 4#3,E#2@20",
    "DALA: 15X20 4#3 E#2@20",
    "DE K-1 A K-4 15X20 4#3",
    "DE K-1 A K-4 4#3",
    "DET. 5 K-1 4#3",
    "DET. K-1 4#3",
    "DET. K-2A E#3@1S",
    "DETALLE DE K-1 15X15 4#3",
    "DETALLE K 1 4#3",
    "DETALLE T1-1 20X40",
    "E #4@20",
    "E | #4@20",
    "E#2@10",
    "E#2@15",
    "E#2@15 2E#3 VER CORTE",
    "E#2@15 VER CORTE",
    "E#2@15 VER CORTE C-2",
    "E#2@15 VER CORTE C-2 8#6 E#3@20",
    "E#2@15 VER DET. K-2A",
    "E#2@15 VER DETALLE",
    "E#2@15 VER DETALLE K-2",
    "E#2@20",
    "E#2@25",
    "E#3",
    "E#3 @20CMS",
    "E#3 VER CORTE",
    "E#3@10",
    "E#3@14",
    "E#3@15",
    "E#3@20",
    "E#3@20CMS CADENA DE DESPLANTE",
    "E#4@30",
    "EYG#2@15",
    "EYG#3@15",
    "EYG#3@1S",
    "HUECOS DE HASTA 15X20 EN CONTRATRABES 4#4",
    "K 7 #3",
    "K 7#3",
    "K-07 E#3@1S",
    'K-1 15X15 4 VARS 3/8" E 1/4 @ 15',
    'K-1 15X15 4 VARS 5/16" E 1/4 @ 15',
    "K-1 15X15 4 VARS DE 3 E#2@15",
    "K-1 15X15 4#3",
    "K-1 15X15 4#3 #2@20",
    "K-1 15X15 4#3 E#2@15 VER CORTE C-2",
    "K-1 15X15 4#3 E#2@15 VER CORTE C-2 30X30 8#6",
    "K-1 15X15 4#3 VER CORTE C-2",
    "K-1 15X15 E#2@20 CON V 4",
    "K-1 15X15 E#2@20 V 4",
    "K-1 15X15 E#2@20 V-4",
    "K-1 15X15 NO. 3",
    "K-1 15X15 N° 3 E#2@15",
    "K-1 15X15 V 4",
    "K-1 15X15 V4#4 E#2@20",
    "K-1 15X20 4#3",
    "K-1 15X20 4#3 IGUAL A K-2",
    "K-1 15x20 4#3 E#2@20",
    "K-1 20X15 4#3",
    "K-1 20X40.5 4#3",
    "K-1 4 VARILLAS DEL No. 3",
    'K-1 4 VARS 3/8"',
    "K-1 4 VARS. N° 3",
    "K-1 4#3",
    "K-1 4#3 E#2@20 (V-4) 4#5",
    "K-1 4#3 E#2@20 V-4 - 4#5",
    "K-1 4#3 E#2@20 V-4 CON 4#5",
    "K-1 4#3 E#2@20 V-4 LECHO SUP. 2#5",
    "K-1 4#3 E#2@20 V-4: 20X40 4#5 E#3@15",
    "K-1 4#3 E#2@20 V-4= 4#5",
    "K-1 4#3 E#2@20, V-4: 4#5",
    "K-1 4#3 VER CORTE C-2 E#2@15",
    "K-1 4#3, V-4 4#5",
    "K-1 4) #3",
    "K-1 4-#3",
    "K-1 A 15X20",
    "K-1 A 15X20 4#3",
    "K-1 A 4 15X20 4#3",
    "K-1 A 4 4#3",
    "K-1 A 4#3",
    "K-1 A 4#3 E#3@20",
    "K-1 A 40 CENTIMETROS E#3@1S",
    "K-1 A C-4 15X20 4#3",
    "K-1 A K-4 15X20 4#3",
    "K-1 A K-4 4#3",
    "K-1 DE 15 CM 4#3 E#2@20",
    "K-1 LONG. 8 4#3",
    "K-1 Y 2 15X20",
    "K-1 Y 2 15X20 4#3",
    "K-1 Y 2 E#2@20",
    "K-1 Y K-2 15X20",
    "K-1 Y K-2 15X20 4#3",
    "K-1 Y K-2 15X20 4#3 E#2@20",
    "K-1 Y K–2 4#3",
    "K-1 Y V-4 15X20 4#3",
    "K-1 — 4#3",
    "K-1, 2 Y 3 15X20 4#3",
    'K-1, 4 VARS 3/8" E 1/4" @ 15',
    "K-1, 4#3",
    "K-1, K-2 15X20 4#3",
    "K-1, K-2 4#3",
    "K-1-3 4#3",
    "K-1-A 15X20 4#4",
    "K-1-A 4#3",
    "K-1-A-K-3 4#3",
    "K-1-CE 4#3",
    "K-1-E 4#3",
    "K-1-K 3 4#3",
    "K-1-K-3 15X20 4#3",
    "K-1-K-3 4#3",
    "K-1-K-3 E#3@1S",
    "K-1. 4#3",
    "K-1.1 4#3",
    "K-1/K 7 4#3",
    "K-1/K 7 E#3@1S",
    "K-11 · 8#6 / 2E#3EXT@10 / CENTRO@20",
    "K-15 A 20X20 4#3 E#3@20",
    "K-15 A 4#3",
    "K-15 A 4#3 E#3@20",
    "K-15A.1 4#3",
    "K-1–K-3 15X20 4#3",
    "K-1–K-3 4#3",
    "K-1–K-3 E#3@1S",
    "K-1—K-3 E#3@1S",
    "K-2 15X20 4 VAR. No. 3 E#2@15",
    "K-2 15X20 4#3",
    "K-2 15X20 4#3 E#2@15",
    "K-2 15X20 4#4 E#2@20",
    "K-2A 20X20 4#4 E#2@15",
    "K-2A E#3@1S",
    "K-3 15X30 6#3",
    "K-7 15X15",
    "K-7 20X30",
    "K-7 4#3",
    "K-7 4#3 15X20",
    "K-7 E#3@1S",
    "K-7 E#3@20",
    "K-7-E #3@20 15X20",
    "K-70 4#3",
    "K-7E#3@20 15X20",
    "K-8 E #3@20",
    "K-9 15X20 4#3 E#2@15",
    "K-9 15X20 4#3 E#2@1S",
    "K-9 20X30",
    "K-9 20X40",
    "K-9 20X40 4#3",
    "K-9 4#3",
    "K-9 E#3@1S",
    "K15A 15X15 4#3",
    "K15A 4#3",
    "K‑7 4#3",
    "K–7 4#3",
    "L=8.00 M",
    "LIGA#2@20",
    "LONGITUD DE ANCLAJE 40 DIAM. 4#5",
    "LOS CASTILLOS DEL EJE 3 LLEVAN E#3@15",
    "LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S",
    "NOTAS:\n1.- 4#3 E#2@20 VER CORTE C-2",
    "P 4#3",
    "P-4 L=8.00 M",
    "P-5-P 4#3",
    "PLACA BASE 35X35",
    "PLACA DE 30X30 CON 4#4",
    "PLACA DE APOYO 2#4 #3@20",
    "REFUERZO 12#6",
    "SECCION K-1 15X20 4#3",
    "SECCIÓN K-1 15X20 4#3",
    "T-1 20X40 V 4 LS V 3 LI E#3@15",
    "T-1 30X60 E#3@15 LS V 3",
    "T-1 40X20 4#3",
    "T-1&T-2 E#3@1S",
    "T-1-E #3@20 20X40",
    "T-1-T 4#3",
    "T-1-T-2 20X40 2#6",
    "T-11 20X40 4#3",
    "T-11 20X40 4#3 E#2@20",
    "T-1=T-2 E#3@1S",
    "T-2 E#3@1S",
    "T1-1 (E#3@1S)",
    "T1-1 25X50 2#5",
    "T1-1 4#3",
    "T1-1 A 3 4#3",
    "T1-1 A T1-3 30X60 4#5",
    "T1-1 A T1-3 4#3",
    "T1-1 E#3@1S",
    "T1-1 Y 2 4#3",
    "T1-1 Y T1-2 E#3@1S",
    "T1-1-T1-3 4#3",
    "T1-1: E#3@1S",
    "T1-1E#3@20 20X40",
    "T1-4#3 E#2@20",
    "T2 4#3",
    "T2-15E#3@15 20X40",
    "T2-7 20X40",
    "TE-A 40X20 4#4",
    "TL-1 4#3",
    "TL-1E#3@20 20X40",
    "TRABE T - 1 E#3@1S",
    "TRABE T 1 E#3@1S",
    "TRABE T-1 E#3@1S",
    "TRABE T-1&T-2 E#3@1S",
    "TRABE T-1+T-2 E#3@1S",
    "TRABE T-1-T-2 E#3@1S",
    "TRABE T-1=T-2 E#3@1S",
    "TRABE TE A 20X40 E#3@20",
    "TRABE TE A E#3@20 20X40",
    "TRABE TL 1 20X40 4#3",
    "TRABE TL 1 E#3@1S",
    "TRABE V 1 E#3@1S",
    "TRABE-T 1 E#3@1S",
    "TRABE:T-1 E#3@1S",
    "V 1 4#4",
    "V-1 15X20",
    "V-1 4#4",
    "V-1E#3@20 20X40",
    "V-4 #4 E#3@20",
    "V-4 - 4#5",
    "V-4 20X40 V4#4 E#3@15",
    "V-4 CON 4#5",
    "V-4 LECHO SUP. 2#5",
    "V-4: 20X40 4#5 E#3@15",
    "V-4= 4#5",
    "V12 #5",
    "V12 #5 E#3 @20CMS",
    "V12#5 E#3 @20cms",
    "V4 #4",
    "V4#4",
    "V4#4 E#2 @20cms",
    "V4#4 E#3",
    "VAR 4#4",
    "VER CORTE C-2 30X30 8#6",
    "VER CORTE C-2 30X30 8#6 E#2@15",
    "Z-100A 4#3",
    "ZA-3 120X150 #4@20",
    "ZA-3 4#4 E#3@20",
]
