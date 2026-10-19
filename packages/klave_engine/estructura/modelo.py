"""El modelo estructural de una lectura: las reglas, las definiciones, los elementos y las
verificaciones del propio plano, juntos en ``estructura.json``; las decisiones humanas que
sobreviven a la reprocesada; la tarjeta por familia con lo que está en juego; y lo que el modelo
escribe de vuelta en las detecciones que el presupuesto lee.

**El archivo.** ``estructura.json`` vive junto a los demás artefactos de la corrida. Sus campos
``reglas`` y ``elementos`` son los que lee la etapa del acero (R6: ``compute_steel`` lee
``estructura["reglas"]`` y ``estructura["elementos"]``, con esos nombres). Un archivo escrito
antes de que existieran algunos campos opcionales se lee igual (sus campos faltantes toman su
valor por omisión); uno que no se puede leer no tumba nada: se dice. El recálculo nunca reescribe
la corrida (es inmutable): escribe su escenario derivado en ``estructura_override.json`` del
directorio de control, sellado con la corrida de la que sale (``base``); un escenario de otra
corrida no se toma.

**Las decisiones.** Una decisión (``Decision``) dice el valor de un campo de una marca, por quien
la toma; se guarda por marca y campo en ``estructura_decisiones.json`` del directorio de control
(fuera de las corridas: sobrevive a la reprocesada). Aplicada, es un ``Dato`` ``humano`` en la
definición de la marca (y en cada una de sus variantes): le gana a todo (``elegir``) en todas las
hojas (``para_hoja`` nunca la desplaza, R141), y lo que había queda como su alternativa. Una marca
que el plano coloca sin definir la toma en cada colocación (su verificación 1 sigue: el plano no
la define). Los elementos se vuelven a juntar con las definiciones y las verificaciones se vuelven
a correr, así que el hallazgo que la decisión contesta desaparece y los demás conservan su id
(R229). Aplicar es idempotente: lo que una decisión anterior puso se deshace primero (quitar una
decisión deja el plano como lo lee la lectura). Una decisión cuya marca ya no está en la lectura
es un aviso, nunca un error, y se conserva. Las revisiones de detecciones
(``detection_reviews.json``) son otra cosa y aquí no se tocan.

**Lo que está en juego** (``resumir``). Por familia: cuántas colocaciones, cuántas con la
definición de su marca, cuántos datos críticos y cuántos dice el plano, los hallazgos por
severidad, y el dinero en juego: donde el plano da dos valores de un dato (una contradicción, dos
cortes de una marca), lo que cambia el concreto entre ellos por el P.U. del renglón que tiene la
colocación y lo que cambia el acero (``acero_elemento``) por el P.U. de su renglón de acero; lo que
no tiene precio queda en cantidad.

**La escritura de vuelta** (``escribir_en_detecciones``, diseño §3.5). En E0–E1 el concreto y la
cimbra todavía leen las detecciones: cada elemento escribe en la suya la sección que resolvió
(``section_cm``, ``section_area_du2``; el área de un contorno no rectangular, R142) y el claro que
su definición declara, sólo cuando difiere de lo que la detección ya trae, con su fuente honesta
(un supuesto nunca dice «cuadro») y lo que había en ``seccion_previa`` / ``claro_previo``. Un
supuesto o una lectura IA del modelo nunca tapa una medida de la detección ni llena una detección
sin sección (el presupuesto usa la suya); sólo corrige un valor que el cuadro estampó y el modelo
no eligió. Cuando el concreto y el acero quedan con secciones distintas, se dice."""

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, PrivateAttr, ValidationError, field_validator

from klave_engine.common.io import read_json, write_json
from klave_engine.common.logging import get_logger
from klave_engine.costing.steel import SteelAssumptions
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.schedules import FAMILIAS_QUE_SE_ORDENAN, ScheduleInventory
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.acero import acero_elemento
from klave_engine.estructura.armado import (
    FAMILIAS_CON_PARRILLA,
    GrupoVarillas,
    JuegoEstribos,
    Parrilla,
    parsear_armado,
)
from klave_engine.estructura.dato import Dato, elegir
from klave_engine.estructura.definiciones import (
    Definicion,
    construir_definiciones,
    normalizar_marca,
)
from klave_engine.estructura.elementos import (
    FAMILIAS_ESTRUCTURALES,
    Elemento,
    construir_elementos,
    resolver_todos,
)
from klave_engine.estructura.reglas import Reglas, leer_reglas
from klave_engine.estructura.verificaciones import (
    CRITICOS,
    Verificacion,
    valores_en_disputa,
    verificar,
    volumen,
)

logger = get_logger(__name__)

ESTRUCTURA_FILENAME = "estructura.json"
DECISIONES_FILENAME = "estructura_decisiones.json"
# El escenario derivado del recálculo (como ``cost_report_override.json``): en el directorio de
# control, sellado con la corrida de la que sale.
ESTRUCTURA_DERIVADA_FILENAME = "estructura_override.json"
VERSION = 1

CampoDecidible = Literal["seccion_cm", "longitud_m", "longitudinales", "estribos", "parrillas"]
CAMPOS_DECIDIBLES: tuple[str, ...] = get_args(CampoDecidible)
_NOMBRE_DEL_CAMPO = {
    "seccion_cm": "sección",
    "longitud_m": "longitud",
    "longitudinales": "varillas longitudinales",
    "estribos": "estribos",
    "parrillas": "parrillas",
}
# Lo que dice un aviso de decisión (se rehace en cada aplicación: aplicar es idempotente).
_DE_DECISION = "Decisión"
_ALTURA_SIN_NIVELES = "el plano no declara los niveles de su planta"
# Las fuentes que leen el plano: lo que cuenta como «del plano» en la tarjeta (ni la IA, ni el
# supuesto, ni la regla de Klave; la decisión humana se cuenta aparte).
_DEL_PLANO = frozenset({"cuadro", "detalle", "seccion_dibujada", "nota", "medido"})


class Decision(BaseModel):
    """El valor que alguien decide para un campo de una marca (definición: vale para todas sus
    colocaciones). ``valor``: la sección ``[b, h]`` en cm (o ``{"area_cm2": …}``), la longitud
    en m, o el armado como texto («4#5+2#4», «2E#3@15», «LS #4@20 A/S») o como la lista de sus
    piezas."""

    marca: str
    campo: CampoDecidible
    valor: Any
    nota: str = ""
    actor: str = ""
    fecha: datetime
    # R239: en una marca con variantes por muro, la variante que decide (el espesor del muro, cm);
    # sin él, la decisión sólo vale para las colocaciones cuya variante no se resolvió.
    para_muro_cm: float | None = None

    @field_validator("fecha")
    @classmethod
    def _en_utc(cls, fecha: datetime) -> datetime:
        """R238: toda fecha en UTC (una sin zona se toma como UTC): así se comparan siempre."""
        if fecha.tzinfo is None:
            return fecha.replace(tzinfo=UTC)
        return fecha.astimezone(UTC)


class ResumenFamilia(BaseModel):
    """La tarjeta de una familia.

    Cada hallazgo está en una sola tarjeta (R240): la de la familia de la mayoría de sus
    elementos, si no la de sus marcas (su definición o el prefijo), si no «general».

    ``con_definicion``: colocaciones juntadas con la definición de su propia marca (la de la
    familia no cuenta: su marca sigue sin definir). ``criticos_del_plano``: datos críticos
    (``CRITICOS``) que da el plano: ni supuesto, ni IA, ni regla; los que decidió alguien van en
    ``criticos_humanos``. Lo que está en juego es lo que cambia entre dos valores que el plano da
    para un dato (una contradicción, dos cortes), en las colocaciones que el presupuesto cuenta:
    ``en_juego_cantidad`` (``concreto_m3``, ``acero_kg``), con precio o sin él;
    ``en_juego_sin_precio``, la parte sin precio; ``en_juego_mxn``, el dinero de la parte con
    precio. ``en_juego_mxn`` es ``None`` —nunca $0— si hay un hallazgo abierto (bloquea o duda)
    cuya cantidad en juego no tiene cifra (``en_juego_desconocido`` dice cuántos) o si lo que hay
    en juego no tiene precio; 0.0 sólo si no hay nada abierto. ``en_juego_fuera_del_presupuesto``:
    lo que cambia en colocaciones que ningún renglón cuenta (dicho aparte, no sumado).
    ``en_juego_mxn_conocido``: el dinero de la parte con precio de lo que está en juego, siempre
    (0.0 si no hay); con ``en_juego_mxn`` en ``None`` por un hallazgo sin cifra o por una parte sin
    precio, lo que sí tiene precio no se esconde: es el piso de lo que está en juego, no el total.
    ``en_juego_aparte``: lo que pone en juego un hallazgo cuyos valores no son de un elemento (los
    entrepisos contados de dos maneras), por su id: aparece igual en cada tarjeta que toca, así
    que es compartido por id y nunca se suma entre tarjetas."""

    familia: str
    colocaciones: int
    con_definicion: int
    criticos_total: int
    criticos_del_plano: int
    bloquea: int
    duda: int
    aviso: int
    en_juego_mxn: float | None
    en_juego_cantidad: dict[str, float] = Field(default_factory=dict)
    criticos_humanos: int = 0
    en_juego_sin_precio: dict[str, float] = Field(default_factory=dict)
    en_juego_aparte: dict[str, dict[str, float]] = Field(default_factory=dict)
    en_juego_desconocido: int = 0
    en_juego_fuera_del_presupuesto: dict[str, float] = Field(default_factory=dict)
    en_juego_mxn_conocido: float = 0.0


