"""Definiciones por marca: lo que el plano dice de cada marca, campo por campo, con su fuente.

Cada lectura del inventario (``detection.schedules.ScheduleInventory.specs``) da un ``Dato`` por
campo: la sección, la longitud, las varillas longitudinales, los estribos y las parrillas, con la
fuente de su lectura (``FUENTE_DE_LECTURA``), su hoja, su texto y sus entidades. Un campo que el
plano tiene escrito pero que no se pudo leer es un ``Dato`` ilegible (sin valor, con su texto),
nunca un campo vacío. Por campo se elige con ``elegir``: la fuente de mayor rango gana y lo demás
queda en ``alternativas``; dos hojas del mismo rango que no coinciden quedan ``en_conflicto``.

La IA va detrás del plano: sólo llena lo que nada del plano dice, y lo que el plano tiene escrito
para esa marca —leído o no— la bloquea (R64, R68). Su lectura llega con lo bloqueado y por qué
texto (``ElementSpec.campos_bloqueados``, R69): cada campo bloqueado tiene un ``Dato`` del plano
(el de la lectura que lo bloquea o uno ilegible con el texto que lo bloquea), y el valor de la IA
sólo queda como alternativa: nunca se elige.

Las marcas se juntan por ``normalizar_marca``: maneras de escribir la misma marca, nunca marcas
distintas. Las notas de familia («DALA 15X30 4#3 E#2@20») dan las definiciones por familia.

Las formas de los estribos (perimetral, rombo, interior, grapa) las dice el corte dibujado (E3);
hasta entonces ``asignar_formas`` las supone por la práctica del taller y lo dice."""

from typing import Any, get_args

from pydantic import BaseModel, Field

from klave_engine.detection.schedules import (
    _SENALADA,
    FAMILIAS_DE_VIGA,
    FAMILIAS_QUE_SE_ORDENAN,
    Bloqueo,
    Campo,
    ElementSpec,
    Metodo,
    ScheduleInventory,
    Source,
    _loose_key,
    bloqueos_de,
    campos_de_fragmento,
    family_of_mark,
)
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.estructura.armado import (
    Armado,
    Forma,
    GrupoVarillas,
    JuegoEstribos,
    parsear_armado,
)
from klave_engine.estructura.dato import PRECEDENCIA, Dato, Fuente, elegir
from klave_engine.estructura.marcas import (
    es_rango,
    extremos_de_rango,
    leer_marcas,
    marca_en_rango,
    marca_normalizada,
    titulos,
)

# De qué fuente es una lectura, por quién la dio (``source``) y cómo (``metodo``). Todo par que
# los lectores producen está aquí; uno que no, revienta (nunca se supone una fuente):
# - un cuadro con títulos da filas; una pila de armado junto a su marca, las cotas del detalle y
#   la llamada de un corte («SECCIÓN 1» / «30X80», R4) son texto de un detalle; la sección
#   dibujada es geometría del detalle;
# - («cuadro», «nota») es la lectura de un lector por disciplina (los cuadros enchufables:
#   cancelería, tableros…): declara su rango de cuadro y deja el método por omisión;
# - una nota y la IA son lo que son, las haya dado quien las haya dado.
# («cuadro», «pila») no lo produce ningún lector: un cuadro se lee por filas.
FUENTE_DE_LECTURA: dict[tuple[str, str], Fuente] = {
    ("cuadro", "fila"): "cuadro",
    ("cuadro", "nota"): "cuadro",
    ("detalle", "pila"): "detalle",
    ("detalle", "cotas"): "detalle",
    ("detalle", "llamada"): "detalle",
    ("detalle", "geometria"): "seccion_dibujada",
    **{("nota", metodo): "nota" for metodo in get_args(Metodo)},
    **{("ia", metodo): "ia" for metodo in get_args(Metodo)},
}

# Los campos de armado: el de la definición (y de ``Armado``), el de ``ElementSpec`` y el de su
# bloqueo.
_ARMADO: tuple[tuple[str, str, Campo], ...] = (
    ("longitudinales", "rebar", "longitudinales"),
    ("estribos", "stirrups", "estribos"),
    ("parrillas", "mesh", "parrillas"),
)
# Los campos de armado de una definición (los que ``sin_leer`` dice).
_ARMADO_DE_LA_DEFINICION = ("longitudinales", "estribos", "parrillas")
_NOMBRE = {
    "seccion_cm": "sección",
    "longitud_m": "longitud",
    "longitudinales": "longitudinales",
    "estribos": "estribos",
    "parrillas": "parrillas",
}
_DE_CAMPO: dict[Campo, str] = {
    "seccion": "seccion_cm",
    "longitudinales": "longitudinales",
    "estribos": "estribos",
    "parrillas": "parrillas",
    "longitud": "longitud_m",
}


