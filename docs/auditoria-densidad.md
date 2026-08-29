# Auditoría de densidad — dónde se pierde la señal en las pantallas de datos

Fecha: 2026-08-25. Complementa [auditoria-ui.md](auditoria-ui.md) (lo que se
rompe, se repite y carga sin avisar) y se juzga contra
[principios-de-interfaz.md](principios-de-interfaz.md) (la regla escrita).
Aquella auditoría preguntaba *¿funciona?*. Esta pregunta **¿se lee?**

## Método

Recorrido en vivo de **Marina Lote 04 — Completo** (12 hojas, 48 líneas de
presupuesto, $4,143,241, corrida `run_7b0ba030`) en 1512×950, más análisis de
los artefactos de la corrida en disco y del código de cada pantalla. Todas las
cifras de este documento son medidas, no impresiones: altura real del
documento, conteo de nodos, entropía por columna, duración de las peticiones y
distribución de hallazgos leída del `risk_report.json` y del `cost_report.json`.

Dos advertencias honestas:

- El grupo **Contrato** (Estimaciones, Convenios, Bitácora, Finiquito) no tiene
  datos en este taller, así que se auditó **solo por código**. Queda marcado
  donde aplica.
- Otra sesión estaba editando el repositorio durante el recorrido (el menú del
  proyecto creció de 16 a 17 entradas mientras se medía). Las cifras llevan
  fecha; el mecanismo que describen no depende de ellas.

---

## 0. La tesis

**Klave no muestra demasiados datos. Muestra pocos hechos distintos, muchas
veces.**

Esa distinción decide todo lo que sigue. Si el problema fuera densidad, la
respuesta sería esconder cosas — y esconder es exactamente lo que el principio
17 prohíbe (94 de 106 moderadores quieren ver todo por defecto) y lo que un
perito que defiende un presupuesto no perdona. Pero la densidad no es el
problema. El problema es que **la misma decisión se dibuja decenas de veces, y
que varios campos que parecen medición son constantes**.

Tres ejemplos, los tres medidos:

| Pantalla | Lo que dibuja | Lo que en realidad dice |
|---|---|---|
| **Riesgos** | 163 tarjetas | **4** tipos de riesgo. 88 de ellas dicen «verifícalo en el visor», que *es* el trabajo completo de la pantalla de Revisión |
| **Presupuesto** | 21 hallazgos, 9.2 pantallas de scroll, 7,559 palabras | 19 son el mismo hallazgo. La misma frase literal aparece **19 veces** |
| **Revisión** | 500 renglones × 8 columnas | 5 de 8 columnas tienen ≤ 21 valores distintos en 501 renglones; dos de ellas son el mismo número |

Y el caso que resume todo: **6 de 11 fases cierran en $0.00** — aire
acondicionado, cancelería, gas, sanitaria, hidráulica, eléctrica. El motor sí
las leyó (238.89 m de bajadas pluviales, 150.87 m de agua fría, 25 compuertas).
Lo que falta son precios en el catálogo. Ese hecho único hoy se dibuja **de
cuatro maneras distintas** — 19 hallazgos, 6 encabezados de sección en $0, 6
renglones en cero de la gráfica por fase, y 11 renglones de indicador que dicen
«sin referencia» — y **ninguna de las cuatro lo enuncia**.

La frase que falta es una:

> El total es de obra negra. Seis especialidades tienen cantidad medida y ningún
> precio en tu catálogo: 19 conceptos. Ponerles precio o declararlas fuera de
> alcance.

Esa frase sustituye cerca de tres pantallas de scroll.

---

## 1. La medición

Marina Lote 04 — Completo, 1512×950. «Pantallas» = alto del documento ÷ alto de
la ventana.

