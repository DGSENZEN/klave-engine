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
    Campo,
    ElementSpec,
    Metodo,
    ScheduleInventory,
    Source,
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
from klave_engine.estructura.marcas import marca_normalizada

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
}


class Definicion(BaseModel):
    """Lo que el plano dice de una marca (o de una familia, para las notas de familia), campo por
    campo. ``seccion_cm`` va con sus dos lados, el menor primero (los lectores no coinciden en
    cuál es el ancho: las notas y los cuadros dan los lados ordenados); ``longitudinales``,
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


def fuente_de_lectura(spec: ElementSpec) -> Fuente:
    """La fuente de una lectura (``FUENTE_DE_LECTURA``); un par que nadie mapeó revienta."""
    try:
        return FUENTE_DE_LECTURA[(spec.source, spec.metodo)]
    except KeyError:
        raise ValueError(
            f"lectura de {spec.mark} con fuente «{spec.source}» y método «{spec.metodo}»: "
            "ese par no tiene fuente en FUENTE_DE_LECTURA"
        ) from None


def _seccion(valor: tuple[int, int]) -> tuple[int, int]:
    a, b = sorted(valor)
    return (a, b)


def _es_de_familia(spec: ElementSpec) -> bool:
    """Una nota de familia («DALA 15X30 4#3 E#2@20»): su marca es el nombre de su familia."""
    return spec.source == "nota" and spec.mark == spec.family.upper()


def construir_definiciones(
    inv: ScheduleInventory, config: TextPatternConfig | None = None
) -> tuple[dict[str, Definicion], dict[str, Definicion]]:
    """Las definiciones del plano: (por marca, por familia). Las lecturas se juntan por
    ``normalizar_marca`` y las notas de familia por su familia; cada campo es el ``Dato`` que
    ``elegir`` escoge entre las lecturas (sin hoja preferida: la de cada colocación la decide la
    Tarea 9 con ``para_hoja``)."""
    config = config or TextPatternConfig()
    por_marca: dict[str, list[ElementSpec]] = {}
    por_familia: dict[str, list[ElementSpec]] = {}
    for spec in inv.specs:
        if _es_de_familia(spec):
            por_familia.setdefault(spec.family, []).append(spec)
        else:
            por_marca.setdefault(normalizar_marca(spec.mark, config), []).append(spec)
    repetidas = _hojas_con_el_mismo_codigo(inv)
    marcas = {marca: _definir(marca, specs, inv, repetidas) for marca, specs in por_marca.items()}
    familias = {
        familia: _definir(familia.upper(), specs, inv, repetidas, familia=familia)
        for familia, specs in por_familia.items()
    }
    return marcas, familias


def _hojas_con_el_mismo_codigo(inv: ScheduleInventory) -> dict[str, list[str]]:
    """Los códigos de hoja que llevan dos o más marcos distintos (archivo y marco): el código no
    las distingue (lo usan las definiciones, como las reglas, en ``Dato.hoja``)."""
    llaves: dict[str, set[str]] = {}
    for spec in inv.specs:
        if spec.hoja and spec.hoja_llave:
            llaves.setdefault(spec.hoja, set()).add(spec.hoja_llave)
    for linea in inv.textos_con_fragmento:
        if linea.hoja and linea.hoja_llave:
            llaves.setdefault(linea.hoja, set()).add(linea.hoja_llave)
    return {hoja: sorted(ks) for hoja, ks in llaves.items() if len(ks) > 1}


def _nombre_de_marco(llave: str) -> str:
    archivo, _, marco = llave.rpartition("#")
    return f"{marco or 'sin marco'} de {archivo.rsplit('/', 1)[-1]}"


def _definir(
    marca: str,
    specs: list[ElementSpec],
    inv: ScheduleInventory,
    repetidas: dict[str, list[str]],
    familia: str | None = None,
) -> Definicion:
    lecturas = [s for s in specs if s.source != "ia"]
    de_ia = [s for s in specs if s.source == "ia"]
    avisos: list[str] = []
    familia = familia or _familia(lecturas, de_ia, avisos)
    datos: dict[str, list[Dato]] = {campo: [] for campo in _NOMBRE}

    # Las lecturas del plano: un dato por campo, ilegible si el texto está pero no se leyó.
    de_lecturas: dict[str, list[str]] = {}
    for s in lecturas:
        fuente = fuente_de_lectura(s)
        if s.section_cm is not None:
            datos["seccion_cm"].append(_dato(s, fuente, _seccion(s.section_cm)))
        elif "seccion" in s.campos_con_texto:
            datos["seccion_cm"].append(_dato(s, fuente, None, ilegible=True))
        armado = s.armado if s.armado is not None else _armado_de_textos(s, familia, avisos)
        for campo, _attr, de_texto in _ARMADO:
            valor = getattr(armado, campo) if armado is not None else []
            if valor:
                datos[campo].append(_dato(s, fuente, [v.model_copy(deep=True) for v in valor]))
            elif de_texto in s.campos_con_texto:
                datos[campo].append(_dato(s, fuente, None, ilegible=True))
        if s.length_m is not None:
            datos["longitud_m"].append(_dato(s, fuente, s.length_m))
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

    # La IA: detrás del plano, y nunca en un campo que el plano tiene escrito (R69).
    ya: set[tuple[str, tuple[str, ...], str]] = set()
    for s in de_ia:
        if s.section_cm is not None:
            datos["seccion_cm"].append(_dato(s, "ia", _seccion(s.section_cm)))
        for campo, attr, _de_texto in _ARMADO:
            escrito = getattr(s, attr)
            if not escrito:
                continue
            leido = parsear_armado([escrito], familia)
            valor = getattr(leido, campo)
            if not valor or leido.avisos:
                avisos.append(
                    f"{_NOMBRE[campo]}: la lectura IA «{escrito}» no se lee como "
                    f"{_NOMBRE[campo]}: no se toma"
                )
                continue
            datos[campo].append(_dato(s, "ia", valor, texto=f"{s.source_text} · «{escrito}»"))
        if s.length_m is not None:
            datos["longitud_m"].append(_dato(s, "ia", s.length_m))
        for campo, dato, aviso in _lo_que_bloquea(s, lecturas, ya):
            if dato is not None:
                datos[campo].append(dato)
            avisos.append(aviso)

    campos = {campo: elegir(lista, preferir_hoja=None) for campo, lista in datos.items()}
    for campo, dato in campos.items():
        # Por construcción un campo bloqueado tiene un dato del plano: la IA nunca gana ahí.
        if dato is not None and dato.fuente == "ia":
            assert not any(_DE_CAMPO[c] == campo for s in de_ia for c in s.campos_bloqueados), (
                f"{marca}: la IA elegida en {campo}, que el plano bloquea"
            )
    hojas = sorted({s.hoja for s in lecturas if s.hoja})
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
        **campos,
    )


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