class Definicion(BaseModel):
    """Lo que el plano dice de una marca (o de una familia, para las notas de familia), campo por
    campo. ``seccion_cm`` va como b×h en una viga (trabe, contratrabe, dala, cerramiento: como la
    escribió o la dibujó el plano, R75) y con sus lados ordenados, el menor primero, en un
    castillo, una columna o un pilote; ``longitudinales``,
    ``estribos`` y ``parrillas`` llevan la lista de ``GrupoVarillas``, ``JuegoEstribos`` y
    ``Parrilla``. ``hojas`` son las hojas donde el plano la define."""

    marca: str
    familia: str
    seccion_cm: Dato | None = None
    longitud_m: Dato | None = None
    longitudinales: Dato | None = None
    estribos: Dato | None = None
    parrillas: Dato | None = None
    hojas: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    # Los campos vacíos para los que el plano tiene texto que puede ser de esta marca y que nadie
    # leyó (un renglón sin dueño junto a su sección, R140; una coincidencia suelta; la IA, si la
    # hay, no se toma, R69): campo → esos textos. Quien use el campo sabe que el plano lo
    # escribe.
    sin_leer: dict[str, str] = Field(default_factory=dict)
    # R142, R150: el plano dibuja su sección y no es un rectángulo (K-15A).
    seccion_no_rectangular: bool = False
    # R168: las variantes de la marca por el muro que corona, cada una con el espesor que su
    # detalle declara («CI (PARA MUROS DE 15CM)»): la definición de las lecturas de ese detalle.
    # La definición de la marca junta todas (y su sección queda en conflicto); cada colocación
    # toma la de su muro.
    para_muro_cm: float | None = None
    variantes: list["Definicion"] = Field(default_factory=list)


def normalizar_marca(texto: str, config: TextPatternConfig | None = None) -> str:
    """La llave de una marca para juntar sus lecturas, con la gramática de marcas
    (``estructura.marcas``): sólo maneras de escribir la misma marca («K1», «K-1», «K 1», «k-1»
    → K-1; «K15A.1» → K-15A.1), nunca marcas distintas (K-1, K-1A, K-15A, K-15A.1 y K-1-A son
    cinco; T1-1 no es T-11; K-07 queda K-07). Lo que no es una marca se queda como se escribió,
    en mayúsculas («CTA-3 (SECCIÓN 1)»). Con las etiquetas de ``config`` (las del proyecto);
    sin ella, las de siempre. La Tarea 9 junta las marcas de las colocaciones con esta misma
    función: una sola llave para la definición y para sus elementos."""
    normal = marca_normalizada(texto, config or TextPatternConfig())
    return normal if normal is not None else " ".join(texto.upper().split())


Definicion.model_rebuild()


def fuente_de_lectura(spec: ElementSpec) -> Fuente:
    """La fuente de una lectura (``FUENTE_DE_LECTURA``); un par que nadie mapeó revienta."""
    try:
        return FUENTE_DE_LECTURA[(spec.source, spec.metodo)]
    except KeyError:
        raise ValueError(
            f"lectura de {spec.mark} con fuente «{spec.source}» y método «{spec.metodo}»: "
            "ese par no tiene fuente en FUENTE_DE_LECTURA"
        ) from None


def fuente_de_seccion(spec: ElementSpec) -> Fuente:
    """La fuente de la sección de una lectura: la de la lectura (``fuente_de_lectura``), salvo
    que un lado de la sección sea supuesto (``seccion_supuesta``: una sola cota tomada cuadrada,
    el ancho de las demás secciones de la familia): entonces es «supuesto», nunca «detalle»
    (R81)."""
    return "supuesto" if spec.seccion_supuesta else fuente_de_lectura(spec)


# Las familias cuya sección se compara con sus lados ordenados (castillo, columna, pilote); las
# demás —una viga es b×h— quedan como las leyó quien sabe orientarlas (R75, R88).
_SE_ORDENA = FAMILIAS_QUE_SE_ORDENAN


def _seccion(
    valor: tuple[int | float, int | float], familia: str
) -> tuple[int | float, int | float]:
    a, b = sorted(valor) if familia in _SE_ORDENA else valor
    return (a, b)


