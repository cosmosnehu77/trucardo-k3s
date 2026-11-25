# #53 — Una elección tardía dispara otra aunque ya haya primario

| Campo | Valor |
| --- | --- |
| Issue | #53 |
| Rama | `issue-53-eleccion-tardia` |
| Requisitos | RF-08, RNF-01 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Al verificar la #10 se vio que una `ELECCION` que llega tarde dispara otra elección, aunque ya haya primario. Quien tiene mejores credenciales contestaba «mando yo» y **siempre** convocaba su propia elección. Se pidió que no convoque si es primario o si sigue a un primario que late, sin dejar colgado al candidato.

## Qué se hizo
- **`nodo/cluster/membresia.py`:** `primario_vivo()` responde si el nodo es primario o si sigue a uno cuyo último latido es más reciente que `TIMEOUT_CAIDO`.
- **`nodo/cluster/eleccion.py`:** `_al_eleccion` sigue contestando «mando yo» al candidato peor, pero convoca sólo si no hay un primario vivo. La condición se calcula con el mismo lock que las credenciales.
- **`nodo/cluster/latido.py`:** `_vigilar` usa `primario_vivo()` para decidir si hay algo que hacer. Es la misma condición que antes estaba escrita a mano (rol distinto de backup, o silencio menor que el *timeout*), así que no cambia su comportamiento (DRY).
- **`tests/test_membresia.py`:** cuatro tests (ver *Tests*).
- **`PLAN.md`:** estado de la #53.

## Por qué así
- **«Mando yo» sin convocar.** El candidato se retira a esperar un `COORDINADOR`, y no necesita que llegue: el primario late a **todos** los nodos del cluster, también a los que no tiene en la vista, y el latido le hace adoptar al primario (`adoptar_primario` limpia la elección en curso). Así se entera en a lo sumo un latido, mucho antes de `TIMEOUT_ELECCION`.
- **Y si el candidato tenía razón**, porque el primario murió y el que contesta todavía no lo notó: el que contesta lo va a detectar al vencer su `TIMEOUT_CAIDO`, y convoca él. Y el candidato reintenta al vencer `TIMEOUT_ELECCION`. No queda nadie colgado.
- **«Vivo» es la misma condición que usa `_vigilar` para no dar al primario por caído.** Si las dos condiciones pudieran diferir, un nodo podría negarse a convocar mientras su vigilancia ya lo considera caído, o al revés.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió primero los tests y después el código;
  - se revisó que el cambio en `_vigilar` fuera equivalente, y que los tests no pasaran con un «nunca convoca»: para eso está el caso de control.

## Tests
- **Agregados** (`tests/test_membresia.py`):
  - `test_eleccion_tardia_no_convoca_si_el_primario_esta_vivo`: un backup que acaba de recibir un latido contesta «mando yo» y no convoca;
  - `test_eleccion_tardia_no_convoca_si_ya_es_primario`;
  - `test_eleccion_convoca_si_no_hay_primario_vivo`, el control: sin primario, o con el último latido vencido, **sí** convoca;
  - `test_eleccion_tardia_no_cambia_la_epoca_con_primario_vivo`: con tres nodos reales armados, una `ELECCION` de un candidato peor no sube la época.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  FALLO  test_eleccion_tardia_no_cambia_la_epoca_con_primario_vivo: una ELECCION tardia no puede subir la epoca si el primario esta vivo
  FALLO  test_eleccion_tardia_no_convoca_si_el_primario_esta_vivo: sigue a un primario vivo: no tiene que convocar
  FALLO  test_eleccion_tardia_no_convoca_si_ya_es_primario: ya es primario: no tiene que convocar
  ```

  El control ya pasaba, como corresponde.

## Verificación
```
$ docker compose run --build --rm tests
217 tests, todo ok
```

**Bajo carga** (12 procesos `yes`, como en la #39). Antes del cambio, la suite completa había fallado 2 veces en 12 corridas, y el test aislado 1 vez en 60 (ver el registro de la #10). Con el cambio:

```
$ suite-fallas.sh 20      # suite completa, 20 veces, bajo carga
[1] 217 tests, todo ok
…
[20] 217 tests, todo ok

$ test_si_el_primario_deja_de_latir_los_backups_lo_detectan, aislado, 60 veces bajo carga
0 fallas de 60
```

## Pendientes o riesgos detectados
- Ninguno nuevo. El límite de fondo sigue siendo el de D4: sin quórum, una partición deja dos primarios. Esta issue sólo saca una elección innecesaria.
