# La lectura estructural, en una página

Para el ingeniero que revisa un proyecto en Klave: de dónde sale cada valor de un elemento, qué quiere decir cada hallazgo y cómo se decide un conflicto. Está en la pestaña **Revisión → Lectura estructural**.

## De dónde sale cada valor

Cada dato de un elemento (sección, altura o longitud, varillas, estribos, parrilla, f'c) dice su **fuente**, la hoja y el texto del plano de donde salió. Si dos fuentes dan valores distintos, gana la de más rango y la otra se queda a la vista como alternativa:

| rango | fuente | qué es |
|---|---|---|
| 1 | **humano** | lo que tú decidiste en Revisión («Usar este valor») |
| 2 | **cuadro** | una fila de un cuadro con títulos (MARCA · SECCIÓN · ARMADO) |
| 3 | **detalle** | lo escrito junto al título de la marca: su pila de armado («8#6 / 2E#3EXT@10 / CENTRO@20») y las cotas de su sección |
| 4 | **sección dibujada** | lo que mide el dibujo de la sección a la escala de sus cotas (los cuadros «SIN ESCALA» casi nunca coinciden: por eso pierde contra la cota) |
| 5 | **nota** | una nota de familia («CADENA DE ENRASE 15x25 4#3 E#2@15») o una nota general |
| 6 | **medido** | la geometría de la planta (el contorno de un castillo, el largo de un muro) |
| 7 | **regla** | lo que las notas del proyecto mandan (recubrimientos, ganchos, anclajes) |
| 8 | **supuesto** | el valor de Klave cuando el plano no lo dice; siempre marcado |

La **IA** sólo llena un campo que ningún texto del plano toca, y queda *por confirmar*: nunca cuenta como «del plano». Si el texto existe pero no se pudo leer, el campo queda vacío con un aviso que cita el texto; la IA no lo tapa.

**Las reglas del proyecto** salen de la tabla de varillas y de las notas generales de cada hoja: recubrimiento por familia, ganchos, primer estribo, anclajes declarados, desde qué varilla se suelda y hasta cuál se traslapa. Cada hoja usa las de su propia nota (en Marina la cimentación traslapa hasta #6 y suelda desde #8; la superestructura traslapa hasta #8 y suelda desde #10).

**El armado se lee entero o se avisa.** «4#5+2#4» son dos grupos de varillas, «2E+1G#3EXT@10 / CENTRO@15» es un juego de dos estribos y una grapa con zona de extremos y de centro, «EYG#3@15» es estribo y grapa (nunca una malla). Lo que no se entiende se cita en un aviso; nunca se tira en silencio.

## Qué quiere decir cada hallazgo

Severidad: **bloquea** (no se puede cuantificar sin ti), **duda** (Klave tomó un valor, pero el plano deja la pregunta), **aviso** (para que lo sepas).

| # | hallazgo | qué hacer |
|---|---|---|
| 1 | Marca colocada en planta y definida en ningún lado | buscar su cuadro o detalle; si una nota de familia la cubre, es duda y se usa la nota |
| 2 | Marca definida y nunca colocada | normalmente nada; confirma que no falta en planta |
| 7 | Falta un valor crítico (pilote sin longitud, losa sin armado, estribo sin separación) | dice qué supuesto lo reemplazó; dar el valor o aceptarlo |
| 8 | El plano se contradice (la tabla contra una nota, dos copias de un detalle que no dicen lo mismo) | decidir cuál vale; preguntar al calculista si hace falta |
| 10 | Una marca escrita en planta sin su elemento | revisar si el detector dejó un elemento sin ver |
| 11 | Un texto de armado sin dueño claro, o que no se pudo leer | decir de qué marca es, o ignorarlo |

La tarjeta muestra, por familia: colocaciones, cuántas tienen su definición, qué parte de los valores críticos viene del plano (no de reglas, supuestos ni IA), los hallazgos abiertos y **el dinero en juego** (la diferencia entre el valor ganador y el perdedor por su precio). Empieza por arriba.

## Cómo se decide un conflicto

1. Abre el hallazgo: muestra los dos valores, su fuente y su hoja lado a lado; cada uno abre el visor en el texto o la cota que lo dio.
2. Elige con **«Usar este valor»**. La decisión es de la marca (vale para todas sus colocaciones), queda guardada como fuente *humano*, sobrevive al reprocesar y mueve las cantidades de inmediato.
3. Si el plano no alcanza para decidir, déjalo en duda y pregunta a la oficina: Klave nunca elige en silencio entre dos lecturas del mismo rango.