def _es_de_familia(spec: ElementSpec) -> bool:
    """Una nota de familia («DALA 15X30 4#3 E#2@20»), o una lectura IA cuya marca es el nombre de
    su familia (R80): es de toda la familia, no de una marca."""
    return spec.source in ("nota", "ia") and spec.mark.strip().upper() == spec.family.upper()


def construir_definiciones(
    inv: ScheduleInventory, config: TextPatternConfig | None = None
) -> tuple[dict[str, Definicion], dict[str, Definicion]]:
    """Las definiciones del plano: (por marca, por familia). Las lecturas se juntan por
    ``normalizar_marca`` y las notas de familia por su familia; cada campo es el ``Dato`` que
    ``elegir`` escoge entre las lecturas (sin hoja preferida: la de cada colocación la decide la
    Tarea 9 con ``para_hoja``). Una marca que el plano nombra sin ambigüedad en un texto que nadie
    leyó también tiene su definición, con ese campo ilegible (R77)."""
    config = config or TextPatternConfig()
    por_marca: dict[str, list[ElementSpec]] = {}
    por_familia: dict[str, list[ElementSpec]] = {}
    for spec in inv.specs:
        if _es_de_familia(spec):
            por_familia.setdefault(spec.family, []).append(spec)
        else:
            por_marca.setdefault(normalizar_marca(spec.mark, config), []).append(spec)
    nombradas = _nombradas_sin_leer(inv, config)
    for marca in nombradas:
        por_marca.setdefault(normalizar_marca(marca, config), [])
    known = (
        {_loose_key(s.mark) for s in inv.specs}
        | {_loose_key(m) for m in inv.by_mark}
        | {_loose_key(m) for m in nombradas}
    )
    repetidas = _hojas_con_el_mismo_codigo(inv)
    marcas = {
        marca: _definir(marca, specs, inv, config, known, repetidas)
        for marca, specs in por_marca.items()
    }
    # R168: las lecturas de un detalle que dice para qué muro es son una variante de su marca.
    for marca, specs in por_marca.items():
        espesores = sorted({s.para_muro_cm for s in specs if s.para_muro_cm is not None})
        for cm in espesores:
            variante = _definir(
                marca,
                [s for s in specs if s.para_muro_cm == cm],
                inv,
                config,
                known,
                repetidas,
                familia=marcas[marca].familia,
            )
            variante.para_muro_cm = cm
            marcas[marca].variantes.append(variante)
    familias = {
        familia: _definir(
            familia.upper(), specs, inv, config, known, repetidas, familia=familia, de_familia=True
        )
        for familia, specs in por_familia.items()
    }
    return marcas, familias


def _nombradas_sin_leer(inv: ScheduleInventory, config: TextPatternConfig) -> list[str]:
    """Las marcas que nombra sin ambigüedad un texto rechazado (R77): su única marca («K-9
    E#3@1S», «CORTE K-1 …»), los miembros de su lista y los extremos de su rango («K-1 Y K-2 …»,
    «K-1 A K-4 …»), las etiquetas entre las que dudó un renglón de pila o las de una etiqueta de
    varias marcas. Las candidatas de una marca pegada («K-7E#3@20») no: no se sabe si existen.

    Una marca que sólo nombran textos rechazados no tiene definición (R85: nada de marcas
    fantasma, «C-1 A 20 CM» no es C-20): la tiene si también la nombra sin ambigüedad otro texto
    del plano (una lectura, una etiqueta, la de una colocación: ``marcas_del_plano``)."""
    nombradas: list[str] = []
    # Cuántos textos rechazados nombran a cada marca como su única marca: no cuentan como «otro».
    solo_en_rechazos: dict[str, set[str]] = {}
    for r in inv.rechazos:
        if r.motivo not in ("ambigua", "varias_marcas", "sin_lector"):
            continue
        lectura = leer_marcas(r.texto, config)
        titulos_del_texto = titulos(r.texto, config)
        if not lectura.nombra and not titulos_del_texto:
            piezas = list(r.marcas)  # un renglón de pila: lo que nombran sus etiquetas
        elif lectura.tipo == "unica" and lectura.marca is not None:
            piezas = [lectura.marca]
            solo_en_rechazos.setdefault(normalizar_marca(lectura.marca, config), set()).add(
                r.entidad_id
            )
        elif lectura.tipo == "varias":
            piezas = lectura.piezas
        elif lectura.tipo == "ninguna":
            piezas = titulos_del_texto
        else:
            piezas = []  # ambigua: sólo candidatas
        for pieza in piezas:
            nombradas += extremos_de_rango(pieza, config) if es_rango(pieza, config) else [pieza]
    leidas = {normalizar_marca(s.mark, config) for s in inv.specs if s.source != "ia"}

    def en_otro_texto(marca: str) -> bool:
        normal = normalizar_marca(marca, config)
        textos = inv.marcas_del_plano.get(normal, 0)
        return normal in leidas or textos > len(solo_en_rechazos.get(normal, set()))

    return [m for m in dict.fromkeys(nombradas) if en_otro_texto(m)]


