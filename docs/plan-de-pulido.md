# Plan de pulido — de "funciona en mi máquina" a herramienta que una firma paga

Fecha: 2026-08-23. Fuente: tres auditorías de código (web, API/motor, detección/costeo) más un recorrido página por página del producto con los proyectos Marina Lote 04. Cada punto cita archivo:línea. Prioridad: **P0** = números incorrectos o bloqueo del piloto; **P1** = el piloto se queja; **P2** = pulido.

La regla del orden: primero lo que hace que los **números mientan**, luego lo que hace que **un usuario real no pueda usarlo**, luego lo que falta para **vender y operar**, y al final el pulido.

---

## 0. Resumen ejecutivo

| Bloque | P0 | P1 | Qué cambia para la firma |
|---|---|---|---|
| A. Números que mienten | 13 | 9 | El presupuesto deja de duplicar acero y cimbra (~30 % del concreto), de inflar castillos en hojas sin marcos, de cobrar pretiles a 2.7 m, de omitir pilotes |
| B. Seguridad y tenencia | 4 | 7 | Un taller no ve ni edita el catálogo de otro; nadie toma una cuenta por Google; los correos no se filtran por SSE |
| C. Cobertura de elementos | 4 | 11 | Escaleras, zapatas corridas, vanos, pretiles, cimentación en un solo archivo |
| D. Producto usable | 6 | 22 | Nombre del proyecto en vez del id, enlaces que llevan al plano, revisión con miles de filas, errores visibles |
| E. Operación y venta | 3 | 6 | Docker, respaldos, retención, observabilidad, un catálogo por workspace |
| F. Evaluación | 1 | 4 | Pruebas de dinero, no solo de F1; un gold set con verdad humana |

---

## A. Números que mienten (motor y costeo)

### A1 — Acero y cimbra cobrados dos veces · **P0** · **hecho** (migración v13; Marina estructural $5.31M → $3.82M de costo directo; plantilla como `CIM-003` derivada del área de zapatas)
Las matrices de los conceptos de concreto traen acero y cimbra adentro (`EST-001`: `MAT-ACERO 0.160 t/m³`, `MAT-CIMBRA 9.00 m²/m³` — `costing/insumos.py:299-300`; `EST-002` `:342-343`; `CIM-002`, `CIM-008`, `EST-003`, `EST-014` igual), y además `apply_steel`/`apply_formwork` agregan `ACE-001…006`, `EST-008…011`, `CIM-006/009` con sus propias matrices (`costing/steel.py:400`, `costing/formwork.py:279`). En Marina, ~32 % del P.U. de `EST-001` ($13,386/m³) es acero y cimbra que `ACE-001` y `EST-008` vuelven a cobrar. Los indicadores no lo ven porque solo miran las líneas ACE/cimbra.
- **Fix**: migración v13 que retira `MAT-ACERO`, `MAT-CIMBRA`, `MAT-PLANTILLA` de las matrices de concreto (en `insumos.py` y en `catalog.db`), descripciones sin "incluye acero y cimbra", y una prueba que asegure que ningún concepto de concreto lleve acero/cimbra en su matriz cuando existen los conceptos derivados. Recalibrar el invariante del demo.

### A2 — Acero de columnas con la altura total del edificio · **P0** · **hecho** (altura de entrepiso por planta, como la cimbra)
`costing/steel.py:161` usa `segmentation.total_height()` para cada columna de cada planta: en 3 niveles, 3× el acero. `formwork.py` ya lo hace bien por planta (arreglado ayer); `steel.py` no.
- **Fix**: misma lógica que cimbra (`story_heights` por `assignment`), prueba en `test_story_heights.py`.

### A3 — Secciones declaradas ignoradas en hojas sin marcos · **P0** · **hecho** (`_column_volume` también en el camino plano)
`EST-001` es `COUNT × column_section_m2 × column_height_m` en el camino plano (`boq.py:87,468`); `_column_volume` (la única que lee `section_cm`, marcador y `castillo_section_m2`) solo corre dentro de `ViewScope.COLUMN_VOLUME` en hojas segmentadas. En una casa de una planta o en un archivo sin marcos, cada castillo K vale 0.09 m² (3× su concreto) y el cuadro leído se descarta; la nota "si no hay marcador" se imprime igual.
- **Fix**: usar `_column_volume` también en el camino plano; `supersedes` en ambos; prueba con segmentación `None`.

