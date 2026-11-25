# #14 — *Spans* de dominio

| Campo | Valor |
| --- | --- |
| Issue | #14 |
| Rama | `issue-14-spans-de-dominio` |
| Requisitos | RF-15 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
*Spans* con nombre propio para la jugada, la réplica (uno por backup), la elección (`ELECCION` y `COORDINADOR`) y la puesta al día. Cada uno lleva la época, el número de operación, el sello de Lamport y el rol. Los latidos se trazan sólo si son rechazados.

## Qué se hizo
- **`nodo/telemetria.py`:** `span(nombre, nodo, **atributos)`, el único ayudante para abrir un *span* de dominio:
  - siempre pone `trucardo.nodo`, `trucardo.rol` y `trucardo.epoca`;
  - el resto de los atributos los pone con el prefijo `trucardo.`, salvo los que son `None`.
- **Los *spans*:**

  | *Span* | Dónde | Atributos propios |
  | --- | --- | --- |
  | `jugada <tipo>` | primario, `_atender` | `seq`, `lamport`; `reintento` si ya estaba aplicada |
  | `replica` | cada backup | `seq`, `lamport`, `motivo` si la rechaza |
  | `eleccion` | candidato | `ultimo_seq`, `epoca_ultima`, `resultado` (`gano`/`perdio`) |
  | `desafio` | cada nodo que recibe `ELECCION` | `candidato`, `le_gano` |
  | `coordinador` | ganador | — |
  | `coordinador recibido` | cada nodo que recibe `COORDINADOR` | `primario`, `aceptado` |
  | `puesta al dia` | primario | `destino`, `desde`, `cantidad` |
  | `puesta al dia recibida` | backup | `desde`, `cantidad`, `motivo` |
  | `latido rechazado` | primario que se entera de una época mayor | `destino`, `epoca_nueva` |

- **`tests/test_trazas.py`:** ver *Tests*.
- **`PLAN.md`:** estado de la #14.

## Por qué así
- **La réplica se traza del lado del backup.** El mensaje `REPLICA` sale una sola vez para todos, con el contexto de la jugada. Así cada backup que lo atiende abre su *span* como hijo de la jugada, y queda uno por backup sin tocar `preguntar_a_todos`. Un backup caído no aparece en el árbol, y eso también es información: muestra quién tiene la op.
- **El *span* se abre antes de armar el mensaje.** `Membresia.mensaje()` inyecta el contexto que esté activo en ese momento (#12). Por eso la elección, el coordinador y la puesta al día abren su *span* antes de armar el pedido: si no, los del receptor quedarían colgando de otro padre.
- **La elección es un árbol.** `eleccion` → un `desafio` por nodo que contesta, y si gana, `coordinador` → un `coordinador recibido` por nodo. El *span* se abre después del *jitter*, así no mide la espera al azar.
- **Los latidos aceptados no se trazan.** Son uno por segundo por backup y taparían todo lo demás en Jaeger. El rechazado sí, porque es justo cuando un primario viejo se entera de que ya no manda.
- **Las consultas no se trazan** (`ver`, `historial`, `quien_es`): son lecturas periódicas del cliente.
- **La jugada también se ve si llega a un backup.** `_exigir_primario` lanza `NoPrimario` adentro del *span*, y OpenTelemetry lo registra como error. Así la redirección del cliente queda en la traza.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano, con los nombres y los atributos de cada *span*. Un subagente implementador escribió primero los tests y después el código;
  - se revisó el diff: los cuerpos de los métodos no cambian, sólo quedan adentro del *span*.

## Tests
- **Agregados** (`tests/test_trazas.py`), con un exportador en memoria:
  - `test_una_jugada_replicada_genera_span_en_primario_y_en_cada_backup`: dos `replica`, uno por backup, hijos de la jugada y con su mismo `seq`;
  - `test_un_reintento_marca_reintento_y_no_lleva_seq`;
  - `test_una_eleccion_produce_eleccion_desafios_y_coordinador`: el árbol completo de la elección al arrancar tres nodos;
  - `test_una_puesta_al_dia_genera_span_en_primario_y_en_backup`;
  - `test_los_latidos_normales_no_producen_spans`: con el cluster estable, varios latidos no dejan ningún *span*;
  - `test_un_latido_rechazado_produce_span_con_epoca_nueva`;
  - `test_replica_con_op_invalida_no_falla_y_registra_motivo`.
- **Cambiados:** los controles de la #12 y la #13 filtran por nombre, porque ahora puede haber *spans* de dominio.
- **Fallaron antes del cambio** por la razón esperada: los siete nuevos no encontraban sus *spans*, y los de la #13 buscaban `jugada crear` en el servidor.

## Verificación
```
$ docker compose run --build --rm tests
235 tests, todo ok
```

`tests/test_trazas.py` corrió 10 veces seguidas sin fallas, en 20 s en total. Como ahora hay *spans* dentro de secciones con el lock tomado, la suite completa se corrió además 10 veces bajo carga (12 procesos `yes`): 10 de 10 sin fallas.
