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

### Espine multidisciplina cerrado (2026-08-28, rama `motor-espine`)

S1–S5 v1, todo con la conducta de detección **byte-estable** contra P1
(Marina: 593 ejes, 175 ancladas, 0 fantasma — idéntico):

- **S1** El registro de disciplinas (`detection/disciplines/`) es dueño del
  ruteo y del vocabulario; `reads_as_structure` es un delegado. El
  contenido **vota** y avisa cuando contradice al nombre (Marina: 0
  contradicciones — los nombres del set dicen la verdad). El hueco
  `detect` lo llena cada suite al aterrizar con su gold.
- **S2** `prefab_index.json`: cada definición de bloque clasificada una vez
  (tabla de símbolos + semántica del nombre + ATTDEF), con todas sus
  instancias. Marina: 124 definiciones, 1,690 instancias; el fixture de
  instalaciones clasifica `subida-bajada→bajada` y
  `DESCSAN1→salida_sanitaria`. La Lectura lo sirve (`prefabs`).
- **S3** Cobertura declarada por archivo: `ok | parcial | ilegible` con
  razones, incluidos los DWG que no convirtieron (renglón ilegible con el
  error del convertidor). Marina: **las 12 hojas son «parcial»** — modo de
  recuperación, xrefs ausentes, anidamiento profundo — la verdad de esos
  dibujos, dicha una vez por hoja en vez de dispersa en avisos.
- **S4** `build_schedule_inventory(..., extra_readers=)`: los cuadros por
  disciplina (cancelería, tablero eléctrico) se enchufan a la cadena de
  autoridad con rango de cuadro.
- **S5** Primer gold multidisciplina: `instalaciones-mini` (sanitario + AA
  de Marina como DXF ya convertidos — el eval completo sigue en ~8 s):
  109 muebles, 20 corridas, F1 = 1.0; los 25 compuertas y 16 DESCSAN1
  coinciden con lo que la memoria del proyecto recuerda.

### Suite hidrosanitaria cerrada (2026-08-29, rama `suite-hidrosanitaria`)

Medir primero pagó otra vez: la mitad del §2 **ya existía** (corridas por
sistema con diámetro/material, muebles→salidas por familia, registros) y el
plan solo construyó los huecos reales:

- **La corrida se parte donde cambia el diámetro.** Medido: 16 de 20
  corridas del fixture tenían ≥2 diámetros rotulados (481 m perdiendo
  resolución). Ahora cada segmento se adjudica al rótulo legible más
  cercano: instalaciones completas, 68 corridas y 64 con diámetro nominal
  (sanitaria 4"/2", agua fría 1/2", gas 3/4"). Gold recapturado y
  declarado (20→34 en `instalaciones-mini`).
- **Las bajadas se ligan entre niveles** por posición relativa al marco:
  45 de 56 símbolos en 18 tiros. La decisión «bajada sin concepto» se
  revisó con su razón: en planta sigue sin doble cobro; el **tramo
  vertical** — que la corrida en planta nunca dibuja — lo mide SAN-006
  cuando hay N.P.T. de dónde (aquí no los hay, y el diagnóstico lo dice).
- **Dos hallazgos agrupados** (principio 7, en el Diagnóstico, no en
  Riesgos): «4 de 68 corridas sin diámetro legible: 47 m que ninguna
  publicación deja cotizar» y «18 tiros de bajada sin niveles N.P.T.».
- **El hueco `detect` tiene su primer inquilino**: hidráulica y sanitaria
  se leen por su suite del registro, con conducta idéntica al trío.

### Suite cancelería cerrada (2026-08-29, rama `suite-canceleria`)

El scout tumbó el supuesto del spec: **no hay cuadro de cancelería como
tabla** en Marina (309 textos, cero N×M) — los tipos se dibujan como
alzados acotados (119 cotas, la ronda siguiente). Lo que sí hay es mejor:
**el globo de nomenclatura sabe su clave** — `CANC_ALUM` con atributo
`CLAVE` (CA-01…PA-02). La suite lee de ahí:

- `detect_cancel_pieces`: una pieza por globo con clave, familia por
  prefijo (CA/CB→cancel, PA/PTA→puerta, V/PV→ventana), como detección
  `opening` — CAN-001/CAN-002/CAR-001 la cobran **sin cambiar una línea
  del costing**. Marina: 35 piezas (29 cancel, 6 puerta), 22 claves.
- La suite ocupa su hueco `detect` con filtro de reclamo: el mismo insert
  jamás es pieza y además vano genérico (43 openings = 35 piezas + 8
  genéricos, cero dobles).
- Hallazgo agrupado «5 de 40 piezas sin clave legible» — y un mecanismo
  nuevo con doctrina: `promote_detection_warnings` lleva al diagnóstico
  SOLO los avisos de detección que sus reglas saben clasificar (el
  detector conoce denominadores que el presupuesto no ve; promover todo
  inundaría la lista que el diagnóstico existe para no inundar).
- Gold `canceleria-mini` (43 openings, F1 = 1.0); el eval completo sigue
  en ~10 s. Marina completo: estable (593/175/0) y con sus 35 piezas.

**Para la siguiente ronda de cancelería:** dimensiones por clave desde las
cotas del alzado (119 en la hoja) → los m² del cancel y el primer lector
real del seam S4.

### Ronda acabados cerrada (2026-08-29, rama `ronda-acabados`) — y el veredicto que cambia la cola

La suite de acabados existe y es correcta: marcas PI/PL con su clave
(98 leídas en Marina), locales anclados por marca (extensión razonada del
detector de rooms: una hoja que no nombra sus locales pero los marca con
acabados declarados ES una planta de locales), áreas por clave por local en
`acabados.json` y la Lectura, hallazgo agrupado «locales sin clave», gold
`acabados-mini` (98 marcas, F1 = 1.0). Sin locales, las claves cuentan
igual — piezas por clave con `m² = None`, nunca un área inventada.

