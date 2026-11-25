# #27 — Logs correlacionados con las trazas

| Campo | Valor |
| --- | --- |
| Issue | #27 |
| Rama | `issue-27-logs-correlacionados` |
| Requisitos | RF-13, RF-22 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
- Que el logger `trucardo` mande sus líneas también por OpenTelemetry, además de a la consola.
- Que los datos del prefijo (nodo, rol, época y Lamport) salgan de **una sola** función, usada por la consola y por los atributos del log exportado.
- Que la consola quede idéntica.
- Que una línea emitida dentro de un *span* se exporte con su `trace_id`.

## Qué se hizo
- **`nodo/registro.py`:**
  - `estado(nodo)` devuelve nodo, rol, época y Lamport. De ahí salen el prefijo de la consola y los atributos `trucardo.*` del log exportado;
  - si hay telemetría, `configurar()` suma el manejador de OpenTelemetry, con un filtro que agrega esos atributos.
- **`nodo/telemetria.py`:**
  - un `LoggerProvider` propio, con el mismo `Resource`. Exporta por OTLP en lotes, o a un exportador en memoria (tests);
  - `manejador_de_logs()` devuelve el manejador, o `None` sin telemetría;
  - `cerrar()` saca el manejador del logger y apaga el proveedor.
- **`nodo/servidor.py`:** `main()` configura la telemetría antes del registro, para que el registro encuentre el manejador.
- **`tests/test_logs.py`** (nuevo): ver *Tests*.
- **`PLAN.md`:** estado de la #27.

## Por qué así
- **El `trace_id` no lo agrega Trucardo.** El `LoggingHandler` de OpenTelemetry toma el *span* activo al emitir la línea. Como las operaciones ya corren dentro de *spans* (#14), y los hilos heredan el contexto (#12), cada línea de una jugada, una elección o una puesta al día queda atada a su traza sin tocar ningún `log.info`.
- **Los atributos van por un filtro.** El `LoggingHandler` exporta como atributos los campos extra del registro de `logging`. Un filtro que copia `estado(nodo)` alcanza. Va antes que el de consola en la lista, para que el prefijo armado como texto no viaje como atributo.
- **API experimental.** En la versión fijada (1.45.2), la API de logs de OpenTelemetry para Python sigue en módulos con guion bajo (`opentelemetry.sdk._logs`, `..._log_exporter`): es experimental, como pedía verificar la issue. Se usa igual porque es la única forma de exportar los logs por OTLP desde el SDK. Si cambia, el cambio queda en `nodo/telemetria.py` (D16).
- **Cómo se trabajó:**
  - la API se probó en la imagen antes de diseñar;
  - un subagente implementador escribió primero los tests y después el código;
  - se revisó el diff.

## Tests
- **Agregados** (`tests/test_logs.py`), con un exportador de logs en memoria:
  - `test_log_dentro_de_un_span_lleva_su_trace_id_y_span_id`;
  - `test_log_exportado_lleva_atributos_del_estado_del_nodo_en_ese_momento`;
  - `test_la_linea_de_consola_es_identica_con_y_sin_telemetria`;
  - `test_sin_destino_otlp_no_configura_manejador_de_logs`;
  - `test_cerrar_saca_el_manejador_de_opentelemetry_del_logger`.
- **Fallaron antes del cambio** por la razón esperada (`unexpected keyword argument 'exportador_logs'`, `no attribute 'manejador_de_logs'`).

## Verificación
```
$ docker compose run --build --rm tests
250 tests, todo ok
```

## Pendientes o riesgos detectados
- **Hasta la #28, los logs tampoco tienen a dónde ir**, igual que las métricas de la #26: Jaeger sólo recibe trazas.