class Escritura(BaseModel):
    """Lo que el modelo escribió en una detección (o le corrigió la fuente)."""

    detection_id: str
    marca: str
    familia: str
    hoja: str
    # ``claro``: el de una viga; ``longitud_m``: la de un pilote (lo que mide CIM-011).
    campo: Literal["seccion", "fuente", "claro", "armado", "longitud_m"]
    antes: str | None
    fuente_antes: str | None
    despues: str
    fuente: str
    texto: str = ""


@dataclass
class ContextoDelPlano:
    """Lo que las verificaciones leen del dibujo además del modelo (para volver a correrlas
    después de una decisión)."""

    entities: list[NormalizedEntity]
    inv: ScheduleInventory
    detections: list[Detection]
    segmentation: SheetSegmentation | None
    meters_factor: float | None


class Estructura(BaseModel):
    """El modelo estructural de una lectura (ver el docstring del módulo). ``reglas`` y
    ``elementos`` NO se renombran (R6). ``decisiones``: las vigentes que se le aplicaron (también
    las que no encontraron su marca, que ``avisos`` dice); ``escrituras``: lo que escribió en las
    detecciones; ``marcos``: los de la corrida (las hojas de cimentación, R144: con ellos se vuelve
    a juntar un elemento); ``altura_supuesta_m``: la de los castillos y columnas cuya planta no
    declara niveles; ``base``: en un escenario derivado, la huella de la corrida de la que sale."""

    version: int = VERSION
    reglas: Reglas
    definiciones: list[Definicion] = Field(default_factory=list)
    por_familia: list[Definicion] = Field(default_factory=list)
    elementos: list[Elemento] = Field(default_factory=list)
    verificaciones: list[Verificacion] = Field(default_factory=list)
    resumen: list[ResumenFamilia] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    decisiones: list[Decision] = Field(default_factory=list)
    escrituras: list[Escritura] = Field(default_factory=list)
    marcos: list[SheetFrame] = Field(default_factory=list)
    patrones: TextPatternConfig = Field(default_factory=TextPatternConfig)
    altura_supuesta_m: float | None = None
    base: str = ""
    _contexto: ContextoDelPlano | None = PrivateAttr(default=None)

    def para_el_costo(self) -> dict[str, Any]:
        """Lo que la etapa de costo lee (R6), sin volcar ni volver a validar: las reglas y los
        elementos tal cual."""
        return {"reglas": self.reglas, "elementos": self.elementos}


# -------------------------------------------------------------------------------- construir


def construir_estructura(
    entities: list[NormalizedEntity],
    frames: list[SheetFrame],
    inv: ScheduleInventory,
    detections: list[Detection],
    segmentation: SheetSegmentation | None,
    meters_factor: float | None,
    altura_supuesta_m: float,
    *,
    config: TextPatternConfig | None = None,
    decisiones: list[Decision] | None = None,
) -> Estructura:
    """Las reglas del plano (``leer_reglas``), las definiciones (``construir_definiciones``), los
    elementos (``construir_elementos``, con ``altura_supuesta_m`` para los castillos y columnas
    de una planta sin niveles) y las verificaciones (``verificar``), con las ``decisiones``
    aplicadas (``aplicar_decisiones``; las verificaciones se corren una sola vez).

    Las formas de los estribos las supone la etapa del acero por elemento (``acero_elemento`` →
    ``asignar_formas``, con las varillas de cada uno): escribirlas aquí en el ``Dato`` de la
    definición separaría lecturas iguales en valores distintos y ``elegir`` vería conflictos que
    el plano no tiene."""
    config = config or TextPatternConfig()
    reglas = leer_reglas(entities, frames)
    por_marca, por_familia = construir_definiciones(inv, config)
    elementos = construir_elementos(
        detections,
        segmentation,
        por_marca,
        por_familia,
        reglas,
        meters_factor,
        altura_supuesta_m,
        frames=frames,
        config=config,
    )
    contexto = ContextoDelPlano(entities, inv, detections, segmentation, meters_factor)
    estructura = Estructura(
        reglas=reglas,
        definiciones=list(por_marca.values()),
        por_familia=list(por_familia.values()),
        elementos=elementos,
        marcos=list(frames),
        patrones=config,
        altura_supuesta_m=altura_supuesta_m,
    )
    estructura._contexto = contexto
    if decisiones and _vigentes(decisiones, config):
        return aplicar_decisiones(estructura, decisiones)  # vuelve a juntar y verifica
    estructura.verificaciones = _verificar(
        por_marca, por_familia, elementos, reglas, frames, config, contexto
    )
    return estructura


def _verificar(
    por_marca: dict[str, Definicion],
    por_familia: dict[str, Definicion],
    elementos: list[Elemento],
    reglas: Reglas,
    frames: list[SheetFrame],
    config: TextPatternConfig,
    contexto: ContextoDelPlano,
) -> list[Verificacion]:
    a = SteelAssumptions()
    return verificar(
        por_marca,
        por_familia,
        elementos,
        reglas,
        contexto.inv,
        contexto.entities,
        contexto.detections,
        contexto.segmentation,
        frames=frames,
        config=config,
        anclaje_m=a.anchorage_m,
        desperdicio=a.waste_pct / 100,
        meters_factor=contexto.meters_factor,
    )


def con_contexto(e: Estructura, contexto: ContextoDelPlano | None) -> Estructura:
    """``e`` con lo que sus verificaciones leen del dibujo (para volver a correrlas)."""
    e._contexto = contexto
    return e


def cargar_contexto(processed: Path) -> ContextoDelPlano | None:
    """Lo que las verificaciones leen del dibujo, de los artefactos de una corrida; ``None`` si
    falta alguno (una corrida vieja o incompleta)."""
    nombres = (
        "normalized_entities.json",
        "schedules.json",
        "detections.json",
        "drawing_units.json",
    )
    if not all((processed / n).exists() for n in nombres):
        return None
    from klave_engine.dxf.units import DrawingUnits

    try:
        vistas = processed / "views.json"
        return ContextoDelPlano(
            entities=[
                NormalizedEntity.model_validate(x)
                for x in read_json(processed / "normalized_entities.json")
            ],
            inv=ScheduleInventory.model_validate(read_json(processed / "schedules.json")),
            detections=[
                Detection.model_validate(x) for x in read_json(processed / "detections.json")
            ],
            segmentation=SheetSegmentation.model_validate(read_json(vistas))
            if vistas.exists()
            else None,
            meters_factor=DrawingUnits.model_validate(
                read_json(processed / "drawing_units.json")
            ).to_meters(),
        )
    except (OSError, ValueError, ValidationError) as error:
        logger.warning("No se pudo leer el contexto del plano de %s: %s", processed, error)
        return None


# ------------------------------------------------------------------------------ el archivo


def escribir_estructura(processed: Path, e: Estructura) -> None:
    write_json(processed / ESTRUCTURA_FILENAME, e)


def leer_estructura(processed: Path) -> Estructura | None:
    """El modelo de una corrida; ``None`` si la corrida no lo tiene (una corrida anterior al
    modelo) o no se puede leer (``leer_estructura_con_motivo`` dice por qué)."""
    return leer_estructura_con_motivo(processed)[0]


def leer_estructura_con_motivo(processed: Path) -> tuple[Estructura | None, str | None]:
    """(el modelo, ``None``) o (``None``, por qué no se pudo leer); (``None``, ``None``) si la
    corrida no tiene ``estructura.json``. Los campos opcionales que falten (un archivo escrito
    antes de que existieran) toman su valor por omisión."""
    return _leer(processed / ESTRUCTURA_FILENAME)


def _leer(ruta: Path) -> tuple[Estructura | None, str | None]:
    if not ruta.exists():
        return None, None
    try:
        return Estructura.model_validate(read_json(ruta)), None
    except (OSError, ValueError, ValidationError) as error:
        primera = str(error).splitlines()[0][:200]
        return None, f"{ruta.name} no se pudo leer ({primera})"


def huella(processed: Path) -> str:
    """La huella del ``estructura.json`` de una corrida (vacío si no lo tiene)."""
    ruta = processed / ESTRUCTURA_FILENAME
    if not ruta.exists():
        return ""
    return hashlib.sha1(ruta.read_bytes()).hexdigest()[:16]


def escribir_estructura_derivada(control_dir: Path, corrida: Path, e: Estructura) -> None:
    """El escenario del recálculo: en el directorio de control, sellado con la corrida."""
    e.base = huella(corrida)
    write_json(control_dir / ESTRUCTURA_DERIVADA_FILENAME, e)


