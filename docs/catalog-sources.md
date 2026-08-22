# Fuentes del catálogo

Ningún precio entra al catálogo sin fuente, región y vigencia. Hay cuatro
tipos: **referencia** (semilla de Klave), **cotización** (del taller),
**publicación** (tabulador oficial) y **calculado** (salario real, costo
horario). Esta nota documenta las publicaciones y los cálculos.

## Publicaciones importables (`data/sources/`)

Los archivos oficiales se descargan a `data/sources/` (no se versionan) y se
registran en `data/sources/manifest.json` con URL, tamaño, hash y fecha.
`GET /catalog/sources` lista las publicaciones conocidas y si su archivo
está presente; `POST /catalog/sources/{key}/import` las parsea a la
biblioteca de referencia (`reference_prices`), desde donde un renglón se
adopta como precio de un insumo con su clave y vigencia.

| clave | documento | formato | renglones |
|---|---|---|---|
| `cdmx-tabulador-2026-06` | Tabulador General de Precios Unitarios CDMX, actualización junio 2026 (SOBSE) | PDF de texto, 357 páginas | 5 429 |
| `cdmx-tabulador-2026-03` | Edición 2026 (marzo) | PDF de texto, 350 páginas | ~5 400 |
| `sict-maquinaria-2026` | Tabulador de costos horarios de maquinaria y equipo, SICT, febrero 2026 | PDF de texto, 52 páginas | 262 (activo / espera / reserva) |

Descargados pero **no** importables hoy, y por qué:

- **Notas y Anexo 3 (factor de indirecto integrado) CDMX 2026** — PDFs
  escaneados sin texto; requieren OCR.
- **SICT tabulador de costos paramétricos 2026** — modelos paramétricos de
  carreteras (terracerías, pavimentos); útil como referencia de
  infraestructura, no para vivienda/edificación.
- **ComprasMX / CompraNet** — los CSV abiertos (2023–2025, 110–190 MB) son
  *por contrato* (dependencia, título, importe, proveedor); no contienen
  catálogos de conceptos ni precios unitarios. Sirven para totales de
  mercado, no para el catálogo.
- **CONAVI** — no publica un tabulador de costo por m²; las Reglas de
  Operación del Programa de Vivienda Social fijan precios máximos de
  vivienda (≈ $600–630 mil por 60 m² en 2026), un parámetro de orden de
  magnitud, no un precio unitario.

## Salario real (RLOPSRM art. 190–191)

`Sr = Sn · Fsr`, `Fsr = (1 + Ps) · Tp / Tl`. Parámetros 2026 por defecto:
salario mínimo general $315.04 (frontera $440.87), UMA $117.31, cuotas
patronales IMSS 2026 por ramo (cesantía y vejez progresiva por bandas de
UMA, riesgo de trabajo clase V 7.58875 %), INFONAVIT 5 %, aguinaldo 15 días,
vacaciones 12 días con prima 25 %, 7 festivos LFT, 3 días de costumbre.
El ISN estatal (4 % CDMX) se muestra y **no** entra al Fsr salvo que se
active — va en indirectos. Cada categoría guarda su desglose
(`insumo_analysis`, tipo `fsr`).

## Costo horario (RLOPSRM art. 194–206)

`Phm = (D + Im + Sm + Mn) + (Co + Lb + N + Ae) + Po` con cada símbolo como
entrada editable por insumo de equipo; el resultado sustituye el costo
unitario y guarda el análisis (`insumo_analysis`, tipo `costo_horario`).
