# #26 — Métricas de dominio

| Campo | Valor |
| --- | --- |
| Issue | #26 |
| Rama | `issue-26-metricas-de-dominio` |
| Requisitos | RF-13, RF-21 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
El proveedor de métricas en `nodo/telemetria.py`, con el mismo destino OTLP (D16). Tiene que medir:

- operaciones por tipo y la latencia de confirmación;
- la época, el rol y el `ultimo_seq` de cada nodo;
- el atraso de cada backup visto desde el primario;
- las operaciones confirmadas con menos acks de los esperados;
- las elecciones con su duración, y los latidos perdidos.

## Qué se hizo
- **`nodo/telemetria.py`:**
  - `configurar(servicio, exportador=None, lector=None)` suma un `MeterProvider` propio, como el de trazas, con el mismo `Resource`. Exporta por OTLP cada 5 s, o con el lector que reciba (los tests usan uno en memoria);
  - las métricas:

    | Métrica | Tipo | Atributos |
    | --- | --- | --- |
    | `trucardo.operaciones` | contador | `tipo` |
    | `trucardo.confirmacion.duracion` | histograma (s) | — |
    | `trucardo.operaciones.sin_acks` | contador | — |
    | `trucardo.elecciones` | contador | — |
    | `trucardo.eleccion.duracion` | histograma (s) | `resultado` |
    | `trucardo.latidos.perdidos` | contador | `destino` |
    | `trucardo.epoca`, `trucardo.primario` (1/0), `trucardo.ultimo_seq` | valores instantáneos | — |
    | `trucardo.backup.atraso` | valor instantáneo, sólo del primario | `backup` |

    Todas llevan `trucardo.nodo`;
  - cuatro funciones de dominio (`operacion_confirmada`, `eleccion`, `latido_perdido` y `observar`), las únicas que usa `nodo/`. Sin métricas configuradas no hacen nada.
- **`nodo/cluster/membresia.py`:**
  - `visto`: el último `ultimo_seq` conocido de cada nodo, que no se borra cuando el nodo sale de la vista;
  - `anotar_seq()`, el único lugar que actualiza `vivos` y `visto`;
  - `arrancar()` registra la membresía para que la observen las métricas instantáneas.
- **Mediciones:**
  - `ServidorTruco._atender` mide desde que llega el pedido hasta la confirmación. Los reintentos no cuentan;
  - `Eleccion.convocar` mide cada candidatura;
  - `Latido.latir_a` cuenta cada latido sin respuesta.
- **`tests/test_metricas.py`** (nuevo): ver *Tests*.
- **`PLAN.md`:** estado de la #26.

## Por qué así
- **El atraso usa el último `seq` conocido, no la vista.** Un backup detenido sale de `vivos` en el primer latido perdido. Si el atraso se calculara con la vista, la serie desaparecería justo cuando importa. Con `visto`, crece con cada jugada.
- **El rol es `trucardo.primario`, con 1 o 0.** Sumado entre los nodos, da la cantidad de primarios simultáneos que pide el tablero de la #28: 2 es un cerebro dividido.
- **Sin acks contra los esperados, no contra los que contestaron.** El log dice «la tienen 1/1 de los que contestaron», pero el riesgo de cerebro dividido es confirmar sin todo el cluster. Por eso se compara contra `len(cluster) - 1`.
- **Las métricas instantáneas se leen con el lock del nodo**, en cada recolección. No hace falta actualizar nada en cada cambio de rol o de época: se mira el estado cuando hace falta.
- **Funciones de dominio y no instrumentos sueltos.** El código del nodo dice qué pasó (`latido_perdido`), y la forma de medirlo queda en un solo módulo (D16).
- **Cada 5 s, no 60.** El valor por defecto del SDK es 60 s, demasiado para ver una elección en un tablero.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió primero los tests y después el código;
  - se revisó el diff.

## Tests
- **Agregados** (`tests/test_metricas.py`), con el lector en memoria del SDK:
  - `test_una_jugada_replicada_registra_operacion_y_duracion`;
  - `test_el_rol_y_la_epoca_cambian_tras_una_eleccion`;
  - `test_el_atraso_de_un_backup_detenido_crece_y_registra_latidos_perdidos`: con un backup detenido y dos jugadas, su atraso es 2 y el del otro, 0;
  - `test_operacion_confirmada_sin_acks_suma_al_contador`;
  - `test_sin_configurar_las_funciones_de_dominio_no_fallan`.
- **Fallaron antes del cambio** por la razón esperada (`configurar() got an unexpected keyword argument 'lector'`, `no attribute 'observar'`).

## Verificación
```
$ docker compose run --build --rm tests
245 tests, todo ok
```

`tests/test_metricas.py` corrió 10 veces seguidas sin fallas, y la suite completa, 5 de 5 bajo carga (12 procesos `yes`).

## Pendientes o riesgos detectados
- **Hasta la #28, las métricas no tienen a dónde ir.** Con `--telemetria`, los nodos mandan todo a Jaeger, y Jaeger contesta 404 a `/v1/metrics` (se probó). El SDK lo registra como error cada 5 s, pero las trazas no se ven afectadas. La #28 cambia el destino al *Collector*.