def _hojas_con_el_mismo_codigo(inv: ScheduleInventory) -> dict[str, list[str]]:
    """Los códigos de hoja que llevan dos o más marcos distintos (archivo y marco): el código no
    las distingue (lo usan las definiciones, como las reglas, en ``Dato.hoja``)."""
    llaves: dict[str, set[str]] = {}
    for spec in inv.specs:
        if spec.hoja and spec.hoja_llave:
            llaves.setdefault(spec.hoja, set()).add(spec.hoja_llave)
    for hoja in inv.textos_con_fragmento:
        if hoja.hoja and hoja.hoja_llave:
            llaves.setdefault(hoja.hoja, set()).add(hoja.hoja_llave)
    return {hoja: sorted(ks) for hoja, ks in llaves.items() if len(ks) > 1}


def _nombre_de_marco(llave: str) -> str:
    archivo, _, marco = llave.rpartition("#")
    return f"{marco or 'sin marco'} de {archivo.rsplit('/', 1)[-1]}"


def _definir(
    marca: str,
    specs: list[ElementSpec],
    inv: ScheduleInventory,
    config: TextPatternConfig,
    known: set[str],
    repetidas: dict[str, list[str]],
    familia: str | None = None,
    de_familia: bool = False,
) -> Definicion:
    lecturas = [s for s in specs if s.source != "ia"]
    de_ia = [s for s in specs if s.source == "ia"]
    avisos: list[str] = []
    familia = familia or _familia(marca, lecturas, de_ia, avisos)
    datos: dict[str, list[Dato]] = {campo: [] for campo in _NOMBRE}
    # R155: a leader's claim covers the parrillas too (R139) unless the mark's final family is a
    # beam's and something states it (its title's family word, a reading, the AI: R125, R130); a
    # family only its prefix gives exempts nothing.
    viga_dicha = familia in FAMILIAS_DE_VIGA and (
        de_familia or any(_dicha(s) and s.family == familia for s in [*lecturas, *de_ia])
    )

    # Las lecturas del plano: un dato por campo, ilegible si el texto está pero no se leyó.
    de_lecturas: dict[str, list[str]] = {}
    for s in lecturas:
        fuente = fuente_de_lectura(s)
        if s.section_cm is not None:
            seccion = _seccion(s.section_cm, familia)
            datos["seccion_cm"].append(_dato(s, fuente_de_seccion(s), seccion))
        elif "seccion" in s.campos_con_texto:
            datos["seccion_cm"].append(_dato(s, fuente, None, ilegible=True))
        armado = s.armado if s.armado is not None else _armado_de_textos(s, familia, avisos)
        for campo, _attr, de_texto in _ARMADO:
            valor = getattr(armado, campo) if armado is not None else []
            if valor:
                datos[campo].append(_dato(s, fuente, [v.model_copy(deep=True) for v in valor]))
            elif de_texto in s.campos_con_texto and not (
                campo == "parrillas" and viga_dicha and _por_flecha(s)
            ):
                datos[campo].append(_dato(s, fuente, None, ilegible=True))
        if s.length_m is not None:
            datos["longitud_m"].append(_dato(s, fuente, s.length_m))
        elif "longitud" in s.campos_con_texto:
            datos["longitud_m"].append(_dato(s, fuente, None, ilegible=True))
        for aviso in s.avisos:
            de_lecturas.setdefault(aviso, []).append(s.hoja or "sin hoja")
    avisos += [f"{a} ({', '.join(dict.fromkeys(h))})" for a, h in de_lecturas.items()]

    # Lo que dicen las notas de toda la familia de pilotes.
    if familia == "pilote" and inv.pile_length_m is not None:
        datos["longitud_m"].append(
            Dato(
                valor=inv.pile_length_m,
                fuente="nota",
                texto=f"longitud de pilote declarada en las notas: {inv.pile_length_m:g} m",
            )
        )

    # Lo que el plano dice de la marca y nadie leyó, sólo de los textos que la nombran con la
    # gramática de marcas (R90): con IA o sin ella.
    if not de_familia:
        _sin_leer(_textos_que_la_nombran(inv, marca, familia, config), lecturas, datos, avisos)

    # La IA: detrás del plano, y nunca en un campo que el plano tiene escrito (R69). Lo que la
    # bloquea sin nombrar la marca (la llave suelta, el respaldo) no da datos (R90): sólo la deja
    # fuera, y se dice.
    bloqueos = [] if de_familia else bloqueos_de(inv, marca, config, known, family=familia)
    bloqueos += [b for s in de_ia for b in s.bloqueos]
    bloqueados: dict[str, list[Bloqueo]] = {}
    for b in bloqueos:
        bloqueados.setdefault(_DE_CAMPO[b.campo], []).append(b)
    for s in de_ia:
        de_esta: dict[str, list[Dato]] = {campo: [] for campo in _NOMBRE}
        if s.section_cm is not None:
            de_esta["seccion_cm"].append(_dato(s, "ia", _seccion(s.section_cm, familia)))
        for _campo, attr, _de_texto in _ARMADO:
            escrito = getattr(s, attr)
            if escrito:
                # R125: con una familia que sólo da el prefijo, la de la IA (la que ella dice, si
                # la dice: ``_familia``) es la elegida; nada se tira por la familia.
                _de_la_ia(s, escrito, familia, de_esta, avisos)
        if s.length_m is not None:
            de_esta["longitud_m"].append(_dato(s, "ia", s.length_m))
        for campo, lista in de_esta.items():
            if not lista:
                continue
            del_plano = any(d.fuente != "ia" for d in datos[campo])
            if campo in bloqueados and not del_plano:
                textos = ", ".join(dict.fromkeys(f"«{b.texto}»" for b in bloqueados[campo]))
                avisos.append(
                    f"{_NOMBRE[campo]}: la lectura IA «{s.source_text}» no se toma: el plano "
                    f"tiene texto que puede ser de esta marca ({textos})"
                )
                continue
            datos[campo] += lista

    campos = {campo: elegir(lista, preferir_hoja=None) for campo, lista in datos.items()}
    for campo, dato in campos.items():
        if dato is not None and dato.ilegible and any(a.fuente == "ia" for a in dato.alternativas):
            avisos.append(
                f"{_NOMBRE[campo]}: el plano tiene texto para esta marca que no se leyó "
                f"(«{dato.texto}»); la lectura IA queda sólo como alternativa, por confirmar"
            )
        if dato is None or dato.fuente != "ia":
            continue
        if campo in bloqueados:
            raise ValueError(f"{marca}: la IA elegida en {campo}, que el plano bloquea")
    hojas = sorted(
        {s.hoja for s in lecturas if s.hoja}
        | {d.hoja for lista in datos.values() for d in lista if d.fuente != "ia" and d.hoja}
    )
    for hoja in sorted(set(hojas) & set(repetidas)):
        marcos = ", ".join(_nombre_de_marco(llave) for llave in repetidas[hoja])
        avisos.append(
            f"hoja «{hoja}»: {len(repetidas[hoja])} marcos distintos llevan ese código ({marcos});"
            " sus lecturas quedan bajo el mismo nombre y no se pueden separar por hoja"
        )
    return Definicion(
        marca=marca,
        familia=familia,
        hojas=hojas,
        avisos=list(dict.fromkeys(avisos)),
        seccion_no_rectangular=any(s.seccion_no_rectangular for s in lecturas),
        sin_leer={
            campo: ", ".join(dict.fromkeys(f"«{b.texto}»" for b in lista))
            for campo, lista in bloqueados.items()
            if campos[campo] is None and campo in _ARMADO_DE_LA_DEFINICION
        },
        para_muro_cm=None,  # R168: sus variantes las pone ``construir_definiciones``
        variantes=[],
        **campos,
    )