**El veredicto estratégico, medido tres veces:** las áreas de acabados, la
albañilería profunda y los m² de cancelería están bloqueados por **la misma
causa raíz** — el fondo arquitectónico (xref) no entrega sus muros: la hoja
de acabados trae 378 «líneas de muro» que son flechas de símbolo, la de
albañilería es 988 cotas sobre una base ausente, y los alzados de
cancelería no anclan sus claves. Igual que eléctrica (DWG ilegible) y
carpintería (bloques tirados). **Cinco cosas, un desbloqueador: el
workstream de conversión (S3 profundo).** Ese spike deja de ser opcional:
es lo siguiente del motor.

### Spike de conversión cerrado (2026-08-29, rama `conversion-s3`) — el desbloqueador funcionó

- **El xref embebe, por fin.** Tres defectos apilados lo impedían: el
  casamiento exigía nombres idénticos cuando la subida slugifica
  (`_slug_key`); los directorios de búsqueda asumían hojas en `drawings/`
  cuando las convertidas viven en `converted/<dir>/`; y ezdxf valida la
  ruta declarada del bloque **antes** de consultar el `load_fn` — se
  reescribe a la resuelta. Marina completo + el archivo xref: **10 de 10
  referencias embebidas** (eran 10 ausentes), 22 locales poligonizados en
  la hoja de acabados desde los muros de la base, y los primeros m² reales
  por clave — *piso 8 → 69.82 m²*. La base convertida en modo mínimo trae
  los muros como entidades directas (MUROS1 ×272, MUROBAJO ×416): no hizo
  falta cirugía a LibreDWG.
- **Carpintería se lee: 2,583 entidades** (era ilegible). Cuatro
  enfermedades del convertidor, curadas en el saneador: BLOCK sin ENDBLK y
  POLYLINE sin SEQEND (ahora se **cierran** — antes la corrida se tiraba
  entera), entidades huérfanas dentro de BLOCKS tras un ENDBLK prematuro
  (se tiran contadas), ATTRIBs sin su INSERT (ídem), y el INSERT que
  declara `66=1` sin escribir ni un ATTRIB ni su SEQEND (la cadena abre
  desde la bandera). Gold `carpinteria-mini` (33 openings, F1 = 1.0).
- **Eléctrico: veredicto externo.** `dwgread` 0.13.3 rechaza el DWG
  (0x940) en todos los modos: el decodificador mismo no puede con el
  archivo. Camino de producto: pedir el re-export al cliente (o un
  LibreDWG más nuevo cuando exista); la cobertura ya lo declara ilegible
  con su razón.
- **Para el usuario:** subir el archivo XREF a los proyectos reales ahora
  sí paga — el aviso «súbela como hoja adicional» deja de ser un deseo.
- **Siguiente ronda registrada:** el casamiento marca↔local necesita
  tolerancia (2 de 22 locales con clave: la marca suele pararse junto al
  muro, no en el centroide), y albañilería profunda ya tiene su base
  embebida esperando su suite.

### Ronda albañilería y sustrato cerrada (2026-08-29, rama `ronda-albanileria`)

- **La ruta `arquitectura` (spec §9) existe**: XREF/ARQ es sustrato — sus
  muros y locales se detectan estampados `substrate: true`, el visor los
  ve, los locales anclan, y el presupuesto los ignora por regla general
  (guardia única en boq). El «leak» sospechado de EST-004 resultó no
  existir (el view-scoping ya lo excluía): la guardia queda de cinturón y
  tirantes.
- **Albañilería profunda, por fin**: su suite corre el detector de muros en
  sus hojas (la base embebida entrega), estampa `wall_kind: "tabique"`, y
  **ALB-001** cobra el m² con vano descontado — Marina: 736.5 m de muros,
  **1,983 m² de tabique sin precio**, con su nota de altura supuesta.
  EST-004 intacto (253.7). El hueco que lo escondía: la suma por plantas
  con niveles declarados solo recorría vistas estructurales — los muros de
  una planta de disciplina cobran ahora a altura supuesta, nunca cero en
  silencio.
- **La marca casa en su marco**: tolerancia de 2 m dentro del mismo marco,
  jamás de otro (la mediana de 16 m era marcos sin base, no near-misses).
  Marina: 5 claves con m² (eran 3).
- Gold `albanileria-mini` (154 muros: 136 sustrato + 18 tabique → ALB-001
  81.7 m², F1 = 1.0). Ocho fixtures, eval ~13 s.

### Tablero de nodos, Fase 1 cerrada (2026-08-29, rama `tablero-fase-1`)

La identidad de interfaz aprobada en la pista del tablero empezó a existir:

- **Candados con firma** — `ProjectReviews.gates` guarda quién abrió cada
  nodo y cuándo (`GateState`, nodos `presupuesto|programa|contrato`);
  `PUT /projects/{id}/gates/{node}` exige admin del taller u owner del
  proyecto (modo abierto pasa, como todo lo local-first), asienta en el
  `audit_log` y publica SSE `gate_updated`.
- **`GET /projects/{id}/tablero`** — una sola lectura barata que compone los
  seis nodos (planos, revisión, catálogo, presupuesto, programa, contrato)
  desde artefactos ya en disco: cobertura de lectura, verificación m de 3,
  líneas sin precio n de N, total, riesgos, candados y `my_role` (el hueco
  conocido del frontend, cerrado aquí). Artefacto ausente → nodo
  «pendiente», nunca 500.
- **El tablero es la vista principal** — la raíz del proyecto pinta los seis
  nodos sobre el lienzo punteado (DOM+CSS, sin librerías de grafo), un hecho
  por chip con denominador, presencia por nodo y el rail de actividad en
  vivo. El Resumen viejo vive intacto en `/resumen`; la barra lateral
  sobrevive hasta la paridad (decisión 1 de la especificación).
- **GateGuard** — las secciones de Programa y Contrato bloqueadas muestran
  el candado: qué falta (con enlaces), quién puede abrir y el botón para la
  autoridad. Presupuesto queda sin guardia en v1 a propósito (el money gate
  ya lo gobierna). Un error al leer el estado deja pasar: candado de
  proceso, no de seguridad.

Verificado: pytest completo verde, gold intacto (8 fixtures), lint + tsc +
build de producción verdes. Las rutas nuevas responden 401 en modo protegido
como el resto (sin puerta abierta accidental); la vista autenticada queda
para el humo con sesión de Diego.

