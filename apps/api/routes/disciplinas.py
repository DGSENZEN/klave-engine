"""Qué datos jala el motor de cada archivo, antes de subirlo.

El diálogo de subida pregunta por nombre de archivo y este endpoint contesta
con el ruteo real del registro de disciplinas — la misma función que usará
el pipeline — y una lista honesta de lo que esa suite lee hoy. Nada de
promesas: lo que una disciplina aún no detecta se dice como levantamiento.
"""

from klave_engine.detection.disciplines import route_sheet
from pydantic import BaseModel, Field

from fastapi import APIRouter

router = APIRouter(prefix="/disciplines", tags=["disciplinas"])

_LABELS = {
    "estructural": "Estructural",
    "hidraulica": "Hidráulica",
    "sanitaria": "Sanitaria",
    "electrica": "Eléctrica",
    "gas": "Gas",
    "aire": "Aire acondicionado",
    "cctv": "CCTV y seguridad",
    "canceleria": "Cancelería",
    "acabados": "Acabados",
    "carpinteria": "Carpintería",
    "albanileria": "Albañilería",
    "indice": "Índice / portada",
    "arquitectura": "Arquitectura (sustrato)",
}

# Lo que cada suite jala HOY. La estructural es la lectura completa; las
# suites con detector propio dicen lo suyo; el resto es levantamiento
# honesto: bloques contados y metros por capa, sin inventar conceptos.
_LEVANTAMIENTO = [
    "Símbolos contados por bloque y capa",
    "Metros de trazo por capa (sin anotación)",
    "Especificaciones escritas en la hoja",
]
_JALA: dict[str, list[str]] = {
    "estructural": [
        "Ejes y su malla (por marco de hoja)",
        "Columnas y castillos, anclados a ejes",
        "Zapatas, contratrabes y trabes",
        "Tableros de losa entre trabes",
        "Muros con su espesor",
        "Cotas, niveles y cuadros de la hoja",
    ],
    "hidraulica": [
        "Salidas y muebles (bloques contados)",
        "Tubería por diámetro, en metros de red",
        "Bajadas verticales entre niveles",
        "Trazo de símbolo descontado de los metros",
    ],
    "sanitaria": [
        "Salidas y muebles (bloques contados)",
        "Tubería por diámetro, en metros de red",
        "Bajadas verticales entre niveles",
        "Trazo de símbolo descontado de los metros",
    ],
    "canceleria": [
        "Etiquetas V-n / P-n (burbujas y atributos)",
        "Conteo por tipo de cancel",
        "m² cuando la hoja trae cuadro de cancelería",
    ],
    "acabados": [
        "Claves de acabado ancladas a su local",
        "Áreas por local cuando hay polilínea de piso",
        "Simbología de muros y plafones",
    ],
    "albanileria": [
        "Muros de tabique en m², con vano descontado",
        "El fondo arquitectónico cuenta aquí como muro",
        "Vanos y aberturas de la hoja",
    ],
    "arquitectura": [
        "Sustrato: se dibuja y ancla locales",
        "Sus muros no cobran (cobran en albañilería)",
    ],
    "electrica": [
        "Levantamiento por capas (el detector eléctrico está pendiente)",
        *_LEVANTAMIENTO,
    ],
    "indice": [
        "Portada o índice: se registra, no genera cantidades",
    ],
}


class PreviewInput(BaseModel):
    filenames: list[str] = Field(max_length=200)


@router.post("/preview")
def preview(body: PreviewInput) -> dict:
    previews = []
    for filename in body.filenames:
        suite = route_sheet(filename)
        previews.append(
            {
                "filename": filename,
                "discipline": suite.key,
                "label": _LABELS.get(suite.key, suite.key),
                "structural": suite.structural,
                "jala": _JALA.get(suite.key, _LEVANTAMIENTO),
            }
        )
    return {"previews": previews}
