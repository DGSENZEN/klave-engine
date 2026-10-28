# Interfaz de Klave — las 30 pantallas en `main` (064f3ba)

## Veredicto de patrones dañinos

**Problemas significativos.** Ningún patrón engañoso, de urgencia fabricada ni de enganche. Sí hay defaults destructivos y fallas que no se ven:

- **Destructive Defaults (alta):** asentar una nota de bitácora (irreversible por ley) con un clic; la tecla X excluye un elemento del presupuesto desde cualquier punto de la página, sin motivo y sin deshacer; quitar un ajuste firmado con un clic; reemplazar el catálogo firmado del contrato sin confirmar.
- **Missing Feedback / Broken Error Recovery (alta):** una carga fallida deja datos en blanco que el siguiente guardado escribe encima del servidor (conteos, costo horario); «Revocar» la liga compartida dice que se revocó aunque la liga siga viva.
- **Dead Ends (media):** no existe forma de capturar la primera estimación.
- **Jargon Overload / Inconsistent Patterns (media):** códigos internos en el paso que libera el dinero; el mismo gesto con tres o cuatro nombres y tres o cuatro formas.

## Problemas prioritarios

### Críticos

**C1. Un fallo al cargar los conteos y el siguiente guardado borra los conteos de todos.**
`revision/page.tsx:918-930` pone la tabla en blanco cuando la carga falla (también en una recarga en vivo, `:777`); `:1018-1027` arma el PUT completo desde esa tabla en blanco, y `:1026` borra el aviso. El estimador captura un conteo y el servidor queda con un solo renglón; los conteos de los demás desaparecen sin que nadie lo vea.
Heurística: prevención de errores. **Cambio:** con la carga fallida, la tabla queda en solo lectura con «Reintentar»; un fallo en recarga en vivo conserva lo ya cargado; guardar envía solo el renglón cambiado, o se bloquea mientras no haya una base cargada.

**C2. El costo horario muestra valores por omisión como si fueran los guardados, y «Guardar y aplicar» los escribe encima.**
`catalogo/page.tsx:3395-3401` (`.catch(() => setParams(EQ_DEFAULTS))`), pie en `:3443-3452`. El análisis guardado del equipo y el costo del insumo se reemplazan por valores de partida.
Heurística: visibilidad del estado del sistema. **Cambio:** un fallo muestra error con reintentar y deshabilita «Guardar»; los valores de partida solo aparecen cuando el servidor dice que no hay análisis, y la pantalla lo nombra: «Sin análisis guardado: valores de partida».

**C3. Estimaciones no se pueden empezar.**
El único botón llama a «siguiente» (`estimaciones/page.tsx:82-98`); el servidor responde 409 cuando no hay una anterior (`apps/api/routes/obra.py:260-268`); el estado vacío no tiene acción (`:186-192`). Todo contrato nuevo llega a «Sin estimaciones todavía» y «Nueva estimación» contesta «No hay una estimación anterior». Además cualquier otra falla (500, red) se reporta con ese mismo texto (`:90-95`), y si la lista no carga el esqueleto tapa el error para siempre (`:72-77`, `:116-130`).
Heurística: control y libertad del usuario. **Cambio:** el estado vacío lleva «Capturar la estimación 1», sembrada desde el catálogo del contrato (o manda a cargarlo si falta); «Nueva estimación» encadena solo cuando ya hay una; el texto de «primera estimación» se reserva para `sin_estimacion_previa`.

**C4. «Asentar nota» en la bitácora es permanente, sin confirmación y sin estado pendiente.**
`bitacora/page.tsx:159-170`, botón en `:305`. Un doble clic o una red lenta asientan dos notas idénticas en un registro que la misma página dice que no se edita ni se quita.
Heurística: prevención de errores. **Cambio:** `ConfirmDialog` («Asentar la nota 14 — no se podrá editar ni quitar»), botón deshabilitado con «Asentando…»; igual para la nota de apertura.

**C5. Reprocesar o cerrar un nodo desmonta la pantalla de todos los colaboradores y se pierde lo capturado.**
`proyecto/[id]/layout.tsx:107-120` y `:190-212` cambian el shell entero por «Procesando tu plano…»; `GateGuard.tsx:24-34` lo cambia por el candado. Los disparadores no piden confirmación: «Reprocesar» en Inicio (`page.tsx:787-797`), Resumen (`resumen/page.tsx:137-148`) y Visor (`plano/page.tsx:517-528`); «Cerrar nodo» en `Tablero.tsx:613-623`. Quien estaba a media captura de un finiquito, una estimación o unos parámetros pierde el trabajo.
Heurística: control y libertad del usuario. **Cambio:** reprocesar y cerrar nodo pasan por `ConfirmDialog` diciendo que afectan a todos; una pantalla abierta se queda montada con un aviso fijo («Se está reprocesando; lo que guardes se conserva»); con cambios sin guardar, aviso y oportunidad de guardar antes de bloquearse.

