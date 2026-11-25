# #23 — Recuperación consistente desde el disco

| Campo | Valor |
| --- | --- |
| Issue | #23 |
| Rama | `issue-23-recuperacion-consistente` |
| Requisitos | RF-18, RF-20 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Con disco, un nodo puede volver con operaciones que nadie más tiene. El ejemplo de la issue:
1. un primario confirma la op 41 y se cae antes de replicarla;
2. el primario nuevo escribe **otra** op 41;
3. el viejo vuelve diciendo «estoy en la 41» y nadie nota la diferencia.

Se pidió (D15):
- que el backup informe número **y época** de su última operación;
- que el primario le indique desde dónde recortar y le mande el resto;
- que el backup recorte en disco y en memoria;
- que la elección compare (época de la última op, `ultimo_seq`, id).

## Qué se hizo
Se llama **punta** de un log al par (época de su última op, `ultimo_seq`).

- **`nodo/estado.py`:** `EstadoServicio.epoca_ultima`.
- **`nodo/cluster/membresia.py`:** toda respuesta del cluster lleva `epoca_ultima`, además de `ultimo_seq`.
- **`nodo/cluster/eleccion.py`:**
  - el pedido `ELECCION` lleva la punta;
  - las credenciales pasan a ser (`epoca_ultima`, `ultimo_seq`, id).
- **`nodo/cluster/replica.py`**, del lado del primario:
  - `punto_en_comun(su_seq, su_epoca)`: si la última op del backup coincide con la mía en esa posición, coincide todo el prefijo (la coincidencia de logs de Raft) y se sigue desde ahí. Si no, desde 0;
  - la `PUESTA_AL_DIA` lleva `desde` y las ops que siguen;
  - la `REPLICA` lleva `previa`, la época de la op anterior. Es el chequeo de consistencia de `AppendEntries`, que mantiene la coincidencia de logs.
- **`nodo/cluster/latido.py`:** el primario compara la punta del backup con la suya, ya no sólo `ultimo_seq`. Si difiere, lo pone al día.
- **`nodo/servidor.py`**, del lado del backup:
  - **réplica:**
    - una op de un número que ya tengo cuenta como `DUPLICADA` sólo si es **la misma**. Si es otra, contesta `ATRASADO`, porque mi cola diverge;
    - si `previa` no coincide con mi última op, también contesta `ATRASADO`;
  - **puesta al día:** recorta sólo ante una op **distinta** de la que tiene en esa posición, como en Raft. Después de lo recibido, conserva la cola sólo si es de la época del primario que manda;
  - **`_recortar(n)`** reescribe el disco y reconstruye el estado con lo que quedó.
- **`nodo/disco.py`:** `reescribir(ops)`, atómico. Comparte con `guardar_epoca` el mismo reemplazo atómico (DRY).
- **Tests:** ver *Tests*.

## Por qué así
- **Recortar a 0 cuando la última op no coincide.** El primario sólo conoce la punta del backup. Buscar el punto exacto de divergencia pediría ir hacia atrás de a una op, como en Raft, o mandar el historial de épocas del backup. Con los logs de una partida de truco, reenviar todo es barato (YAGNI). El caso común, un backup que vuelve sin divergencias, recibe sólo lo que le falta.
- **El cambio de diseño durante la issue.** El diseño inicial recortaba siempre hasta `desde`. El subagente implementador encontró que, en plena replicación, un latido puede calcular la puesta al día con una punta vieja. Si esa puesta al día llega **después** de una `REPLICA` nueva, el backup recortaba una op que ya le había confirmado al primario. Terminaba igual que el primario, pero mientras tanto esa op confirmada dejaba de estar en el backup. Se reprodujo con el código anterior:

  ```
  ultimo_seq tras la puesta al dia vieja: 2        # tenía 3, la 3 ya confirmada
  recorto el log de la op 3 a la 1: diverge del primario
  ```

  Se cambió a la regla de Raft: recortar sólo ante un conflicto. Queda una cola que el mensaje no cubre. Si es de la época del primario que manda, la tiene él, porque es el único que crea ops de su época. Si es de otra época, es la de un primario viejo y se recorta.

  El agente había resuelto el síntoma agregando esperas al test. Se sacaron, para que el test pruebe la corrección.
