# El motor multidisciplina — diseño

Fecha: 2026-08-28. Decisión de producto de Diego, en sesión: **el motor deja
de ser un motor estructural con acompañantes; lee todas las disciplinas de un
proyecto de edificación, a profundidad, y correcto.** Sin atajos: detección
por disciplina con derivación geométrica, no solo conteos. Dos decisiones
cerradas en la misma sesión: la primera suite profunda es **hidrosanitaria**,
y el alcance cercano es **edificación** (Marina-like); las obras pesadas
(terracerías, pavimentos, SICT) entran después por el mismo registro.

Contexto: [auditoria-motor.md](../../auditoria-motor.md) ·
[2026-08-28-tablero-de-nodos-design.md](2026-08-28-tablero-de-nodos-design.md)
· memoria de Marina (16 DWG reales, 12 hojas no estructurales).

## 0. La tesis

Lo estructural tardó meses porque construyó el **sustrato**: marcos, vistas,
unidades por archivo, índice espacial, cadena de autoridad de cuadros,
ligas de cotas, confianza, gold set. Ese sustrato es neutral a la disciplina.
Lo que falta no es repetir el esfuerzo doce veces: es (a) un **registro** que
haga de cada disciplina un ciudadano de primera, (b) el **índice de
prefabricados** como primitivo central — las instalaciones se dibujan casi
enteramente como bloques —, (c) **conversión pareja** — nada se lee de lo que
LibreDWG tira —, y (d) **gold por disciplina**, porque "profundo y correcto"
sin fixture propio es solo profundo.

El sesgo estructural vive hoy en una línea: `reads_as_structure` con su
«desconocido = estructura» y su blocklist `NON_STRUCTURAL`. Eso se invierte.

## 1. El espine (S1–S5)

### S1 · Registro de disciplinas

`detection/disciplines/` — cada disciplina declara un `DisciplineSuite`:

- **vocabulario**: patrones de capas, familias de bloques, gramáticas de
  tags (V-1, CA-15), frases de especificación ("PEAD 19MM", "Ø 1/2\"").
- **detectores**: la lista de funciones de detección geométrica propia.
- **lectores de cuadros**: parsers de sus tablas (cuadro de cancelería,
  tablero eléctrico), enchufados a la cadena de autoridad de `schedules.py`.
- **familias de conceptos**: qué códigos del catálogo alimenta.
- **riesgos**: comprobaciones propias (bajada sin registro, salida sin
  circuito), con la política de agrupación del Diagnóstico (principio 7 —
  nunca una tarjeta por repetición).

**Ruteo por votación, no solo por nombre de archivo.** El nombre propone
(slug con ñ perdida incluido), y el contenido vota: capas y bloques del
archivo contra los vocabularios. Una hoja que ninguna suite reclama cae a
**levantamiento con aviso** — nada se lee como cero, nunca. La simbología
del propio plano (su cuadro de leyenda) tiene rango de autoridad **sobre**
la tabla global de símbolos: el plano que declara qué significa su símbolo
manda sobre nuestra convención.

`reads_as_structure`/`NON_STRUCTURAL` se retiran; estructura se vuelve una
suite más del registro (la más rica, no la default).

### S2 · Índice de prefabricados (primitivo central)

Una pasada por **definición de bloque**: nombre, firma geométrica, atributos
(exige las correcciones E7: INSERT anidado normalizado, ATTDEF leído, aviso
en corte de profundidad), clasificación contra los vocabularios del registro,
y la lista de instancias con transformación. **Se detecta una vez por
definición y se estampa por instancia.** Sale `prefab_index.json`; alimenta
el pre-escaneo de subida del tablero y elimina de raíz la clase de bugs de
doble conteo. Un detalle típico (castillo K-1, bajada tipo) dibujado como
bloque entra a la cadena de autoridad con rango propio.

### S3 · Conversión pareja

Sin esto las suites leen aire: `06 ELECTRICO` no convierte (READ ERROR
0x940), carpintería convierte con el contenido varado en bloques que se
tiran, los xrefs fallan en modo estándar. Workstream de primera clase:
escalera de reintentos ampliada, preservación de bloques, embed de xrefs,
y **cobertura declarada por archivo** — cuando algo no se pudo leer, la
Lectura lo dice con el tamaño de lo perdido, no con silencio.
*Aceptación: 16/16 archivos de Marina legibles o con su pérdida enunciada.*

### S4 · Sustrato generalizado

