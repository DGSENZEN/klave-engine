"""Texto y tablas de un PDF publicado, con el lector que mejor lo lee.

pypdfium2 conserva los espacios en las fuentes que pdfplumber pega
(«Despalmede20cm») y abre los PDF cifrados sin contraseña de usuario
(INIFECH); pdfplumber sigue siendo el mejor para tablas con celdas.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_MONEY_RE = re.compile(r"\$?\s*([\d\s,]+\.\d{2})")


def pdf_pages(path: Path) -> Iterator[tuple[int, list[str]]]:
    """(número de página, líneas) de cada página, con pypdfium2."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(document)):
            text = document[index].get_textpage().get_text_range() or ""
            yield index + 1, [line.rstrip() for line in text.splitlines()]
    finally:
        document.close()


def pdf_tables(path: Path) -> Iterator[tuple[int, list[list[str]]]]:
    """(número de página, tabla) por cada tabla con celdas, con pdfplumber."""
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages):
            for table in page.extract_tables() or []:
                yield index + 1, [[(cell or "").strip() for cell in row] for row in table]


def money(text: str) -> float | None:
    """«$ 1 ,006.84» → 1006.84; None si no hay importe."""
    match = _MONEY_RE.search(text or "")
    if not match:
        return None
    digits = re.sub(r"[\s,]", "", match.group(1))
    try:
        return float(digits)
    except ValueError:
        return None
