# #33 — Regla de comentarios en el código

| Campo | Valor |
| --- | --- |
| Issue | #33 |
| Rama | `issue-33-regla-de-comentarios` |
| Requisitos | RNF-04, RNF-10 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Una regla de trabajo para los comentarios:
- en lo que se implemente desde ahora, comentar sólo cuando sea muy necesario o útil;
- no comentar todo, porque cada issue queda documentada;
- dejar como están los comentarios del código existente.

## Qué se hizo
- **`PLAN.md`:**
  - una fila **Comentarios** en los principios (1.1);
  - un punto nuevo en la definición de terminado (1.8);
  - la issue en la sección 10, y calendario y estado actualizados.
- **`REQUISITOS.md`:** **RNF-10**, que remite al plan para el detalle.

## Por qué así
- **El porqué vive en un solo lugar (DRY).** Cada issue deja su justificación en el registro de construcción y en el commit. Repetirla en comentarios crearía una segunda copia que nadie actualiza.
- **Qué cuenta como «imprescindible».** El plan da ejemplos concretos: una restricción externa, un valor que parece arbitrario o una trampa conocida. Así la regla se puede revisar en un PR sin discutir gustos.
- **Las *docstrings* cuentan como comentarios.** Si no, la regla se esquivaría pasando el texto a una *docstring*.
- **La excepción para comentarios existentes que quedan falsos.** Un comentario que contradice el código es un error. Si una issue cambia el código que describe, se corrige lo mínimo y se anota en el registro. Fuera de ese caso, no se tocan.
- **Regla en el plan y no en la skill `ub-mode`.** La skill es de terceros y está versionada tal cual. Las reglas propias del proyecto van en `PLAN.md`.

## Tests
No aplica: la issue no cambia código Python.

## Verificación
```
$ docker compose run --build --rm tests
168 tests, todo ok
```

## Pendientes o riesgos detectados
- Ninguno. La siguiente es la **#3**.
