# Las suites por disciplina — diseño

Fecha: 2026-08-28. Hija de
[2026-08-28-motor-multidisciplina-design.md](2026-08-28-motor-multidisciplina-design.md)
(el espine S1–S5 y la suite hidrosanitaria viven allá). Este documento
especifica **las demás disciplinas de edificación**, cada una con la misma
vara: detección geométrica que deriva cantidades, no conteos; cuadros con
autoridad; riesgos agrupados; gold propio. El vocabulario citado no es
inventado: sale de los 16 DWG reales de Marina Lote 04 y de la convención
mexicana de planos.

## 0. El contrato de una suite (lo que cada sección llena)

Toda suite del registro (S1) declara: **vocabulario** (capas, bloques, tags,
frases de especificación) · **detectores** (geometría → elementos) ·
**cuadros** (sus tablas, enchufadas a la cadena de autoridad) · **conceptos**
(familias del catálogo que alimenta) · **riesgos** (propios, agrupados por
causa, con denominador y exposición física) · **gold** (fixtures reales) ·
**dependencias** (qué necesita del espine o de otras suites).

**Reglas de reclamo entre suites** — donde dos disciplinas ven lo mismo:

- **Muros**: la suite estructural reclama los de concreto (EST-MURO
  CONCRETO, MC-n); albañilería reclama tabique/block. Un muro reclamado por
  una suite no vuelve a contarse en otra; el vano vive en el muro y
  cancelería/carpintería solo lo **consumen**.
- **Salidas eléctricas vs especiales**: el símbolo decide por vocabulario;
  un bloque que ambas reconocen se resuelve por la capa, y si persiste el
  empate, se emite en una sola con aviso — nunca en las dos.
- **La simbología del plano manda** sobre la tabla global (regla de S1),
  para todas las suites por igual.

---

## 1. Cancelería (aluminio: ventanas, puertas-ventana, canceles)

**Por qué va temprano:** es la prueba visible del modelo — cuadro + vanos ya
existentes — y Marina la trae legible (`CANC_ALUM`, tags sobre
`NOMENCLATURA`).

- **Vocabulario:** capas CANC/CANCEL/ALUM/VENTAN; tags V-n, PV-n, CA-n en
  capa de nomenclatura (la gramática de tags del levantamiento ya los lee);
  bloques de cancel por tipo.
- **Detectores:** (1) tag en planta → pieza posicionada; (2) casamiento
  **tag ↔ vano** — el detector de muros ya devuelve `openings[]` con su
  ancho medido; la pieza hereda el vano y su dimensión real; (3) piezas en
  alzado dentro de marcos de detalle quedan como detalle, no como pieza
  (regla de vistas existente).
- **Cuadros:** el **cuadro de cancelería** (clave, dimensiones, material,
  cristal, cantidad) es la autoridad de dimensiones y de tipos — rango
  cuadro > vano medido > supuesto. La cantidad del cuadro **se compara**
  con las piezas contadas en planta y la discrepancia es riesgo, no
  sobrescritura silenciosa.
- **Conceptos:** piezas por tipo (PZA) y m² de cancel por sistema; el vano
  ya descuenta en albañilería/acabados (regla A4 existente).
- **Riesgos:** tag sin vano que lo reciba (n de N); cuadro declara k piezas
  y la planta cuenta j; vano sin cancel asignado.
- **Gold:** hoja de cancelería de Marina — piezas por tipo etiquetadas.
- **Dependencias:** vanos del detector de muros; lector de tablas de S4.

## 2. Eléctrica

**Por qué así:** el valor está en el **tablero y sus circuitos** — la tabla
del plano es un presupuesto en miniatura. En Marina el DWG no convierte
(READ ERROR 0x940): esta suite **arranca cuando S3 lo destrabe** y se
desarrolla contra otros planos reales mientras tanto.

- **Vocabulario:** capas ELEC/LUMIN/CONTACT/APAG; bloques de salida
  (contacto, apagador, luminaria, salida especial), símbolo de tablero;
  frases de calibre y canalización ("2-12 AWG + 1-14", "POLIDUCTO 3/4\"").
- **Detectores:** (1) salidas por símbolo vía índice de prefabricados, por
  tipo y por local (rooms); (2) **cuadro de cargas del tablero** →
  circuitos, con qué salidas alimenta cada uno (la tabla lo declara);
  (3) canalización: corridas de guía entre salidas por capa, ML por
  trayectoria con calibre del texto; las curvas de guía (arcos) cuentan
  como trayectoria, no como pieza.
- **Cuadros:** cuadro de cargas (circuito, polos, calibre, carga, longitud)
  con rango de autoridad máximo; simbología propia del plano.
