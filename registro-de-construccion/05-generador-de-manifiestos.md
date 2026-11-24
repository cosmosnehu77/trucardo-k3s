# #5 — Generador de manifiestos: un Deployment y un Service por nodo

| Campo | Valor |
| --- | --- |
| Issue | #5 |
| Rama | `issue-05-generador-de-manifiestos` |
| Requisitos | RF-01, RF-02, RF-07 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Un módulo que genere los manifiestos de Kubernetes a partir de `TRUCARDO_NODOS`: por cada nodo, un Deployment de 1 réplica con estrategia `Recreate` y un Service con el nombre del host. Tiene que validar que cada host sirva como nombre de Service e imprimir JSON.

## Qué se hizo
- **`despliegue/manifiestos.py`** (nuevo):
  - `manifiestos(texto_nodos, imagen)`, función **pura** que devuelve la lista de objetos, ordenados por id;
  - por cada nodo, un **Deployment** `trucardo-nodo<id>`:
    - 1 réplica y estrategia `Recreate` (D3);
    - el comando `python -m nodo.servidor <id>`;
    - `TRUCARDO_NODOS` con el texto de entrada **idéntico**;
    - `imagePullPolicy: IfNotPresent` (D10);
  - por cada nodo, un **Service** llamado como el host, con los puertos `pyro` y `cluster` (D5);
  - las etiquetas `app: trucardo` y `nodo: <id>` unen cada Service con su Deployment;
  - antes de generar nada, valida que cada host sea un nombre **DNS-1035**. Si no lo es, `ValueError` con el host en el mensaje;
  - `python3 -m despliegue.manifiestos --imagen trucardo:local` imprime un `List` de Kubernetes en JSON (D2). Con un host inválido, termina con el error y código 1.
- **`nodo/config.py`:** `texto_nodos()` lee `TRUCARDO_NODOS` con su valor por defecto. La usan `nodos()` y el generador.
- **`Dockerfile`:** copia `despliegue/`, para que la suite corra igual en Docker.
- **`tests/test_manifiestos.py`** (nuevo): ver *Tests*.
- **`PLAN.md`:** estado de la #5.