| Pantalla | Scroll | Palabras | Objetos repetidos | Señal real |
|---|---:|---:|---|---|
| Presupuesto | 9.2 | 7,559 | 19 hallazgos idénticos = **30.8 % del alto de la página** | 1 bloqueante ($1,005,983) + acero 3× bajo |
| Revisión | 32.8 | — | 500 renglones; `CONF.` y `DUDAS` son el mismo número | 62 con dudas |
| Riesgos | ~32 | — | 163 tarjetas, 4 tipos, 12 plantillas de acción | 1 malla de ejes sin leer |
| Lectura | 10.5 | 2,970 | **111 chips** de tipos de entidad DXF | 10 XREF faltantes, 7 hojas en recuperación |
| Catálogo (Insumos) | 11.8 | 1,914 | 111 renglones × 4 controles = **470 controles** | ~6 insumos mueven $3.1 M |

**El detalle más caro:** en Presupuesto, los 19 hallazgos idénticos ocupan de
y=616 a y=3310 — **2,694 px, 2.8 pantallas completas, el 30.8 % del documento**
— y empiezan inmediatamente debajo del título. La tabla de presupuesto, que da
nombre a la pantalla, arranca después de ellos.

**El costo de entrada:** la petición `/revision` tardó **29.6 s** y se lanzó
**dos veces** (29,595 ms y 29,499 ms). Treinta segundos de esqueleto sin
progreso ni estimación, para una pantalla de 500 renglones.

---

## 2. Los seis mecanismos

Cada uno se nombra para poder pedirlo por su nombre en una revisión de código.

### M1 · Repetición sin agrupar

El principio 7 ya está escrito — «nunca un hallazgo por renglón», «seis
conceptos con el f'c equivocado son **una** decisión» — y está implementado en
`hallazgos.py`. **Riesgos no lo aplica.** Hay dos sistemas de hallazgos en la
misma aplicación con políticas opuestas:

| | Diagnóstico (`hallazgos.py`) | Riesgos (`risk_report.json`) |
|---|---|---|
| Agrupa repeticiones | sí, por `Rule.group` | **no** |
| Lleva dinero | sí, o exposición física | **no, nunca** |
| Lleva denominador | sí | **no** |
| Momento límite | sí | no |
| Identificadores internos | ocultos | **visibles** (`footing_column_proximity_check`) |

Riesgos: 163 tarjetas → 4 tipos → 12 plantillas de acción, de las que 3 cubren
el 89 %:

```
88 × low_confidence_detection_in_takeoff   → 72 × «Verifica manualmente X en el visor»
43 × footing_without_column                → 43 × «Revisa si la zapata X soporta una columna sin etiqueta»
31 × duplicate_column_tag                  → 30 × «Confirma si X se repite a propósito»
 1 × sparse_grid
```

Presupuesto: 19 hallazgos «X tiene cantidad pero no precio», cada uno con la
misma frase literal — *«Elige de dónde sale el precio: no tengo forma de saber
cuánto cuesta sin que me lo digas o me apuntes a una fuente»* — **19 veces**,
más «Dale precio a X en el catálogo del taller» 19 veces y «Revisa la línea X en
el presupuesto» 19 veces.

**Y el peor efecto no es el volumen, es el orden.** El hallazgo `sparse_grid`
dice: *«se leyeron 6 ejes y 222 de 222 columnas quedan sin eje cercano; la
comprobación columna–eje no aplica hasta que la malla se lea completa»*. Es
decir: **explica y probablemente invalida las otras 74 medias**. La pantalla
ordena por severidad, `sparse_grid` es `low`, y por lo tanto **el hallazgo que
explica los otros 162 aparece en la posición 163**.

> Ordenar por severidad enumerada entierra la causa debajo de sus síntomas.

### M2 · Constantes disfrazadas de medición

Un campo cuyo valor es idéntico en el 100 % de los renglones no es un dato: es
tinta. Y es peor que tinta cuando parece una medición, porque tranquiliza.