### A4 — Vanos nunca descontados (y puertas sobre-descontadas) · **P0** · **hecho** (el muro sigue sobre la puerta y guarda el vano; descuento medido ancho × 2.10 m × caras, o `opening_share_pct` supuesto y declarado en la línea; pendiente: vanos desde bloques/cancelería cuando el muro no se dibuja partido)
Aplanado, pintura y muro son `longitud × altura × caras` (`catalog.py:363-402, 328-345`). Puertas: el detector de muros parte el tramo en cada hueco > 2×espesor (`wall_detector.py:112`) y elimina toda la altura del muro sobre la puerta (incluido el cerramiento). Ventanas: nada. Vanos en vivienda = 15–25 % de la cara.
- **Fix**: (1) `QuantityRule.opening_deduction_pct` por concepto, editable, escrito en la línea ("vanos −18 % supuesto"); (2) detector de vanos desde bloques de puerta/ventana y cancelería del levantamiento (`inventory` tags V-n/P-n) que reemplace el supuesto con medida; (3) los muros no se cortan en puertas: el hueco queda como vano con altura de dintel.

### A5 — Topes de plausibilidad que sustituyen en silencio · **P0** · **hecho** (columna 2.0 m², lado 400 cm; la sección rechazada se escribe en la línea)
`MAX_COLUMN_SECTION_M2 = 1.00` (`boq.py:38-40`), `max_m2 = 0.25` para castillos (`:181`), lado ≤ 150 cm en cuadros (`schedules.py:50`). Una columna 1.2×1.2 o una zapata 200×200 se vuelve el default sin aviso.
- **Fix**: subir topes a valores de edificación (columna 2.0 m², zapata 400 cm) y, cuando se rechace, advertencia con el valor leído.

### A6 — Unidades desconocidas → presupuesto completo a factor 1.0 · **P0** · **hecho** (sin unidad confiable: cantidades en unidades de dibujo, todas las líneas sin precio, SIN UNIDADES en cada hoja del XLSX; umbrales de detección por extensión del dibujo; el demo deja de valer $105 M)
`boq.py:409-415` advierte y sigue; `suite.py:57-60` deja los umbrales genéricos (centímetros) cuando `to_meters()` es `None` (confianza < 0.7). El demo enviado muestra `PRE-001 = 120,000 m²`. La web sí bloquea el dinero (`MoneyGate`) pero el XLSX no.
- **Fix**: sin unidades confiables, el motor produce cantidades en "unidades de dibujo" sin precio, el export lleva SIN UNIDADES en cada hoja, y los umbrales caen a un preset por extensión del dibujo.

### A7 — `"MC"` reclasifica muros de block como concreto · **P0** · **hecho** (`layer_matches` por tokens: ≤ 3 letras = token completo, ≥ 4 = inicio de token; prueba con capas trampa)
`wall_detector.py:48-50` usa subcadenas; cualquier capa con `MC` (p. ej. `A-MCOBILIARIO`) manda el muro a `EST-014` en m³.
- **Fix**: hints como palabras completas (`\bMC\b`, `MURO CONC`), y una prueba con capas trampa. Revisar `"PILA"` (`footing_detector.py:42`), `"BORDE"` (`slab_detector.py:27`), `"ARQ"` (`rooms.py:62`).

### A8 — Alias / P.U. adoptado sin validar la unidad · **P0** · **hecho** (422 `unit_mismatch` en alias, P.U. e insumo; `force` solo con nota; el selector ofrece "Usar de todos modos" con la razón)
`adopt_concept_reference` y `set_concept_alias` (`catalog_store.py:594-616, ~890`) no comparan `reference.unit` con `concept.unit`. Adoptar `$/m` en un concepto `M3` multiplica sin aviso. El matcher sí filtra por unidad; la adopción no.
- **Fix**: rechazar con 422 `unit_mismatch` salvo `force=true` con nota; mostrar la unidad en el selector.

