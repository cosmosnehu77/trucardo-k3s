# #10 — Experimentos de falla en k3s

| Campo | Valor |
| --- | --- |
| Issue | #10 |
| Rama | `issue-10-experimentos-de-falla` |
| Requisitos | RF-04, RF-05, RF-09, RF-12 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
`experimentos/README.md`, con un guion reproducible de siete casos, lo que se espera ver en cada uno, la evidencia con hora y la explicación de **por qué** pasó lo que pasó:

1. borrar el Pod del primario;
2. colgar un nodo;
3. apagar una máquina con un backup;
4. apagar la máquina del primario;
5. actualizar la versión con una partida en curso;
6. apagar el servidor k3s;
7. el límite: una partición de red.

## Qué se hizo
- **`experimentos/README.md`** (nuevo):
  - una preparación con funciones de shell para acortar los comandos (`k`, `quien_es`) y cómo encontrar el PID de un nodo dentro de su máquina;
  - los siete casos, cada uno con guion, lo esperado, la evidencia y el porqué.
- **Dos issues nuevas**, en PLAN.md y en GitHub:
  - la **#52**: el caso 6 encontró que los nodos dependen del DNS del cluster;
  - la **#53**: al verificar la suite apareció una elección de más (ver *Verificación*).
- **`README.md`:** la nota de estado nombra el log en disco y enlaza los experimentos.
- **`PLAN.md`:** estado de la #10, la #52 y la #53.

## Por qué así
- **El cluster local y no el laboratorio.** Los casos son los mismos, y en contenedores se pueden repetir en cualquier momento. Apagar una máquina es `docker compose stop`, y una partición es `iptables` dentro de la máquina simulada.
- **Los jugadores de la evidencia juegan solos.** Un script de prueba, fuera del repo, juega al azar con la misma `Conexion` que el cliente y anota cada jugada con su hora y su demora. Así se ve el corte de servicio en segundos, que a mano no se mide. El guion usa los clientes de siempre: no hace falta otra herramienta para repetirlo (YAGNI).
- **Los experimentos se corrieron con la persistencia de la #22 a la #24 ya hecha.** Eso no cambia ninguno de los siete casos, pero aparece en la evidencia: en el caso 5, N3 arrancó con el log que había dejado en otra máquina y se puso al día desde la op 24.
- **El caso 6 no dio lo esperado, y se documenta lo que pasó.** Se esperaba que, sin plano de control, la partida siguiera. Quedaron dos primarios: CoreDNS corre sólo en el servidor, y sin DNS los nodos no se encuentran. Se confirmó resolviendo los nombres desde el Pod de N2 (`Temporary failure in name resolution`) y listando dónde corre CoreDNS. La corrección va en una issue aparte, la #52, porque es código con tests.
- **Cómo se trabajó:**
  - los experimentos y el README los hizo el agente principal: dependen de leer la salida en vivo y decidir el paso siguiente;
  - un subagente revisor contrastó cada bloque de evidencia con las salidas crudas y con el código. Encontró dos explicaciones equivocadas, que se corrigieron:
    - **caso 3:** decía que el primario deja de esperar el ack del backup caído cuando lo saca de la vista. No es así: replica a todo el cluster, y cada jugada paga 1 s de espera hasta que vuelve el Pod;
    - **caso 6:** atribuía las demoras de 7,5 y 15 s a los 20 s del DNS. Salen de los 2 s que espera el primario por cada nodo, más la vuelta del cliente por los tres nodos (3 × 2,5 s);
  - también encontró líneas de evidencia fuera de orden, una línea de `kubectl` que no probaba lo que decía y una función de la preparación incómoda de usar. Se corrigieron.

## Tests
Sin tests nuevos: es documentación (PLAN 1.4). La verificación reproducible es el propio experimento, y la evidencia está en `experimentos/README.md`.

## Verificación
```
$ docker compose run --build --rm tests
210 tests, todo ok
```

**Una falla intermitente.** La primera corrida de la suite, con el cluster local levantado, falló en `test_un_backup_que_vuelve_con_su_disco_recibe_solo_lo_que_le_falta` (#23). La segunda pasó. Como esta issue no cambia código, se buscó la causa:

- ese test, aislado, dio 0 fallas en 40 corridas, también con las CPU ocupadas;
- la suite completa con las CPU ocupadas falló 2 veces en 12, las dos en `test_si_el_primario_deja_de_latir_los_backups_lo_detectan`;
- ese test, aislado y con log, falló 1 vez en 60. El log muestra la causa: una `ELECCION` que llega tarde hace que un backup convoque otra elección aunque ya conoce al primario. Es del protocolo, no del test. Siguiendo la regla de la #39, va en una issue aparte: la #53.

La falla del test de la #23 no se volvió a ver. Si la causa es la misma, se confirmará en la #53.

Cada comando del guion se corrió tal como figura, salvo las funciones de la preparación, que se probaron aparte con el cluster levantado.

## Pendientes o riesgos detectados
- **Los nodos dependen de CoreDNS** (caso 6). Es la #52.
- **Una elección tardía dispara otra.** Es la #53.
- **Los clientes entran por la IP de una sola máquina.** El valor de `--clientes` apunta todos los nodos a una IP. Si esa máquina se apaga, el cliente no llega a nadie. En el caso 6 hubo que cambiar de IP antes de apagar. No lo pide ninguna issue: se menciona en el informe y, si alcanza el tiempo, se puede abrir una.
- **Kubernetes no detecta un nodo colgado** (caso 2). La *probe* TCP la contesta el kernel. Una *probe* que pregunte algo a Trucardo lo detectaría, pero Trucardo ya resuelve el cuelgue con sus latidos (RNF-08).
- **Una partición deja dos procesos con el mismo id** (caso 7). Es el límite aceptado en D4.
- **Con `kill -STOP` no se pierden mensajes.** El kernel los guarda mientras el proceso está detenido. En una prueba de la #25 se vio que un primario colgado no perdía sus operaciones sin ack, porque los backups las recibían al reanudarse. Para perder mensajes de verdad hace falta una partición.
