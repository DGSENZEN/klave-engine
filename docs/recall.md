# Medir cuánto ve el motor

El gold set compara al motor contra sí mismo: fija lo que detectó ayer para
que no se rompa hoy. Eso protege contra regresiones y **no dice nada** sobre
la pregunta que decide si Klave sirve:

> De todo lo que está dibujado en el plano, ¿qué fracción encuentra?

Esa pregunta solo la contesta una persona contando. No hay atajo: si el motor
pudiera contar lo que se le escapa, no se le escaparía.

## El procedimiento

```bash
uv run python -m klave_engine.evals.recall_cli plantilla <project_id>
```

Escribe `evals/conteos/<project_id>.json` con las familias que el motor sí
detectó, todas en cero. Entonces alguien abre el plano y cuenta.

**Lo importante es agregar las familias que no están en la plantilla.** Una
familia que el motor no detectó *en absoluto* no aparece en el archivo, y es
justo la que más caro cuesta descubrir tarde. Si el plano tiene escaleras y
la plantilla no las menciona, ese renglón lo escribes tú con su cuenta.

```bash
uv run python -m klave_engine.evals.recall_cli medir <project_id>
```

## Cómo leer el reporte

```
familia          dibujados detectados  recall         IC 95%       importe
trabe                   40         31    0.78    0.63–0.88     $313,231  ← revisar
castillo               120        118    0.98    0.94–1.00     $208,900
escalera                 2          0    0.00    0.00–0.66      $14,300  ← revisar
```

Tres cosas que el reporte hace a propósito:

**Por familia, no en global.** Un 90 % que esconde un 40 % en zapatas no
informa nada.

**Con intervalo.** Con quince elementos contados, un recall de 0.87 no
distingue entre 0.6 y 0.98. El intervalo de Wilson lo dice para que nadie lea
precisión donde solo hay una muestra chica. Si el intervalo sale ancho, la
respuesta no es creerle al centro: es contar más obras.

**Pesado por dinero.** El *recall ponderado* pesa cada familia por el importe
que representa en el presupuesto. Perder una trabe cuesta más que perder un
eje, y una media simple deja que cien ejes bien detectados tapen diez trabes
perdidas. Ese es el número que decide dónde invertir en detección.

`dinero que el motor no vio` estima, con el promedio de la familia, cuánto
importe representan los elementos faltantes. Es aproximado por construcción y
se rotula así.

## Qué se hace con el resultado

- Recall bajo en una familia cara → ahí va el siguiente detector.
- Recall alto con intervalo ancho → falta muestra; corre más obras.
- Sobrantes altos → probable doble conteo entre vistas, que infla el
  presupuesto en vez de encogerlo. También cuesta dinero.

## La muestra que hace falta

Dos familias de dibujo (PRUEBA-1 y Marina) no sostienen ninguna afirmación
sobre planos de otros despachos. Para poder decir "Klave encuentra el 90 % de
lo que está dibujado" hacen falta **quince o veinte obras de despachos
distintos**, contadas por alguien que sepa leer un plano. Hasta entonces, lo
honesto es decir que no se sabe.

Ver también: [evals.md](evals.md) · [lectura-ia.md](lectura-ia.md)