**C6. El detalle de un concepto en Presupuesto solo se abre con el ratón.**
`presupuesto/page.tsx:670-677` es un `<tr onClick>` sin rol, foco ni teclas; ahí viven «elegir de mi catálogo», variantes, croquis y generadores. Lo mismo en los encabezados de grupo (`:635-638`), los grupos de `VariantesSection.tsx:300` y las filas del catálogo (`catalogo/page.tsx:1977`, foco solo visual).
Heurística: flexibilidad y eficiencia de uso (WCAG 2.1.1). **Cambio:** un `<button aria-expanded aria-controls>` en la celda del concepto; la fila puede seguir respondiendo al clic.

### Mayores

**M1. El porcentaje de confianza sigue a la vista en 11 lugares.**
`ConfidenceBadge` (`ui.tsx:493-498`) en cada renglón de Presupuesto (`presupuesto/page.tsx:751`, columna «Conf.») y cada fila de Revisión (`revision/page.tsx:659`); «Confianza 87%» y el deslizador «Confianza mínima» en el Visor (`plano/page.tsx:774, 1346`); «m · confianza 90%» en Resumen (`resumen/page.tsx:305, 676`), Lectura (`lectura/page.tsx:326`) y la compuerta de unidades (`MoneyGate.tsx:120`); puntajes de coincidencia (`SuggestionsBar.tsx:94,143`, `ConceptPicker.tsx:223`); el glosario lo define en porcentaje (`glosario/page.tsx:12`); el CSV exporta decimales crudos. La métrica «Importe en lecturas firmes» marca 100 % alta y no puede bajar de 100 %. Un 87 % junto a cada renglón invita a firmar sin abrir el recorte del plano.
Heurística: correspondencia con el mundo real. **Cambio:** palabra e ícono («firme» / «dudosa» / «débil»), nunca la cifra; el deslizador pasa a «Todo · Dudosas y débiles · Solo débiles»; las sugerencias muestran sus razones; el CSV exporta la palabra; la métrica constante sale.

**M2. El plazo dice tres cosas en tres pantallas.**
Tablero: «Plazo 202 días hábiles»; Resumen: «Plazo estimado 202 días»; Programa: «Plazo contractual 235 días naturales». La LOPSRM (art. 31 fr. V) fija el plazo en días naturales.
Heurística: consistencia y estándares. **Cambio:** las tres pantallas muestran el plazo en días naturales con la misma etiqueta que Programa; los hábiles van en la pista.

**M3. Cuatro vocabularios de severidad.**
Diagnóstico usa los cuatro canales de la doctrina (bloqueante / dinero faltante / por revisar / criterios). Riesgos usa Alta/Media/Baja con 255 tarjetas en Marina Lote 04 (0 / 49 / 206), sin dinero ni denominador (`riesgos/page.tsx:22-26, 92-97`). Estructura usa Bloquea/Duda/Aviso (`EstructuraSection.tsx:56-58`). La confianza se llama firme/duda/débil, alta/en el límite/media, «baja confianza», «lectura débil» y «motor inseguro».
Heurística: consistencia y estándares. **Cambio:** los cuatro canales en Riesgos y Estructura, con repetidos agrupados como en Diagnóstico; confianza solo «firme / dudosa / débil».

**M4. Los errores de carga culpan al servidor y casi ninguno ofrece reintentar.**
«No se pudo cargar … Revisa que el servidor esté activo» en presupuesto, apus, flujo, programa, riesgos, lectura, resumen, catálogo y parámetros (p. ej. `presupuesto/page.tsx:172-178`), «¿Está activo el servidor?» en `layout.tsx:83` y `Copilot.tsx:169`. Solo Resumen trae botón. `useCostReport` y `useRiskReport` (`lib/useProjectReport.ts:20-102`) no exponen `refetch`.
Heurística: ayudar a reconocer, diagnosticar y recuperarse de errores. **Cambio:** `refetch` en los hooks y «Reintentar» en cada callout: «No pudimos cargar el presupuesto. Reintenta; si sigue, avisa a tu administrador».

