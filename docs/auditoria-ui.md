# Auditoría UI/UX — qué se repite, qué se rompe, qué carga sin avisar, qué sobra

Fecha: 2026-08-23. Fuentes: inventario control por control de todas las páginas (app, componentes, `lib/api.ts`), auditoría de UX previa y recorrido con Marina Lote 04 en escritorio, móvil y tema oscuro. Las correcciones marcadas **hecho** están en `main`.

## 1. Lo que se rompe (primer día de un piloto)

| Bug | Estado |
|---|---|
| Todas las pantallas del proyecto mostraban el id en vez del nombre | **hecho** (`layout.tsx` carga el nombre) |
| "verlos en el plano" y "plano" apuntaban a `?concept=` y nada lo leía | **hecho** (el visor filtra y hace zoom a los elementos del concepto; `?bbox=` para riesgos) |
| Proyecto subido pero nunca encolado → "Procesando…" infinito sin botón | **hecho** (pantalla "aún no se procesa" con Procesar ahora; error de estado con Reintentar) |
| Visor sin `.catch` → esqueleto eterno | **hecho** (error con Reintentar) |
| Parámetros y Configuración: error inalcanzable detrás del esqueleto | **hecho** |
| Revisión: "seleccionar todo" > 2,000 claves → 422 | **hecho** (lotes de 500, un solo recálculo) |
| Estado "SIN VERIFICAR" del dinero nunca se renderizaba | **hecho** (banner en presupuesto, APUs, programa, flujo) |
| Build de producción sin `NEXT_PUBLIC_API_URL` culpa al servidor | **hecho** (banner de configuración) |
| Resumen: confirmar paso / reprocesar tragaban el error; home Reprocesar sin respuesta | **hecho** (ocupado + error visible) |
| Lectura: asignar mapeo sin estado ocupado (doble clic = mapeo doble); `m²` no coincidía con `M2` | **hecho** |
| Riesgos: 407 "columna sin eje" por una malla de 6 ejes; rutas de archivo en vez de hojas | **hecho** (malla pobre = un hallazgo; hojas por nombre; 452 → 94) |
| Visor: 336 "Castillos" incluían 137 etiquetas de cuadro | **hecho** (familia "Etiquetas de cuadro", oculta por defecto) |
| Lectura: "Hojas 1" contaba archivos | **hecho** (22 marcos) |
| Home "precios con más de 6 meses" ≠ catálogo "0 por revisar" | **hecho** (una sola regla de vigencia) |
| Presupuesto titulado "Catálogo de conceptos" | **hecho** |
| Parámetros/Taller con llaves crudas (`castillo_section_m2`…) | **hecho** (etiquetas con unidad y condición) |
| Borrar versión/plantilla/regla sin confirmar mientras restaurar sí confirma | **hecho** (ConfirmDialog) |
| Sugerencias de alias para conceptos que no están en el presupuesto | **hecho** |
| Revisión sin orden por columna ni métrica de excluidos | **hecho** |

Pendientes de esta lista: `Restablecer` en parámetros sin confirmación; `Recargar` en conflicto descarta ediciones sin avisar; el preset regional muta al seleccionar; "Actualizar vencidos por índice" y "Aplicar salario real" reescriben precios sin vista previa; cuenta: cerrar sesiones sin confirmar; `Cambios guardados.` que nunca se va; callout de catálogo "deben recalcular" sin enlace.

## 2. Lo que se repite (y qué hacemos con cada repetición)

| Acción | Dónde aparece | Decisión |
|---|---|---|
| Reprocesar | kebab del home, callout del resumen, pantalla "no procesado", "Agregar hojas" (re-encola sin decirlo) | Un solo contrato: ocupado + error visible + el mismo texto. Agregar hojas dice que reprocesa. **hecho** salvo el texto de hojas. |
| "Confirmar" | 3 pasos de verificación (resumen), revisión en lote, visor por elemento, unidades | El verbo del elemento se queda ("Confirmar"); los pasos del resumen pasan a **"Marcar como verificado"** y el deshacer oculto en el ícono pasa a un botón **"Deshacer"**; unidades: "Confirmar unidades". |
| Cambiar una cantidad | lápiz → Fijar (motivo obligatorio), "Agregar ajuste" ± (nota opcional), medición del visor → Agregar | Una sola superficie: el formulario de ajustes exige motivo como el lápiz; el visor entra por ahí. |
| Usar un precio de referencia | catálogo `Aplicar` (insumo), catálogo `P.U.` (concepto: pausa la matriz), selector `Usar`, sugerencias `Adoptar` | Un verbo: **"Usar este precio"** + alcance explícito ("como insumo" / "como P.U. del concepto" / "como clave del taller"). `P.U.` de dos letras desaparece. |
| Importar en el catálogo | Importar precios, Importar matrices, Importar/Reimportar fuente, Importar catálogo, Importar presupuesto anterior | **Un menú "Importar…"** con cinco tipos, cada uno con su contrato de columnas antes de abrir el archivo. Las secciones conservan sus listas, no sus botones. |
| Exportar | menú del presupuesto (7), catálogo `Exportar` (CSV de insumos sin decirlo), dos descargas de cotización | El presupuesto ya es un menú; catálogo → "Exportar insumos (CSV)"; cotización → menú en la tarjeta de vigencia. |
| Historial | versiones del presupuesto, "Cambios del último procesamiento", línea de tiempo de sesión, registro de actividad | El diff de corrida entra a Versiones como entrada automática "corrida N → N+1"; lo demás se queda donde está. |
| Renombrar / cliente / archivar / quitar | kebab del home y Configuración | Se quedan ambos puntos de entrada con el mismo texto y la misma señal de éxito. |
| Recalcular | botón de parámetros, callout de catálogo cambiado, efecto automático del mapeo en lectura, frase en catálogo | Botón explícito + "recalculado" donde sea automático + el catálogo enlaza a los proyectos afectados en vez de pedirlo. |
| Abrir/cerrar secciones | ocho implementaciones distintas | Un primitivo `Disclosure` en `ui.tsx` (con `aria-expanded`). |

