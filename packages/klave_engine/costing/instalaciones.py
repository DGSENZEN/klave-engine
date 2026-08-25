"""Instalaciones: lo que el levantamiento ya lee y el presupuesto no cobra.

Un juego de planos de edificación trae hojas de hidráulica, sanitaria, gas y
aire acondicionado, y el levantamiento ya las recorre: sabe que la capa
``P-04IH-CPIP`` de la hoja de hidráulica tiene 149.41 m de desarrollo, que
``00-SANITARIA`` tiene 128.27 m y 16 bloques ``DESCSAN1``. Esa lectura hoy
muere ahí, porque no hay concepto al cual mandarla — y las instalaciones son
entre el 15 y el 25 % del costo de un edificio. El presupuesto salía sin
ellas y nadie lo decía.

Este módulo cierra el hueco por sus dos extremos:

* **Los conceptos existen** — hidráulica, sanitaria, gas, aire, eléctrica —
  pero **sin matriz**. El motor puede sostener la cantidad, porque la midió
  del plano; no puede sostener el precio, porque nadie se lo dio. Entran como
  cantidad real marcada «sin precio» hasta que el taller adopte una de su
  catálogo o de una publicación. Cero sería peor que nada: se suma.

* **Los mapeos se proponen, no se aplican.** Una capa llamada ``00-SANITARIA``
  en una hoja que el levantamiento ya clasificó como sanitaria es casi
  seguramente tubería sanitaria — casi. La propuesta viene con la razón, con
  la hoja de la que salió y con la cantidad que produciría, y alguien la
  confirma. Aplicarla sola convertiría una convención de dibujo en dinero sin
  que nadie mirara.

El filtro de disciplina es lo que hace utilizable a la biblioteca. En la hoja
de aire acondicionado conviven ``AireDucto`` (que sí es ducto) con ``MUROS2``,
``COLUMNA`` y ``PLAFONES``, que son el fondo arquitectónico del dibujo. Sin
disciplina habría que adivinar; con ella, sólo se proponen capas cuyo nombre
además dice de qué son.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from klave_engine.costing.models import Concept, QuantityKind, QuantityRule
from klave_engine.detection.results import DetectionType

# Las partidas como se llaman en un presupuesto mexicano, no como se llaman
# en el árbol de capas de un DWG.
FASE_HIDRAULICA = "Instalación hidráulica"
FASE_SANITARIA = "Instalación sanitaria"
FASE_ELECTRICA = "Instalación eléctrica"
FASE_GAS = "Instalación de gas"
FASE_AIRE = "Aire acondicionado"
# Los vanos no son instalación, pero salen del mismo sitio: un símbolo
# sobre el plano que hasta ahora sólo se contaba.
FASE_CANCELERIA = "Cancelería y carpintería"
# Los muebles son su propia partida en un presupuesto mexicano: el W.C.
# cuesta miles y su salida hidráulica cientos, y se contratan por separado.
FASE_MUEBLES = "Muebles y accesorios"
FASE_IMPERMEABILIZACION = "Impermeabilización"

# code, description, unit, phase, rendimiento/día, orden
_CONCEPTOS: tuple[tuple[str, str, str, str, float, int], ...] = (
    # --- Hidráulica -------------------------------------------------------
    ("HID-001", "Salida hidráulica de agua fría en muro, incluye conexiones y pruebas",
     "SAL", FASE_HIDRAULICA, 6.0, 10),
    ("HID-002", "Salida hidráulica de agua caliente en muro, incluye conexiones y pruebas",
     "SAL", FASE_HIDRAULICA, 5.0, 20),
    ("HID-003", "Tubería de agua fría, incluye conexiones, soportería y prueba hidrostática",
     "M", FASE_HIDRAULICA, 30.0, 30),
    ("HID-004", "Tubería de agua caliente con aislamiento, incluye conexiones y prueba",
     "M", FASE_HIDRAULICA, 25.0, 40),
    ("HID-005", "Tubería de retorno de agua caliente, incluye conexiones y prueba",
     "M", FASE_HIDRAULICA, 25.0, 50),
    # --- Sanitaria --------------------------------------------------------
    ("SAN-001", "Salida sanitaria de descarga, incluye conexiones y pruebas",
     "SAL", FASE_SANITARIA, 6.0, 10),
    ("SAN-002", "Tubería sanitaria de albañal, incluye conexiones y soportería",
     "M", FASE_SANITARIA, 28.0, 20),
    ("SAN-003", "Bajada de aguas pluviales, incluye abrazaderas y conexiones",
     "M", FASE_SANITARIA, 30.0, 30),
    ("SAN-004", "Registro sanitario de tabique con tapa de concreto",
     "PZA", FASE_SANITARIA, 1.5, 40),
    # --- Gas --------------------------------------------------------------
    ("GAS-001", "Tubería de gas, incluye conexiones y prueba de hermeticidad",
     "M", FASE_GAS, 22.0, 10),
    # --- Aire acondicionado ----------------------------------------------
    ("AIR-001", "Ducto de lámina galvanizada con aislamiento y soportería, "
     "por metro de desarrollo", "M", FASE_AIRE, 12.0, 10),
    ("AIR-002", "Ducto flexible aislado, incluye collarines y soportería",
     "M", FASE_AIRE, 30.0, 20),
    ("AIR-003", "Tubería de cobre para refrigerante con aislamiento, en pares",
     "M", FASE_AIRE, 20.0, 30),
    ("AIR-004", "Rejilla o difusor de suministro/retorno, incluye marco y compuerta",
     "PZA", FASE_AIRE, 8.0, 40),
    # --- Eléctrica --------------------------------------------------------
    ("ELE-001", "Salida eléctrica para contacto, incluye caja, chalupa y cableado",
     "SAL", FASE_ELECTRICA, 8.0, 10),
    ("ELE-002", "Salida eléctrica para centro de luz o apagador, incluye caja y cableado",
     "SAL", FASE_ELECTRICA, 8.0, 20),
    ("ELE-003", "Canalización con tubo conduit, incluye accesorios y soportería",
     "M", FASE_ELECTRICA, 35.0, 30),
    ("ELE-004", "Alimentador con cable de cobre THW, incluye identificación y conexión",
     "M", FASE_ELECTRICA, 40.0, 40),
    # --- Cancelería y carpintería (vanos) ---------------------------------
    ("CAN-001", "Cancelería de aluminio con cristal, según cuadro de vanos, "
     "incluye herrajes y sellado", "PZA", FASE_CANCELERIA, 3.0, 10),
    ("CAN-002", "Ventana de aluminio con cristal, según cuadro de vanos, "
     "incluye herrajes y sellado", "PZA", FASE_CANCELERIA, 4.0, 20),
    ("CAR-001", "Puerta con marco y herrajes, según cuadro de vanos, "
     "incluye colocación y ajuste", "PZA", FASE_CANCELERIA, 4.0, 30),
    # --- Muebles y equipos --------------------------------------------------
    # El mueble no es su salida. Detectábamos el W.C. y sólo cobrábamos la
    # salida hidráulica: el mueble, que cuesta entre mil y veintitantos mil
    # pesos, se quedaba fuera del presupuesto estando detectado.
    ("MUE-001", "W.C. de tanque bajo, incluye asiento, conexiones y accesorios",
     "PZA", FASE_MUEBLES, 4.0, 10),
    ("MUE-002", "Lavabo con mezcladora, incluye céspol, contras y accesorios",
     "PZA", FASE_MUEBLES, 5.0, 20),
    ("MUE-003", "Regadera con mezcladora y brazo, incluye accesorios",
     "PZA", FASE_MUEBLES, 6.0, 30),
    ("MUE-004", "Fregadero o tarja con mezcladora, incluye céspol y accesorios",
     "PZA", FASE_MUEBLES, 5.0, 40),
    ("MUE-005", "Mingitorio con fluxómetro, incluye conexiones y accesorios",
     "PZA", FASE_MUEBLES, 4.0, 50),
    ("MUE-006", "Tina de baño, incluye conexiones y accesorios",
     "PZA", FASE_MUEBLES, 2.0, 60),
    ("MUE-007", "Lavadero, incluye conexiones y accesorios",
     "PZA", FASE_MUEBLES, 4.0, 70),
    ("MUE-008", "Calentador de agua, incluye conexiones, base y prueba",
     "PZA", FASE_MUEBLES, 3.0, 80),
    # --- Piezas de red que se cuentan por pieza ----------------------------
    ("HID-006", "Válvula, incluye instalación, conexiones y prueba",
     "PZA", FASE_HIDRAULICA, 8.0, 60),
    ("HID-007", "Medidor o toma domiciliaria, incluye conexiones y registro",
     "PZA", FASE_HIDRAULICA, 2.0, 70),
    ("SAN-005", "Coladera con rejilla, incluye conexión a la red",
     "PZA", FASE_SANITARIA, 8.0, 50),
    ("ELE-005", "Tablero o centro de carga, incluye pastillas termomagnéticas "
     "y conexión", "PZA", FASE_ELECTRICA, 1.5, 50),
    ("ELE-006", "Salida eléctrica especial para equipo, incluye canalización y "
     "cableado", "SAL", FASE_ELECTRICA, 5.0, 60),
    ("AIR-005", "Equipo de aire acondicionado, incluye instalación, base y "
     "arranque", "PZA", FASE_AIRE, 1.0, 50),
    ("AIR-006", "Compuerta reguladora de volumen en ducto, incluye marco",
     "PZA", FASE_AIRE, 6.0, 60),
    ("GAS-002", "Tanque estacionario de gas, incluye base, conexión y prueba",
     "PZA", FASE_GAS, 1.0, 20),
    # --- Impermeabilización ------------------------------------------------
    # El plano no la dibuja: se sigue del área de azotea o se levanta a mano.
    # Existe como concepto para que tenga a dónde llegar cuando alguien la
    # capture, y porque el tabulador publica 54 renglones para ella.
    ("IMP-001", "Impermeabilización de azotea con manto prefabricado, "
     "incluye preparación de la superficie", "M2", FASE_IMPERMEABILIZACION, 60.0, 10),
)

# Un concepto de instalaciones sale del catálogo **sin matriz**: la cantidad
# la sostiene el plano, el precio no lo sostiene nadie todavía.
SIN_MATRIZ: list[tuple[str, float]] = []

CONCEPTOS_STORE: list[tuple[str, str, str, str, float, int, list[tuple[str, float]]]] = [
    (code, desc, unit, phase, rate, order, SIN_MATRIZ)
    for code, desc, unit, phase, rate, order in _CONCEPTOS
]

CODIGOS: tuple[str, ...] = tuple(c[0] for c in _CONCEPTOS)

# Qué detección alimenta a qué concepto. Los muebles y salidas se cuentan por
# pieza; las corridas se miden por metro de su sistema. Nada de esto se
# adivina: la familia la puso el detector al reconocer el nombre del bloque o
# de la capa, y aquí sólo se dice a qué concepto corresponde.
_MUEBLES_POR_CONCEPTO: dict[str, tuple[str, ...]] = {
    # Cada mueble lleva su salida de agua fría; la de agua caliente es una
    # decisión de proyecto que se lee de la red, no del mueble, y por eso
    # HID-002 no se cuantifica sola.
    "HID-001": ("wc", "lavabo", "regadera", "fregadero", "mingitorio", "tina", "lavadero"),
    "SAN-001": ("salida_sanitaria",),
    "SAN-004": ("registro",),
    "ELE-001": ("contacto",),
    "ELE-002": ("apagador", "luminaria"),
    "AIR-004": ("difusor",),
    # El mueble, aparte de su salida: las dos cosas se detectan del mismo
    # símbolo y las dos se pagan.
    "MUE-001": ("wc",),
    "MUE-002": ("lavabo",),
    "MUE-003": ("regadera",),
    "MUE-004": ("fregadero",),
    "MUE-005": ("mingitorio",),
    "MUE-006": ("tina",),
    "MUE-007": ("lavadero",),
    "MUE-008": ("calentador",),
    "HID-006": ("valvula",),
    "HID-007": ("medidor",),
    "SAN-005": ("coladera",),
    "ELE-005": ("tablero",),
    "ELE-006": ("salida_especial",),
    "AIR-005": ("equipo_aa",),
    "AIR-006": ("compuerta",),
    "GAS-002": ("tanque_gas",),
}

# «bajada» se detecta y a propósito no recibe concepto: el símbolo de
# subida-bajada marca dónde la tubería cambia de nivel, y esos metros ya los
# cobra la corrida. Darle concepto propio sería cobrar dos veces el mismo
# tramo. Se queda visible en el visor, que es donde sirve.

_VANOS_POR_CONCEPTO: dict[str, tuple[str, ...]] = {
    "CAN-001": ("cancel",),
    "CAN-002": ("ventana",),
    "CAR-001": ("puerta",),
}

_CORRIDAS_POR_CONCEPTO: dict[str, tuple[str, ...]] = {
    "HID-003": ("agua_fria",),
    "HID-004": ("agua_caliente",),
    "HID-005": ("retorno",),
    "SAN-002": ("sanitaria",),
    "SAN-003": ("pluvial",),
    "GAS-001": ("gas",),
    "AIR-001": ("ducto",),
    "AIR-002": ("ducto_flexible",),
    "AIR-003": ("refrigerante",),
    "ELE-003": ("conduit",),
}


def _regla(code: str) -> QuantityRule | None:
    """La regla de cantidad del concepto, o None si sólo se llena a mano."""
    familias = _MUEBLES_POR_CONCEPTO.get(code)
    if familias:
        return QuantityRule(
            detection_type=DetectionType.fixture,
            kind=QuantityKind.COUNT,
            property_filter={"fixture_family": list(familias)},
        )
    familias = _VANOS_POR_CONCEPTO.get(code)
    if familias:
        return QuantityRule(
            detection_type=DetectionType.opening,
            kind=QuantityKind.COUNT,
            property_filter={"opening_family": list(familias)},
        )
    familias = _CORRIDAS_POR_CONCEPTO.get(code)
    if familias:
        return QuantityRule(
            detection_type=DetectionType.pipe_run,
            kind=QuantityKind.LENGTH,
            source_property="estimated_length",
            property_filter={"run_family": list(familias)},
        )
    return None


_SIN_PRECIO = (
    "Sin matriz: el plano sostiene la cantidad, no el precio. "
    "Adopta un P.U. de tu catálogo o de una publicación."
)


# Los que el motor sabe leer del plano. El resto del catálogo de
# instalaciones sigue llenándose por asignación desde el levantamiento.
CODIGOS_CON_REGLA: tuple[str, ...] = tuple(
    code
    for code in CODIGOS
    if code in _MUEBLES_POR_CONCEPTO
    or code in _CORRIDAS_POR_CONCEPTO
    or code in _VANOS_POR_CONCEPTO
)


def _origen(code: str) -> str:
    """De dónde salió la cantidad, dicho en los términos de ese concepto."""
    if code in _VANOS_POR_CONCEPTO:
        return (
            "Cantidad leída del plano: cada puerta, ventana o cancel dibujado, "
            "contado por pieza (la altura viene del cuadro de vanos)"
        )
    if code in _CORRIDAS_POR_CONCEPTO:
        return (
            "Cantidad leída del plano: metros de trazo sobre las capas de este "
            "sistema, por planta"
        )
    if code in _MUEBLES_POR_CONCEPTO:
        return "Cantidad leída del plano: cada símbolo insertado de este tipo, contado"
    return "Cantidad por levantamiento: capas y bloques que alguien asignó a este concepto"


def conceptos_de_instalaciones() -> list[Concept]:
    """Los conceptos para el catálogo por omisión, sin regla y sin matriz."""
    return [
        Concept(
            code=code,
            description=description,
            unit=unit,
            phase=phase,
            rule=_regla(code),
            production_rate_per_day=rate,
            sequence_order=400 + order,
            assumptions=[_origen(code), _SIN_PRECIO],
        )
        for code, description, unit, phase, rate, order in _CONCEPTOS
    ]


# --------------------------------------------------------- biblioteca ------


@dataclass(frozen=True)
class ReglaSugerida:
    """Un nombre de capa o de bloque que casi siempre es cierto concepto.

    ``disciplinas`` acota dónde vale la regla: la disciplina la puso el
    levantamiento al clasificar la hoja, y sin ese filtro «flexible» en una
    hoja de aire acondicionado y «flexible» en cualquier otra cosa se verían
    igual."""

    kind: str  # "run" (metros de capa) | "block" (piezas) | "area"
    patron: str  # regex, sin distinguir mayúsculas
    concepto: str
    razon: str
    disciplinas: tuple[str, ...] = ()
    factor: float = 1.0


# Convenciones que se repiten en planos mexicanos de instalaciones. Cada una
# se propone; ninguna se aplica sola.
SUGERENCIAS: tuple[ReglaSugerida, ...] = (
    # --- Hidráulica: C/H/R PIP = cold / hot / return pipe -----------------
    ReglaSugerida(
        kind="run", patron=r"(^|[-_ ])C\s*PIP|AGUA[ _-]?FRIA|\bA\.?F\.?\b",
        concepto="HID-003", disciplinas=("hidraulica",),
        razon="Capa de tubería de agua fría en la hoja de hidráulica; el desarrollo "
              "dibujado son los metros de tubería.",
    ),
    ReglaSugerida(
        kind="run", patron=r"(^|[-_ ])H\s*PIP|AGUA[ _-]?CALIENTE|\bA\.?C\.?\b",
        concepto="HID-004", disciplinas=("hidraulica",),
        razon="Capa de tubería de agua caliente en la hoja de hidráulica.",
    ),
    ReglaSugerida(
        # "RETORNO" a secas es demasiado ancho: en una hoja de hidráulica con
        # alberca, "SEB - Retorno Filtrado" es el retorno de filtración, no el
        # de agua caliente. Se pide que el nombre diga de qué retorno habla.
        kind="run", patron=r"(^|[-_ ])R\s*PIP|RETORNO[ _-]*(A\.?C\.?|AGUA|CALIENTE)",
        concepto="HID-005", disciplinas=("hidraulica",),
        razon="Capa de retorno de agua caliente en la hoja de hidráulica.",
    ),
    # --- Sanitaria --------------------------------------------------------
    ReglaSugerida(
        kind="run", patron=r"SANITARI",
        concepto="SAN-002", disciplinas=("sanitaria",),
        razon="Capa de albañal sanitario; el desarrollo dibujado son los metros "
              "de tubería.",
    ),
    ReglaSugerida(
        kind="run", patron=r"PLUVIAL|B\.?A\.?P\.?",
        concepto="SAN-003", disciplinas=("sanitaria",),
        razon="Capa de bajadas de aguas pluviales en la hoja de sanitaria.",
    ),
    ReglaSugerida(
        kind="block", patron=r"^DESCSAN|^DESC[ _-]?SAN|DESCARGA",
        concepto="SAN-001", disciplinas=("sanitaria",),
        razon="Bloque de descarga sanitaria: cada inserción es una salida.",
    ),
    ReglaSugerida(
        kind="block", patron=r"^REG(ISTRO)?([ _-]|$)|^RS[ _-]?\d",
        concepto="SAN-004", disciplinas=("sanitaria",),
        razon="Bloque de registro sanitario: cada inserción es una pieza.",
    ),
    # --- Gas --------------------------------------------------------------
    ReglaSugerida(
        kind="run", patron=r"^GAS([ _-]|$)|TUB.*GAS",
        concepto="GAS-001", disciplinas=("gas",),
        razon="Capa de tubería de gas; el desarrollo dibujado son sus metros.",
    ),
    # --- Aire acondicionado ----------------------------------------------
    ReglaSugerida(
        kind="run", patron=r"DUCTO|DUCT\b",
        concepto="AIR-001", disciplinas=("aire",),
        razon="Capa de ducto de lámina. Ojo: el precio real depende de la sección "
              "(las medidas están en las notas de la hoja); esto mide desarrollo.",
    ),
    ReglaSugerida(
        kind="run", patron=r"FLEXIBLE",
        concepto="AIR-002", disciplinas=("aire",),
        razon="Capa de ducto flexible en la hoja de aire acondicionado.",
    ),
    ReglaSugerida(
        kind="run", patron=r"TUBO[ _-]?CU|COBRE|REFRIGERANT",
        concepto="AIR-003", disciplinas=("aire",),
        razon="Capa de tubería de cobre para refrigerante.",
    ),
    ReglaSugerida(
        kind="block", patron=r"^REJ|DIFUSOR|^DL\d|^RI\b|^RR\b",
        concepto="AIR-004", disciplinas=("aire",),
        razon="Bloque de rejilla o difusor: cada inserción es una pieza.",
    ),
    # --- Eléctrica --------------------------------------------------------
    ReglaSugerida(
        kind="block", patron=r"CONTACTO|^C[ _-]?DOBLE|TOMACORR",
        concepto="ELE-001", disciplinas=("electrica",),
        razon="Bloque de contacto: cada inserción es una salida.",
    ),
    ReglaSugerida(
        kind="block", patron=r"APAGADOR|CENTRO[ _-]?LUZ|LUMINARI|^LAMP",
        concepto="ELE-002", disciplinas=("electrica",),
        razon="Bloque de apagador, centro de luz o luminaria: cada inserción es "
              "una salida.",
    ),
    ReglaSugerida(
        kind="run", patron=r"CONDUIT|CANALIZ|^E[ _-]?TUB",
        concepto="ELE-003", disciplinas=("electrica",),
        razon="Capa de canalización eléctrica; el desarrollo dibujado son sus metros.",
    ),
)


@dataclass
class Sugerencia:
    """Un mapeo propuesto, con la cuenta que produciría y de dónde salió."""

    kind: str  # el "kind" que espera inventory_mappings: layer | block
    patron: str  # el nombre exacto de la capa o del bloque, no la regex
    concepto: str
    unidad: str
    cantidad: float
    razon: str
    disciplina: str = ""
    hojas: list[str] = field(default_factory=list)


def ya_detectado(detections: list) -> set[tuple[str, str]]:
    """Las capas y bloques que los detectores ya contaron, como (kind, nombre).

    Una corrida que el motor midió y una asignación del taller sobre la misma
    capa son el mismo metro contado dos veces. El detector manda: midió del
    archivo, con evidencia y con vista. La asignación se salta y se dice."""
    claves: set[tuple[str, str]] = set()
    for d in detections:
        props = getattr(d, "properties", None) or {}
        tipo = str(getattr(d, "detection_type", ""))
        if tipo.endswith("pipe_run") and props.get("layer"):
            claves.add(("layer", _normaliza(str(props["layer"])).lower()))
        elif tipo.endswith("fixture") and props.get("block_name"):
            claves.add(("block", _normaliza(str(props["block_name"])).lower()))
    return claves


def _normaliza(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip())


def sugerir_mapeos(
    inventory: dict | None,
    existentes: list[dict] | None = None,
    codigos_catalogo: set[str] | None = None,
    detectados: set[tuple[str, str]] | None = None,
) -> list[Sugerencia]:
    """Capas y bloques del levantamiento que la biblioteca reconoce.

    Devuelve propuestas ordenadas por cantidad — lo más grande primero, que es
    lo que más dinero mueve. No incluye lo que ya está asignado (la asignación
    del taller manda sobre la biblioteca) ni lo que los detectores ya contaron
    (proponerlo sería invitar a contar el mismo metro dos veces)."""
    if not inventory:
        return []
    ya = {
        (str(m.get("kind") or ""), _normaliza(str(m.get("pattern") or "")).lower())
        for m in (existentes or [])
    } | (detectados or set())
    unidades = {code: unit for code, _d, unit, _f, _r, _o in _CONCEPTOS}
    encontrado: dict[tuple[str, str, str], Sugerencia] = {}

    for sheet in inventory.get("sheets") or []:
        disciplina = str(sheet.get("discipline") or "").lower()
        etiqueta = str(sheet.get("label") or sheet.get("sheet") or "")
        for regla in SUGERENCIAS:
            if regla.disciplinas and disciplina not in regla.disciplinas:
                continue
            if codigos_catalogo is not None and regla.concepto not in codigos_catalogo:
                continue  # el taller borró ese concepto de su catálogo
            patron = re.compile(regla.patron, re.I)
            if regla.kind == "run":
                for run in sheet.get("runs") or []:
                    nombre = _normaliza(str(run.get("layer") or ""))
                    cantidad = float(run.get("length_m") or 0.0)
                    if not nombre or cantidad <= 0 or not patron.search(nombre):
                        continue
                    _acumula(
                        encontrado, "layer", nombre, regla, cantidad * regla.factor,
                        unidades, disciplina, etiqueta,
                    )
            elif regla.kind == "block":
                for bloque in sheet.get("blocks") or []:
                    nombre = _normaliza(str(bloque.get("block_name") or ""))
                    cantidad = float(bloque.get("count") or 0.0)
                    if not nombre or cantidad <= 0 or not patron.search(nombre):
                        continue
                    _acumula(
                        encontrado, "block", nombre, regla, cantidad * regla.factor,
                        unidades, disciplina, etiqueta,
                    )

    salida = [s for key, s in encontrado.items() if (key[0], key[1].lower()) not in ya]
    salida.sort(key=lambda s: (-s.cantidad, s.concepto))
    return salida


def _acumula(
    destino: dict[tuple[str, str, str], Sugerencia],
    kind: str,
    nombre: str,
    regla: ReglaSugerida,
    cantidad: float,
    unidades: dict[str, str],
    disciplina: str,
    hoja: str,
) -> None:
    """El mismo nombre en varias hojas es un solo mapeo: así lo guarda la
    tabla de asignaciones, y así hay que proponerlo."""
    clave = (kind, nombre, regla.concepto)
    actual = destino.get(clave)
    if actual is None:
        destino[clave] = Sugerencia(
            kind=kind,
            patron=nombre,
            concepto=regla.concepto,
            unidad=unidades.get(regla.concepto, ""),
            cantidad=round(cantidad, 2),
            razon=regla.razon,
            disciplina=disciplina,
            hojas=[hoja] if hoja else [],
        )
        return
    actual.cantidad = round(actual.cantidad + cantidad, 2)
    if hoja and hoja not in actual.hojas:
        actual.hojas.append(hoja)