**M5. Una falla se disfraza de «no hay nada» o de esqueleto eterno.**
Vacío falso en 11 lugares: Cambios («Hace falta una segunda lectura», `cambios/page.tsx:68-70`), versiones (`VersionsPanel.tsx:54-60`), omitidos (`OmittedSection.tsx:69-73`, invita a volver a agregarlos), ajustes a mano (`presupuesto/page.tsx:123,136`), invitaciones (`equipo/page.tsx:120-122`), importaciones de matrices (`catalogo/page.tsx:2610-2619`), mapeos en Lectura (`:150-158`), el selector de conceptos del ajuste medido (`plano/page.tsx:1107-1110`) y el buscador de referencias, que tampoco indica que está buscando (`ConceptPicker.tsx:49-97`, `VariantesSection.tsx:435-456`). En Bitácora, Convenios y Ajuste de costos el error sale junto a un vacío que lo contradice y el botón de crear queda vivo (`bitacora/page.tsx:310-316`: el botón no hace nada). Esqueleto que nunca termina en estimaciones, catálogo, equipo, cuenta, taller y el acceso de configuración.
Heurística: visibilidad del estado del sistema. **Cambio:** cada sección distingue «falló» de «no hay»; un estado a la vez (error > cargando > vacío > contenido); las acciones que pueden duplicar datos se pausan hasta que la lista cargue.

**M6. Presupuesto muestra una barra gris durante 26 segundos en cada carga.**
`SuggestionsBar.tsx:58-63` reserva su lugar con un esqueleto mientras espera `GET /catalog/matches?min_score=0.8`, que tarda 26.3 s con el catálogo de Marina Lote 04; mientras tanto la API atiende más lento a las demás pantallas.
Heurística: visibilidad del estado del sistema. **Cambio:** las sugerencias se calculan una vez por cambio de catálogo y se sirven de lo calculado; la barra no reserva espacio mientras no haya nada que sugerir.

**M7. Cinco pantallas sin margen de página.**
Convenios, Bitácora, Ajuste de costos, Finiquito y Medición del piloto empiezan con `<div className="space-y-6">` (`convenios/page.tsx:208`, `bitacora/page.tsx:173`, `ajuste-costos/page.tsx:286`, `finiquito/page.tsx:159`, `piloto/page.tsx:129`) y el título y las tarjetas tocan el borde de la ventana; sus pestañas hermanas sí usan `px-6 py-7 lg:px-8`.
Heurística: consistencia y estándares. **Cambio:** el mismo marco de página en las cinco.

**M8. Acciones destructivas o de autoridad sin `ConfirmDialog`.**
Eliminar un ajuste firmado con motivo (`presupuesto/page.tsx:1098-1135`); quitar un componente de matriz, además visible solo al pasar el cursor (`catalogo/page.tsx:2141`); quitar un elemento omitido (`OmittedSection.tsx:158-162`); reemplazar el catálogo firmado del contrato (`CatalogoConvocanteView.tsx:89-104`); dar el rol de Propietario (`configuracion/page.tsx:279-291`); borrar convenios y solicitudes de ajuste con un «No / Sí, quitar» en línea (`convenios/page.tsx:372-385`, `ajuste-costos/page.tsx:344-361`); quitar un mapeo que afecta a todos los proyectos del taller (`lectura/page.tsx:220-237`); «Quitar revisión» sobre cientos de filas en lote. Versiones, plantillas y alias sí confirman.
Heurística: prevención de errores. **Cambio:** `ConfirmDialog` que nombre el documento y el importe afectado, o «Deshacer» en un aviso como el de los ajustes de precio del catálogo (`catalogo/page.tsx:1004-1040`); los botones de quitar siempre visibles.

**M9. Excluir sigue reglas distintas en el Visor, y la tecla X excluye desde cualquier parte.**
Revisión exige el motivo (`revision/page.tsx:493`); el Visor lo hace opcional y la tecla X excluye del presupuesto escuchando en todo el documento (`plano/page.tsx:430-474, 820-825`), sin aviso ni deshacer. El motivo es lo que defiende el número meses después.
Heurística: consistencia y estándares. **Cambio:** motivo obligatorio también en el Visor; los atajos solo con el foco en el visor o el panel, con un interruptor para apagarlos y un aviso con «Deshacer».

