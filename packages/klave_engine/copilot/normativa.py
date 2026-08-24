"""La normativa mexicana de obra que un ingeniero de costos consulta a diario.

Cada entrada aquí fue **verificada literalmente** contra el PDF oficial de la
Cámara de Diputados o del DOF: el texto entre comillas es el texto de la ley,
no una paráfrasis. Esa disciplina es la razón de que este módulo exista. Un
copiloto que cita un artículo inventado le cuesta a alguien una licitación o
su cédula, y en ese caso vale mucho más no tener copiloto.

Tres reglas que gobiernan este archivo:

1. **Nada entra sin fuente.** Si no se pudo abrir el documento oficial y leer
   el texto, no se escribe aquí. Una entrada sin `cita` no existe.
2. **Los números de artículo no son eternos.** El Reglamento vigente es el de
   2010; su ley se reformó en 2025 y el Transitorio Sexto ordenó actualizar el
   Reglamento en noventa días hábiles, plazo que ya venció sin publicación. Hay
   contradicciones vivas entre ambos. Por eso cada entrada declara su
   `vigencia` y el copiloto la muestra: la respuesta correcta hoy puede dejar
   de serlo, y quien lea debe saberlo.
3. **Esto orienta, no dictamina.** La entrada dice dónde está escrito; el
   ingeniero lee el artículo. El copiloto nunca afirma que un caso concreto
   cumple o no cumple.

Ámbito: obra pública federal. La obra estatal (CDMX, Jalisco, Oaxaca…) se rige
por sus propias leyes con articulado distinto, y la obra privada no tiene
formato obligatorio: lo que manda ahí es el contrato.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LOPSRM = "LOPSRM"
RLOPSRM = "RLOPSRM"

VIGENCIA_LEY = "Última reforma DOF 14-11-2025"
VIGENCIA_REGLAMENTO = "DOF 28-07-2010, última reforma DOF 24-02-2023"

URL_LEY = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LOPSRM.pdf"
URL_REGLAMENTO = "https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LOPSRM.pdf"

# La advertencia que acompaña a toda respuesta de obra pública federal.
AVISO_VIGENCIA = (
    "El Reglamento vigente es el de 2010; su ley se reformó en 2025 y el "
    "reglamento nuevo aún no se publica, así que hay artículos del Reglamento "
    "que ya no concuerdan con la Ley. Verifica el texto vigente antes de "
    "apoyarte en un número de artículo."
)


@dataclass
class Entrada:
    """Un punto de normativa, con el texto de la ley y de dónde salió."""

    id: str
    titulo: str
    # Lo que significa, en el lenguaje del oficio.
    resumen: str
    # El texto de la ley, literal. Vacío solo cuando la entrada es de Klave.
    cita: str = ""
    fuente: str = ""  # "RLOPSRM art. 45, apartado A, fracción X"
    url: str = ""
    vigencia: str = ""
    # Qué hace Klave con esto, cuando hace algo.
    en_klave: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def referencia(self) -> str:
        partes = [self.fuente]
        if self.vigencia:
            partes.append(f"({self.vigencia})")
        return " ".join(p for p in partes if p)


def _r(articulo: str) -> dict:
    return {"fuente": f"{RLOPSRM} {articulo}", "url": URL_REGLAMENTO,
            "vigencia": VIGENCIA_REGLAMENTO}


def _l(articulo: str) -> dict:
    return {"fuente": f"{LOPSRM} {articulo}", "url": URL_LEY, "vigencia": VIGENCIA_LEY}


NORMATIVA: list[Entrada] = [
    # ---------------------------------------------------- programas
    Entrada(
        id="programa-ejecucion",
        titulo="Programa de ejecución de los trabajos",
        resumen=(
            "El programa calendarizado por partidas y subpartidas de todos los "
            "conceptos. La ley prefiere el diagrama de barras; la red con ruta "
            "crítica es alternativa, no obligatoria, en precios unitarios."
        ),
        cita=(
            "Programa de ejecución convenido conforme al catálogo de conceptos con sus "
            "erogaciones, calendarizado y cuantificado de acuerdo a los periodos "
            "determinados por la convocante, dividido en partidas y subpartidas, del "
            "total de los conceptos de trabajo, utilizando preferentemente diagramas de "
            "barras, o bien, redes de actividades con ruta crítica"
        ),
        **_r("art. 45, apartado A, fracción X"),
        en_klave=(
            "Klave calcula la red completa por dentro (para que las barras sean "
            "defendibles) y entrega el diagrama de barras por concepto en la hoja "
            "Programa del Excel."
        ),
        tags=["programa", "ruta crítica", "gantt", "licitación", "barras"],
    ),
    Entrada(
        id="programas-erogaciones",
        titulo="Los cuatro programas de erogaciones",
        resumen=(
            "Mano de obra, maquinaria y equipo, materiales y equipo de instalación "
            "permanente, y personal técnico-administrativo. Ojo: la mano de obra "
            "(costo directo) y el personal técnico (costo indirecto) son programas "
            "distintos, no el mismo."
        ),
        cita=(
            "Programas de erogaciones a costo directo, calendarizados y cuantificados "
            "en partidas y subpartidas de utilización, conforme a los periodos "
            "determinados por la convocante, para los siguientes rubros: a) De la mano "
            "de obra; b) De la maquinaria y equipo para construcción, identificando su "
            "tipo y características; c) De los materiales y equipos de instalación "
            "permanente expresados en unidades convencionales y volúmenes requeridos, y "
            "d) De utilización del personal profesional técnico, administrativo y de "
            "servicio encargado de la dirección, administración y ejecución de los "
            "trabajos."
        ),
        **_r("art. 45, apartado A, fracción XI"),
        en_klave=(
            "Klave genera los tres primeros desde la explosión de insumos puesta sobre "
            "el calendario del programa. El de personal técnico es costo indirecto: no "
            "está en las matrices, así que sale vacío diciendo de dónde debe venir — "
            "inventarlo sería inventar dinero."
        ),
        tags=["programas", "erogaciones", "suministros", "mano de obra", "maquinaria",
              "materiales", "personal técnico", "licitación"],
    ),
    Entrada(
        id="red-actividades",
        titulo="Red de actividades: qué debe permitir calcular",
        resumen=(
            "Si entregas red, la ley pide que permita calcular fechas de inicio, de "
            "terminación y las holguras de cada actividad. Las holguras son requisito "
            "explícito."
        ),
        cita=(
            "La red de actividades es la representación gráfica del proceso constructivo "
            "[…] en la que se deberán contemplar las actividades a realizar, indicando su "
            "duración y secuencia de ejecución, así como las relaciones existentes con "
            "las actividades que las anteceden y las que le proceden, a efecto de "
            "calcular las fechas de inicio y de terminación y las holguras de cada una "
            "de ellas."
        ),
        **_r("art. 224"),
        en_klave=(
            "El programa de Klave calcula holgura total y libre por actividad y marca la "
            "ruta crítica; ambas viajan en el Excel."
        ),
        tags=["red de actividades", "holgura", "ruta crítica", "cpm", "precio alzado"],
    ),
    Entrada(
        id="precio-alzado-red",
        titulo="Precio alzado: la red sí es obligatoria",
        resumen=(
            "En precio alzado cambia el requisito: red de actividades calendarizada y "
            "cédula de avances y pagos programados. La bisagra es la modalidad de pago, "
            "no el gusto de la convocante."
        ),
        cita=(
            "Red de actividades, calendarizada e indicando la duración de cada actividad "
            "a ejecutar, o bien, la ruta crítica"
        ),
        **_r("art. 45, apartado B, fracción II"),
        tags=["precio alzado", "red de actividades", "cédula de avances"],
    ),
    Entrada(
        id="plazo-dias-naturales",
        titulo="El plazo de ejecución se cuenta en días naturales",
        resumen=(
            "La convocatoria fija el plazo en días naturales. Un programa calculado en "
            "jornadas y reportado como plazo contractual queda corto: con semana de seis "
            "días, seis hábiles son siete naturales."
        ),
        cita=(
            "Plazo de ejecución de los trabajos determinado en días naturales, indicando "
            "la fecha estimada de inicio de los mismos"
        ),
        **_l("art. 31, fracción V"),
        en_klave=(
            "Klave calcula en jornadas y reporta las dos cifras: el plazo hábil y el "
            "contractual en días naturales."
        ),
        tags=["plazo", "días naturales", "días hábiles", "calendario"],
    ),
    # ---------------------------------------------------- rendimientos
    Entrada(
        id="rendimiento-mano-obra",
        titulo="Rendimiento de mano de obra: la definición legal",
        resumen=(
            "El costo de mano de obra es Mo = Sr / R, y R está expresado **por jornada "
            "de ocho horas**. De ahí sale la duración: cantidad ÷ (R × cuadrillas). "
            "Multiplicar además por la jornada sobre-divide."
        ),
        cita=(
            "«R» Representa el rendimiento, es decir, la cantidad de trabajo que "
            "desarrolla el personal que interviene directamente en la ejecución del "
            "concepto de trabajo por jornada de ocho horas. Para realizar la evaluación "
            "del rendimiento, se deberá considerar en todo momento el tipo de trabajo a "
            "desarrollar y las condiciones ambientales, topográficas y en general "
            "aquéllas que predominen en la zona o región donde se ejecuten."
        ),
        **_r("art. 190"),
        en_klave=(
            "Klave toma el rendimiento de la propia matriz del concepto, no de un dato "
            "aparte: así el programa y el dinero no pueden contradecirse."
        ),
        tags=["rendimiento", "mano de obra", "duración", "matriz", "apu", "cuadrilla"],
    ),
    Entrada(
        id="rendimiento-maquinaria",
        titulo="Rendimiento de maquinaria: por hora efectiva",
        resumen=(
            "Para maquinaria el costo es ME = Phm / Rhm, con el rendimiento en la misma "
            "unidad de tiempo que el costo horario: la hora efectiva. Tratar una tasa "
            "horaria como diaria es el error que hace incongruente un programa."
        ),
        cita="ME = Phm / Rhm",
        **_r("art. 194"),
        en_klave=(
            "Cuando la matriz no tiene cuadrilla por jornada, Klave lee las horas "
            "efectivas del equipo y las convierte a jornada de ocho horas."
        ),
        tags=["rendimiento", "maquinaria", "costo horario", "hora efectiva"],
    ),
    # ---------------------------------------------------- evaluación
    Entrada(
        id="evaluacion-congruencia",
        titulo="Qué revisa la convocante: congruencia entre programas",
        resumen=(
            "El criterio central de la evaluación técnica no es la belleza del Gantt: es "
            "que los programas concuerden entre sí y con los rendimientos de tus "
            "matrices. Es la causa de descalificación más común."
        ),
        cita=(
            "a) Que el programa de ejecución de los trabajos corresponda al plazo "
            "establecido por la convocante; b) Que los programas específicos "
            "cuantificados y calendarizados de suministros y utilización sean congruentes "
            "con el programa calendarizado de ejecución general de los trabajos; c) Que "
            "los programas de suministro y utilización de materiales, mano de obra y "
            "maquinaria y equipo de construcción sean congruentes con los consumos y "
            "rendimientos considerados por el licitante y en el procedimiento "
            "constructivo a realizar; […] e) Que los insumos propuestos por el licitante "
            "correspondan a los periodos presentados en los programas"
        ),
        **_r("art. 64, apartado A, fracción I"),
        en_klave=(
            "Klave deriva los programas de las mismas matrices que costean la obra, así "
            "que el inciso c) se cumple por construcción y no por revisión manual."
        ),
        tags=["evaluación", "congruencia", "descalificación", "licitación", "revisión"],
    ),
    # ---------------------------------------------------- dinero
    Entrada(
        id="anticipo",
        titulo="Anticipo: hasta 30 %, y es techo, no norma",
        resumen=(
            "La dependencia puede otorgar hasta 30 % de la asignación del ejercicio, y "
            "puede excederlo con autorización escrita del titular. En la práctica muchas "
            "convocatorias dan 10 %. El anticipo es obligatorio considerarlo en el costo "
            "de financiamiento."
        ),
        cita=(
            "podrán otorgar hasta un treinta por ciento de la asignación presupuestaria "
            "correspondiente al contrato para cada ejercicio"
        ),
        **_l("art. 50, fracción II"),
        en_klave="El porcentaje es un parámetro del proyecto en Klave, no una constante.",
        tags=["anticipo", "financiamiento", "flujo", "porcentaje"],
    ),
    Entrada(
        id="amortizacion-anticipo",
        titulo="Amortización del anticipo",
        resumen=(
            "Se amortiza de cada estimación en proporción al porcentaje otorgado, y lo "
            "que falte por amortizar se liquida en la estimación final."
        ),
        cita=(
            "se amortizará del importe de cada estimación […] conforme al programa de "
            "ejecución convenido; dicha amortización deberá ser proporcional al "
            "porcentaje de anticipo otorgado"
        ),
        **_r("art. 143, fracción I"),
        tags=["anticipo", "amortización", "estimación", "flujo"],
    ),
    Entrada(
        id="estimaciones",
        titulo="Estimaciones: periodicidad y plazos de pago",
        resumen=(
            "En precios unitarios, periodicidad no mayor de un mes. El contratista "
            "presenta dentro de los 6 días naturales del corte, la residencia revisa y "
            "autoriza en 15 días naturales, y el pago va en 20 días naturales desde la "
            "autorización. El ciclo real de caja ronda los 41–51 días."
        ),
        **_l("art. 54"),
        en_klave=(
            "El flujo de Klave debe modelar ese desfase; el costo de financiamiento sale "
            "de ahí, no de suponer cobro inmediato."
        ),
        tags=["estimación", "pago", "flujo", "financiamiento", "periodicidad"],
    ),
    Entrada(
        id="penas-convencionales",
        titulo="Penas convencionales y retenciones",
        resumen=(
            "Las penas se calculan sobre los trabajos no ejecutados conforme al programa "
            "convenido, midiendo el avance físico a la fecha de corte. Las retenciones "
            "por atraso son recuperables si te regularizas. El programa no es un adorno: "
            "es la vara con la que te miden."
        ),
        cita=(
            "Las penas convencionales serán determinadas en función del importe de los "
            "trabajos que no se hayan ejecutado […] conforme al programa de ejecución "
            "convenido, considerando […] el avance físico […] conforme a la fecha de "
            "corte para el pago de estimaciones."
        ),
        **_r("art. 86"),
        tags=["penas", "retenciones", "atraso", "avance físico", "programa"],
    ),
    Entrada(
        id="avance-fisico-financiero",
        titulo="Avance físico y avance financiero no son la misma curva",
        resumen=(
            "El financiero es el porcentaje de lo **pagado** contra el importe "
            "contractual; el físico es el porcentaje de lo **ejecutado y verificado** "
            "contra el programa convenido. Van desfasadas y deben graficarse aparte."
        ),
        **_r("art. 2, fracciones VI y VII"),
        tags=["avance físico", "avance financiero", "curva s", "flujo"],
    ),
    # ---------------------------------------------------- Klave's own rules
    Entrada(
        id="klave-sin-unidades",
        titulo="Por qué un plano sin unidades no lleva precios",
        resumen=(
            "Si el archivo no declara una unidad confiable, las cantidades quedan en "
            "unidades de dibujo y ninguna línea lleva precio. Un total calculado sobre "
            "una unidad supuesta parece un presupuesto y no lo es; Klave prefiere no "
            "dar precio a dar uno equivocado."
        ),
        fuente="Klave · principio de honestidad",
        en_klave=(
            "Confirma la unidad en Resumen → Ruta de verificación y todo se recalcula."
        ),
        tags=["unidades", "sin unidades", "verificación", "precio", "bloqueante"],
    ),
    Entrada(
        id="klave-sin-precio",
        titulo="Por qué un concepto aparece «sin precio» y no en cero",
        resumen=(
            "Cuando un concepto tiene cantidad pero no matriz ni P.U. adoptado, su "
            "importe es desconocido, no cero. Ponerlo en cero haría que el total mienta "
            "por omisión; Klave lo muestra como faltante y descuenta ese concepto del "
            "costo directo diciéndolo."
        ),
        fuente="Klave · principio de honestidad",
        en_klave="Dale precio en Catálogo del taller, o adopta un P.U. de tu catálogo propio.",
        tags=["sin precio", "unpriced", "catálogo", "matriz", "dinero faltante"],
    ),
    Entrada(
        id="klave-verificacion",
        titulo="Qué significa el sello SIN VERIFICAR",
        resumen=(
            "Las pantallas y el Excel salen sellados hasta que alguien confirma tres "
            "cosas: la unidad del plano, las detecciones (con sus exclusiones) y los "
            "supuestos. El presupuesto es tuyo cuando tú lo firmas, no cuando el motor "
            "lo calcula."
        ),
        fuente="Klave · ruta de verificación",
        tags=["sin verificar", "verificación", "firma", "entrega"],
    ),
    Entrada(
        id="klave-ia-sugerencia",
        titulo="Qué puede y qué no puede hacer la lectura con IA",
        resumen=(
            "El modelo de visión lee la imagen de cada hoja y propone especificaciones "
            "(sección, armado, f'c) con procedencia. Rankea por debajo de un cuadro, un "
            "detalle o una nota leídos por reglas, y **nunca** cuantifica ni pone precio. "
            "Cada lectura trae el recorte de la hoja para que la compruebes."
        ),
        fuente="Klave · lectura asistida por IA",
        tags=["ia", "lectura", "recorte", "procedencia", "sugerencia"],
    ),
]


def entradas_por_tag(tag: str) -> list[Entrada]:
    return [e for e in NORMATIVA if tag in e.tags]