def leer_estructura_vigente(control_dir: Path, corrida: Path) -> Estructura | None:
    """El modelo que vale para la corrida activa: el escenario del recálculo si es de ella y está
    al día con las decisiones guardadas, si no el de la corrida. Si ése tampoco lo está (se
    guardó o se quitó una decisión y no se ha recalculado), lo dice en sus avisos."""
    decisiones = cargar_decisiones(control_dir)
    derivada, _ = _leer(control_dir / ESTRUCTURA_DERIVADA_FILENAME)
    if (
        derivada is not None
        and derivada.base
        and derivada.base == huella(corrida)
        and _vigentes(decisiones, derivada.patrones) == derivada.decisiones
    ):
        return derivada
    e = leer_estructura(corrida)
    if e is not None and _vigentes(decisiones, e.patrones) != e.decisiones:
        e.avisos.append(
            f"{_DE_DECISION}: las decisiones guardadas cambiaron desde este modelo; se aplican al "
            "recalcular"
        )
    return e


def estructura_para_recalcular(
    corrida: Path,
    control_dir: Path,
    segmentation: SheetSegmentation | None,
    column_height_m: float,
) -> tuple[Estructura | None, list[str]]:
    """El modelo con que se recalcula una corrida, y los avisos: el de la corrida con las
    decisiones guardadas ahora y la altura supuesta de ahora (si nada cambió desde que se
    escribió, tal cual: un cambio de precio no rehace nada). Una corrida anterior al modelo no
    tiene: su acero sigue por el camino con que se costeó (nada se mueve sin reprocesar). Un
    ``estructura.json`` que no se puede leer se rehace con los artefactos de la corrida, si están;
    si no, sin modelo, y se dice."""
    from klave_engine.costing.steel import altura_supuesta_m

    base, motivo = leer_estructura_con_motivo(corrida)
    decisiones, avisos = leer_decisiones(control_dir)
    if base is None and motivo is None:
        if decisiones:
            avisos.append(
                f"{_DE_DECISION}: esta lectura es anterior al modelo estructural; las "
                f"{len(decisiones)} decisiones guardadas se aplican al reprocesar"
            )
        return None, avisos
    contexto: ContextoDelPlano | None = None
    if base is None:
        contexto = cargar_contexto(corrida)
        marcos_ruta = corrida / "frames.json"
        if contexto is None or not marcos_ruta.exists():
            avisos.append(
                f"Modelo estructural: {motivo}; faltan los artefactos de la corrida para "
                "rehacerlo, así que el acero se calcula sin él. Reprocesa el proyecto."
            )
            return None, avisos
        marcos = [SheetFrame.model_validate(f) for f in read_json(marcos_ruta)]
        base = construir_estructura(
            contexto.entities,
            marcos,
            contexto.inv,
            contexto.detections,
            contexto.segmentation,
            contexto.meters_factor,
            altura_supuesta_m(contexto.segmentation, column_height_m),
            decisiones=decisiones,
        )
        avisos.append(f"Modelo estructural: {motivo}; se rehízo con los artefactos de la corrida.")
    altura = altura_supuesta_m(segmentation, column_height_m)
    vigentes = _vigentes(decisiones, base.patrones)

    def al_dia(e: Estructura) -> bool:
        return vigentes == e.decisiones and (
            e.altura_supuesta_m is None or altura == e.altura_supuesta_m
        )

    if not al_dia(base):
        derivada, _ = _leer(control_dir / ESTRUCTURA_DERIVADA_FILENAME)
        if (
            motivo is None
            and derivada is not None
            and derivada.base
            and derivada.base == huella(corrida)
            and al_dia(derivada)
        ):
            base = derivada  # el escenario que un recálculo anterior ya hizo, todavía al día
        else:
            contexto = contexto or base._contexto or cargar_contexto(corrida)
            base = aplicar_decisiones(base, decisiones, contexto=contexto, altura_supuesta_m=altura)
    avisos += [a for a in base.avisos if a.startswith(_DE_DECISION)]
    return base, list(dict.fromkeys(avisos))


# ------------------------------------------------------------------------------ decisiones


def leer_decisiones(control_dir: Path) -> tuple[list[Decision], list[str]]:
    """Las decisiones guardadas y los avisos de las que no se pudieron leer (nunca un error: una
    decisión ilegible se dice y se conserva en el archivo)."""
    ruta = control_dir / DECISIONES_FILENAME
    if not ruta.exists():
        return [], []
    try:
        crudas = read_json(ruta)
    except (OSError, ValueError) as error:
        return [], [f"{_DE_DECISION}: {DECISIONES_FILENAME} no se pudo leer ({error}); no se "
                    "aplica ninguna decisión"]  # fmt: skip
    if not isinstance(crudas, list):
        return [], [f"{_DE_DECISION}: {DECISIONES_FILENAME} no es una lista; no se aplica"]
    salida: list[Decision] = []
    avisos: list[str] = []
    for i, cruda in enumerate(crudas):
        try:
            salida.append(Decision.model_validate(cruda))
        except ValidationError as error:
            avisos.append(
                f"{_DE_DECISION} {i + 1} de {DECISIONES_FILENAME} no se pudo leer "
                f"({str(error).splitlines()[0][:120]}); no se aplica"
            )
    return salida, avisos


def cargar_decisiones(control_dir: Path) -> list[Decision]:
    return leer_decisiones(control_dir)[0]


def guardar_decision(control_dir: Path, d: Decision) -> None:
    """Guarda ``d``; reemplaza la que había para la misma marca y campo (el registro de etiquetas
    guarda la historia). Las entradas que no se pueden leer se conservan tal cual."""
    ruta = control_dir / DECISIONES_FILENAME
    crudas: list[Any] = []
    if ruta.exists():
        try:
            leidas = read_json(ruta)
            crudas = leidas if isinstance(leidas, list) else []
        except (OSError, ValueError):
            crudas = []
    llave = _llave(d.marca, d.campo, d.para_muro_cm)
    conservadas = [
        c
        for c in crudas
        if not (
            isinstance(c, dict)
            and _llave(str(c.get("marca", "")), str(c.get("campo", "")), c.get("para_muro_cm"))
            == llave
        )
    ]
    write_json(ruta, [*conservadas, d.model_dump(mode="json")])
    # El escenario del recálculo ya no está al día: se rehace en el próximo recálculo.
    (control_dir / ESTRUCTURA_DERIVADA_FILENAME).unlink(missing_ok=True)


def _llave(
    marca: str, campo: str, para_muro_cm: Any = None, config: TextPatternConfig | None = None
) -> tuple[str, str, float | None]:
    """La llave de una decisión: su marca normalizada, su campo y (R239) su variante."""
    muro = _numero(para_muro_cm) if para_muro_cm is not None else None
    return (normalizar_marca(marca, config) if marca.strip() else "", campo, muro)


def _vigentes(decisiones: list[Decision], config: TextPatternConfig) -> list[Decision]:
    """Una por marca, campo y variante: la más reciente."""
    por_llave: dict[tuple[str, str, float | None], Decision] = {}
    for d in sorted(decisiones, key=lambda x: x.fecha):
        por_llave[_llave(d.marca, d.campo, d.para_muro_cm, config)] = d
    return list(por_llave.values())