**M10. Acciones que fallan en silencio o se envían dos veces.**
Confirmar/Excluir en el Inspector del Visor no dice nada si falla (`plano/page.tsx:321-335`). «Revocar» la liga quita la tarjeta aunque falle y la liga siga viva (`presupuesto/page.tsx:388-394`); «Copiar» no confirma. «Agregar» un ajuste medido sin estado pendiente: un doble clic duplica la cantidad (`plano/page.tsx:1113-1140`). Sin pendiente también: guardar convenio, guardar ajuste de costos, importar CSV y matrices del catálogo, «Compartir». Descargas de estimación y de la convocante sin manejo de error (`estimaciones/page.tsx:259-264`, `CatalogoConvocanteView.tsx:146-156`). La revisión en lote reporta un fallo total cuando solo falló un lote, y no confirma el éxito (`revision/page.tsx:233-266`); una recarga en vivo fallida reemplaza toda la pantalla de Revisión por un error y se pierde la selección (`:84-106`).
Heurística: visibilidad del estado del sistema. **Cambio:** un botón con estado pendiente en `ui.tsx` (hoy hay 21 `CircleNotch` sueltos); todo manejador pasa por pendiente → confirmación que nombra el resultado («412 confirmados») → falla con los datos intactos; una recarga en vivo fallida conserva la pantalla con un aviso discreto.

**M11. La fase de contrato no se actualiza en vivo y gana el último que guarda; ninguna pantalla avisa de cambios sin guardar.**
Estimaciones, finiquito, bitácora, convenios, ajuste de costos, contrato y convocante no escuchan eventos, aunque el servidor ya publica `estimacion_guardada`, `nota_bitacora`, `convenio_guardado`, etc.; tampoco llegan a los avisos ni a «Cambios» (`ProjectLive.tsx:295-387`). Los PUT no llevan versión. No hay `beforeunload` ni guardia de navegación en ningún formulario.
Heurística: visibilidad del estado del sistema. **Cambio:** suscribir esas pantallas a sus eventos y al reconectar; el manejo de conflicto de Parámetros (`parametros/page.tsx:146-153, 208-219`) en los PUT de contrato; aviso de cambios sin guardar al navegar o cerrar.

**M12. Códigos internos y nombres de servidor en pantalla.**
La compuerta de unidades, que libera el dinero, muestra «drawing_units · 0 % de confianza (unknown)», «(dxf_header)», «(heuristics)» (`MoneyGate.tsx:119-120`, `resumen/page.tsx:305, 676`); Lectura escribe «($INSUNITS)» y los tipos DXF en inglés («784 de SOLID, 117 de SPLINE»). Taller muestra `KLAVE_AI_BUDGET_USD` y el id crudo `marina_-_prueba_4110e291`; Equipo, `KLAVE_SMTP_HOST` / `KLAVE_RESEND_API_KEY` (`equipo/page.tsx:182-190`) y «como member», «(pending → active)» en el registro (`:762-767`). El catálogo pide colocar un archivo en `data/sources/` del servidor (`catalogo/page.tsx:2513`). Inicio muestra el estado «unknown» en inglés cuando un proyecto no se encuentra.
Heurística: correspondencia con el mundo real. **Cambio:** un helper de unidad y fuente («metros, leídos del encabezado del archivo») compartido por Lectura, Resumen y la compuerta; las variables de entorno van a una ayuda desplegable para el administrador; los estados y roles pasan por sus etiquetas; la instrucción del catálogo dice «súbelo con Importar → Publicación oficial».

**M13. El mismo concepto con varios nombres, y el mismo nombre para varios conceptos.**
- «Revisión» es el grupo de navegación, una página titulada «Revisión del presupuesto» que revisa elementos, la versión del plano («Cambios entre revisiones») y un botón «Quitar revisión».
- La pestaña «Partidas» cuenta conceptos junto a la métrica «Conceptos» con la misma cifra (`presupuesto/page.tsx:420, 451`); el glosario define concepto como «una partida».
- «Lectura» es una pantalla y un nivel de permiso (`configuracion/page.tsx:40-41`).
- Verificar / Confirmar / Validar / Aprobar / Abrir nodo; Proyecto / Obra; Exportar / Descargar / Entregar; Quitar / Eliminar / Borrar / Retirar / Descartar; liga / enlace; recurso / insumo; propietario / dueño.
Heurística: consistencia y estándares. **Cambio:** un vocabulario en `lib/` usado por todas las pantallas: Confirmar/Excluir para elementos, Verificar para los tres pasos, Concepto para la línea y Partida para el grupo (como OPUS), «Revisión de elementos», permisos «Solo ver / Puede editar / Propietario», Exportar para todo archivo de Klave, Quitar (reversible) contra Eliminar (permanente, con confirmación), enlace, insumo, propietario.

