"""El copiloto: responde con lo que puede citar, y calla lo que no sabe.

La utilidad de un copiloto de costos no está en redactar bonito. Está en
ahorrarle a alguien el viaje al Reglamento, al manual y a la pantalla de
enfrente — y eso solo sirve si lo que dice se puede comprobar sin salir de la
respuesta. Por eso:

* Solo puede usar los pasajes que la búsqueda le entregó. El prompt se lo
  ordena, y el servicio verifica: una respuesta que no coincide con ningún
  pasaje se marca ``fundamentada=False`` y la interfaz la presenta como lo
  que es.
* Si no hay pasajes, no llama al modelo. Contestar de memoria sobre un
  artículo del RLOPSRM es exactamente el modo de fallar que este archivo
  existe para prevenir.
* Sobre el proyecto abierto responde con los hallazgos vivos, no con lo que
  recuerda: el diagnóstico se le pasa como contexto cada vez.
* Nunca dictamina. Dice dónde está escrito y qué dice; quien firma es el
  ingeniero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from klave_engine.copilot.busqueda import Pasaje, buscar, normalizar
from klave_engine.copilot.normativa import AVISO_VIGENCIA

SYSTEM_PROMPT = """Eres el copiloto de Klave, una herramienta mexicana de ingeniería \
de costos. Ayudas a ingenieros de costos y peritos que firman con su cédula lo que \
entregan.

