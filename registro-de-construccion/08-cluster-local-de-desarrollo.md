# #8 — Cluster local de desarrollo

| Campo | Valor |
| --- | --- |
| Issue | #8 |
| Rama | `issue-08-cluster-local-de-desarrollo` |
| Requisitos | RF-11, RNF-06 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Un cluster k3s de tres máquinas simuladas en contenedores, con IPs fijas y el *kubeconfig* expuesto. También un script que cargue la imagen en las tres, y los pasos en el README: levantar el cluster, cargar la imagen, aplicar los manifiestos y jugar desde afuera.

## Qué se hizo
- **`despliegue/cluster-local/compose.yaml`** (nuevo):
  - `maquina1` es el servidor (172.30.0.11) y `maquina2` y `maquina3` son agentes (.12 y .13), todos con `rancher/k3s:v1.37.2-k3s1`;
  - red `maquinas` con subred fija 172.30.0.0/24 (D11);
  - el servidor escribe el *kubeconfig* en `despliegue/cluster-local/salida/` y publica el puerto 6443 (`--tls-san 127.0.0.1`);
  - Traefik y metrics-server desactivados.
- **`despliegue/cluster-local/cargar-imagen.sh`** (nuevo): carga `trucardo:local`, o la imagen que se le pase, en cada máquina levantada, con `docker save | ctr images import` (D10). Funciona desde cualquier directorio.
- **`README.md`:**
  - sección «Cluster local de desarrollo», con los pasos de punta a punta;
  - la nota de estado, actualizada.
- **`.gitignore`:** `despliegue/cluster-local/salida/` y `trucardo.json`, que se generan al seguir el README.
- **`PLAN.md`:** estado de la #8.

## Por qué así
- **Se reusa el compose de la investigación.** Es el que se probó el 23/11 en los experimentos de la nota *Kubernetes y k3s*: `privileged`, `tmpfs` en `/run` y token compartido.
- **La versión de k3s vive sólo en este compose (DRY).** Es la fuente única que fija PLAN 1.1. El README remite a este archivo en vez de repetir la versión.
- **IPs fijas (D11).** Un agente reiniciado conserva su IP y vuelve al cluster. Se verificó reiniciando `maquina3` (ver *Verificación*).
- **«Máquinas» y no «nodos».** Así no se confunden con los nodos de Trucardo, que son Pods.
- **El cliente corre fuera del cluster**, en un contenedor conectado a la red de las máquinas, y entra por NodePort con el valor de `--clientes` (#6). La compu no necesita Pyro5: su `python3` sólo corre el generador.
- **Sin publicar los NodePort en la compu (YAGNI).** Los clientes ya llegan por la red de Docker. Publicarlos sólo serviría para un cliente nativo, que necesitaría Pyro5 instalado.
- **Cómo se trabajó:**
  - un subagente implementador escribió el compose y el script, y uno redactor la sección del README, en paralelo y en archivos distintos;
  - se revisaron los dos diffs. Se corrigió el `down -v` del encabezado del compose para que coincida con el README, y se agregó `trucardo.json` al `.gitignore`;
  - la prueba desde cero se hizo siguiendo el README tal cual.

## Tests
Sin tests nuevos: es infraestructura (PLAN 1.4). La verificación reproducible está abajo, y la suite sigue pasando:

```
$ docker compose run --build --rm tests
193 tests, todo ok
```

## Verificación
Desde cero, con los comandos del README. Se abrevia `docker compose -f despliegue/cluster-local/compose.yaml` como `…`:

```
$ docker compose build nodo1
$ … up -d
$ … exec maquina1 kubectl get nodes -o wide
NAME       STATUS   ROLES           AGE   VERSION        INTERNAL-IP
maquina1   Ready    control-plane   13s   v1.37.2+k3s1   172.30.0.11
maquina2   Ready    <none>          3s    v1.37.2+k3s1   172.30.0.12
maquina3   Ready    <none>          1s    v1.37.2+k3s1   172.30.0.13

$ sh despliegue/cluster-local/cargar-imagen.sh
Cargando trucardo:local en maquina1...
docker.io/library/trucardo:local   saved
(lo mismo en maquina2 y maquina3)

$ TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" python3 -m despliegue.manifiestos --imagen trucardo:local > trucardo.json
$ … exec -T maquina1 kubectl apply -f - < trucardo.json
deployment.apps/trucardo-nodo1 created
service/nodo1 created
(…nodo2 y nodo3)

$ … exec maquina1 kubectl get pods -o wide
NAME                             READY  STATUS   RESTARTS  NODE
trucardo-nodo1-55574b68b6-hm72v  1/1    Running  0         maquina2
trucardo-nodo2-9b89b6d7c-66s2p   1/1    Running  0         maquina3
trucardo-nodo3-5775d4c6dd-2rqdn  1/1    Running  0         maquina1
```

Hay un Pod por máquina, gracias a la anti-afinidad de la #7.

Desde afuera del cluster:

```
$ TRUCARDO_NODOS=… python3 -m despliegue.manifiestos --clientes 172.30.0.11
1@172.30.0.11:30501:30601,2@172.30.0.11:30502:30602,3@172.30.0.11:30503:30603

$ docker run --rm --network trucardo-k3s_maquinas -e TRUCARDO_NODOS="<valor>" trucardo:local python -m cliente.quien_es
│ 1 │ 172.30.0.11:30501 │ BACKUP   │ 3 │ 1 │ 0 │
│ 2 │ 172.30.0.11:30502 │ BACKUP   │ 3 │ 1 │ 0 │
│ 3 │ 172.30.0.11:30503 │ PRIMARIO │ 3 │ 1 │ 0 │
```

Las columnas son: nodo, dirección, rol, primario, época y `ultimo_seq`. Hay un solo primario.

Dos clientes, `leo` y `beto`, cada uno en su contenedor, juegan en la misma mesa:

```
leo:   Estas en la mesa 14a04f · leo 0 vs 0 beto
beto:  Estas en la mesa 14a04f · beto 0 vs 0 leo · a 15 · mano 1 · es mano el rival
```

Después, `quien_es` muestra `ultimo_seq` 2 en los tres nodos: crear la mesa y sumarse quedaron replicados.

Además:

```
$ grep server: despliegue/cluster-local/salida/kubeconfig.yaml
    server: https://127.0.0.1:6443

$ … restart maquina3
maquina3 Ready 172.30.0.13          # vuelve con la misma IP (D11)

$ … down
```

## Pendientes o riesgos detectados
- **`salida/` queda con dueño root.** Docker crea el directorio del *bind mount* y k3s escribe el *kubeconfig* como root (modo 644, se puede leer). Para borrarlo a mano hace falta `sudo`. No afecta el uso y está en `.gitignore`.
- **El primario de esta corrida fue N3, en `maquina1`, que es el servidor de k3s.** Los experimentos de la #10 tienen que considerar que apagar `maquina1` se lleva también el plano de control: los Pods siguen corriendo, pero nadie reprograma nada hasta que vuelva (nota de investigación, §4.3).
