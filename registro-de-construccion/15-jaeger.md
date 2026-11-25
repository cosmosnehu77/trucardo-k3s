# #15 — Jaeger en docker compose y en k3s

| Campo | Valor |
| --- | --- |
| Issue | #15 |
| Rama | `issue-15-jaeger` |
| Requisitos | RF-16 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
- Jaeger, con versión fija, en `docker-compose.yml`.
- Con `--telemetria`, que el generador agregue:
  - el Deployment y el Service de Jaeger, con la interfaz por NodePort (D6);
  - el destino OTLP en los nodos;
  - `OTEL_RESOURCE_ATTRIBUTES` con el Pod y la máquina, tomados de la *Downward API*.

## Qué se hizo
- **`despliegue/manifiestos.py`:**
  - `manifiestos(..., telemetria=False)` y la opción `--telemetria`, que sólo vale con `--imagen`;
  - con telemetría:
    - al final de la lista, un Deployment y un Service `jaeger` con `jaegertracing/jaeger:2.23.0`;
    - el Service tiene la IP fija `10.43.0.100`;
    - la interfaz va por el NodePort 30686, y OTLP por HTTP por el 4318;
    - cada nodo recibe el `hostAlias` `jaeger`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318`, `K8S_POD_NAME` y `K8S_NODE_NAME` desde la *Downward API*, y `OTEL_RESOURCE_ATTRIBUTES` armado con esas dos.
- **`docker-compose.yml`:**
  - el servicio `jaeger`, en el perfil `telemetria`;
  - `OTEL_EXPORTER_OTLP_ENDPOINT` en el entorno de nodos y clientes. Vacía por defecto, que es lo mismo que no tenerla.
- **`README.md`:** cómo prenderlo en el cluster local y en docker compose.
- **`tests/test_manifiestos.py`:** ver *Tests*.
- **`PLAN.md`:** estado de la #15.

## Por qué así
- **Jaeger también con IP fija y `hostAlias`.** Es la lección de la #52: si los nodos buscaran `jaeger` por CoreDNS, con el servidor de k3s apagado dejarían de mandar trazas, justo en el experimento que más interesa mirar. Usa `10.43.0.100`, la base de la banda: ningún nodo la toma, porque los ids empiezan en 1.
- **El NodePort de la interfaz sale del puerto del Service.** La regla de D6 (puerto + 21000) da 37686 para el 16686 de Jaeger, fuera del rango de NodePort. El Service escucha en 9686, redirige al 16686 del contenedor, y la regla da 30686. Así sigue habiendo una sola regla, en `puerto_externo`.
- **El puerto OTLP no tiene NodePort fijo.** Lo usan sólo los nodos, desde adentro del cluster. Kubernetes le asigna uno cualquiera porque el Service es NodePort, pero nadie lo usa.
- **Los atributos del Pod los lee el SDK solo.** `Resource.create` toma `OTEL_RESOURCE_ATTRIBUTES` por su cuenta: se probó antes de diseñar, y `nodo/` no cambió. Kubernetes arma la variable expandiendo `$(K8S_POD_NAME)` y `$(K8S_NODE_NAME)`, que se definen antes en el mismo contenedor.
- **Sin `--telemetria`, nada cambia.** Se comparó la salida del generador antes y después del cambio: idéntica byte a byte.
- **Cómo se trabajó:**
  - el diseño se fijó de antemano, después de verificar la imagen de Jaeger y que el SDK lee la variable. Un subagente implementador escribió primero los tests y después el código;
  - la prueba en el cluster local la hizo el agente principal.

## Tests
- **Agregados** (`tests/test_manifiestos.py`):
  - `test_sin_telemetria_no_aparece_jaeger_ni_variables_otel`;
  - `test_con_telemetria_agrega_deployment_y_service_jaeger`: la imagen fija, la IP 10.43.0.100, el NodePort 30686 hacia el 16686 y el 4318;
  - `test_con_telemetria_los_nodos_apuntan_a_jaeger_y_declaran_downward_api`;
  - `test_cli_con_telemetria_imprime_json_con_jaeger`;
  - `test_cli_clientes_con_telemetria_termina_con_error`.
- **Fallaron antes del cambio** por la razón esperada (`manifiestos() got an unexpected keyword argument 'telemetria'`, y `--telemetria` desconocido para la CLI).

## Verificación
```
$ docker compose run --build --rm tests
240 tests, todo ok
```

**Criterio de aceptación, en el cluster local.** Se cargaron las imágenes de Trucardo y de Jaeger y se aplicaron los manifiestos con `--telemetria`. Jaeger quedó en `maquina2`. Después se jugó una partida con un cliente automático y se pidió una traza de jugada a la API de Jaeger (`/api/v3/traces`):

```
jugada jugar | trucardo-nodo3 trucardo-nodo3-5796ddb59d-sxvkg maquina1 | seq 1270 rol primario | span f9f20f padre
replica      | trucardo-nodo2 trucardo-nodo2-69f9bb7db-q559w  maquina3 | seq 1270 rol backup   | span 08d683 padre f9f20f
replica      | trucardo-nodo1 trucardo-nodo1-764f5bdc8b-4jn22 maquina2 | seq 1270 rol backup   | span d00eb6 padre f9f20f
```

Cada *span* trae `k8s.pod.name` y `k8s.node.name`, y la jugada tiene una réplica por backup (#14), cada una en su máquina. La jugada no tiene padre porque el cliente automático no exporta trazas; con el cliente de verdad, el padre sería la `jugada` del cliente (#13).

Con docker compose (`OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 docker compose --profile telemetria up`), Jaeger recibió los tres nodos.

## Pendientes o riesgos detectados
- **Jaeger guarda en memoria.** Si su Pod se reinicia o se muda, pierde las trazas. Alcanza para los experimentos. Un almacenamiento persistente sería otra pieza más que desplegar (YAGNI).
- **Los clientes fuera del cluster no mandan trazas en k3s.** El puerto OTLP no tiene NodePort fijo, porque 4318 + 21000 se sale del rango. Si la #16 necesita la traza completa desde el cliente, se le agrega un puerto de Service siguiendo la misma regla que la interfaz.
