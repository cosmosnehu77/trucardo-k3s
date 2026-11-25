# Experimentos

Qué pasa cuando algo falla con Trucardo en k3s, caso por caso. Cada caso tiene el guion para repetirlo, lo que se espera ver, la evidencia de una corrida real y **por qué** pasa lo que pasa.

Hay dos capas que reaccionan a una falla, y los experimentos muestran cómo se reparten el trabajo:

- **Trucardo** detecta en segundos que el primario no late (`TIMEOUT_CAIDO` = 3 s), elige otro y la partida sigue;
- **Kubernetes** repara después: vuelve a crear el Pod que falta, en la misma máquina o en otra. Tarda más, porque detectar una máquina caída le lleva unos 40 s, a los que suma 10 s de tolerancia (D8).

## Preparación

Todo corre en el cluster local de la #8. Levantalo, cargá la imagen y aplicá los manifiestos con los pasos del [README](../README.md#cluster-local-de-desarrollo-k3s-en-contenedores).

Para acortar los comandos, en cada terminal definí:

```bash
C="docker compose -f despliegue/cluster-local/compose.yaml"
k() { $C exec -T maquina1 kubectl "$@"; }
VALOR="1@172.30.0.11:30501:30601,2@172.30.0.11:30502:30602,3@172.30.0.11:30503:30603"
quien_es() { docker run --rm -it --network trucardo-k3s_maquinas -e TRUCARDO_NODOS="$VALOR" trucardo:local python -m cliente.quien_es "$@"; }
```

`VALOR` es la salida de `--clientes 172.30.0.11` (ver el README): los clientes entran por la IP de `maquina1`.

Durante cada caso conviene tener abiertas:

- dos terminales con `leo` y `beto` jugando una partida (comandos en el README);
- una con `quien_es --seguir`, que actualiza la tabla cada segundo;
- una con el log del nodo que interese: `k logs -f deploy/trucardo-nodo<id>`.

Para colgar o matar el proceso de un nodo hace falta su PID **dentro de la máquina** donde corre su Pod (columna `NODE` de `k get pods -o wide`):

```bash
$C exec -T maquina3 ps -eo pid,args | grep "nodo.servidor 2"
```

### Cómo leer la evidencia

- Las salidas son de una corrida del 25/11/2026, en orden y con la hora de cada línea. Se recortaron líneas repetidas.
- Las tablas de `quien_es` se abrevian a sus columnas: nodo, rol, primario que cree, época y `ultimo_seq`.
- En la evidencia, `leo` y `beto` juegan solos, con jugadas al azar, mediante un script de prueba que usa la misma conexión que el cliente. Cada jugada se anota así:

  ```
  07:41:19 beto: tira 12 de oro (primario N2, 4.2 s)
  ```

  El número final es lo que tardó la jugada, contando los reintentos del cliente. Jugando a mano se ve lo mismo, pero más lento.
- Desde la #24 cada nodo guarda su log en el disco de su máquina, en `/var/lib/trucardo/nodo<id>`. Los casos de esta parte no dependen de eso. Los de persistencia se agregan con la #25.

---

## 1. Borrar el Pod del primario

**Guion.** Con la partida en curso, borrá el Pod del primario (N3 en la corrida):

```bash
k delete pod -l nodo=3 --wait=false
```

**Qué se espera.** Los backups dejan de recibir latidos y eligen otro primario en unos 5 s. Mientras tanto, Kubernetes ya creó el Pod nuevo, que entra como backup y se pone al día.

**Evidencia.**