| Campo | Valor observado | Verdad |
|---|---|---|
| `Confianza 100%` (Riesgos) | 1.0 en **las 163** | constante |
| `0 meses` (Catálogo) | en **73 de 111** renglones | casi constante |
| `IMPORTE EN LECTURAS FIRMES` | **100 %** | **no puede dar otra cosa** |
| `CRÍTICA` (Programa) | en 27 de 30 barras | la excepción son 3 |
| `sin referencia` (Indicadores) | en **11 de 15** renglones | panel medio vacío |

El tercero merece detenerse. El indicador pesa dinero sobre las lecturas de
confianza ≥ 70 %. La confianza mínima entre las líneas **con precio** es
exactamente **0.70**. El umbral es el piso de la distribución: el indicador
**está construido para dar 100 %**. Hoy anuncia «100 % en lecturas firmes» —
acompañado de tres renglones de prosa que explican lo cuidadoso que es el
cálculo — en un presupuesto donde el 40 % de las líneas no tiene precio y el
acero está 3× por debajo del rango típico.

Eso no es ruido: es el principio 1 al revés. **La pantalla se ve mejor de lo que
es.**

### M3 · Columnas de baja entropía

Entropía por columna en la tabla de Revisión, sobre los 501 renglones
efectivamente dibujados:

| Columna | Valores distintos / 501 |
|---|---:|
| ELEMENTO | 501 |
| MEDIDA | 176 |
| CONCEPTO | **21** |
| PLANTA | **15** |
| CONF. | **14** |
| DUDAS | **9** |
| ESTADO | **2** |

Cinco de ocho columnas tienen ≤ 21 valores distintos. `ESTADO` dibuja 501
celdas con 2 valores. Y `CONF.` y `DUDAS` son **el mismo número, en columnas
contiguas**: la fila dice `68%` y luego `confianza 68%`.

Franconeri et al. miden que comparar subconjuntos corre a dos o tres
comparaciones por segundo. Una tabla de 500 × 8 pide del orden de 4,000 lecturas
de celda para encontrar 62 dudas. Aritméticamente no se puede.

Una columna de baja entropía no es una columna: es un **filtro** o un
**encabezado de grupo** que se dibujó mal.

### M4 · Un hecho contado cuatro veces

Ya está arriba: las 6 especialidades sin precio, dibujadas cuatro veces sin
enunciarse una. El efecto de redundancia de Sweller dice que presentar la misma
información en dos formas que hay que reconciliar **agrega** carga en vez de
quitarla. Aquí son cuatro formas, ninguna suficiente por sí sola.

Lo mismo, más chico, en otros lados: los conteos de entidades por hoja aparecen
en Lectura (111 chips) y otra vez en el riel del Visor; el reparto por fase
aparece en la gráfica del Resumen, en los subtotales de sección del Presupuesto
y en los 11 renglones de `phase_shares`.

### M5 · Andamiaje pedagógico permanente

La pantalla de Revisión encabeza con ~70 palabras de investigación:

> «Cuando lo que falla es raro, la vista se rinde antes de encontrarlo: en las
> mediciones clásicas de búsqueda visual, con 1 % de objetivos se pasa por alto
> el 30 %, y avisarlo de antemano no lo corrige…»

El contenido es correcto y la decisión de producto que lo respalda es correcta.
**La permanencia no lo es.** El efecto de reversión por experiencia (Kalyuga y
cols.) mide que el apoyo que un novato necesita **degrada** el desempeño de
quien ya sabe: obliga a reconciliar una explicación externa con un modelo
interno que ya la contiene. En la visita 40, el párrafo es exactamente el ruido
del que habla.

Igual el bloque de tres renglones que explica «importe en lecturas firmes», e
igual el «Klave no puede hacerlo solo: …» repetido 19 veces.

**Regla:** el andamiaje se muestra la primera vez y se colapsa después, por
persona y por proyecto, con la explicación siempre a un clic.

### M6 · Incoherencia entre pantallas

