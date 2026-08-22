# Evaluación del motor

Dos niveles, ambos en `make`:

- `make eval-demo` — la suite sintética (`evals/regression_suite.py`): un plano
  generado con verdad conocida. Debe dar PASS siempre.
- `make eval-gold` — el **gold set** de planos reales (`evals/gold/*.json`).
  Los planos no se versionan; cada entrada guarda el hash de sus archivos y
  se salta con aviso si no están en esta máquina.

## Cómo crece el gold set

Cada entrada nace de un proyecto procesado y **absorbe las revisiones
humanas** del visor: una detección marcada con X sale de las etiquetas
esperadas, una marcada con C queda fijada. El estado dice cuánto confiar:

| estado | significado |
|---|---|
| `baseline` | sin revisiones: protege contra regresiones, no es verdad |
| `partial` | hay revisiones; las excluidas son deuda visible del detector |
| `verified` | el ingeniero firmó el paso de detecciones; se exige F1 = 1 |

```bash
make gold-capture ROOT=data/uploads/<proyecto> ID=<clave-del-plano>
make eval-gold
```

`--fresh` (que `make gold-capture` ya usa) etiqueta con una corrida del motor
actual, para que la base nunca quede atrás del parser. Recaptura una entrada
después de revisar detecciones en el visor; el runner falla si una confirmada
desaparece, si una entrada `verified` deja de ser perfecta, o si cualquier tipo
cae por debajo de su F1 base.
