# #9 — Despliegue en máquinas reales

| Campo | Valor |
| --- | --- |
| Issue | #9 |
| Rama | `issue-09-guia-maquinas-reales` |
| Requisitos | RF-03, RF-05, RNF-06 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Una guía en el README para tres computadoras Linux de la misma red: instalar el servidor y los agentes k3s, abrir los puertos 6443/TCP, 8472/UDP y 10250/TCP, cargar la imagen en cada máquina, generar y aplicar los manifiestos, y jugar.

## Qué se hizo
- **`README.md`:**
  - sección «Despliegue en tres máquinas reales», en nueve pasos: armado en una compu con Docker, firewall, servidor, agentes, verificación, carga de la imagen, manifiestos, partida y desinstalación;
  - «Si algo falla», con los problemas típicos de un laboratorio: logs, agente que no se une, máquinas clonadas con el mismo `hostname`, varias interfaces de red e imagen sin cargar;
  - la nota de estado, actualizada.
- **`PLAN.md`:** estado de la #9.

## Por qué así
- **La versión de k3s no se escribe en la guía (DRY).** Su fuente única es `despliegue/cluster-local/compose.yaml` (PLAN 1.1). La guía la deriva de ahí con un `sed` que pasa la etiqueta de la imagen (`v…-k3s1`) al formato del instalador (`v…+k3s1`). Cambiar la versión sigue tocando un solo archivo.
- **Una «compu de armado».** Construir la imagen y generar los manifiestos piden Docker, `python3` y el repo. Las tres máquinas sólo necesitan `systemd`, `sudo` y `curl`. La imagen viaja como `.tar` (D10): no hace falta un registro.
- **Además de los tres puertos de la issue, se abren otros tres:**
  - el rango de NodePort (30000–32767/TCP): sin él los clientes externos no entran (D6);
  - las redes de Pods (10.42.0.0/16) y de Services (10.43.0.0/16) de k3s: con el firewall activo, el tráfico entre Pods de máquinas distintas también pasa por las reglas de entrada. Es lo que recomienda la documentación de k3s para `ufw`.
- **Clientes con `--network host`.** En una compu real, el cliente ve la red del laboratorio igual que la compu, y no hace falta saber el nombre de una red de Docker.
- **Cómo se trabajó:**
  - los comandos se fijaron primero y se probaron en la simulación de abajo;
  - un subagente redactor escribió la sección del README con esos comandos exactos, sin poder cambiarlos;
  - se revisó el diff y se ajustó una línea: sin la imagen, el Pod también puede quedar en `ImagePullBackOff`.

## Tests
Sin tests nuevos: es documentación (PLAN 1.4). La suite sigue pasando:

```
$ docker compose run --build --rm tests
193 tests, todo ok
```

## Verificación
**Simulada, con «VMs» livianas.** La issue pide verificar en las máquinas del laboratorio o en VMs. Se simularon tres computadoras Debian 12 con `systemd` como PID 1, una por contenedor, en una red de Docker con IPs fijas (192.168.77.11 a .13). Así el instalador oficial de k3s corre igual que en una máquina real: crea y arranca los servicios `k3s` y `k3s-agent` de `systemd`.

```dockerfile
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv dbus curl ca-certificates ufw iptables iproute2 sudo procps kmod && rm -rf /var/lib/apt/lists/* \
 && systemctl mask getty@tty1.service systemd-logind.service
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
```

```
docker network create --subnet 192.168.77.0/24 lab09
docker run -d --name maquina$i --hostname maquina$i --privileged --cgroupns=private \
  --tmpfs /run --tmpfs /run/lock -v /lib/modules:/lib/modules:ro \
  -v /var/lib/rancher -v /var/lib/kubelet --network lab09 --ip 192.168.77.1$i maquina-sim:09
```

En cada máquina se **activó `ufw` con `deny incoming`**, como en un laboratorio con el firewall prendido, y se corrieron los pasos de la guía tal cual. Lo único que se cambió fueron las IPs. La compu de armado fue la del desarrollador, y el `scp` se reemplazó por `docker cp`.