Woods llamó *visual momentum* a lo que permite pasar de una pantalla a otra sin
volver a orientarse. Klave lo pierde en números que el usuario va a citar:

| Concepto | Una pantalla dice | Otra dice |
|---|---|---|
| Plazo | Resumen: **393 días** | Programa: **458 días naturales** |
| Hojas | Resumen: **12** | Lectura: **81** · Resumen: «Vistas de planta **50**» |
| Dudas | Revisión: **62 con dudas** | Riesgos: **88 de baja confianza** |
| Elementos | Revisión: **670** | Visor: **1,044 visibles** de 1,183 detecciones |

Ninguno es un error de cálculo: cada número es correcto bajo su propia
definición, y **Programa sí explica la suya** («393 días hábiles en semana de
seis días… el contrato se cuenta en naturales»). El problema es que el Resumen
enseña **393** sin calificarlo, y el plazo es una cifra contractual. Quien solo
ve el Resumen cita el número equivocado.

---

## 3. Pantalla por pantalla

### Resumen
- Cuatro tarjetas con **tres totales distintos** ($3,112,058 / $3,945,944 /
  $4,143,241) más el plazo. Ninguna dice cuál se cita.
- «Costo directo por fase» con **6 renglones en $0** de 11.
- «Unidades del plano — m · **confianza 90 %**»: porcentaje de confianza no
  calibrado, justo lo que rechaza el principio 2.
- «Cotas leídas **3461**» sin denominador ni interpretación.
- Las 12 hojas se listan con su nombre crudo de archivo
  (`02-02_estructural_l_04_-_26_01_15.dwg`).

### Presupuesto
- 30.8 % del alto son 19 hallazgos idénticos, encima de la tabla.
- Cada hallazgo dibuja siempre «Cómo comprobarlo» y «Qué hacer»: el nivel 2 de
  revelación está permanentemente abierto, así que el bloqueante de $1,005,983 y
  `AIR-005` (4 PZA sin precio) pesan lo mismo en pantalla.
- Columna `CONF.` con porcentajes por renglón (94 %, 90 %, 79 %, 70 %…),
  agrupados en el piso 0.70 — el sesgo de centrado que documenta Hubbard.
- Descripciones importadas en MAYÚSCULA SOSTENIDA de hasta ~250 caracteres
  dentro de una celda, junto a descripciones de una línea.
- «Conceptos agregados a mano» vuelca el catálogo entero al final de la página.
- El desglose por vista dentro de la celda de cantidad es **buen instinto**
  (principio 13) mal dibujado: triplica el alto del renglón y no distingue los
  parciales del total.

### Revisión
- 29.6 s de carga, petición duplicada, esqueleto sin progreso.
- 5 tarjetas de métrica para 3 números independientes: al arrancar,
  `ELEMENTOS 670` y `SIN REVISAR 670` son el mismo número dos veces.
- **3 de esas 5 tarjetas filtran al hacer clic y 2 no** (`CONFIRMADOS` y
  `EXCLUIDOS`), sin ninguna diferencia visual. Clic impredecible.
- La distribución que exige el principio 12 existe pero no es el control.

### Riesgos
- 163 tarjetas / 4 tipos. Sin dinero, sin denominadores, con nombres de método
  internos y `Confianza 100%` constante.
- La causa raíz ordenada al final.
- 88 de las 163 duplican el trabajo de Revisión.

### Lectura del plano
- **111 chips** de tipos de entidad DXF («Arcos 164», «Achurados 8»). Ninguna
  decisión del usuario depende de ellos.
- Debajo de esos 111 chips: **10 «Falta: súbela como hoja»** — referencias
  externas ausentes, es decir, geometría que no entró al presupuesto. Es un
  hecho de clase bloqueante dibujado como texto chico, diez veces.
- `HOJAS 81` contra las 12 del Resumen.

