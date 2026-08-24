"""Cuánto de lo que está dibujado alcanza a ver el motor.

El resto de las evaluaciones comparan al motor contra sí mismo: el gold set
fija lo que detectó ayer para que no se rompa hoy. Eso protege contra
regresiones y no dice nada sobre la pregunta que decide si el producto sirve
— **de todo lo que hay en el plano, ¿qué fracción encuentra?**

Esa pregunta solo la contesta un humano contando. Así que aquí el patrón se
invierte: alguien abre la hoja, cuenta los castillos que ve, lo escribe, y el
motor se mide contra ese número. Es trabajo manual y no hay forma de evitarlo;
la única alternativa es no saber.

Tres decisiones que hacen útil el resultado:

* **Por familia, no en global.** Un 90 % de recall que esconde un 40 % en
  zapatas no informa nada. Cada familia lleva su cuenta.
* **Ponderado por dinero.** Perder una trabe cuesta más que perder un eje. El
  reporte pesa cada familia por el importe que representa en el presupuesto,
  para que el esfuerzo de mejora vaya donde está el dinero.
* **Con intervalo, no con una cifra sola.** Con quince elementos contados, un
  recall de 0.87 no distingue entre 0.6 y 0.98. Se reporta el intervalo de
  Wilson para que nadie lea precisión donde solo hay una muestra chica.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.costing.models import CostReport
from klave_engine.detection.results import Detection

CONTEOS_DIR = Path("evals/conteos")


@dataclass
class ConteoHumano:
    """Lo que una persona contó en una hoja, con su nombre y su fecha.

    ``hoja`` vacía significa "en toda la obra"; contar por hoja es mejor
    porque permite ubicar dónde falla, pero un conteo global sigue valiendo."""

    familia: str
    dibujados: int
    hoja: str = ""
    nota: str = ""


@dataclass
class ConteoDeObra:
    drawing_id: str
    contado_por: str
    contado_en: str
    conteos: list[ConteoHumano] = field(default_factory=list)
    nota: str = ""

    @classmethod
    def desde_json(cls, ruta: Path) -> ConteoDeObra:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        return cls(
            drawing_id=crudo["drawing_id"],
            contado_por=crudo.get("contado_por", ""),
            contado_en=crudo.get("contado_en", ""),
            nota=crudo.get("nota", ""),
            conteos=[ConteoHumano(**c) for c in crudo.get("conteos", [])],
        )

    def a_json(self) -> dict:
        return {
            "drawing_id": self.drawing_id,
            "contado_por": self.contado_por,
            "contado_en": self.contado_en,
            "nota": self.nota,
            "conteos": [
                {k: v for k, v in vars(c).items() if v not in ("", 0) or k == "dibujados"}
                for c in self.conteos
            ],
        }


def wilson(aciertos: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza al 95 % para una proporción.

    Con muestras chicas —y todas las nuestras lo son— la fórmula normal da
    intervalos imposibles (negativos, o por encima de 1). La de Wilson no."""
    if total <= 0:
        return (0.0, 0.0)
    p = aciertos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margen = (
        z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominador
    )
    return (max(0.0, round(centro - margen, 3)), min(1.0, round(centro + margen, 3)))


@dataclass
class RecallFamilia:
    familia: str
    dibujados: int  # lo que contó la persona
    detectados: int  # lo que encontró el motor
    recall: float
    intervalo: tuple[float, float]
    # Importe del presupuesto que depende de esta familia, cuando se sabe.
    importe: float = 0.0

    @property
    def faltantes(self) -> int:
        return max(0, self.dibujados - self.detectados)

    @property
    def sobrantes(self) -> int:
        """El motor detectó de más: no es un fallo de recall, pero se anota —
        suele ser doble conteo entre vistas y también cuesta dinero."""
        return max(0, self.detectados - self.dibujados)


