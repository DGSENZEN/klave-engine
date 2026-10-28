# Klave — acabado de la interfaz

## Users

- Ingenieros de costos y presupuestadores de una constructora mexicana: primero la oficina de Diego, después las oficinas invitadas al piloto.
- Llevan planos estructurales (DWG/DXF, en cm o m, a veces mal declarados) a un presupuesto que se entrega o se importa en OPUS o Neodata.
- Trabajan en escritorio, en sesiones largas y repetitivas de revisión: decenas de hojas, cientos de elementos, el mismo gesto muchas veces.
- Un error de cantidad se paga en un concurso. Les importa poder demostrar de dónde sale cada número frente a un supervisor o un cliente.
- Leen en español de México. Conocen OPUS, Neodata, precios unitarios, generadores, la LOPSRM; no conocen el vocabulario interno del motor.
- A veces consultan desde el teléfono en obra; el trabajo de fondo se hace en escritorio.

## Product

- Klave lee los planos de una obra, mide cada elemento y arma generadores ligados al dibujo, con precios del catálogo de la oficina.
- La columna vertebral antes del contrato: subir planos → lectura → revisión en el visor → verificación → catálogo y variantes → presupuesto con diagnóstico → programa de obra → revisiones de planos (Rev B, C) → entrega a Excel, OPUS o Neodata.
- Después del contrato existen pantallas de contrato, convenios, estimaciones, ajuste de costos, bitácora, finiquito y riesgos.
- 30 pantallas en Next 16 / React 19, sistema de diseño propio (tokens claros y oscuros, primitivas en `components/ui.tsx`, iconos Phosphor).
- Colaboración en vivo por SSE; cuentas y roles por espacio de trabajo; un recorrido guiado de nueve capítulos sobre una obra de ejemplo por persona.
- Piloto con oficinas invitadas; el frontend se publica en Vercel desde `main`, la API se libera a mano en EC2.

## Constraints

- La interfaz está en español de México; la conversación con el equipo, en inglés.
- Identidad visual fija: paleta de tinta casi monocroma, un solo acento cobalto, `--primary` como color de acción, Space Grotesk para títulos y métricas, Geist para texto. No se vuelve a una interfaz multicolor.
- Sin funciones nuevas: el trabajo es terminar bien las que existen.
- La lectura determinista del motor no cambia en este trabajo.
- Las acciones destructivas o de autoridad siempre detrás de `ConfirmDialog`; los flujos repetitivos sin fricción y con teclado.
- El programa de obra sigue la LOPSRM vigente: plazo en días naturales, cuatro programas calendarizados.
- Regla de efectos del lint: nada de `setState` síncrono dentro de efectos.
- Claro, oscuro y ancho de teléfono funcionan en cada pantalla.

## Ethical stance

- Tres niveles de severidad que piden algo: bloqueante, dinero, revisar. Lo que no pide nada va al registro de criterios, no a una alarma.
- Sin porcentajes de confianza crudos; se muestra el recorte del plano como evidencia, no una explicación en prosa.
- Dinero sólo donde un renglón con precio lo respalda; si no, la exposición física (m³, PZA).
- Un bloqueante detiene la entrega; seguir exige escribir el motivo, que queda en la carátula.
- Nada se borra con un clic; lo reversible se puede deshacer.
- La obra de ejemplo y sus mapeos nunca tocan los datos de la oficina.
- Ninguna métrica de enganche: el producto se mide por presupuestos que la oficina se atreve a entregar.

## Success

- Una persona nueva llega del plano al Excel de OPUS en su primera sesión, en la obra de ejemplo y luego en una propia.
- Cada pantalla se reconoce como parte del mismo producto: el mismo gesto se ve y se comporta igual en todas.
- Ninguna pantalla deja a la persona sin saber qué pasa: carga, vacío, error y éxito siempre visibles y con salida.
- Cada cifra del presupuesto se rastrea hasta el elemento del plano en dos clics.
- Claro, oscuro y teléfono sin cortes ni desbordes en las 30 pantallas.

## Open questions

- ¿Qué pantallas posteriores al contrato (estimaciones, convenios, ajuste de costos, finiquito, bitácora, riesgos) entran en este acabado, o quedan para después del piloto?
