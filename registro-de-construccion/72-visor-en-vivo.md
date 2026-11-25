# #72 — Visor en vivo del cluster

| Campo | Valor |
| --- | --- |
| Issue | #72 |
| Rama | `issue-72-visor-en-vivo` |
| Requisitos | RF-21 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Una página que muestre, en vivo, la arquitectura desplegada en k3s: qué corre en cada máquina, quién manda, qué se mandan los nodos y los jugadores. La figura es isométrica y cada pieza se explica al hacer clic.

## Qué se hizo
- `visor/estado.py`: funciones puras que arman la instantánea a partir de los nodos y Pods de Kubernetes, las respuestas de `listar_mesas` de cada nodo y las trazas de Jaeger.
- `visor/fuentes.py`: lee la API de Kubernetes con el token de la cuenta del Pod (sólo `urllib`), pregunta a los tres nodos en paralelo y busca en Jaeger las trazas de los últimos 20 s.
- `visor/servidor.py`: refresca la instantánea cada segundo y sirve `/api/estado` y la página en el puerto 9808.
- `despliegue/manifiestos.py`: con `--visor` suma la cuenta `visor`, un `ClusterRole` de sólo lectura (`nodes` y `pods`, `get` y `list`), el Deployment y un Service `NodePort` 9808 → 30808 con IP fija (10.43.0.95). Usa `hostAliases` y las mismas tolerancias que los nodos. Con `--telemetria` le pasa `VISOR_JAEGER`. No se puede usar junto con `--clientes`.
- `visor/figura/`: `build.mjs` dibuja la figura con el kit isométrico de anatomy (`kit/`, MIT) y la junta con `textos.js` (la ficha de cada pieza), `vivo.js` (aplica la instantánea y anima los pulsos) y `visor.css`. El resultado es `visor/pagina/index.html`, que se versiona.
- `Dockerfile`: copia `visor/`.

## Por qué así
- **El visor es un Pod más, con la misma imagen.** No suma dependencias: Python estándar para el servidor y un HTML estático para la página.
- **Sólo lectura.** El visor nunca crea ni borra nada. La cuenta sólo puede leer nodos y Pods.
- **Un mensaje es un span cuyo padre es de otro servicio.** Así se ven la jugada del cliente al primario y la réplica del primario a cada backup, sin cambiar el código de los nodos. Sin telemetría, los pulsos se deducen del estado: el latido por el rol, la réplica y la jugada por el avance de `ultimo_seq`, y el coordinador por el cambio de época.
- **Un Pod está listo según su condición `Ready`, no según sus contenedores.** Con la máquina caída, el kubelet no actualiza el estado del contenedor, pero el controlador de nodos sí baja la condición del Pod.
- **Alternativas descartadas:** un tablero más en Grafana (no dibuja la arquitectura ni sigue a los jugadores) y una página fuera del cluster con un kubeconfig (no se despliega con el resto).

## Tests
- **Agregados:** `tests/test_visor.py` (12 tests: máquinas, componentes, Pods, nodos, mesas, mensajes, jugadores y la instantánea) y 7 en `tests/test_manifiestos.py` para `--visor`.
- **El test nuevo falló antes del cambio:** al principio, porque no existían `visor.estado` ni `--visor`. Después de la prueba en el cluster se agregaron dos más, que fallaron antes de su arreglo:
  - `test_un_pod_en_una_maquina_caida_no_esta_listo_aunque_su_contenedor_diga_que_si`: el visor seguía marcando 3 de 3 nodos listos con una máquina caída;
  - `test_si_jaeger_no_contesta_ninguna_consulta_no_hay_telemetria`: si Jaeger no contestaba, el visor creía tener telemetría y dejaba de deducir los pulsos.

## Verificación
```
$ docker compose run --build --rm tests
...
284 tests, todo ok
```

En el cluster local, con `--telemetria --visor` y cuatro jugadores (dos con trazas):
- `/api/estado` devuelve las tres máquinas, los nueve Pods, los tres nodos con su rol y época, las dos mesas y los mensajes de Jaeger (`cliente-ana → nodo2`, `nodo2 → nodo1`, `nodo2 → nodo3`);
- se apagó `maquina3` (`docker compose stop maquina3`, 20:39:11). A los 50 s la figura la mostró caída, con sus Pods apagados, y a los 90 s N1 y N3 ya corrían en `maquina1`;
- a 390 px de ancho la página no tiene scroll horizontal.

## Pendientes o riesgos detectados
- **#73.** El visor mostró a N3 trabado en la op 16: cada segundo cortaba la puesta al día en la op 17, porque la jugada no era válida sobre su estado. Se abrió la #73.
- No se probó en las máquinas reales ni en la Raspberry.
- La página se versiona generada (unos 400 KB). Si se cambia `visor/figura/`, hay que correr `node visor/figura/build.mjs`.
