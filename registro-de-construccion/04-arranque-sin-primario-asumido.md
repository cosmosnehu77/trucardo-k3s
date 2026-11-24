# #4 — Arranque sin primario asumido

| Campo | Valor |
| --- | --- |
| Issue | #4 |
| Rama | `issue-04-arranque-sin-primario-asumido` |
| Requisitos | RF-08, RF-10 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Que ningún nodo arranque creyéndose primario. Hasta ahora, `main()` hacía que el nodo de id mayor arrancara como primario de la época 0 (`primario=max(cluster)`). Si Kubernetes lo reiniciaba antes de que los backups notaran su ausencia, quedaba de primario **con el estado vacío**.

## Qué se hizo
- **`nodo/cluster/membresia.py`:** `arrancar()` deja al nodo de **backup y sin primario** antes de empezar a escuchar. Desde ahí, el vigía convoca una elección.
- **`nodo/servidor.py`:**
  - `main()` construye el nodo sin `primario=max(cluster)`;
  - el log de arranque dice «arranco de backup y sin primario: se elige uno (gana el mas al dia y, si empatan, el de id mayor)».
- **`nodo/cluster/latido.py`:** cuando el vigía convoca porque no conoce al primario, el log dice «no conozco al primario: convoco una eleccion». «Reintento» queda sólo para una elección que de verdad no terminó.
- **`tests/test_membresia.py`:**
  - tests nuevos (ver *Tests*);
  - el ayudante `_arrancar` ya no recibe `primario`, porque `arrancar()` lo decide. `_armar`, que agregó la #18, se eliminó (ver *Verificación*);
  - el *docstring* de `_cluster` decía «el primario es el 3, como en main()». Quedó falso y se corrigió lo mínimo: «al arrancar eligen primario, y gana el 3» (excepción de la regla de comentarios, PLAN 1.1);
  - ajustes a tests que asumían el arranque viejo:
    - `test_el_primario_depuesto_se_baja` arma al zombi a mano después de arrancarlo: primario, de la época 0;
    - `test_no_anuncia_reintento_mientras_la_eleccion_corre` empieza a contar reintentos recién con el cluster armado, porque ahora el arranque también tiene elecciones;
    - `test_si_el_ganador_muere_en_plena_eleccion_se_reintenta` ya no le pasa el primario al nodo.
- **`PLAN.md`:** estado de la #4.

## Por qué así
- **La regla vive en la membresía, no en `ServidorTruco`.** Un `ServidorTruco` solo, sin cluster, sigue siendo su propio primario: así lo usan los tests del servidor y de la conexión. Lo que cambia es **entrar a un cluster**: quien entra no sabe quién manda. Por eso lo decide `Membresia.arrancar()`, que reusa `sin_primario()`.
- **No hizo falta tocar la elección.** Bully ya compara (`ultimo_seq`, id). Un nodo reiniciado vacío pierde contra cualquiera que tenga operaciones, y si todos están vacíos gana el id mayor, como antes.
- **El log nuevo no es cosmético.** Con elecciones al arrancar, cada nodo anunciaba «reintento» en el primer segundo, y eso es falso. Además ensuciaba el test que cuenta reintentos.
- **Alternativa descartada:** esperar un *timeout* de latidos antes de la primera elección, para que un backup que se reinicia escuche primero al primario vigente. Ahorraría una elección de más, pero retrasa el arranque del cluster y suma un estado nuevo al vigía. Si el primario vigente existe, su latido suele llegar antes que el *jitter* de la elección y la cancela.

## Tests
- **El test que reproduce el problema** (`test_un_primario_reiniciado_vacio_no_vuelve_a_mandar`) falló con el código viejo **por la razón esperada**:

  ```
  AssertionError: arranca con el estado vacio: no se puede creer primario
  ```

  Y el estado final con el código viejo, 2 s después de reiniciar al primario:

  ```
  N1 rol=backup primario=3 epoca=0 ultimo_seq=1
  N2 rol=backup primario=3 epoca=0 ultimo_seq=1
  N3 rol=primario primario=3 epoca=0 ultimo_seq=0
  ```

  N3 manda con el log vacío mientras los backups tienen la partida.
- **Agregados:**
  - `test_un_primario_reiniciado_vacio_no_vuelve_a_mandar`;
  - `test_tres_nodos_que_arrancan_juntos_eligen_uno_solo`;
  - `test_un_nodo_solo_se_corona_al_arrancar`;
  - `test_al_arrancar_no_anuncia_un_reintento`, que falló antes del cambio del log.

## Verificación
La suite completa, 10 veces seguidas sin carga:

```
$ docker compose run --rm tests        # x10
172 tests, todo ok                     # las 10 corridas
```

Los 4 tests nuevos, 25 veces cada uno con 12 procesos `yes` ocupando las 12 CPU: **0 fallas**.

**Historia de la issue:**
- La primera versión de estos cambios hizo fallar la suite 2 de 8 veces. La falla del test de la #18 empezó a aparecer más seguido, porque ahora cada arranque tiene una elección.
- Como pide el plan, la #4 se pausó con `git stash`, se resolvió la #18 (PR #40) y la #4 se retomó encima. Al recuperar el *stash* hubo un conflicto en `tests/test_membresia.py`: la #18 había partido `_arrancar` en `_armar` + `arrancar()` para el test del zombi.
- Con el arranque nuevo, `arrancar()` siempre deja al nodo de backup, así que armar al zombi antes de arrancarlo ya no sirve. Se arma después de arrancar (primario, época 0) y `_armar` se eliminó por quedar sin uso.

## Pendientes o riesgos detectados
- **Elecciones de más.** Cada arranque convoca una elección. Si un backup se reinicia y su elección sale antes del primer latido, el primario vigente vuelve a coronarse en una época nueva. Es inofensivo, pero sube la época.
- **#38:** las elecciones al arrancar hacen más probable que dos nodos queden un rato en épocas distintas. Va inmediatamente después.
