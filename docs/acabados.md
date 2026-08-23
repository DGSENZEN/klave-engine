# Albañilería y acabados leídos de la arquitectura

La planta de arquitectura dibuja los muros como líneas dobles en capas de
muro (`A-WALL`, `MUROS`, `TABIQUE`…) y nombra cada local (RECÁMARA, BAÑO,
COCINA, PATIO…). De ahí salen los acabados.

## Locales

`detection/rooms.py` arma la red de líneas de muro y toma sus caras
cerradas como locales:

- Las dos líneas de cada muro se unen en su extremo (la mocheta) y después
  se cierran los vanos de puerta entre extremos de muro a menos de 1.3 m,
  siempre que el cierre no cruce otro muro. Así un local con puerta cierra.
- Una cara más angosta que 0.7 m es la franja entre las dos líneas de un
  muro, no un local. Una cara que contiene otras caras es el contorno del
  edificio, no un local.
- El texto dentro de la cara nombra el local y dice si es **interior**
  (plafón y piso) o **exterior** (patio, terraza, cochera: firme, sin plafón).
- Una cara con textos estructurales (K-1, DADO, DETALLE, CORTE…) es una caja
  de detalle. Una cara sin nombre y menor de 4 m² es un bolsillo entre muros.
  Una cara sin nombre de 4 m² o más se reporta "sin nombre, uso por
  confirmar" y **no alimenta ningún concepto**: la cantidad nunca se adivina.
- Una hoja que no nombra al menos dos locales interiores distintos no es una
  planta de arquitectura (los juegos estructurales también dibujan A-WALL):
  no se leen locales y la hoja lo dice en sus advertencias.

## Conceptos (catálogo v11)

| Clave | Concepto | Cantidad |
|---|---|---|
| ACA-001 | Aplanado de mezcla en muros, ambas caras | longitud de muros de block × altura de entrepiso de su planta (NTC/NPT) × 2 |
| ACA-002 | Pintura vinílica en muros, ambas caras | igual que ACA-001 |
| ACA-003 | Plafón de yeso | área de locales interiores nombrados, por planta |
| ACA-004 | Pintura en plafones | igual que ACA-003 |
| PIS-001 | Piso de loseta cerámica | área de locales interiores nombrados |
| PIS-002 | Firme de concreto f'c=150 de 10 cm | locales nombrados (interiores y exteriores) de la planta baja, una sola vez |

Los vanos no se descuentan del aplanado y la pintura: el plano no los acota
y el supuesto queda escrito en la línea. El tipo de piso por local viene del
catálogo de acabados del taller (adopta el P.U. del concepto), no del plano.

Los insumos sembrados (pintura, sellador, loseta, adhesivo, yeso, pintor,
yesero) son **de referencia** y así quedan etiquetados; un taller los
sustituye por sus cotizaciones o adopta el P.U. de su catálogo propio.

## Límites honestos

- Marina Lote 04: las hojas de arquitectura llegan como xref que LibreDWG
  no resuelve, así que no hay locales; los muros del estructural sí alimentan
  aplanado y pintura.
- PRUEBA-1: juego estructural con líneas A-WALL pero sin nombres de locales:
  cero locales, por diseño.