### A9 — Pilotes contados y tirados · **P0** · **hecho** (longitud por notas/cuadro/IA → `CIM-011` en M con matriz; sin longitud, `CIM-010` visible **sin precio** en presupuesto y XLSX; `BoqLine.unpriced`)
`CIM-010` tiene regla pero no matriz (`insumos.py:271`, `catalog_store.py:891-909`): se cuentan, se advierte y no suman. En una cimentación con pilotes es la partida más grande.
- **Fix**: leer longitud de pilote (cuadro/nota/IA — `length_m` ya se lee y se descarta), concepto en `M` con matriz de referencia, y mientras no haya longitud, línea sin precio **visible** en el presupuesto (no solo advertencia).

### A10 — `_calibrate_assumptions` sobreescribe la sección de columna con el `NxM` más frecuente de todo el texto · **P0** · **hecho** (solo secciones ligadas a marcas de columna, ≥ 2)
`report.py:54-61`, `dimensions.py:198-202`. En una hoja con cuadro de zapatas el "típico" puede ser 150x150.
- **Fix**: calibrar solo con secciones ligadas a marcas de columna (ya existe `section_cm` por detección); quitar la calibración global.

### A11 — Pretiles y muretes de azotea a 2.7 m · **P0** · **hecho** (`parapet_height_m` 0.90 editable; muros de la planta de azotea marcados `on_roof` y costeados como pretil con o sin niveles)
`catalog.py:340`: un muro en la planta de azotea se cobra con `wall_height_m`. Un pretil de 0.9 m vale 3×.
- **Fix**: altura por planta ya existe; para la planta de azotea usar `parapet_height_m` (0.9 default, editable) y etiquetar `wall_kind = pretil` cuando el muro vive en la azotea.

### A12 — Locales omitidos si no hay 2 nombres interiores distintos · **P0 en comercial** · **hecho** (un nombre repetido en ≥ 3 etiquetas — OFICINA 101/102/103 — basta)
`rooms.py:212`: una planta `OFICINA 101/102/103` tiene un solo nombre → cero locales, cero acabados.
- **Fix**: contar nombres distintos normalizando números; aceptar 1 nombre si hay ≥ 3 caras nombradas.

### A13 — Zapatas corridas fuera de `max_area`; cuadro de zapatas ilegible · **P0** · **hecho** (franjas ≤ 1.5 m de ancho y ≥ 4× de largo son `footing_kind=corrida` con su largo real; marcas Z-n/ZC-n ligadas a la zapata → el cuadro nombra tamaño y armado; topes de cuadro a 400 cm; cimbra/plantilla usan cota > franja > cuadro > lado equivalente)
`footing_detector.py:93-95` + `suite.py:78` (≤ 5.5 m²); `schedules._parse_section` tope 150 cm. Una zapata corrida 0.6×18 m desaparece; `200x200` no parsea; las zapatas se etiquetan `F1…Fn`, nunca `Z-1`, así que el cuadro no se les puede unir.
- **Fix**: familia `zapata_corrida` (rectángulo largo en capa de cimentación, m³ = ancho × peralte × largo), marcas `Z-n/ZC-n` ligadas a la zapata más cercana, topes de cuadro 400 cm.

### A14–A22 — P1 de costeo
- **Retención nunca se devuelve** en el flujo; falta el finiquito (`financial.py:29-52`).
- **Total de licitación ≠ total del motor**: el export omite contingencia y redondea por línea (`exports.py:185-186`, `integration.py:43-49`). Decidir una sola definición de "total" y que ambos la digan.
- **IVA fijo 16 %** (`exports.py:122`): parámetro del taller con 8 % franja fronteriza y obra exenta.
- **Abundamiento** aplicado a la excavación en banco (`catalog.py:95`) en vez del acarreo; **despalme** en m² sin acarreo del material (0.20 m × área).
- **Financiamiento** es un % constante, nunca se reconcilia con el flujo que lo justificaría (`report.py:220-227`).
- **`SteelAssumptions`** (recubrimiento, ganchos, anclaje, desperdicio, armado default) no editables (`steel.py:41-51`); **desperdicios** de concreto (1.05) y block fijos dentro de las matrices.
- **Acero no leído**: bastones, zonas de estribos variables, segundo lecho en trabes, dimensiones de zapata del cuadro (todas se asumen cuadradas), longitud de pilote; trabes sin armado se omiten en silencio.
- **Cimbra**: sin obra falsa, sin aparente/común, zapata con peralte completo; losa reticular cobra `EST-011` y además la matriz de `EST-003` trae cimbra.
- **`dala_section_m2`** es configuración muerta (`models.py:254`); `despalme_thickness_m` no mueve cantidad.
- **Texto**: el bbox aproximado ignora rotación y alineación (`normalizer.py:134-136`); todos los radios de asociación miden desde un punto desplazado.

