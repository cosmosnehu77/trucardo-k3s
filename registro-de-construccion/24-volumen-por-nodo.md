# #24 — Un volumen por nodo en docker compose y en k3s

| Campo | Valor |
| --- | --- |
| Issue | #24 |
| Rama | `issue-24-volumen-por-nodo` |
| Requisitos | RF-19 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que cada nodo tenga su volumen, montado en el directorio de `TRUCARDO_DATOS`:
- en `docker compose`, un volumen con nombre;
- en k3s, un `hostPath` por nodo (D14), armado por una sola función, con el punto de montaje y la variable tomados de la misma constante;
- en el cluster local, un volumen en `/var/lib/trucardo` de cada máquina simulada.

## Qué se hizo
- **`despliegue/manifiestos.py`:**
  - `_ruta_datos(nodo)` es la única función que arma la ruta en la máquina: `/var/lib/trucardo/nodo<id>`;
  - cada Deployment tiene el volumen `datos` (`hostPath`, tipo `DirectoryOrCreate`), montado en `_DIRECTORIO_DATOS`;
  - la variable `TRUCARDO_DATOS` toma su valor de esa misma constante. Sin PVC.
- **`docker-compose.yml`:**
  - el entorno común pasó a un ancla (`x-entorno`), porque el `<<` de YAML no mezcla mapas anidados;
  - `x-nodo` le suma `TRUCARDO_DATOS: &datos /datos`;
  - cada nodo monta su volumen `datosN` con `target: *datos`. El punto de montaje se escribe una sola vez;
  - clientes, tests y demo no reciben la variable.
- **`despliegue/cluster-local/compose.yaml`:** volúmenes `datos-maquina1` a `datos-maquina3` en `/var/lib/trucardo`, con el mismo recurso del ancla.
- **`README.md`:**
  - en `docker compose` y en el cluster local, los datos sobreviven a `down`, y `down -v` los borra;
  - en la guía de máquinas reales, cómo borrar `/var/lib/trucardo` al desinstalar.
- **`PLAN.md`:** estado de la #24.

## Por qué así
- **`hostPath` y no un PVC (D14).** Un PVC de `local-path` ata el Pod a su máquina: si se apaga, el Pod queda `Pending`. Con `hostPath`, el Pod que se muda arranca con lo que haya en la máquina nueva y se pone al día por la red. La #23 garantiza que eso sea consistente.
- **La ruta lleva el id del nodo.** Si dos nodos terminan en la misma máquina, no se pisan. Se vio en la verificación: después de la mudanza, `maquina1` tiene `nodo1` y `nodo2`.
- **El volumen del cluster local.** `docker compose stop` conserva el disco de una máquina simulada, pero recrearla no. Con el volumen, el apagón total de la #25 se puede probar también recreando las máquinas.
- **Cómo se trabajó:**
  - un subagente implementador escribió primero los tests y después los cambios, con el diseño fijado de antemano, incluida la sintaxis larga de volúmenes para no repetir el punto de montaje;
  - se revisó el diff;
  - el README y la prueba de aceptación se hicieron aparte.

## Tests
- **Agregados** (`tests/test_manifiestos.py`):
  - `test_cada_nodo_tiene_su_volumen_hostpath`: rutas distintas y `DirectoryOrCreate`;
  - `test_el_punto_de_montaje_y_trucardo_datos_coinciden`;
  - `test_no_hay_ningun_pvc`.
- **Fallaron antes del cambio** por la razón esperada:

  ```
  FALLO  test_cada_nodo_tiene_su_volumen_hostpath: KeyError: 'volumes'
  FALLO  test_el_punto_de_montaje_y_trucardo_datos_coinciden: KeyError: 'volumes'
  ```

  `test_no_hay_ningun_pvc` pasaba ya, porque nunca hubo PVC. Queda como regresión.

## Verificación
```
$ docker compose run --build --rm tests
210 tests, todo ok
```

**`docker compose`:** los tres nodos levantan con `/datos` y escriben su época ahí (`ls /datos` → `epoca`). `docker compose config` muestra `TRUCARDO_DATOS` sólo en los nodos.

**Cluster local (#8), desde cero.** Con los pasos del README, y con `leo` y `beto` en una mesa:

```
$ … kubectl get pods -o wide
trucardo-nodo1-…   Running   maquina2
trucardo-nodo2-…   Running   maquina1
trucardo-nodo3-…   Running   maquina3

maquina1: /var/lib/trucardo/nodo2 ops=2
maquina2: /var/lib/trucardo/nodo1 ops=2
maquina3: /var/lib/trucardo/nodo3 ops=2
```

1. **Un nodo reiniciado conserva su log.** Al borrar el Pod de N1, vuelve en `maquina2` con la época 1 desde la primera línea y sin puesta al día:

   ```
   $ … kubectl delete pod -l nodo=1
   trucardo-nodo1-…-zv4sm   Running   maquina2
   23:53:43 [N1│BACKUP│e=1│L=0] escuchando en PYRO:truco@<tu-ip>:9501 · …
   23:53:44 [N1│BACKUP│e=1│L=323] N3 es el primario de la epoca 1
   ```

2. **Uno que se muda de máquina se pone al día por la red.** Con `maquina2` acordonada, el Pod de N1 va a `maquina1`. Arranca vacío, con la época 0, y recibe las dos operaciones:

   ```
   $ … kubectl cordon maquina2 && … kubectl delete pod -l nodo=1
   trucardo-nodo1-…-gmgh4   Running   maquina1
   23:54:06 [N1│BACKUP│e=0│L=0] escuchando en PYRO:truco@<tu-ip>:9501 · …
   23:54:07 [N1│BACKUP│e=0│L=471] N3 es el primario de la epoca 1
   23:54:07 [N1│BACKUP│e=1│L=477] puesta al dia: de la op 0 a la 2

   maquina1: /var/lib/trucardo/nodo1 ops=2 /var/lib/trucardo/nodo2 ops=2
   maquina2: /var/lib/trucardo/nodo1 ops=2          # el log viejo queda en la máquina de antes
   ```

## Pendientes o riesgos detectados
- **El log viejo queda en la máquina de antes.** Si N1 vuelve más tarde a `maquina2`, arranca con ese log, que puede estar atrasado o divergir. La #23 lo resuelve: se pone al día o recorta. Es parte del experimento 2 de la #25.
- **Un `hostPath` no protege contra la pérdida de una máquina.** Si su disco se pierde, el nodo depende de los otros dos. Es el motivo de la fase opcional de Longhorn (RF-24).
