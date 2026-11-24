# Requisitos — Trucardo en k3s

Qué tiene que hacer este proyecto y bajo qué reglas. El **cómo** y el **orden** están en [PLAN.md](PLAN.md); cada issue del plan cita los requisitos que cumple por su código (`RF-xx`, `RNF-xx`).

---

## 1. Contexto

- **Trabajo de promoción** de Sistemas Distribuidos 2026 (UNPSJB), de a dos: Nehuén García y Alan Viera. **Entrega: jueves 26/11/2026.**
- La consigna pide investigar una tecnología de SD **no vista** en la materia, construir un ejemplo **básico pero funcional** que muestre sus principios, entregarlo en un repositorio con `README.md` e instrucciones claras (se recomienda Docker), y escribir un informe de hasta 10 páginas.
- **Tecnología elegida:** orquestación de contenedores con **Kubernetes (distribución k3s)**.
    - **Fase recomendada:** persistencia del log de cada nodo en un **volumen**.
    - **Fases extra:** observabilidad con **OpenTelemetry** (trazas en Jaeger, métricas y logs) y, después, almacenamiento replicado con **Longhorn**.
- **Base:** Trucardo, el servicio de truco distribuido del Proyecto 1 (primario-backup, elección Bully con épocas, log replicado, relojes de Lamport). El código tal como se entregó está marcado con el tag `proyecto1-base`.

## 2. Objetivo

Desplegar los tres nodos de Trucardo en un cluster **k3s de tres máquinas** para que Kubernetes se ocupe de que **los procesos existan** —reiniciarlos, reubicarlos y actualizarlos— mientras Trucardo conserva su propia tolerancia a fallas: quién es el primario y cuál es el estado de cada mesa.

> Kubernetes devuelve **procesos**; Trucardo devuelve **estado**. Ninguna de las dos capas hace el trabajo de la otra.

Con la fase recomendada, cada nodo guarda además su log en disco: si se apagan las tres máquinas y vuelven, las partidas siguen.

## 3. Glosario

Hay dos palabras que en este proyecto significan cosas distintas según la capa. Se usan **siempre** así, en código, documentos y commits:

| Término | Significado |
| --- | --- |
| **Máquina** | Una computadora del cluster. En Kubernetes se llama *Node*; acá se dice **máquina** para no confundirla con un nodo de Trucardo |
| **Nodo** | Un proceso de Trucardo con un id fijo (1, 2 o 3) definido en `TRUCARDO_NODOS` |
| **Servidor k3s** | La máquina que corre el plano de control de Kubernetes (en la demo, también corre nodos) |
| **Agente k3s** | Una máquina que sólo corre Pods |
| **Pod** | El contenedor donde corre un nodo. Si se reinicia o se mueve de máquina, el nodo **conserva su id** |
| **Primario / backup** | El rol de un nodo dentro de Trucardo. Lo decide la elección Bully, nunca Kubernetes |
| **Época** | Número que sube en cada elección y viaja en todos los mensajes entre nodos |
| **Manifiesto** | La descripción del estado deseado que se le entrega a Kubernetes |
| **Generador** | El módulo que produce los manifiestos a partir de `TRUCARDO_NODOS` |
| **Volumen** | Almacenamiento que sobrevive al contenedor. En este proyecto: un directorio de la máquina por nodo (`hostPath`) o, en la fase opcional, un volumen replicado de Longhorn |
| **Log persistente** | La copia en disco del log de operaciones de un nodo, de la que se reconstruye su estado al arrancar |
| **Telemetría** | Las tres señales de OpenTelemetry: **trazas** (el camino de una operación), **métricas** (cuánto y cada cuánto, a lo largo del tiempo) y **logs** (qué pasó, con detalle) |
| **Registro de construcción** | El archivo que documenta cada issue resuelta (ver [PLAN.md](PLAN.md), sección 1.7) |

---

## 4. Requisitos funcionales

Los códigos no se renumeran: los requisitos que se agregan después reciben el siguiente número libre, para que las issues ya escritas sigan citando lo mismo. Por eso el orden de las secciones no coincide con el de los números.