- **Conceptos:** salidas por tipo (SAL), ML de canalización+cableado por
  calibre, tableros por catálogo, luminarias PZA.
- **Riesgos:** salida sin circuito declarado; circuito del cuadro sin
  salidas halladas; tablero sin cuadro de cargas legible (bloqueante de la
  disciplina, no del proyecto).
- **Gold:** pendiente de un plano eléctrico legible; el primero que
  convierta se captura.
- **Dependencias:** S3 (conversión), S2 (símbolos), rooms (S4).

## 3. Gas

Suite corta y de alto valor de seguridad.

- **Vocabulario:** capa GAS; frases "PEAD 19MM", "COBRE TIPO L"; bloques de
  calentador, tanque estacionario, medidor.
- **Detectores:** corridas por material/diámetro (mismo motor de corridas
  segmentadas de hidrosanitaria, parametrizado); equipos por símbolo;
  llegadas a muebles (estufa, calentador, secadora) por cercanía a bloques
  de mueble.
- **Conceptos:** ML por material/diámetro, PZA de equipos y válvulas.
- **Riesgos:** corrida sin especificación de material (aquí el material es
  norma, no detalle); equipo sin llegada.
- **Gold:** hoja de gas de Marina ("PEAD 19MM" ya leído como spec hoy).
- **Dependencias:** el detector de corridas por spec de hidrosanitaria (se
  construye una vez, se parametriza por disciplina).

## 4. Aire acondicionado (AA / HVAC)

- **Vocabulario:** bloques con la capacidad en el nombre («Cond Mini 1
  Ton», «Compuerta 12 CZ» — Marina los trae así); capas AA/CLIMA/DUCTO;
  frases de tonelaje y de diámetro de condensado.
- **Detectores:** (1) equipos por símbolo con **capacidad parseada del
  nombre del bloque** (`parse_block_name` ya existe para eso); (2) pares
  evaporadora↔condensadora ligados por la línea de refrigerante/condensado;
  (3) ductos y compuertas donde el plano los dibuja; drenes de condensado
  como corridas.
- **Conceptos:** equipos PZA por tonelaje, ML de refrigerante/condensado,
  compuertas/rejillas PZA.
- **Riesgos:** evaporadora sin condensadora casada; equipo sin dren.
- **Gold:** hoja AA de Marina (25 compuertas ya se contaron una vez).
- **Dependencias:** S2 (los nombres de bloque son el dato).

## 5. Instalaciones especiales (CCTV, seguridad, voz y datos)

- **Vocabulario:** bloques Camara/sirena/sensor/nodo; capas CCTV/SEG/VOZ;
  central/DVR por símbolo.
- **Detectores:** dispositivos por símbolo y por local; cableado como
  corridas hacia la central cuando está dibujado, y como supuesto declarado
  (distancia por trayectoria) cuando no — **el supuesto se enuncia**, regla
  de la casa.
- **Conceptos:** dispositivos PZA, ML de cableado por tipo, central PZA.
- **Riesgos:** dispositivo sin trayectoria a la central; central ausente
  con dispositivos presentes.
- **Gold:** hoja CCTV de Marina.
- **Dependencias:** S2; rooms para "dispositivos por local".

## 6. Acabados y plafones

**El caso que rompe el molde:** Marina NO dibuja los acabados como
regiones — los declara con símbolos QRF/CAMBIO-ACABADO y con el **cuadro de
acabados** (por local: piso, muro, plafón). La geometría viene de otro lado:
de los **locales**.

- **Vocabulario:** capas ACAB/A-PISOS/CAMBIO-ACABADOS/PLAFON; textos
  "H LIBRE"; claves de acabado del cuadro.
- **Detectores:** (1) **locales** por el detector de rooms sobre la planta
  arquitectónica (el sustrato); (2) el cuadro de acabados asigna
  clave → local; el área del local es el m² del piso, el perímetro × altura
  (H LIBRE, menos vanos ya medidos) es el m² de muro, el área del local es
  el plafón; (3) los símbolos de cambio de acabado parten un local en zonas
  cuando existen.
- **Cuadros:** el cuadro de acabados es la autoridad; sin cuadro, el
  levantamiento de claves queda mapeable por el taller (flujo existente).
- **Conceptos:** m² por acabado (piso/muro/plafón), zoclos en ML.
- **Riesgos:** local sin acabado declarado (n de N con m² expuestos);
  clave del cuadro sin local que la use.
- **Gold:** hojas de acabados y plafones de Marina.
- **Dependencias:** rooms + niveles (S4), vanos (muros), lector de tablas.

## 7. Albañilería (profunda)

Hoy albañilería cayó a levantamiento (correcto para frenar zapatas
fantasma); la suite propia la vuelve primera clase.