**Refinado el mismo día (rama `tablero-railway`):** el lienzo ganó las
aristas del proceso — curvas medidas entre tarjetas que «fluyen» animadas
cuando el nodo de origen está en orden (dash sobre `--accent`, quieto bajo
`prefers-reduced-motion`) — y los permisos se volvieron visuales: un nodo
con candado que no puedes abrir se ve apagado y no responde al clic; el
botón «Abrir nodo» solo existe para quien tiene la autoridad. Se retiraron
las frases «tú puedes abrir» / «lo abre el administrador» del tablero y del
GateGuard: el permiso se ve, no se explica.

**Segundo refinado (rama `tablero-escenario`):** los nodos pasaron al
centro — el lienzo toma el ancho completo (la actividad bajó a una tira
discreta), y los chips-píldora se volvieron renglones etiqueta·valor con
número tabular y tono como punto: minimalismo denso. El backend ahora emite
`facts` descriptivos por nodo (entidades leídas, riesgos, plazo en días
hábiles con su calificador, anticipo/retención, periodos) y el importe del
nodo Presupuesto respeta el money gate: sin unidad confiable no viaja
ningún peso; con unidad sin firmar, viaja marcado «sin verificar».

**Tercer refinado (misma rama `tablero-escenario`):** el lienzo cubre toda
la pantalla con una barra superior delgada (identidad, Resumen, en vivo,
cambios, configuración); la navegación se mudó a los nodos — un clic abre
el nodo EN SU LUGAR con su menú adentro (nada de saltos sorpresa), la barra
lateral de las subpantallas se volvió contextual (Tablero/Resumen fijos +
el nodo donde estás + Ajustes; el mapa completo vive en el tablero y en el
cajón móvil) y las descripciones-tooltip de los nodos se retiraron. El
copiloto también se pulió: botón flotante circular con conteo en acento,
panel con identidad y burbujas de conversación, entrada redonda.

**Consolidación (misma rama, 2026-08-29):** la barra lateral desapareció de
toda la app — una sola barra superior con la miga proyecto/nodo/entrada
como navegación (el nombre regresa al tablero; identidad y conexión en un
popover). El lienzo se volvió lienzo de verdad: nodos que se arrastran y
estiran, paneo y zoom (rueda y controles), acomodo recordado por persona en
localStorage — datos de todos, acomodo tuyo. El visor del plano tomó la
retroalimentación del cliente: medidas al pasar el cursor (solo con unidad
honesta: metros nativos o unidades de dibujo × factor confiable), y en el
elemento seleccionado la ida y vuelta con el dinero — su concepto del
presupuesto, buscar uno parecido en el catálogo (ConceptPicker) y el ajuste
rápido de cantidad, sin salir del plano. El catálogo habla OPUS con nuestra
piel: una sola hoja jerárquica (fase → concepto → matriz como renglones),
celdas que guardan al salir sin botón, recurso nuevo por teclado
(typeahead), renglones fantasma para crear, y los insumos con descripción y
costo editables en su lugar.

