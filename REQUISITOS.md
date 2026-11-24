# Requisitos — Trucardo en k3s

Qué tiene que hacer este proyecto y bajo qué reglas. El **cómo** y el **orden** están en [PLAN.md](PLAN.md); cada issue del plan cita los requisitos que cumple por su código (`RF-xx`, `RNF-xx`).

---

## 1. Contexto

- **Trabajo de promoción** de Sistemas Distribuidos 2026 (UNPSJB), de a dos: Nehuén García y Alan Viera. **Entrega: jueves 26/11/2026.**
- La consigna pide investigar una tecnología de SD **no vista** en la materia, construir un ejemplo **básico pero funcional** que muestre sus principios, entregarlo en un repositorio con `README.md` e instrucciones claras (se recomienda Docker), y escribir un informe de hasta 10 páginas.
- **Tecnología elegida:** orquestación de contenedores con **Kubernetes (distribución k3s)**. Fase extra: trazas distribuidas con **OpenTelemetry + Jaeger**.
- **Base:** Trucardo, el servicio de truco distribuido del Proyecto 1 (primario-backup, elección Bully con épocas, log replicado, relojes de Lamport). El código tal como se entregó está marcado con el tag `proyecto1-base`.

## 2. Objetivo

Desplegar los tres nodos de Trucardo en un cluster **k3s de tres máquinas** para que Kubernetes se ocupe de que **los procesos existan** —reiniciarlos, reubicarlos y actualizarlos— mientras Trucardo conserva su propia tolerancia a fallas: quién es el primario y cuál es el estado de cada mesa.

> Kubernetes devuelve **procesos**; Trucardo devuelve **estado**. Ninguna de las dos capas hace el trabajo de la otra.

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
| **Registro de construcción** | El archivo que documenta cada issue resuelta (ver [PLAN.md](PLAN.md), sección 1.7) |

---

## 4. Requisitos funcionales

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

### 4.2. Trazas con OpenTelemetry + Jaeger (fase extra)
| Código | Requisito |
| --- | --- |
| **RF-13** | **Trazas opcionales.** Si está definido el destino OTLP, cada nodo exporta trazas. Si no, funciona exactamente igual que sin trazas. |
| **RF-14** | **Propagación de contexto** en los dos canales —Pyro5 (cliente → nodo) y TCP/JSON (nodo ↔ nodo)— y entre los hilos que lanza cada nodo. |
| **RF-15** | ***Spans* de dominio** para jugada, réplica, elección y puesta al día, con época, número de operación, sello de Lamport y rol como atributos. Los latidos se trazan **sólo** cuando son rechazados. |
| **RF-16** | **Jaeger desplegado** tanto con `docker compose` como en k3s. Cada *span* indica el Pod y la máquina donde se ejecutó. |

---

## 5. Requisitos no funcionales

| Código | Requisito |
| --- | --- |
| **RNF-01** | **TDD.** Cada issue que cambia código Python agrega tests unitarios de **ese** cambio, escritos antes que el código. Para commitear tiene que pasar **la suite completa**, no sólo los tests nuevos. |
| **RNF-02** | **YAGNI.** No se construye nada que no pida una issue. Lo que no está en el plan no se hace; si hace falta, primero se agrega una issue. |
| **RNF-03** | **DRY.** Cada decisión vive en un solo lugar: la lista de nodos (`TRUCARDO_NODOS`), la versión de k3s, el nombre de la imagen, los tiempos del cluster (`nodo/config.py`) y la regla de puertos externos. |
| **RNF-04** | **Clean Code** según la skill `ub-mode` (versionada en `.claude/skills/ub-mode/`). |
| **RNF-05** | **Trazabilidad.** Issue → rama → un commit → PR → merge → registro de construcción. |
| **RNF-06** | **Reproducible.** Desde un `git clone`, con Docker y las instrucciones del `README.md`. |
| **RNF-07** | **Dependencias mínimas.** No se agrega una dependencia si la biblioteca estándar alcanza. Toda dependencia nueva se fija con versión exacta y se justifica en el registro. |
| **RNF-08** | **Tiempos coherentes entre capas.** Trucardo decide primero (detecta la caída del primario a los 3 s) y Kubernetes repara después: su detección tiene que ser más lenta que la de Trucardo. |
| **RNF-09** | **Estilo de la casa.** Español en documentos, mensajes y nombres; identificadores y nombres de archivo sin acentos, como el resto de Trucardo. |

## 6. Restricciones

- **Plazo:** jueves 26/11/2026.
- k3s sólo corre en **Linux**: las máquinas reales tienen que ser Linux (las VMs del laboratorio sirven).
- **Versiones fijas:** Python 3.10 (la imagen de Trucardo) y k3s `v1.37.2+k3s1`.
- Dos personas: las issues se resuelven de a una por vez, en orden (ver [PLAN.md](PLAN.md), sección 1.3).

## 7. Fuera de alcance (YAGNI)

Se deja afuera a propósito. Si alguno hace falta, primero se agrega una issue que lo justifique.

| Qué | Por qué no |
| --- | --- |
| Alta disponibilidad del plano de control (3 servidores k3s con etcd) | Es el tema de otro grupo (etcd). Con un solo servidor alcanza para mostrar los principios |
| Persistir el log de jugadas en volúmenes | Si mueren los tres nodos a la vez, las partidas se pierden igual que en el Proyecto 1. Es una limitación conocida, no un objetivo |
| Arreglar el cerebro dividido (quórum) | Kubernetes no lo resuelve y no es el tema. Se **muestra** como límite en los experimentos |
| Helm, Kustomize, operadores, *autoscaling* | La membresía de Trucardo es fija (tres nodos): no hay nada que escalar ni que parametrizar más allá del generador |
| Un Service que apunte sólo al primario | El cliente ya sabe encontrar al primario |
| Registro de imágenes propio o CI que publique imágenes | La imagen se carga directo en cada máquina |
| Métricas y logs con OpenTelemetry | La fase extra cubre sólo trazas |

## 8. Criterios de aceptación de la entrega

1. Desde un `git clone`, siguiendo el `README.md`, se levanta el cluster local, se despliega Trucardo y dos clientes juegan una partida.
2. Los experimentos de falla (reinicio, proceso colgado, máquina apagada, actualización) se reproducen con el resultado documentado.
3. La suite completa pasa en el último commit de `main`.
4. Cada issue cerrada tiene su PR mergeado y su registro de construcción.