@dataclass
class ReporteRecall:
    drawing_id: str
    contado_por: str
    familias: list[RecallFamilia] = field(default_factory=list)
    generado_en: str = ""

    @property
    def recall_global(self) -> float:
        dibujados = sum(f.dibujados for f in self.familias)
        if not dibujados:
            return 0.0
        encontrados = sum(min(f.detectados, f.dibujados) for f in self.familias)
        return round(encontrados / dibujados, 3)

    @property
    def recall_ponderado(self) -> float:
        """El que importa: pesado por el dinero que cada familia representa.

        Perder una trabe no cuesta lo que perder un eje, y una media simple
        deja que cien ejes bien detectados tapen diez trabes perdidas."""
        peso = sum(f.importe for f in self.familias)
        if peso <= 0:
            return self.recall_global
        return round(
            sum(f.recall * f.importe for f in self.familias) / peso, 3
        )

    @property
    def dinero_no_visto(self) -> float:
        """Importe aproximado de lo que el motor no vio, suponiendo que cada
        elemento faltante vale como el promedio de su familia."""
        total = 0.0
        for f in self.familias:
            if f.detectados > 0 and f.importe > 0 and f.faltantes:
                total += f.importe / f.detectados * f.faltantes
        return round(total, 2)


# Qué familia del catálogo alimenta qué concepto, para poder pesar por dinero.
FAMILIA_POR_CONCEPTO = {
    "EST-001": "castillo", "EST-006": "castillo",
    "EST-002": "trabe", "CIM-008": "contratrabe",
    "EST-005": "dala",
    "CIM-002": "zapata",
    "CIM-010": "pilote", "CIM-011": "pilote",
    "EST-003": "losa", "EST-012": "losa", "EST-013": "losa", "CIM-007": "losa",
    "EST-004": "muro", "EST-014": "muro_concreto",
    "EST-015": "escalera",
}


def importe_por_familia(report: CostReport | None) -> dict[str, float]:
    """Cuánto dinero del presupuesto depende de cada familia detectada."""
    if report is None:
        return {}
    salida: dict[str, float] = {}
    for linea in report.boq.lines:
        familia = FAMILIA_POR_CONCEPTO.get(linea.concept_code)
        if familia:
            salida[familia] = round(salida.get(familia, 0.0) + linea.amount, 2)
    return salida


def medir(
    conteo: ConteoDeObra,
    detections: list[Detection],
    report: CostReport | None = None,
) -> ReporteRecall:
    """El recall de esta obra contra lo que la persona contó."""
    importes = importe_por_familia(report)
    por_familia: dict[str, int] = {}
    for conteo_humano in conteo.conteos:
        por_familia[conteo_humano.familia] = (
            por_familia.get(conteo_humano.familia, 0) + conteo_humano.dibujados
        )

    detectados_por_familia: dict[str, int] = {}
    for deteccion in detections:
        if deteccion.family:
            detectados_por_familia[deteccion.family] = (
                detectados_por_familia.get(deteccion.family, 0) + 1
            )

    familias: list[RecallFamilia] = []
    for familia, dibujados in sorted(por_familia.items()):
        detectados = detectados_por_familia.get(familia, 0)
        aciertos = min(detectados, dibujados)
        familias.append(
            RecallFamilia(
                familia=familia,
                dibujados=dibujados,
                detectados=detectados,
                recall=round(aciertos / dibujados, 3) if dibujados else 0.0,
                intervalo=wilson(aciertos, dibujados),
                importe=importes.get(familia, 0.0),
            )
        )
    return ReporteRecall(
        drawing_id=conteo.drawing_id,
        contado_por=conteo.contado_por,
        familias=familias,
        generado_en=datetime.now(UTC).isoformat(),
    )


def plantilla_de_conteo(drawing_id: str, familias: list[str]) -> ConteoDeObra:
    """Un formato en blanco para que alguien lo llene contando.

    Se genera con las familias que el motor sí detectó, porque son las que ya
    sabemos nombrar — pero quien cuenta debe agregar las que el motor no
    detectó en absoluto, que son justamente las más caras de descubrir."""
    return ConteoDeObra(
        drawing_id=drawing_id,
        contado_por="",
        contado_en="",
        nota=(
            "Cuenta sobre el plano, hoja por hoja. Agrega familias que el motor no "
            "haya detectado: las que faltan por completo son las que más importan."
        ),
        conteos=[ConteoHumano(familia=f, dibujados=0) for f in sorted(familias)],
    )