def _lo_que_bloquea(
    ia: ElementSpec,
    lecturas: list[ElementSpec],
    ya: set[tuple[str, tuple[str, ...], str]],
) -> list[tuple[str, Dato | None, str]]:
    """Por cada campo que el plano le bloquea a la lectura IA ``ia`` (R69): un dato ilegible del
    plano por cada texto que lo bloquea y que no es ya una lectura de esta definición con ese
    campo (ésa tiene su propio dato, leído o ilegible), y el aviso del campo. Devuelve (campo de
    la definición, dato o ``None``, aviso)."""
    salida: list[tuple[str, Dato | None, str]] = []
    for campo in ia.campos_bloqueados:
        propias = {tuple(s.entidades) for s in lecturas if campo in s.campos_con_texto}
        nuevos: list[Dato] = []
        for b in ia.bloqueos:
            llave = (campo, tuple(b.entidades), b.texto)
            if b.campo != campo or (b.por == "lectura" and tuple(b.entidades) in propias):
                continue
            if llave not in ya:
                ya.add(llave)
                nuevos.append(
                    Dato(
                        valor=None,
                        ilegible=True,
                        fuente=b.fuente,
                        hoja=b.hoja,
                        texto=b.texto,
                        entidades=list(b.entidades),
                    )
                )
        textos = list(dict.fromkeys(b.texto for b in ia.bloqueos if b.campo == campo))
        if len(textos) > 3:
            textos = [*textos[:3], f"y {len(textos) - 3} más"]
        aviso = (
            f"{_NOMBRE[_DE_CAMPO[campo]]}: el plano tiene texto para esta marca "
            f"({', '.join(textos)}); la lectura IA «{ia.source_text}» queda sólo como "
            "alternativa, por confirmar"
        )
        salida += [(_DE_CAMPO[campo], dato, aviso) for dato in nuevos] or [
            (_DE_CAMPO[campo], None, aviso)
        ]
    return salida


def _armado_de_textos(spec: ElementSpec, familia: str, avisos: list[str]) -> Armado | None:
    """El armado de una lectura del plano que no trae el suyo estructurado (un lector por
    disciplina): sus textos canónicos, leídos con el parser."""
    textos = [t for t in (spec.rebar, spec.stirrups, spec.mesh) if t]
    if not textos:
        return None
    armado = parsear_armado(textos, familia)
    avisos += [f"{spec.hoja or 'sin hoja'}: {aviso}" for aviso in armado.avisos]
    return armado


def _familia(lecturas: list[ElementSpec], de_ia: list[ElementSpec], avisos: list[str]) -> str:
    """La familia de una marca: la de su lectura del plano de más rango (la IA sólo si el plano
    no la lee). Si las lecturas no coinciden se dice cuáles, nunca se escoge callado. «elemento»
    (no se sabe) no es una familia."""
    dichas: dict[str, list[str]] = {}
    for s in [*lecturas, *de_ia]:
        if s.family and s.family != "elemento":
            quien = "IA" if s.source == "ia" else (s.hoja or "sin hoja")
            dichas.setdefault(s.family, []).append(quien)
    candidatas = sorted(
        lecturas or de_ia,
        key=lambda s: -PRECEDENCIA[fuente_de_lectura(s)],
    )
    elegida = next((s.family for s in candidatas if s.family != "elemento"), None)
    if elegida is None:
        elegida = (lecturas or de_ia)[0].family if (lecturas or de_ia) else "elemento"
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
assert {s for s, _ in FUENTE_DE_LECTURA} == set(get_args(Source))