**M14. El tablero dice cosas que las pantallas desmienten.**
En Marina Lote 04: «Planos — Legibles 0 de 12» mientras Lectura muestra las 12 hojas leídas; «Contrato — En orden» con anticipo y 9 periodos aunque no hay catálogo del contrato ni estimaciones; el estado de cada hecho es solo un punto de color (`Tablero.tsx:668-681`). El botón «Lo que sigue» es el único botón cobalto de la app, hecho a mano (`Tablero.tsx:420-424`), y en oscuro su texto queda a 2.7:1. El tablero no tiene `h1`.
Heurística: visibilidad del estado del sistema. **Cambio:** cada hecho del nodo sale del mismo dato que su pantalla; «En orden» solo cuando el nodo tiene lo que necesita; ícono o palabra además del color; el CTA como `Button` primario; `h1` con el nombre del proyecto.

**M15. La verificación es una palomita, no una pregunta.**
Resumen ofrece «Unidades del plano — m · confianza 90%. Si no corresponde, corrige el archivo y vuelve a procesar» y «Marcar como verificado» (`resumen/page.tsx:675-752`); la compuerta de unidades, en cambio, deja elegir la unidad en la app (`MoneyGate.tsx:126-137`). El glosario dice que el dinero sin verificar «no se entrega» (`glosario/page.tsx:51`) cuando sale sellado SIN VERIFICAR.
Heurística: correspondencia con el mundo real. **Cambio:** cada paso como pregunta con la evidencia al lado («Leí metros. Una puerta mide 0.90 → Sí, coincide · No, son centímetros»); fuera «corrige el archivo»; el glosario dice «se entrega sellado SIN VERIFICAR en la carátula».

**M16. Pantallas repetidas o en el lugar equivocado.**
«Catálogo de la convocante» (pestaña de Presupuesto) y «Catálogo del contrato» (pestaña de Contrato) son el mismo componente con el mismo vacío y el mismo botón «Cargar catálogo de la convocante». «Medición del piloto», un instrumento interno con un resumen en texto monoespaciado, es pestaña de Presupuesto para todo usuario. Parámetros, que fija los supuestos que convierten elementos en cantidades y que la ruta de verificación llama «Supuestos de cálculo», vive bajo Programa. Taller y Parámetros muestran el mismo formulario de supuestos sin decir cuál es el valor de partida y cuál el del proyecto.
Heurística: reconocer antes que recordar. **Cambio:** un solo catálogo de la convocante con una entrada; Medición del piloto fuera de la navegación del proyecto (en Taller o detrás del rol administrador); Parámetros junto a Revisión; en Parámetros, cada valor dice si viene del taller o se cambió en este proyecto.

**M17. Teclado y foco en menús, pestañas, paleta, copiloto y plano.**
`Menu.tsx` no mueve el foco ni maneja flechas; los menús de la barra del proyecto no cierran con Escape (`ProjectShell.tsx:162-187, 295-333`); el menú de un nodo del tablero se alcanza solo cruzando todos los nodos. `Tabs` declara `role="tab"` sin flechas ni `tabpanel` (`ui.tsx:547-586`). La paleta ⌘K no es diálogo ni listbox (`CommandPalette.tsx:153-219`). El copiloto no recibe ni devuelve el foco (`Copilot.tsx:183-215`, `CopilotFab.tsx:66`). El plano no se acerca ni se mueve sin ratón (`PlanoCanvas.tsx:602-616`). El cajón de filtros del Visor en teléfono no tiene Escape ni trampa de foco (`plano/page.tsx:630-650`).
Heurística: flexibilidad y eficiencia de uso. **Cambio:** un `useMenu` y un `Tabs` con el comportamiento ARIA completo; la paleta y el copiloto con el manejo de foco de `Modal`; botones +/− y flechas en el plano.

**M18. Etiquetas y anuncios.**
46 controles solo tienen placeholder como etiqueta, incluidos entrada, registro, cuenta, equipo y el precio de cada insumo en Parámetros. Los botones de borrar de convenios y ajuste de costos no tienen nombre (`convenios/page.tsx:383`, `ajuste-costos/page.tsx:358`). Las herramientas del Visor pierden su nombre bajo `lg` (`plano/page.tsx:1018-1035`). El lienzo del plano no tiene alternativa de texto, ni siquiera en el enlace compartido con el supervisor. `Callout` no tiene rol: 40 errores y 42 resultados no se anuncian; tampoco los avisos de colaboradores ni las etapas de procesamiento.
Heurística: visibilidad del estado del sistema. **Cambio:** un `Field` con etiqueta en `ui.tsx`; `IconButton` con nombre en todo botón de ícono; `Callout` con `role="alert"` (peligro) o `role="status"`; una región viva en el layout para avisos.