---

## B. Seguridad y tenencia

| # | Hallazgo | Dónde | Fix |
|---|---|---|---|
| B1 **P0** · **hecho** | Google sign-in liga una cuenta existente por `email` sin comprobar `email_verified`, `iss`, `aud` → toma de cuenta | `apps/api/auth/routes.py:273-286` | exigir `email_verified is True`, validar `iss/aud`, no ligar automáticamente: pedir contraseña o enlace de confirmación |
| B2 **P0** · **hecho** (un `catalogs/<workspace>.db` por taller resuelto en `get_catalog`/`store_for_project`; defaults por taller; el workspace por defecto adopta `catalog.db`; eventos `catalog_updated` por taller; escrituras siguen abiertas a miembros activos del taller — su propio catálogo) | Todo `/catalog` (≈40 rutas, incl. importaciones y roll-forward) es escribible por cualquier miembro activo de cualquier workspace; `catalog.db` es global: insumos, conceptos, fuentes, alias, plantillas, reglas, índices, mapeos, `taller_defaults.json` | `auth/middleware.py:139-157`, `catalog_store.py:32-157`, `defaults.py:19-28` | `workspace_id` en cada tabla (o un `catalog.db` por workspace resuelto en `get_catalog`), roles admin/editor para escrituras, migración que asigne lo existente al workspace por defecto |
| B3 **P0** · **hecho** | El bus publica eventos globales con correos (`user_pending`, `user_joined`) a todo suscriptor; `/events` global expone nombres de proyecto de otros workspaces | `events.py:107-119`, `auth/routes.py:136,307`, `routes/events.py:182-223` | eventos con `workspace_id`; `since()` filtra por workspace; nada de PII en `data` |
| B4 **P0** | Tokens de recuperación/invitación en claro en `data/outbox/*.json`, para siempre (ruta por defecto sin SMTP) | `mail.py:157-177` | cifrar o no persistir el cuerpo; TTL; solo admin lee el outbox |
| B5 P1 · **hecho** | `X-Actor` se confía para atribución con sesión válida | `reviews.py`, `versions.py`, `catalog.py`, `projects.py:210` | actor = usuario de sesión; `X-Actor` solo en modo abierto |
| B6 P1 · **hecho** | `load_version` valida prefijo, no contención de ruta | `versions.py:100-104` | `resolve().relative_to()` como en `dependencies.py:152` |
| B7 P1 | Importaciones leen todo el cuerpo antes de medir; sin tope de número de archivos | `catalog.py:322-327,465,500,734`, `projects.py:216-236` | streaming con límite; tope de archivos por proyecto |
| B8 P1 | CORS `localhost:*` con credenciales en producción | `main.py:46-57`, `middleware.py:27,42` | orígenes solo por configuración; sin regex localhost fuera de dev |
| B9 P1 · **hecho** (límites por usuario — o IP sin sesión — en upload/process/ai-read/matches/exports, además de los de auth) | Sin rate limit en upload, process, ai-read, matches, exports | `auth/common.py:19-42` | límites por usuario/IP; presupuesto de tokens por workspace para IA |
| B10 P1 | Correos en logs | `mail.py:115-121`, `auth/store.py:374,674,803` | redacción |
| B11 P2 | `/docs`, `/openapi.json` sin auth; oráculo de existencia de rutas en `projects.py:192-198`; cookie `secure` derivada de `web_origin` | | proteger docs fuera de dev; un solo error genérico; `KLAVE_COOKIE_SECURE` explícito |

---

