# #16 — Experimentos de falla con trazas

| Campo | Valor |
| --- | --- |
| Issue | #16 |
| Rama | `issue-16-experimentos-con-trazas` |
| Requisitos | RF-12, RF-15, RF-16 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Repetir experimentos de la #10 con Jaeger abierto y capturar:

- una jugada replicada;
- la elección tras matar al primario;
- un nodo que cambia de máquina, visible en `k8s.node.name`;
- el cerebro dividido: jugadas confirmadas por dos primarios de épocas distintas.

## Qué se hizo
- **`experimentos/README.md`:** la sección «Trazas», con los casos 12 a 15, en el mismo formato que los anteriores: guion, lo esperado, evidencia y porqué. Incluye:
  - cómo hacer que el cliente exporte su *span*;
  - cómo buscar en Jaeger;
  - cómo leer los árboles de la evidencia.
- **`experimentos/capturas/`:** cuatro capturas de la interfaz de Jaeger: la jugada, la elección, la puesta al día y la curación del cerebro dividido.
- **`PLAN.md`:** estado de la #16.

## Por qué así
- **La evidencia es texto, con capturas de apoyo.** Los árboles salen de la API de Jaeger (`/api/v3/traces`), con un script de prueba fuera del repo. En texto se pueden citar horas, atributos y duraciones, y se comparan con los logs, como en la #10. Las capturas muestran cómo se ve lo mismo en la interfaz. Se tomaron con Chromium sin ventana, sobre la vista de cada traza.
- **Los casos 13 y 14 salen de una sola corrida.** Se acordonó la máquina del primario antes de borrar su Pod. Así el borrado dispara la elección y, además, la mudanza a otra máquina.
- **El cliente automático abre el mismo *span* que el cliente.** Es el script de la #10, con el *span* `jugada <qué>` agregado alrededor de cada jugada, como `Cliente._enviar` (#13). El guion usa el cliente de verdad.
- **Se documentan dos cosas que sólo mostraron las trazas:**
  - **caso 14:** el primario registra que N3 «no contesta» durante una puesta al día de 1061 ops, pero N3 estaba escribiéndolas, cada una con su `fsync`, y tardó 4,6 s, más que los 3 s que espera el primario. Converge con el latido siguiente;
  - **caso 15:** la partición también corta la telemetría. Se perdieron las trazas de N2 de unos 15 s, porque Jaeger estaba del otro lado.
- **Cómo se trabajó:**
  - los experimentos y el texto los hizo el agente principal: dependen de leer la salida en vivo;
  - un subagente revisor contrastó la evidencia con las salidas crudas, con el código y con el SDK instalado. Se corrigió lo que encontró:
    - **la op 1834 de N2 no se confirmó.** La evidencia había perdido la marca de error. N1 la rechazó con `EPOCA_VIEJA` y su *span* `replica` era el rechazo, no un ack;
    - **los envíos a todos van en paralelo.** La elección de N1 dura 2 s porque el coordinador, de 1 s, corre dentro de ella. No es que espere a cada nodo por separado. Y durante la partición pagan 1 s por jugada los dos primarios, no sólo N2;
    - **el hueco en las trazas de N2** se explica con los lotes de 5 s y la espera de 10 s del exportador. Así se entiende por qué llegaron las jugadas de los últimos 9 s de la partición;
    - **el Pod nuevo de N3 también abrió una `eleccion` al arrancar**, que se había quitado de la evidencia;
    - **dos líneas estaban fuera de orden**, y faltaba explicar de dónde salían las ops 1381 a 1383.

## Tests
Sin tests nuevos: es documentación (PLAN 1.4). La verificación reproducible es el propio experimento, y la evidencia está en `experimentos/README.md`.

## Verificación
```
$ docker compose run --build --rm tests
240 tests, todo ok
```

Los comandos del guion se corrieron tal como figuran.

## Pendientes o riesgos detectados
- **Una puesta al día grande supera la espera del primario** (caso 14). El primario registra un error que no es tal y repite una puesta al día corta. No se pierde nada. Si molestara, la espera podría crecer con la cantidad de ops, o el backup podría hacer un solo `fsync` por puesta al día. Por ahora sólo se documenta.
- **Las trazas del lado aislado de una partición se pierden** (caso 15). Lo resolvería un *Collector* por máquina con cola persistente. Se evalúa en la #28.
- **El puerto OTLP para clientes externos lo asigna Kubernetes.** El guion lo obtiene con `kubectl`. Alcanza para los experimentos.
