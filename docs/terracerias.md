# Terracerías leídas del levantamiento topográfico

Corte, terraplén y despalme necesitan el terreno natural y el nivel de
plataforma. El terreno se lee del plano; el nivel de plataforma lo define el
ingeniero. Ninguno de los dos se supone.

## Terreno natural

`detection/terrain.py` lee, por archivo:

- **Curvas de nivel**: polilíneas en capas topográficas (`CURVA`, `NIVEL`,
  `TOPO`, `CONTOUR`, `TN`, `TERRENO`…) con su nivel en la elevación de la
  polilínea (LWPOLYLINE `elevation`, POLYLINE 3D, SPLINE 3D — el normalizador
  lo conserva en `properties.elevation`) o en un texto numérico junto a la
  curva.
- **Puntos de nivel**: un texto numérico en una capa topográfica.
- **El lote**: la polilínea cerrada mayor en capas `LOTE`, `LINDERO`,
  `PREDIO`, `TERRENO`, `PROPIEDAD`; si no hay, la envolvente del levantamiento.

Con menos de 3 curvas con nivel o 6 puntos, o sin pendiente, no hay terreno y
la hoja lo dice en sus advertencias. El resultado es **una** detección
`terrain` (familia Terreno, TER) con una muestra de hasta 4 000 puntos
(x, y, z), el polígono del lote, los niveles mínimo y máximo y la fuente del
lote.

## Volúmenes

`costing/earthwork.py` interpola el terreno dentro del lote en una malla
(1/60 del lado del lote, mínimo 5 cm) por distancia inversa con los 8 puntos
más cercanos, y compara cada celda contra el nivel de plataforma: lo que
queda arriba es corte, lo que queda abajo es terraplén. La línea del
presupuesto escribe la malla, el rango del terreno y el nivel usado.

| Clave | Concepto | Cantidad |
|---|---|---|
| TER-001 | Despalme | área del lote (m²), espesor en supuestos (0.20 m) |
| TER-002 | Corte en banco | m³ sobre la plataforma |
| TER-003 | Terraplén compactado | m³ bajo la plataforma, material de banco |

## El nivel de plataforma

`Parámetros → Supuestos geométricos → Nivel de plataforma` (en el datum del
levantamiento; vacío = sin definir). Mientras esté vacío, el despalme se
cuenta y corte/terraplén no aparecen; el presupuesto advierte
"Terracerías: el plano trae topografía pero no se ha definido el nivel de
plataforma".

Sin abundamiento ni acarreo: el corte se mide en banco, el terraplén
compactado; acarreos y abundamiento se cotizan aparte, como lo dice la línea.

## Límites honestos

- Ni Marina Lote 04 ni PRUEBA-1 traen topografía: cero terreno en ambos. La
  lectura está probada con un levantamiento sintético (`tests/test_terrain.py`);
  el primer levantamiento real de una firma es el que la calibra.
- Las curvas sin nivel (ni elevación ni texto junto) no cuentan; una curva con
  dos textos cerca tampoco (ambiguo).