## C. Cobertura de elementos (lo que el plano tiene y nadie lee)

| Elemento | Estado | Prioridad | Camino |
|---|---|---|---|
| Escaleras y rampas | **hecho** (`DetectionType.stair`: texto ESCALERA/RAMPA sobre su patrón de huellas → ancho, paso, tramo; EST-015 en M2 de losa inclinada × 1.15 con matriz completa; el texto solo, advierte) | **P0** | `DetectionType.stair` desde `ESCALERA` + huellas (líneas paralelas equidistantes) → losa inclinada m² + escalones; concepto EST-015 |
| Vanos (puertas, ventanas, cancelería) | no existe | **P0** | ver A4 |
| Zapatas corridas / mampostería | rechazadas por área | **P0** | ver A13 |
| Pretiles / parapetos | cobrados como muro completo | **P0** | ver A11 |
| Muros de contención / sótano | `max_thickness 0.45` los descarta | P1 | `wall_kind = contencion` (≥ 0.3 m en capa MC/CONT), m³ con acero de cuadro |
| Estructura metálica (IPR/IPS/OR, placas, anclas) | sin regex ni kg de perfil | P1 | marcas `IPR-n/VM-n`, tabla de pesos de perfil (kg/m), concepto en kg/ton |
| Castillos ahogados / armex | `EST-006` sin regla | P1 | uno por vértice y cada N m de muro de block (parámetro del taller) |
| Dalas de desplante / cadenas de cimentación | `EST-005` solo superestructura | P1 | `D-n/CD-n` en planta de cimentación → concepto cimentación |
| Firmes, banquetas, pavimentos, plataformas | solo dentro de locales nombrados | P1 | áreas en capas `FIRME/PAV/BANQUETA` del levantamiento → `EST-007`/`PIS-002` |
| Impermeabilización y pendientes de azotea | nada | P1 | azotea = tableros de la última planta → `IMP-001` m²; pendientes desde NPT |
| Cisternas, registros, pozos | solo por mapeo manual de bloques | P1 | mapeos sugeridos por nombre de bloque (`CISTERNA`, `REGISTRO`) |
| Longitud de pilotes | leída por IA y descartada | P1 | ver A9 |
| Geometría curva (ARC/CIRCLE) | sin `points` → invisible para polígonos | P1 | aplanar arcos/círculos a polilíneas en el normalizador |
| Paper space / viewports | nunca cuantificado | P1 | aplicar `scale_factor` del viewport o rechazar con aviso claro |
| Varias disciplinas en un archivo | gating por nombre de archivo | P1 | gating por hoja (marco) además de por archivo |
| `CIM-003/004/005` (plantilla, relleno, acarreo) | **hecho** (plantilla = área de zapatas + margen; relleno = excavación banco − enterrado; acarreo = banco × abundamiento; excavación ya sin abundamiento — parte de A14) | P1 | derivar de zapatas (plantilla = área), excavación − cimentación (relleno), excavación × abundamiento (acarreo) |

---

## D. Producto usable (web)

### D1 — Bugs que un piloto encuentra el primer día · **P0**
1. Todas las pantallas del proyecto muestran el **id** en vez del nombre (`proyecto/[id]/layout.tsx:82` pasa `name={undefined}`).
2. Enlaces "verlos en el plano" / "plano" apuntan a `?concept=` y **nada lo lee** (`presupuesto:570`, `revision:378`; cero `useSearchParams`): el rastro cantidad → plano está roto.
3. Proyecto `created`/`unknown` (subido, nunca encolado) → "Procesando tu plano…" infinito sin botón de procesar (`layout.tsx:26`); fallo de `getStatus` → mismo spinner para siempre.
4. `plano`: `getGeometry` sin `.catch` → esqueleto eterno y rechazo sin manejar (`plano:66,76`).
5. `parametros`: el error de carga es inalcanzable detrás del esqueleto (`parametros:92/258`); `configuracion` igual.
6. `revision`: renderiza todas las filas (miles) y "seleccionar todo" supera el tope de 2,000 claves del API → 422 genérico (`revision:129`, `reviews.py:54`).
7. El estado "SIN VERIFICAR" del dinero está diseñado y **nunca se renderiza** (`MoneyGate.tsx:8-26`); el XLSX sí lo marca, la web no.
8. `API_BASE` cae a `localhost:8000` sin aviso en producción (`lib/api.ts:4`).