### 4.1. Despliegue en k3s (obligatorio)
| Código | Requisito |
| --- | --- |
| **RF-01** | **Fuente única.** Los manifiestos se generan a partir de la misma definición `TRUCARDO_NODOS` que usan los nodos y los clientes. La lista de nodos no se escribe en ningún otro lugar. |
| **RF-02** | **Nombres estables.** Cada nodo es alcanzable por los demás por el nombre que figura en `TRUCARDO_NODOS` (`nodo1`, `nodo2`, `nodo3`), sin IPs escritas en ningún archivo. |
| **RF-03** | **Clientes externos.** Un cliente de consola fuera del cluster puede jugar apuntando a la IP de **cualquier** máquina. |
| **RF-04** | **Reinicio automático.** Si el proceso de un nodo termina o deja de responder en su puerto del cluster, Kubernetes lo reinicia sin intervención humana. |
| **RF-05** | **Reubicación.** Si se apaga una máquina, sus nodos vuelven a correr en otra máquina en **90 s o menos**. |
| **RF-06** | **Dispersión.** En funcionamiento normal, cada nodo corre en una máquina distinta. Es una **preferencia**: si una máquina falta, dos nodos pueden compartir otra. |
| **RF-07** | **Identidad única.** Nunca corren dos procesos con el mismo id de nodo por culpa de una actualización. |
| **RF-08** | **Arranque seguro.** Un nodo que arranca o se reinicia **no asume el rol de primario** hasta ganar una elección o reconocer a un primario vigente. No puede quedar de primario con el estado vacío. |
| **RF-09** | **Actualización sin corte.** Se puede cambiar la versión de los nodos, de a uno, con una partida en curso. |
| **RF-10** | **Funcionalidad intacta.** Todo lo del Proyecto 1 sigue funcionando: juego, Bully con épocas, réplica, puesta al día, Lamport, reconexión del cliente, `historial` y `quien_es`. `docker compose` sigue sirviendo para correr todo en una sola máquina. |
| **RF-11** | **Cluster local.** Se puede levantar un cluster k3s de tres máquinas simuladas en una sola computadora, para desarrollar y probar. |
| **RF-12** | **Experimentos de falla reproducibles**, con evidencia guardada (salidas de comandos y capturas). |

### 4.2. Persistencia con volúmenes (recomendada)
| Código | Requisito |
| --- | --- |
| **RF-17** | **Log en disco, opcional por entorno.** Si está definida `TRUCARDO_DATOS`, el nodo guarda en ese directorio cada operación **antes** de confirmarla (el primario, antes de responder al cliente; un backup, antes de dar el ack) y también su época. Al arrancar, reconstruye su estado desde ahí. Sin la variable, funciona exactamente igual que antes. |
| **RF-18** | **Recuperación consistente.** Un nodo que vuelve con su disco **nunca** conserva operaciones que contradigan al primario vigente: las que divergen se descartan y recibe las que le faltan. La elección prefiere el log más actualizado, comparando primero la época de la última operación y después su número. |
| **RF-19** | **Un volumen por nodo** en `docker compose` y en k3s. En k3s, el volumen no impide la reubicación (RF-05): si el nodo se muda de máquina, arranca con lo que haya allí y se pone al día por la red. |
| **RF-20** | **Apagón total.** Si se apagan las tres máquinas y vuelven, las partidas en curso siguen donde estaban, siempre que sus operaciones hubieran llegado a los backups. |

### 4.3. Observabilidad con OpenTelemetry (fase extra)
| Código | Requisito |
| --- | --- |
| **RF-13** | **Telemetría opcional.** Si está definido el destino OTLP, cada nodo exporta su telemetría. Si no, funciona exactamente igual que sin ella. |
| **RF-14** | **Propagación de contexto** en los dos canales —Pyro5 (cliente → nodo) y TCP/JSON (nodo ↔ nodo)— y entre los hilos que lanza cada nodo. |
| **RF-15** | ***Spans* de dominio** para jugada, réplica, elección y puesta al día, con época, número de operación, sello de Lamport y rol como atributos. Los latidos se trazan **sólo** cuando son rechazados. |
| **RF-16** | **Jaeger desplegado** tanto con `docker compose` como en k3s. Cada *span* indica el Pod y la máquina donde se ejecutó. |
| **RF-21** | **Métricas de dominio:** operaciones por tipo, latencia de confirmación, época y rol de cada nodo, atraso de cada backup, operaciones confirmadas con menos acks de los esperados, elecciones y su duración, y latidos perdidos. Dos nodos que se declaran primarios a la vez se ven en un solo panel. |
| **RF-22** | **Logs correlacionados.** Cada línea de log del nodo se exporta con sus datos (nodo, rol, época, Lamport) y, si ocurrió dentro de un *span*, con su `trace_id`, para saltar del log a la traza. La salida por consola no cambia. |
| **RF-23** | **Un solo destino de telemetría.** Los nodos envían todo a un *Collector* de OpenTelemetry, que reparte las trazas a Jaeger, las métricas a Prometheus y los logs a Loki. Grafana muestra métricas y logs, y enlaza a Jaeger. Funciona con `docker compose` y en k3s. |

### 4.4. Almacenamiento replicado con Longhorn (fase opcional)
| Código | Requisito |
| --- | --- |
| **RF-24** | **Volumen que viaja con el Pod.** Con una opción del generador, cada nodo usa un volumen replicado de Longhorn en lugar del directorio de la máquina. Sin la opción, el despliegue no cambia. |
| **RF-25** | **Reubicación con datos.** Si se apaga una máquina, el nodo vuelve en otra **con su log**. Se mide el tiempo de reubicación y se compara con RF-05 y con el volumen local. |

