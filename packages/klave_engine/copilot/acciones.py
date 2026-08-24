"""Lo que el copiloto puede *hacer*, no solo explicar.

Un asistente que solo conversa deja el trabajo donde estaba. Lo que ahorra
tiempo de verdad es cerrar el paso que el hallazgo ya identificó: el
presupuesto dice «seis conceptos costean un f'c menor al que declara el
plano», y la acción es cambiarlos — con el precio publicado que corresponde,
a la vista, antes de tocar nada.

Cuatro reglas, y las cuatro salen de la misma idea: el ingeniero firma.

1. **Determinista donde se pueda.** Estas propuestas no las redacta un
   modelo: salen del propio diagnóstico y del catálogo. Son reproducibles,
   auditables y gratis. El modelo hace falta para lo abierto, no para esto.
2. **Nada se aplica sin que alguien lo vea.** Cada acción trae su
   `vista_previa`: qué cambia, de cuánto a cuánto, y en qué conceptos. La
   evidencia sobre decisiones asistidas por máquina es clara en que un campo
   ya rellenado ancla al humano; aquí no hay nada rellenado hasta que se
   acepta.
3. **Nada se inventa.** Un precio propuesto viene de una fuente publicada,
   con su clave y su vigencia. Cuando no hay fuente, la acción no existe y el
   hallazgo se queda pidiendo un dato, que es la respuesta honesta.
4. **Se aplica por la puerta de siempre.** Cada acción nombra el endpoint que
   ya existe, con su validación, su bitácora y su recálculo. El copiloto no
   tiene un camino privado a la base de datos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from klave_engine.costing.hallazgos import Diagnostico
from klave_engine.costing.models import CostReport

_FC = re.compile(r"f\s*'?\s*c\s*=?\s*(\d{3})", re.I)


@dataclass
class Cambio:
    """Una línea de la vista previa: qué pasa de qué a qué."""

    concepto: str
    de: str
    a: str
    monto_actual: float | None = None


@dataclass
class Accion:
    """Algo concreto que el copiloto puede hacer, si el ingeniero acepta."""

    tipo: str
    titulo: str
    # Qué va a pasar, en una frase que se entienda sin abrir nada.
    descripcion: str
    # El endpoint que ya existe y que ejecuta esto (nunca un camino privado).
    endpoint: str
    metodo: str = "POST"
    # Lo que hay que mandarle, por concepto o en bloque.
    peticiones: list[dict[str, Any]] = field(default_factory=list)
    vista_previa: list[Cambio] = field(default_factory=list)
    # Qué falta para poder ejecutarla (un precio, una decisión). Vacío = lista.
    requiere: str = ""
    # Cómo se deshace, dicho antes de hacerla.
    reversible: str = ""
    # El hallazgo del que nació, para que la interfaz la ponga junto a él.
    hallazgo_id: str = ""


def _misma_unidad(a: str, b: str) -> bool:
    """M3 y m³ son la misma unidad; M2 y M3 no lo son ni de lejos.

    Adoptar un precio por m³ en un concepto que se mide en m² multiplica mal
    por un factor que nadie nota hasta la obra, así que la comparación es
    estricta."""
    def limpia(u: str) -> str:
        return (
            str(u or "").strip().upper().replace("³", "3").replace("²", "2").replace(".", "")
        )

    return limpia(a) == limpia(b)


def _referencias_fc(store: Any, fc: int, unidad: str) -> list[dict]:
    """Renglones publicados que ofrecen concreto de ese f'c en esa unidad.

    Solo publicaciones y catálogos propios: nada que el motor haya inventado.
    Y solo en la unidad del concepto — una referencia en otra unidad no es una
    propuesta más barata, es una propuesta equivocada."""
    try:
        filas = store.list_reference_rows()
    except Exception:  # noqa: BLE001 — sin catálogo no hay propuesta, y ya
        return []
    salida = []
    for fila in filas:
        descripcion = str(fila.get("description") or "")
        precio = fila.get("price")
        if precio in (None, 0):
            continue
        encontrado = _FC.search(descripcion)
        if not encontrado or int(encontrado.group(1)) != fc:
            continue
        if "concreto" not in descripcion.lower():
            continue
        if not _misma_unidad(fila.get("unit") or "", unidad):
            continue
        salida.append(fila)
    salida.sort(key=lambda f: float(f.get("price") or 0))
    return salida


def _fc_declarado(hallazgo_detalle: str) -> tuple[int, int] | None:
    """(el del plano, el que se está costeando) del texto del hallazgo."""
    encontrados = _FC.findall(hallazgo_detalle)
    if len(encontrados) < 2:
        return None
    return int(encontrados[0]), int(encontrados[1])


def proponer(
    report: CostReport, diagnostico: Diagnostico, store: Any, project_id: str
) -> list[Accion]:
    """Las acciones que resuelven los hallazgos de este presupuesto.

    Derivadas, no redactadas: si el diagnóstico no lo detectó, aquí no
    aparece."""
    acciones: list[Accion] = []
    lineas = {line.concept_code: line for line in report.boq.lines}

    for hallazgo in diagnostico.hallazgos:
        texto = f"{hallazgo.title} {hallazgo.detail}"

        # --- el f'c que no coincide con el plano ----------------------
        if hallazgo.id.startswith("motor:fc_menor_al_plano"):
            pares = [
                (codigo, _fc_declarado(fragmento))
                for fragmento in hallazgo.detail.split(" · ")
                for codigo in re.findall(r"\b([A-Z]{2,4}-\d{3})\b", fragmento)[:1]
            ]
            cambios: list[Cambio] = []
            peticiones: list[dict[str, Any]] = []
            sin_fuente: set[int] = set()
            sin_referencia: list[str] = []
            for codigo, par in pares:
                if par is None or codigo not in lineas:
                    continue
                del_plano, costeado = par
                referencias = _referencias_fc(store, del_plano, lineas[codigo].unit)
                if not referencias:
                    sin_fuente.add(del_plano)
                    sin_referencia.append(codigo)
                    continue
                mejor = referencias[0]
                linea = lineas[codigo]
                fuente = mejor.get("source_name") or mejor.get("source_key")
                cambios.append(
                    Cambio(
                        concepto=codigo,
                        de=f"f'c={costeado} · {linea.unit_price:,.2f}/{linea.unit}",
                        a=(
                            f"f'c={del_plano} · {float(mejor['price']):,.2f}"
                            f"/{mejor.get('unit') or 'M3'} ({fuente})"
                        ),
                        monto_actual=linea.amount,
                    )
                )
                peticiones.append(
                    {
                        "endpoint": f"/catalog/concepts/{codigo}/adopt",
                        "body": {"ref_id": mejor.get("ref_id")},
                        "concepto": codigo,
                        # La descripción es lo que firma el cliente: si el
                        # concepto se cobra a f'c=300, no puede seguir
                        # diciendo 250 en el presupuesto.
                        "descripcion": _FC.sub(
                            f"f'c={del_plano}", linea.description, count=1
                        ),
                        "fc": del_plano,
                    }
                )
            if cambios:
                falta = (
                    f" No traigo referencia en la unidad de {', '.join(sin_referencia)} "
                    f"para f'c={', '.join(str(f) for f in sorted(sin_fuente))}: esos los "
                    "ajustas tú."
                    if sin_referencia
                    else ""
                )
                acciones.append(
                    Accion(
                        tipo="adoptar_precio_publicado",
                        titulo="Adoptar el P.U. publicado del f'c que declara el plano",
                        descripcion=(
                            f"Cambia el P.U. de {len(cambios)} concepto(s) al precio "
                            "publicado del tabulador para el f'c correcto, y corrige su "
                            "descripción al f'c que se está cobrando. El importe cambia y "
                            "el presupuesto se recalcula." + falta
                        ),
                        endpoint="/catalog/concepts/{code}/adopt",
                        peticiones=peticiones,
                        vista_previa=cambios,
                        reversible=(
                            "Se deshace con «Volver a la matriz» en cada concepto del "
                            "catálogo."
                        ),
                        hallazgo_id=hallazgo.id,
                    )
                )

        # --- un concepto con cantidad y sin precio --------------------
        elif hallazgo.id.startswith("sin_precio:") and hallazgo.concept_code:
            codigo = hallazgo.concept_code
            sin_precio = lineas.get(codigo)
            if sin_precio is None:
                continue
            acciones.append(
                Accion(
                    tipo="dar_precio",
                    titulo=f"Darle precio a {codigo}",
                    descripcion=(
                        f"{sin_precio.quantity:,.2f} {sin_precio.unit} sin costo. Puedes "
                        "adoptar un "
                        "P.U. de tu catálogo propio o de una publicación, o capturar la "
                        "matriz."
                    ),
                    endpoint=f"/catalog/concepts/{codigo}/adopt",
                    requiere=(
                        "Elige de dónde sale el precio: no tengo forma de saber cuánto "
                        "cuesta sin que me lo digas o me apuntes a una fuente."
                    ),
                    reversible="Se quita con «Volver a la matriz».",
                    hallazgo_id=hallazgo.id,
                )
            )

        # --- terracerías sin nivel de plataforma ----------------------
        elif "nivel de plataforma" in texto.lower():
            acciones.append(
                Accion(
                    tipo="definir_parametro",
                    titulo="Definir el nivel de plataforma",
                    descripcion=(
                        "Con el nivel de proyecto, el motor calcula corte y terraplén "
                        "contra la topografía del plano. Sin él no los calcula contra "
                        "un nivel supuesto."
                    ),
                    endpoint=f"/projects/{project_id}/recompute",
                    requiere="El nivel de plataforma en metros, como lo fija el proyecto.",
                    reversible="Se cambia otra vez en Parámetros; queda una versión previa.",
                    hallazgo_id=hallazgo.id,
                )
            )

    return acciones
