## 2026-10-27 · El acabado no añade funciones: termina las que existen
- Decided by: Diego
- Why: la app creció por parches; la meta es una interfaz más intencional, legible, fluida y mejor construida.
- Rejected: ninguna alternativa planteada.
- Rests on: conversación del 2026-10-27.

## 2026-10-27 · Contexto de usuarios, producto, restricciones y postura ética
- Decided by: Claude (default)
- Why: sale del trabajo previo en Klave (principios de interfaz, sistema de diseño, recorrido guiado); Diego confirmó el encuadre sin correcciones.
- Rejected: —
- Rests on: docs/principios-de-interfaz.md; docs/auditoria-ui.md; docs/auditoria-densidad.md.

## 2026-10-27 · La evaluación cubre las 30 pantallas, antes y después del contrato
- Decided by: Claude (default)
- Why: el desorden se ve entre pantallas; evaluar sólo la columna previa al contrato escondería las incoherencias con las demás. Qué entra al arreglo se decide después, con los hallazgos.
- Rejected: evaluar sólo las nueve pantallas del recorrido guiado.
- Rests on: el inventario de rutas en apps/web/app.

## 2026-10-27 · El porcentaje de confianza a la vista es mayor, no crítico
- Decided by: Claude (default)
- Why: contradice la doctrina (principio 2) y empuja a firmar sin abrir la evidencia, pero no impide ninguna tarea ni pierde datos; crítico queda para lo que bloquea o borra.
- Rejected: crítico, como lo calificó la revisión de palabras y accesibilidad.
- Rests on: docs/principios-de-interfaz.md; evaluation-klave-interfaz.md M1.

## 2026-10-27 · El detalle del concepto sin teclado es crítico
- Decided by: Claude (default)
- Why: para quien trabaja con teclado o lector de pantalla, asignar la clave del taller, variantes y croquis es imposible; es una tarea central bloqueada.
- Rejected: mayor.
- Rests on: WCAG 2.2 · 2.1.1; presupuesto/page.tsx:670-677.

## 2026-10-27 · Lo que la evaluación no cubrió
- Decided by: Claude (default)
- Why: el recorrido en vivo corrió en modo local (sin cuentas) con datos copiados de la máquina de Diego; las pantallas de cuentas (bienvenida con contraseña, invitación, recuperar, restablecer, verificar, cuenta, equipo) y el enlace compartido se revisaron solo en código. Nada se probó con lector de pantalla ni en un teléfono real; el teléfono fue emulación a 375 px.
- Rejected: crear cuentas de prueba para recorrer el modo protegido en esta ronda.
- Rests on: docs/ux/evaluation-klave-interfaz.md.

## 2026-10-27 · Artefactos de este trabajo
- Decided by: Claude (default)
- Why: el contexto (context-klave.md) fija para quién y con qué límites; la evaluación (evaluation-klave-interfaz.md) da los hallazgos ordenados; de ella sale el plan de arreglos.
- Rejected: un rediseño visual — la identidad visual está aprobada y se conserva.
- Rests on: conversación del 2026-10-27.
