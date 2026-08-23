# Conceptos del taller (alias) y coincidencias con tu catálogo

Klave lee el plano con sus propios conceptos (EST-004 "Muros de block…").
Tu taller los llama de otra forma, con su clave, su descripción y su precio.
El alias es esa traducción, hecha una vez y recordada para todos los
proyectos.

## Qué es un alias

Un alias liga un concepto de Klave a:

- **una fila de tu catálogo** (o de un tabulador): la clave, la descripción y
  el P.U. de esa fila sustituyen a los nuestros; el precio queda adoptado
  con su fuente y vigencia, o
- **un concepto de tu taller** (creado a mano o importado con su matriz desde
  OPUS/Neodata): su matriz pone el precio; su clave y descripción van en la
  línea.

El alias es del taller, no del proyecto: se aplica a cada presupuesto desde
que se decide, y guarda quién lo decidió, en qué proyecto y con qué nota.
Quitarlo regresa al concepto y a la matriz de Klave.

Dónde se ve:

- En el presupuesto, la columna Clave muestra tu clave y, debajo, la de Klave.
- En todas las exportaciones (Excel completo, OPUS, Neodata, licitación) la
  clave es la tuya.
- En el APU, `price_source` dice "matriz del taller ALB-010" o la fila y
  fuente adoptadas.

## Coincidencias (matching)

`GET /catalog/concepts/{code}/matches` ordena tu catálogo contra un
concepto; `GET /catalog/matches?min_score=0.8` devuelve la mejor
coincidencia de cada concepto sin alias (la barra "N conceptos coinciden
con tu catálogo" del presupuesto). Cada coincidencia trae su puntaje y
sus razones:

- la unidad tiene que coincidir (M2 nunca empata con M3);
- las palabras en común, sin las de relleno, pesan más;
- el **sustantivo principal** manda: "muro … con aplanado" es un muro, no un
  aplanado;
- las especificaciones deciden: f'c, sección (15x20), espesor (10 cm) iguales
  suman; distintos restan fuerte;
- demolición, retiro, renta o flete de la cosa no es la cosa;
- misma partida suma un poco.

0.8 o más es "lo mismo dicho de otra forma"; entre 0.5 y 0.8 vale la pena
mirar; abajo de 0.5 es ruido. Nada se adopta solo: "Adoptar N" lo hace el
ingeniero, y cada alias lleva la nota "sugerido (NN %)".

## Flujo en el presupuesto

1. La barra de coincidencias ofrece las de ≥ 80 %: Revisar (una por una,
   Usar u Omitir) o Adoptar todas.
2. En cualquier línea, "Concepto del taller → elegir de mi catálogo" abre el
   selector: coincidencias ordenadas con razones y precio, y una búsqueda
   sobre todo el catálogo filtrada por la unidad de la línea.
3. Al guardar, el proyecto se recalcula de inmediato; los demás proyectos lo
   toman en su siguiente recálculo.

## Límites honestos

- El matcher es léxico; no entiende sinónimos que no compartan palabras
  ("tabique" vs "ladrillo") ni marcas. Para eso está la búsqueda.
- Un concepto de Klave sin espesor en su descripción empata igual con las
  variantes de 12 y 15 cm de tu catálogo: la nota del plano (espesor de muro
  leído) es la que debe decidir; hoy la decide el ingeniero en el selector.