- `schedules.py`: la cadena cuadro > cota > marcador > supuesto acepta
  lectores de cuadros no estructurales (cancelería, tableros).
- Habitaciones y niveles (ya existen) se comparten: acabados por local,
  bajadas ligadas entre plantas por los niveles de las vistas.
- Los vanos que el detector de muros ya devuelve son la mitad del trabajo
  de cancelería.

### S5 · Gold por disciplina

Ninguna suite aterriza sin fixtures propios. Materia prima: los 12 planos
no estructurales de Marina (más los que los talleres suban). El flujo de
captura/recaptura existe; se extiende con etiquetas por disciplina
(corridas por diámetro, salidas por tipo, piezas de cuadro). La regla de la
casa aplica íntegra: cambio intencional de cantidades ⇒ recaptura declarada
en el commit.

## 2. Suite 1: Hidrosanitaria (hidráulica + sanitaria + pluvial)

Por qué primera: comparten vocabulario y detectores, Marina trae datos que
sí convierten, y es el dinero más grande de las instalaciones.

**Detección geométrica (no conteo):**

- **Corridas por diámetro y material**: las polilíneas de las capas del
  sistema, unidas en tramos; el diámetro/material del texto sobre la corrida
  ("Ø 1/2\"", "PVC 4\"", "CPVC"), segmentando el tramo donde el texto cambia.
  Salida: ML por (sistema, diámetro, material), por planta.
- **Bajadas/subidas ligadas entre niveles**: los símbolos `subida-bajada`
  del índice de prefabricados, casados por posición entre plantas usando los
  niveles de las vistas — la bajada pluvial deja de ser "238 m de líneas" y
  se vuelve N bajadas × altura entre niveles.
- **Muebles → salidas**: la tabla `MUEBLES` ya clasifica; cada mueble deriva
  sus salidas (desagüe, agua fría/caliente) como conceptos, no solo piezas.
- **Registros, coladeras, cisterna/tinaco, bombas**: equipos por símbolo.
- **Pendientes y especificaciones**: de las notas y cotas de la corrida.

**Riesgos propios (agrupados, con denominador):** corrida sin diámetro
legible (n de N, ML expuestos), bajada sin registro/coladera en planta baja,
mueble sin corrida que lo alcance.

**Conceptos:** familias INS-* por sistema/diámetro/material; los precios
siguen la doctrina — sin fuente no hay peso, y el mapeo del taller manda.

**Gold:** fixtures de Marina instalaciones con ML por diámetro y salidas por
tipo etiquetadas a mano una vez, protegidas para siempre.

## 3. Secuencia y cola de trabajo

Las suites 4–7 de abajo están especificadas a detalle — contrato, reglas de
reclamo entre suites, vocabulario real de Marina, estado de datos por
disciplina — en
[2026-08-28-suites-por-disciplina-design.md](2026-08-28-suites-por-disciplina-design.md);
eléctrica y carpintería/herrería quedan explícitamente detrás de S3.

1. **P1 estructural pendiente** (E5–E9 + fragmentación de ejes) — corto, ya
   diagnosticado, no bloquea el espine.
2. **Espine S1–S5** (registro, prefab index, conversión, sustrato, gold
   multidisciplina) — el plan grande siguiente.
3. **Suite hidrosanitaria** (§2).
4. **Cancelería** (cuadro + vanos existentes — prueba visible del modelo).
5. **Eléctrica** (tableros y circuitos; depende de conversión S3).
6. Gas / AA / CCTV (mayormente índice de prefabricados + corridas por spec).
7. Acabados / albañilería profunda (áreas por local con rooms).
8. Obras pesadas: entran por el mismo registro cuando haya planos reales
   con qué construir su gold.

**En paralelo, sin cambios:** la pista de interfaz (tablero de nodos, visor,
pre-escaneo) — es agnóstica a la disciplina; su nodo «Planos» empieza a
mostrar el estado de lectura por disciplina cuando el registro exista.

## 4. Aceptación global (por suite, sin excepciones)

- Gold propio en verde, capturado de planos reales.
- Cero silencios: lo no leído se enuncia con su tamaño (capas, bloques,
  archivos, hojas).
- Riesgos agrupados por causa, con denominador y exposición física.
- La Lectura muestra cobertura por disciplina: qué reclamó cada suite, qué
  cayó a levantamiento, qué no se pudo leer.
- Nada de este trabajo re-rompe el gold estructural.
