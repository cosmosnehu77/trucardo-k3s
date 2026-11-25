# Trucardo en k3s

Trabajo de **promoción** de Sistemas Distribuidos 2026 (UNPSJB). Integrantes: Nehuén García y Alan Viera.

Tomamos **Trucardo** —el servicio de truco distribuido del Proyecto 1, con primario-backup, elección Bully con épocas, log replicado y relojes de Lamport— y lo desplegamos en un cluster **Kubernetes (k3s)** de tres máquinas.

- **Kubernetes** se ocupa de que los procesos existan: los reinicia, los reubica cuando se apaga una máquina y los actualiza.
- **Trucardo** sigue decidiendo quién es el primario y cuál es el estado de cada mesa.

Además:
- **Fase recomendada:** cada nodo guarda su log en un **volumen**, así un apagón de las tres máquinas no pierde las partidas.
- **Fases extra:** observabilidad con **OpenTelemetry** (trazas en Jaeger, métricas y logs en Grafana) y almacenamiento replicado con **Longhorn**, para que el nodo se mude de máquina con su disco.

**Estado (25/11/2026).** Están hechas la fase de despliegue, la recomendada (log en disco) y la de OpenTelemetry (trazas, métricas y logs). De la fase opcional de Longhorn está el generador (`--almacenamiento longhorn`, #30), sin probar en un cluster. Los experimentos (#31) quedan como trabajo futuro (ver [Límites](#límites-y-trabajo-futuro)). El detalle está en la tabla de estado al final de [PLAN.md](PLAN.md).

## Arquitectura: dos capas

```
  clientes, desde fuera del cluster (NodePort: puerto + 21000)
                │
                ▼
┌─ k3s ─────────────────────────────────────────────────────────┐
│                                                               │
│    maquina1: Pod N3, primario                                 │
│    disco: /var/lib/trucardo/nodo3                             │
│       │                     │                                 │
│       │ réplica y latido    │ réplica y latido                │
│       ▼                     ▼                                 │
│    maquina2: Pod N1,     maquina3: Pod N2,                    │
│    backup                backup                               │
│    disco: .../nodo1      disco: .../nodo2                     │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

**Kubernetes hace que los procesos existan.** El generador (`despliegue/manifiestos.py`) arma, desde la misma `TRUCARDO_NODOS` del Proyecto 1:

- un Deployment de una réplica por nodo, con estrategia `Recreate`. Los nodos tienen id: no son réplicas intercambiables (D3, D4);
- un Service por nodo, con el mismo nombre que el host del nodo y una IP fija. Cada Pod lo resuelve por `hostAliases`, sin depender del DNS del cluster (D5, #52);
- una *liveness probe* más lenta que la detección de Trucardo, así Trucardo decide primero y Kubernetes repara después (D7);
- 10 s de tolerancia a una máquina caída, así el Pod se reubica en alrededor de un minuto, y anti-afinidad preferida, para repartir los nodos sin impedir la reubicación (D8, D9);
- un volumen `hostPath` por nodo, `/var/lib/trucardo/nodo<id>`, en la máquina donde corre (D14).

**Trucardo decide quién manda y qué pasó en cada mesa.** No cambió su protocolo del Proyecto 1:

- primario-backup con un log replicado;
- elección Bully con épocas;
- relojes de Lamport.

Se le sumaron tres cosas:

- **el log en disco** (#22): cada op se escribe con `fsync` antes de confirmarse;
- **la recuperación al estilo Raft** (#23, D15): un nodo que vuelve, en la misma máquina o en otra, recorta lo que difiere del primario y recibe sólo lo que le falta;
- **la telemetría opcional** (#11 a #28): trazas, métricas y logs por OpenTelemetry.

Ninguna capa sabe de la otra. Kubernetes no sabe quién es el primario, y Trucardo no sabe que corre en Kubernetes: sólo ve nodos que se caen y vuelven.

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

Cada nodo guarda su log en un volumen (`datos1` a `datos3`), así que las partidas sobreviven a `docker compose down`. Para arrancar de cero, borrá también los volúmenes:

```bash
docker compose down -v
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

**Telemetría (opcional).** Con `--telemetria`, el generador suma un *Collector* de OpenTelemetry, que reparte lo que mandan los nodos: las trazas a Jaeger, las métricas a Prometheus y los logs a Loki. Suma también Grafana, con un tablero de Trucardo. Primero cargá las imágenes en las máquinas:

```bash
for i in jaegertracing/jaeger:2.23.0 otel/opentelemetry-collector:0.165.0 prom/prometheus:v3.16.0 grafana/loki:3.6.22 grafana/grafana:13.3.2; do sh despliegue/cluster-local/cargar-imagen.sh $i; done
```

Después generá los manifiestos con `--telemetria` y aplicalos como antes. Quedan:

- Grafana en <http://172.30.0.11:30300>, con el tablero «Trucardo». Desde una línea de log, el campo `trace_id` lleva a su traza;
- Jaeger en <http://172.30.0.11:30686>;
- Prometheus en <http://172.30.0.11:30090>;
- para que un cliente externo mande sus trazas, `-e OTEL_EXPORTER_OTLP_ENDPOINT=http://172.30.0.11:30318`.

Sin Kubernetes, `OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318 docker compose --profile telemetria up --build` levanta lo mismo, con Grafana en <http://localhost:3000>.

Para consultar quién es el primario desde afuera:

```bash
docker run --rm -it --network trucardo-k3s_maquinas -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.quien_es
```

Si querés correr `kubectl` desde la compu (opcional), el *kubeconfig* queda en `despliegue/cluster-local/salida/kubeconfig.yaml` apuntando a `127.0.0.1:6443`.

Apagá el cluster con:

```bash
docker compose -f despliegue/cluster-local/compose.yaml down
```

Cada máquina guarda los logs de sus nodos en un volumen montado en `/var/lib/trucardo`, así que sobreviven a `down`. Para borrarlos, sumá `-v`.

## Despliegue en tres máquinas reales

Hacen falta tres computadoras Linux con `systemd` en la misma red, cada una con IP fija o reservada, un nombre de host distinto (`hostname`), `sudo` y `curl`. Además, una «compu de armado» con Docker, `python3` y este repo (puede ser una de las tres).

En los ejemplos: `maquina1` con `192.168.0.11` (servidor k3s), `maquina2` con `192.168.0.12` y `maquina3` con `192.168.0.13` (agentes). Reemplazá las IPs por las de ustedes.

### 1. En la compu de armado

Construí la imagen y guardala en un archivo `.tar` para cargarla sin registro de imágenes:

```bash
docker compose build nodo1
```

```bash
docker save trucardo:local -o trucardo.tar
```

Generá los manifiestos desde la raíz del repo:

```bash
TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" python3 -m despliegue.manifiestos --imagen trucardo:local > trucardo.json
```

El generador fija la IP de cada Service (`10.43.0.101` para el nodo 1, y así), para que los nodos se encuentren sin depender de CoreDNS. Esas IPs están dentro del rango de Services que k3s usa por defecto, `10.43.0.0/16`. Si instalás k3s con otro `--service-cidr`, cambialas en `despliegue/manifiestos.py`.

Consultá la versión de k3s fijada en el cluster local y anotala (va donde dice `<version>` más abajo):

```bash
sed -n 's|.*rancher/k3s:\(v.*\)-\(k3s.*\)|\1+\2|p' despliegue/cluster-local/compose.yaml
```

Copiá `trucardo.tar` a las tres máquinas y `trucardo.json` a `maquina1` (con `scp` o en un pendrive):

```bash
scp trucardo.tar trucardo.json usuario@192.168.0.11:
```

```bash
scp trucardo.tar usuario@192.168.0.12:
```

```bash
scp trucardo.tar usuario@192.168.0.13:
```

### 2. En las tres máquinas: firewall

Si `sudo ufw status` dice `inactive`, salteá este paso. Si está activo, las tres primeras reglas son las que pide k3s y las otras dejan pasar a los clientes y el tráfico interno del cluster:

```bash
sudo ufw allow 6443/tcp            # API de Kubernetes (los agentes se unen al servidor)
sudo ufw allow 8472/udp            # red entre Pods (VXLAN de Flannel)
sudo ufw allow 10250/tcp           # kubelet (logs y exec de los Pods)
sudo ufw allow 30000:32767/tcp     # NodePort: los clientes entran por acá
sudo ufw allow from 10.42.0.0/16   # Pods
sudo ufw allow from 10.43.0.0/16   # Services
```

### 3. En maquina1: servidor

Instalá el servidor k3s con la `<version>` del paso 1:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=<version> sh -s - server --disable traefik --disable metrics-server
```

Copiá el token del servidor:

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

### 4. En maquina2 y maquina3: agentes

Uní cada agente al servidor reemplazando `<version>` y `<token>`:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=<version> K3S_URL=https://192.168.0.11:6443 K3S_TOKEN=<token> sh -s - agent
```

### 5. En maquina1: verificar

Esperá a que las tres máquinas aparezcan `Ready`:

```bash
sudo k3s kubectl get nodes -o wide
```

### 6. En las tres: cargar la imagen

En `maquina1`, `maquina2` y `maquina3`, importá la imagen en el containerd de k3s:

```bash
sudo k3s ctr images import trucardo.tar
```

### 7. En maquina1: aplicar y ver los Pods

Aplicá los manifiestos y verificá que corra un Pod por máquina:

```bash
sudo k3s kubectl apply -f trucardo.json
```

```bash
sudo k3s kubectl get pods -o wide
```

### 8. Jugar

Desde la compu de armado (o cualquier compu de la red con Docker y la imagen `trucardo:local`), obtené el valor de `TRUCARDO_NODOS` para clientes externos (`NodePort`, puerto + 21000):

```bash
TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" python3 -m despliegue.manifiestos --clientes 192.168.0.11
```

Reemplazá `<valor>` por esa salida y corré un jugador en cada una de dos terminales o computadoras:

```bash
docker run --rm -it --network host -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.cliente leo
```

```bash
docker run --rm -it --network host -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.cliente beto
```

Para ver quién es el primario:

```bash
docker run --rm -it --network host -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.quien_es
```

### Opcional: volumen replicado con Longhorn

> [!WARNING]
> **Sin probar.** El generador está testeado, pero Longhorn no corre en el cluster local (ver [Límites](#límites-y-trabajo-futuro)), y todavía no se probó en máquinas reales.

Con Longhorn, cada nodo guarda su log en un volumen replicado en las tres máquinas, que viaja con el Pod si se muda. Longhorn necesita `open-iscsi` en cada máquina. En Debian o Ubuntu, en las tres:

```bash
sudo apt install -y open-iscsi && sudo systemctl enable --now iscsid && sudo modprobe iscsi_tcp
```

En `maquina1`, instalá Longhorn (versión fija, D17) y esperá a que todos sus Pods estén `Running`:

```bash
sudo k3s kubectl apply -f https://raw.githubusercontent.com/longhorn/longhorn/v1.13.0/deploy/longhorn.yaml
```

```bash
sudo k3s kubectl -n longhorn-system get pods
```

Hacé que, si se apaga una máquina, Longhorn borre el Pod de un Deployment y libere su volumen. Si no, el Pod nuevo no puede montarlo en otra máquina:

```bash
sudo k3s kubectl -n longhorn-system patch settings.longhorn.io node-down-pod-deletion-policy --type merge -p '{"value":"delete-both-statefulset-and-deployment-pod"}'
```

En la compu de armado, generá los manifiestos con `--almacenamiento longhorn` (un PVC por nodo en lugar del `hostPath`) y aplicalos como en el paso 7:

```bash
TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" python3 -m despliegue.manifiestos --imagen trucardo:local --almacenamiento longhorn > trucardo.json
```

### 9. Desinstalar

En `maquina1`:

```bash
sudo /usr/local/bin/k3s-uninstall.sh
```

En `maquina2` y `maquina3`:

```bash
sudo /usr/local/bin/k3s-agent-uninstall.sh
```

Los logs de los nodos quedan en `/var/lib/trucardo` de cada máquina. Para borrarlos:

```bash
sudo rm -rf /var/lib/trucardo
```

### Si algo falla

- **Logs:** `sudo journalctl -u k3s` (servidor) y `sudo journalctl -u k3s-agent` (agentes).
- **Un agente no aparece en `get nodes`:** desde ese agente, `curl -k https://192.168.0.11:6443` tiene que contestar (un `401` en JSON está bien); si no, revisá el firewall y la IP.
- **Máquinas clonadas con el mismo `hostname`:** k3s no deja entrar a la segunda; cambiá el `hostname` o sumá `--node-name <nombre>` al comando de instalación.
- **Máquinas con varias interfaces de red:** sumá `--node-ip <ip de esa máquina>` al comando de instalación.
- **Pods en `ErrImagePull` o `ImagePullBackOff`:** falta el paso 6 en esa máquina.

## Experimentos

[experimentos/README.md](experimentos/README.md) tiene 19 casos, cada uno con su guion, lo esperado, la evidencia con hora y el porqué. Se corrieron en el cluster local, y cada uno se puede repetir.

| Casos | Qué muestran |
| --- | --- |
| 1 a 6 | Fallas de proceso y de infraestructura: borrar el Pod del primario, colgar un nodo, apagar la máquina de un backup y la del primario, actualizar la versión con una partida en curso, apagar el servidor k3s |
| 7 | El límite: una partición de red deja dos primarios |
| 8 a 11 | Persistencia: un backup reiniciado, un nodo que se muda con un log viejo, el apagón total y la operación confirmada sin acks que se pierde |
| 12 a 15 | Trazas: una jugada replicada, una elección, una puesta al día y el cerebro dividido en Jaeger |
| 16 a 19 | Métricas y logs: el tablero ante una caída y ante el cerebro dividido, de un log a su traza, y qué agrega OpenTelemetry a `kubectl` |

## Límites y trabajo futuro

- **Sin quórum, una partición deja dos primarios** (casos 7, 15 y 17). Las épocas lo resuelven al curarse, pero las ops que el primario viejo confirmó solo se pierden (caso 11). Evitarlo pide confirmar sólo con la mayoría, como Raft.
- **Después de un apagón, el primero en volver se corona solo** (caso 10). Si es un backup atrasado, los que vuelven después pierden lo que él no tenía. Es el mismo límite.
- **El disco es de la máquina, no del nodo** (D14). Un nodo que se muda arranca con lo que haya en la máquina nueva y se pone al día por la red. La fase de Longhorn iba a mostrar la alternativa: un volumen replicado que viaja con el Pod. El generador ya lo arma (#30), pero falta probarlo y comparar (#31). En el cluster local no se puede: Longhorn expone cada volumen por iSCSI, y el iniciador iSCSI del kernel sólo funciona en la red del host, no en la de un contenedor. Hace falta probarlo en máquinas reales o en VMs.
- **Kubernetes no detecta un nodo colgado** (caso 2). La *probe* TCP la contesta el kernel. Trucardo lo resuelve con sus latidos.
- **Los clientes entran por la IP de una máquina.** Si esa máquina se apaga, hay que cambiar de IP (caso 6).
- **La telemetría guarda su historia en el Pod.** Si Prometheus, Loki o Jaeger se mudan de máquina, se pierde. Una partición también corta la telemetría del lado aislado (caso 15).

## Cómo se trabaja

Resumen de [PLAN.md](PLAN.md), sección 1:

- Una issue a la vez, en orden. Una rama `issue-NN-descripcion` por issue.
- Test que falla primero; después el cambio más chico que lo hace pasar.
- **Un solo commit por issue**, y sólo si pasa la suite completa.
- Un PR por issue, que se mergea con *merge commit*.
- La rama de una issue se borra cuando se crea la de la siguiente.
- Cada issue deja su registro en `registro-de-construccion/`.
- Principios: YAGNI, DRY y Clean Code según la skill `ub-mode` (`.claude/skills/ub-mode/`).

## Créditos

Basado en **Trucardo**, el Proyecto 1 de Sistemas Distribuidos 2026: el juego, el protocolo primario-backup, la elección Bully con épocas, el log replicado, los relojes de Lamport y los clientes. La historia completa de ese desarrollo, con sus autores, se conserva en este repositorio, y su estado final está en el tag `proyecto1-base`.

El despliegue en k3s, la persistencia, la observabilidad y los experimentos son de este trabajo de promoción. Cada issue dejó su registro en [registro-de-construccion/](registro-de-construccion/), con su autor y cómo se trabajó.
