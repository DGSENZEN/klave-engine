"""What a person counted on the plan, stored beside what they reviewed.

Counting used to mean hand-editing a JSON file in the repo, which a deployed
server cannot write and a cost engineer will not do. These live in the
project's control dir next to detection_reviews.json, because they are the
same kind of thing: a human's judgement about this drawing.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.io import read_json, write_json
from klave_engine.evals.recall import ConteoDeObra, ConteoHumano

CONTEOS_FILENAME = "conteos.json"


class ConteoHoja(BaseModel):
    """One family counted on one sheet."""

    hoja: str
    familia: str
    # What the person counted on the sheet.
    dibujados: int = 0
    # What the engine found there, carried for context at counting time.
    detectados: int = 0
    nota: str = ""


class ConteosDeProyecto(BaseModel):
    contado_por: str = ""
    contado_en: str = ""
    hojas: list[ConteoHoja] = Field(default_factory=list)

    def a_conteo_de_obra(self, drawing_id: str) -> ConteoDeObra:
        """Fold the per-sheet counts into the per-family shape recall measures.

        Counting is per sheet because that is how a person reads a plan;
        recall is per family because that is how a detector fails.
        """
        totales: dict[str, int] = {}
        for hoja in self.hojas:
            totales[hoja.familia] = totales.get(hoja.familia, 0) + hoja.dibujados
        return ConteoDeObra(
            drawing_id=drawing_id,
            contado_por=self.contado_por,
            contado_en=self.contado_en,
            conteos=[
                ConteoHumano(familia=familia, dibujados=dibujados)
                for familia, dibujados in sorted(totales.items())
            ],
        )


def load_conteos(control_dir: Path) -> ConteosDeProyecto:
    path = control_dir / CONTEOS_FILENAME
    if not path.exists():
        return ConteosDeProyecto()
    return ConteosDeProyecto.model_validate(read_json(path))


def save_conteos(control_dir: Path, conteos: ConteosDeProyecto) -> None:
    write_json(control_dir / CONTEOS_FILENAME, conteos)