def aplicar_decisiones(
    e: Estructura,
    decisiones: list[Decision],
    *,
    contexto: ContextoDelPlano | None = None,
    altura_supuesta_m: float | None = None,
) -> Estructura:
    """``e`` con las decisiones vigentes (una por marca y campo, la más reciente): lo que una
    decisión anterior puso se deshace, cada decisión es un ``Dato`` ``humano`` en la definición
    de su marca (y sus variantes) o, si el plano coloca la marca sin definirla, en cada colocación;
    los elementos se vuelven a juntar y las verificaciones se vuelven a correr (con ``contexto``,
    o el que ``e`` trae; sin ninguno se conservan las de la lectura y se dice). Una decisión cuya
    marca ya no está, o cuyo valor no se puede usar, es un aviso. ``altura_supuesta_m``: la altura
    de los castillos y columnas sin niveles, si cambió (los supuestos de Klave, R73). Devuelve una
    copia."""
    ctx = contexto if contexto is not None else e._contexto
    vigentes = _vigentes(decisiones, e.patrones)
    altura_cambia = altura_supuesta_m is not None and altura_supuesta_m != e.altura_supuesta_m
    if not vigentes and not e.decisiones and not altura_cambia:
        return e  # nada que deshacer ni que aplicar: el modelo es el de la lectura
    # Sólo se copia lo que se cambia: las definiciones (se les ponen y quitan decisiones); los
    # elementos se vuelven a juntar (nuevos) y lo demás se lee.
    salida = e.model_copy(
        update={
            "definiciones": [d.model_copy(deep=True) for d in e.definiciones],
            "elementos": list(e.elementos),
            "verificaciones": list(e.verificaciones),
            "avisos": list(e.avisos),
        }
    )
    config = salida.patrones
    avisos = [a for a in salida.avisos if not a.startswith(_DE_DECISION)]
    por_marca = {d.marca: d for d in salida.definiciones}
    por_familia = {d.familia: d for d in salida.por_familia}
    for definida in por_marca.values():
        for parte in (definida, *definida.variantes):
            _deshacer(parte)
    en_colocaciones: dict[str, dict[str, Dato]] = {}
    con_variante: dict[tuple[str, str], list[Decision]] = {}
    for d in vigentes:
        marca = normalizar_marca(d.marca, config) if d.marca.strip() else ""
        nombre = _NOMBRE_DEL_CAMPO[d.campo]
        definicion = por_marca.get(marca)
        colocadas = [x for x in salida.elementos if marca and x.marca == marca]
        if definicion is None and not colocadas:
            avisos.append(
                f"{_DE_DECISION} sobre {d.marca or '(sin marca)'} ({nombre}"
                + (f", {d.actor}" if d.actor else "")
                + "): la marca ya no está en esta lectura (ni definida ni colocada); se "
                "conserva y no se aplica"
            )
            continue
        familia = definicion.familia if definicion is not None else colocadas[0].familia
        quien = f"{_DE_DECISION} sobre {marca} ({nombre})"
        try:
            valor = _valor_de_decision(d.campo, d.valor, familia)
            _se_puede_decidir(d, familia, colocadas, definicion)
        except ValueError as error:
            avisos.append(f"{quien}: {error}; no se aplica")
            continue
        humano = Dato(valor=valor, fuente="humano", texto=_texto_de_decision(d))
        if definicion is None:
            en_colocaciones.setdefault(marca, {})[d.campo] = humano
            continue
        if d.para_muro_cm is not None:
            # R239: la variante que la decisión nombra, y sólo ella.
            variante = next(
                (
                    v
                    for v in definicion.variantes
                    if v.para_muro_cm is not None
                    and abs(v.para_muro_cm - d.para_muro_cm) <= _TOLERANCIA_DE_MURO_CM
                ),
                None,
            )
            if variante is None:
                avisos.append(
                    f"{quien}: {marca} no tiene una variante para muros de "
                    f"{_cm(d.para_muro_cm)} cm; no se aplica"
                )
                continue
            setattr(variante, d.campo, _decidido(humano, getattr(variante, d.campo)))
            con_variante.setdefault((marca, d.campo), []).append(d)
        else:
            # R239: en una marca con variantes, sólo para las colocaciones cuya variante no se
            # resolvió (las demás conservan la de su muro); sin variantes, para todas.
            setattr(definicion, d.campo, _decidido(humano, getattr(definicion, d.campo)))
            if definicion.variantes:
                con_variante.setdefault((marca, d.campo), []).append(d)
    if altura_supuesta_m is not None and altura_cambia:
        nueva = Dato(
            valor=altura_supuesta_m,
            fuente="supuesto",
            texto=f"{_ALTURA_SIN_NIVELES}: altura supuesta {altura_supuesta_m:g} m",
        )
        salida.elementos = [
            x.model_copy(update={"colocacion": x.colocacion.model_copy(update={"altura_m": nueva})})
            if _sin_niveles(x)
            else x
            for x in salida.elementos
        ]
        salida.altura_supuesta_m = altura_supuesta_m
    elementos = resolver_todos(
        salida.elementos, por_marca, por_familia, salida.reglas, frames=salida.marcos
    )
    for i, x in enumerate(elementos):
        for campo, humano in en_colocaciones.get(x.marca, {}).items():
            destino = "altura_m" if campo == "longitud_m" and x.familia in _CON_ALTURA else campo
            elementos[i] = x = x.model_copy(
                update={destino: _decidido(humano, getattr(x, destino))}
            )
    for (marca, campo), ds in sorted(con_variante.items()):
        # R239: qué colocaciones tomaron la decisión de una marca con variantes, dicho.
        destino = "altura_m" if campo == "longitud_m" else campo
        suyas = [x for x in elementos if x.marca == marca]
        tomaron = [x for x in suyas if (getattr(x, destino) or Dato(fuente="supuesto")).fuente
                   == "humano"]  # fmt: skip
        cuenta = Counter(x.hoja for x in tomaron)
        donde = ", ".join(f"{h} ({n})" for h, n in sorted(cuenta.items())) or "ninguna"
        cuales = " y ".join(
            f"la de la variante para muros de {_cm(d.para_muro_cm)} cm"
            if d.para_muro_cm is not None
            else "la de la marca (sólo donde la variante por muro no se resolvió)"
            for d in ds
        )
        avisos.append(
            f"{_DE_DECISION} sobre {marca} ({_NOMBRE_DEL_CAMPO[campo]}, {cuales}): la toman "
            f"{_pzas(len(tomaron))} de {len(suyas)} ({donde}); las demás conservan la de su muro"
        )
    salida.definiciones = list(por_marca.values())
    salida.elementos = elementos
    salida.decisiones = vigentes
    if ctx is not None:
        salida.verificaciones = _verificar(
            por_marca, por_familia, elementos, salida.reglas, salida.marcos, config, ctx
        )
        salida._contexto = ctx
    elif vigentes or e.decisiones:
        avisos.append(
            f"{_DE_DECISION}: las verificaciones son las de la lectura; no se volvieron a correr "
            "con las decisiones porque faltan los artefactos de la corrida (sus textos)"
        )
    salida.avisos = list(dict.fromkeys(avisos))
    return salida


_CON_ALTURA = frozenset({"castillo", "columna"})


def _sin_niveles(x: Elemento) -> bool:
    """Si la altura de la planta de ``x`` es la supuesta porque el plano no declara niveles."""
    alto = x.colocacion.altura_m
    return (
        alto is not None
        and alto.fuente == "supuesto"
        and alto.texto.startswith(_ALTURA_SIN_NIVELES)
    )


def _deshacer(definicion: Definicion) -> None:
    """Quita lo que una decisión puso: el ``Dato`` ``humano`` vuelve a ser lo que había (su
    primera alternativa, como la deja ``_decidido``), o nada."""
    for campo in CAMPOS_DECIDIBLES:
        dato = getattr(definicion, campo)
        if dato is not None and dato.fuente == "humano":
            setattr(definicion, campo, dato.alternativas[0] if dato.alternativas else None)


def _decidido(humano: Dato, previo: Dato | None) -> Dato:
    """La decisión elegida sobre lo que había: ``elegir`` (``humano`` gana a todo) deja lo que había
    como su única alternativa, intacto."""
    elegido = elegir([humano] + ([previo] if previo is not None else []))
    assert elegido is not None
    return elegido


def _texto_de_decision(d: Decision) -> str:
    quien = d.actor or "alguien"
    nota = f": {d.nota}" if d.nota else ""
    return f"decidido por {quien} el {d.fecha.date().isoformat()}{nota}"


# R168: el espesor de muro de una variante coincide con éste de holgura (cm), como en elementos.
_TOLERANCIA_DE_MURO_CM = 2.0


def _se_puede_decidir(
    d: Decision, familia: str, colocadas: list[Elemento], definicion: Definicion | None
) -> None:
    """``ValueError`` con por qué no se aplica una decisión que concreto y acero no pueden tomar
    igual (R237): la altura de un castillo o una columna (el concreto se mide por entrepiso,
    E1), una longitud de marca para vigas cuyos claros medidos no son iguales, una variante en
    una marca sin variantes."""
    if d.campo == "longitud_m" and familia in _CON_ALTURA:
        raise ValueError(f"la altura de un {familia} se decide por entrepiso (pendiente)")
    if d.campo == "longitud_m" and familia in _VIGAS:
        claros = sorted(
            {
                round(float(x.colocacion.longitud_m.valor), 2)
                for x in colocadas
                if x.colocacion.longitud_m is not None
                and _numero(x.colocacion.longitud_m.valor) is not None
            }
        )
        if len(claros) > 1 and claros[-1] - claros[0] > _TOLERANCIA_CLARO_M:
            medidos = ", ".join(f"{c:g} m" for c in claros[:8])
            raise ValueError(
                f"sus colocaciones miden claros distintos ({medidos}); una longitud para toda la "
                "marca no vale para todas"
            )
    if d.para_muro_cm is not None and (definicion is None or not definicion.variantes):
        raise ValueError("la marca no tiene variantes por muro")


