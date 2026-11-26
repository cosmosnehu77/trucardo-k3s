# #73 — Un backup queda trabado si su log diverge del primario en la misma época

| Campo | Valor |
| --- | --- |
| Issue | #73 |
| Rama | `issue-73-backup-trabado` |
| Requisitos | RF-21 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Que un backup con un log distinto al del primario, pero con la misma época en su última op, vuelva a seguir al primario sin recrear su Pod. El visor (#72) mostró a N3 parado en la op 16: cada segundo la puesta al día cortaba en la op 17 por `ILEGAL`.

## Qué se hizo
- `nodo/cluster/replica.py`:
  - `_poner_al_dia` manda primero lo que falta desde el punto en común, como antes. Si el backup contesta `ILEGAL`, le manda el log entero (`desde=0`), y el backup recorta en la primera op distinta, con la regla que ya tenía de la #23.
  - El envío pasó a `_mandar_log`, que devuelve el motivo de la respuesta.
  - Una `REPLICA` que vuelve `ILEGAL` ya no sólo se anota en el log: dispara la puesta al día, igual que `ATRASADO`.

## Por qué así
- **La causa.** Una elección corona con `max(épocas que veo) + 1`. Dos nodos aislados que estaban en la época 4 se coronan los dos en la 5 y escriben ops distintas con la misma época. `punto_en_comun` confía en la última op, como Raft: si coincide el seq y la época, el prefijo es el mismo. Raft lo garantiza porque cada época tiene un solo líder, elegido por mayoría. Trucardo no vota por mayoría, así que la garantía no vale.
- **Mandar el log entero sólo cuando falla.** Lo común es que el prefijo coincida, y entonces no hace falta reenviar todo (el test de la #23 lo sigue verificando). El log entero es la red de seguridad: es caro, pero sólo pasa después de un cerebro dividido.
- **Alternativa descartada:** elegir épocas únicas (por ejemplo, época × 10 + id). Evita la coincidencia, pero cambia el formato de las épocas, el desempate de la elección y los experimentos ya hechos. La causa de fondo es no tener quórum, que ya está en Límites.
- Las ops que el backup tenía de su rama se pierden: es el mismo límite del caso 11.

## Tests
- **Agregados en `tests/test_recuperacion.py`:**
  - `test_un_backup_que_diverge_en_la_misma_epoca_recibe_el_log_entero`: el primario y el backup tienen la op 2 distinta, los dos en la época 5, y la op 3 del primario es ilegal sobre el estado del backup. Después de la puesta al día, el backup tiene el log del primario;
  - `test_una_replica_ilegal_dispara_la_puesta_al_dia_del_log_entero`: el mismo caso, pero el backup se entera por la `REPLICA` de la op 3.
- **Los dos fallaron antes del cambio:** la puesta al día arrancaba en la op 3 y cortaba por `ILEGAL`, y la `REPLICA` ilegal no disparaba nada.

## Verificación
```
$ docker compose run --build --rm tests
...
286 tests, todo ok
```

## Pendientes o riesgos detectados
- Ninguno nuevo. Mientras no haya quórum, dos primarios pueden coexistir; esto sólo asegura que, al curarse, todos terminen con el mismo log.
