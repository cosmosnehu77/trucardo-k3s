# #7 — Tolerancia a fallas de infraestructura

| Campo | Valor |
| --- | --- |
| Issue | #7 |
| Rama | `issue-07-tolerancia-a-fallas-de-infraestructura` |
| Requisitos | RF-04, RF-05, RF-06, RNF-08 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que el generador agregue a cada Deployment:
- una *liveness probe* TCP al puerto del cluster que detecte **después** que Trucardo (D7);
- tolerancias de 10 s a máquinas caídas (D8);
- anti-afinidad **preferida** (D9).

Además, verificar con qué señal Kubernetes detiene el contenedor, porque la imagen declara `STOPSIGNAL SIGINT`.

## Qué se hizo
- **`despliegue/manifiestos.py`:**
  - `_probe(nodo)`: `tcpSocket` al puerto del cluster, con `failureThreshold` 3 y `periodSeconds` igual al menor entero que hace que período × 3 > `TIMEOUT_CAIDO`. `TIMEOUT_CAIDO` se lee de `nodo/config.py` **al generar**, no al importar. Con el valor actual (3 s) da 2 s × 3 = 6 s;
  - `_tolerancias()`: `node.kubernetes.io/unreachable` y `node.kubernetes.io/not-ready`, ambas `NoExecute` y de 10 s (`_TOLERANCIA_SEGUNDOS`);
  - `_anti_afinidad()`: `podAntiAffinity` **preferida** (peso 100) entre Pods `app: trucardo`, por máquina (`kubernetes.io/hostname`);
  - la constante `_APP` reemplaza el literal `"trucardo"` en las etiquetas y en la afinidad (DRY).
- **`tests/test_manifiestos.py`:** ver *Tests*.
- **`PLAN.md`:** estado de la #7.
- **`Dockerfile`:** sin cambios. `STOPSIGNAL SIGINT` funciona en k3s (ver *Verificación*).

## Por qué así
- **La probe se calcula desde `nodo/config.py` (D7, DRY).** Si Kubernetes reiniciara un nodo antes de que Trucardo lo dé por caído, se pisarían las dos reparaciones. Leer `TIMEOUT_CAIDO` al generar hace que cambiarlo en un solo lugar mueva también la probe.
- **TCP al puerto del cluster.** Es el puerto que usan latidos y elecciones. Si no acepta conexiones, el nodo no participa del cluster.
- **Sin `initialDelaySeconds`, *readiness probe* ni recursos (YAGNI).** El puerto del cluster se abre en `Membresia.arrancar()`, antes que Pyro, y en la prueba en k3s ningún Pod se reinició.
- **Tolerancias de 10 s (D8).** Con las 300 s por defecto, un nodo en una máquina apagada tardaría 5 minutos en reubicarse (RF-05).
- **Anti-afinidad preferida y no obligatoria (D9).** Si fuera obligatoria, con una máquina caída el Pod reubicado no tendría dónde ir (RF-06).
- **Cómo se trabajó:**
  - un subagente implementador escribió primero los tests y después el código, con el diseño fijado de antemano;
  - el diff se revisó contra PLAN 1.1. La verificación en k3s se hizo aparte.

## Tests
- **Agregados** (`tests/test_manifiestos.py`):
  - `test_la_probe_apunta_al_puerto_del_cluster`;
  - `test_la_probe_detecta_despues_que_trucardo`: para `TIMEOUT_CAIDO` de 0,5, 3, 10 y 47,3 s, período × fallas lo supera, y el período es un entero ≥ 1. Así el test **sigue siendo cierto si se cambia** `TIMEOUT_CAIDO`, como pide la issue;
  - `test_las_tolerancias_son_de_10_segundos`;
  - `test_la_anti_afinidad_es_preferida`: tiene la preferida y no tiene la obligatoria.
- **Los cuatro fallaron antes del cambio** por la razón esperada:

  ```
  test_la_probe_apunta_al_puerto_del_cluster KeyError('livenessProbe')
  test_la_probe_detecta_despues_que_trucardo KeyError('livenessProbe')
  test_las_tolerancias_son_de_10_segundos    KeyError('tolerations')
  test_la_anti_afinidad_es_preferida         KeyError('affinity')
  ```

## Verificación
```
$ docker compose run --build --rm tests
193 tests, todo ok
```

**En un k3s efímero** (`rancher/k3s:v1.37.2-k3s1` en Docker). Los criterios de aceptación formales son de la #8 y la #10.

- La API acepta los manifiestos, y los tres Pods quedan `Running` sin reinicios. La probe y las tolerancias quedan como se generaron:

  ```
  {"failureThreshold":3,"periodSeconds":2,"successThreshold":1,"tcpSocket":{"port":9601},"timeoutSeconds":1}
  [{"effect":"NoExecute","key":"node.kubernetes.io/unreachable","operator":"Exists","tolerationSeconds":10},
   {"effect":"NoExecute","key":"node.kubernetes.io/not-ready","operator":"Exists","tolerationSeconds":10}]
  ```

- **Señal de parada.** La imagen importada en k3s conserva `"StopSignal": "SIGINT"`. Se detuvo el contenedor del nodo 1 con `crictl stop`, que es la misma llamada CRI (`StopContainer`) que usa el kubelet:

  ```
  exitCode= 0 Completed 00:23:26.864 -> 00:24:28.273
  ```

  Terminó con 0, en alrededor de un segundo. Para interpretar ese 0 se contrastaron las dos señales con Docker puro:

  ```
  SIGINT  -> exit 0
  SIGTERM -> exit 137     # no se detuvo: hubo que matarlo con SIGKILL
  ```

  El nodo corre como **PID 1** dentro del contenedor y no instala un manejador para SIGTERM. El kernel no le aplica a PID 1 la acción por defecto de una señal sin manejador, así que **ignora el SIGTERM**. Con SIGINT, Python sí tiene manejador y sale con 0.

  **Conclusión:** k3s respeta `STOPSIGNAL SIGINT` y no hace falta ajustar nada. Sin esa línea, cada nodo tardaría los 30 s de gracia de Kubernetes en detenerse y terminaría con SIGKILL.
- El log del nodo no muestra «chau.» al detenerse. `daemon.requestLoop()` de Pyro5 atrapa el Ctrl+C y termina normalmente, así que el `except KeyboardInterrupt` de `nodo/servidor.py` no llega a correr. Pasaba igual en el Proyecto 1 con `docker compose stop` y no afecta la parada: el `finally` cierra la membresía igual.

## Pendientes o riesgos detectados
- **El «chau.» que nunca se ve.** Es código del Proyecto 1 y no lo pide esta issue (YAGNI). Si molesta en los experimentos de la #10, se puede abrir una issue.
- **Al borrar un Pod se vio una reelección.** Los dos que quedaron se dieron por caídos entre sí antes de que ganara N2, en la época 2. El cluster convergió a un solo primario, y el Pod nuevo de N3 volvió a entrar. Corresponde observarlo con calma en los experimentos de falla de la #10.