**M19. Fechas ISO y unidades en dos notaciones en pantallas legales.**
«caduca el 2026-11-10» (`presupuesto/page.tsx:400`), periodos «2026-09-01 → 2026-09-30» en estimaciones, `{c.fecha}` en convenios y `{nota.fecha}` en bitácora, meses «2026-06» en vigencias. Las líneas imprimen «M3», «M2», «PZA», «HR» de la API junto a «m³» en la prosa.
Heurística: consistencia y estándares. **Cambio:** `formatDate()` («27 oct 2026») y `formatMonth()` en `lib/time.ts`; `unitLabel()` en `lib/format.ts` para toda la pantalla; las exportaciones conservan los códigos de OPUS.

**M20. El Visor abre ilegible.**
En «02-02 estructural» se encienden de entrada todas las familias con sus etiquetas (Intersecciones 558, Ejes 526, Castillos 209…): el plano queda cubierto de texto encimado.
Heurística: estética y diseño minimalista. **Cambio:** de entrada solo las familias que alimentan el presupuesto, sin intersecciones ni etiquetas de cuadro; las demás a un clic.

**M21. En teléfono, el encabezado del proyecto se come el nombre.**
A 375 px la barra del proyecto muestra «Ma…» y cinco íconos; la ruta de verificación de Resumen aprieta «Unidades / del / plano» en una columna de una palabra junto al botón; los filtros de Revisión y una fila de Parámetros se salen del ancho.
Heurística: estándares de plataforma. **Cambio:** en teléfono, los íconos secundarios pasan al menú «yo» y el nombre del proyecto ocupa la barra; las filas de verificación ponen el botón debajo del texto.

### Menores

