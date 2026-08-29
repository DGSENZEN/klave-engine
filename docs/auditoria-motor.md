# Auditoría del motor de detección — dónde se desconecta lo que el plano sí conecta

Fecha: 2026-08-28. Tercera auditoría. Las dos anteriores preguntaron por la
interfaz ([auditoria-ui.md](auditoria-ui.md): *¿funciona?*,
[auditoria-densidad.md](auditoria-densidad.md): *¿se lee?*). Esta pregunta
**¿el motor conecta las entidades como el plano las conecta?** — y la
respuesta corta es: en hojas de un solo marco, sí (el gold da F1 = 1.0 en
los tres proyectos); en conjuntos reales de varios marcos, **no, y por una
causa dominante que explica la mayoría de los síntomas**.

## Método

Tres fuentes, todas medidas en esta sesión:

- `make eval-gold` (corrida 2026-08-28): demo, prueba-1, torre-reforma.
- Los artefactos en disco de **Marina Lote 04 — Completo**
  (`run_f57759d1`, 12 hojas, 77,925 entidades, 1,183 detecciones,
  163 riesgos), leídos con scripts ad hoc — no se reprocesó nada.
- Lectura del código con cuatro barridos paralelos (pipeline, bloques,
  web, roles) y verificación puntual de cada hallazgo citado.

---

## 0. La tesis

**El motor no "pierde" las losas ni la cimentación: pierde la malla de
ejes, y todo lo que se ancla a la malla cae en cascada.** El detector de
ejes exige que una línea mida ≥ 50 % del extent del **archivo**
([grid_detector.py:51,273](../packages/klave_engine/detection/grid_detector.py)).
En una hoja de un marco eso es correcto. En Marina, el archivo
estructural son **22 marcos de hoja mosaicados en model space**: el
extent es el del mosaico completo, y ningún eje real de un marco
(10–27 m) alcanza el umbral.

Medido sobre `run_f57759d1`:

| Hecho | Cifra |
|---|---:|
| Líneas en capas de eje (`A-EJES`, `EJES`, `ARQ-Ejes 9`, `E-EJE`) en el archivo estructural | **383** (348 alineadas a eje, 86 de más de 10 m) |
| Ejes detectados en ese archivo | **6** |
| Columnas con `has_nearby_grid` | **0 de 359** |
| Intersecciones de malla en todo el proyecto | 7 |
| El propio motor lo dice (`sparse_grid`) | «se leyeron 6 ejes y 222 de 222 columnas quedan sin eje cercano» |

Y la cascada, porque la malla es el tejido conectivo de casi todo:

- Las **columnas** no encuentran intersección de eje → no se anclan
  ([column_detector.py:97](../packages/klave_engine/detection/column_detector.py)).
- Las **zapatas** se comprueban contra columnas que no están ancladas →
  43 hallazgos `footing_without_column`, ruido, no señal.
- Los **tableros de losa** se poligonizan sobre la red trabes+muros+**ejes**
  ([slab_panels.py:292](../packages/klave_engine/detection/slab_panels.py));
  sin ejes, caras que no cierran o que se funden — la sensación de
  «losas desconectadas» del usuario.
- La pantalla de **Riesgos** dibuja 163 tarjetas cuyo hallazgo raíz
  (`sparse_grid`, severidad `low`) queda al final — ya documentado en la
  auditoría de densidad; esta auditoría encuentra la causa del hallazgo.

Los umbrales relativos al extent del archivo son tres, todos en el mismo
config: `min_relative_length` (0.5 × extent), `label_search_radius_factor`
(0.05 × diagonal — en Marina, un radio de búsqueda de etiqueta de más de
13 m) y los factores de merge colineal (0.002/0.02 × extent — tolerancias
que en un mosaico pueden fundir ejes de **hojas distintas**). La malla
además se calcula **por archivo**, cuando los marcos ya existen desde la
etapa 8 del pipeline ([pipeline.py:296](../packages/klave_engine/pipeline.py))
— la corrección natural es detectar la malla **por marco**, con el extent
del marco.

---

## 1. Hallazgos, en orden de daño

### E1 · La malla se mide contra el archivo, no contra el marco — P0

Lo de arriba. **Prueba de corrección:** en Marina estructural, ejes
detectados ≥ 15 por marco de planta, `has_nearby_grid` > 90 % de las
columnas, `sparse_grid` desaparece, y el gold de prueba-1 no se mueve
(una hoja de un marco no cambia de extent efectivo).