```
07:41:13 kubectl delete pod -l nodo=3
07:41:13 beto: tira 1 de oro (primario N3, 0.0 s)
07:41:15 [N3│BACKUP│e=0] escuchando en PYRO:truco@…:9503          ← el Pod nuevo, en maquina3
07:41:16 [N1│BACKUP│e=1] 3.1 s sin latido de N3: lo doy por caido
07:41:17 [N3│BACKUP│e=0] arranco una eleccion (epoca_ultima 0, ultimo_seq 0)
07:41:17 [N3│BACKUP│e=0] me gana otro candidato: espero su COORDINADOR
07:41:18 [N2│BACKUP│e=1] arranco una eleccion (epoca_ultima 1, ultimo_seq 24)
07:41:18 [N2│BACKUP│e=1] nadie me gana (contestaron 2 de 2): me corono
07:41:18 [N2│PRIMARIO│e=2] gano la eleccion: soy el primario de la epoca 2
07:41:19 beto: tira 12 de oro (primario N2, 4.2 s)
07:41:19 [N2│PRIMARIO│e=2] N3 esta en la op 0 y yo en la 24: le mando las 24 que le faltan
07:41:19 [N2│PRIMARIO│e=2] N3 quedo al dia en la op 24
```

**Por qué.**

- **Kubernetes no espera a Trucardo.** Al borrar el Pod, el ReplicaSet crea otro enseguida, 2 s antes de que los backups noten la falta del primario. Como la anti-afinidad es preferida (D9) y `maquina1` todavía tenía el Pod viejo terminando, el nuevo fue a `maquina3`.
- **El Pod nuevo no se queda con el puesto.** N3 tiene el id mayor, pero arranca con el log vacío. Las credenciales de la elección comparan primero la frescura del log (época de la última op, `ultimo_seq`) y recién después el id (#23), así que N3 pierde contra N1 y N2.
- **La jugada no se pierde.** El cliente reintenta durante 25 s (`REINTENTO_TOTAL`) y su jugada entra con el primario nuevo, 4,2 s después.
- **Por qué arrancó vacío.** Se mudó a `maquina3`, que no tenía su log, y se puso al día por la red. Si hubiera vuelto a `maquina1`, habría arrancado con su disco.

## 2. Colgar un nodo (`kill -STOP`)

**Guion.** Colgá el proceso del primario (N2, en `maquina3`), esperá unos 25 s y reanudalo:

```bash
$C exec -T maquina3 kill -STOP <pid>
```

```bash
$C exec -T maquina3 kill -CONT <pid>
```

**Qué se espera.** Para Trucardo, un nodo colgado es igual a uno caído: los backups eligen otro primario. Kubernetes, en cambio, **no se entera**. Al reanudarlo, el primario viejo descubre que hay una época mayor y se degrada a backup.

**Evidencia.**

```
07:42:59 beto: canta truco (primario N2, 0.0 s)
07:43:00 kill -STOP (N2, primario de la época 2)
07:43:03 [N3│BACKUP│e=2] 3.1 s sin latido de N2: lo doy por caido
07:43:05 [N3│BACKUP│e=2] arranco una eleccion (epoca_ultima 2, ultimo_seq 103)
07:43:06 [N3│PRIMARIO│e=3] gano la eleccion: soy el primario de la epoca 3
07:43:07 leo: responde no quiero (primario N3, 6.5 s)

07:43:13 quien_es
1 BACKUP     3  e=3  108
2 no responde
3 PRIMARIO   3  e=3  109
k get pods → los tres Running, RESTARTS 0

07:43:26 kill -CONT
07:43:26 [N2│PRIMARIO│e=2] N1 me rechaza el latido: hay epoca 3 y yo estoy en la 2
07:43:26 [N2│BACKUP│e=3] N3 es el primario de la epoca 3
07:43:26 [N2│BACKUP│e=3] op 104 · responder · leo …              ← se pone al día: 104 a 116
```

**Por qué.**

- **Kubernetes no ve el cuelgue.** La *liveness probe* abre una conexión TCP al puerto del cluster (D7). Con el proceso detenido, el kernel igual acepta la conexión, porque la cola de conexiones del socket la atiende el sistema operativo, no el proceso. Para Kubernetes, el Pod sigue sano.
- **Trucardo sí lo ve**, porque un nodo colgado no late. Al no contestar, a los 3 s los backups lo dan por caído.
- **Las épocas resuelven la vuelta.** Al reanudarse, N2 sigue creyéndose primario de la época 2. Su primer latido le llega a N1, que ya está en la época 3 y lo rechaza. N2 adopta la época 3, pasa a backup y recibe lo que se jugó mientras estaba colgado.

## 3. Apagar una máquina con un backup

**Guion.** Apagá la máquina donde sólo corre un backup (`maquina2`, con N1) y, al rato, volvé a encenderla:

```bash
$C stop -t 0 maquina2
```

```bash
$C start maquina2
```

**Qué se espera.** La partida sigue sin elección, con el otro backup, aunque cada jugada tarda un poco más. Kubernetes marca la máquina `NotReady` y, a los 10 s, recrea el Pod en otra máquina, donde arranca y se pone al día.

**Evidencia.**

```
07:43:56 docker compose stop maquina2
07:43:58 beto: tira 4 de espada (primario N3, 1.0 s)
07:43:59 [N3│PRIMARIO│e=3] N1 fuera de la vista: no contesta el latido
07:44:00 beto: tira 3 de espada (primario N3, 1.0 s)
07:44:01 leo: tira 10 de basto (primario N3, 2.0 s)
          en los 100 s siguientes, ninguna jugada tardó más de 2 s

07:44:40 maquina2=Ready      nodo1:Running@maquina2
07:44:45 maquina2=NotReady   nodo1:Running@maquina2
07:44:53 [N1│BACKUP│e=0] escuchando en PYRO:truco@…:9501     ← en maquina1
07:44:54 [N1│BACKUP│e=0] N3 es el primario de la epoca 3
07:44:54 [N3│PRIMARIO│e=3] N1 entra a la vista (ultimo_seq 0)
07:44:56 maquina2=NotReady   nodo1:Running@maquina1  nodo1:Terminating@maquina2
```

**Por qué.**

- **Para Trucardo, perder un backup cuesta poco.** El primario saca a N1 de la vista en el primer latido sin respuesta. Pero la vista no decide a quién replicar: cada jugada se manda a todos los nodos del cluster, y el primario espera hasta `TIMEOUT_ACK` (1 s) la respuesta de N1. Por eso las jugadas pasan a tardar 1 s, o 2 s si dos se encolan, hasta que el Pod nuevo de N1 contesta.
- **Kubernetes tarda casi un minuto.** El servidor declara `NotReady` a la máquina recién a los ~45 s sin noticias del kubelet. Después aplica los 10 s de tolerancia (D8) y desaloja el Pod.
- **El Pod viejo queda `Terminating`** hasta que vuelva `maquina2`: nadie puede confirmar que el proceso murió, porque el kubelet que lo haría está en la máquina apagada. Al encenderla, el kubelet lo borra.
- **El Pod nuevo arranca vacío**, porque `maquina1` no tenía el log de N1, y se pone al día por la red.

## 4. Apagar la máquina del primario

**Guion.** Apagá la máquina donde corre **sólo** el primario (`maquina3`, con N3) y después volvé a encenderla. Si el primario comparte máquina con un backup, primero borrá el Pod del backup para que se mude.

```bash
$C stop -t 0 maquina3
```

**Qué se espera.** Es el caso 3 más una elección: los backups eligen otro primario en unos 5 s, y Kubernetes recrea el Pod perdido casi un minuto después.

**Evidencia.**

```
07:46:36 leo: responde quiero (primario N3, 0.0 s)
07:46:38 docker compose stop maquina3 (N3, primario)
07:46:41 [N2│BACKUP│e=3] 3.3 s sin latido de N3: lo doy por caido
07:46:42 [N2│BACKUP│e=3] arranco una eleccion (epoca_ultima 3, ultimo_seq 319)
07:46:44 [N2│PRIMARIO│e=4] gano la eleccion: soy el primario de la epoca 4
07:46:45 beto: tira 1 de basto (primario N2, 7.1 s)
07:46:46 leo: canta retruco (primario N2, 8.0 s)

07:47:27 maquina3=NotReady
07:47:38 nodo3:Running@maquina2  nodo3:Terminating@maquina3
07:47:38 [N3│BACKUP│e=0] N2 es el primario de la epoca 4
07:47:38 [N2│PRIMARIO│e=4] N3 esta en la op 0 y yo en la 357: le mando las 357 que le faltan
07:47:39 [N2│PRIMARIO│e=4] N3 quedo al dia en la op 357
```

**Por qué.**

- **La partida se corta unos 8 s**, la suma de la detección (3 s), la espera al azar antes de postularse (`JITTER`), la elección y el reintento del cliente.
- **Kubernetes no participa de la recuperación del servicio:** cuando recrea el Pod, la partida ya lleva casi un minuto jugándose con N2. Sólo devuelve el cluster a tres nodos.
- **La elección no necesitó a Kubernetes**, sólo a los dos backups. Es el reparto de RNF-08: Trucardo decide primero y Kubernetes repara después.

## 5. Actualizar la versión con una partida en curso

**Guion.** Cargá la imagen nueva en las tres máquinas y actualizá los Deployments **de a uno**: primero los backups y al final el primario. En la corrida, la «versión nueva» es la misma imagen con otra etiqueta:

```bash
docker tag trucardo:local trucardo:v2
```

```bash
sh despliegue/cluster-local/cargar-imagen.sh trucardo:v2
```

Por cada nodo, en ese orden:

```bash
k set image deploy/trucardo-nodo1 nodo=trucardo:v2
```

```bash
k rollout status deploy/trucardo-nodo1
```

Antes de pasar al siguiente, confirmá con `quien_es` que el nodo actualizado volvió y tiene el mismo `ultimo_seq` que el resto.

**Qué se espera.** Cada backup se reinicia y se pone al día sin que la partida lo note. Actualizar el primario cuesta una elección, como en el caso 1.

**Evidencia.**

```
07:49:02 set image nodo1 → nodo1 en maquina3: arranca vacío, puesta al dia de la op 0 a la 465
07:49:12 quien_es → 1 BACKUP e=4 474 | 2 PRIMARIO e=4 474 | 3 BACKUP e=4 474
07:49:13 set image nodo3 → nodo3 en maquina1, con el log que dejó ahí en la época 1:
07:49:14 [N3│BACKUP│e=1] escuchando en PYRO:truco@…:9503
07:49:15 [N3│BACKUP│e=4] puesta al dia: de la op 24 a la 476
07:49:21 quien_es → 1 BACKUP e=4 486 | 2 PRIMARIO e=4 486 | 3 BACKUP e=4 486
07:49:22 set image nodo2 (el primario)
07:49:24 [N2│BACKUP│e=4] escuchando en PYRO:truco@…:9502     ← vuelve en maquina2, con su disco
07:49:25 [N2│BACKUP│e=4] arranco una eleccion (epoca_ultima 4, ultimo_seq 486)
07:49:27 [N3│PRIMARIO│e=5] gano la eleccion: soy el primario de la epoca 5
07:49:28 leo: canta envido (primario N3, 4.1 s)
07:49:31 quien_es → 1 BACKUP e=5 492 | 2 BACKUP e=5 492 | 3 PRIMARIO e=5 492

trucardo-nodo1   trucardo:v2
trucardo-nodo2   trucardo:v2
trucardo-nodo3   trucardo:v2
```

Mientras se actualizaban los backups, ninguna jugada tardó más de 1 s.

**Por qué.**

- **De a uno y el primario al final.** Mientras dos nodos están al día, actualizar el tercero no pone en riesgo nada. Si se actualizara primero el primario, la elección se haría con un backup que quizás todavía se está poniendo al día.
- **`Recreate` (D3).** Kubernetes mata el Pod viejo antes de crear el nuevo. Así nunca hay dos procesos con el mismo id, aunque haya unos segundos sin ese nodo. Con `RollingUpdate`, el nuevo arrancaría con el viejo todavía vivo.
- **N2 volvió como backup aunque tenía todo.** Arrancó con su disco y las mismas credenciales que N3, (4, 486). En el empate gana el id mayor, N3. No hubo pérdida: el log de los dos era el mismo.
- **N3 arrancó en la época 1 y se puso al día desde la op 24.** En `maquina1` estaba el log de N3 de cuando era primario, al principio. Sus 24 operaciones coinciden con las del primario, así que sólo recibe lo que sigue (la coincidencia de logs de la #23).

## 6. Apagar el servidor k3s

**Guion.** Apagá `maquina1`, que tiene el plano de control. Antes, cambiá los clientes para que entren por otra máquina, porque la IP de `maquina1` desaparece. Por ejemplo, con `--clientes 172.30.0.12`:

```bash
VALOR="1@172.30.0.12:30501:30601,2@172.30.0.12:30502:30602,3@172.30.0.12:30503:30603"
```

```bash
$C stop -t 0 maquina1
```

Al rato, volvé a encenderla con `$C start maquina1`.

**Qué se esperaba.** Sin plano de control, nadie reprograma nada, pero los Pods de las otras máquinas siguen corriendo y la red entre ellos sigue andando. Trucardo debería elegir otro primario si el que se apagó era el primario, y seguir.

**Qué pasó.** Quedaron **dos primarios**. En la corrida, `maquina1` tenía además al primario, N3:

```
07:50:05 docker compose stop maquina1 (servidor k3s y N3, primario)
07:50:07 [N2│BACKUP│e=5] 3.4 s sin latido de N3: lo doy por caido
07:50:09 [N2│BACKUP│e=5] arranco una eleccion (epoca_ultima 5, ultimo_seq 536)
07:50:13 [N2│BACKUP│e=5] nadie me gana (contestaron 0 de 2): me corono
07:50:13 [N2│PRIMARIO│e=6] gano la eleccion: soy el primario de la epoca 6
          …y N1, en maquina3, también se corona en la época 6

07:50:18 [N1│PRIMARIO│e=6] op 537 · responder · beto · … · la tienen 0/0 de los que contestaron
07:50:20 [N2│PRIMARIO│e=6] op 537 · responder · beto · … · la tienen 0/0 de los que contestaron
07:51:03 leo: tira 11 de oro (primario N1, 15.0 s)
07:51:12 leo: canta truco (primario N1, 7.5 s)

consulta de nombres desde el Pod de N2 (07:51):
nodo1 ERROR [Errno -3] Temporary failure in name resolution   (20 s)
nodo2 ERROR [Errno -3] Temporary failure in name resolution   (20 s)
nodo3 ERROR [Errno -3] Temporary failure in name resolution   (20 s)
```

Al volver `maquina1` (07:53:00), los dos primarios se encuentran:

```
07:53:08 [N1│PRIMARIO│e=6] N2 manda en la epoca 6: dejo de ser primario
07:53:08 [N2│PRIMARIO│e=6] N3 esta en la op 536 y yo en la 558: le mando las 22 que le faltan
07:53:47 quien_es → 1 BACKUP e=6 608 | 2 PRIMARIO e=6 608 | 3 BACKUP e=6 608
```

**Por qué.**

- **Los nodos se buscan por nombre** (`nodo1`, `nodo2`, `nodo3`, D5), y los nombres los resuelve CoreDNS. En k3s, CoreDNS es **una sola réplica** y corre en el servidor:

  ```
  $ k get pods -n kube-system -o custom-columns=POD:.metadata.name,NODO:.spec.nodeName
  coredns-577d995dff-4p782   maquina1
  ```

  Al apagar `maquina1`, `kube-proxy` sigue ruteando en las otras máquinas, pero nadie contesta las consultas de DNS. N1 y N2 no se encuentran, y cada uno gana su elección sin rivales («contestaron 0 de 2»).
- **Por eso cada jugada tardaba 7,5 a 15 s.** Cada envío del primario se quedaba 20 s resolviendo un nombre, pero el primario espera como mucho 2 s por nodo: confirmaba la jugada a los 4 s, con «0/0». El cliente espera 2 s (`TIMEOUT_RPC`) y hace una pausa de 0,5 s, así que cortaba antes y probaba el nodo siguiente. Al dar la vuelta a los tres nodos (7,5 s), el primero ya había terminado y contestaba que era un reintento. Si la consulta anterior también daba la vuelta, sumaba 15 s. Así, cada jugada se aplicó **en los dos** primarios. Por casualidad, los dos logs quedaron iguales, y al reencontrarse no hubo nada que recortar. Con dos clientes entrando por lados distintos, divergirían, como en el caso 7.
- **El servidor de k3s es un punto único de falla para Trucardo**, aunque no debería serlo. Se corrige en la [#52](https://github.com/cosmosnehu77/trucardo-k3s/issues/52): IPs fijas para los Services y nombres en `/etc/hosts` de cada Pod, sin pasar por CoreDNS.
- **Los clientes también dependen de una IP.** El valor de `--clientes` apunta todos los nodos a la IP de una sola máquina. Si esa máquina se apaga, el cliente no llega a nadie aunque los nodos sigan vivos. Por eso hubo que cambiar a `172.30.0.12` antes de apagar.

## 7. Límite: partición de red

**Guion.** Separá la máquina del primario (`maquina2`, con N2) de las otras dos, con dos jugadores de cada lado: unos entran por `172.30.0.12` y otros por `172.30.0.11`.

```bash
$C exec -T maquina2 sh -c 'for ip in 172.30.0.11 172.30.0.13; do iptables -I INPUT -s $ip -j DROP; iptables -I OUTPUT -d $ip -j DROP; done'
```

Al rato, curá la partición con el mismo comando, cambiando `-I` por `-D`.

**Qué se espera.** Es el límite que el plan acepta (D4): Trucardo no tiene quórum, así que cada lado tiene su primario y confirma jugadas que el otro no ve. Kubernetes no lo resuelve. Al contrario: agrega una **segunda copia** del nodo aislado.

**Evidencia.**

```
07:54:59 particion: maquina2 deja de hablar con maquina1 y maquina3

07:55:14 quien_es desde .11 → 1 BACKUP e=7 719 | 2 no responde | 3 PRIMARIO e=7 720
07:55:17 quien_es desde .12 → 1 no responde | 2 PRIMARIO e=6 715 | 3 no responde

bot-b (por .11):  07:55:09 beto: tira 4 de espada (primario N3, 1.0 s)
bot-a (por .12):  07:55:21 beto: tira 3 de espada (primario N2, 15.0 s)
[N2│PRIMARIO│e=6] op 713 … 726 · la tienen 0/0 de los que contestaron

07:55:54 maquina2=NotReady
07:56:05 nodo2:Running@maquina3  nodo2:Terminating@maquina2   ← dos N2 corriendo
$C exec maquina2 crictl ps → trucardo-nodo2-…-tkwr6  Running   ← el viejo sigue vivo

07:56:49 se cura la particion
07:56:50 bot-a, beto: rechazada: el jugador 2 no tiene 12 de oro (le quedan: [3 de espada, 4 de copa])
07:56:52 bot-a, beto: tira 3 de espada (primario N3, 0.0 s)
```

Después de la partición, el disco que N2 dejó en `maquina2` todavía tiene esas 14 operaciones de la época 6, que nadie más tiene. Lo que pasa con ellas es un caso de la #25.

**Por qué.**

- **Sin quórum, cada lado se corona.** La mayoría (N1 y N3) elige un primario de la época 7. N2 no recibe nada y sigue siendo el de la época 6. Confirma las jugadas de `bot-a` sin acks («0/0»), porque el diseño del Proyecto 1 prefiere seguir jugando a frenar.
- **Kubernetes empeora el problema.** El servidor deja de oír al kubelet de `maquina2`, la marca `NotReady` y crea otro N2 en `maquina3`. No puede matar al viejo, porque el kubelet que lo haría está del otro lado. Quedan **dos procesos con el id 2**, que `Recreate` (D3) evita en todos los demás casos. Por eso un StatefulSet espera a que la máquina vuelva (D4): prefiere no tener el nodo antes que tenerlo dos veces.
- **Al curarse, gana la época mayor.** El kubelet de `maquina2` se entera de que su Pod fue borrado y lo mata. `bot-a` vuelve a la mayoría, y sus jugadas de la época 6 ya no existen: su jugador ve otras cartas en la mano («no tiene 12 de oro»).
- **Es el mismo problema que el caso 6**, pero causado por la red. Las épocas evitan que el primario viejo siga mandando después de curarse la partición, pero no que confirme jugadas mientras dura. Resolverlo exige quórum: no confirmar sin la mayoría (Raft, Paxos). Es la frontera del modelo primario-backup.
