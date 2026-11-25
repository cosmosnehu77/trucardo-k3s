# #12 — Contexto de traza entre nodos y entre hilos

| Campo | Valor |
| --- | --- |
| Issue | #12 |
| Rama | `issue-12-contexto-entre-nodos` |
| Requisitos | RF-14 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que una traza cruce de un nodo a otro y de un hilo a otro:

- `Membresia.mensaje()` inyecta el contexto (`traceparent`) y `despachar()` lo extrae. Con esos dos puntos se cubren todos los tipos de mensaje;
- los hilos que lanza el nodo reciben el contexto con **un único** ayudante.

## Qué se hizo
- **`nodo/telemetria.py`:**
  - `inyectar(mensaje)` y `extraer(mensaje)`, con el propagador estándar de OpenTelemetry (W3C `traceparent`);
  - `hilo(funcion, *args)`: un `Thread` *daemon*, sin arrancar, que corre la función dentro de una copia del contexto de quien lo crea.
- **`nodo/cluster/membresia.py`:**
  - `mensaje()` inyecta el contexto en el diccionario;
  - `despachar()` atiende cada mensaje con el contexto del emisor adjunto, y lo suelta al terminar.
- **Los nueve lugares de `nodo/` que creaban hilos** (`eleccion.py`, `latido.py`, `replica.py`, `membresia.py` y `transporte.py`) usan `telemetria.hilo`.
- **`tests/test_trazas.py`** (nuevo): ver *Tests*.
- **`PLAN.md`:** estado de la #12.

## Por qué así
- **El propagador estándar.** El campo `traceparent` es el de W3C Trace Context. Jaeger y cualquier otro *backend* lo entienden, y no hay formato propio que mantener.
- **`despachar()` no crea *spans*.** Sólo adjunta el contexto: los *spans* los crean los manejadores en la #14, que decide cuáles valen la pena. Uno por mensaje llenaría Jaeger de latidos, que la #14 excluye a propósito.
- **`contextvars.copy_context().run`.** OpenTelemetry guarda el contexto en `contextvars`, y un `Thread` nuevo arranca con un contexto vacío. Copiarlo al crear el hilo hace que la réplica o la puesta al día lanzadas durante una jugada sigan en la traza de esa jugada.
- **Un solo ayudante también en el transporte.** Los hilos del puerto del cluster no tienen contexto que heredar, porque el contexto llega en cada mensaje. Igual usan el ayudante, para que no quede ningún `threading.Thread` suelto que alguien copie después en un lugar donde sí importa (DRY).
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió primero los tests y después el código;
  - se revisó el diff: los hilos conservan `daemon`, los argumentos y el `join` donde lo había.

## Tests
- **Agregados** (`tests/test_trazas.py`), con tres nodos en proceso y un exportador en memoria. El nodo receptor tiene un manejador de prueba que abre un *span* «receptor»:
  - `test_contexto_se_propaga_entre_nodos`: un mensaje enviado dentro del *span* «emisor» produce un «receptor» de la misma traza, hijo del emisor;
  - `test_contexto_se_propaga_entre_nodos_desde_otro_hilo`: lo mismo, enviando desde un hilo creado con `telemetria.hilo`;
  - `test_sin_span_emisor_el_receptor_no_tiene_padre`: el control, para que el test no pase adjuntando cualquier contexto;
  - `test_hilo_propaga_contexto_es_daemon_y_no_arranca_solo`.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  FAILED test_contexto_se_propaga_entre_nodos - AssertionError (receptor.context.trace_id != emisor.context.trace_id)
  FAILED test_contexto_se_propaga_entre_nodos_desde_otro_hilo - AttributeError: module 'nodo.telemetria' has no attribute 'hilo'
  FAILED test_hilo_propaga_contexto_es_daemon_y_no_arranca_solo - AttributeError: module 'nodo.telemetria' has no attribute 'hilo'
  ```

  El control ya pasaba, como corresponde.

## Verificación
```
$ docker compose run --build --rm tests
224 tests, todo ok
```

## Pendientes o riesgos detectados
- **El control cuenta un solo *span*.** Cuando la #14 sume *spans* de dominio, ese test tiene que filtrar por nombre.
