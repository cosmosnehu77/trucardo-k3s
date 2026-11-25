# #52 — Los nodos se encuentran sin depender del DNS del cluster

| Campo | Valor |
| --- | --- |
| Issue | #52 |
| Rama | `issue-52-sin-dns-del-cluster` |
| Requisitos | RF-02, RF-12 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
En el experimento 6 de la #10, apagar el servidor k3s dejó dos primarios: CoreDNS es una sola réplica y corre en el servidor, y sin DNS los nodos no se encuentran. Se pidió que cada Service tenga una IP fija y que cada Pod resuelva los nombres de los nodos por `/etc/hosts`, sin cambiar `TRUCARDO_NODOS`.

## Qué se hizo
- **`despliegue/manifiestos.py`:**
  - `ip_servicio(nodo)` es la única función que calcula la IP de un Service: `10.43.0.100` más el id del nodo. Si no cae en `10.43.0.0/24`, lanza `ValueError`, y la CLI termina con ese error;
  - cada Service lleva su `clusterIP`;
  - cada Deployment lleva `hostAliases` con todos los nodos y la IP de su Service. `TRUCARDO_NODOS` sigue idéntico a la entrada.
- **`tests/test_manifiestos.py`:** tres tests (ver *Tests*).
- **`README.md`:** en la guía de máquinas reales, de dónde salen esas IPs y qué cambiar si k3s usa otro rango de Services.
- **`experimentos/README.md`:** el caso 6 suma la corrida después de la #52.
- **`PLAN.md`:** D5 dice cómo se resuelve ahora el nombre, y el estado de la #52.

## Por qué así
- **`hostAliases` y no cambiar `TRUCARDO_NODOS`.** Si `TRUCARDO_NODOS` llevara IPs, el valor de los Pods dejaría de ser idéntico al de entrada, y los logs mostrarían IPs en vez de nombres. Con `hostAliases`, el nombre `nodo1` sigue valiendo (D5): sólo cambia quién lo resuelve.
- **IPs fijas en la banda baja del rango.** k3s asigna las `clusterIP` al azar en `10.43.0.0/16`. Kubernetes reserva las primeras 256 para IPs elegidas a mano y asigna las automáticas preferentemente en el resto, así que es difícil que una IP fija choque con un Service creado antes. Se empieza en `.101` para no acercarse a `.1` (`kubernetes`) ni a `.10` (CoreDNS). Alcanza para ids del 1 al 155, mucho más de lo que necesita el plan.
- **Una sola función (DRY).** El Service y los `hostAliases` de todos los Pods toman la IP de `ip_servicio`. No pueden quedar distintas.
- **Alternativas descartadas:**
  - **más réplicas de CoreDNS:** k3s administra ese Deployment como un *addon* y vuelve a ponerlo como estaba al reiniciar;
  - **ir por la IP del Pod:** cambia cada vez que el Pod se recrea.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano. Un subagente implementador escribió primero los tests y después el código y la nota del README;
  - en la revisión se sacó un rechazo del id 0 que el diseño no pedía (`10.43.0.100` es una IP válida de la banda), y se reescribió la nota del README;
  - la prueba de aceptación en el cluster local la hizo el agente principal.

## Tests
- **Agregados** (`tests/test_manifiestos.py`):
  - `test_cada_service_tiene_una_cluster_ip_fija_distinta_y_en_la_banda_baja`;
  - `test_los_host_aliases_tienen_todos_los_nodos_con_la_ip_de_su_service`;
  - `test_un_id_que_no_entra_en_la_banda_da_error`, también por la CLI.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  FALLO  test_cada_service_tiene_una_cluster_ip_fija_distinta_y_en_la_banda_baja: KeyError: 'clusterIP'
  FALLO  test_los_host_aliases_tienen_todos_los_nodos_con_la_ip_de_su_service: KeyError: 'hostAliases'
  FALLO  test_un_id_que_no_entra_en_la_banda_da_error: entrada '200@nodo200:9501:9601' tendria que haber dado ValueError
  ```

## Verificación
```
$ docker compose run --build --rm tests
213 tests, todo ok
```

**Aceptación en el cluster local.** Se borraron los Services, porque la `clusterIP` de un Service existente no se puede cambiar, y se aplicaron los manifiestos nuevos. Después se repitió el experimento 6 con el mismo guion. Queda un solo primario y la partida sigue, con 1 s por jugada por la espera del ack de N3. La evidencia completa está en el caso 6 de `experimentos/README.md`:

```
08:40:18 docker compose stop maquina1 (servidor k3s y N3, primario)
08:40:23 [N2│BACKUP│e=11] nadie me gana (contestaron 1 de 2): me corono
08:40:23 [N1│BACKUP│e=11] N2 es el primario de la epoca 12
08:41:22 quien_es → 1 BACKUP e=12 1230 | 2 PRIMARIO e=12 1230 | 3 no responde
```

## Pendientes o riesgos detectados
- **Un cluster que ya corre con los manifiestos viejos** necesita borrar los Services antes de aplicar los nuevos. Aplicar sin borrar da error, porque la `clusterIP` no se puede cambiar. En el laboratorio se aplica desde cero, así que no hace falta otro paso en el README.
- **Si k3s se instala con otro `--service-cidr`**, las IPs fijas quedan fuera del rango y el `apply` falla con un error claro. Está anotado en el README.