def _textos_que_la_nombran(
    inv: ScheduleInventory, marca: str, familia: str, config: TextPatternConfig
) -> list[Bloqueo]:
    """Los textos del plano que no se leyeron y que la gramática de marcas dice que nombran a
    ``marca`` (R90: comparada por ``normalizar_marca``, nunca por la llave suelta ni por el
    respaldo), cada uno con los campos que reclama. Su única marca, un miembro de su lista o un
    extremo de su rango, su título: es suyo (inequívoco). Una candidata de una marca pegada, una
    marca entre los extremos de un rango, una de las etiquetas entre las que dudó un renglón de
    pila: puede ser de otra (ambiguo). Un texto que una lectura de la marca leyó no cuenta: ésa
    ya tiene su dato."""
    leidos = {
        e
        for s in inv.specs
        if s.source != "ia" and normalizar_marca(s.mark, config) == marca
        for e in s.entidades
    }
    lectura_de = {
        e: s.source
        for s in inv.specs
        if s.source in ("cuadro", "detalle", "nota")
        for e in s.entidades
    }
    textos: list[tuple[str, str, str, list[str], str]] = []  # (entidad, texto, hoja, marcas, de)
    for r in inv.rechazos:
        if r.motivo in ("ambigua", "varias_marcas", "sin_lector"):
            textos.append((r.entidad_id, r.texto, r.hoja, list(r.marcas), r.motivo))
    for t in inv.textos_con_marca:
        textos.append((t.entidad_id, t.texto, t.hoja, list(t.marcas), "texto"))
    salida: list[Bloqueo] = []
    vistos: set[tuple[str, str]] = set()
    for entidad, texto, hoja, marcas, de in textos:
        if entidad in leidos or (entidad, texto) in vistos:
            continue
        vistos.add((entidad, texto))
        nombre = _como_la_nombra(texto, marcas, de, marca, config)
        if nombre is None:
            continue
        nota = leer_marcas(texto, config).nombra or bool(titulos(texto, config))
        fuente = lectura_de.get(entidad) or ("nota" if nota else "detalle")
        salida += [
            Bloqueo(
                campo=campo,
                texto=texto,
                entidades=[entidad],
                hoja=hoja,
                fuente=fuente,  # type: ignore[arg-type]
                por="rechazo" if de != "texto" else "texto",
                inequivoco=nombre,
            )
            for campo in campos_de_fragmento(texto, familia)
        ]
    return salida