### D2 — Lo que el ingeniero de costos reclamará · **P1**
- **Revisión**: sin ordenar por columna, sin "excluidos" en las métricas, sin atajos de teclado, sin virtualización.
- **Presupuesto**: cabecera "Catálogo de conceptos" (confunde con el catálogo), sin búsqueda/orden/filtro, CSV mal escapado, exports por `window.location` sin estado de carga (un error reemplaza la app por JSON), notas obligatorias en un sitio y opcionales en otro, sugerencias de alias para conceptos que no están en este presupuesto, callout roto en móvil.
- **Plano**: sin touch (no se puede usar en tableta), dos paneles llamados "Hojas", 14/143 capas visibles sin aviso, sin zoom por botones; **336 "Castillos"** incluyen las 137 etiquetas de cuadro (filtrar `role=cuadro`).
- **Lectura**: "Hojas 1" cuenta archivos, no los 22 marcos; asignación de mapeos sin estado ocupado (doble clic = mapeo doble); dropdown de conceptos filtra por unidad con igualdad estricta (`m²` desaparece).
- **Riesgos**: 407 "columna sin eje cercano" porque la malla leyó 6 ejes → regla muda cuando la malla es pobre; agrupar repetidos; ruta del archivo en vez de nombre de hoja; sin "visto/aceptado"; `bbox` y `related_detections` llegan y no se usan (sin salto al plano).
- **Programa**: sin fecha de inicio ni calendario; sin export; rendimientos bajos (cimbra contratrabes 12 m²/día → 49 días); secuencia sin predecesores.
- **Flujo**: sin export, tablas sin totales, sin finiquito.
- **Parámetros/Taller**: llaves crudas (`castillo_section_m2`, `slab_thickness_m`…), sin unidades ni ayuda; grupo `schedule` no editable por proyecto; "Restablecer" sin confirmación; tabla de insumos completa sin búsqueda.
- **Catálogo**: seis secciones apiladas sin tabs; insumos y matrices sin búsqueda; primer APU auto-expandido; vigencia muestra conteos pero no cuáles; sin página de alias.
- **Consistencia**: cuatro órdenes de fases y colores por posición; dinero con 0 o 2 decimales según la página; confianza con cinco presentaciones; dos `timeAgo`; borrados sin confirmación (versiones, plantillas, reglas, ajustes, mapeos) mientras restaurar sí confirma.
- **Capacidades del API sin UI**: diff entre dos versiones, crear regla paramétrica a mano, lista/revocación de alias, descripción LOPSRM (ni siquiera tiene cliente), roll-forward por códigos/mes, croquis por planta, exports de APUs/programa/flujo/revisión/riesgos.

### D3 — Onboarding · **P1** · **hecho en lo esencial** (obra de ejemplo procesada al instante desde la pantalla vacía; regla de ingestión antes de subir; `/glosario` enlazado; `docs/primeros-pasos.md`)
- Sin datos de muestra: una firma no ve un presupuesto terminado sin subir un DWG y esperar.
- El catálogo y el taller nunca se presentan; los no-admin no descubren `/taller`.
- Identidad aleatoria ("Carla") cuando `localStorage` falla; `cuenta` redirige fuera en modo abierto.
- Glosario inexistente (FSR, Ps, Tp, Tl, %MO, LOPSRM, u.dib).
- Regla de ingestión invisible hasta después de subir: decir **antes** qué archivos abre (DXF siempre; DWG según LibreDWG) y ofrecer "exporta a DXF desde AutoCAD".

---

## E. Operación y venta