### Visor del plano
- El riel repite los conteos de entidades por hoja.
- Con las 12 hojas encendidas el lienzo se ve prácticamente vacío. **No
  verificado**: el servidor de desarrollo estaba recompilando durante la prueba
  y no pude confirmarlo limpiamente. Queda como sospecha a reproducir, no como
  hallazgo.

### Catálogo del taller
- 470 controles en la pestaña de Insumos: cada renglón es un formulario de 4
  campos. Los 111 renglones son igual de editables, y nada señala los ~6 que
  mueven los $3.1 M de Marina.
- `0 meses` en 73 renglones.

### Precios unitarios — **el modelo a seguir**
Buscador, una barra de composición por renglón (etiqueta directa, no leyenda),
el precio a la derecha, sin adorno. Es la pantalla menos ruidosa de la
aplicación y el patrón del que deberían derivarse las demás. Único pero:
`CONCEPTOS ANALIZADOS 29` sin su denominador — son 29 **de 48**, y las 19
ausentes son justo las que no tienen precio.

### Programa y flujo
- `EN RUTA CRÍTICA 27 de 30` está bien hecho: denominador y palanca nombrada.
- Pero entonces `CRÍTICA` se estampa en el 90 % de las barras. El principio 5 ya
  lo advierte para «SIN VERIFICAR»: **marca la excepción, no la regla.** Aquí la
  excepción son 3.

### Contrato (Estimaciones, Convenios, Bitácora, Finiquito) — solo código
Sin datos en este taller. El estado vacío de Estimaciones es correcto: dice qué
falta y qué pasa después. **La advertencia estructural** es que el menú del
proyecto ya tiene 16–17 entradas en 5 grupos y el riel mide 1,054 px contra 950
px de ventana: **no cabe en una laptop**, y «Catálogo del taller» quedó debajo
del pliegue.

---

## 4. Lo que sí funciona (no romperlo)

- **Precios unitarios**: el patrón de referencia.
- **Esqueletos con la forma del contenido** y estados vacíos que dicen qué
  hacer.
- **`27 de 30` con la palanca nombrada** — el mejor renglón de la aplicación.
- **Exposición física cuando no hay dinero** (`23.00 PZA` en vez de un peso
  inventado): principio 1 bien aplicado.
- **`momento`** (entregar / cotizar / contratar) en los hallazgos del
  Diagnóstico.
- **El lote de revisión** como decisión de producto.
- **Confirmaciones duras** para lo destructivo (`typeToConfirm`) y el color
  contenido de la identidad visual.

---

## 5. Direcciones priorizadas

Cada una nombra el mecanismo que mata y cómo se comprueba.

### P0 — el número miente o la pantalla no se puede trabajar

1. **Un solo hecho para las especialidades sin precio.** (M1, M4)
   Sustituir 19 hallazgos + 6 secciones en $0 + 6 renglones de gráfica + 11
   «sin referencia» por un enunciado en Resumen y Presupuesto con su acción.
   *Prueba:* «tiene cantidad pero no precio» aparece **una vez**.

2. **Riesgos se agrupa con la misma regla que Diagnóstico.** (M1)
   163 → ≤ 6 tarjetas, cada una con `n de N`, dinero o exposición física, y sin
   nombres de método internos.
   *Prueba:* ningún tipo de riesgo dibuja más de una tarjeta.

3. **La causa se ordena antes que el síntoma.** (M1)
   Un hallazgo que invalida a otros se muestra primero y **dice a cuáles**.
   *Prueba:* con la malla sin leer, `sparse_grid` es el primero y las 43 zapatas
   quedan marcadas como «no comprobable todavía».

4. **Fuera los porcentajes de confianza de las superficies de lectura.** (M2)
   Columna `CONF.`, `confianza 68%`, `m · confianza 90 %`, `Confianza 100%`. La
   confianza dirige el orden y arma el lote, no se estampa (principio 2).
   *Prueba:* ningún porcentaje junto a una detección.

