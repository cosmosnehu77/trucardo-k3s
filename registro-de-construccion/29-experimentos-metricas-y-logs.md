# #29 — Experimentos con métricas y logs

| Campo | Valor |
| --- | --- |
| Issue | #29 |
| Rama | `issue-29-experimentos-metricas-y-logs` |
| Requisitos | RF-12, RF-21, RF-22 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Repetir experimentos de la #10 con el tablero abierto, y dejar en `experimentos/README.md` las capturas con su explicación:

1. la caída del primario: la época sube, el rol cambia y el atraso vuelve a 0 tras la puesta al día;
2. el cerebro dividido: el panel de primarios simultáneos marca 2, y crecen las operaciones confirmadas sin acks;
3. un log como «lo doy por caído» y el salto a su traza;
4. una comparación con `kubectl logs` y `kubectl top`.

## Qué se hizo
- **`experimentos/README.md`:** la sección «Métricas y logs», con los casos 16 a 19 en el formato de siempre: guion, lo esperado, evidencia y porqué. Tres capturas nuevas en `experimentos/capturas/`.
- **`despliegue/observabilidad/tablero-trucardo.json`:** los paneles de rol, época, atraso y primarios simultáneos toman el máximo por nodo en los últimos 10 s, y todos los paneles de métricas usan un paso de 5 s.
- **Una issue nueva, la #67,** en PLAN.md y en GitHub: dos errores en la medición del atraso.
- **`PLAN.md`:** estado de la #29 y la #67.

## Por qué así
- **El primer caso junta dos fallas.** Borrar el Pod del primario muestra el rol y la época. Pero el N2 nuevo volvió a su misma máquina, con su disco, y no tuvo nada que poner al día. Para ver el atraso crecer y volver a 0 se colgó un backup con `kill -STOP`, en la misma corrida.
- **El cerebro dividido corta sólo los puertos de Trucardo.** En el caso 15 se cortaba toda la máquina, y se perdían los *spans* del lado aislado. Acá la telemetría tiene que seguir llegando para que el tablero vea a los dos primarios. Cada cliente conoce sólo un lado, así los dos lados juegan.
- **El tablero se corrigió para que la evidencia fuera cierta.** La primera tabla de la caída marcó 2 primarios a las 11:09:57: el Pod borrado de N2 y el nuevo eran dos series distintas (cambia `k8s.pod.name`), y la del Pod borrado seguía valiendo 1 en la ventana de 15 s. Con el máximo por nodo, un nodo cuenta una vez aunque haya cambiado de Pod. Con 10 s, una serie que deja de llegar se va en dos exportaciones. Con un paso de 5 s, cada punto es una exportación, y una ventana corta no se ve en blanco. Es configuración sin tests, y la evidencia de esta issue depende de ella: por eso va en esta rama.
- **El atraso mal medido va en otra issue.** Es código con tests (regla de la #10): la #67.
- **`kubectl top` no anda.** metrics-server está desactivado desde la #8 (`--disable metrics-server`), en el cluster local y en las máquinas reales (#9). La comparación lo dice, y explica qué daría si se activa. Para `kubectl logs` se usó el Pod borrado en el caso 16: Kubernetes ya no tiene sus logs y Loki sí.
- **Las capturas salen de Chromium sin ventana,** sobre el tablero con el rango de tiempo fijo. Para que el panel de primarios marque 2, el rango termina durante la partición: el panel muestra el último valor.
- **Cómo se trabajó:**
  - los experimentos, las capturas y el texto los hizo el agente principal;
  - un subagente revisor contrastó la evidencia con las salidas crudas y con el código. Lo que encontró se corrigió:
    - **el atraso de 1 de N2 en el caso 16 se explicaba mal.** Se decía que la métrica se leía mientras la jugada esperaba a N1, pero el lector de métricas toma el mismo lock que la jugada. La causa es un latido viejo que pisa el ack: es un segundo error de medición, y se sumó a la #67;
    - **la vuelta a 0 del atraso al reanudar a N1** no venía del próximo ack, sino de la respuesta a la puesta al día. Y N1 volvió en la 3393 porque aplicó las réplicas que habían quedado en la cola del socket;
    - **el panel de operaciones sin acks dibuja una línea por nodo**, y la tabla las sumaba sin decirlo;
    - **el guion del cerebro dividido** no decía qué nodos conoce cada partida, que es lo que separa los lados cuando la partición no corta el tráfico de los clientes;
    - el atraso de N3 llega a 23 y recorta 24: la 3682 no se confirmó;
    - metrics-server también está desactivado en las máquinas reales.

## Tests
Sin tests nuevos: es documentación (PLAN 1.4). La verificación reproducible es el propio experimento, y la evidencia está en `experimentos/README.md`.

## Verificación
```
$ docker compose run --build --rm tests
256 tests, todo ok
```

## Pendientes o riesgos detectados
- **Dos errores en la medición del atraso:** el de un backup desconocido y el de un latido viejo que pisa un ack. Los dos son la #67.
- **El panel de primarios simultáneos puede marcar 2 un instante** si la elección tarda menos que la ventana de 10 s después de la caída del primario. En la corrida, la elección tardó 5 s y no pasó. Un cerebro dividido real dura lo que dura la partición.
- **Prometheus, Loki y Jaeger pierden su historia si su Pod se muda** (#28).
