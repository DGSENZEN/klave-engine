# Principios de interfaz de Klave

Klave muestra miles de datos a un profesional que va a firmar con su cédula
lo que la pantalla dice. Eso descarta casi todo el manual de diseño de
aplicaciones de consumo: aquí no se optimiza el deleite ni el número de
clics, se optimiza **que la decisión correcta sea la fácil y que la
incorrecta sea visible**.

Tres pilares, en orden de precedencia. Cuando choquen, gana el de más
arriba.

1. **Honestidad** — la pantalla dice lo que sabe, lo que no sabe y qué tan
   seguro está. Nunca se ve mejor de lo que es.
2. **Severidad** — lo que puede costar dinero se distingue de lo que no, y
   se distingue *antes* de que el usuario tenga que leerlo todo.
3. **Legibilidad** — el que lee llega a la decisión sin cruzar referencias
   entre tres pantallas.

Este documento es la regla escrita. Un hallazgo, una advertencia o una
pantalla nueva se diseña contra esta lista, no contra el gusto de quien la
escribe. Las afirmaciones llevan su fuente; donde la evidencia está
peleada, lo decimos.

---

## I. Honestidad

### 1. Lo que no se sabe no se rellena

Un precio ausente sale como «sin precio», nunca como `$0`. Un plano sin
unidad confiable no produce precios, produce cantidades en unidades de
dibujo y lo dice. Un total que esconde huecos es peor que un total
incompleto que los enseña.