5. **Reconciliar los números que se contradicen entre pantallas.** (M6)
   Plazo, hojas, dudas, elementos: una definición por concepto, y donde haya dos
   (hábiles/naturales) **las dos siempre juntas**.
   *Prueba:* el plazo se lee igual en Resumen y en Programa.

### P1 — se puede trabajar, pero cuesta de más

6. **Pasada de compresión en la tabla de Revisión.** (M3)
   Las columnas de baja entropía suben a filtro o a encabezado de grupo; `CONF.`
   y `DUDAS` se funden.
   *Prueba:* ninguna columna con < 25 valores distintos en 500 renglones
   sobrevive como columna.

7. **Progreso real en `/revision`.** (—)
   Deduplicar la petición y, sobre 3 s, decir qué se está leyendo.
   *Prueba:* primer renglón visible en < 3 s, o progreso enumerado.

8. **Lectura: fuera los 111 contadores, arriba los 10 XREF faltantes.** (M4)
   *Prueba:* «faltan 10 referencias externas» es lo primero de la pantalla.

9. **Invertir la insignia `CRÍTICA`.** (M2) Marcar las 3 que **no** lo son.

10. **Catálogo ponderado por dinero en riesgo.** (M2, M3)
    Ordenar/marcar por importe en proyectos vivos; un solo afford. de edición
    por renglón en vez de cuatro campos siempre abiertos.

11. **Andamiaje que se retira.** (M5)
    El párrafo del lote, la explicación de «lecturas firmes» y el «Klave no puede
    hacerlo solo» se colapsan después de la primera lectura.

12. **Arreglar o retirar `IMPORTE EN LECTURAS FIRMES`.** (M2)
    Un indicador que no puede variar no es un indicador.

### P2 — pulido

13. Menú del proyecto: 17 entradas no caben en 950 px.
14. Denominadores en todas partes (`29` → `29 de 48`).
15. Descripciones importadas en MAYÚSCULAS → caja normal.
16. Las 5 tarjetas de Revisión filtran, o ninguna.

---

## 6. Una métrica de ruido que se pueda seguir

El principio 11 ya pide instrumentar falsos positivos por tipo. Estas cuatro son
computables hoy, sin telemetría, sobre cualquier proyecto:

| Métrica | Definición | Marina hoy | Objetivo |
|---|---|---:|---:|
| **Hallazgos por decisión** | tarjetas ÷ (tipo × acción) distintas | Riesgos **40.8** | ≤ 1.5 |
| **Constantes en pantalla** | campos con un solo valor en el 100 % de los renglones | ≥ 4 | 0 |
| **Celdas de baja entropía** | columnas con < 5 % de valores distintos | 5 de 8 | 0 |
| **Scroll hasta el objeto** | pantallas antes de lo que da nombre a la página | Presupuesto **2.8** | < 0.5 |

Son cuatro números que se pueden poner en una prueba y que fallan en verde o
rojo. Es lo que le faltaba a la auditoría anterior para no repetirse.

---

## 7. Base de evidencia

`principios-de-interfaz.md` ya carga la evidencia sobre alarmas, incertidumbre,
confianza en la IA, listas de verificación y baja prevalencia. Esta auditoría
usa cinco hilos que **no** están ahí todavía, porque son específicos del
problema de *ruido* y no del de *severidad*.

**Advertencia de método, con el mismo estándar que el documento madre:** las
fuentes de abajo se verificaron en esta sesión al nivel de resumen y ficha, no
leyendo el PDF primario completo. Sirven como puntero y como marco; **antes de
que cualquiera de ellas entre a `principios-de-interfaz.md` como regla, hay que
leer el original**, que es como se escribió el resto de ese documento.

### 7.1 El ruido se puede medir

Rosenholtz, Li y Nakano, *Measuring visual clutter* (Journal of Vision, 2007):
proponen **feature congestion** y **subband entropy** como medidas de desorden
visual, con la intuición de que una pantalla está tan desordenada como difícil
sea meterle un elemento nuevo que llame la atención de forma confiable. Se usan
como sustituto del tamaño del conjunto en modelos de búsqueda visual y
correlacionan con el desempeño de búsqueda.