| # | Hallazgo | Fix |
|---|---|---|
| E1 **P0** · **hecho** (Dockerfiles api/web, compose de producción con Caddy TLS, healthchecks, `KLAVE_ENV=production` valida al arrancar) | Sin `Dockerfile`, sin compose de producción, API con `uvicorn --reload`, web con `npm run dev` | Dockerfile api + web, compose con Postgres, nginx/Caddy con TLS, healthchecks, un VPS o Fly/Render; `KLAVE_ENV` que valide configuración al arrancar |
| E2 **P0** · **hecho** (servicio `backup` nocturno: pg_dump + tar de /data, retención N días, restauración probada) | Sin respaldo de `catalog.db` ni `data/uploads` (lo irreemplazable); solo `pg_dump` de cuentas | job diario de respaldo + restauración probada |
| E3 **P0** · **hecho** (poda tras cada publicación: corridas activa+N, croquis por corrida, jobs; `DELETE ?purge=true` borra de verdad con confirmación y contención) | Sin retención: 4 GB en 5 proyectos de prueba (`runs/`, `jobs/`, `versions/`, `croquis/`, `renders/`, `outbox/`); `DELETE /projects` no borra nada | conservar N corridas/M días, borrar croquis/renders de corridas viejas, borrado real con confirmación, política escrita |
| E4 P1 · **hecho** (enqueue decide bajo el lock; reparación de huérfanos al arrancar; SQLite WAL y conexiones que cierran) | Locks y cola de trabajos en proceso; `enqueue` con TOCTOU; trabajos huérfanos tras crash; SQLite sin WAL y sin cierre explícito; escrituras sin lock | `get` dentro del lock; reparación al arrancar; `journal_mode=WAL` + `closing`; assert de un solo worker; a mediano plazo cola persistente (RQ/arq) |
| E5 P1 · **hecho** (request id en cada línea de log `rid=…`, eco `X-Request-Id`, duración por petición; Sentry queda opcional para después) | Sin observabilidad: logs de texto, sin request id, sin métricas, sin error tracking | logging JSON + request id, Sentry/OpenTelemetry, duración de pipeline y endpoints |
| E6 P1 | Rendimiento: `read_artifact` reparsea 6 MB por petición; `/geometry` sin paginar; `/catalog/matches` reconstruye candidatos y APUs por llamada; croquis renderiza por línea dentro de la petición; renders en caché sobreviven el reproceso | caché por mtime; geometría por hoja/viewport; memoizar candidatos; croquis en job; renders por corrida |
| E7 P1 | Migraciones a mano en el constructor (v2→v13) y en strings de Postgres sin tabla de versión | Alembic para Postgres; tabla `schema_migrations` y migraciones como funciones nombradas para SQLite |
| E8 P1 | Docs: README con `apps/dashboard`/Streamlit/ODA inexistentes y 10 de ~90 rutas; `CPU_MVP_ARCHITECTURE.md` niega la auth y el recompute; `DATA_CONTRACTS.md` sin `views/frames/schedules/inventory/ai_reads/run_diff/engine.json`; `DETECTION_RULES.md` con umbrales viejos | reescribir los cuatro; una página por característica (cola, SSE, versiones, croquis, correcciones, workspaces) |
| E9 P1 | Huella del motor hashea todo `costing/` (exports incluidos): cada commit marca todos los proyectos como "lectura anterior" | huella solo de lo que cambia cantidades (dxf, detection, pipeline, boq/steel/formwork/catalog), y "precio/export" aparte |
| E10 P2 | Código: cuatro parsers de encabezados (`custom/matrices/presupuesto/compare` + `_rows_from_xlsx`) con reglas de coma decimal distintas; imports privados entre módulos; `run_full_pipeline` 314 líneas, `detect_slab_panels` 289, `build_default_catalog` 281, `compute_steel` 251, `generate_risk_report` 242 | `costing/sources/tabular.py` único; API pública de `custom.py`; partir las cinco funciones |
| E11 | Comercial: términos, aviso de privacidad (LFPDPPP), disclaimer de precios de referencia en forma contractual, planes y cobro (Stripe/Conekta), medición de uso | después del piloto |

---

## F. Evaluación (cómo sabremos que los números son buenos)

