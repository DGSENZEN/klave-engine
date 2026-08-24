"""Qué pasajes puede usar el copiloto para responder una pregunta.

Recuperación léxica, deliberadamente: sin embeddings, sin índice remoto, sin
una dependencia más. Un buscador que alguien puede leer y depurar vale más
aquí que uno que acierta un poco más y nadie puede auditar — y el corpus son
unas decenas de entradas de normativa y las secciones de la documentación,
no un millón de documentos.

Dos fuentes, con rangos distintos:

* **normativa** — la ley y las reglas de Klave, cada una con su cita.
* **documentación** — los `docs/*.md` del repositorio, partidos por encabezado.
  Explican cómo se usa la aplicación y por qué hace lo que hace.

Lo que este módulo NO hace es responder. Devuelve pasajes; quien redacta la
respuesta solo puede usarlos, y si no alcanzan, tiene que decirlo.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from klave_engine.copilot.normativa import NORMATIVA

# Palabras que aparecen en todo y no distinguen nada.
_VACIAS = {
    "a", "al", "algo", "ante", "antes", "aqui", "como", "con", "cual", "cuando",
    "de", "del", "desde", "donde", "dos", "el", "ella", "ellos", "en", "entre",
    "es", "esa", "ese", "eso", "esta", "este", "esto", "hace", "hacer", "hasta",
    "hay", "klave", "la", "las", "le", "les", "lo", "los", "mas", "me", "mi",
    "mucho", "muy", "no", "nos", "o", "para", "pero", "poner", "por", "porque",
    "que", "se", "ser", "si", "sin", "sobre", "solo", "son", "su", "sus", "tan",
    "te", "tiene", "todo", "un", "una", "uno", "y", "ya",
}


def normalizar(texto: str) -> list[str]:
    """Palabras sin acentos ni signos, que es como la gente escribe de prisa."""
    plano = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    return [w for w in re.findall(r"[a-z0-9']+", plano) if w not in _VACIAS and len(w) > 1]


@dataclass
class Pasaje:
    """Un trozo de conocimiento que puede sustentar una respuesta."""

    id: str
    titulo: str
    cuerpo: str
    fuente: str  # de dónde salió, para citarlo
    url: str = ""
    vigencia: str = ""
    tipo: str = "normativa"  # normativa | documentacion


def _pasajes_normativa() -> list[Pasaje]:
    salida: list[Pasaje] = []
    for entrada in NORMATIVA:
        cuerpo = entrada.resumen
        if entrada.cita:
            cuerpo += f"\n\nTexto de la norma: «{entrada.cita}»"
        if entrada.en_klave:
            cuerpo += f"\n\nEn Klave: {entrada.en_klave}"
        salida.append(
            Pasaje(
                id=entrada.id,
                titulo=entrada.titulo,
                cuerpo=cuerpo,
                fuente=entrada.referencia or "Klave",
                url=entrada.url,
                vigencia=entrada.vigencia,
                tipo="normativa",
            )
        )
    return salida


# Documentos internos de trabajo: listas de pendientes, auditorías y notas de
# arquitectura. Explican cómo se construye Klave, no cómo se usa ni qué dice la
# ley, y en una respuesta solo restan.
_DOCS_INTERNOS = {
    "plan-de-pulido",
    "auditoria-ui",
    "EVALUATION",
    "evals",
    "DATA_CONTRACTS",
    "CPU_MVP_ARCHITECTURE",
}

_ENCABEZADO = re.compile(r"^(#{1,3})\s+(.*)$")


def _seccion(path: Path, seccion: str, buffer: list[str], indice: int) -> list[Pasaje]:
    """Una sección de documentación como pasaje; vacía si no enseña nada."""
    cuerpo = "\n".join(buffer).strip()
    if len(cuerpo) < 80:  # un encabezado suelto no explica nada
        return []
    return [
        Pasaje(
            id=f"{path.stem}#{indice}",
            titulo=seccion,
            cuerpo=cuerpo[:2400],
            fuente=f"docs/{path.name} · {seccion}",
            tipo="documentacion",
        )
    ]


def _pasajes_documentacion(docs_dir: Path) -> list[Pasaje]:
    """Cada `docs/*.md` partido por encabezado: una sección es la unidad que
    un lector abriría de todos modos."""
    salida: list[Pasaje] = []
    if not docs_dir.is_dir():
        return salida
    for path in sorted(docs_dir.glob("*.md")):
        if path.stem in _DOCS_INTERNOS:
            continue
        try:
            lineas = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        seccion = path.stem
        buffer: list[str] = []
        indice = 0
        for linea in lineas:
            match = _ENCABEZADO.match(linea)
            if match:
                salida.extend(_seccion(path, seccion, buffer, indice))
                indice += 1
                seccion = match.group(2).strip()
                buffer = []
            else:
                buffer.append(linea)
        salida.extend(_seccion(path, seccion, buffer, indice))
    return salida


@lru_cache(maxsize=4)
def _corpus(docs_dir: str) -> tuple[list[Pasaje], dict[str, float]]:
    """Los pasajes y el peso idf de cada palabra, calculados una vez."""
    pasajes = _pasajes_normativa() + _pasajes_documentacion(Path(docs_dir))
    documentos = len(pasajes) or 1
    apariciones: Counter[str] = Counter()
    for pasaje in pasajes:
        for palabra in set(normalizar(f"{pasaje.titulo} {pasaje.cuerpo}")):
            apariciones[palabra] += 1
    idf = {
        palabra: math.log(1 + documentos / (1 + veces))
        for palabra, veces in apariciones.items()
    }
    return pasajes, idf


def buscar(pregunta: str, docs_dir: Path, limite: int = 6) -> list[Pasaje]:
    """Los pasajes que mejor cubren la pregunta, de más a menos.

    Un título que coincide pesa el triple que el cuerpo: quien pregunta por
    «anticipo» quiere la entrada de anticipos, no las quince que lo mencionan
    de pasada."""
    pasajes, idf = _corpus(str(docs_dir))
    consulta = normalizar(pregunta)
    if not consulta:
        return []
    puntuados: list[tuple[float, Pasaje]] = []
    for pasaje in pasajes:
        titulo = set(normalizar(pasaje.titulo))
        cuerpo = Counter(normalizar(pasaje.cuerpo))
        largo = sum(cuerpo.values()) or 1
        puntos = 0.0
        for palabra in consulta:
            peso = idf.get(palabra, 1.0)
            if palabra in titulo:
                puntos += 3.0 * peso
            if palabra in cuerpo:
                # Saturación: la décima repetición no vale como la primera.
                puntos += peso * (1 + math.log(cuerpo[palabra])) / math.sqrt(largo) * 6
        if puntos > 0:
            puntuados.append((puntos, pasaje))
    puntuados.sort(key=lambda par: -par[0])
    return [pasaje for _puntos, pasaje in puntuados[:limite]]