def _como_la_nombra(
    texto: str, marcas: list[str], de: str, marca: str, config: TextPatternConfig
) -> bool | None:
    """Cómo nombra un texto a ``marca`` según la gramática: ``True`` sin ambigüedad (su única
    marca, un miembro de su lista, un extremo de su rango, su título), ``False`` como una de
    varias candidatas, ``None`` si no la nombra."""

    def normales(piezas: list[str]) -> set[str]:
        return {normalizar_marca(p, config) for p in piezas}

    lectura = leer_marcas(texto, config)
    if lectura.tipo == "unica" and lectura.marca is not None:
        return True if normalizar_marca(lectura.marca, config) == marca else None
    if lectura.tipo == "varias":
        explicitas: list[str] = []
        for pieza in lectura.piezas:
            explicitas += extremos_de_rango(pieza, config) if es_rango(pieza, config) else [pieza]
        if marca in normales(explicitas):
            return True
        entre = any(
            es_rango(p, config) and marca_en_rango(p, marca, config) for p in lectura.piezas
        )
        return False if entre else None
    if lectura.tipo == "ambigua":
        return False if marca in normales(lectura.piezas) else None
    titulos_del_texto = titulos(texto, config)
    if titulos_del_texto:
        if marca not in normales(titulos_del_texto):
            return None
        return len(titulos_del_texto) == 1
    # Un renglón de pila que no nombra marcas: las de sus etiquetas (la asociación las leyó con
    # la misma gramática). Entre dos etiquetas dudó: ambiguo; la de varias marcas: suyo.
    if de == "texto" or marca not in normales(
        [e for p in marcas for e in (extremos_de_rango(p, config) if es_rango(p, config) else [p])]
    ):
        return None
    return de == "varias_marcas"


def _sin_leer(
    bloqueos: list[Bloqueo],
    lecturas: list[ElementSpec],
    datos: dict[str, list[Dato]],
    avisos: list[str],
) -> None:
    """Los textos del plano que dicen algo de la marca y no se leyeron, como datos ilegibles de
    su campo (R77). Un texto que nombra la marca y ninguna otra (su nota, su título, su lista) es
    suyo: siempre es un dato. Uno que puede ser de otra marca (un renglón de pila entre dos
    etiquetas, una candidata, una coincidencia suelta, una lectura de otra marca con la misma
    llave suelta) es un dato sólo si la marca no tiene uno propio en ese campo; si lo tiene, es
    un aviso (R74). Una lectura de la marca misma ya tiene su dato."""
    propias = {tuple(s.entidades) for s in lecturas}
    # R89: un mismo texto (el bloqueo que trae la lectura IA y el que se calcula aquí) es uno:
    # se junta por campo y entidad, y es inequívoco si alguna de sus copias lo es.
    por_texto: dict[tuple[str, tuple[str, ...]], Bloqueo] = {}
    for b in bloqueos:
        if b.por == "lectura" and tuple(b.entidades) in propias:
            continue
        llave = (b.campo, tuple(b.entidades))
        previo = por_texto.get(llave)
        suyo = b.inequivoco and b.por != "lectura"
        if previo is None:
            por_texto[llave] = b.model_copy(update={"inequivoco": suyo})
        elif suyo and not previo.inequivoco:
            por_texto[llave] = previo.model_copy(update={"inequivoco": True})
    vistos: set[tuple[str, tuple[str, ...], str]] = set()
    dudosos: list[Bloqueo] = []
    for b in sorted(por_texto.values(), key=lambda b: (b.campo, b.entidades, b.texto)):
        if b.inequivoco:
            _ilegible(b, datos, vistos)
        else:
            dudosos.append(b)
    for b in dudosos:
        campo = _DE_CAMPO[b.campo]
        if any(d.fuente != "ia" for d in datos[campo]):
            avisos.append(
                f"{_NOMBRE[campo]}: un texto que puede ser de esta marca o de otra no se leyó "
                f"(«{b.texto}», {b.hoja or 'sin hoja'}); se usa lo que dicen sus lecturas"
            )
        else:
            _ilegible(b, datos, vistos)