| # | Hallazgo | Fix |
|---|---|---|
| F1 **P0** · **hecho** | Ninguna prueba compara cantidad, precio ni total: A1–A13 pasan `eval-gold` y `eval-demo` | **eval de dinero**: por proyecto gold, tabla esperada de `concept_code → cantidad ± tolerancia` y `direct_cost`, capturada con `--fresh` y editada a mano donde haya verdad |
| F2 P1 | El gold set son 3 dibujos, todos `baseline` (confirmed/excluded vacíos): solo prueba que el motor no cambió; dos apuntan a rutas locales | promover Marina y PRUEBA-1 a `partial` con las revisiones humanas; fixtures portables (copiar DXF mínimos a `evals/fixtures`) |
| F3 P1 · **hecho** (tres pasadas: clave/alias del taller, matcher por descripción con % visible, huérfanos; unidades normalizadas y desacuerdos marcados; totales de importe) | `compare.py` empareja solo por clave exacta; contra un OPUS real todo cae en "solo humano" | usar alias + matcher para emparejar; normalizar unidades; comparar importes y totales por partida |
| F4 P1 | Sin pruebas HTTP para `catalog.py` (40 rutas), `reviews.py`, `versions.py`, `croquis.py`, `exports.py`, `events.py`, `jobs.py`; módulos del motor sin prueba (`risks/rules.py`, `dxf/normalizer.py`, `schedule.py`, `financial.py`, `integration.py`…) | contratos HTTP con `TestClient` por módulo; pruebas de normalizador con DXF sintéticos |
| F5 P1 | La lectura IA no tiene eval (solo stub); campos leídos (`desplante`, `cover`, `fy`, `slab_system`, `length_m`) se descartan; sin comparación regla-vs-IA | correr en vivo sobre Marina con llave, medir acierto por campo, consumir los campos útiles, mostrar desacuerdos |

---

## G. Orden de ejecución propuesto

**Semana 1 — que los números no mientan y nadie se meta donde no debe**
1. A1 doble cobro de acero/cimbra (migración v13 + pruebas + invariante del demo).
2. A2 acero por planta; A3 `_column_volume` en el camino plano; A10 calibración; A5 topes con aviso.
3. A7 hints por palabra completa; A8 unidad en alias/adopción; A9 pilotes visibles.
4. B1 Google `email_verified`; B3 eventos por workspace; B6 contención de ruta; B5 actor de sesión.
5. F1 eval de dinero sobre Marina + PRUEBA-1 (sin esto, lo anterior no se puede proteger).

**Semana 2 — que un usuario real lo use**
6. D1 completo (nombre, deep link `?concept=`, estados de error, revisión paginada/virtualizada y por lotes de 500, SIN VERIFICAR en web, `API_BASE`).
7. A4 vanos: descuento paramétrico disclosed + detector desde bloques/cancelería; A11 pretiles; A12 locales comerciales.
8. Riesgos: reglas mudas con malla pobre, agrupación, salto al plano; visor: cuadro vs castillos, capas, touch.
9. Parámetros/Taller con etiquetas, unidades y ayuda; `schedule` por proyecto; fecha de inicio y calendario del programa.

**Semana 3 — tenencia, operación, deploy**
10. B2 catálogo por workspace con roles (migración de datos existentes).
11. E1 Docker + compose + TLS; E2 respaldos; E3 retención; E4 cola robusta; E5 logs/errores; E9 huella acotada.
12. B4/B7/B8/B9/B10.

**Semana 4 — cobertura y entregables**
13. C: escaleras, zapatas corridas, castillos ahogados, dalas de desplante, firmes/banquetas, impermeabilización, contención; `CIM-003/004/005`.
14. A14–A22: flujo con finiquito, IVA configurable, un solo total, abundamiento en acarreo, `SteelAssumptions` editables, acero de trabes de dos lechos.
15. D2/D3 restante: exports de APUs/programa/flujo/revisión, alias/reglas a mano, diff entre versiones, datos de muestra, glosario, onboarding de ingestión.
16. F2–F5; E8 docs; E10 refactors.

**Después del piloto**: E11 comercial, IA en vivo con eval, estimaciones (avance de obra), cola persistente.

---

## H. Qué no cambia

- La regla de provenance: ningún número sin fuente, ningún precio inventado, la IA propone y no cuantifica.
- Lo que ya se verificó en Marina y PRUEBA-1 (alturas por planta, cuadros de castillos, tableros, contratrabes, cimbra por planta, alias, paramétricos, indicadores) se protege con la eval de dinero antes de tocar el motor otra vez.