- **Credenciales sin la época del nodo.** La #38 comparaba (época del nodo, `ultimo_seq`, id). Ahora manda la frescura del log, como en Raft. Sigue siendo un orden total, que es lo que arregló la #38: los dos candidatos calculan la misma comparación. El test de la #38 se adaptó para expresar el mismo caso con logs de épocas distintas.
- **Un nodo detenido no se corona.** Una elección en vuelo que terminaba después de `detener()` se coronaba y escribía la época en un directorio que ya no existía. Lo encontró el agente con los directorios temporales de los tests. En un nodo real pasaría al apagarlo. `convocar` y `_coronarme` cortan si el nodo está detenido.

  El agente además hacía que `detener()` tomara el lock. Se sacó: bajo carga, esa espera retrasaba el momento de la muerte que mide `test_si_el_primario_deja_de_latir_los_backups_lo_detectan`, y el test falló una vez (ver *Verificación*).
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió los tests y el código;
  - en la revisión:
    - se corrigió la carrera de arriba;
    - `desde` pasó a ser obligatorio: con 0 por defecto, un mensaje sin ese campo borraba el log;
    - se actualizó la llamada en `tests/test_servidor.py`;
    - se corrigieron las dos fallas intermitentes que aparecieron bajo carga (ver *Verificación*).

## Tests
- **Agregados** (`tests/test_recuperacion.py`, con tres nodos en proceso y un directorio temporal por nodo):
  - `test_un_backup_que_vuelve_con_su_disco_recibe_solo_lo_que_le_falta`: la puesta al día arranca en la op 2, no en la 0, y no recorta nada;
  - `test_un_backup_con_una_cola_divergente_la_recorta`: el caso del zombie, con disco. Su op no confirmada queda en disco, el primario nuevo escribe otra op 1, y al volver los tres terminan con el mismo log, también en el disco del zombie;
  - `test_un_log_mas_corto_de_epoca_mayor_gana_la_eleccion`;
  - `test_tras_apagar_los_tres_las_mesas_siguen`: se apagan los tres, vuelven con sus discos, eligen primario y la partida sigue con una jugada que llega a todos;
  - `test_una_replica_distinta_a_la_mia_no_cuenta_como_ack`;
  - `test_una_puesta_al_dia_vieja_no_recorta_lo_ya_confirmado`: el test de la carrera;
  - `test_una_cola_de_otra_epoca_que_el_primario_no_tiene_se_recorta`.
- **Modificados:**
  - `test_dos_candidatos_de_epocas_distintas_no_se_contestan_mando_yo_los_dos` (#38), con el criterio nuevo;
  - `_membresia` y `_arrancar` aceptan `disco`;
  - la llamada a `_atiendo_puesta_al_dia` de `test_un_backup_contesta_el_historial_aunque_no_atienda_el_juego`.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  FAIL test_un_backup_con_una_cola_divergente_la_recorta: los tres nodos tienen que converger al mismo log
  FAIL test_un_log_mas_corto_de_epoca_mayor_gana_la_eleccion: AttributeError: ... 'epoca_ultima'
  FAIL test_una_replica_distinta_a_la_mia_no_cuenta_como_ack: TypeError: ... 'previa'
  ```

  `test_un_backup_que_vuelve…` y `test_tras_apagar…` ya pasaban con la #22: sin divergencias, el disco alcanza. Quedan como regresión. Los dos tests de la carrera fallaron contra el primer diseño (ver arriba).

## Verificación
```
$ docker compose run --build --rm tests      # tres veces seguidas
207 tests, todo ok
207 tests, todo ok
207 tests, todo ok
```

**Bajo carga** (12 procesos `yes`, como en la #39). Las primeras 22 corridas dieron dos fallas intermitentes, una en cada tanda:

```
FALLO test_si_el_primario_deja_de_latir_los_backups_lo_detectan
FALLO test_un_backup_con_una_cola_divergente_la_recorta: el disco de N3 tiene que haber recortado la op divergente
```

- **La primera.** Venía del lock en `detener()`: el momento de la muerte del test quedaba después de esperar el lock, mientras el primario ya no latía. Aislado, el test dio 0 fallas en 60, porque depende de la contención de toda la suite. Se volvió `detener()` a como estaba.
- **La segunda era del test.** Leía el disco sin el lock del nodo, y `_aplicar` primero aplica en memoria y después escribe, los dos pasos bajo el lock. Ahora lee con el lock tomado. El protocolo no tenía problema: el ack sale recién después de escribir.

Con las dos correcciones:

```
$ suite-fallas.sh 20      # suite completa, 20 veces, bajo carga
[1] 207 tests, todo ok
…
[20] 207 tests, todo ok
```

## Pendientes o riesgos detectados
- **El disco no reemplaza al quórum.** La coincidencia de logs supone un solo primario por época. Si una partición deja dos primarios con la **misma** época, dos ops distintas pueden tener igual número y época, y la punta no las distingue. Es el cerebro dividido que el plan acepta (D4). Lo muestra el experimento 4 de la #25.
- **Una op confirmada sin acks se puede perder.** Si el primario la confirma, se cae y gana otro, la op se recorta cuando vuelve. Es el mismo límite, y también es un caso de la #25.
