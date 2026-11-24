# #36 — Imagen con Python 3.15

| Campo | Valor |
| --- | --- |
| Issue | #36 |
| Rama | `issue-36-imagen-python-3-15` |
| Requisitos | RNF-06, RNF-07 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Pasar la imagen de Trucardo de Python 3.10 a Python 3.15 y hacer los cambios que hicieran falta.

## Qué se hizo
- **`Dockerfile`:** `FROM python:3.10-slim` → `FROM python:3.15-slim`. Es el único cambio que hace efectiva la versión: nodos, clientes, tests, *hook* y verificación de GitHub usan esta imagen.
- **`REQUISITOS.md`, Restricciones:** la versión fija pasa a ser Python 3.15.
- **`PLAN.md`:**
  - sección 1.4: correr la suite sin Docker pide Python 3.15;
  - la issue en la sección 10, y calendario y estado.
- **Código Python:** ningún cambio. No hizo falta.

## Por qué así
- **Python 3.10 ya no tiene soporte de seguridad:** terminó en octubre de 2026. 3.15 lo tiene hasta 2031.
- **Misma versión que en las computadoras de desarrollo.** Con las dependencias instaladas, `python3 run_tests.py` prueba lo mismo que el cluster.
- **3.15 y no 3.13.** Se probaron las dos antes de decidir y las dos pasaron todo. Con 3.13 seguiría la diferencia de versiones con las computadoras de desarrollo, sin ninguna ventaja medida.
- **`requirements.txt` no cambia.** Pyro5 5.17, Serpent 1.43 y Rich 15.0.0 funcionan en 3.15 sin tocar versiones. Pyro5 5.17 es la última versión publicada y pide Python 3.7 o más.
- **El *workflow* de GitHub no cambia:** usa la imagen (#3).
- **No se tocó la descripción de la #3 en el plan,** que dice «con Python 3.10». Es el texto de una issue cerrada y cuenta lo que se pidió en su momento.

## Tests
No lleva test unitario: es configuración. Verificación reproducible, antes de decidir, con imágenes temporales iguales a la del repo salvo la versión:

| Imagen | Suite completa | OpenTelemetry 1.45.2 (fase 4) |
| --- | --- | --- |
| `python:3.15-slim` (3.15.2) | 168 tests, todo ok | se instala y se importa |
| `python:3.13-slim` (3.13.18) | 168 tests, todo ok | se instala y se importa |

```
$ docker run --rm trucardo:py3.15 sh -c "pip install opentelemetry-sdk==1.45.2 \
      opentelemetry-exporter-otlp-proto-http==1.45.2 && python -c 'import ...'"
otel ok
```

## Verificación
En la imagen del repo, ya con el cambio:

```
$ docker compose run --build --rm tests
168 tests, todo ok
$ docker compose run --rm --entrypoint python tests --version
Python 3.15.2
```

## Pendientes o riesgos detectados
- Alguna dependencia futura podría tardar en publicar versiones para 3.15. Si pasa, el *hook* y la verificación del PR lo detectan al agregarla.