## Por qué así
- **La función recibe el texto y no el diccionario de nodos.** La issue pide que la variable del Pod sea **idéntica** a la de entrada. Reconstruirla desde los `Nodo` podría cambiarla (espacios, orden). Con el texto, se parsea una sola vez con `nodo.config.nodos()` y se copia tal cual.
- **`texto_nodos()` en `nodo/config.py` (DRY).** El borrador leía `TRUCARDO_NODOS` y su valor por defecto en el generador, repitiendo lo que ya hacía `nodos()`. Ahora la variable se lee en un solo lugar.
- **La regla de puertos vive en `_puertos(nodo)`.** Deployment y Service los toman de ahí, así que un nombre no se puede desincronizar. La #6 suma ahí la regla de NodePort (D6).
- **`List` en vez de varios documentos.** `kubectl apply -f` lo acepta y un solo `json.dumps` lo produce, sin PyYAML (D2, RNF-07).
- **Validar en la entrada (`ub-mode`).** Si un nombre no es DNS-1035, Kubernetes rechaza el Service al aplicarlo, con media configuración ya creada. Validar antes de generar nada da un error claro y no deja nada a medias.
- **YAGNI:** sin NodePort (#6), sin *probes*, tolerancias ni anti-afinidad (#7), sin volúmenes (#24). Cada cosa llega con su issue.
- **Cómo se trabajó:**
  - un subagente implementador escribió el borrador fuera del repo mientras se cerraban la #38 y la #39;
  - un subagente revisor auditó el diff contra PLAN 1.1, 1.4 y `ub-mode`. Sus cuatro hallazgos menores se aplicaron:
    - `_entorno` se importa de `tests/test_config.py` en vez de copiarse;
    - el test del contenedor compara la lista exacta de puertos y la cantidad de Deployments;
    - tests del borde válido (63 caracteres) y del error del CLI;
    - `_puertos(nodo)`.

## Tests
- **Agregados** (`tests/test_manifiestos.py`, 10 tests):
  - un Deployment y un Service por nodo, ordenados por id, con etiquetas y selector coherentes;
  - `Recreate` y 1 réplica;
  - el contenedor: comando con el id, imagen, `IfNotPresent` y los dos puertos con nombre;
  - `TRUCARDO_NODOS` idéntica a la entrada, aun con espacios;
  - el Service: nombre del host, selector y los dos puertos;
  - hosts inválidos (`Nodo_1`, `10.0.0.1`, `1nodo`, `nodo-`, 64 caracteres) dan `ValueError`, y los bordes válidos (`a`, `nodo-1`, 63 caracteres) pasan;
  - el CLI imprime JSON válido, con la variable y sin ella;
  - el CLI termina con error ante un host inválido.
- **El test falló antes del cambio** por la razón esperada:

  ```
  ModuleNotFoundError: No module named 'despliegue.manifiestos'
  ```

## Verificación
```
$ docker compose run --build --rm tests
184 tests, todo ok
```

El CLI desde la raíz, como dice la issue:

```
$ TRUCARDO_NODOS="1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603" \
    python3 -m despliegue.manifiestos --imagen trucardo:local > trucardo.json
$ TRUCARDO_NODOS="1@Nodo_1:9501:9601" python3 -m despliegue.manifiestos --imagen x
host invalido para un Service de Kubernetes (DNS-1035, max 63): 'Nodo_1'     # código de salida 1
```

**Prueba simulada en k3s.** El criterio de aceptación se verifica formalmente en la #8, pero se adelantó una prueba en un k3s efímero: un solo servidor `rancher/k3s:v1.37.2-k3s1` en Docker, con la imagen importada con `ctr images import` (D10).

```
$ kubectl apply -f trucardo.json
deployment.apps/trucardo-nodo1 created
service/nodo1 created
deployment.apps/trucardo-nodo2 created
service/nodo2 created
deployment.apps/trucardo-nodo3 created
service/nodo3 created
$ kubectl get pods
trucardo-nodo1-574f46b9-dp48d     1/1     Running   0          12s
trucardo-nodo2-56cf9c48d9-ldqtn   1/1     Running   0          12s
trucardo-nodo3-7cbd6cb645-swzvd   1/1     Running   0          12s
$ kubectl run q --rm -i --image=trucardo:local ... -- python -m cliente.quien_es
│ 1    │ nodo1:9501 │ BACKUP   │ 3                │ 1     │ 0          │
│ 2    │ nodo2:9502 │ BACKUP   │ 3                │ 1     │ 0          │
│ 3    │ nodo3:9503 │ PRIMARIO │ 3                │ 1     │ 0          │
```

El JSON aplicado es idéntico, byte a byte, a la salida final del generador.

## Pendientes o riesgos detectados
- **Arranque con la red de Services todavía no lista.** En el k3s recién creado, los tres nodos convocaron su primera elección antes de que las conexiones a los Services funcionaran. Nadie contestó y los tres se coronaron en la época 1:

  ```
  20:24:01 [N1│BACKUP│e=0│L=1] nadie me gana (contestaron 0 de 2): me corono
  20:24:02 [N2│BACKUP│e=0│L=1] nadie me gana (contestaron 0 de 2): me corono
  20:24:02 [N3│BACKUP│e=0│L=1] nadie me gana (contestaron 0 de 2): me corono
  20:24:17 [N1│BACKUP│e=1│L=89] N3 es el primario de la epoca 1
  ```

  En cuanto la red respondió, los latidos resolvieron el empate por (época, id): quedó N3, en unos 15 s. No es un error del protocolo sino del momento: con el cluster vacío no se pierde nada. Con partidas en curso es el mismo riesgo de varios primarios que el plan ya acepta en D4 y que la #16 muestra como «cerebro dividido»: Trucardo se corona sin mayoría y las épocas lo acotan. Hay que observarlo en la #8 (cluster local) y tenerlo en cuenta en la #7, donde se definen las *probes*.