- **Tres familias de tabla.** Solo Presupuesto y Revisión usan `TableCard`; las tablas de contrato y editores quedan insertas sin banda de encabezado y con la primera columna 36 px adentro (`estimaciones/page.tsx:202, 395`, `convenios/page.tsx:294, 396`, `CatalogoConvocanteView.tsx:231`, …); diez cajas propias con radio de 8 px sin sombra; cuatro tablas a mano con encabezados en minúsculas. **Cambio:** `TableCard` con variantes `dense` e `inset` para las 27 tablas.
- **Siete controles de filtro distintos.** Inicio, bienvenida, Visor, Riesgos (el activo es tinta sólida, parece botón primario), BaseSheet, Variantes y fichas de Atención; las tarjetas que filtran Cambios no muestran estado activo. Solo Revisión usa `aria-pressed`. **Cambio:** un `SegmentedControl` con `aria-pressed` y anillo.
- **Dos sistemas de menú y tres indicadores de navegación activa.** `Menu.tsx` contra los popovers de ProjectShell/Tablero/Paleta (radio, sombra, animación); píldora en el taller, subrayado cobalto en la barra del nodo, subrayado tinta en `Tabs`, apilados en Presupuesto, Revisión, Lectura, Parámetros y Catálogo. **Cambio:** un menú y un solo lenguaje de selección.
- **Botones secundarios de 20 a 32 px.** «Dónde se usa» y «Costo horario» en el catálogo miden ~20 px, bajo el mínimo de 24 px (`catalogo/page.tsx:704, 766`); íconos en seis tamaños; enlaces en cinco estilos. **Cambio:** `Button sm`, `IconButton` y un `InlineLink`.
- **Anchos del taller que brincan.** Inicio 4xl, Catálogo 5xl, Equipo/Cuenta/Glosario/Cómo funciona 3xl bajo un encabezado 4xl: el título se mueve al cambiar de pestaña. **Cambio:** un ancho por tipo de página, alineado con el encabezado.
- **Encabezados de sección en tres tamaños, «microlabel» en dos versiones, 64 textos de 10–11 px.** «CRÍTICA» a 10 px en Programa, la clave Klave a 10 px en `text-faint`, el motivo de una exclusión a 11 px. **Cambio:** `SectionTitle` y `.microlabel` únicos; mínimo 12 px para lo que sostiene una decisión.
- **Leyenda de cambios en hex fijo.** El Visor colorea agregado/movido/modificado/eliminado con hex que no coincide con los badges de Cambios ni cambia en oscuro (`plano/page.tsx:143, 683-686`); un violeta fuera de paleta para propuestas. **Cambio:** tokens de tipo de cambio.
- **Blanco sobre acento en oscuro a 2.7:1.** Variante `accent` de botón, avatar propio, contadores de `LiveOverlay` y del copiloto. **Cambio:** token `--accent-fg`.
- **Ruido repetido en Inicio.** «lectura anterior» en casi todos los renglones, «sin unidades / CONFIRMA LA ESCALA» en mayúsculas en cada proyecto sin unidades, «2/3 verificado» por «2 de 3 pasos». **Cambio:** una sola ficha de atención «7 leídos con versión anterior · Reprocesar»; en el renglón, la palabra en minúsculas con su acción.
- **Lectura cuenta hojas de dos maneras.** La métrica dice «Hojas 81» y la pestaña «Hojas 12»; el Tablero dice «Archivos 12». **Cambio:** «Archivos 12 · 81 presentaciones».
- **Descripciones en mayúsculas sostenidas.** Las matrices importadas de catálogos oficiales se muestran tal cual («MURO DE 15 CM. DE ESPESOR DE BLOCK…»). **Cambio:** mostrar en tipo oración; exportar el original.
- **«Cargando…» en texto** en Equipo (×2), conteos de Revisión y las tarjetas del Taller; bloques grises genéricos en las pantallas de contrato. **Cambio:** esqueletos con la forma del contenido.
- **Porcentajes, factor y totales con formatos distintos.** «73 %» y «73%» en la misma pantalla; factor con 3 o 4 decimales; costo directo sin centavos sobre renglones con centavos. **Cambio:** `pct()`, `factor()` y `money2()` únicos en `lib/format.ts`.
- **Encabezados de la tarea.** «Visor del plano», «Inspector», «El lector», «Este nodo tiene candado». **Cambio:** titular por la decisión («El presupuesto se libera cuando estén verificadas las unidades»).
- **Muros de texto.** La pista de «Importe en lecturas firmes» (332 caracteres), el párrafo de método en Programa, el pie de Resumen. **Cambio:** una línea y «Por qué →».
- **Enlaces que no dicen adónde van.** «Ir», «ver», «plano» repetidos por fila. **Cambio:** «Ir a Parámetros», «Ver K-3 en el plano».
- **Equipo y Cuenta en modo local regresan sin explicación.** Equipo vuelve a Inicio y Cuenta a la bienvenida, aunque Equipo está en la navegación. **Cambio:** en modo local, Equipo explica cómo activar cuentas y Cuenta muestra el nombre local.
- **`⌘K` solo con el glifo de Mac** en la barra del proyecto. **Cambio:** «Ctrl K» fuera de macOS.
- **Pantallas sin `h1` y saltos de nivel.** Tablero, Programa y el enlace compartido sin `h1`; `h1 → h3` en Visor y Cambios. **Cambio:** jerarquía completa.

### Cosméticos

- Cuatro opacidades de velo en diálogos, paleta, cajón del Visor y recorrido.
- Tres grosores de línea entre filas.
- «Fsr» y «FSR» en la misma pantalla del catálogo.
- Encabezados del CSV en snake_case (`p_unitario`).

## Veredictos por heurística

- **Visibilidad del estado del sistema:** rota — C1, C2, M5, M6, M10.
- **Correspondencia con el mundo real:** rota — M1, M12, M15.
- **Control y libertad del usuario:** rota — C3, C5.
- **Consistencia y estándares:** rota — M2, M3, M7, M13.
- **Prevención de errores:** rota — C4, M8, M9.
- **Reconocer antes que recordar:** rota — M16.
- **Flexibilidad y eficiencia de uso:** rota — C6, M17.
- **Estética y diseño minimalista:** rota — M20.
- **Ayudar a reconocer, diagnosticar y recuperarse de errores:** rota — M4.
- **Ayuda y documentación:** tensa — el glosario contradice al producto (M15); el recorrido guiado y «Cómo funciona» cubren la columna previa al contrato.

## Recorrido cognitivo

Tarea: del plano subido al Excel para OPUS, en Marina Lote 04.

