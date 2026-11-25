# #30 — Volumen replicado con Longhorn

| Campo | Valor |
| --- | --- |
| Issue | #30 (queda abierta: falta el criterio de aceptación) |
| Rama | `issue-30-longhorn` |
| Requisitos | RF-24 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
- Verificar los requisitos de Longhorn (`open-iscsi`) y probar si corre en el cluster local. Si no corre, anotarlo y probarlo sólo en máquinas reales o VMs.
- Instalar Longhorn con su manifiesto oficial de versión fija (D17) y documentarlo.
- Configurar la política para Pods en una máquina caída, verificando el nombre del ajuste en la versión fijada.
- En el generador, `--almacenamiento longhorn`: un PVC por nodo (`ReadWriteOnce`, clase `longhorn`), montado en el mismo punto que el `hostPath`.

## Qué se hizo
- **`despliegue/manifiestos.py`:**
  - la opción `--almacenamiento hostpath|longhorn`, sólo con `--imagen`, y `hostpath` por defecto;
  - con `longhorn`, un PVC por nodo (`datos-nodo<id>`, 1 Gi) antes de su Deployment, y el volumen `datos` apunta a ese PVC en lugar del `hostPath`;
  - el punto de montaje y `TRUCARDO_DATOS` no cambian.
- **`README.md`:**
  - en la guía de máquinas reales, un paso opcional para instalar `open-iscsi` y Longhorn v1.13.0, ajustar la política y generar con `--almacenamiento longhorn`. Está marcado como **sin probar**;
  - el estado y los límites dicen por qué no corre en el cluster local.
- **`PLAN.md`:** el estado de la #30, que queda abierta.

## Por qué así
- **El cluster local no puede correr Longhorn, y se intentó todo lo que estaba a mano.** Pasó así:
  1. **No hay `iscsiadm`.** La imagen `rancher/k3s` no trae libc ni gestor de paquetes. Se armó una imagen de máquina que copiaba `open-iscsi` 2.1.10 de Alpine 3.22.8 con sus bibliotecas musl. Al arrancar, cada máquina generaba su nombre de iniciador, dejaba `/` como montaje compartido, creaba `/run/lock/iscsi` y arrancaba `iscsid`.
  2. **Longhorn v1.13.0 se instaló.** Todos sus Pods quedaron `Running`, y un PVC de prueba se creó con sus tres réplicas.
  3. **El kernel no tenía `iscsi_tcp`.** Se cargó en el host con `sudo modprobe iscsi_tcp`.
  4. **El login iSCSI falla igual.** `iscsid` se conecta al destino, pero no puede hablar con el kernel:

     ```
     iscsid: connected local port 55778 to 10.42.1.6:3260
     iscsid: sendmsg: bug? ctrl_fd 4
     ```

     El iniciador iSCSI del kernel sólo atiende a la red del host. Cada máquina simulada es un contenedor con su propia red, así que su `iscsid` no llega al kernel. Longhorn crea el volumen y sus réplicas, pero no puede exponerlo como disco, y el Pod se queda en `ContainerCreating`.

  Poner las máquinas en la red del host no sirve: las tres necesitan sus IPs propias (D11). Por eso la imagen de máquina se descartó (YAGNI), y el cluster local quedó como estaba.
- **El ajuste es `node-down-pod-deletion-policy`.** En v1.13.0 viene en `do-nothing`, y se lo pasa a `delete-both-statefulset-and-deployment-pod`. Se verificó en el cluster local, donde el ajuste existe aunque los volúmenes no monten.
- **Se mergea el generador sin cerrar la issue.** Su parte es código con tests, y no depende del cluster. El criterio de aceptación («un nodo reiniciado conserva su log») pide máquinas reales, y queda pendiente. La #31 depende de esa misma prueba.
- **Cómo se trabajó:**
  - el generador y sus tests los hizo un subagente implementador, con los tests primero;
  - la imagen de máquina, la instalación de Longhorn y el diagnóstico los hizo el agente principal.

## Tests
- **Agregados**, en `tests/test_manifiestos.py`:
  - con `longhorn`, un PVC por nodo con clase `longhorn` y `ReadWriteOnce`, y ningún `hostPath`;
  - el punto de montaje es el mismo;
  - combina con `--telemetria`;
  - la salida por la línea de comandos tiene los PVC;
  - sin la opción, la salida es la misma que con `hostpath`;
  - un valor desconocido da error, en la función y en la línea de comandos;
  - `--almacenamiento` con `--clientes` da error.
- **Fallaron antes del cambio:** los 7, por la opción o el argumento que no existía.

## Verificación
```
$ docker compose run --build --rm tests
265 tests, todo ok
```

Sin `--almacenamiento`, y con `--almacenamiento hostpath`, la salida del generador es idéntica byte a byte a la de antes, con y sin `--telemetria`.

## Pendientes o riesgos detectados
- **El criterio de aceptación** queda para las máquinas reales, siguiendo la guía del README.
- **La guía no abre los puertos de Longhorn** en el firewall del paso 2. Se ajusta al probarla.