### E2 · El símbolo reventado se cuenta dos veces — P0

El parser emite **el INSERT y además sus hijos reventados**
([parser.py:114–117, 205–207](../packages/klave_engine/dxf/parser.py)).
Un solo detector se protege de contar ambos:
[opening_detector.py:127–130](../packages/klave_engine/detection/opening_detector.py)
filtra `parent_insert` — con el comentario que ya dice la regla. Muros,
columnas, zapatas, losas y los acumuladores de metros/áreas del
levantamiento ([inventory.py:225–265](../packages/klave_engine/detection/inventory.py))
**no filtran**: la línea interna de un bloque suma longitud de muro y área
de hatch junto con el bloque que ya se contó como pieza.
**Prueba:** grep de `parent_insert` aparece en cada detector geométrico, y
las cantidades del gold no suben al reprocesar un plano con bloques.

### E3 · Detectores estructurales en hojas que no son estructura — P0

`NON_STRUCTURal` ([inventory.py:129](../packages/klave_engine/detection/inventory.py))
no incluye albañilería, plafones ni el índice. Medido en Marina: **25
"zapatas" en las dos hojas de albañilería y 1 en el índice** (26 de 64 =
40 % de las zapatas del proyecto), y 17 de los 23 ejes del proyecto
leídos en el índice y albañilería. Esas zapatas fantasma inflan CIM-002 y
son parte de los 43 `footing_without_column`.
**Prueba:** en Marina, zapatas solo en hojas estructurales; el conteo del
gold estructural no cambia.

### E4 · La plantilla desapareció y el relleno la absorbió — P0 (regresión activa)

`make eval-gold` **falla hoy** en los tres proyectos, con un solo
mecanismo: si un concepto de cimbra/plantilla no tiene matriz,
[formwork.py:320–329](../packages/klave_engine/costing/formwork.py) lo
**descarta con un aviso** en vez de emitir la línea sin precio — contra la
doctrina A9 («las líneas sin precio quedan visibles y lo dicen»,
commit `5f79aeb`). Desde `49bd10f` (fuera los precios inventados) CIM-003
no tiene matriz por defecto → la línea no existe → la resta del relleno
([cimentacion.py:38–40](../packages/klave_engine/costing/cimentacion.py))
no ve plantilla que restar. La aritmética delata la causa: el exceso de
CIM-004 es **exactamente** área de plantilla × 0.05 m en los tres
proyectos (demo 362.4 m³, prueba-1 0.601 m³, torre 0.192 m³).
Además el fence de dinero del gold quedó obsoleto tras `49bd10f`
(espera $689,042.75 / $83,098.87; el motor puro da $0.00 — correcto por
decisión de producto), y AIR-004 / CAR-001 no están fenceados.
**Prueba:** CIM-003 aparece `sin precio`, CIM-004 vuelve al valor
esperado, y el gold se recaptura declarando el cambio de dinero.

### E5 · La losa sin tipo se cobra como reticular — P1

`sin_tipo`, `None` y `losa` caen en EST-003 (losa reticular) por el
`property_filter` de [catalog.py:327–338](../packages/klave_engine/costing/catalog.py)
+ el fallback de familia en [boq.py:52–53](../packages/klave_engine/costing/boq.py).
Una losa de cimentación cuyo tablero no contiene literalmente
`CIMENTACI` en su etiqueta se cobra como reticular **y en la fase
equivocada**. Emparentado: la deduplicación panel-vs-contorno borra
**todos** los contornos de un archivo que produjo páneles
([pipeline.py:344–351](../packages/klave_engine/pipeline.py)) — una
esquina sin panelizar pierde su losa.

### E6 · «La vista con más columnas» no es deduplicación — P1

Sin alturas de entrepiso declaradas,
[boq.py:390](../packages/klave_engine/costing/boq.py) toma
`max(by_view)` como canónica: los elementos de las otras plantas no se
deduplican, **se descartan**. Y si ninguna vista se identifica como
cimentación, los conceptos `FOUNDATION_ONLY` se calculan sobre todas las
plantas ([boq.py:394](../packages/klave_engine/costing/boq.py)).

### E7 · Pérdidas silenciosas del parser — P1

- Anidamiento de bloques a profundidad ≥ 2 se corta **sin aviso**
  ([parser.py:167](../packages/klave_engine/dxf/parser.py)) — el cap de
  presupuesto sí avisa; este no.