def _numero(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _valor_de_decision(campo: str, valor: Any, familia: str) -> Any:
    """El valor de una decisión en la forma del modelo, o ``ValueError`` con por qué no sirve."""
    if campo == "seccion_cm":
        if isinstance(valor, dict):
            area = _numero(valor.get("area_cm2"))
            if area is None or area <= 0:
                raise ValueError(f"el área de la sección no es un número positivo ({valor!r})")
            return {"area_cm2": area}
        lados = valor.lower().split("x") if isinstance(valor, str) else valor
        if not isinstance(lados, list | tuple) or len(lados) != 2:
            raise ValueError(f"la sección no es b×h en cm ({valor!r})")
        b, h = (_numero(x) for x in lados)
        if b is None or h is None or b <= 0 or h <= 0:
            raise ValueError(f"la sección no es b×h en cm ({valor!r})")
        par = [int(x) if float(x).is_integer() else x for x in (b, h)]
        return sorted(par) if familia in FAMILIAS_QUE_SE_ORDENAN else par
    if campo == "longitud_m":
        largo = _numero(valor)
        if largo is None or largo <= 0:
            raise ValueError(f"la longitud no es un número positivo de metros ({valor!r})")
        return largo
    if campo == "parrillas" and familia not in FAMILIAS_CON_PARRILLA:
        raise ValueError(f"la familia {familia} no lleva parrillas")
    if isinstance(valor, str):
        armado = parsear_armado([valor], familia)
        if armado.avisos:
            raise ValueError(f"«{valor}» no se lee entero ({'; '.join(armado.avisos)})")
        piezas = getattr(armado, campo)
        if not piezas:
            raise ValueError(f"«{valor}» no dice {_NOMBRE_DEL_CAMPO[campo]}")
        return [p.model_dump(mode="json") for p in piezas]
    if isinstance(valor, list):
        tipos: dict[str, type[BaseModel]] = {
            "longitudinales": GrupoVarillas,
            "estribos": JuegoEstribos,
            "parrillas": Parrilla,
        }
        modelo = tipos[campo]
        try:
            piezas_ = [modelo.model_validate(p) for p in valor]
        except ValidationError as error:
            raise ValueError(f"las piezas no se leen ({str(error).splitlines()[0]})") from None
        if campo == "longitudinales" and not piezas_:
            raise ValueError("un elemento sin varillas longitudinales no se decide así")
        return [p.model_dump(mode="json") for p in piezas_]
    raise ValueError(f"el valor no es un armado ({valor!r})")


# ------------------------------------------------------------------------- la escritura


_CON_ESCRITURA = frozenset({"castillo", "columna", "trabe", "contratrabe", "dala", "cerramiento"})
_VIGAS = frozenset({"trabe", "contratrabe", "dala", "cerramiento"})
# Lo que un cuadro estampó (``apply_schedule``) en una detección: lo puede corregir el modelo.
_DEL_CUADRO = frozenset({"cuadro", "supuesto"})
_TOLERANCIA_CM = 0.05
_TOLERANCIA_AREA = 0.005  # relativa
_TOLERANCIA_CLARO_M = 0.005


def _lados(texto: Any) -> tuple[float, float] | None:
    if not isinstance(texto, str) or "x" not in texto.lower():
        return None
    try:
        a, b = (float(v) for v in texto.lower().split("x"))
    except ValueError:
        return None
    return (a, b) if a > 0 and b > 0 else None


def _cm(v: float) -> str:
    return f"{v:g}"


def _seccion_texto(valor: Any) -> str:
    if isinstance(valor, dict):
        return f"{_cm(float(valor['area_cm2']))} cm²"
    return f"{_cm(float(valor[0]))}x{_cm(float(valor[1]))}"


def _iguales(familia: str, modelo: Any, props: dict, factor: float) -> bool:
    """Si la detección ya trae la sección del modelo (con el mismo orden de lados en una viga; en
    un castillo o una columna el orden no cambia nada)."""
    actual = _lados(props.get("section_cm"))
    if isinstance(modelo, dict):
        if actual is not None:
            return False
        du2 = props.get("section_area_du2")
        area = float(modelo["area_cm2"])
        if not isinstance(du2, int | float) or du2 <= 0:
            return False
        return abs(float(du2) * factor * factor * 10_000 - area) <= _TOLERANCIA_AREA * area
    if actual is None:
        return False
    b, h = float(modelo[0]), float(modelo[1])
    if familia in FAMILIAS_QUE_SE_ORDENAN:
        return all(
            abs(x - y) <= _TOLERANCIA_CM
            for x, y in zip(sorted(actual), sorted((b, h)), strict=True)
        )
    return abs(actual[0] - b) <= _TOLERANCIA_CM and abs(actual[1] - h) <= _TOLERANCIA_CM


def escribir_en_detecciones(
    detections: list[Detection], elementos: list[Elemento], meters_factor: float | None
) -> tuple[list[Detection], list[Escritura]]:
    """(las detecciones con lo que el modelo resolvió escrito en ellas, lo escrito). Es una
    función pura de (la detección del detector, el modelo) (R235): lo que una escritura anterior
    dejó en una detección (``seccion_previa``, ``claro_previo``, ``longitud_previa``: una
    corrida que lo guardó en ``detections.json``) se restaura primero, así que quitar una decisión
    deja la detección como la leyó el detector. Las detecciones que cambian son copias; las demás,
    las mismas. Ver el docstring del módulo. Sin unidades confiables no se escribe nada (el
    presupuesto no tiene precio)."""
    por_id = {e.detection_id: e for e in elementos}
    salida: list[Detection] = []
    escritas: list[Escritura] = []
    for det in detections:
        props = dict(det.properties or {})
        restaurada = _restaurar(props)
        e = por_id.get(det.detection_id)
        cambios: list[Escritura] = []
        notas: list[str] = []
        if e is not None and meters_factor:
            if e.familia in _CON_ESCRITURA and det.detection_type in (
                DetectionType.column_tag,
                DetectionType.beam_tag,
            ):
                _escribir_seccion(det, e, props, meters_factor, cambios, notas)
                _escribir_claro(det, e, props, meters_factor, cambios, notas)
            elif e.familia == "pilote" and det.detection_type == DetectionType.pile:
                _escribir_largo_de_pilote(det, e, props, cambios, notas)
        if cambios or restaurada:
            nueva = det.model_copy(deep=True)
            nueva.properties = props
            nueva.evidence.notes = [
                n for n in nueva.evidence.notes if _NOTA_DEL_MODELO not in n
            ] + notas
            salida.append(nueva)
            escritas += cambios
        else:
            salida.append(det)
    return salida, escritas


# Lo que dicen las notas que el modelo agrega a una detección (para quitarlas al restaurar).
_NOTA_DEL_MODELO = " del modelo estructural ("
# Lo que el modelo escribe (además de lo que restaura de cada previa).
_DEL_MODELO = ("seccion_del_modelo", "armado_del_modelo", "longitud_fuente")


def _restaurar(props: dict) -> bool:
    """Deshace lo que una escritura del modelo dejó en ``props`` (R235): cada clave vuelve a lo
    que la detección traía (``None``: no la traía). Si había algo que deshacer."""
    hubo = False
    for previa_de in ("seccion_previa", "claro_previo", "longitud_previa"):
        previa = props.pop(previa_de, None)
        if not isinstance(previa, dict):
            continue
        hubo = True
        for clave, valor in previa.items():
            if valor is None:
                props.pop(clave, None)
            else:
                props[clave] = valor
    for clave in _DEL_MODELO:
        if clave in props:
            hubo = True
            props.pop(clave)
    return hubo


def _pzas(n: int) -> str:
    return f"{n} pza" if n == 1 else f"{n} pzas"


def diferencias_con_el_concreto(
    detections: list[Detection],
    elementos: list[Elemento],
    meters_factor: float | None,
    assumptions: Any,
    segmentation: SheetSegmentation | None,
    en_lineas: set[str],
) -> list[str]:
    """Dónde el concreto (lo que mide el presupuesto con la detección, ya escrita) y el acero (el
    elemento del modelo) no usan la misma sección o la misma altura, en las colocaciones que
    están en un renglón de concreto (``en_lineas``): una por marca, con lo que usa cada uno. El
    modelo no toma marcadores ni pone un supuesto sobre una medida, y el concreto de un castillo
    toma la altura de su entrepiso (``boq``): lo que no coincide se dice."""
    if not meters_factor:
        return []
    from klave_engine.costing import boq

    por_id = {d.detection_id: d for d in detections}
    secciones: dict[tuple[str, str, str], Counter[str]] = {}
    alturas: dict[tuple[str, str, str], Counter[str]] = {}
    alto_de_planta = _alturas_del_concreto(segmentation, assumptions, por_id, elementos)
    for e in elementos:
        det = por_id.get(e.detection_id)
        if det is None or e.detection_id not in en_lineas or e.familia not in _CON_ESCRITURA:
            continue
        s = e.seccion_cm
        modelo = _area_m2(s.valor) if s is not None else None
        if modelo is not None and s is not None:
            usada, como = _seccion_del_concreto(det, e.familia, meters_factor, assumptions, boq)
            if usada is not None and abs(usada - modelo) > _TOLERANCIA_AREA * modelo:
                clave = (e.marca, e.familia, f"{_seccion_texto(s.valor)} ({s.fuente})")
                secciones.setdefault(clave, Counter())[como] += 1
        if e.familia in _CON_ALTURA and e.altura_m is not None:
            alto = _numero(e.altura_m.valor)
            del_concreto = alto_de_planta.get(e.detection_id)
            if alto is not None and del_concreto is not None:
                if abs(alto - del_concreto) > _TOLERANCIA_CLARO_M:
                    clave = (e.marca, e.familia, f"{alto:g} m ({e.altura_m.fuente})")
                    alturas.setdefault(clave, Counter())[f"{del_concreto:g} m"] += 1
    avisos = []
    for (marca, familia, del_modelo), usadas in sorted(secciones.items()):
        n = sum(usadas.values())
        lista = ", ".join(
            f"{como} ({k})" if len(usadas) > 1 else como for como, k in sorted(usadas.items())
        )
        avisos.append(
            f"Concreto y acero con secciones distintas en {marca or 'sin marca'} ({familia}, "
            f"{_pzas(n)}): el concreto toma {lista}; el acero, {del_modelo} del modelo "
            "estructural, que no toma marcadores ni pone un supuesto sobre una medida. Por "
            "confirmar."
        )
    for (marca, familia, del_modelo), usadas in sorted(alturas.items()):
        n = sum(usadas.values())
        lista = ", ".join(f"{a} ({k})" if len(usadas) > 1 else a for a, k in sorted(usadas.items()))
        avisos.append(
            f"Concreto y acero con alturas distintas en {marca or 'sin marca'} ({familia}, "
            f"{_pzas(n)}): el concreto toma {lista}; el acero, {del_modelo} del modelo "
            "estructural. Por confirmar."
        )
    return avisos


def _area_m2(valor: Any) -> float | None:
    if isinstance(valor, dict):
        area = _numero(valor.get("area_cm2"))
        return area / 10_000 if area is not None and area > 0 else None
    if isinstance(valor, list | tuple) and len(valor) == 2:
        a, b = _numero(valor[0]), _numero(valor[1])
        if a is not None and b is not None and a > 0 and b > 0:
            return a * b / 10_000
    return None


def _seccion_del_concreto(
    det: Detection, familia: str, factor: float, assumptions: Any, boq: Any
) -> tuple[float | None, str]:
    """La sección (m²) con que el presupuesto mide el concreto de la detección y de dónde sale,
    con las reglas de ``boq`` (``_column_volume`` para castillos y columnas, ``_section_m2`` para
    trabes y contratrabes); ``None`` en una dala (su renglón es por metro)."""
    props = det.properties or {}
    lados = _lados(props.get("section_cm"))
    du2 = props.get("section_area_du2")
    marcador = float(du2) * factor * factor if isinstance(du2, int | float) and du2 > 0 else None
    if familia in _CON_ALTURA:
        castillo = det.label.strip().upper().startswith("K")
        supuesta = assumptions.castillo_section_m2 if castillo else assumptions.column_section_m2
        tope = boq.MAX_CASTILLO_SECTION_M2 if castillo else boq.MAX_COLUMN_SECTION_M2
        if lados is not None:
            area, como = lados[0] * lados[1] / 10_000, f"{_cm(lados[0])}x{_cm(lados[1])}"
        elif marcador is not None:
            area, como = marcador, f"{marcador * 10_000:.0f} cm² de la detección"
        else:
            return supuesta, f"la supuesta del presupuesto ({supuesta * 10_000:g} cm²)"
        if boq.MIN_COLUMN_SECTION_M2 <= area <= tope:
            return area, como
        return supuesta, (
            f"la supuesta del presupuesto ({supuesta * 10_000:g} cm²), porque {como} está fuera "
            "de rango"
        )
    if familia in ("trabe", "contratrabe"):
        supuesta = (
            assumptions.beam_section_m2
            if familia == "trabe"
            else assumptions.contratrabe_section_m2
        )
        if lados is not None:
            area = lados[0] * lados[1] / 10_000
            if boq.MIN_COLUMN_SECTION_M2 <= area <= boq.MAX_LINEAR_SECTION_M2:
                return area, f"{_cm(lados[0])}x{_cm(lados[1])}"
        if (
            marcador is not None
            and boq.MIN_COLUMN_SECTION_M2 <= marcador <= boq.MAX_COLUMN_SECTION_M2
        ):
            return marcador, f"{marcador * 10_000:.0f} cm² de la detección"
        return supuesta, f"la supuesta del presupuesto ({supuesta * 10_000:g} cm²)"
    return None, ""


def _alturas_del_concreto(
    segmentation: SheetSegmentation | None,
    assumptions: Any,
    por_id: dict[str, Detection],
    elementos: list[Elemento],
) -> dict[str, float]:
    """La altura con que el presupuesto mide el concreto de cada castillo y columna (``boq``,
    ``COLUMN_VOLUME``): la de su entrepiso declarado; sin niveles que se junten, la supuesta en
    cada planta (si hay dos o más con columnas) o la total en la planta más poblada."""
    if segmentation is None or not segmentation.is_segmented:
        return {}
    alturas = segmentation.story_heights()
    asignacion = segmentation.assignment
    salida: dict[str, float] = {}
    columnas = [e for e in elementos if e.familia in _CON_ALTURA and e.detection_id in por_id]
    if alturas:
        for e in columnas:
            vista = asignacion.get(e.detection_id)
            if vista in alturas:
                salida[e.detection_id] = alturas[vista]
        return salida
    super_ids = {v.view_id for v in segmentation.superstructure_views()}
    con_columnas = {asignacion.get(e.detection_id) for e in columnas} & super_ids
    if len(con_columnas) >= 2:
        return {e.detection_id: assumptions.column_height_m for e in columnas}
    total = segmentation.total_height()
    alto = total if total else assumptions.column_height_m
    return {e.detection_id: alto for e in columnas}


def _escribir_largo_de_pilote(
    det: Detection, e: Elemento, props: dict, cambios: list[Escritura], notas: list[str]
) -> None:
    """La longitud de un pilote que el modelo resolvió del plano (o de una decisión): la que
    mide sus metros (CIM-011, ``apply_piles`` la toma antes que las especificaciones)."""
    largo = e.longitud_m
    if largo is None or largo.fuente in ("supuesto", "ia") or largo.ilegible:
        return
    metros = _numero(largo.valor)
    if metros is None or metros <= 0:
        return
    actual = _numero(props.get("longitud_m"))
    if actual is not None and abs(actual - metros) <= _TOLERANCIA_CLARO_M:
        return
    # Lo que traía la detección (ya restaurada: ``_restaurar``), para deshacerlo después.
    props["longitud_previa"] = {"longitud_m": props.get("longitud_m")}
    props["longitud_m"] = metros
    props["longitud_fuente"] = largo.fuente
    antes = f"{actual:g} m" if actual is not None else None
    cambios.append(_escritura(e, det, "longitud_m", antes, None, largo))
    notas.append(f"Longitud {metros:g} m del modelo estructural ({largo.fuente}: «{largo.texto}»)")


def _escribir_seccion(
    det: Detection,
    e: Elemento,
    props: dict,
    factor: float,
    cambios: list[Escritura],
    notas: list[str],
) -> None:
    s = e.seccion_cm
    if s is None or s.valor is None or s.ilegible:
        return
    valor = s.valor
    rectangulo = isinstance(valor, list | tuple) and len(valor) == 2
    if not rectangulo and not (isinstance(valor, dict) and _numero(valor.get("area_cm2"))):
        return
    fuente_actual = props.get("section_source")
    del_cuadro = props.get("spec_source") is not None and fuente_actual in _DEL_CUADRO
    actual_txt = _actual(props, factor)
    leida = s.fuente not in ("supuesto", "ia")
    if _iguales(e.familia, valor, props, factor):
        if fuente_actual == "cuadro" and not leida:
            # El valor es el mismo; lo que no es del cuadro no lo dice.
            _previa(props)
            props["section_source"] = s.fuente
            cambios.append(_escritura(e, det, "fuente", actual_txt, fuente_actual, s))
        if _variante_resuelta(e):
            # R236: la sección es la de su variante; su armado también lo es.
            _escribir_armado(det, e, props, cambios, notas)
        return
    if not leida and not del_cuadro:
        # Un supuesto (o la IA) del modelo no tapa la medida de la detección ni llena la que no
        # trae sección: el presupuesto usa la suya (``diferencias_con_el_concreto`` lo dice).
        return
    _previa(props)
    if rectangulo:
        b, h = float(valor[0]), float(valor[1])
        props["section_cm"] = f"{_cm(b)}x{_cm(h)}"
        props["section_area_du2"] = round(b * h / 10_000 / (factor * factor), 6)
        props.pop("section_perimetro_du", None)
    else:
        props.pop("section_cm", None)
        area = float(valor["area_cm2"])
        props["section_area_du2"] = round(area / 10_000 / (factor * factor), 6)
        perimetro = _numero(valor.get("perimetro_cm"))
        if perimetro:
            # R242: la cimbra de una sección que no es un rectángulo es su contorno.
            props["section_perimetro_du"] = round(perimetro / 100 / factor, 6)
        else:
            props.pop("section_perimetro_du", None)
    props["section_source"] = s.fuente
    props["seccion_del_modelo"] = s.texto
    cambios.append(_escritura(e, det, "seccion", actual_txt, fuente_actual, s))
    notas.append(
        f"Sección {_seccion_texto(valor)} del modelo estructural ({s.fuente}: «{s.texto}»); "
        f"antes {actual_txt or 'sin sección'}" + (f" ({fuente_actual})" if fuente_actual else "")
    )
    # R236: la sección y el armado de la detección salen de la misma lectura, nunca mezclados.
    _escribir_armado(det, e, props, cambios, notas)


def _variante_resuelta(e: Elemento) -> bool:
    """Si el elemento tomó la variante por muro de su marca (R168)."""
    return any(a.startswith(f"variante: {e.marca} «para muros de") for a in e.avisos)


def _textos_del_armado(e: Elemento) -> tuple[str | None, str | None]:
    """El armado del elemento como lo escriben las especificaciones (``spec_rebar``,
    ``spec_stirrups``): sus varillas y sus estribos en forma canónica, o ``None``."""
    from klave_engine.estructura.armado import Armado, texto_estribos, texto_longitudinal

    def piezas(dato: Dato | None, modelo: type[BaseModel]) -> list[Any]:
        if dato is None or not isinstance(dato.valor, list) or dato.ilegible:
            return []
        return [modelo.model_validate(p) for p in dato.valor]

    grupos = piezas(e.longitudinales, GrupoVarillas)
    juegos = piezas(e.estribos, JuegoEstribos)
    try:
        varillas = texto_longitudinal(Armado(longitudinales=grupos)) if grupos else None
    except ValueError:
        varillas = None
    try:
        estribos = texto_estribos(Armado(estribos=juegos)) if juegos else None
    except ValueError:
        estribos = None
    return varillas or None, estribos or None


def _escribir_armado(
    det: Detection, e: Elemento, props: dict, cambios: list[Escritura], notas: list[str]
) -> None:
    varillas, estribos = _textos_del_armado(e)
    if props.get("spec_rebar") == varillas and props.get("spec_stirrups") == estribos:
        return
    _previa(props)
    antes = " ".join(str(x) for x in (props.get("spec_rebar"), props.get("spec_stirrups")) if x)
    for clave, texto in (("spec_rebar", varillas), ("spec_stirrups", estribos)):
        if texto:
            props[clave] = texto
        else:
            props.pop(clave, None)
    fuente = next((d.fuente for d in (e.longitudinales, e.estribos) if d is not None), "supuesto")
    despues = " ".join(x for x in (varillas, estribos) if x) or "sin armado"
    props["armado_del_modelo"] = fuente
    cambios.append(
        Escritura(
            detection_id=det.detection_id,
            marca=e.marca,
            familia=e.familia,
            hoja=e.hoja,
            campo="armado",
            antes=antes or None,
            fuente_antes=str(props.get("spec_source")) if props.get("spec_source") else None,
            despues=despues,
            fuente=fuente,
        )
    )
    notas.append(
        f"Armado {despues} del modelo estructural ({fuente}: el de la misma lectura que su "
        f"sección); antes {antes or 'sin armado'}"
    )


def _actual(props: dict, factor: float) -> str | None:
    lados = _lados(props.get("section_cm"))
    if lados is not None:
        return f"{_cm(lados[0])}x{_cm(lados[1])}"
    du2 = props.get("section_area_du2")
    if isinstance(du2, int | float) and du2 > 0:
        return f"{float(du2) * factor * factor * 10_000:.0f} cm²"
    return None


def _previa(props: dict) -> None:
    """Lo que la detección traía antes de la primera escritura del modelo (nunca se pisa)."""
    if "seccion_previa" not in props:
        props["seccion_previa"] = {
            "section_cm": props.get("section_cm"),
            "section_area_du2": props.get("section_area_du2"),
            "section_source": props.get("section_source"),
            "section_perimetro_du": props.get("section_perimetro_du"),
            "spec_rebar": props.get("spec_rebar"),
            "spec_stirrups": props.get("spec_stirrups"),
        }


def _escritura(
    e: Elemento, det: Detection, campo: str, antes: str | None, fuente_antes: Any, s: Dato
) -> Escritura:
    return Escritura(
        detection_id=det.detection_id,
        marca=e.marca,
        familia=e.familia,
        hoja=e.hoja,
        campo=campo,  # type: ignore[arg-type]
        antes=antes,
        fuente_antes=str(fuente_antes) if fuente_antes is not None else None,
        despues=(
            f"{float(s.valor):g} m" if campo in ("claro", "longitud_m") else _seccion_texto(s.valor)
        ),
        fuente=s.fuente,
        texto=s.texto,
    )


def _escribir_claro(
    det: Detection,
    e: Elemento,
    props: dict,
    factor: float,
    cambios: list[Escritura],
    notas: list[str],
) -> None:
    """El claro que declara la definición de una viga (o una decisión), cuando no es el medido."""
    largo = e.longitud_m
    if e.familia not in _VIGAS or largo is None or largo.fuente in ("medido", "supuesto", "ia"):
        return
    metros = _numero(largo.valor)
    if metros is None or metros <= 0 or largo.ilegible:
        return
    actual = props.get("estimated_span_length")
    actual_m = float(actual) * factor if isinstance(actual, int | float) else None
    if actual_m is not None and abs(actual_m - metros) <= _TOLERANCIA_CLARO_M:
        return
    if "claro_previo" not in props:
        props["claro_previo"] = {"estimated_span_length": actual}
    props["estimated_span_length"] = round(metros / factor, 6)
    antes = f"{actual_m:g} m" if actual_m is not None else None
    cambios.append(_escritura(e, det, "claro", antes, "medido" if antes else None, largo))
    notas.append(
        f"Claro {metros:g} m del modelo estructural ({largo.fuente}: «{largo.texto}»); antes "
        f"{antes or 'sin claro'}"
    )


def notas_de_escritura(detections: list[Detection]) -> list[str]:
    """Lo que el modelo escribió en las detecciones que el presupuesto lee, por marca: su sección
    (o su fuente) y su armado (R236: la sección y el armado de una variante van juntos), dicho en
    el presupuesto (lo que se mide ya no es lo que el detector leyó). Lo que no cambió no se
    dice: una detección a la que sólo se le reescribió el armado no dice una sección «→» igual."""
    por_marca: dict[tuple[str, str, str], int] = {}
    for d in detections:
        props = d.properties or {}
        previa = props.get("seccion_previa")
        if not isinstance(previa, dict):
            continue
        seccion = ""
        if any(
            previa.get(k) != props.get(k)
            for k in ("section_cm", "section_area_du2", "section_source")
        ):
            antes = previa.get("section_cm") or (
                "marcador" if previa.get("section_area_du2") else "sin sección"
            )
            despues = props.get("section_cm") or "área de su contorno"
            seccion = (
                f"{antes} ({previa.get('section_source') or '—'}) → "
                f"{despues} ({props.get('section_source') or '—'})"
            )
        armado = ""
        if "armado_del_modelo" in props:
            claves = ("spec_rebar", "spec_stirrups")
            antes = " ".join(str(previa[k]) for k in claves if previa.get(k))
            despues = " ".join(str(props[k]) for k in claves if props.get(k))
            # ``_escribir_armado`` sólo lo marca cuando el armado cambia.
            armado = (
                f"armado {antes or 'sin armado'} → {despues or 'sin armado'} "
                f"({props['armado_del_modelo']})"
            )
        if not seccion and not armado:
            continue
        clave = (d.mark or d.label, seccion, armado)
        por_marca[clave] = por_marca.get(clave, 0) + 1
    if not por_marca:
        return []
    partes = [
        f"{marca} ({n}): " + ", ".join(x for x in (seccion, armado) if x)
        for (marca, seccion, armado), n in sorted(por_marca.items())
    ]
    return [
        "Secciones y armados del modelo estructural escritos en las detecciones (la definición de "
        "cada marca en su hoja, con su fuente; lo que había queda en la detección): "
        + "; ".join(partes)
    ]


# ------------------------------------------------------------------------------ la tarjeta


_GENERAL = "general"


def resumir(e: Estructura, report: Any) -> list[ResumenFamilia]:
    """La tarjeta por familia (``ResumenFamilia``): las familias con colocaciones o con hallazgos,
    más «general» para los hallazgos que no son de ninguna (R240: cada hallazgo en una sola
    tarjeta), ordenadas por el dinero en juego que se conoce (``en_juego_mxn_conocido``), luego
    por la cantidad conocida (concreto, acero) y luego como ``FAMILIAS_ESTRUCTURALES``. ``report``
    es el ``CostReport`` de la misma lectura: de él salen los P.U. de los renglones que tienen las
    colocaciones."""
    from klave_engine.detection.schedules import family_of_mark

    por_marca = {d.marca: d for d in e.definiciones}
    familia_de_marca = {d.marca: d.familia for d in e.definiciones}
    por_elemento = {x.element_id: x for x in e.elementos}
    familias: dict[str, list[Elemento]] = {}
    for x in e.elementos:
        familias.setdefault(x.familia, []).append(x)
    rango = {f: i for i, f in enumerate(FAMILIAS_ESTRUCTURALES)}

    def de_la_marca(marca: str) -> str | None:
        base = marca.split(" (", 1)[0]
        familia = familia_de_marca.get(base) or family_of_mark(base)
        return None if familia == "elemento" else familia

    def tarjeta(v: Verificacion) -> str:
        """R240: la familia de la mayoría de sus elementos; si no tiene, la de sus marcas (su
        definición o su prefijo); si tampoco, «general»."""
        cuenta = Counter(por_elemento[i].familia for i in v.elementos if i in por_elemento)
        if not cuenta:
            cuenta = Counter(f for m in v.marcas if (f := de_la_marca(m)) is not None)
        if not cuenta:
            return _GENERAL
        return min(cuenta, key=lambda f: (-cuenta[f], rango.get(f, len(rango)), f))

    hallazgos: dict[str, list[Verificacion]] = {}
    for v in e.verificaciones:
        hallazgos.setdefault(tarjeta(v), []).append(v)
    precios = _Precios(report)
    reglas: dict[str, Reglas] = {}
    a = SteelAssumptions()

    def reglas_de(hoja: str) -> Reglas:
        if hoja not in reglas:
            reglas[hoja] = e.reglas.para(hoja)
        return reglas[hoja]

    con_cifra: set[str] = set()  # los hallazgos cuya cantidad en juego tiene cifra
    deltas: dict[tuple[str, str], tuple[float, float]] = {}  # (element_id, campo) → (m³, kg)
    for v in e.verificaciones:
        valores = valores_en_disputa(v, por_marca)
        if len(valores) < 2:
            continue
        con_cifra.add(v.id)
        campo = v.campo.split(",")[0] if v.numero == 8 else "seccion_cm"
        for i in v.elementos:
            el = por_elemento.get(i)
            if el is None or _decidido_en(el, campo):
                continue
            delta = _delta(el, campo, valores, reglas_de, a)
            anterior = deltas.get((i, campo), (0.0, 0.0))
            deltas[(i, campo)] = (max(anterior[0], delta[0]), max(anterior[1], delta[1]))
    # Lo que un hallazgo pone en juego sin valores por elemento (los entrepisos contados de dos
    # maneras: el acero y el concreto de todas sus colocaciones juntas): dicho aparte, por su id,
    # en cada familia que toca —compartido por id, nunca sumado entre tarjetas— y nunca repartido
    # a ojo entre ellas. Tiene cifra, pero no dinero: la tarjeta no da $ mientras esté abierto.
    aparte: dict[str, dict[str, dict[str, float]]] = {}
    sin_dinero: set[str] = set()
    for v in e.verificaciones:
        if v.severidad == "aviso" or v.numero != 8 or v.cantidad != "conocida":
            continue
        if valores_en_disputa(v, por_marca):
            continue
        juego = {k: q for k, q in v.en_juego.items() if k in ("concreto_m3", "acero_kg") and q}
        if not juego:
            continue
        sin_dinero.add(v.id)
        for f in {por_elemento[i].familia for i in v.elementos if i in por_elemento}:
            aparte.setdefault(f, {})[v.id] = juego
    orden = [f for f in FAMILIAS_ESTRUCTURALES if f in familias or f in hallazgos]
    orden += sorted((set(familias) | set(hallazgos)) - set(orden) - {_GENERAL})
    if _GENERAL in hallazgos:
        orden.append(_GENERAL)
    salida: list[ResumenFamilia] = []
    for familia in orden:
        els = familias.get(familia, [])
        criticos = CRITICOS.get(familia, ())
        del_plano = humanos = 0
        for x in els:
            for c in criticos:
                dato = getattr(x, c)
                if dato is None or dato.valor is None or dato.ilegible:
                    continue
                del_plano += dato.fuente in _DEL_PLANO
                humanos += dato.fuente == "humano"
        suyos = hallazgos.get(familia, [])
        abiertos = [v for v in suyos if v.severidad != "aviso"]
        desconocido = sum(1 for v in abiertos if v.id not in con_cifra and v.id not in sin_dinero)
        cantidad: dict[str, float] = {}
        sin_precio: dict[str, float] = {}
        fuera: dict[str, float] = {}
        dinero = 0.0
        for (i, _campo), (m3, kg) in deltas.items():
            x = por_elemento[i]
            if x.familia != familia:
                continue
            en_presupuesto = precios.en_presupuesto(x.detection_id)
            for clave, q, pu in (
                ("concreto_m3", m3, precios.concreto(x.detection_id)),
                ("acero_kg", kg, precios.acero(x.detection_id)),
            ):
                if q <= 0:
                    continue
                if not en_presupuesto:
                    # Una colocación que ningún renglón cuenta: aparte, no sumado.
                    fuera[clave] = fuera.get(clave, 0.0) + q
                    continue
                cantidad[clave] = cantidad.get(clave, 0.0) + q
                if pu is None:
                    sin_precio[clave] = sin_precio.get(clave, 0.0) + q
                else:
                    dinero += q * pu
        con_aparte = any(v.id in sin_dinero for v in abiertos)
        con_precio = any(q for k, q in cantidad.items() if q > sin_precio.get(k, 0.0))
        mxn: float | None = round(dinero, 2)
        if desconocido or con_aparte or (cantidad and not con_precio):
            # Algo abierto no tiene cifra, o lo que hay en juego no tiene ningún precio: nunca $0.
            # Con una parte sin precio, el dinero es el de la otra; ``en_juego_sin_precio`` lo dice.
            mxn = None
        salida.append(
            ResumenFamilia(
                familia=familia,
                colocaciones=len(els),
                con_definicion=sum(1 for x in els if x.definicion == "marca"),
                criticos_total=len(els) * len(criticos),
                criticos_del_plano=del_plano,
                bloquea=sum(1 for v in suyos if v.severidad == "bloquea"),
                duda=sum(1 for v in suyos if v.severidad == "duda"),
                aviso=sum(1 for v in suyos if v.severidad == "aviso"),
                en_juego_mxn=mxn,
                en_juego_cantidad={k: round(q, 4) for k, q in cantidad.items()},
                criticos_humanos=humanos,
                en_juego_sin_precio={k: round(q, 4) for k, q in sin_precio.items()},
                en_juego_aparte=aparte.get(familia, {}),
                en_juego_desconocido=desconocido,
                en_juego_fuera_del_presupuesto={k: round(q, 4) for k, q in fuera.items()},
                en_juego_mxn_conocido=round(dinero, 2),
            )
        )
    posicion = {f: i for i, f in enumerate(orden)}
    salida.sort(
        key=lambda r: (
            # El dinero conocido: una tarjeta con precio en juego no baja por un hallazgo sin cifra.
            -r.en_juego_mxn_conocido,
            -r.en_juego_cantidad.get("concreto_m3", 0.0),
            -r.en_juego_cantidad.get("acero_kg", 0.0),
            posicion[r.familia],
        )
    )
    return salida


def _decidido_en(x: Elemento, campo: str) -> bool:
    destino = "altura_m" if campo == "longitud_m" and x.familia in _CON_ALTURA else campo
    dato = getattr(x, destino, None)
    return dato is not None and dato.fuente == "humano"


def _delta(
    x: Elemento,
    campo: str,
    valores: list[Dato],
    reglas_de: Any,
    a: SteelAssumptions,
) -> tuple[float, float]:
    """Lo que cambia el concreto (m³) y el acero (kg, con desperdicio) de ``x`` entre los valores
    que el plano da para ``campo`` (el mayor menos el menor)."""
    destino = "altura_m" if campo == "longitud_m" and x.familia in _CON_ALTURA else campo
    concretos: list[float] = []
    aceros: list[float] = []
    for dato in valores:
        otro = x.model_copy(update={destino: dato})
        if campo in ("seccion_cm", "longitud_m"):
            m3 = volumen(otro)
            if m3 is not None:
                concretos.append(m3)
        try:
            acero = acero_elemento(otro, reglas_de(x.hoja), a.anchorage_m)
        except (ValueError, TypeError):
            acero = None
        if acero is not None:
            aceros.append(acero.total_kg() * (1 + a.waste_pct / 100))
    m3 = max(concretos) - min(concretos) if len(concretos) == len(valores) else 0.0
    kg = max(aceros) - min(aceros) if len(aceros) == len(valores) else 0.0
    return m3, kg


class _Precios:
    """Los P.U. de los renglones del presupuesto que tienen cada detección: el de su variante si
    la variante tiene uno, si no el del renglón; ``None`` si el renglón no tiene precio."""

    def __init__(self, report: Any) -> None:
        self._concreto: dict[str, float | None] = {}
        self._acero: dict[str, float | None] = {}
        self._contadas: set[str] = set()
        boq = getattr(report, "boq", None)
        if boq is None:
            return
        confiable = getattr(boq, "units_reliable", True)
        for line in boq.lines:
            self._contadas.update(line.source_detections)
            destino = (
                self._concreto
                if line.unit.upper() == "M3"
                else self._acero
                if line.unit.upper() == "KG"
                else None
            )
            if destino is None:
                continue
            base = None if (line.unpriced or not confiable) else float(line.unit_price)
            de_variante: dict[str, float | None] = {}
            for variante in line.variants:
                pu = variante.unit_price if variante.unit_price is not None else base
                for i in variante.source_detections:
                    de_variante[i] = None if (line.unpriced or not confiable) else pu
            for i in line.source_detections:
                destino.setdefault(i, de_variante.get(i, base))

    def concreto(self, detection_id: str) -> float | None:
        return self._concreto.get(detection_id)

    def acero(self, detection_id: str) -> float | None:
        return self._acero.get(detection_id)

    def en_presupuesto(self, detection_id: str) -> bool:
        """Si algún renglón del presupuesto cuenta la detección."""
        return detection_id in self._contadas