```
$ [maquina1] sudo ufw status | head -1
Status: active
$ [maquina1..3] sudo ufw allow …           # las seis reglas del paso 2
$ sed -n 's|…|\1+\2|p' despliegue/cluster-local/compose.yaml
v1.37.2+k3s1
$ [maquina1] curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.37.2+k3s1 sh -s - server --disable traefik --disable metrics-server
[INFO]  systemd: Starting k3s
$ [maquina2] curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.37.2+k3s1 K3S_URL=https://192.168.77.11:6443 K3S_TOKEN=<token> sh -s - agent
[INFO]  systemd: Starting k3s-agent
(lo mismo en maquina3)

$ [maquina1] sudo k3s kubectl get nodes -o wide
NAME       STATUS   ROLES           VERSION        INTERNAL-IP     OS-IMAGE
maquina1   Ready    control-plane   v1.37.2+k3s1   192.168.77.11   Debian GNU/Linux 12 (bookworm)
maquina2   Ready    <none>          v1.37.2+k3s1   192.168.77.12   Debian GNU/Linux 12 (bookworm)
maquina3   Ready    <none>          v1.37.2+k3s1   192.168.77.13   Debian GNU/Linux 12 (bookworm)

$ [maquina1..3] sudo k3s ctr images import trucardo.tar
docker.io/library/trucardo:local   saved

$ [maquina1] sudo k3s kubectl apply -f trucardo.json
deployment.apps/trucardo-nodo1 created
service/nodo1 created
(…nodo2 y nodo3)

$ [maquina1] sudo k3s kubectl get pods -o wide
NAME                              READY   STATUS    RESTARTS   NODE
trucardo-nodo1-55574b68b6-msf8c   1/1     Running   0          maquina2
trucardo-nodo2-9b89b6d7c-ngks8    1/1     Running   0          maquina3
trucardo-nodo3-5775d4c6dd-rxzh9   1/1     Running   0          maquina1
```

Desde la compu de armado, con `--network host`:

```
$ TRUCARDO_NODOS=… python3 -m despliegue.manifiestos --clientes 192.168.77.11
1@192.168.77.11:30501:30601,2@192.168.77.11:30502:30602,3@192.168.77.11:30503:30603

leo:   Estas en la mesa 8def0f · leo 0 vs 0 beto · a 15 · mano 1 · sos mano
beto:  Estas en la mesa 8def0f · beto 0 vs 0 leo · a 15 · mano 1 · es mano el rival

$ … python -m cliente.quien_es          # nodo, rol, primario, época, ultimo_seq
1 BACKUP   3 1 2
2 BACKUP   3 1 2
3 PRIMARIO 3 1 2
```

Hay un solo primario, y crear la mesa y sumarse quedaron replicados en los tres nodos. Los Pods no se reiniciaron.

**Controles adicionales:**
- **El firewall simulado bloquea de verdad.** Un puerto sin regla (8000) no se alcanza desde otra máquina con `ufw` activo, y sí con `ufw` apagado. El NodePort 30501 se alcanza. Por eso, las seis reglas del paso 2 alcanzan.
- **El diagnóstico de «Si algo falla» contesta lo esperado.** Desde `maquina2`, `curl -k https://192.168.77.11:6443` devuelve el `401 Unauthorized` en JSON.

**Problemas de la simulación, no de la guía:**
1. **Overlay sobre overlay.** Con `/var/lib/rancher` dentro de la capa del contenedor, el *snapshotter* de containerd no podía montar overlay y el servidor no arrancaba. Se resolvió con un volumen, como hace la imagen `rancher/k3s`. En una máquina real ese directorio está en el disco.
2. **cgroups compartidos.** En el primer intento, con `--cgroupns=host`, los tres kubelets usaban el mismo `kubepods.slice` del host y se recreaban los *sandboxes* entre sí. Se vieron:
   - Pods reiniciados sin motivo (`SandboxChanged`);
   - elecciones espontáneas: tres primarios en el arranque y una época 3 sin ninguna falla.

   Con `--cgroupns=private`, cada máquina tiene su propia jerarquía, como una computadora real, y nada de eso volvió a pasar. Se anota porque el síntoma se parece a una falla de Trucardo, y no lo era.

## Pendientes o riesgos detectados
- **El criterio de aceptación es humano.** Que otra persona siga la guía sin ayuda y llegue a una partida en tres máquinas se verifica en el laboratorio. La simulación prueba que los comandos son correctos y suficientes, aun con el firewall activo. No prueba que la guía se entienda sin ayuda. Cuando se haga, conviene agregar sus salidas a este registro.
- **Sólo `ufw`.** Si las máquinas del laboratorio usan `firewalld`, las reglas son equivalentes: `firewall-cmd --permanent --add-port=…` y las redes 10.42.0.0/16 y 10.43.0.0/16 en la zona `trusted`. Se agrega a la guía si hace falta (YAGNI).
- **Una sola IP en el valor para clientes** (ya anotado en la #6). Si se apaga `maquina1`, los clientes pierden el acceso aunque el cluster siga vivo. Además, `maquina1` es el plano de control (#8). Corresponde mirarlo en los experimentos de la #10.