def _ilegible(
    b: Bloqueo, datos: dict[str, list[Dato]], vistos: set[tuple[str, tuple[str, ...], str]]
) -> None:
    llave = (b.campo, tuple(b.entidades), "")
    if llave in vistos:
        return
    vistos.add(llave)
    datos[_DE_CAMPO[b.campo]].append(
        Dato(
            valor=None,
            ilegible=True,
            fuente=b.fuente,
            hoja=b.hoja,
            texto=b.texto,
            entidades=list(b.entidades),
        )
    )


def _de_la_ia(
    s: ElementSpec, escrito: str, familia: str, datos: dict[str, list[Dato]], avisos: list[str]
) -> None:
    """Un texto de la lectura IA, leído entero con el parser (R80): cada cosa que da va a su
    campo, diga la IA lo que diga («4#3 E#2@15» como varillas trae también sus estribos); lo que
    no se lee se dice, nunca se tira callado."""
    leido = parsear_armado([escrito], familia)
    tomados = [campo for campo, _attr, _t in _ARMADO if getattr(leido, campo)]
    for campo in tomados:
        datos[campo].append(
            _dato(s, "ia", getattr(leido, campo), texto=f"{s.source_text} · «{escrito}»")
        )
    if leido.avisos or not tomados:
        motivo = "; ".join(leido.avisos) or "no da varillas, estribos ni parrillas"
        avisos.append(f"la lectura IA «{escrito}» no se lee entera: {motivo}")


def _dato(
    s: ElementSpec, fuente: Fuente, valor: Any, ilegible: bool = False, texto: str | None = None
) -> Dato:
    """El dato de un campo de la lectura ``s``, con su fuente, su hoja, su texto y sus
    entidades."""
    return Dato(
        valor=valor,
        fuente=fuente,
        hoja=s.hoja,
        texto=s.source_text if texto is None else texto,
        entidades=list(s.entidades),
        ilegible=ilegible,
    )


def _armado_de_textos(spec: ElementSpec, familia: str, avisos: list[str]) -> Armado | None:
    """El armado de una lectura del plano que no trae el suyo estructurado (un lector por
    disciplina): sus textos canónicos, leídos con el parser."""
    textos = [t for t in (spec.rebar, spec.stirrups, spec.mesh) if t]
    if not textos:
        return None
    armado = parsear_armado(textos, familia)
    avisos += [f"{spec.hoja or 'sin hoja'}: {aviso}" for aviso in armado.avisos]
    return armado


def _por_flecha(s: ElementSpec) -> bool:
    """Si la lectura es (o lleva) el reclamo de un título señalado por flecha (R124, R139)."""
    return any(a.endswith(_SENALADA) for a in s.avisos)


def _dicha(s: ElementSpec) -> bool:
    """Si la lectura dice una familia (no «elemento» ni sólo el prefijo de su marca, R125)."""
    return bool(s.family) and s.family != "elemento" and not s.familia_supuesta


