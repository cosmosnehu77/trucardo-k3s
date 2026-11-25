# #17 — README final y prueba limpia desde cero

| Campo | Valor |
| --- | --- |
| Issue | #17 |
| Rama | `issue-17-readme-final` |
| Requisitos | RNF-06 y los criterios de aceptación de la entrega (REQUISITOS §8) |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
- Completar el README: qué es, arquitectura en dos capas, cómo levantarlo, experimentos, límites y créditos al Proyecto 1.
- Clonar el repo en una carpeta vacía y seguir el README **al pie de la letra**.

## Qué se hizo
- **`README.md`:**
  - el estado: qué fases están hechas y cuál queda como trabajo futuro;
  - «Arquitectura: dos capas», con un diagrama y qué hace cada capa, citando las decisiones de PLAN §2;
  - «Experimentos», con lo que muestra cada grupo de los 19 casos;
  - «Límites y trabajo futuro»;
  - «Créditos», en lugar de «Origen».
- **`PLAN.md`:** estado de la #17.

## Por qué así
- **La #30 y la #31 (Longhorn) quedan abiertas.** Son la fase opcional. El cluster local no puede correr Longhorn: la imagen `rancher/k3s` no trae `iscsiadm` ni un gestor de paquetes para instalarlo, y Longhorn necesita `open-iscsi` en cada máquina. Probarlo pedía las máquinas reales o una imagen de k3s propia, con la entrega al día siguiente. El criterio 6 de la entrega prevé este caso: las issues quedan abiertas y el README las menciona como trabajo futuro.
- **Las guías de uso no cambiaron.** La prueba desde cero las valida tal como están.
- **Los límites citan los casos que los muestran,** así el informe puede remitir a la evidencia.

## Tests
Sin tests nuevos: es documentación (PLAN 1.4). La verificación es la propia prueba desde cero y la suite completa.

## Verificación
**Prueba desde cero.** Se bajó el cluster local con sus volúmenes (`down -v`), se borró la imagen `trucardo:local` y se clonó `main` en una carpeta vacía. Se siguió el README del clon. Las secciones que agrega esta rama no tienen pasos.

```
docker compose build nodo1                 → Image trucardo:local Built
compose ... up -d                          → maquina1, maquina2, maquina3 Started
compose ... exec maquina1 kubectl get nodes → las tres Ready
sh despliegue/cluster-local/cargar-imagen.sh → importada en las tres
manifiestos --imagen trucardo:local > trucardo.json; kubectl apply → 3 Deployments y 3 Services
compose ... exec maquina1 kubectl get pods -o wide
  trucardo-nodo1-…  Running  maquina2
  trucardo-nodo2-…  Running  maquina3
  trucardo-nodo3-…  Running  maquina1
manifiestos --clientes 172.30.0.11         → 1@172.30.0.11:30501:30601,2@…,3@…
```

Los dos jugadores corrieron con el comando del README (`docker run --rm -it … cliente.cliente leo` y `beto`), cada uno en su terminal. Un script contestaba cada menú: la primera carta, «quiero» a los cantos y «no» a otra partida.

```
leo:  GANASTE 15- 13     ¿Jugar otra? (s/n): n
beto: perdiste 13- 15    ¿Jugar otra? (s/n): n
quien_es → 1 BACKUP e=1 146 | 2 BACKUP e=1 146 | 3 PRIMARIO e=1 146
```

También se siguió la parte de telemetría:

- se cargaron las cinco imágenes y se aplicaron los manifiestos con `--telemetria`;
- quedaron 8 Pods `Running`;
- Grafana, Jaeger y Prometheus contestaron 200;
- el tablero mostró un solo primario.

Por último, `docker compose run --build --rm tests` en el clon (`258 tests, todo ok`) y `compose ... down`.

```
$ docker compose run --build --rm tests
258 tests, todo ok
```

## Pendientes o riesgos detectados
- **La #30 y la #31 quedan abiertas** como trabajo futuro (criterio 6 de la entrega).
- **El `down` del cluster avisa que la red sigue en uso** si queda algún contenedor conectado a `trucardo-k3s_maquinas`, como un `quien_es --seguir`. Las máquinas se bajan igual.