Esto no es escrúpulo: es la única defensa cuando el motor se equivoca.
Joslyn y LeClerc midieron que declarar la incertidumbre **aumenta** la
confianza del usuario y —lo importante— **amortigua el daño a esa
confianza el día que el pronóstico falla**
([JEP:Applied 2012](https://www.apa.org/pubs/journals/features/xap-18-1-126.pdf)).
Decir «sin precio» es un seguro, no un costo.

Vale la pena saber contra qué se está peleando: Hullman encuestó a 90
autores de visualizaciones y encontró que omiten la incertidumbre **a
propósito**, porque mostrarla «reduce los grados de libertad» con que el
lector interpreta el dato — es decir, esconderla es retóricamente útil
([TVCG 2020](https://arxiv.org/abs/1908.01697)). La tentación es la norma
profesional. Por eso está escrita como regla.

### 2. Un número de confianza solo se muestra si está calibrado

Mostrar «87 %» junto a una detección afirma que 87 de cada 100 lecturas
así son correctas. La confianza de Klave es un puntaje heurístico, no una
probabilidad medida: presentarlo como porcentaje es una mentira con
decimales.

La evidencia tampoco lo respalda como palanca de decisión. Zhang, Liao y
Bellamy encontraron que el puntaje de confianza *calibra la confianza del
usuario* pero **no basta para mejorar la decisión conjunta**
([FAT\* 2020](https://arxiv.org/abs/2001.02114)); Rechkemmer y Yin
encontraron que la confianza declarada mueve *la creencia* sobre la
exactitud, mientras que la exactitud **observada** es la que mueve la
conducta ([CHI 2022](https://mingyin.org/paper/CHI-22/multiple-camera.pdf)).

Reglas que salen de ahí:

- La confianza se usa **por dentro, para dirigir la atención** (ordenar,
  agrupar, poner primero lo dudoso), no por fuera como estampa.
- Donde haya que resumir calidad, se pesa **dinero, no elementos**. El
  presupuesto muestra «importe en lecturas firmes», no «confianza
  promedio»: un promedio simple deja que cien tornillos seguros tapen una
  trabe dudosa.
- Cuando la IA exprese duda, que la exprese **en primera persona** («no
  estoy seguro de esta especificación»). Kim et al. midieron, con 404
  participantes preregistrados, que la duda en primera persona **redujo la
  sobreconfianza en respuestas incorrectas y mejoró la exactitud**,
  mientras que la formulación impersonal («no está claro») no alcanzó
  significancia ([FAccT 2024](https://arxiv.org/abs/2405.00623)).

### 3. La procedencia es un recorte de la hoja, no un párrafo

Aquí está el hallazgo más incómodo de toda la investigación, y hay que
mirarlo de frente: **las explicaciones aumentan la aceptación de lo que
dice la máquina, sea correcto o no**. Bansal et al., textual: las mejoras
«no aumentaron con las explicaciones; más bien, las explicaciones
aumentaron la probabilidad de que el humano acepte la recomendación de la
IA, independientemente de si era correcta»
([CHI 2021](https://arxiv.org/abs/2006.14779)). Eiband et al. fueron más
lejos: explicaciones **vacías de contenido** producen casi la misma
confianza que las reales ([CHI EA 2019](https://dl.acm.org/doi/10.1145/3290607.3312787)).

La salida existe y es específica: las explicaciones sí funcionan cuando
**abaratan la verificación**. Vasconcelos et al. mostraron con 731
participantes que la sobreconfianza sube y baja con el *costo* de
verificar — es una decisión económica, no un sesgo inevitable
([CSCW 2023](https://arxiv.org/abs/2212.06823)); Fok y Weld argumentan que
las explicaciones ayudan solo en la medida en que permiten verificar, y
que «la mayoría de las tareas no permiten verificación fácil»
([arXiv 2023](https://arxiv.org/abs/2305.07722)).

**Klave está en el caso raro donde sí se puede.** Un croquis recortado de
la hoja exacta de donde salió la cantidad se comprueba en segundos. Por eso:

- Una lectura de IA se presenta con **el recorte de la hoja**, no con una
  narración de por qué el modelo cree lo que cree. La narración es lo que
  la literatura llama explicación placebo.
- El tiempo que cuesta verificar es una métrica de producto, no un
  detalle. Si confirmar una lectura toma más de unos segundos, se deja de
  confirmar, y ninguna redacción lo arregla.

### 4. La verificación es desafío-respuesta, no una palomita

Una casilla se marca sin mirar; por lo tanto se marcará sin mirar. La
aviación resolvió esto hace décadas distinguiendo la lista *read-do* (para
ejecutar un procedimiento) de la lista *challenge–response* (para
**verificar** que algo ya está bien): uno nombra el ítem, otro confirma el
estado observado (Degani y Wiener,
[Human Factors 1993](https://journals.sagepub.com/doi/10.1177/001872089303500209)).

Los tres pasos de Klave se redactan así: «Unidades: el motor leyó metros.
¿Coincide con el plano?», con la evidencia al lado — nunca «☐ Revisé las
unidades», que es infalsificable y por construcción se vuelve rito.

Y conviene no ser ingenuos sobre las listas de verificación. La lista
quirúrgica de la OMS bajó la mortalidad de 1.5 % a 0.8 % en el estudio de
Haynes ([NEJM 2009](https://www.nejm.org/doi/full/10.1056/NEJMsa0810119)),
pero cuando Ontario la volvió obligatoria en 101 hospitales y ~216 000
procedimientos, **ningún hospital mostró una reducción significativa**
([Urbach, NEJM 2014](https://www.nejm.org/doi/full/10.1056/NEJMsa1308261)).
El ingrediente activo no era la lista: Dixon-Woods atribuye el éxito de
Michigan a la **rendición de cuentas, la comunidad y la retroalimentación
de datos a quien hace el trabajo**
([Milbank 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3142336/)).

De ahí dos consecuencias para Klave: la firma nombra a la persona y lo que
está certificando (Skitka et al. midieron que la **responsabilidad
pre-decisional** reduce errores de omisión y de comisión), y las
correcciones del ingeniero se le devuelven visibles — «tus verificaciones
corrigieron 12 lecturas este mes» — porque eso es lo que convierte un
trámite en un instrumento profesional.

### 5. El sello no puede estar en todas partes

«SIN VERIFICAR» en todo, siempre, no se lee. Anderson et al. midieron con
resonancia que la respuesta visual a una advertencia **idéntica se
desploma a partir de la segunda exposición**, y que las advertencias
*polimórficas* —que cambian de forma— resisten la habituación
([CHI 2015](https://dl.acm.org/doi/10.1145/2702123.2702322)). En sistemas
clínicos, las alertas se ignoran entre el 49 % y el 96 % de las veces
(van der Sijs et al., [JAMIA 2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC1447540/)).

Regla: el estado pasivo (el sello) se queda; **lo interruptivo se reserva
para lo que de verdad bloquea**, y su contenido cambia nombrando el ítem
concreto en riesgo. Una advertencia que dice algo nuevo es una advertencia
que se lee.

---

## II. Severidad

### 6. Cuatro canales, tres de ellos alarmas

Klave clasifica todo hallazgo antes de mostrarlo, como una *filosofía de
alarmas* racionaliza una alarma (ANSI/ISA-18.2, EEMUA 191). La prueba de
validez es la de Rockwell, literal: si no hay consecuencia, no amerita
alarma; **si no hay acción correctiva enunciada, no amerita alarma**; y
reconocer la alerta no es una acción
([Rockwell PROCES-WP015](https://literature.rockwellautomation.com/idc/groups/literature/documents/wp/proces-wp015_-en-p.pdf)).

| Canal | Significa | Comportamiento |
|---|---|---|
| **Bloqueante** | Entregarlo así estaría mal: el total no es un precio, o el presupuesto contradice al plano que dice leer | **Rehúsa la exportación.** Pasar exige un motivo escrito, que queda impreso en la carátula |
| **Dinero faltante** | Hay cantidad real sin costo: el total está subestimado en una cantidad que desde aquí no se puede saber | Agrupado por causa, ordenado por pesos |
| **Por revisar** | Falta una decisión humana; el número se sostiene sin ella | Listado, accionable, no bloquea |
| **Criterios adoptados** | Una decisión deliberada del motor | **No es alarma**: no pide nada. Va al registro de supuestos |

El cuarto canal es el que más cuesta aceptar y el más importante. Una nota
como «la losa de vigueta no lleva cimbra de contacto» no pide nada al
lector: por la prueba de validez **no es una alarma**, y mantenerla en la
lista diluye a las tres de arriba. No se borra —es justo lo que defiende
el número meses después— se muda al registro de supuestos.

La cifra que justifica todo esto: en sistemas clínicos se estima que
**entre 85 % y 99 % de las alertas no requieren intervención**, y el
resultado documentado es que el personal «se desensibiliza o se vuelve
inmune»
([Joint Commission, Sentinel Event Alert 50](https://www.jointcommission.org/en-us/knowledge-library/newsletters/sentinel-event-alert/issue-50)).
Esa misma alerta reporta 98 eventos centinela relacionados con alarmas
entre 2009 y 2012, **80 de ellos con muerte**. Las apuestas de Klave son
dinero, no vidas; el mecanismo de falla es idéntico.

### 7. Nunca un hallazgo por renglón

Seis conceptos con el f'c equivocado son **una** decisión y se muestran
como un hallazgo que carga el millón de pesos completo. La gestión de
alarmas define inundación en **10 alarmas en 10 minutos**, y grave arriba
de 30, con la observación de que «durante esos periodos es probable que se
pierdan alarmas»
([Emerson/ISA](https://isa.ie/wp-content/uploads/2016/06/Alarm_System_Performance_Metrics_Kim_Van_camp.pdf)).
Graham y Cvach lograron una reducción del **43 %** en alarmas de alta
prioridad principalmente **eliminando duplicados**, no reordenándolos.

Corolario: todo grupo lleva denominador. «40 de 277 marcas de trabe sin
sección» dice algo; «40 marcas sin sección» no.

### 8. La categoría nunca sustituye al número

Las matrices de riesgo tienen un defecto documentado: Cox mostró que
resuelven correctamente **menos del 10 %** de los pares de riesgos, que
comprimen rangos, y que con frecuencia y severidad correlacionadas
negativamente son «peores que inútiles»
([Risk Analysis 2008](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1539-6924.2008.01030.x)).
Thomas, Bratvold y Bickel añaden el sesgo de centrado —Hubbard encontró
que **75 % de los puntajes elegidos caen en 3 o 4** de una escala de 5— y
la inversión de rangos según la convención de puntaje
([SPE 2014](https://maverisk.nl/wp-content/uploads/TheRiskofUsingRiskMatrices.pdf)).

Por eso en Klave la categoría **acompaña** al número y nunca lo reemplaza:
el orden dentro de cada nivel son pesos, y los pesos se ven en la fila. Y
por eso **no hay eje de probabilidad**: no tenemos una frecuencia medida
que poner ahí, y adivinarla es exactamente el caso donde Cox mide que la
matriz empeora las decisiones.

### 9. Cada hallazgo dice cuándo deja de ser barato

La prioridad en ISA-18.2 es bidimensional: consecuencia **×** tiempo de
respuesta. El análogo en costos no es el reloj, es la etapa: *antes de
entregar*, *antes de cotizar*, *antes de contratar*. Arreglar un f'c antes
de cotizar cuesta trabajo; después de contratar cuesta una orden de
cambio. Esa etiqueta es lo que permite triar sin leerlo todo.

### 10. Un bloqueo se bloquea; no se pinta de rojo

Akhawe y Felt midieron 25 millones de impresiones de advertencias de
navegador: la misma advertencia de SSL tuvo **33 % de click-through en
Firefox y 70.2 % en Chrome** — el doble, por diseño de la interfaz, no por
el contenido ([USENIX Security 2013](https://research.google/pubs/pub41323)).
Felt et al. después recuperaron ~30 % más de usuarios seguros **sin lograr
que entendieran mejor la advertencia**, solo con diseño opinionado: la
opción segura como botón, la insegura como texto gris detrás de un clic
más ([CHI 2015](https://dl.acm.org/doi/10.1145/2702123.2702442)).

Por eso un hallazgo bloqueante en Klave **detiene el archivo**. El camino
para pasar es escribir por qué, y lo escrito viaja dentro del Excel: quien
lo recibe se entera por el archivo, no por quien se lo mandó.

### 11. Lo que nadie atiende se mide y se degrada

Google define falso positivo de manera conductual: un hallazgo es
«efectivamente falso positivo» **si el desarrollador no hizo nada después
de verlo**, sea técnicamente correcto o no. Exigen menos del 10 % para
mostrar un análisis en revisión de código y operan por debajo del 5 %
([Software Engineering at Google, cap. 20](https://abseil.io/resources/swe-book/html/ch20.html)).

Klave debe instrumentar lo mismo por *tipo* de hallazgo y degradar los que
pasen el umbral. La distribución objetivo también está publicada:
80 % baja / 15 % media / 5 % alta. La realidad de la industria cuando
nadie la vigila es 25/40/35 — y un 35 % de «alta prioridad» es lo mismo
que no tener prioridades ([Honeywell](https://process.honeywell.com/content/dam/process/en/documents/document-lists/honeywell_enhanced-a.pdf)).

*(Pendiente de implementar: telemetría por tipo de hallazgo y control «no
me sirve». Está aquí porque la regla se decide antes que el código.)*

---

## III. Legibilidad

### 12. Panorama primero; y el panorama es el filtro

«Overview first, zoom and filter, then details-on-demand» (Shneiderman,
[1996](https://www.cs.umd.edu/~ben/papers/Shneiderman1996eyes.pdf)). La
pantalla de revisión no puede empezar en el detalle de 2 000 renglones.
Empieza en la distribución —por estado, por confianza, por planta— y esa
distribución **es** el control de filtrado, no un adorno encima de él.

De las siete tareas de Shneiderman, las dos que Klave más descuida son
*History* (qué confirmó o excluyó alguien, y poder revertirlo) y *Extract*
(exportar el subconjunto filtrado **con sus parámetros de filtro**). Son
justo las que necesita un perito que defiende un presupuesto seis meses
después.

### 13. Cada renglón carga su propio contexto

La queja original —«hay que escarbar para tener contexto legible»— tiene
nombre técnico: **falta de rastro de información** (Pirolli y Card,
[1999](https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/280uir-1999-05-pirolli.pdf)).
Un renglón que no permite predecir qué hay detrás obliga a abrirlo, y
abrirlo es lo que destruye la economía de la revisión.

Y es una economía real: Papadopoulos et al. midieron que **verificar es de
6 a 9 veces más barato que crear** ([CVPR 2016](https://arxiv.org/abs/1602.08405)).
Ese factor se pierde íntegro en el momento en que el revisor tiene que
navegar para decidir. La prueba de aceptación es concreta: **toma 20
renglones al azar; el veredicto debe ser el mismo leyendo solo el renglón
que leyendo el renglón más su panel de detalle.**

### 14. Lo que hay que integrar mentalmente va junto físicamente

El *efecto de atención dividida*: separar dos fuentes que solo se entienden
juntas impone carga extraneosa (Chandler y Sweller,
[1992](https://bpspsychub.onlinelibrary.wiley.com/doi/abs/10.1111/j.2044-8279.1992.tb01017.x)).
La cantidad de una línea, las detecciones que la produjeron, sus supuestos
y sus advertencias son mutuamente ininteligibles por separado. Repartirlas
entre una tabla, un cajón lateral y un panel de advertencias al pie es el
caso de manual.

Regla: la advertencia de la línea *N* se dibuja dentro de la línea *N*.

### 15. Etiquetas directas, no leyendas

Franconeri et al., revisión par-evaluada: la gente responde **más rápido y
con más exactitud** con datos etiquetados directamente que con leyenda, y
recomiendan «convertir leyendas en etiquetas directas»
([PSPI 2021](https://journals.sagepub.com/doi/full/10.1177/15291006211051956)).
El mismo trabajo mide que **comparar subconjuntos corre a dos o tres
comparaciones por segundo**: una pantalla que exige comparar 2 000
renglones entre sí es aritméticamente imposible, y el software tiene que
precomputar la comparación y mostrar la diferencia.

De ahí también: la severidad nunca la carga el color solo. Cada nivel dice
su nombre y muestra su ícono.

### 16. Dos niveles de revelación, no tres

Nielsen: más de dos niveles de revelación progresiva «típicamente tienen
baja usabilidad porque los usuarios se pierden»
([NN/g 2006](https://www.nngroup.com/articles/progressive-disclosure/)).
Renglón → detalle. Nunca renglón → detalle → subpanel.

Y el control de revelación dice lo que hay dentro («3 detecciones, 2
supuestos»), nunca «Ver más». La guía #7 de NN/g para aplicaciones
complejas dice lo mismo por el otro lado: permitir ver información
suplementaria **sin salir de la pantalla principal**
([NN/g 2020](https://www.nngroup.com/articles/complex-application-design/)).

### 17. Una cola plana de 2 000 elementos está rota

Este es el hallazgo que más obliga a rediseñar, y no es intuitivo.

Wolfe, Horowitz y Kenner midieron el **efecto de baja prevalencia**: con
50 % de objetivos presentes la gente falla el 7 %; con 10 %, el 16 %; con
**1 %, el 30 %** — un aumento de cuatro veces solo por cambiar la
frecuencia ([Nature 2005](https://www.nature.com/articles/435439a)). Peor:
al mezclar prevalencias en la misma tarea, los objetivos raros empeoran —
**52 % de fallos** en los muy raros. El mecanismo es que la búsqueda sin
objetivo termina demasiado pronto. Y es resistente a advertirle al
participante de antemano.

Si el detector acierta el 95 %, entonces ~5 % de los renglones están mal:
**ese es exactamente el régimen de baja prevalencia**. Un ingeniero
revisando 2 000 renglones parejos se le va a pasar cerca de la mitad de
los errores reales, y no por descuido — por cómo funciona la búsqueda
visual humana.

Consecuencias, no negociables:

- No ofrecer «revisar todo» sobre el conjunto completo como camino
  principal.
- **Subir la prevalencia efectiva**: agrupar en lotes donde lo sospechoso
  esté denso (dudas, confianza baja, cobertura marcada, paramétricos),
  y decirlo con todas sus letras.
- Cuidado con los atajos que permiten decir «todo bien» rápido sobre una
  pantalla de poca señal: aceleran justo el mecanismo que causa los
  fallos.
- Para el resto, muestreo y auditoría — no la ficción de una revisión
  exhaustiva.

Un contrapeso honesto: Bajpai y Chandrasekharan encuestaron a 106
moderadores y encontraron que **prefieren señales visuales en línea antes
que filtros** (74.5 %) y que 94 de 106 quieren ver *todo* por defecto
([2025](https://arxiv.org/html/2409.16840)). Los profesionales rankean
exactitud (μ=4.35) muy por encima de eficiencia (μ=2.10). Así que el lote
de alta prevalencia se ofrece y se explica, pero **no se esconde nada**:
quien quiera ver los 2 000, los ve.

---

## IV. Lo que este documento rechaza

Cosas que suenan a buen diseño y no lo son. Están aquí para que nadie las
proponga otra vez sin evidencia nueva.

| Idea | Por qué no |
|---|---|
| «Limitar las opciones a 7±2» | Miller llamó al número siete «una coincidencia pitagórica perniciosa» y advirtió explícitamente contra confundir sus tres medidas — «un error fundamental», textual ([1956](https://psychclassics.yorku.ca/Miller/)). Cowan sitúa el límite real en ~4 fragmentos y solo cuando se bloquean el agrupamiento y el repaso ([2001](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/44023F1147D4A1D44BDC0AD226838496/S0140525X01003922a.pdf)). Nada de eso aplica a cosas **visibles en pantalla**, donde reconocer sustituye a recordar. Una tabla puede tener 80 renglones. |
| «Todo a tres clics» | NN/g: la regla «no ha sido respaldada por datos en ningún estudio publicado». Lo que hace abandonar no es el número de clics, es el rastro débil ([NN/g](https://www.nngroup.com/articles/3-click-rule/)). Se optimizan clics **predecibles**, no pocos. |
| «Maximizar la razón dato-tinta» | Franconeri et al.: la definición de «tinta» es «frustrantemente vaga», la evidencia de preferencia se contradice, y quitar unos elementos acelera mientras quitar otros retrasa. Heurística estética, no ley. En una tabla que alguien va a barrer 40 minutos, los separadores están trabajando. |
| Quitar toda decoración por «chartjunk» | Mismo trabajo: los adornos **relacionados con el dato** pueden mejorar memoria y enganche. La literatura está dividida, no cerrada. |
| Mostrar «87 %» junto a cada detección | Ver principio 2. Sin calibración medida, es una mentira con decimales. |
| Explicar en prosa por qué la IA leyó lo que leyó | Ver principio 3: aumenta la aceptación sin aumentar el acierto, y una explicación vacía funciona casi igual. Va el recorte de la hoja. |
| Pre-llenar el presupuesto con lo que propone la IA y dejar que el ingeniero corrija | Green y Chen, N=2 140: presentar la evaluación algorítmica **cambió cómo la gente pondera valores** y esos corrimientos **cancelaron** la ganancia de exactitud ([CSCW 2021](https://dl.acm.org/doi/10.1145/3479562)). Un campo pre-llenado es el ancla más fuerte que se puede construir. |
| «Que el ingeniero decida primero y luego vea la IA» | Suena obvio y la evidencia está **peleada**. Buçinca et al. midieron que forzar el compromiso reduce la sobreconfianza ([CSCW 2021](https://arxiv.org/abs/2102.09692)); Fogliato et al., con 19 radiólogos reales, encontraron que decidir primero los hizo **menos propensos a estar de acuerdo con la IA tuviera o no razón**, y consultar menos a colegas ([FAccT 2022](https://arxiv.org/abs/2205.09696)). Su población se parece más a nuestros ingenieros. Se prueba con bandera, no se asume. |

---

## V. Cómo se usa esta lista

- **Al escribir un hallazgo nuevo:** el tipo se registra con causa,
  consecuencia, cómo comprobarlo, acción, momento límite y nivel. Si no se
  puede escribir la acción, no es un hallazgo (principio 6). El nivel se
  decide contra esta regla escrita, nunca al vuelo por quien agrega el
  check — que es justo lo que Cox mide que produce calificaciones opuestas
  para el mismo riesgo.
- **Al diseñar una pantalla de datos:** panorama primero (12), el renglón
  se basta solo (13), lo relacionado va junto (14), etiquetas directas
  (15), dos niveles (16).
- **Al pedirle algo al usuario:** si es una verificación, es
  desafío-respuesta (4). Si es una revisión masiva, se sube la prevalencia
  (17).
- **Al mostrar algo de la IA:** recorte verificable, duda en primera
  persona, y la confianza dirige la atención en vez de estamparse (2, 3).

### Advertencia honesta sobre estas fuentes

Ninguna es de ingeniería de costos ni de lectura de planos. Vienen de
meteorología, transporte, medicina, justicia penal, aviación, moderación
de contenido y herramientas de desarrollo. La transferencia es plausible
—el perito de Klave se parece más al radiólogo de Fogliato o al piloto de
Skitka que a un participante de laboratorio— pero **es una transferencia,
no un hallazgo**. La telemetría de correcciones del propio Klave será
mejor evidencia sobre Klave que cualquiera de estos artículos.

Ver también: [seguridad.md](seguridad.md) · [lectura-ia.md](lectura-ia.md)
· [cómo funciona](../apps/web/app/como-funciona/page.tsx)
