# #28 — Collector, Prometheus, Loki y Grafana

| Campo | Valor |
| --- | --- |
| Issue | #28 |
| Rama | `issue-28-collector-y-grafana` |
| Requisitos | RF-21, RF-22, RF-23 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
- Un *Collector* de OpenTelemetry que reciba OTLP y reparta: las trazas a Jaeger, las métricas a Prometheus y los logs a Loki.
- Que los nodos apunten al *Collector*, cambiando un solo valor (D16).
- Grafana con sus fuentes y un tablero de Trucardo, provisto por archivos:
  - rol y época;
  - atraso de cada backup;
  - operaciones por segundo y latencia p99;
  - primarios simultáneos;
  - un enlace de cada log a su traza.
- Todo en `docker-compose.yml` y en el generador con `--telemetria`.

## Qué se hizo
- **`despliegue/observabilidad/`** (nuevo), la única copia de cada configuración, que usan docker compose y el generador:
  - `collector.json`: el receptor OTLP por HTTP, un `batch` y tres canalizaciones con exportadores `otlp_http`;
  - `prometheus.json`: promueve a etiquetas `service.name`, `k8s.pod.name` y `k8s.node.name`;
  - `fuentes.yaml`, `tableros.yaml` y `tablero-trucardo.json`: las fuentes (Prometheus, Loki con el campo derivado `trace_id` → Jaeger), el proveedor de tableros y el tablero.
- **`docker-compose.yml`:**
  - `collector`, `prometheus`, `loki` y `grafana` en el perfil `telemetria`;
  - Jaeger ya no publica su 4318: ahora recibe del *Collector*.
- **`despliegue/manifiestos.py`:**
  - una tabla única de los cinco servicios de observabilidad, de la que salen sus Deployments, Services y ConfigMaps;
  - IPs fijas de `10.43.0.96` a `.100`, y `hostAliases` de los cinco en cada Pod;
  - NodePorts 30686 (Jaeger), 30318 (OTLP del *Collector*, para clientes externos), 30090 (Prometheus) y 30300 (Grafana). Loki queda sólo dentro del cluster;
  - los nodos mandan a `http://collector:4318`.
- **`Dockerfile`:** copia `docker-compose.yml` a la imagen, para el test que compara sus imágenes con las del generador.
- **Dos correcciones de código**, encontradas al mirar el tablero:
  - **`nodo/telemetria.py`:** los histogramas usan cubos en segundos. Los del SDK están pensados para milisegundos (0, 5, 10…), y la p99 daba unos 5 s con jugadas de milisegundos;
  - **`nodo/cluster/replica.py`:** cada ack de réplica actualiza el último `seq` conocido del backup. Con sólo el latido, el atraso de un backup al día marcaba 3 a 5 ops.
- **`README.md`:** cómo prender la telemetría y dónde queda cada interfaz.
- **`PLAN.md`:** estado de la #28.

## Por qué así
- **Las configuraciones son archivos y el generador los lee.** Docker compose los monta y el generador los mete en ConfigMaps, así que hay una sola copia de cada una (DRY). Están en JSON, que el *Collector* y Prometheus aceptan como YAML (D2). Las de Grafana usan la extensión `.yaml` porque Grafana sólo lee esa, aunque el contenido es JSON.
- **Un *Collector* sin módulos extra.** Prometheus 3 recibe OTLP (`--web.enable-otlp-receiver`) y Loki 3 también (`/otlp`). Así alcanza con la imagen base del *Collector* y su exportador `otlp_http`, sin la distribución *contrib*.
- **IPs fijas y `hostAliases` para todos.** Es la lección de la #52, extendida: sin CoreDNS, los nodos siguen llegando al *Collector*, y el *Collector* a Jaeger, Prometheus y Loki. Una sola tabla define nombre, IP, puertos y configuración de cada servicio.
- **El tablero mira los últimos 15 s.** Las métricas llegan por OTLP, empujadas cada 5 s, y Prometheus no marca como vencida una serie que dejó de llegar. Sin `last_over_time(...[15s])`, un primario muerto seguiría contando cinco minutos en «primarios simultáneos».
- **Del log a la traza.** Loki guarda `trace_id` como metadato de cada línea (#27). El campo derivado de la fuente Loki lo convierte en un enlace a Jaeger.
- **Grafana sin usuario.** El acceso anónimo como administrador sirve para la demo en una red local. No es para exponer.
- **Cómo se trabajó:**
  - las configuraciones y el tablero los armó el agente principal, probándolos con docker compose hasta que llegaron las tres señales;
  - un subagente implementador hizo el generador, las dos correcciones y sus tests, siempre los tests primero. Además, señaló que en k3s Grafana buscaba a Jaeger en el 16686, que el Service no exponía: se agregó ese puerto, sólo interno;
  - se revisó el diff y se sacó un `with lock` de más en `replicar`, que ya corre con el lock tomado.

## Tests
- **Agregados:**
  - en `tests/test_manifiestos.py`:
    - la pila completa con sus imágenes e IPs fijas;
    - los ConfigMaps;
    - las tres canalizaciones del *Collector*;
    - los NodePorts y Loki sin NodePort;
    - los `hostAliases` en todos los Pods;
    - que los nodos apunten al *Collector*;
    - que las imágenes coincidan con las de `docker-compose.yml`;
  - en `tests/test_metricas.py`: `test_los_histogramas_usan_cubos_en_segundos` y `test_tras_una_jugada_replicada_el_atraso_es_cero_sin_esperar_latido`.
- **Cambiados:** los de la #15 que esperaban a Jaeger como destino de los nodos.
- **Fallaron antes del cambio**, por la razón esperada.

## Verificación
```
$ docker compose run --build --rm tests
256 tests, todo ok
```

Sin `--telemetria`, la salida del generador es idéntica byte a byte a la de antes.

**Criterio de aceptación, en el cluster local.** Se aplicaron los manifiestos con `--telemetria` (8 Pods) y se jugó con un cliente automático que manda por el 30318:

```
primario   [('1', 'maquina2', '0'), ('2', 'maquina3', '1'), ('3', 'maquina1', '0')]
primarios simultaneos 1
atraso     [('1', '0'), ('3', '0')]
p99        0.399
log de N3 en Loki:  trace_id 672944c8377c42d07069f769c9f23add  «op 2306 · jugar · leo · mesa 667ea7»
esa traza, pedida a Jaeger a través de Grafana: encontrada
```

El tablero muestra los tres nodos, y desde un log se llega a su traza.

## Pendientes o riesgos detectados
- **Los logs muestran sus atributos en el panel** (`code_*`, `trucardo_*`). Sirven para filtrar, aunque ocupan lugar. Se podrían descartar en el *Collector*, pero eso pide la distribución *contrib*.
- **Prometheus, Loki y Jaeger guardan en el disco del contenedor**, o en memoria. Si su Pod se muda, se pierde la historia. Alcanza para los experimentos.
