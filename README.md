# Trucardo en k3s

Trabajo de **promoción** de Sistemas Distribuidos 2026 (UNPSJB). Integrantes: Nehuén García y Alan Viera.

Tomamos **Trucardo** —el servicio de truco distribuido del Proyecto 1, con primario-backup, elección Bully con épocas, log replicado y relojes de Lamport— y lo desplegamos en un cluster **Kubernetes (k3s)** de tres máquinas.

- **Kubernetes** se ocupa de que los procesos existan: los reinicia, los reubica cuando se apaga una máquina y los actualiza.
- **Trucardo** sigue decidiendo quién es el primario y cuál es el estado de cada mesa.

Además:
- **Fase recomendada:** cada nodo guarda su log en un **volumen**, así un apagón de las tres máquinas no pierde las partidas.
- **Fases extra:** observabilidad con **OpenTelemetry** (trazas en Jaeger, métricas y logs en Grafana) y almacenamiento replicado con **Longhorn**, para que el nodo se mude de máquina con su disco.

> [!NOTE]
> **Estado:** en construcción. Hoy el repositorio ya tiene el generador de manifiestos y el cluster local de desarrollo sobre la base del Proyecto 1 (tag `proyecto1-base`). El despliegue en k3s se construye issue por issue; ver la tabla de estado al final de [PLAN.md](PLAN.md).

## Documentos

| Documento | Para qué |
| --- | --- |
| [REQUISITOS.md](REQUISITOS.md) | Qué tiene que hacer el proyecto, glosario y qué queda fuera de alcance |
| [PLAN.md](PLAN.md) | Reglas de trabajo, decisiones de diseño y las issues por fase. **Leer la sección 1 antes de tocar el código** |
| [registro-de-construccion/](registro-de-construccion/) | Un registro por issue resuelta: qué se hizo y por qué |

## Cómo correrlo hoy (una sola máquina, con Docker)

Hace falta Docker con el plugin `compose`. Todos los comandos se corren desde la raíz del repo.

Levantar los tres nodos (los logs salen mezclados, con el nombre de cada nodo adelante):

```bash
docker compose up --build
```

Un jugador en cada una de otras dos terminales:

```bash
docker compose run --rm cliente leo
```

```bash
docker compose run --rm cliente beto
```

Correr la suite de tests (`--build` hace que la imagen tome el código actual):

```bash
docker compose run --build --rm tests
```

Una vez por clon, activar el *hook* que corre la suite antes de cada commit y lo rechaza si falla:

```bash
git config core.hooksPath .githooks
```

En GitHub, cada PR corre el mismo *hook* como verificación (`.github/workflows/suite.yml`).

La guía completa del Proyecto 1 está en el [README del tag `proyecto1-base`](https://github.com/cosmosnehu77/trucardo-k3s/blob/proyecto1-base/README.md). Ahí se explica cómo jugar, cómo correrlo en varias computadoras sin Kubernetes, cómo matar al primario y cómo seguir una partida.

## Cluster local de desarrollo (k3s en contenedores)

Simula tres máquinas con k3s en contenedores (`maquina1` servidor, `maquina2` y `maquina3` agentes), con IPs fijas `172.30.0.11` a `172.30.0.13`. La versión de k3s está fijada en `despliegue/cluster-local/compose.yaml`. El `python3` de la compu sólo corre el generador (biblioteca estándar); todo lo demás va en contenedores.

Construí la imagen `trucardo:local`:

```bash
docker compose build nodo1
```

Levantá el cluster:

```bash
docker compose -f despliegue/cluster-local/compose.yaml up -d
```

Esperá a que las tres máquinas estén `Ready`:

```bash
docker compose -f despliegue/cluster-local/compose.yaml exec maquina1 kubectl get nodes
```

Cargá la imagen en las tres máquinas:

```bash
sh despliegue/cluster-local/cargar-imagen.sh
```

Generá los manifiestos y aplicalos en el cluster:

```bash
TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" python3 -m despliegue.manifiestos --imagen trucardo:local > trucardo.json
```

```bash
docker compose -f despliegue/cluster-local/compose.yaml exec -T maquina1 kubectl apply -f - < trucardo.json
```

Verificá los Pods (uno por máquina):

```bash
docker compose -f despliegue/cluster-local/compose.yaml exec maquina1 kubectl get pods -o wide
```

El cliente corre fuera del cluster y entra por `NodePort` (puerto + 21000). Obtené el valor de `TRUCARDO_NODOS` para clientes externos:

```bash
TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" python3 -m despliegue.manifiestos --clientes 172.30.0.11
```

Reemplazá `<valor>` por esa salida y corré un jugador en cada una de dos terminales:

```bash
docker run --rm -it --network trucardo-k3s_maquinas -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.cliente leo
```

```bash
docker run --rm -it --network trucardo-k3s_maquinas -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.cliente beto
```

Para consultar quién es el primario desde afuera:

```bash
docker run --rm -it --network trucardo-k3s_maquinas -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.quien_es
```

Si querés correr `kubectl` desde la compu (opcional), el *kubeconfig* queda en `despliegue/cluster-local/salida/kubeconfig.yaml` apuntando a `127.0.0.1:6443`.

Apagá el cluster con:

```bash
docker compose -f despliegue/cluster-local/compose.yaml down
```

## Cómo se trabaja

Resumen de [PLAN.md](PLAN.md), sección 1:

- Una issue a la vez, en orden. Una rama `issue-NN-descripcion` por issue.
- Test que falla primero; después el cambio más chico que lo hace pasar.
- **Un solo commit por issue**, y sólo si pasa la suite completa.
- Un PR por issue, que se mergea con *merge commit*.
- La rama de una issue se borra cuando se crea la de la siguiente.
- Cada issue deja su registro en `registro-de-construccion/`.
- Principios: YAGNI, DRY y Clean Code según la skill `ub-mode` (`.claude/skills/ub-mode/`).

## Origen

Basado en Trucardo, Proyecto 1 de Sistemas Distribuidos 2026. La historia completa de ese desarrollo, con sus autores, se conserva en este repositorio.
