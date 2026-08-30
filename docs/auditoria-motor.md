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

Ver también: [principios-de-interfaz.md](principios-de-interfaz.md) ·
[auditoria-densidad.md](auditoria-densidad.md) ·
[plan-de-pulido.md](plan-de-pulido.md)