- Un INSERT anidado se recorre pero **nunca se normaliza**: su nombre de
  bloque y sus ATTRIB se pierden ([parser.py:191–193](../packages/klave_engine/dxf/parser.py)).
  El levantamiento subcuenta cualquier símbolo empacado dentro de un
  bloque contenedor — exactamente como se dibujan los detalles típicos.
- `ATTDEF` no se lee en ninguna parte.

### E8 · Marcos «unknown» y asignación por centroide — P1

En Marina, **53 de 81 marcos** quedan `unknown`. La asignación por
título (fallback) es Voronoi por centroide sin tope de distancia
([views.py:409](../packages/klave_engine/detection/views.py)): una
detección lejos de todo título igual se atribuye a alguno.

### E9 · Minas de configuración — P2

- Un `detector_config_path` externo se aplica **verbatim** y se salta
  todo el escalado por unidades ([suite.py:142](../packages/klave_engine/detection/suite.py)).
- Con unidades desconocidas, varios umbrales quedan en 0.0 y apagan
  silenciosamente zapatas corridas, marcas Z-n, merge de muros y vanos.
- `detections.json` se escribe dos veces cuando hay muros de azotea
  ([pipeline.py:396,431](../packages/klave_engine/pipeline.py)).

---

## 2. El índice de prefabricados — sí se puede, y casi todo ya existe

La pregunta del usuario: los planos traen «prefabs» (detalles típicos
dibujados como bloques) — ¿se puede construir un índice al ingerir y
usarlo de guía? **Sí.** El parser ya lee la sección BLOCKS, revienta los
INSERT con transformaciones, conserva `block_name` / `from_block` /
`parent_insert`, y hay una librería de símbolos por nombre de bloque
(instalaciones), un inventario por bloque y hoja, y una cadena de
autoridad de secciones (cuadro > cota > marcador > supuesto). Lo que
**no** existe es la noción de **definición de bloque como detalle típico
reutilizable**: cada instancia se re-detecta desde cero y el vínculo
detalle→elemento es solo por texto de marca.

La forma propuesta, tres capas sobre lo ya construido:

1. **Identidad primero (es E2/E7):** normalizar INSERTs anidados,
   filtrar `parent_insert` en todos los detectores geométricos, leer
   ATTDEF. Sin esto el índice contaría lo mismo dos veces.
2. **El índice:** al parsear, una pasada por definición de bloque —
   nombre, firma geométrica, atributos, clasificación con los parsers
   que ya existen (`parse_block_name`, símbolos, secciones de detalle) —
   y la lista de colocaciones (instancias con transformación). Se
   **detecta una vez por definición y se estampa por instancia**. Sale
   como artefacto (`prefab_index.json`) junto a `block_summary.json`.
3. **El detalle como plantilla:** cuando una definición es un detalle
   típico (castillo K-1, zapata Z-2), su lectura entra a la cadena de
   autoridad de `schedules.py` con rango propio, y sus instancias quedan
   vinculadas definición↔elementos — el «detalle que gobierna N piezas»
   deja de depender de que la marca esté escrita cerca.

Esto además alimenta directo la petición del cliente de «menú desplegable
al cargar el plano, para saber qué datos jalan»: el índice es exactamente
esa lista.

---

## 3. Prioridades

| # | Qué | Mata | Prueba |
|---|---|---|---|
| P0-1 | Malla por marco, umbrales por extent de marco | E1 y su cascada (columnas, zapatas, tableros, 163 riesgos) | Marina: ejes por planta ≥ 15, `sparse_grid` fuera; gold intacto |
| P0-2 | Emitir plantilla/cimbra sin matriz como línea sin precio | E4 (gold roto hoy) | eval-gold verde tras recaptura declarada |
| P0-3 | `parent_insert` filtrado en todos los detectores geométricos | E2 | cantidades estables en planos con bloques |
| P0-4 | Albañilería/plafones/índice fuera de los detectores estructurales | E3 | 0 zapatas en hojas no estructurales de Marina |
| P1-1 | Losa sin tipo: fase y concepto honestos (no reticular por defecto) | E5 | losa `sin_tipo` sale como `sin tipo`, con aviso |
| P1-2 | Unión de vistas en vez de `max(by_view)`; aviso cuando cimentación no se identifica | E6 | elementos de plantas no-máximas sobreviven |
| P1-3 | Parser: aviso en corte de profundidad; INSERT anidado normalizado; ATTDEF | E7 | `block_summary` cuenta símbolos anidados |
| P1-4 | Índice de prefabricados (§2) | E2 estructural + detalle→instancia | detalle típico gobierna sus N instancias |
| P2 | Config externo escala unidades; una sola escritura de `detections.json` | E9 | — |

