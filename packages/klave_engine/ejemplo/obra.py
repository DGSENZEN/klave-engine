"""Los planos de la obra de ejemplo: un edificio chico de concreto, dibujado
en centímetros con las convenciones que el lector de reglas ya lee. Cada
elemento que el recorrido señala está puesto a propósito:

- el cuadro de columnas, cuyas marcas el lector también ve como columnas y
  duda de ellas — la duda del visor (excluir con X es la respuesta);
- notas generales con f'c=300 en cimentación, que el catálogo costea en
  f'c=250 — el hallazgo bloqueante de la exportación;
- columnas C-1 y C-2 de secciones distintas en el cuadro — las variantes que
  se mapean al catálogo del taller;
- la Rev B agranda una zapata, cambia la columna de B-4 por una C-2 y quita
  el muro — aditivas y deductivas en Cambios.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import ezdxf

# Ejes: A–C en Y, 1–4 en X (cm).
EJES_Y = {"A": 0.0, "B": 500.0, "C": 1000.0}
EJES_X = {"1": 0.0, "2": 600.0, "3": 1200.0, "4": 1800.0}
H = 15.0  # altura de texto, cm


def _doc():
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5  # centímetros
    return doc


def _texto(msp, valor: str, x: float, y: float, capa: str, h: float = H) -> None:
    msp.add_text(valor, dxfattribs={"layer": capa, "height": h}).set_placement((x, y))


def _ejes(msp) -> None:
    for marca, y in EJES_Y.items():
        msp.add_line((-200, y), (2000, y), dxfattribs={"layer": "S-GRID"})
        _texto(msp, marca, -300, y - H / 2, "S-GRID", 25)
    for marca, x in EJES_X.items():
        msp.add_line((x, -200), (x, 1200), dxfattribs={"layer": "S-GRID"})
        _texto(msp, marca, x - 8, -300, "S-GRID", 25)


def _trabe(msp, marca: str, y: float, ancho: float) -> None:
    """Una trabe a lo largo de un eje horizontal: un solo paño (nunca el eje
    mismo, que el lector no toma por trabe; dos paños se leerían como muro en
    una hoja sin capa de muros) y su marca en cada claro."""
    paño = y + ancho / 2
    msp.add_line((0, paño), (1800, paño), dxfattribs={"layer": "S-BEAM"})
    xs = sorted(EJES_X.values())
    for a, b in zip(xs, xs[1:], strict=False):
        _texto(msp, marca, (a + b) / 2 - 20, y + ancho / 2 + 10, "S-BEAM")


def _columnas(revision: str) -> dict[tuple[str, str], str]:
    """Columna por intersección: C-2 en las esquinas, C-1 en el resto."""
    out: dict[tuple[str, str], str] = {}
    for ey in EJES_Y:
        for ex in EJES_X:
            esquina = ey in ("A", "C") and ex in ("1", "4")
            out[(ey, ex)] = "C-2" if esquina else "C-1"
    if revision == "B":
        out[("B", "4")] = "C-2"  # la Rev B la cambia por una más grande
    return out


def _cimentacion(path: Path, revision: str) -> Path:
    doc = _doc()
    msp = doc.modelspace()
    _ejes(msp)
    for (ey, ex), marca in _columnas(revision).items():
        x, y = EJES_X[ex], EJES_Y[ey]
        zapata = "Z-2" if marca == "C-2" else "Z-1"
        mitad = 75.0 if zapata == "Z-2" else 60.0
        if revision == "B" and (ey, ex) == ("A", "4"):
            mitad = 95.0  # la Rev B agranda esta zapata
        msp.add_lwpolyline(
            [(x - mitad, y - mitad), (x + mitad, y - mitad),
             (x + mitad, y + mitad), (x - mitad, y + mitad)],
            close=True, dxfattribs={"layer": "S-FOOTING"},
        )
        _texto(msp, zapata, x - mitad + 10, y - mitad + 10, "S-FOOTING")
    # Contratrabes sobre los ejes A y C.
    for ey in ("A", "C"):
        _trabe(msp, "CT-1", EJES_Y[ey], 30.0)
    _texto(msp, "PLANTA DE CIMENTACION", 600, -500, "S-ANNO", 30)
    _texto(msp, "NOTAS GENERALES", 2400, 900, "S-ANNO", 20)
    _texto(msp, "CONCRETO EN CIMENTACION F'C=300 KG/CM2", 2400, 860, "S-ANNO")
    _texto(msp, "ACERO DE REFUERZO FY=4200 KG/CM2", 2400, 830, "S-ANNO")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))
    return path


def _estructura(path: Path, revision: str) -> Path:
    doc = _doc()
    msp = doc.modelspace()
    _ejes(msp)
    for (ey, ex), marca in _columnas(revision).items():
        x, y = EJES_X[ex], EJES_Y[ey]
        msp.add_circle((x, y), 12, dxfattribs={"layer": "S-COL"})
        _texto(msp, marca, x + 20, y + 20, "S-COL-TAG")
    # Trabes sobre los ejes A–C: T-1 en las orillas, T-2 al centro.
    for ey, y in EJES_Y.items():
        _trabe(msp, "T-2" if ey == "B" else "T-1", y, 30.0)
    # Losa entre ejes.
    msp.add_lwpolyline(
        [(0, 0), (1800, 0), (1800, 1000), (0, 1000)],
        close=True, dxfattribs={"layer": "S-SLAB"},
    )
    if revision == "A":
        # Muro de colindancia (la Rev B lo quita).
        msp.add_line((0, 1100), (1200, 1100), dxfattribs={"layer": "S-WALL"})
        msp.add_line((0, 1115), (1200, 1115), dxfattribs={"layer": "S-WALL"})
    # Cuadro de columnas.
    x0, y0 = 2400.0, 1000.0
    filas = [
        ["MARCA", "SECCION", "ARMADO", "ESTRIBOS"],
        ["C-1", "30x40", "8#5", "E#3@15"],
        ["C-2", "40x40", "12#5", "E#3@15"],
    ]
    for r, fila in enumerate(filas):
        for c, valor in enumerate(fila):
            _texto(msp, valor, x0 + c * 180, y0 - r * 30, "S-ANNO")
    # Cuadro de trabes y contratrabes.
    filas = [
        ["MARCA", "SECCION", "ARMADO", "ESTRIBOS"],
        ["T-1", "30x50", "6#5", "E#3@20"],
        ["T-2", "30x60", "8#5", "E#3@20"],
        ["CT-1", "30x60", "8#6", "E#3@15"],
    ]
    for r, fila in enumerate(filas):
        for c, valor in enumerate(fila):
            _texto(msp, valor, x0 + c * 180, y0 - 200 - r * 30, "S-ANNO")
    _texto(msp, "PLANTA ESTRUCTURAL NIVEL 1", 600, -500, "S-ANNO", 30)
    _texto(msp, "NOTAS GENERALES", x0, 600, "S-ANNO", 20)
    _texto(msp, "CONCRETO EN COLUMNAS, TRABES Y LOSA F'C=250 KG/CM2", x0, 560, "S-ANNO")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))
    return path


def build_obra_ejemplo(project_root: Path, revision: Literal["A", "B"] = "A") -> list[Path]:
    """Escribe las hojas de la obra en ``project_root/drawings``. La Rev B
    reescribe los mismos archivos: es una revisión del mismo juego."""
    dibujos = project_root / "drawings"
    return [
        _cimentacion(dibujos / "S-101 Cimentacion.dxf", revision),
        _estructura(dibujos / "S-201 Estructura.dxf", revision),
    ]