def _familia(
    marca: str, lecturas: list[ElementSpec], de_ia: list[ElementSpec], avisos: list[str]
) -> str:
    """La familia de una marca: la que dice su lectura del plano de más rango (la palabra de
    familia de su propio título, R130, la dice); si el plano no la dice —sólo «elemento» (no se
    sabe) o sólo el prefijo de la marca, R125—, la que dice la IA, y se avisa (R80); si nadie la
    dice, la de su prefijo. Si las lecturas no coinciden se dice cuáles, nunca se escoge
    callado."""
    dichas: dict[str, list[str]] = {}
    for s in [*lecturas, *de_ia]:
        if s.family and s.family != "elemento":
            quien = "IA" if s.source == "ia" else (s.hoja or "sin hoja")
            dichas.setdefault(s.family, []).append(quien)
    del_plano = sorted(lecturas, key=lambda s: -PRECEDENCIA[fuente_de_lectura(s)])
    elegida = next((s.family for s in del_plano if _dicha(s)), None)
    de_prefijo = next((s.family for s in del_plano if s.family != "elemento"), None)
    if elegida is None:
        de_la_ia = next((s.family for s in de_ia if _dicha(s)), None)
        if de_la_ia is not None and lecturas:
            dice = f"sólo el prefijo de la marca: {de_prefijo}" if de_prefijo else "«elemento»"
            avisos.append(f"familia: el plano no la dice ({dice}); se toma la de la IA: {de_la_ia}")
        elegida = de_la_ia
    if elegida is None:
        elegida = de_prefijo or family_of_mark(marca)
    if len(dichas) > 1:
        lista = ", ".join(f"{f} ({', '.join(dict.fromkeys(q))})" for f, q in sorted(dichas.items()))
        avisos.append(f"familia: las lecturas no coinciden — {lista}; se toma {elegida}")
    return elegida


def asignar_formas(
    estribos: list[JuegoEstribos], longitudinales: list[GrupoVarillas]
) -> tuple[list[JuegoEstribos], list[str]]:
    """Las formas de cada pieza de cada juego de estribos, supuestas por la práctica del taller
    mientras no se lea el corte dibujado (E3), con ``formas_fuente="supuesto"``. Con N varillas
    longitudinales en total: 1 pieza → perimetral; 2 → perimetral y rombo si N ≥ 8, si no
    perimetral e interior; 3 → perimetral, rombo e interior; 4 → perimetral, rombo, interior e
    interior; las grapas, grapa cada una. Lo demás (5 piezas o más, ligas, sin varillas
    longitudinales) se queda sin formas y se avisa. Las formas que ya dice el plano
    (``formas_fuente`` puesto) no se tocan. Devuelve copias: no cambia lo que recibe."""
    total = sum(g.cantidad for g in longitudinales)
    salida: list[JuegoEstribos] = []
    avisos: list[str] = []
    for juego in estribos:
        j = juego.model_copy(deep=True)
        salida.append(j)
        if j.formas_fuente is not None:
            continue  # lo dice el plano
        if j.referencia is not None and j.cantidad == 1:
            # «E#3 VER CORTE»: sin cuenta de piezas, las formas están en el corte (R80).
            avisos.append(
                f"{_juego(j)}: sin formas supuestas (el plano remite a «{j.referencia}» y no "
                "dice cuántas piezas); las dirá el corte dibujado"
            )
            continue
        formas = _formas(j, total)
        if formas is None:
            avisos.append(_sin_formas(j, total))
            continue
        j.formas, j.formas_fuente = formas, "supuesto"
        if j.referencia is not None:
            avisos.append(
                f"{_juego(j)}: formas supuestas ({', '.join(formas)}); el plano remite a "
                f"«{j.referencia}», que todavía no se lee"
            )
    return salida, avisos


def _formas(j: JuegoEstribos, total: int) -> list[Forma] | None:
    if j.tipo == "grapa":
        return ["grapa"] * j.cantidad
    if j.tipo != "estribo" or total == 0:
        return None
    por_piezas: dict[int, list[Forma]] = {
        1: ["perimetral"],
        2: ["perimetral", "rombo"] if total >= 8 else ["perimetral", "interior"],
        3: ["perimetral", "rombo", "interior"],
        4: ["perimetral", "rombo", "interior", "interior"],
    }
    return por_piezas.get(j.cantidad)


def _juego(j: JuegoEstribos) -> str:
    return f"{j.cantidad} {j.tipo}{'s' if j.cantidad > 1 else ''} del #{j.numero}"


def _sin_formas(j: JuegoEstribos, total: int) -> str:
    if j.tipo == "liga":
        por = "son ligas"
    elif total == 0:
        por = "no hay varillas longitudinales"
    else:
        por = f"{j.cantidad} piezas por juego"
    return f"{_juego(j)}: sin formas supuestas ({por}); las dirá el corte dibujado"


# Que las fuentes de ``Source`` tengan todas su lugar en el mapa (una nueva revienta aquí).
if {s for s, _ in FUENTE_DE_LECTURA} != set(get_args(Source)):
    raise ValueError("FUENTE_DE_LECTURA no cubre todas las fuentes de las lecturas")
