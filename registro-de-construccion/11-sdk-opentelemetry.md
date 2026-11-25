# #11 — SDK de OpenTelemetry, opcional por entorno

| Campo | Valor |
| --- | --- |
| Issue | #11 |
| Rama | `issue-11-sdk-opentelemetry` |
| Requisitos | RF-13, RNF-07 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Las dependencias de OpenTelemetry con versión exacta, y `nodo/telemetria.py` como **único** punto de configuración (D16):

- si está `OTEL_EXPORTER_OTLP_ENDPOINT`, el nodo exporta con `service.name=trucardo-nodo<id>`;
- si no, no hace nada.

## Qué se hizo
- **`requirements.txt`:** `opentelemetry-api`, `opentelemetry-sdk` y `opentelemetry-exporter-otlp-proto-http`, las tres en la 1.45.2.
- **`nodo/telemetria.py`** (nuevo):
  - `configurar(id_nodo, exportador=None)`:
    - sin exportador y sin la variable, no arma nada;
    - si no, arma un `TracerProvider` con el `service.name` del nodo y un `BatchSpanProcessor`, con el exportador recibido o con el OTLP por HTTP, que toma el destino de la variable;
  - `tracer()` devuelve el tracer del proveedor o, sin proveedor, uno que no registra nada;
  - `cerrar()` vacía lo pendiente y apaga el proveedor.
- **`nodo/servidor.py`:** `main()` configura la telemetría al arrancar y la cierra al salir, junto a la membresía.
- **`tests/test_telemetria.py`** (nuevo): ver *Tests*.
- **`PLAN.md`:** estado de la #11.

## Por qué así
- **Un proveedor propio y no el global de OpenTelemetry.** `trace.set_tracer_provider` sólo se puede llamar una vez por proceso: la segunda llamada se ignora con un aviso. La suite corre todos los tests en un solo proceso, así que el primer test que configurara la telemetría fijaría el proveedor para todos los demás. Con el proveedor guardado en el módulo, cada test configura el suyo y lo cierra.
- **`cerrar()` al salir.** El `BatchSpanProcessor` junta los *spans* y los manda de a tandas. Sin vaciarlo, lo último antes de un Ctrl+C se perdería, que suele ser justamente lo interesante de un experimento de falla.
- **El destino sale de la variable estándar.** El exportador OTLP lee `OTEL_EXPORTER_OTLP_ENDPOINT` por su cuenta. Cambiar Jaeger por un *Collector* (D16) es cambiar ese valor, sin tocar el nodo.
- **Sin *spans* todavía (YAGNI).** Los de dominio son la #14. Esta issue sólo deja el punto de configuración.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió primero los tests y después el código;
  - se revisó el diff. Los tests reusan el ayudante `_entorno` de `tests/test_config.py`, sin duplicarlo.

## Tests
- **Agregados** (`tests/test_telemetria.py`):
  - `test_sin_endpoint_no_registra_spans`;
  - `test_con_exportador_en_memoria_registra_el_span_con_service_name`: el *span* llega al exportador con `service.name=trucardo-nodo2`, y después de `cerrar()` ya no se registra nada;
  - `test_con_endpoint_otlp_activa_el_sdk_con_el_nombre_del_nodo`: con la variable y sin exportador, el *span* se registra. No se termina, para que el test no intente exportar a un destino que no existe.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  E   ImportError: cannot import name 'telemetria' from 'nodo' (/app/nodo/__init__.py)
  ```

## Verificación
```
$ docker compose run --build --rm tests
220 tests, todo ok
```

Sin la variable, la suite tarda lo mismo que antes, unos 36 s.

Por la falla intermitente de *Pendientes*, la suite se corrió también 20 veces bajo carga (12 procesos `yes`):

```
$ suite-fallas.sh 20
[1] 220 tests, todo ok
…
[20] 220 tests, todo ok
```

## Pendientes o riesgos detectados
- **Una falla intermitente que no es de esta issue.** El primer intento de commit lo rechazó el *hook*: falló `test_tres_nodos_que_arrancan_juntos_eligen_uno_solo`, con el cluster local corriendo de fondo. No se reprodujo en 60 corridas aisladas ni en 15 corridas del módulo de membresía bajo carga. Una hipótesis: desde la #53, si bajo carga N2 se corona sin que N3 llegue a contestar, ninguna elección tardía lo corrige, y N3 queda de backup. Sigue habiendo un solo primario, pero el test exige que sea el de id mayor. Como pide la #39, no se corrige sin reproducirlo. En 20 corridas de la suite bajo carga no volvió a aparecer (ver *Verificación*). Si reaparece, se abre una issue con el log.
- **La imagen crece** con el SDK y el exportador, aunque no se use la telemetría. Se aceptó al planificar la fase (RNF-07: versiones exactas, sin dependencias opcionales).
