"""El catálogo de conceptos de la convocante, que en obra pública manda.

Hasta aquí el motor armaba su propio catálogo desde los planos, y eso sirve
para un anteproyecto. Una licitación funciona al revés: la convocante manda un
catálogo con sus claves, sus descripciones, sus unidades y **sus cantidades**,
y el licitante devuelve exactamente ese documento con precios puestos. Ni una
clave más, ni una menos, ni en otro orden — una propuesta que reordena o
agrega renglones se desecha por no apegarse al catálogo (RLOPSRM art. 61,
fracción I).

Así que el catálogo entrante es la autoridad sobre **qué** se cotiza y en qué
orden. Lo que el motor aporta encima es lo que nadie más puede aportar:
comparar las cantidades de la convocante contra las que salen del plano.

Esa comparación es el verdadero valor y conviene decir por qué. En obra
pública a precios unitarios se paga lo ejecutado, no lo catalogado: si el
catálogo dice 420 m² de muro y el plano tiene 507, el licitante que reparte
sus indirectos sobre 420 los está repartiendo sobre menos obra de la que va a
hacer, y lo descubre construyendo. Al revés —catálogo de más— infla el monto
de la propuesta con obra que no existe y se cae en la evaluación. Las dos
cosas se ven aquí antes de firmar, que es el único momento en que sirven.

Lo que el motor **no** hace es corregir el catálogo. Las cantidades de la
convocante son el contrato; la diferencia se reporta, se aclara en junta y se
firma o no. Cambiarlas por las del plano sería presentar otra propuesta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from klave_engine.costing.matching import Candidate, rank
from klave_engine.costing.models import BillOfQuantities, Concept
from klave_engine.costing.sources.presupuesto import PresupuestoRow

# Debajo de esto la coincidencia no se propone sola: el renglón queda para que
# alguien lo ate a mano, que es más barato que atarlo mal.
UMBRAL_ATADURA = 0.55
# Los conceptos que el motor mide del plano se atan con una vara más baja, y
# la razón es que su error se ve: al atarlos aparece la cantidad del plano al
# lado de la del catálogo, y una atadura equivocada salta como una diferencia
# absurda. Un concepto que no mide se ata a ciegas y ahí sí conviene la vara
# alta.
UMBRAL_MOTOR = 0.45
# Diferencia de cantidad que deja de ser redondeo y pasa a ser un aviso.
TOLERANCIA_CANTIDAD_PCT = 5.0


@dataclass
class RenglonConvocante:
    """Un renglón del catálogo entrante, con lo que el motor le encontró."""

    clave: str
    description: str
    unit: str
    quantity: float
    orden: int
    group: str = ""
    # El concepto del motor al que se ató, y cómo.
    concept_code: str = ""
    match_score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)
    # La cantidad que el plano sostiene para ese concepto, cuando la hay.
    quantity_engine: float | None = None
    unit_price: float | None = None

    @property
    def amount(self) -> float | None:
        if self.unit_price is None:
            return None
        return round(self.quantity * self.unit_price, 2)

    @property
    def diferencia_pct(self) -> float | None:
        """Cuánto se aparta la cantidad del plano de la catalogada."""
        if self.quantity_engine is None or self.quantity <= 0:
            return None
        return (self.quantity_engine - self.quantity) / self.quantity * 100.0


@dataclass
class CatalogoConvocante:
    nombre: str
    renglones: list[RenglonConvocante]
    notas: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(r.amount or 0.0 for r in self.renglones), 2)

    @property
    def sin_precio(self) -> list[RenglonConvocante]:
        return [r for r in self.renglones if r.unit_price is None]

    @property
    def sin_atar(self) -> list[RenglonConvocante]:
        return [r for r in self.renglones if not r.concept_code]


def _candidatos(catalog: list[Concept]) -> list[Candidate]:
    return [
        Candidate(
            kind="concept", key=c.code, clave=c.code, description=c.description,
            unit=c.unit, price=None, phase=c.phase,
        )
        for c in catalog
    ]


def _atadura(
    fila: PresupuestoRow,
    del_motor: list[Candidate],
    del_taller: list[Candidate],
) -> tuple[str, float, list[str]] | None:
    """El concepto al que se ata el renglón, prefiriendo los que el motor mide.

    Un concepto importado de un catálogo de destajos puede parecerse más en
    palabras y no sirve para lo que importa aquí: no tiene cantidad leída del
    plano, así que atar el renglón a él pierde la comparación, que es lo único
    que el motor aporta sobre el catálogo de la convocante. Primero se busca
    entre los que miden; sólo si ninguno alcanza se mira el resto."""
    for grupo, umbral in ((del_motor, UMBRAL_MOTOR), (del_taller, UMBRAL_ATADURA)):
        mejor = rank(fila.description, fila.unit, grupo, phase=fila.group, limit=1)
        if mejor and mejor[0].score >= umbral:
            return mejor[0].candidate.key, mejor[0].score, list(mejor[0].reasons)
    return None


def atar_catalogo(
    filas: list[PresupuestoRow],
    catalog: list[Concept],
    boq: BillOfQuantities | None = None,
    nombre: str = "",
    precios: dict[str, float] | None = None,
) -> CatalogoConvocante:
    """Ata cada renglón de la convocante a un concepto del motor.

    El orden y las claves entrantes se respetan tal cual: son el documento que
    hay que devolver. Lo que se agrega al lado es la cantidad que el plano
    sostiene y el precio que el taller tenga, y nada de eso toca el renglón."""
    del_motor = _candidatos([c for c in catalog if c.rule is not None])
    del_taller = _candidatos([c for c in catalog if c.rule is None])
    del_plano = {line.concept_code: line.quantity for line in (boq.lines if boq else [])}
    precios = precios or {}
    renglones: list[RenglonConvocante] = []
    for orden, fila in enumerate(filas):
        renglon = RenglonConvocante(
            clave=fila.clave, description=fila.description, unit=fila.unit,
            quantity=fila.quantity, orden=orden, group=fila.group,
        )
        atado = _atadura(fila, del_motor, del_taller)
        if atado is not None:
            renglon.concept_code, renglon.match_score, renglon.match_reasons = atado
            renglon.quantity_engine = del_plano.get(renglon.concept_code)
        # El precio del renglón es del licitante: el catálogo entrante nunca
        # los trae, y si los trae no son suyos.
        precio = precios.get(renglon.concept_code) if renglon.concept_code else None
        renglon.unit_price = precio
        renglones.append(renglon)

    notas: list[str] = []
    atados = [r for r in renglones if r.concept_code]
    notas.append(
        f"{len(atados)} de {len(renglones)} renglones atados a un concepto del motor; "
        f"el resto espera que alguien los ate o los cotice a mano."
    )
    return CatalogoConvocante(nombre=nombre, renglones=renglones, notas=notas)


def avisos_de_cantidad(catalogo: CatalogoConvocante) -> list[str]:
    """Dónde el plano y el catálogo de la convocante no dicen lo mismo.

    Se reportan por separado los dos sentidos porque duelen distinto: de menos
    en el catálogo significa obra que se ejecuta y no se cataloga —se paga con
    los indirectos del licitante—; de más significa dinero en la propuesta que
    no corresponde a obra, y eso se detecta en la evaluación."""
    faltantes: list[tuple[RenglonConvocante, float]] = []
    sobrantes: list[tuple[RenglonConvocante, float]] = []
    for renglon in catalogo.renglones:
        diferencia = renglon.diferencia_pct
        if diferencia is None or abs(diferencia) <= TOLERANCIA_CANTIDAD_PCT:
            continue
        (faltantes if diferencia > 0 else sobrantes).append((renglon, diferencia))

    avisos: list[str] = []
    if faltantes:
        peor = max(faltantes, key=lambda x: abs(x[1]))
        avisos.append(
            f"{len(faltantes)} renglones del catálogo traen menos cantidad que el plano; "
            f"el mayor es {peor[0].clave} ({peor[0].description[:34]}): el catálogo dice "
            f"{peor[0].quantity:,.2f} {peor[0].unit} y el plano sostiene "
            f"{peor[0].quantity_engine:,.2f} ({peor[1]:+.0f} %). Esa obra se ejecuta y no "
            "se cataloga: la paga el licitante con sus indirectos."
        )
    if sobrantes:
        peor = min(sobrantes, key=lambda x: x[1])
        avisos.append(
            f"{len(sobrantes)} renglones del catálogo traen más cantidad que el plano; "
            f"el mayor es {peor[0].clave} ({peor[0].description[:34]}): el catálogo dice "
            f"{peor[0].quantity:,.2f} {peor[0].unit} y el plano sostiene "
            f"{peor[0].quantity_engine:,.2f} ({peor[1]:+.0f} %). Aclárala en junta antes "
            "de cotizarla: es monto de propuesta sin obra detrás."
        )
    return avisos