## 3. Lo que carga sin avisar (esqueletos y estados)

Regla: toda sección que hace su propia petición tiene sus cuatro estados — cargando (esqueleto con la forma del contenido, nunca texto "Cargando…"), vacío (qué hacer), error (qué pasó y cómo reintentar), y, donde aplica, "lectura anterior / sin procesar".

| Sección | Hoy | Decisión |
|---|---|---|
| Versiones, croquis, selector de concepto | texto "Cargando…" | esqueletos **hecho** |
| Sugerencias de alias | aparece tarde y empuja la página; error invisible | reservar alto mínimo; error = callout |
| Fuentes, vigencia, plantillas, salario real (catálogo) | se ven "cargadas pero vacías" cuando la petición falla | error visible por tarjeta |
| Diff de corrida, ruta de verificación, línea de tiempo | desaparecen en silencio al fallar | error visible |
| Tarjeta de IA (lectura) | botón "Leyendo…" y nada más durante minutos | progreso por hoja, cancelar, coste estimado antes |
| Búsqueda de referencias | sin indicador; error = "Sin resultados" | indicador + error distinto de vacío |
| Revisión: error genérico para 500 y para "no procesado" | un solo mensaje | dos mensajes |
| Presupuesto y visor con cero líneas / cero detecciones | tabla vacía con $0 | estado vacío que diga por qué y qué hacer |
| Descargas por `window.location` | sin estado; un error sustituye la app por JSON | descarga con estado y error en la página |

## 4. Lo que sobra o estorba (podar y enfocar)

Decisiones de diseño, no de código:

1. **Navegación del proyecto**: once entradas es demasiado para tres tareas (leer, revisar, entregar). Se agrupan en tres: *Leer* (Resumen, Lectura, Visor), *Revisar* (Revisión, Riesgos), *Entregar* (Presupuesto, Precios unitarios, Programa y flujo, Parámetros). Riesgos no se fusiona en Revisión todavía: son dudas del plano, no verdictos, pero comparten el salto al visor. Configuración baja al final como ajustes del proyecto.
2. **Catálogo** (1,777 líneas en una página): tabs — *Insumos*, *Conceptos y matrices*, *Fuentes e importación*, *Plantillas y paramétricos*, *Salario real y vigencia*. Sin buscador no se puede operar un catálogo de 2,700 filas: buscador y filtro por tipo en insumos y conceptos.
3. **Precios unitarios**: página de tarjetas sin buscador ni export; se queda como página pero con buscador y el export de APUs; el primer APU deja de auto-expandirse.
4. **Ajustes manuales ±**: sobrevive solo como "Agregar concepto faltante" con motivo obligatorio; la edición de cantidades vive en la línea.
5. **Métrica "MXN"** en APUs, "Cotas (DIMENSION)" en presupuesto, `u.dib`: fuera o con nombre de persona.
6. **Código muerto**: `ProgressBar`, `Spinner`, `actorHeaders`; `getAliases`/`addParametricRule` sin UI → o se usan (lista de alias; regla a mano) o se van. Se usan.
7. **Duplicados de utilidades**: `timeAgo` ×2, etiquetas de tipo de recurso ×3, extracción de mensaje de `ApiError` ×10, diálogo modal ×4, Escape ×6, regex de título de planta ×4, CSV ×2, selectores sin primitivo (~15), checkboxes en cuatro estilos, badge de confianza con cinco reglas. Se consolidan en `lib/families.ts`, `lib/format.ts`, `ui.tsx` (`Select`, `Checkbox`, `ConfidenceBadge`, `Disclosure`, `Modal`).
8. **Identificadores crudos** visibles: tipos de entidad DXF, `mano_de_obra`, `session_created`, `ANTHROPIC_API_KEY`, `make users-db-up`, `data/sources/…`, `Sn/SBC/Ps/Fsr/Tp/Tl`, indicador sin estado → texto vacío. Cada uno recibe etiqueta o se convierte en "pide a tu administrador…".

## 5. Orden de ejecución

1. Consistencia de verbos y confirmaciones (sección 2 y pendientes de 1).
2. Estados por sección (sección 3).
3. Primitivos y utilidades compartidas (sección 4.7) — una sola pasada que toca todas las páginas.
4. Catálogo con tabs + menú Importar + buscadores; navegación agrupada del proyecto; APUs con buscador/export.
5. Identificadores crudos (4.8) y el resto de 4.
