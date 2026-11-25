# #22 — Log de operaciones en disco

| Campo | Valor |
| --- | --- |
| Issue | #22 |
| Rama | `issue-22-log-de-operaciones-en-disco` |
| Requisitos | RF-17, RNF-07 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que el nodo, si está definida `TRUCARDO_DATOS`, guarde en ese directorio cada operación **antes** de confirmarla, y también su época. Al arrancar, tiene que aplicar lo guardado antes de atender pedidos. Todo el acceso al disco va en un solo módulo (D12, D13).

## Qué se hizo
- **`nodo/disco.py`** (nuevo), el único módulo que toca el directorio de datos:
  - `Disco.agregar(op)` agrega una línea JSON a `ops.jsonl`, con `flush` y `fsync`;
  - `Disco.operaciones()` lee las operaciones en orden;
  - `guardar_epoca` y `epoca`: la época va en el archivo `epoca`, que se reescribe de forma atómica (temporal, `fsync` y `os.replace`);
  - al abrir, si el archivo termina en una línea incompleta, se trunca hasta el último salto de línea;
  - `abrir(directorio)` devuelve `None` si no hay directorio.
- **`nodo/config.py`:** `directorio_datos()` lee `TRUCARDO_DATOS`.
- **`nodo/servidor.py`:**
  - `ServidorTruco(..., disco=None)`. Con disco, el constructor reconstruye el estado y la época desde lo guardado, antes de que el nodo atienda nada;
  - `epoca` pasa a ser una propiedad. Al cambiar, se guarda **antes** de asignarse. Así `membresia.py`, que la asigna en tres lugares, no cambió;
  - `_aplicar(op)` aplica y guarda, y lo usan los dos caminos:
    - el **primario**, en `_atender`, antes de replicar y responder;
    - el **backup**, en `_aplicar_replica`, antes del ack;
  - si no se pudo escribir, `_aplicar` vuelve el estado a lo que hay en disco y relanza el error. El primario no replica ni confirma. El backup contesta `ATRASADO` en vez del ack;
  - `main()` abre el disco con `TRUCARDO_DATOS`.
- **`tests/test_disco.py`** (nuevo): ver *Tests*.
- **`PLAN.md`:** estado de la #22.

## Por qué así
- **La época como propiedad.** Es el único punto por donde pasan los tres cambios de época: coronarse, adoptar a un primario y degradarse. Guardarla ahí cumple «guardar antes de actuar» sin repartir llamadas al disco por la membresía (DRY).
- **Aplicar primero y guardar después.** `aplicar()` valida la jugada, y si es ilegal lanza `ValueError` sin tocar el disco. Escribir antes de validar dejaría en el log una operación que al releerla tira error.

  Si la escritura falla, el estado en memoria ya tiene la operación. Se reconstruye desde el disco, el mismo camino que al arrancar, en lugar de escribir código para deshacer una operación.
- **Truncar la línea incompleta al abrir.** No alcanza con ignorarla al leer: el próximo `agregar` se pegaría al pedazo y arruinaría también la operación nueva.
- **`ops.jsonl` se abre y se cierra en cada operación (YAGNI).** Con las pocas operaciones por segundo de una partida de truco, no hace falta mantenerlo abierto.
- **El orden de las issues.** La #22 depende formalmente de la #10, los experimentos de falla en k3s. Por decisión del usuario se adelantó la persistencia, que es la fase recomendada. La #22 no usa nada de la #10.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió primero los tests y después el código;
  - en la revisión se simplificó `guardar_epoca`: el temporal pasó a tener un nombre fijo, sin `mkstemp` ni limpieza por `BaseException`. Siempre se escribe con el lock del nodo tomado;
  - también se reforzó el test de «sin `TRUCARDO_DATOS`». El original listaba un directorio que el servidor no conocía, así que pasaba igual aunque se escribiera en otro lado. Ahora juega con el directorio de trabajo dentro del temporal.

## Tests
- **Agregados** (`tests/test_disco.py`):
  - `test_lo_guardado_se_lee_igual_y_en_orden`;
  - `test_un_backup_guarda_la_replica_antes_del_ack`: y un backup reiniciado tiene el mismo log;
  - `test_una_ultima_linea_incompleta_se_descarta`: se lee el resto, y la operación que se agrega después se lee bien;
  - `test_la_epoca_sobrevive_a_un_reinicio`: en `Disco` y en el servidor;
  - `test_un_nodo_reiniciado_reconstruye_las_mismas_mesas`: mismo `ultimo_seq`, época, log y vista de cada jugador;
  - `test_una_operacion_no_se_confirma_si_no_se_pudo_escribir`: el primario lanza `OSError` y no queda ninguna mesa. El backup contesta `ATRASADO` y no avanza;
  - `test_sin_trucardo_datos_no_se_escribe_nada`.
- **El test falló antes del cambio** por la razón esperada:

  ```
  ImportError: cannot import name 'disco' from 'nodo' (/app/nodo/__init__.py)
  ```

## Verificación
```
$ docker compose run --build --rm tests
200 tests, todo ok
```

**Aceptación con `docker compose`.** Los tres nodos corrieron con `TRUCARDO_DATOS=/tmp/datos` (un *override* local; los volúmenes llegan con la #24). `leo` y `beto` crearon una mesa y se sumaron. Después se detuvo y se volvió a arrancar el backup N1:

```
$ … quien_es        # nodo, rol, época, ultimo_seq
1 BACKUP e=1 seq=2 | 2 BACKUP e=1 seq=2 | 3 PRIMARIO e=1 seq=2

$ docker exec trucardo-nodo1-1 sh -c 'ls /tmp/datos; wc -l /tmp/datos/ops.jsonl; cat /tmp/datos/epoca'
epoca
ops.jsonl
2 /tmp/datos/ops.jsonl
1

$ docker compose stop nodo1 && docker compose start nodo1
23:10:35 [N1│BACKUP│e=1│L=0] escuchando en PYRO:truco@<tu-ip>:9501 · …
23:10:36 [N1│BACKUP│e=1│L=0] no conozco al primario: convoco una eleccion
23:10:36 [N1│BACKUP│e=1│L=245] N3 es el primario de la epoca 1

$ … quien_es
1 BACKUP e=1 seq=2 | 2 BACKUP e=1 seq=2 | 3 PRIMARIO e=1 seq=2
```

N1 arranca con la época 1, antes de hablar con nadie. No hay ninguna línea de «puesta al dia», porque ya tenía las dos operaciones. Sin disco, habría arrancado con la época 0 y la red le habría tenido que mandar todo el log.

## Pendientes o riesgos detectados
- **Un disco que falla en el primario.** El cliente recibe un `OSError`, que `cliente/conexion.py` no maneja, y el primario sigue siéndolo. No lo pide la issue (YAGNI). Si hiciera falta, el primario podría bajarse para que otro tome el mando.
- **El disco todavía no se compara con el de los demás.** Un nodo que vuelve con operaciones que nadie más tiene no lo detecta. Es justamente la #23 (D15).
