# #13 — Contexto de traza del cliente al nodo

| Campo | Valor |
| --- | --- |
| Issue | #13 |
| Rama | `issue-13-contexto-cliente-nodo` |
| Requisitos | RF-14 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que la traza empiece en el cliente: cada jugada abre un *span* raíz, y su contexto viaja por Pyro5 hasta el nodo que la atiende.

## Qué se hizo
- **`nodo/telemetria.py`:**
  - `configurar(servicio, exportador=None)` recibe ahora el `service.name` completo. Así lo usan el nodo (`trucardo-nodo<id>`) y el cliente (`trucardo-cliente-<nombre>`);
  - `anotaciones()` arma `{"TRCP": traceparent}` con el contexto actual, o `{}` si no hay;
  - `de_anotaciones(anotaciones)` reconstruye el contexto desde esa clave.
- **`cliente/conexion.py`:** un ayudante `_invocar` fija las anotaciones antes de cada llamada remota. Lo usan `Conexion.llamar` y `preguntar`.
- **`cliente/cliente.py`:**
  - `main()` configura la telemetría con el nombre del jugador y la cierra al salir;
  - `_enviar` abre el *span* `jugada <qué>` alrededor de la llamada.
- **`nodo/servidor.py`:** `_atender`, por donde pasan todas las operaciones que cambian el estado, corre con el contexto del cliente adjunto.
- **Tests:** ver *Tests*.
- **`PLAN.md`:** estado de la #13.

## Por qué así
- **Las anotaciones de Pyro5 y no un argumento más.** Pyro5 deja mandar metadatos con cada llamada, en `current_context.annotations`, por hilo. Agregar el contexto como argumento cambiaría la firma de todos los métodos remotos. Pyro5 exige claves de 4 letras y valores en bytes, de ahí `TRCP`.
- **En el servidor llega un `memoryview`.** Se descubrió al probar: pasarlo tal cual al propagador falla. `de_anotaciones` lo convierte a texto.
- **El *span* raíz en `_enviar`.** Es la jugada tal como la vive el jugador, con sus reintentos y redirecciones adentro. Las consultas (`ver`, `historial`) no abren *span*, para que Jaeger no se llene de lecturas periódicas.
- **El nodo no crea *spans* todavía.** Sólo adjunta el contexto: los de dominio son la #14, igual que en la #12.
- **`configurar` recibe el nombre del servicio.** El cliente necesita uno distinto del de los nodos, y era más simple que el llamador lo arme que agregar un parámetro de tipo.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano, después de verificar la API de anotaciones de Pyro5 5.17. Un subagente implementador escribió primero los tests y después el código;
  - se revisó el diff y se simplificó la conversión de `de_anotaciones`.

## Tests
- **Agregados** (`tests/test_trazas.py`), con un nodo Pyro5 real y un exportador en memoria. Un envoltorio de `_aplicar` abre un *span* «aplicar» en el servidor:
  - `test_anotaciones_transporta_y_reconstruye_el_contexto`;
  - `test_contexto_se_propaga_del_cliente_al_servidor`: «aplicar» es hijo de la «jugada» del cliente;
  - `test_sin_span_en_el_cliente_el_servidor_no_tiene_padre`: el control;
  - `test_enviar_del_cliente_abre_el_span_raiz_de_la_jugada`: irse al mazo con el `Cliente` real deja `jugada mazo` como padre de «aplicar».
- **Cambiados:** los de `test_telemetria.py` y `test_trazas.py` pasan el nombre del servicio.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  FALLO  test_con_endpoint_otlp_activa_el_sdk_con_el_nombre_del_nodo — service.name
  FALLO  test_con_exportador_en_memoria_registra_el_span_con_service_name — service.name
  FALLO  test_anotaciones_transporta_y_reconstruye_el_contexto — no attribute 'anotaciones'
  FALLO  test_contexto_se_propaga_del_cliente_al_servidor — trace_id distinto
  FALLO  test_enviar_del_cliente_abre_el_span_raiz_de_la_jugada — KeyError: 'jugada mazo'
  ```

## Verificación
```
$ docker compose run --build --rm tests
228 tests, todo ok
```

## Pendientes o riesgos detectados
- **`_atender` quedó un nivel más indentado.** El diff es grande, pero el cuerpo no cambió.