| Paso | ¿Intenta lo correcto? | ¿Ve la acción? | ¿Entiende qué hace? | ¿Ve el avance? | Resultado | Hallazgo |
|---|---|---|---|---|---|---|
| Leer el tablero del proyecto | No: «Legibles 0 de 12» lo manda a revisar planos ya leídos | Sí | Sí | Sí | Duda | M14 |
| Confirmar las unidades | Sí | Sí | No: «m · confianza 90%» y «corrige el archivo» contra elegir la unidad en la compuerta | Sí | Duda | M15, M12 |
| Revisar dudas en el Visor | Sí | No: el plano abre cubierto de etiquetas | Sí | No: confirmar falla sin aviso | Falla | M20, M10 |
| Abrir el presupuesto | Sí | Sí | Sí | No: barra gris 26 s | Duda | M6 |
| Asignar su clave a un concepto | Sí | No con teclado: la fila no recibe foco | Sí | Sí | Duda | C6 |

Tarea: arrancar el contrato con la primera estimación.

| Paso | ¿Intenta lo correcto? | ¿Ve la acción? | ¿Entiende qué hace? | ¿Ve el avance? | Resultado | Hallazgo |
|---|---|---|---|---|---|---|
| Capturar la estimación 1 | Sí | No: el vacío no tiene acción | No: «Nueva estimación» exige una anterior | No: el error dice que falta una anterior | Falla | C3 |
| Asentar la nota de apertura | Sí | Sí | No: nada advierte que es permanente | No: sin estado pendiente | Duda | C4 |

## Lo que funciona

- Diagnóstico ya habla la doctrina: cuatro canales, el momento («antes de entregar / cotizar / contratar»), y un bloqueante detiene la exportación hasta escribir el motivo.
- `Modal` y `ConfirmDialog` manejan el foco bien (entra, se queda, vuelve; Cancelar con el foco inicial; escribir el nombre para confirmar).
- Finiquito separa error de carga y de guardado, con reintentar, «Guardando…» y «Tus cambios siguen en pantalla»: es la plantilla para la fase de contrato.
- El enlace compartido y la invitación distinguen «caducó» de «no pudimos contactar el servicio».
- La pantalla de procesamiento del proyecto: mensajes distintos para 403, 404 y 5xx, sondeo de respaldo y «Tus planos están guardados».
- Deshacer en los ajustes de precio y las importaciones del catálogo, y el manejo de conflictos de versión en Parámetros.
- Las tarjetas de Revisión filtran con anillo y `aria-pressed`; el lote de revisión ofrece la duda densa sin esconder la lista completa.
- Los tokens claro y oscuro son coherentes en todas las pantallas recorridas; ninguna pantalla se desborda a lo ancho en teléfono.
- Solo íconos Phosphor; `muted` y `faint` pasan AA en claro; se respeta `prefers-reduced-motion`.

## Acciones recomendadas

1. Un fallo al cargar los conteos y el siguiente guardado borra los conteos de todos
2. El costo horario muestra valores por omisión como si fueran los guardados
3. Estimaciones no se pueden empezar
4. «Asentar nota» en la bitácora es permanente, sin confirmación y sin estado pendiente
5. Reprocesar o cerrar un nodo desmonta la pantalla de todos los colaboradores
6. Acciones destructivas o de autoridad sin `ConfirmDialog`
7. Excluir sigue reglas distintas en el Visor, y la tecla X excluye desde cualquier parte
8. El detalle de un concepto en Presupuesto solo se abre con el ratón
9. Los errores de carga culpan al servidor y casi ninguno ofrece reintentar
10. Una falla se disfraza de «no hay nada» o de esqueleto eterno
11. Acciones que fallan en silencio o se envían dos veces
12. Presupuesto muestra una barra gris durante 26 segundos en cada carga
13. Cinco pantallas sin margen de página
14. El porcentaje de confianza sigue a la vista en 11 lugares
15. El plazo dice tres cosas en tres pantallas
16. El tablero dice cosas que las pantallas desmienten
17. La verificación es una palomita, no una pregunta
18. Códigos internos y nombres de servidor en pantalla
19. Cuatro vocabularios de severidad
20. El mismo concepto con varios nombres, y el mismo nombre para varios conceptos
21. Pantallas repetidas o en el lugar equivocado
22. La fase de contrato no se actualiza en vivo y gana el último que guarda
23. Fechas ISO y unidades en dos notaciones en pantallas legales
24. El Visor abre ilegible
25. Teclado y foco en menús, pestañas, paleta, copiloto y plano
26. Etiquetas y anuncios
27. En teléfono, el encabezado del proyecto se come el nombre
28. Tres familias de tabla
29. Siete controles de filtro distintos
30. Dos sistemas de menú y tres indicadores de navegación activa
31. Botones secundarios de 20 a 32 px
32. Blanco sobre acento en oscuro a 2.7:1
33. El resto de los menores y los cosméticos
