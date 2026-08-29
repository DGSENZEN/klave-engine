# El tablero de nodos — diseño aprobado

Fecha: 2026-08-28. Aprobado por Diego en sesión (las cuatro decisiones de la
auditoría, todas con la recomendación). Contexto y evidencia:
[auditoria-motor.md](../../auditoria-motor.md) ·
[auditoria-densidad.md](../../auditoria-densidad.md) ·
[principios-de-interfaz.md](../../principios-de-interfaz.md). Artefacto
compartible: https://claude.ai/code/artifact/156ad330-7f91-4299-80db-1d8313605f9b

Este documento es la especificación de la pista de interfaz. Sus planes de
implementación se escriben **después** de que aterrice el plan
[2026-08-28-motor-p0-reconexion.md](../plans/2026-08-28-motor-p0-reconexion.md)
— no tiene caso dibujar mejor un número que todavía está mal conectado.

## La idea

Cada proyecto se presenta como un **tablero de nodos** (inspiración: Railway).
Cada nodo es una etapa del anteproyecto con estado real derivado, y un nodo se
desbloquea **solo cuando el administrador marca sus requisitos**. Es una
consolidación de lo que ya existe — 17+ pantallas, bus SSE con presencia y
línea de tiempo, ruta de verificación, candado de dinero — no una reescritura.

Nodos v1 (el sidebar de 22 entradas en 5 grupos se pliega a 6 nodos con
profundidad interna):

| Nodo | Contiene (rutas actuales) | Estado que muestra |
|---|---|---|
| Planos | resumen de lectura, `/lectura`, `/plano` | hojas, unidades (fuente y confirmación), XREF faltantes |
| Revisión | `/revision`, `/riesgos` | N con dudas, lote listo, quién revisa (presencia) |
| Catálogo | `/catalogo` (taller) + vínculos del proyecto | conceptos sin precio que el proyecto usa |
| Presupuesto | `/presupuesto`, `/apus`, generadores embebidos | candado de dinero, bloqueantes |
| Programa | `/programa`, `/flujo`, `/parametros` | plazo (hábiles **y** naturales, juntos) |
| Contrato | `/contrato`, `/estimaciones`, `/convenios`, `/bitacora`, `/ajuste-costos`, `/finiquito` | estado del catálogo convocante, estimaciones |

Al hacer clic, el nodo se expande a pantalla completa y monta las páginas
existentes como su contenido. El riel derecho es la **actividad** que ya emite
`ProjectLive` (`ChangeEntry` + presencia). El lienzo es DOM con transform CSS
(pan/zoom ligero), sin dependencias nuevas.

## Las cuatro decisiones (cerradas)

1. **Convivencia:** el tablero entra como vista principal del proyecto (el
   nuevo Resumen). El sidebar sobrevive hasta que el tablero tenga paridad;
   solo entonces se decide su retiro.
2. **Nodo bloqueado = visible con candado.** Muestra qué requisitos faltan y
   quién puede abrirlo. Nunca se oculta (94/106 moderadores quieren ver todo;
   principio 17).
3. **La firma del desbloqueo** vive en JSON por proyecto estilo
   `VerificationState` (actor + timestamp por requisito, en el control dir del
   proyecto) más un asiento en `audit_log` (ya es genérico:
   `workspace_id, actor, action, target_type/target_id, detail`). La bitácora
   foliada queda para firmas con peso legal — y antes exige derivar
   autor/parte de la sesión, que hoy no se hace (hallazgo de la exploración
   de roles).
4. **Gold de dinero:** recapturado declarándolo (pista del motor, tarea 2 del
   plan P0). Un catálogo de precios de fixture, solo para pruebas, puede
   volver después si hace falta.

## El candado del administrador

- Modelo: `requisitos` por nodo — lista corta definida por producto (p. ej.
  Presupuesto requiere: unidades confirmadas, lote de revisión cerrado,
  catálogo sin bloqueantes). Cada uno se marca con actor + fecha.
- Quién marca: admin del taller u owner del proyecto (los roles ya se aplican
  en `auth/middleware.py`; la interfaz necesita el dato «mi rol en este
  proyecto», que hoy el frontend **no recibe** — agregarlo al payload del
  proyecto es parte de la pista).
- El gate de interfaz generaliza `moneyGate()`: función pura
  `nodeGate(estado) → ok | pendiente | bloqueado`.
- Todo desbloqueo/bloqueo se asienta en `audit_log` y se emite por SSE
  (`review_updated` o un evento nuevo `gate_updated`).

## Las tres ideas del cliente (alcance de la pista «visor»)

1. **Medidas editables + conceptos parecidos al pasar el cursor.** El
   inspector del visor gana campos de medida editables (escriben un override
   verificado y encolan reproceso — patrón `units_override`) y un buscador de
   conceptos con ranking por familia detectada (reusa la búsqueda del
   catálogo; sustituye el `<select>` plano de «Crear ajuste»).
2. **Ida y vuelta medidas ↔ plano.** El vínculo inverso ya está en los datos
   (`line.source_detections`): detección seleccionada → su línea de
   presupuesto, con retorno, y vista dividida dentro del nodo expandido.
3. **Qué datos jalan, antes de procesar.** Pre-escaneo barato al subir
   (sección BLOCKS + capas + códigos de hoja, segundos, en el diálogo de
   subida): hojas reconocidas, disciplinas, bloques/prefabs, unidades
   estimadas. Después de procesar, el índice de prefabricados alimenta el
   mismo panel.

## Restricciones vinculantes

- `principios-de-interfaz.md` manda: honestidad > severidad > legibilidad;
  sin porcentajes de confianza estampados; dinero resumido por peso de
  importe; nada de $0 inventados.
- Lección de la auditoría de densidad: el tablero enseña **pocos hechos
  distintos** — un chip por decisión, con denominador; jamás una tarjeta por
  repetición.
- Identidad intacta: casi monocromo, un acento, Phosphor, primitivos de
  `ui.tsx`, tokens de `globals.css`. Sin librerías nuevas de grafo/canvas.
- Los números que aparezcan en dos pantallas llevan la misma definición o su
  calificador en ambas (plazo hábiles/naturales siempre juntos).

## Orden de las pistas

1. **Motor P0** (plan escrito) → 2. **Tablero + candados** → 3. **Visor**
(las tres ideas del cliente) → 4. **Pre-escaneo + índice de prefabricados en
la interfaz**. Cada pista recibe su plan de implementación al llegar su turno,
escrito contra el código real de ese momento.
