# #NN — Título de la issue

| Campo | Valor |
| --- | --- |
| Issue | #NN |
| Rama | `issue-NN-descripcion-corta` |
| Requisitos | RF-xx, RNF-xx |
| Fecha | DD/MM/AAAA |
| Autor | Nombre |

## Qué se pidió
Qué pedía la issue, en una o dos líneas.

## Qué se hizo
- Archivos creados o modificados, y qué cambió en cada uno.

## Por qué así
- La justificación de cada decisión, con el principio que la guía (YAGNI, DRY, `ub-mode`) o el requisito que cumple.
- **Alternativas descartadas** y por qué.

## Tests
- **Agregados:** `tests/test_xxx.py::test_yyy` — qué comportamiento prueba.
- **Modificados:** cuál y por qué.
- **El test nuevo falló antes del cambio** por esta razón: …
- Si la issue no lleva tests (infraestructura o documentación): la **verificación reproducible**, con los comandos y su salida.

## Verificación
```
$ python3 run_tests.py
...
N tests, todo ok
```

## Pendientes o riesgos detectados
- Lo que quedó fuera a propósito (YAGNI) o lo que se descubrió y merece una issue nueva.
