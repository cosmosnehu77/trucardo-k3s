# Trucardo en k3s

Trabajo de **promoción** de Sistemas Distribuidos 2026 (UNPSJB). Integrantes: Nehuén García y Alan Viera.

Tomamos **Trucardo** —el servicio de truco distribuido del Proyecto 1, con primario-backup, elección Bully con épocas, log replicado y relojes de Lamport— y lo desplegamos en un cluster **Kubernetes (k3s)** de tres máquinas.

- **Kubernetes** se ocupa de que los procesos existan: los reinicia, los reubica cuando se apaga una máquina y los actualiza.
- **Trucardo** sigue decidiendo quién es el primario y cuál es el estado de cada mesa.

Además:
- **Fase recomendada:** cada nodo guarda su log en un **volumen**, así un apagón de las tres máquinas no pierde las partidas.
- **Fases extra:** observabilidad con **OpenTelemetry** (trazas en Jaeger, métricas y logs en Grafana) y almacenamiento replicado con **Longhorn**, para que el nodo se mude de máquina con su disco.

> [!NOTE]
> **Estado:** en construcción. Hoy el repositorio ya tiene el generador de manifiestos, el cluster local de desarrollo y la guía para tres máquinas reales sobre la base del Proyecto 1 (tag `proyecto1-base`). El despliegue en k3s se construye issue por issue; ver la tabla de estado al final de [PLAN.md](PLAN.md).

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

### 9. Desinstalar

En `maquina1`:

```bash
sudo /usr/local/bin/k3s-uninstall.sh
```

En `maquina2` y `maquina3`:

```bash
sudo /usr/local/bin/k3s-agent-uninstall.sh
```

### Si algo falla

- **Logs:** `sudo journalctl -u k3s` (servidor) y `sudo journalctl -u k3s-agent` (agentes).
- **Un agente no aparece en `get nodes`:** desde ese agente, `curl -k https://192.168.0.11:6443` tiene que contestar (un `401` en JSON está bien); si no, revisá el firewall y la IP.
- **Máquinas clonadas con el mismo `hostname`:** k3s no deja entrar a la segunda; cambiá el `hostname` o sumá `--node-name <nombre>` al comando de instalación.
- **Máquinas con varias interfaces de red:** sumá `--node-ip <ip de esa máquina>` al comando de instalación.
- **Pods en `ErrImagePull` o `ImagePullBackOff`:** falta el paso 6 en esa máquina.

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