- **Vocabulario:** el ya aprendido de Marina — CE-n cadenas (EST-CADENAS Y
  DALAS), CR-n cerramientos, muros de tabique/block por capa; pretiles de
  azotea (regla A11 existente).
- **Detectores:** muros de tabique con el detector de muros (autoridad de
  capa propia, reclamo coordinado con estructural); cadenas y cerramientos
  por tag y por trayectoria de muro; castillos ahogados donde el plano los
  marca.
- **Conceptos:** m² de muro por espesor/material (con descuento de vanos
  medido — A4), ML de cadenas/cerramientos (EST-005 ya existe), firmes.
- **Riesgos:** muro sin cadena de remate declarada; espesor no legible.
- **Gold:** las dos hojas de albañilería de Marina (hoy casi puras cotas —
  el gold fija lo que sí hay, y la cobertura declara lo que no).
- **Dependencias:** coordinación de reclamo con la suite estructural.

## 8. Carpintería y herrería

- **Vocabulario:** tags P-n (puertas), CL-n (closets), muebles de cocina;
  herrería H-n, barandales, rejas; cuadros de carpintería/herrería por
  clave.
- **Detectores:** piezas por tag casadas a vanos (puertas) o a locales
  (closets, cocinas); herrería por tag y por trayectoria (barandal en ML).
- **Cuadros:** cuadro de carpintería (clave, dimensión, material) como
  autoridad, mismo lector que cancelería.
- **Conceptos:** PZA por clave, ML de barandal.
- **Riesgos:** discrepancia cuadro↔planta; puerta sin vano.
- **Gold:** **bloqueado por S3 en Marina** (13 CARPINTERÍA convierte con 0
  entidades: el contenido vive en bloques que LibreDWG tira). Se captura en
  cuanto la conversión lo entregue o llegue otro plano real.
- **Dependencias:** S3 para Marina; vanos; lector de tablas; S2.

## 9. Arquitectónico (sustrato, no partida)

La planta arquitectónica no alimenta conceptos propios: alimenta **locales,
niveles, vanos y ejes de referencia** que las demás suites consumen. Se
declara en el registro como suite de sustrato: sus detecciones (rooms,
niveles) existen, se muestran en la Lectura, y no valen dinero por sí
mismas. El xref arquitectónico embebido en cada hoja de instalaciones es la
misma geometría — leerla una vez y compartirla es trabajo del índice de
prefabricados (S2), no de cada suite.

---

## 10. Orden de aterrizaje y estado de datos

| # | Suite | Datos reales hoy | Bloqueo |
|---|---|---|---|
| 1 | Hidrosanitaria — **cerrada 2026-08-29**: corridas por tramo de Ø, tiros de bajada ligados (SAN-006 espera N.P.T.), hallazgos agrupados, hueco `detect` ocupado. Nota: media §2 ya existía (corridas con Ø/material, muebles→salidas, registros) — medir antes de construir. | Marina convierte | — |
| 2 | Cancelería — **cerrada 2026-08-29**: la pieza se lee del globo con clave (35 piezas, familias por prefijo, cero cambios de costing); no hay cuadro-tabla en Marina — dimensiones por clave desde las 119 cotas del alzado quedan para la ronda 2. | tags legibles | — |
| 3 | Gas | spec "PEAD 19MM" legible | — |
| 4 | AA | bloques con tonelaje legibles | — |
| 5 | Especiales (CCTV/voz) | bloques legibles | — |
| 6 | Acabados y plafones — **suite cerrada 2026-08-29**: marcas PI/PL con clave (98), locales anclados por marca, áreas por clave cuando la base entregue muros. Áreas: bloqueadas por el xref arquitectónico. | símbolos legibles | xref (S3) |
| 7 | Albañilería profunda — **cerrada 2026-08-29** (tras el spike): la base embebe, la suite estampa tabique y ALB-001 cobra el m² con vano descontado (Marina: 1,983 m² sin precio). La ruta arquitectura (§9) quedó implementada: sustrato que se ve y jamás cobra. Cadenas CE-n/CR-n: ronda dos. | base embebida | — |
| 8 | Eléctrica | **no convierte** | S3 |
| 9 | Carpintería/herrería | **0 entidades tras convertir** | S3 |

El orden 2–5 puede reordenarse por lo que los talleres suban; 8 y 9 entran
en cuanto S3 los destrabe. Cada suite = su plan de implementación propio,
escrito contra el código del momento, con su gold como tarea uno.

## 11. Aceptación (hereda la del doc madre, sin excepciones)

Gold propio en verde · cero silencios (cobertura por disciplina en la
Lectura) · riesgos agrupados con denominador · la simbología del plano
manda · nada re-rompe el gold de las suites ya aterrizadas.