REGLAS QUE NO PUEDES ROMPER:
1. Responde ÚNICAMENTE con lo que digan los PASAJES que te doy. No uses conocimiento \
propio sobre leyes, normas, precios ni prácticas: si no está en los pasajes, no lo sabes.
2. Si los pasajes no alcanzan para responder, dilo en una frase y di qué haría falta \
consultar. Es una respuesta correcta y valiosa; inventar no lo es.
3. Cita siempre de dónde sale cada afirmación, con el nombre que trae el pasaje \
(por ejemplo «RLOPSRM art. 190» o «docs/lectura-ia.md»). No inventes números de \
artículo ni de norma.
4. Nunca dictamines si un caso concreto cumple o no cumple, ni des una cantidad, un \
precio o un plazo como si fuera de esta obra salvo que venga en el CONTEXTO DEL \
PROYECTO. Orientas; el ingeniero decide y firma.
5. Español de México, directo y sin rodeos. Habla como un colega con experiencia, no \
como un manual. Frases completas, sin listas de viñetas salvo que ayuden de verdad.
6. Sé breve: tres o cuatro frases bastan casi siempre. Si el usuario quiere el texto \
literal de la norma, ya se lo mostramos aparte."""


@dataclass
class Cita:
    titulo: str
    fuente: str
    url: str = ""
    vigencia: str = ""
    tipo: str = "normativa"


@dataclass
class Respuesta:
    texto: str
    citas: list[Cita] = field(default_factory=list)
    # False cuando no hubo pasajes o el texto no se apoya en ellos: la
    # interfaz lo dice en lugar de presentarlo como respaldado.
    fundamentada: bool = True
    # Se muestra cuando la respuesta toca obra pública federal.
    aviso: str = ""


def _contexto_proyecto(contexto: dict[str, Any] | None) -> str:
    """Los hechos vivos del proyecto abierto, si los hay."""
    if not contexto:
        return ""
    lineas = [f"Proyecto: {contexto.get('nombre') or contexto.get('project_id', '—')}"]
    if contexto.get("resumen"):
        lineas.append(f"Estado: {contexto['resumen']}")
    hallazgos = contexto.get("hallazgos") or []
    for h in hallazgos[:6]:
        stake = ""
        if h.get("monto_afectado"):
            stake = f" (${h['monto_afectado']:,.0f} en juego)"
        elif h.get("exposicion"):
            stake = f" ({h['exposicion']})"
        lineas.append(f"- [{h.get('severity')}] {h.get('title')}{stake}")
    if contexto.get("plazo_natural"):
        lineas.append(
            f"Plazo del programa: {contexto['plazo_natural']} días naturales "
            f"({contexto.get('plazo_habil')} hábiles)."
        )
    return "\n".join(lineas)


def construir_prompt(
    pregunta: str, pasajes: list[Pasaje], contexto: dict[str, Any] | None
) -> str:
    bloques = []
    for indice, pasaje in enumerate(pasajes, start=1):
        cabecera = f"[{indice}] {pasaje.titulo} — fuente: {pasaje.fuente}"
        if pasaje.vigencia:
            cabecera += f" ({pasaje.vigencia})"
        bloques.append(f"{cabecera}\n{pasaje.cuerpo}")
    partes = ["PASAJES:", "\n\n".join(bloques)]
    proyecto = _contexto_proyecto(contexto)
    if proyecto:
        partes.append(
            "CONTEXTO DEL PROYECTO ABIERTO (hechos actuales; puedes usarlos como "
            f"propios de esta obra):\n{proyecto}"
        )
    partes.append(f"PREGUNTA:\n{pregunta.strip()}")
    return "\n\n".join(partes)


_PALABRAS_FEDERALES = {
    "lopsrm", "rlopsrm", "licitacion", "licitación", "convocante", "obra",
    "publica", "pública", "anticipo", "estimacion", "estimación", "programa",
}


def _fundamentada(texto: str, pasajes: list[Pasaje], contexto_texto: str = "") -> bool:
    """¿La respuesta se parece al material que le dimos?

    El material son los pasajes **y** los hechos del proyecto abierto: una
    respuesta que nombra CIM-010 y sus 23 piezas está perfectamente
    fundamentada aunque esa clave no aparezca en ninguna ley. Marcar esas como
    dudosas sería crear la falsa alarma que enseña a ignorar la advertencia —
    justo el modo de fallar que esta señal existe para evitar.

    No es una demostración: un modelo puede parafrasear bien y aun así
    equivocarse. Atrapa el caso que importa — una respuesta que no comparte
    casi nada con el material y, por lo tanto, salió de su memoria."""
    palabras_respuesta = set(normalizar(texto))
    if not palabras_respuesta:
        return False
    material = set(normalizar(contexto_texto))
    for pasaje in pasajes:
        material |= set(normalizar(f"{pasaje.titulo} {pasaje.cuerpo} {pasaje.fuente}"))
    if not material:
        return False
    compartidas = palabras_respuesta & material
    return len(compartidas) / len(palabras_respuesta) >= 0.45


_ARTICULO = re.compile(r"art[íi]?culos?\.?\s*(\d+)", re.IGNORECASE)


def _articulos_inventados(texto: str, pasajes: list[Pasaje]) -> list[str]:
    """Números de artículo citados en la respuesta que no están en ningún
    pasaje. Es la alucinación más cara posible en este dominio, así que se
    detecta explícitamente en vez de confiar en la instrucción."""
    material = " ".join(f"{p.cuerpo} {p.fuente}" for p in pasajes)
    permitidos = set(_ARTICULO.findall(material))
    return sorted({a for a in _ARTICULO.findall(texto) if a not in permitidos})


def responder(
    pregunta: str,
    docs_dir: Path,
    ask: Any,
    contexto: dict[str, Any] | None = None,
    limite_pasajes: int = 6,
) -> Respuesta:
    """Contesta la pregunta con lo que se pueda citar.

    ``ask`` es una función (system, prompt) -> texto: el proveedor ya
    configurado, o cualquier cosa en las pruebas."""
    pregunta = pregunta.strip()
    if not pregunta:
        return Respuesta(texto="Escribe una pregunta.", fundamentada=False)
    pasajes = buscar(pregunta, docs_dir, limite=limite_pasajes)
    if not pasajes:
        return Respuesta(
            texto=(
                "No encontré nada en la normativa que tengo cargada ni en la "
                "documentación de Klave que responda eso. Prefiero decírtelo a "
                "inventarte una respuesta: si es un punto de ley, búscalo en el "
                "texto vigente; si es de la aplicación, dime en qué pantalla estás "
                "y lo vemos."
            ),
            fundamentada=False,
        )

    contexto_texto = _contexto_proyecto(contexto)
    texto = ask(SYSTEM_PROMPT, construir_prompt(pregunta, pasajes, contexto)).strip()
    inventados = _articulos_inventados(texto, pasajes)
    if inventados:
        texto += (
            "\n\n(Cuidado: mencioné artículo(s) "
            + ", ".join(inventados)
            + " que no están en el material que tengo. Verifícalos en el texto "
            "vigente antes de usarlos.)"
        )
    citas = [
        Cita(
            titulo=p.titulo, fuente=p.fuente, url=p.url, vigencia=p.vigencia, tipo=p.tipo
        )
        for p in pasajes
    ]
    federal = bool(_PALABRAS_FEDERALES & set(normalizar(pregunta + " " + texto)))
    return Respuesta(
        texto=texto,
        citas=citas,
        fundamentada=_fundamentada(texto, pasajes, contexto_texto) and not inventados,
        aviso=AVISO_VIGENCIA if federal else "",
    )