---

## 5. Requisitos no funcionales

| Código | Requisito |
| --- | --- |
| **RNF-01** | **TDD.** Cada issue que cambia código Python agrega tests unitarios de **ese** cambio, escritos antes que el código. Para commitear tiene que pasar **la suite completa**, no sólo los tests nuevos. |
| **RNF-02** | **YAGNI.** No se construye nada que no pida una issue. Lo que no está en el plan no se hace; si hace falta, primero se agrega una issue. |
| **RNF-03** | **DRY.** Cada decisión vive en un solo lugar: la lista de nodos (`TRUCARDO_NODOS`), la versión de k3s, el nombre de la imagen, los tiempos del cluster (`nodo/config.py`), la regla de puertos externos, el directorio de datos de cada nodo y el destino de la telemetría. |
| **RNF-04** | **Clean Code** según la skill `ub-mode` (versionada en `.claude/skills/ub-mode/`). |
| **RNF-05** | **Trazabilidad.** Issue → rama → un commit → PR → merge → registro de construcción. |
| **RNF-06** | **Reproducible.** Desde un `git clone`, con Docker y las instrucciones del `README.md`. |
| **RNF-07** | **Dependencias mínimas.** No se agrega una dependencia si la biblioteca estándar alcanza. Toda dependencia nueva se fija con versión exacta y se justifica en el registro. |
| **RNF-08** | **Tiempos coherentes entre capas.** Trucardo decide primero (detecta la caída del primario a los 3 s) y Kubernetes repara después: su detección tiene que ser más lenta que la de Trucardo. |
| **RNF-09** | **Estilo de la casa.** Español en documentos, mensajes y nombres; identificadores y nombres de archivo sin acentos, como el resto de Trucardo. |

## 6. Restricciones

- **Plazo:** jueves 26/11/2026.
- k3s sólo corre en **Linux**: las máquinas reales tienen que ser Linux (las VMs del laboratorio sirven).
- **Longhorn** necesita `open-iscsi` en cada máquina y puede no funcionar en el cluster local simulado con contenedores. Si no funciona, esa fase se prueba sólo en máquinas reales o VMs.
- **Versiones fijas:** Python 3.10 (la imagen de Trucardo) y k3s `v1.37.2+k3s1`.
- Dos personas: las issues se resuelven de a una por vez, en orden (ver [PLAN.md](PLAN.md), sección 1.3).

## 7. Fuera de alcance (YAGNI)

Se deja afuera a propósito. Si alguno hace falta, primero se agrega una issue que lo justifique.

| Qué | Por qué no |
| --- | --- |
| Alta disponibilidad del plano de control (3 servidores k3s con etcd) | Es el tema de otro grupo (etcd). Con un solo servidor alcanza para mostrar los principios |
| Arreglar el cerebro dividido (quórum) | Kubernetes no lo resuelve y no es el tema. Se **muestra** como límite en los experimentos. Por lo mismo, una operación confirmada sin acks puede perderse aunque haya disco |
| ***Autoscaling*** (HPA) | **No aplica** a Trucardo:<br>• todas las escrituras pasan por el primario, así que un nodo más no suma capacidad, suma réplicas que esperar;<br>• los nodos tienen id fijo en `TRUCARDO_NODOS` y la elección depende de él, mientras que el *autoscaling* crea Pods idénticos y sin identidad;<br>• achicar mata nodos, y puede matar al primario;<br>• Trucardo casi no usa CPU, que es lo que mide el HPA.<br>Tendría sentido con las mesas repartidas entre varios grupos de tres nodos (*sharding*), escalando un enrutador sin estado delante. Queda como trabajo futuro |
| Helm, Kustomize, operadores | El generador ya produce los manifiestos desde una sola fuente. Longhorn se instala con su manifiesto oficial, sin Helm |
| Un Service que apunte sólo al primario | El cliente ya sabe encontrar al primario |
| Registro de imágenes propio o CI que publique imágenes | La imagen se carga directo en cada máquina |
| Otros almacenamientos en red (NFS, Ceph) | Longhorn alcanza para mostrar un volumen que viaja con el Pod |

## 8. Criterios de aceptación de la entrega

1. Desde un `git clone`, siguiendo el `README.md`, se levanta el cluster local, se despliega Trucardo y dos clientes juegan una partida.
2. Los experimentos de falla (reinicio, proceso colgado, máquina apagada, actualización) se reproducen con el resultado documentado.
3. Si se completó la fase recomendada: el experimento del apagón total se reproduce y las partidas siguen.
4. La suite completa pasa en el último commit de `main`.
5. Cada issue cerrada tiene su PR mergeado y su registro de construcción.
6. Las fases extra que no se completen quedan con sus issues abiertas y se mencionan en el informe como trabajo futuro.