Lo que aporta: **«ruido» deja de ser una queja estética.** La variabilidad de
color y de textura tiene un costo medible sobre la capacidad de encontrar algo.
De ahí la métrica de la sección 6 y de ahí que 470 controles y 163 insignias no
sean neutrales aunque cada uno, por separado, esté bien diseñado.

### 7.2 La coherencia entre pantallas es un recurso

Woods, *Visual Momentum* (1984), y *Visual momentum redux* (IJHCS, 2012): el
*momentum visual* es la medida en que una interfaz sostiene al usuario cuando
pasa de una actividad de búsqueda de información a otra. Requiere acoplamientos
cognitivos en tres niveles: entre pantallas, dentro de una pantalla y dentro de
un elemento. El **efecto mirilla** (Woods, 1995) describe lo que pasa cuando el
espacio de información es mucho mayor que la ventana disponible.

Lo que aporta: nombre y estatus para el mecanismo M6. Klave tiene 17 pantallas
sobre un mismo objeto; que el plazo diga 393 en una y 458 en otra **no es un
detalle de copy**, es pérdida de momentum, y se paga cada vez que alguien cambia
de pantalla.

### 7.3 La ayuda del novato es ruido del experto

Kalyuga, Ayres, Chandler y Sweller — **efecto de reversión por experiencia**: la
guía instruccional que es esencial para el novato tiene consecuencias negativas
para quien ya tiene el conocimiento. El mecanismo es de carga: el experto debe
reconciliar una fuente externa con una estructura interna que ya la contiene, y
eso **agrega** carga de memoria de trabajo en vez de reducirla. Emparejado con
el **efecto de redundancia** de Sweller: dos presentaciones de lo mismo cuestan
más que una.

Lo que aporta: la justificación de M5, y una regla que no es «escribir menos»
sino **«escribirlo una vez y luego colapsarlo»**. También explica por qué la
solución no es borrar el párrafo del lote de revisión: para el ingeniero que lo
ve por primera vez, ese párrafo es lo que hace legítima la pantalla.

### 7.4 Listar más no discrimina mejor

Teoría de detección de señales: separa la **sensibilidad** (d′, qué tan bien se
distingue señal de ruido) del **criterio** (cuánta evidencia se exige antes de
decir «sí»). Bajar el criterio sube los aciertos **y** las falsas alarmas a la
vez; solo un aumento de d′ mejora de verdad. Y el **decremento de vigilancia**
dice que la tasa de aciertos cae con el tiempo en tarea.

Lo que aporta: el enunciado riguroso de la queja del usuario. **Dibujar 163
tarjetas en vez de 4 no sube d′: mueve el criterio.** Se «reportan» más cosas y
se detectan proporcionalmente más falsas alarmas, sin que nadie distinga mejor
un problema real de uno inventado. Lo que sí sube d′ es agrupar, poner
denominador, poner dinero y poner el recorte de la hoja — que es exactamente lo
que ya hace el Diagnóstico y no hace Riesgos.

Es también el argumento contra la salida fácil: **filtrar por severidad no
arregla nada**, porque el eje de severidad es justo el que el principio 8 ya
declara poco confiable.

### 7.5 El lado del oficio

