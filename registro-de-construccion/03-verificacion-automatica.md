# #3 — Verificación automática de la suite

| Campo | Valor |
| --- | --- |
| Issue | #3 |
| Rama | `issue-03-verificacion-automatica` |
| Requisitos | RNF-01, RNF-05 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Que la regla «no se commitea con la suite en rojo» no dependa de la memoria de nadie:
- un *hook* de Git que bloquee el commit si la suite falla;
- una verificación en GitHub que corra lo mismo en cada PR.

## Qué se hizo
- **`.githooks/pre-commit`** (ejecutable):
  - corre `docker compose run --build --rm tests`;
  - si la suite pasa, muestra sólo la última línea (`168 tests, todo ok`);
  - si falla, muestra la salida completa, avisa que el commit fue rechazado y sale con error.
- **`.github/workflows/suite.yml`:** en cada PR y en cada push a `main`, hace *checkout* (`actions/checkout@v7.0.1`) y ejecuta **el mismo** `.githooks/pre-commit`.
- **`PLAN.md`, sección 1.4:**
  - el comando de Docker pasa a llevar `--build`;
  - cómo activar el *hook* y qué hace la verificación en GitHub;
  - qué prueba el *hook* (la carpeta, no el *stage*) y que `--no-verify` no se usa;
  - estado de la #3.
- **`README.md`:** `--build` en el comando de tests y la activación del *hook*.

## Por qué así
- **Un solo script para la computadora y para GitHub (DRY).** El *workflow* no repite el comando: ejecuta el *hook*. Si mañana cambia cómo se corre la suite, se cambia en un lugar.
- **Docker y no `python3 run_tests.py`.**
  - La imagen fija Python 3.10 y las dependencias exactas.
  - En esta computadora `python3` es 3.15 y no tiene Pyro5: el *hook* con Python local fallaría o probaría otra versión.
  - En GitHub, el mismo contenedor evita instalar Python y dependencias en el *workflow*.
- **`--build` era un error latente del plan.** El `Dockerfile` copia el código dentro de la imagen. `docker compose run --rm tests` sin reconstruir prueba el código de la **última imagen construida**, no el actual: un test roto nuevo pasaría. Con la caché de capas, reconstruir sólo copia el código y tarda segundos (≈13 s la suite completa).
- **Salida corta cuando pasa.** 170 líneas de «ok» en cada commit esconden lo importante; si falla, se muestra todo para ver qué y dónde.
- **El *hook* prueba la carpeta, no el *stage*.** Probar sólo lo que está en el *stage* obliga a guardar y restaurar cambios (`git stash`), con riesgo de perder trabajo. Como cada issue es un solo commit con todo, en la práctica es lo mismo. Queda escrito en 1.4.
- **`actions/checkout` con versión exacta** (RNF-07). Es la última publicada.
- **Push a `main` también se verifica.** El criterio 4 de entrega pide la suite en verde en el último commit de `main`, y así queda a la vista.
- **Sin comentarios en los archivos nuevos** (RNF-10). El nombre del paso del *workflow* ya dice que corre el mismo script que el *hook*.
- **Alternativas descartadas:**
  - **El *framework* `pre-commit` de Python:** una dependencia más para correr un comando.
  - **Instalar el *hook* con un script:** basta un `git config` documentado.
  - **Protección de rama en GitHub que bloquee el merge:** en repos privados de cuentas gratuitas no está disponible. La regla de 1.4 («un PR en rojo no se mergea») cubre el caso.

## Tests
No lleva test unitario: es configuración (PLAN, 1.4). Verificación reproducible:

```
$ git config core.hooksPath .githooks
$ printf 'def test_roto_a_proposito():\n    assert 1 == 2\n' > tests/test_roto_a_proposito.py
$ git add -A && git commit -m "prueba: debe ser rechazado"
...
168 pasaron, 1 FALLARON:
  - test_roto_a_proposito.test_roto_a_proposito
Commit rechazado: la suite no pasa.
$ git log --oneline -1          # el commit no se creó
439e342 Merge pull request #34 from cosmosnehu77/issue-33-regla-de-comentarios
$ rm tests/test_roto_a_proposito.py
```

## Verificación
```
$ .githooks/pre-commit
168 tests, todo ok
$ git commit                    # el commit de esta issue pasó por el hook
168 tests, todo ok
```

Verificación del PR #35 en GitHub (*workflow* `suite`, corrida 45476909255):

```
suite  Suite completa (el mismo script que el hook pre-commit)  168 tests, todo ok
conclusion: success
```

## Pendientes o riesgos detectados
- **#18 (test intermitente):** con el *hook* activo, si vuelve a fallar bloquea commits correctos. Se resuelve antes de la #4 si aparece.