El orden importa: P0-1 a P0-4 cambian cantidades, así que cada una
recaptura gold **diciéndolo en el commit** (regla de la casa). La capa de
interfaz (nodos estilo Railway, edición de medidas al pasar el cursor,
búsqueda de conceptos desde el visor) se diseña aparte — no tiene caso
dibujar mejor un número que todavía está mal conectado.

---

## 4. Resultado de la corrección (2026-08-28, rama `motor-p0-reconexion`)

Los cuatro P0 aterrizaron con TDD y el gold verde en cada paso. Medido
reprocesando Marina Lote 04 — Completo en scratch con el motor corregido:

| Métrica | Antes | Después |
|---|---:|---:|
| Ejes detectados en el archivo estructural | 6 | **685** (186 h / 499 v) |
| `sparse_grid` | 1 (invalidaba 74 medias) | **0** |
| Zapatas en albañilería / índice | 26 de 64 (40 %) | **0** |
| Hallazgos de riesgo totales | 163 | **88** |
| `footing_without_column` | 43 | 17 |
| `column_tag_without_grid` | (el detector no podía saberlo) | **1** |
| CIM-003 / CIM-004 en gold | ausente / +50–145 % | **0 % de desviación** |

**Una meta de la sección 1 estaba mal calibrada, y se corrige aquí:** pedí
`has_nearby_grid` > 90 % de las columnas. El resultado es 172 de 359 (48 %) —
y la investigación muestra que las 359 son marcas K/C (castillos) con la
misma distribución en ancladas y no ancladas, a una mediana de 6.5 m de la
intersección más cercana. En una vivienda de muros y castillos, **el castillo
vive a media pared, no sobre el cruce de ejes**: el 48 % es una propiedad del
edificio, no una falla de lectura. La aceptación correcta es la que el propio
motor reporta: `sparse_grid` en cero y `column_tag_without_grid` ≈ 0 (quedó
en 1). El umbral de eje, además, se juzga ahora contra el span de la propia
malla dentro del marco, no contra el ancho del cajetín.

**Residual conocido, para el plan P1:** los 499 ejes verticales incluyen
fragmentación (las tolerancias de merge colineal, ahora por marco, quedaron
más estrictas que antes: un eje real partido por huecos > 0.9 m sale como
varios ejes). No estorba a las intersecciones ni al anclaje; infla el conteo.

### P1 cerrado (2026-08-28, rama `motor-p1-limpieza`)

E5–E9 y el residual, con dos correcciones de esta misma auditoría:

- **El residual de fragmentación estaba mal diagnosticado.** Medido: el
  grueso de los 685 «ejes» era **un eje por aparición de marco** (correcto,
  la regla de PRUEBA-1); la fragmentación real eran 49 detecciones — huecos
  de burbuja (mediana 1.9 m) y **doble trazo** del mismo eje (desfase ≤ 0.16
  m). Tolerancias de marco (`merge_gap_frame_factor` 0.06,
  `collinear_tolerance_frame_factor` 0.005): 685 → **593** ejes, anclaje
  **sube** a 175, gold intacto.
- **Dos recapturas declaradas de gold:** la losa sin sistema migra
  EST-003 → **EST-016** sin precio (cantidades idénticas: 120000 / 34.291 /
  36 m²) — resultó que *todo* el EST-003 de los tres fixtures era área sin
  familia declarada; y prueba-1 EST-001 17.436 → **12.422 m³**: sin alturas
  las plantas ahora se **suman** por entrepiso supuesto en vez de castillos
  de la vista más poblada a altura de edificio entero (la misma dirección
  que A1/A2 tomó con el acero).
- Riesgos de Marina 88 → 116: honesto — al sumar plantas, más elementos
  reales entran al takeoff y sus dudas se reportan; que Riesgos los agrupe
  es el pendiente M1 de la auditoría de densidad, no de este plan.
- Además: el config externo overlaya el preset escalado; `detections.json`
  se escribe una vez; el INSERT anidado conserva identidad, el corte de
  profundidad avisa y ATTDEF se lee (`block_attdefs`, para el índice de
  prefabricados); la asignación por título tiene tope de distancia.

Ver también: [principios-de-interfaz.md](principios-de-interfaz.md) ·
[auditoria-densidad.md](auditoria-densidad.md) ·
[plan-de-pulido.md](plan-de-pulido.md)