Olly Rosewell, *How I Design SaaS That Looks EXPENSIVE (beginner friendly / UI
guide)*, YouTube, ago-2026 (28:37) —
[9d5fRVDkzRI](https://www.youtube.com/watch?v=9d5fRVDkzRI).

No es investigación ni es sobre herramientas de peritaje: es un video de oficio
para gente que construye SaaS con IA. Se cita por dos razones — aporta
**vocabulario accionable** y **converge de forma independiente** con lo
académico de arriba, desde una tradición distinta.

Lo que dice, y que da directo al hueso de esta auditoría:

- **«La IA es peor en componentes densos y repetidos. Una lista de tarjetas es
  donde vuelca cada botón, chip y marca de tiempo que se le ocurre, todos con el
  mismo peso visual.»** Es una descripción literal de la pantalla de Riesgos:
  163 tarjetas con título + descripción + enlace + acción + método + confianza +
  conteo de relacionados, todas con el mismo peso.
- **«Haz una pasada de compresión… La misma información, un tercio del ruido.»**
  Es el nombre que le faltaba a las direcciones P1-6 y P0-2. *Pasada de
  compresión* es una tarea que se puede pedir; «mejorar la jerarquía» no.
- **«La IA decora. Tu trabajo es informar.»** Con la prueba: *¿esto ayuda al
  usuario a terminar el trabajo por el que vino? Si no, es decoración.*
  Aplicada a Klave, esa prueba tumba `Confianza 100%`, `0 meses`, los 111 chips
  de entidades y los 11 «sin referencia» sin necesidad de más argumento.
  Su lista de síntomas — «**KPIs repetidos, tarjetas sobrecargadas, paneles
  medio vacíos**» — es, uno por uno, M4, M1 y M2.
- **«Cada pantalla es una oración y algo tiene que ser el sujeto. Si todo tiene
  el mismo tamaño y peso, el usuario tiene que leerlo todo para encontrar la
  única cosa que quería.»** El sujeto del Presupuesto debería ser $1,005,983;
  hoy pesa lo mismo que `AIR-005`, 4 PZA.
- **«Deja que tus datos carguen el color.»** Klave ya eligió una identidad casi
  monocroma con un solo acento — y luego puso el color en el *cromo*: insignias
  de severidad en 163 tarjetas, `CRÍTICA` en 27 de 30 barras, `0 meses` en 73
  renglones. El color está donde no hay información y falta donde sí la hay.
- **«Un indicador de progreso para cualquier cosa que pase de un segundo.»**
  Klave ya tiene esqueletos, que resuelven el primer segundo. No resuelven 29.6.
- **«Algunos botones deben ser difíciles de presionar»** (fricción ética,
  efecto Zeigarnik, confirmar-luego-completar). Esto **ya está hecho** en Klave
  y coincide palabra por palabra con la doctrina de fricción del taller.

**Dónde no transfiere, y hay que decirlo:**

- *«Convierte los chips de texto en iconos»* funciona en tarjetas de consumo y
  **es una regresión aquí**: Franconeri et al. miden mejor desempeño con
  etiquetas directas que con leyendas, y el principio 15 ya prohíbe que la
  severidad la cargue el color solo. En Klave se comprime **quitando
  repeticiones**, no quitando palabras.
- *«La velocidad percibida es casi todo»* aplica a esperas de segundos. Una
  espera de 30 s en `/revision` no se arregla con percepción; se arregla en el
  servidor.
- El video optimiza que un producto **parezca** caro. Klave optimiza que una
  cifra **sea** defendible ante un perito. Cuando choquen, gana el documento de
  principios.

---

## 8. Cómo se usa esta auditoría

- **Al agregar una tarjeta, insignia, columna o métrica:** pasar la prueba del
  video — *¿ayuda a terminar el trabajo por el que vino?* — y las cuatro
  métricas de la sección 6.
- **Al agregar un hallazgo:** agruparlo por causa antes de dibujarlo, con
  denominador, con dinero o exposición física, y decidir si invalida a otros.
- **Al escribir una explicación:** escribirla una vez y colapsarla después.
- **Al mostrar un número que también vive en otra pantalla:** o es el mismo
  número, o lleva su calificador en las dos.

Ver también: [principios-de-interfaz.md](principios-de-interfaz.md) ·
[auditoria-ui.md](auditoria-ui.md) · [plan-de-pulido.md](plan-de-pulido.md)