**Ronda de pulido (2026-08-30, rama `pulido-navegacion`):** los menús de la
miga cuelgan de su propia flecha (no del origen de la barra), el hover
cambia de miga como en una barra de menús y el menú de la entrada trae a
los nodos hermanos — de cualquier parte a cualquier otra en un clic. Se
retiraron los tooltips que repetían lo visible o explicaban botones
(quedan los que revelan texto truncado o cargan conocimiento del oficio).
El texto gigante del plano (portadas, títulos) se desvanece al crecer más
allá de lo legible: deja de tapar y se puede explorar debajo. Y nació la
**ficha técnica** (`costing/ficha.py`): f'c, fy, varilla, t.m.a.,
revenimiento, fraguado, clase, colocación, fabricación, acabado, espesor,
proporción y elemento, extraídos del texto del concepto — a la vista en la
hoja del catálogo (el brillo OPUS) y decidiendo en el matcher (fy y
acabado castigan como la f'c; las razones llegan solas al ConceptPicker).

**Pre-escaneo de subida y partidas plegables (2026-08-30, rama
`presupuesto-opus`):** cayó el tercer punto de la retroalimentación del
cliente — el diálogo de nuevo proyecto ahora dice **qué datos jala** cada
hoja: `POST /disciplines/preview` rutea por el registro real de disciplinas
(la misma `route_sheet` del pipeline) y contesta con la disciplina y una
lista honesta de lo que esa suite lee hoy (lo no detectado se declara como
levantamiento; el detector eléctrico se dice pendiente). Cada archivo en el
diálogo trae su chip de disciplina y se despliega. Y el presupuesto ganó el
gesto que faltaba de OPUS: las partidas se pliegan con clic y su renglón
dice cuántos conceptos y qué % del costo directo pesan.

### Integración como análisis cerrada (2026-09-02, en `main`)

Los seis porcentajes planos de la integración dejaron de ser el techo: el
desglose de indirectos (campo + oficina central) se captura renglón por
renglón, el financiamiento se calcula del flujo a una tasa capturada y los
cargos adicionales se detallan — en modo dual, donde el porcentaje
declarado sigue siendo el sello de respaldo y el importe gana cuando el
análisis existe. El modo declarado es bit a bit el de ayer (gold intacto);
nada se inventa: el rubro en $0 es «sin capturar», el faltante se dice con
nombre, y la licitación rechaza con 409 los componentes por declarado (la
utilidad declarada por diseño no bloquea). El Excel imprime los documentos
guardados — hojas «Análisis de indirectos» y «Financiamiento» que cuadran
con la carátula al centavo — y la web enseña el prorrateo mientras se
captura. Once tareas TDD, ~34 pruebas nuevas, aceptación final fenceada.

### Consolidación de confianza-del-número (2026-09-02, rama `consolida-confianza`)

Los 28 commits de la rama paralela (una sola autoridad decide si un número
puede verse como dinero: `costing/presentation.py`, `money_basis` congelado
en el reporte, `MoneyState` hilado a cada hoja del Excel y `moneyState` en
la web; el colado espera a su cimbra en el programa; los conteos humanos de
medición viven junto a las revisiones; hallazgos con cuenta) se fundieron
con la integración como análisis. Decisiones del merge: la carátula itemiza
cada renglón con su fuente Y cada peso pasa por el veredicto (las dos
doctrinas juntas); la migración de cimbra de la rama se renumera a **v24**
(su v22 colisionaba con EST-016) y la cadena aprende la regla medida del
bloque v4 fuera de orden — las versiones nuevas van debajo, y el v23 de
ALB-001 se movió a su lugar; el registro del programa se **espeja** desde
`schedule.assumptions` (la frase canónica de `_crew_assumption_sentence`),
no se redacta dos veces; los cambios de la rama al Resumen viejo se
portaron a `/resumen`. Suite completa, gold, lint, tsc y build verdes sobre
el árbol fundido.

### Riesgos agrupados — la deuda M1 saldada (2026-09-02, rama `riesgos-agrupados`)

El pendiente M1 de la auditoría de densidad: Riesgos era el sistema sin
agrupar (112 tarjetas en Marina donde caben 4). Ahora `risks/agrupar.py`
junta los hallazgos por tipo en la fuente, con la regla del Diagnóstico:
una tarjeta por tipo con título del oficio (nunca el nombre interno del
método), cuenta con denominador donde lo hay («63 de N detecciones»), la
acción dicha una vez y en plural, y los miembros completos — la frase
original de cada elemento con su bbox, para que el salto al visor
sobreviva. La causa abre la lista aunque sea «low» (sparse_grid, unidades
desconocidas, plano vacío explican a los demás). `counts_by_severity`
sigue contando ELEMENTOS: agrupar ordena la pantalla, no encoge el riesgo.
La tarjeta web perdió el «Método:» en monoespaciada y el porcentaje de
confianza estampado (P0-4 de la misma auditoría) y ganó la lista plegable
de miembros. Los evals solo fencean tipos de riesgo — intactos.

### Pulido de pantallas (2026-09-03, rama `pulido-pantallas`)

Tres fricciones dichas por Diego, tres respuestas: (1) **la paleta de
salto directo** — ⌘K/Ctrl+K abre una paleta que lleva a cualquier pantalla
del proyecto en tres letras (la lista es el mismo `NODE_NAV` de la
navegación: una sola fuente), con botón ⌘K discreto en la barra; (2)
**presupuesto y parámetros dejan de bombardear** — las secciones apiladas
se volvieron pestañas `?tab=` (Partidas · Integración · Ajustes ·
Versiones; Supuestos · Análisis de indirectos · Insumos): una vista a la
vez, el resto a un clic, los banners de doctrina siempre visibles y el
estado de las filas sobrevive al cambio (se oculta, no se desmonta); (3)
**el teclado de OPUS en la hoja del catálogo** — ↑↓ recorren los
conceptos, Enter/→ abre la matriz, ← la cierra, la fila enfocada se marca
con el acento y las celdas siguen siendo celdas (tecleando en un input la
hoja no se mueve).

### Nodos condensados (2026-09-11, rama `nodos-condensados`)

La queja: para moverse entre las pantallas de un nodo había que abrir un
menú de la miga, y dentro de Planos y Revisión había que recorrer dos
columnas de tarjetas para llegar a lo de abajo. Cuatro respuestas: (1)
**la barra del nodo** — cuando la ruta pertenece a un nodo con varias
entradas, sus hermanas quedan fijas como pestañas bajo la barra superior
(`NodeWorkspaceBar` en `ProjectShell`, misma fuente `NODE_NAV`); la miga
pierde la tercera entrada y su menú desplegable — proyecto / nodo basta,
lo demás está a la vista; (2) **la lectura del plano en cinco pestañas
`?tab=`** — Hojas · Capas y familias · Levantamiento · Cuadros del plano ·
Avisos, con conteo en cada pestaña y estado vacío honesto en las que
antes simplemente desaparecían; (3) **la revisión en tres** — Elementos
del plano · Omitidos por el motor · Cuántos hay dibujados, el conteo deja
de vivir a dos pantallas de scroll; (4) **Programa y Flujo son dos
entradas del nodo** — fuera la tira `ProgramaFlujoTabs` que duplicaba a
la barra; y **el visor del plano cabe bajo las dos barras**
(`100vh − 5.5rem`, ya no `h-screen`) con la cabecera reducida a una línea,
porque la barra del nodo ya nombra la pantalla. La regla de las pestañas
sigue: la sección se oculta, no se desmonta, y el estado de las filas
sobrevive. Solo cambió la web: suite, gold y ruff intactos; tsc, lint y
build verdes.

### El lector de la base nativa de OPUS (2026-09-14, rama `lector-opus`)

Diego trajo una base OPUS de estructuras de acero y herrería (Ingeniería
Integral, mayo 2026): 301 conceptos, 334 matrices con 3,262 renglones,
417 insumos, 18 cuadrillas, el FSR con su formulación, 13 costos horarios
y el árbol capítulo → subcapítulo → concepto. Es la capa que ninguna
fuente oficial publica —las matrices con rendimiento— y llegaba en el
formato que el Excel de exportación pierde a medias. Ahora
`costing/sources/opus_native.py` lee las tablas Visual FoxPro (.DBF/.FPT)
sin librerías: elementos por `PREFIJO` (material, mano de obra,
herramienta, equipo, auxiliar, concepto), matrices por renglón con la
cantidad por unidad, el porcentaje de herramienta sobre la mano de obra
como `EQ-HERRAMIENTA`, la fase desde el subcapítulo del presupuesto
(`PRE_IDPAD` apunta al `PRE_IDUNI` del padre, el texto vive en la tabla 3
bajo el mismo `ID`), y el rendimiento por día derivado de las jornadas
de mano de obra por unidad — declarado derivado. Lo que Klave no modela
se dice, no se calla: las cuadrillas y los auxiliares entran como insumo
con su precio compuesto (el modelo no anida básicos todavía), los cargos
fijos «C.F.» y los insumos sin precio no entran. El endpoint de
`import-matrices` acepta el .zip de la carpeta (hasta 25 MB) y devuelve,
además del resultado, lo que la base declara: FSR, indirectos,
financiamiento, utilidad, costos horarios y capítulos. Sobre la base
real: 301 conceptos con matriz, 291 con fase del árbol, 297 con
rendimiento derivado. Cinco pruebas con un escritor DBF/FPT mínimo.
Queda para la pista del catálogo base: anidar básicos, importar el FSR y
los costos horarios como parámetros del taller, y leer varias bases de
una vez.

### Fase A · La base con precio (2026-09-14, rama `fase-a-base-con-precio`)

La primera fase del spec de catálogo base y paridad OPUS. (1) **Origen en
cada fila**: conceptos e insumos llevan `origin` (oficial · importada ·
generada · taller) y `origin_ref`; los sembrados por Klave se clasifican
«generada · semilla Klave», una persona que toca una fila ajena la vuelve
del taller y queda quién y cuándo; la migración clasifica lo que ya había.
(2) **La base se hojea sin tocar el taller**: una base de matrices (OPUS,
Excel) entra como fuente con sus componentes (`reference_components`);
`browse_reference` filtra por texto, fuente, partida (la canónica del
matcher) y región, y dice qué renglón ya está en el taller; «traer al
taller» crea el concepto con su precio de tabulador (oficial) o con su
matriz e insumos (importada), sin pisar claves existentes. (3) **Seis
fuentes oficiales nuevas** leídas con pypdfium2 (conserva espacios donde
pdfplumber pega palabras y abre el PDF cifrado de INIFECH) y openpyxl:
SICT costo directo carretero (3,715 conceptos), CONAGUA (2,009), INIFECH
Chiapas (1,644 con quince regiones), Guanajuato UEC en Excel (2,675
conceptos × seis regiones), su listado de materiales (52 insumos con precio
de mercado por región — la primera lista oficial de insumos) y su listado
de maquinaria (12 costos horarios). Descartados tras inspección: SICT
paramétricos (modelos, no renglones) y servicios (sin archivo). (4)
**Descargar e importar en un paso** (`POST /sources/{key}/download`,
manifiesto con sha256) y el **arranque del taller** (`POST
/sources/bootstrap`) que trae toda fuente oficial que falte y reporta la
que falla sin detener a las demás. (5) **La pestaña Base** sustituye a
«Fuentes de referencia»: la lista de publicaciones con «Descargar e
importar», la hoja de la base con filtros por partida (chips), fuente y
región, «Traer» por fila (Enter) y por selección (barra inferior que sólo
existe con selección, Esc la vacía); insignia de origen en las hojas de
conceptos e insumos; el taller vacío invita a traer los conceptos de sus
partidas; ⌘K llega a la base. Fences: suite (+24 pruebas), gold, ruff,
tsc, lint y build verdes.

### Fase B · Básicos, cuadrillas y el primer lote OPUS (2026-09-14, rama `fase-b-basicos`)

(1) **Una matriz puede contener una matriz**: `insumos.kind` (insumo ·
basico · cuadrilla) y `apu_components` con la clave del básico como dueño;
`build_apu` recurre con tope de cuatro niveles y un ciclo se rechaza con
los dos nombres; `recompute_basicos` resuelve de abajo hacia arriba y
escribe el precio como caché con la procedencia «derivado de su matriz»
(un básico con un componente sin precio conserva el suyo y lo dice); cada
línea del análisis lleva `sub_analysis` para desplegarse en su lugar. (2)
**El lector de OPUS deja de aplanar**: cuadrillas y auxiliares entran con
su matriz. Hallazgo de paso: la herramienta importada por porcentaje se
guardaba como cantidad 0.03 sobre un recurso que ya vale 0.03 — un 3 %
costaba 0.09 %; ahora se escala contra la fracción del recurso y un 3 %
es un 3 %. (3) **El diario de ajustes** (`price_adjustments`): subir o
bajar precios en lote por clave o filtro estampa vigencia y origen y deja
el antes de cada fila; sustituir un insumo en las matrices (sumando
cantidades si el nuevo ya estaba) guarda las matrices tal como estaban;
ambos se deshacen exactos y recalculan los básicos. (4) **Dónde se usa**:
conceptos con cantidad, importe y su parte del costo directo, y básicos.
(5) **Cuadrillas** en la pestaña de salario real: se arman con las
categorías, su jornada se deriva y cambia al aplicar el Fsr. (6) **La
web sin botones nuevos**: el inspector (panel derecho, Esc cierra) con
Precio · Matriz · Dónde se usa · Acciones; los básicos se despliegan en la
matriz con un chevrón; la hoja de insumos gana casillas y la barra de
selección con «Ajustar %» y «Sustituir en matrices…» (solo con selección);
⌘K llega a los insumos. Fences verdes; gold intacto.

### Fase C · Matrices generadas, validadas contra el precio oficial (2026-09-15, rama `fase-c-generadas`)

(1) **Plantillas de matriz por familia** (`costing/plantillas_matriz.json`,
diecisiete familias: dala/castillo, firme, plantilla, concreto hecho en
obra, concreto armado por elemento, concreto simple, cimbra, acero de
refuerzo, mampostería, aplanado, pintura, yeso, loseta, excavación,
relleno, acarreo, trazo, tubería): cada línea trae una fórmula sobre la
ficha del texto y **su fuente**, y cada rendimiento también. La ficha se
lee en números (f'c, sección b×h, espesor, elemento, acabado, material,
diámetro) y la firma del plano manda sobre el texto; la cimbra de una
columna de 30×40 sale de 2(b+h)/(b·h), el cemento de un concreto hecho en
obra sale de la tabla por clase, y donde el texto calla entra el valor
usual del oficio con su fuente dicha. Los valores están marcados «valor de
referencia Klave, revisar»: la tabla es un documento con fuentes que Diego
revisa, no un número mágico. La calculadora sólo sabe aritmética (nada de
nombres ni atributos). Una tubería sin diámetro **no se inventa**: se
rechaza con el motivo. (2) **Precios de referencia** (`insumos_semilla.json`):
un insumo sin precio toma el de referencia marcado «precio de referencia,
validar» y origen generada; la mano de obra se cobra a salario real (si el
taller nunca lo aplicó, se aplica con CONASAMI y el Fsr de ley, y queda
dicho); las cuadrillas de la plantilla nacen con su matriz. (3) **La
validación**: el costo directo de la matriz contra el renglón publicado que
mejor le corresponde (el matcher de siempre, sólo fuentes de precios
unitarios, puntaje ≥ 0.5); dentro de la tolerancia → validada, fuera →
fuera de rango con la desviación, sin renglón → sin referencia. El
veredicto vive en `concepts.validation`, se recalcula contra su misma
referencia cuando un precio cambia (alta de precio, ajuste en lote,
sustitución, deshacer, básicos) y sobrevive a la edición de una persona,
que promueve la fila a taller. La tolerancia es del taller (15 % por
defecto). (4) **Las fuentes de las líneas** viven en `apu_components.source`
(v27) y viajan en el análisis y en el estado del catálogo. (5) **API**:
generar una matriz (una del taller no se pisa sin `force`), generar las que
faltan (lo que ninguna plantilla reconoce se reporta), validar una o todas,
la tolerancia y las plantillas a la vista. (6) **Web sin botones nuevos**:
el veredicto en la fila junto al origen, la fuente bajo cada línea,
«Generar matriz» dentro de la matriz vacía, «Validar de nuevo» y
«Regenerar» al pie de una generada, el aviso «Generar las que faltan» que
sólo existe mientras haya huecos, el resumen de validación con la
tolerancia editable en su lugar, ⌘K. Desviación del spec: los archivos
curados viven en el paquete (`data/` es de cada instalación y no va al
repo). Fences: suite (+32 pruebas), gold, ruff, tsc, lint y build verdes.

### V1 · R1 · Variantes del plano y mapeo a tu catálogo (2026-10-05, rama `producto-v1`)

La primera ronda del producto v1 (spec `2026-09-16-producto-v1-cuantificacion-design.md`).
(1) **Variantes dentro del renglón**: cada detección recibe su firma —lo que el
plano declara y cambia el precio: sección y armado en columnas y trabes, tipo y
espesor en muros, sistema y espesor en losas, tipo de zapata, diámetro de
pilote, material y diámetro de tubería— y el renglón se separa por firma
midiendo cada grupo con la misma regla; las variantes suman exacto (reparto
proporcional cuando la regla no es aditiva, y se dice). Viven **dentro** de
`BoqLine.variants` porque quince módulos indexan los renglones por clave del
motor. En Marina: 27 variantes de columnas y castillos (las secciones del
cuadro), 41 de trabes, muros por block y espesor, losas por sistema y peralte,
tuberías por diámetro. Trazo, aplanado, pintura y pisos no se separan: su
precio no depende de esa firma. El aviso «dos diámetros en una línea se
presupuestan juntos y no deberían» desaparece porque ya no pasa.
(2) **Mapeo al catálogo de la oficina**: cada variante se empareja con los
conceptos del taller y los renglones de las bases importadas con el
emparejador de siempre (≥ 0.8 se aplica, 0.5–0.8 queda como duda, debajo
«sin equivalente»); la memoria (`variant_mappings`) es del taller y respeta
la decisión de una persona en el siguiente proyecto; el importe del renglón es
la suma de sus variantes con el precio del concepto o renglón al que apuntan.
Lo que Klave sembró o generó no cuenta como catálogo de la oficina (hallado
contra la base OPUS de acero real: la cimbra del motor se mapeaba a sí misma).
(3) **Etiquetas**: cada confirmación, exclusión y decisión de mapeo se anota
en `labels.jsonl` con lo que el motor sabía del elemento — el gancho del
lector que aprende, activo desde el primer piloto. (4) **API** bajo
`/projects/{id}/variantes` (el middleware cuida el proyecto) y **web**: la
pestaña «Tu catálogo» en Revisión (buscar en mi catálogo, confirmar, elegir
otro, sin equivalente, olvidar) y las variantes con clave y precio en el
renglón abierto del presupuesto; ⌘K. (5) **Limpieza**: mypy sin errores; el
«se puede deshacer desde Importaciones» por fin tiene dónde — «Ajustes
recientes» con Deshacer bajo la hoja de insumos. El gold vigila ahora que las
variantes cuadren con su renglón. Pendiente: la prueba del mapeo contra una
base de obra negra real de una oficina (la de acero sólo da 4 dudas de 150
variantes, como debe).

### V1 · R2 · Fuera de la puerta (2026-10-06, rama `v1-r2`)

(1) **Generadores con referencia** (`costing/referencias.py`): agrupados por
variante con la clave de la oficina; cada elemento con su hoja, su planta (el
marco al que el motor lo asignó), los ejes cercanos **sólo si el plano los
nombró** (la malla de Marina trae nombres automáticos «V1, V2»: no se citan) y
una liga «Ver» al visor encuadrado (`?bbox=`); un id estable por elemento
(hoja, tipo, marca, centro a 5 cm). Fuera la columna de confianza de los
generadores y del presupuesto (doctrina: la duda se resuelve en Revisión, no
se estampa). (2) **OPUS y Neodata por variante**: una fila por variante con
la clave de su mapeo, si no el alias del renglón, si no una neutra
`PL-0001` — la misma en todas las hojas del libro (presupuesto, licitación,
APUs, programa); las claves del motor ya no salen en ningún documento; columna
Partida. (3) **Lo que el plano no dio** (`costing/captura.py`): elementos
vistos que ningún renglón cuantificó, renglones sin precio y hojas de las que
no se leyó nada; hoja en cada libro, `GET /projects/{id}/captura` y un aviso
plegado en el presupuesto. Para contarlo bien, un renglón guarda ahora todos
sus elementos (antes 200; Marina trae 2,405). (4) **Liga para compartir**:
el dueño la crea desde Exportar (14 días, máximo 90, revocable); quien la abre
sin cuenta ve el plano y descarga los generadores con ligas al visor
compartido — nunca dinero; inexistente, caducada o revocada responden igual;
`/compartido/` es el único prefijo abierto nuevo y sólo tiene GET. (5) La
suite ya no toca la base de usuarios de quien la corre: con una cuenta en
desarrollo siete pruebas de endpoints daban 401. Pendiente de R2: verificar
los libros contra una instalación real de OPUS y de Neodata (no hay layout
oficial público; Diego tiene las instalaciones) y el lector de Neodata contra
un export real.

### V1 · R3 · Fluidez del visor (2026-10-06, rama `v1-r3`)

Medido primero en Marina (sólo lectura): `/geometry` pesaba **18.3 MB** sin
comprimir y tardaba **~0.8 s** en cada visita (se rearmaba de un archivo de
100 MB); el catálogo, la revisión y el tablero ya eran ligeros (60 KB / 10 ms,
380 KB / 36 ms, 5 ms). (1) **Servidor**: compresión gzip (Starlette no
comprime el bus SSE), coordenadas a cuatro decimales (una décima de milímetro
en metros), el dibujo de cada corrida armado una vez y guardado en memoria
(tres corridas, ~60 MB cada plano grande), `/geometry/shapes` con ETag (304 si
no cambió), `/geometry/detections` para refrescar sólo veredictos y `?sheet=`
para bajar una hoja. Resultado: **1.46 MB comprimido; 60–150 ms en la segunda
visita**, 1.2 s la primera (`python -m scripts.perf_plano`). (2) **Visor**: la
capa estática se pinta una vez en un lienzo aparte y se desplaza o escala con
el gesto (nítida al detenerse), lo que cae fuera de la vista no se pinta, un
cuadro por fotograma, y pasar el ratón ya no repinta el plano (antes un
efecto sin dependencias repintaba las 76 mil figuras en cada movimiento);
fuera el porcentaje de confianza del tooltip. Una revisión de un colega
refresca sólo las detecciones. (3) **Coordinación**: otra sesión (limpieza de
interfaz) trabaja en el mismo árbol — el encuadre por grupo de hojas, una
hoja a la vez en el visor; sus cambios siguen sin confirmar y se combinan
limpio con éstos. La mitad «camino dorado» de R3 (§4.2) quedó con esa sesión.
Sin medir aún: cuadros por segundo en un navegador real (el visor está detrás
de la sesión y la API de desarrollo corre sin recarga).

### V1 · R3 · El camino dorado (2026-10-06, rama `v1-camino`)

Después de que la sesión de limpieza de interfaz confirmó su trabajo
(8903077). (1) **«Lo que sigue»**: el tablero calcula el siguiente paso del
camino de v1 —subir, leer, confirmar unidades, revisar los elementos, mapear
las variantes a tu catálogo, darle precio a lo que falta, exportar— y lo
muestra como un solo botón principal (`siguiente` en `GET /tablero`). (2)
**Las palabras del oficio**: «elementos» y «la lectura» en vez de
«detecciones», «Klave» en vez de «el motor», «lecturas» en vez de «corridas»
(32 textos en 18 archivos); se quedan las «reglas por m²» de los paramétricos
y las «corridas de instalación», que son del oficio. (3) **El catálogo abre
en «Conceptos y matrices»**. (4) **De cada número al plano**: la fila de
Revisión encuadra su elemento exacto y cada renglón de «Tu catálogo» abre sus
elementos. Ya estaban: la obra de ejemplo en un taller vacío y los estados
vacíos que dicen qué hacer. **No se ocultó** ningún nodo: la decisión del
tablero (visible con candado) manda sobre el «aparecer cuando se llegue» del
spec. Pendiente: la misma gramática de gestos (inspector a la derecha) en
Revisión y Presupuesto, y la prueba con cinco ingenieros.

### Bloqueos de despliegue (2026-10-06, rama `despliegue-bloqueos`)

Los cinco que encontró la auditoría del 2026-09-28, verificados contra el
código de hoy antes de tocar nada. (1) **Producción ya no abre por
accidente**: sin cuentas sólo sirve `/auth` y `/health` (antes un volumen
nuevo servía todo sin sesión); con la base de usuarios caída cierra siempre,
también tras reiniciar (antes, si el proceso no recordaba haber visto
cuentas, abría). En desarrollo sigue el modo local abierto. (2) **El
copiloto y los alias con recálculo cuidan el proyecto**: la regla de acceso
vive en `apps/api/auth/access.py`, el middleware la usa bajo `/projects` y las
rutas de fuera que reciben un proyecto la piden (ver para las acciones y
preguntas del copiloto; editar para aplicar y para los alias); probado con
dos talleres reales. (3) **El respaldo cubre todo `/data`** con las bases
SQLite por copia en línea (probado con escrituras concurrentes y
`integrity_check`); antes faltaban el registro de proyectos, la bitácora, las
fuentes y las ligas. (4) **`apps/web/public` existe en un checkout limpio**.
(5) **El registro**: producción exige `KLAVE_REGISTRATION=invite_only`, y
«sólo por invitación» deja entrar a la primera cuenta, que funda el taller
(antes un servidor cerrado no tenía por dónde entrar). Falta en manos de
Diego: el valor por defecto de `KLAVE_REGISTRATION` en su
`docker-compose.prod.yml` (sin confirmar) sigue en `open`, y con este cambio
producción no arranca así — una línea.

### V1 · R4 · Qué cambió entre revisiones (2026-10-06, rama `v1-r4-cambios`)

(1) **El cálculo** (`costing/cambios.py`): cada elemento de la lectura
anterior se busca en la nueva por identidad (hoja, tipo, marca, posición a
5 cm) y, si no, por la misma marca a menos de 2 m (se movió); lo que no
encuentra pareja es agregado o eliminado — nunca se adivina. «Modificado» es
una propiedad que cambia una cantidad o un precio (sección, armado, longitud,
área, espesor, diámetro, claro, tipo). Por concepto: cantidad antes y
después, diferencia y su importe a precio unitario de hoy. **Probado en
Marina** (2,521 elementos, sólo lectura): una copia sin tocar da cero
cambios; una con tres columnas movidas 1 m, una zapata quitada y una trabe
alargada da exactamente esas cinco. La primera versión daba 56 «modificados»
falsos: corridas partidas por diámetro y tableros con el mismo centro
comparten identidad y se emparejaban cruzados; ahora gana la pieza que
coincide en propiedades y contorno. (2) **Revisiones**: cada lectura guardada
con su nombre (Rev C, ejecutivo), su versión de Klave y — desde ahora — el
sha256 de los planos que leyó (`inputs.json`), para distinguir una revisión
del plano de una lectura nueva de los mismos planos. Las lecturas viejas de
Marina no lo guardaban: entre la del 29 de agosto y la de hoy aparecen 116
elementos (98 muebles y 18 muros) y la pantalla dice que cambió Klave y no se
sabe si el plano. (3) **API** `/revisiones`, `/cambios`, `/cambios.xlsx`
(aditivas y deductivas por concepto con su clave visible, y por elemento con
liga al visor). (4) **Web**: «Cambios entre revisiones» en el nodo Planos,
y el visor pinta los cambios con `?cambios=` (agregado, movido, modificado, y
lo eliminado punteado). Pendiente: la vista «supuesto → leído» del
anteproyecto al ejecutivo (el cálculo ya sirve: compara renglones por
concepto) y verlo en un navegador con sesión.

### V1 · R5 · Esperado y ausente, tus índices, la convocante antes de firmar (2026-10-06, rama `v1-r5`)

(1) **Esperado y ausente** (`costing/implicaciones.json` + `completitud.py`):
lo que una partida trae consigo — plantilla bajo la zapata, relleno y acarreo
tras la excavación, acero y cimbra del concreto armado, aplanado, castillos y
cadenas del muro, pintura del aplanado, escalera con más de una planta — y el
presupuesto no tiene, con su evidencia; viaja en «Lo que el plano no dio». El
acero y la cimbra se piden **renglón por renglón**: la primera versión daba
por presente el acero de Marina porque una losa decía «armada con varilla», y
el acero de una losa no arma las columnas. Lo que un renglón dice incluir
(«incluye acero, cimbra») cuenta. En Marina faltan relleno, acero de refuerzo
(ocho renglones de concreto sin acero) y escalera (cuatro plantas); en
prueba-1, acero y escalera. (2) **Tus índices**: cada recálculo guarda los
índices del proyecto en el catálogo del taller y cada uno se compara con los
otros proyectos (con tres o más: mediana, rango y la frase cuando cae fuera).
El gold no escribe en esa historia (una primera corrida sí lo hizo; se
borraron esas siete filas). (3) **La convocante antes de firmar**: la pantalla
vivía sólo en Contrato, tras su candado; ahora también es una entrada del
nodo Presupuesto. Cada renglón se compara contra la variante del plano que
nombra, dice en palabras lo que Klave mide con su liga al plano (antes: la
clave del motor y un porcentaje) y sale a Excel. De paso: la primera lectura
de un proyecto ya aplica la memoria del mapeo del taller (R1 sólo la aplicaba
al recalcular).

### El lector que aprende · F1 · Lo que se ve y se guarda (2026-10-06, rama `lector-f1`)

La primera ronda del lector (spec `2026-10-04-lector-que-aprende-design.md`):
los datos, sin modelo todavía. (1) **Rasgos** (`detection/features.py`,
versión 1): lo que cada detector medía y tiraba tras su umbral — tamaño en
metros, sección, longitud, área, distancia al cruce de ejes más cercano,
prefijo de la marca y cuántas veces se repite, fichas de capa y de bloque, el
método de la regla — viaja en cada etiqueta; nunca coordenadas absolutas.
(2) **Revisiones que sobreviven a un reproceso**: cada revisión guarda la
identidad estable del elemento y, tras procesar, la que ya no encuentra su
clave se mueve al elemento con la misma identidad (las marcas «MUE-01» que se
vuelven «MUE-001» dejaban de aplicar en silencio); las que no tienen a dónde
ir se dicen. (3) **Candidatos** (`candidates.jsonl` por corrida): figuras
cerradas y bloques con tamaño de elemento que ninguna regla tomó, con sus
rasgos y «no considerado», sin tocar ninguna detección — en Marina 1,667 en
0.18 s, muchos en capas de cotas y muros: los ejemplos de «no es elemento» que
el modelo necesita. (4) **Gestos**: «Es otro elemento…» en cada renglón de
Revisión (excluye y registra la familia nombrada con la medida que la lectura
traía; si no trae la medida que esa familia pide, lo dice), y el elemento
omitido gana su lugar en el plano; los dos escriben etiqueta. Pendiente para
F2/F3: el perfil del taller, el modelo y la duda, el consentimiento para
compartir (las etiquetas de F1 no salen del proyecto).

### El lector que aprende · F2 · El perfil del taller (2026-10-06, rama `lector-f2`)

Cada oficina dibuja a su modo, y lo enseña cada vez que revisa. Ahora esas
revisiones se quedan en el taller: cada confirmación, exclusión,
reasignación y omitido agregado suma a favor o en contra de «este bloque (o
capa) es esta familia» (`costing/perfil.py`, tabla `perfil_taller` del
catálogo). Con **tres a favor y ninguna en contra** la entrada es firme: un
bloque sin reclamar dibujado así entra a la lectura del siguiente proceso
como esa familia — sólo castillo, columna o pilote, porque un bloque
aprendido no da una longitud ni un área —, con método `perfil_del_taller`,
una duda en su renglón que dice cuántas veces lo confirmó el taller, y
excluible como cualquier lectura. Lo que el taller **excluye** tres veces
nunca se quita: entra con una duda que lo dice. Cada proceso lo cuenta en una
línea de avisos; el catálogo lo lista en «Lo que tu taller enseñó» (pestaña
Plantillas) con lo que ya actúa y «Olvidar». El gold corre sin perfil para
medir sólo el motor. Nada de esto sale del taller; deshacer una revisión no
resta su voto — para eso está «Olvidar». Pendiente para F3: el modelo, la
duda con sus dos razones y el consentimiento para compartir.

Ver también: [principios-de-interfaz.md](principios-de-interfaz.md) ·
[auditoria-densidad.md](auditoria-densidad.md) ·
[plan-de-pulido.md](plan-de-pulido.md)
