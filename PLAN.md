# Plan de trabajo — Trucardo en k3s

Este plan dice **qué se hace, en qué orden y cómo**. Los requisitos están en [REQUISITOS.md](REQUISITOS.md).

El trabajo está partido en **issues completables**. Cada una está publicada en GitHub con el mismo número que tiene acá, de modo que `#5` en este plan es la issue #5 del repositorio. GitHub numera issues y PRs con la misma secuencia: los números que no aparecen en el plan (#19, #20, …) son PRs.

> [!IMPORTANT]
> Si vas a trabajar en este repo, **leé primero la sección 1 completa**. Las reglas no son sugerencias: una issue que no las cumple no está terminada.

---

## 1. Reglas de trabajo

### 1.1. Principios

| Principio | Qué significa acá |
| --- | --- |
| **YAGNI** | Sólo se hace lo que pide la issue en curso. Si aparece algo que «estaría bueno», se anota como issue nueva en la sección 10 de este plan y **no** se hace en la rama actual. La sección 7 de [REQUISITOS.md](REQUISITOS.md) lista lo que se dejó afuera a propósito. |
| **DRY** | Cada decisión vive en un solo lugar. Las fuentes únicas de este proyecto son:<br>• lista de nodos → `TRUCARDO_NODOS`, leída con `nodo.config.nodos()`<br>• tiempos del cluster → `nodo/config.py`<br>• regla de puertos externos → una función del generador<br>• versión de k3s → el `compose.yaml` del cluster local<br>• nombre de la imagen → un parámetro del generador<br>• directorio de datos de un nodo → `TRUCARDO_DATOS` en el nodo, y una función del generador que arma la ruta de cada nodo en la máquina<br>• destino de la telemetría → `OTEL_EXPORTER_OTLP_ENDPOINT`, configurado en un solo módulo (`nodo/telemetria.py`)<br>Si para cambiar algo hay que tocar dos archivos, hay una duplicación que resolver. |
| **Clean Code** | Se sigue la skill **`ub-mode`** de Robert C. Martin, versionada en `.claude/skills/ub-mode/`. Con Claude Code, se invoca con `/ub-mode` al empezar cada issue. Resumen: test que falla primero; el cambio más chico que lo hace pasar; después ordenar; una decisión en un lugar; validar los datos donde entran y adentro confiar; restar antes de sumar. |
| **Comentarios** | En el código **nuevo**, un comentario (o *docstring*) se escribe sólo cuando es **imprescindible o claramente útil**: el *por qué* de algo que el código no puede decir solo. Por ejemplo, una restricción externa, un valor que parece arbitrario o una trampa conocida. El *qué* y el *cómo* los dicen los nombres y la estructura del código. La historia y la justificación de cada cambio ya quedan en la issue y en su registro de construcción, así que no se repiten en comentarios (DRY).<br>Los comentarios que **ya existen** en el código del Proyecto 1 **no se tocan**: ni se borran ni se reescriben. Única excepción: si una issue cambia el código que un comentario describe y el comentario queda falso, se corrige lo mínimo y se anota en el registro. |

> [!NOTE]
> La skill menciona tres herramientas de Uncle Bob (*crapper*, *dryer*, *mutator*). **No se instalan:** no está verificado que soporten Python y el plazo es corto. Sus umbrales —funciones simples y cubiertas, sin bloques duplicados, sin código muerto— se revisan a mano en cada PR. Si después hacen falta, se agrega una issue.

La skill se restaura en otra computadora con:

```bash
npx skills experimental_install
```

Ese comando lee la versión fijada en `skills-lock.json`.

### 1.2. El ciclo de una issue, paso a paso

Se hace **siempre** en este orden. Los comandos asumen que estás en la raíz del repo.

1. **Tomar la issue.** Que sea la siguiente del plan y que sus dependencias estén cerradas. Asignátela en GitHub:

   ```bash
   gh issue edit NN --add-assignee @me
   ```

2. **Actualizar `main`.**

   ```bash
   git switch main && git pull --ff-only
   ```

3. **Crear la rama** con el formato `issue-NN-descripcion-corta`:

   ```bash
   git switch -c issue-NN-descripcion-corta
   ```

4. **Borrar la rama anterior** (regla de borrado con retraso, ver 1.3).
5. **Escribir el test que falla** (ver 1.4) y correrlo: tiene que fallar **por la razón esperada**.
6. **Hacer el cambio más chico** que lo haga pasar.
7. **Ordenar** (*refactor*) sin cambiar el comportamiento, según `ub-mode`.
8. **Correr la suite completa** (ver 1.4). Si falla cualquier test, viejo o nuevo, no se sigue.
9. **Escribir el registro de construcción** (ver 1.7).
10. **Un solo commit** con todo: código, tests y registro (ver 1.5).
11. **Subir la rama y abrir el PR** (ver 1.6).
12. **Mergear** cuando la verificación del PR esté en verde. La rama **no** se borra ahora.

### 1.3. Ramas

- Una rama por issue, siempre creada desde `main` actualizado.
- Nombre: `issue-NN-descripcion-corta` (minúsculas, sin acentos, palabras separadas por guiones). Ejemplo: `issue-05-generador-de-manifiestos`.
- **Borrado con una de retraso.** La rama de una issue **no** se borra al mergear. Se borra cuando se crea la rama de la issue **siguiente**. Así, en todo momento queda en GitHub sólo la rama de la última issue mergeada, por si hay que revisarla o recuperar algo.

  Comandos, justo después de crear la rama nueva:

  ```bash
  git branch -d issue-ANTERIOR
  ```

  ```bash
  git push origin --delete issue-ANTERIOR
  ```

  `git branch -d` (con `d` minúscula) se niega a borrar una rama que no fue mergeada. Si se niega, **pará**: la issue anterior no terminó.

  | Momento | Ramas que existen además de `main` |
  | --- | --- |
  | Se mergea el PR de #4 | `issue-04-…` |
  | Se crea `issue-05-…` y se borra `issue-04-…` | `issue-05-…` |
  | Se mergea el PR de #5 | `issue-05-…` |
  | Se crea `issue-06-…` y se borra `issue-05-…` | `issue-06-…` |

- **Una issue a la vez.** Como hay una sola rama activa, las issues se resuelven en orden. Mientras una persona programa, la otra revisa el PR anterior, prepara el informe o los experimentos.
- **La «rama anterior»** es siempre la de la **última issue mergeada**, sin importar quién la hizo.

### 1.4. Tests

- **Dónde:** en `tests/`, un archivo `test_<tema>.py` por tema. Las funciones se llaman `test_<lo_que_se_espera>`.
- **Correr la suite completa**, con cualquiera de estos dos:

  ```bash
  python3 run_tests.py
  ```

  ```bash
  docker compose run --build --rm tests
  ```

  Los dos corren lo mismo. Para el primero hacen falta Python 3.15 y las dependencias de `requirements.txt`. El segundo no necesita nada más que Docker. Lleva `--build` porque la imagen copia el código adentro: sin reconstruirla, se probaría el código de la última vez que se construyó.
- **Toda issue que cambia código Python** trae tests unitarios **de ese cambio**, escritos **antes** que el código.
- **Qué es un buen test acá** (`ub-mode`):
  - llama al código como lo haría quien lo usa y verifica lo que esa persona vería;
  - si seguiría pasando aunque todas las funciones devolvieran nada, no sirve;
  - si un test honesto no es posible, no se escribe uno malo.
- **Issues sin código Python** (infraestructura o documentación): no agregan tests, porque un test de un archivo de configuración no prueba nada útil. En su lugar llevan una **verificación reproducible**: los comandos que se corrieron y su salida, pegados en el registro. La issue lo aclara en su campo *Tests*. Igual tienen que pasar la suite completa.
- **Regla de oro: no se commitea con la suite en rojo.** Desde la issue #3:
  - en la computadora, el *hook* `.githooks/pre-commit` corre la suite con Docker y rechaza el commit si falla. Se activa **una vez por clon**:

    ```bash
    git config core.hooksPath .githooks
    ```

  - en GitHub, el *workflow* `.github/workflows/suite.yml` corre **el mismo script** en cada PR y en cada push a `main`. Un PR con la verificación en rojo no se mergea;
  - el *hook* prueba los archivos tal como están en la carpeta, no sólo lo que está en el *stage*. Como cada issue lleva un solo commit con todo, en la práctica es lo mismo;
  - `git commit --no-verify` saltea el *hook*, pero el PR lo vuelve a verificar. No se usa.

### 1.5. Commit

- **Uno solo por issue.** Lleva el código, los tests y el registro de construcción.
- **Formato del mensaje:**

  ```
  #NN Titulo de la issue

  Por que: el problema o requisito que resuelve (RF-xx).
  Que cambio: los cambios, en dos o tres lineas.
  Como se probo: tests agregados y resultado de la suite (N tests, todo ok).
  ```

- **Si hay que corregir algo después de abrir el PR**, se corrige el mismo commit, para que siga siendo uno:

  ```bash
  git commit --amend
  ```

  ```bash
  git push --force-with-lease
  ```

### 1.6. Pull request y merge

- **Abrir el PR:**

  ```bash
  git push -u origin issue-NN-descripcion-corta
  ```

  ```bash
  gh pr create --fill
  ```

- **Título:** el mismo que el commit (`#NN Titulo de la issue`).
- **Cuerpo:** `Closes #NN`, un resumen de lo hecho y el resultado de la suite.
- **Merge**, con *merge commit* y **sin** `--delete-branch`, porque la rama se borra después (ver 1.3):

  ```bash
  gh pr merge NN --merge
  ```

- **Quién mergea:** quien abrió el PR, después de que la otra persona lo haya mirado. Si la otra persona no está disponible y el plazo aprieta, alcanza con que la verificación del PR esté en verde.

### 1.7. Registro de construcción

- Cada issue resuelta deja un archivo en `registro-de-construccion/NN-descripcion-corta.md`, con el mismo nombre que la rama sin el prefijo `issue-`.
- Usa la plantilla `registro-de-construccion/00-plantilla.md`.
- Sirve para reconstruir **cómo** se hizo el proyecto y **por qué** se tomó cada decisión, y es material directo para el informe.
- Se escribe **antes** del commit y va **en el mismo commit**.

### 1.8. Definición de terminado

Una issue está terminada cuando se cumple **todo** esto:

- [ ] Los criterios de aceptación de la issue se cumplen.
- [ ] Si hay código Python: tiene tests nuevos que fallaban antes del cambio.
- [ ] La suite completa pasa.
- [ ] Un único commit con el formato de 1.5.
- [ ] El registro de construcción está escrito y va en el commit.
- [ ] El PR está mergeado y la issue cerrada (con `Closes #NN`).
- [ ] La rama de la issue anterior fue borrada (local y remota).
- [ ] No se agregó nada que la issue no pidiera (YAGNI) ni se duplicó ninguna decisión (DRY).
- [ ] El código nuevo sólo tiene los comentarios imprescindibles, y los comentarios existentes siguen como estaban (ver 1.1).

---

## 2. Decisiones de diseño transversales

Las toma el plan para que no se rediscutan en cada issue. Si una resulta equivocada, se cambia **acá** primero.

| # | Decisión | Por qué |
| --- | --- | --- |
| D1 | Los manifiestos los genera un módulo Python (`despliegue/manifiestos.py`) a partir de `TRUCARDO_NODOS`, en lugar de escribirse a mano | Fuente única (RF-01, DRY). Kustomize o YAML a mano obligarían a repetir la lista de nodos |
| D2 | El generador emite **JSON**, no YAML | `kubectl` acepta JSON y la biblioteca estándar alcanza. Evita sumar PyYAML (RNF-07) |
| D3 | Un **Deployment de 1 réplica por nodo**, con estrategia `Recreate` | Los nodos tienen id: no son réplicas intercambiables. `Recreate` evita dos procesos con el mismo id durante una actualización (RF-07) |
| D4 | Deployment y no StatefulSet | El StatefulSet no se recupera solo de una máquina apagada (lo demuestra la nota de investigación). Con Deployments la reubicación es automática (RF-05), y el riesgo de duplicado ante una partición lo acotan las épocas de Trucardo |
| D5 | Un Service por nodo, con **el mismo nombre que el host** en `TRUCARDO_NODOS` | La configuración de los nodos no cambia: `nodo1` ya resuelve (RF-02) |
| D6 | Clientes externos por **NodePort**, con puerto externo = puerto interno + 21000 (9501 → 30501, 9601 → 30601) | Cae dentro del rango de NodePort (30000–32767) y es deducible: una regla en una sola función |
| D7 | *Liveness probe* TCP al puerto del cluster, con una detección **más lenta** que `TIMEOUT_CAIDO` | Trucardo decide primero y Kubernetes repara después (RNF-08). La probe se calcula desde `nodo/config.py` |
| D8 | Tolerancia de **10 s** a máquinas `unreachable` / `not-ready` (el valor por defecto es 300 s) | Reubicación en ≈1 min (RF-05) |
| D9 | Anti-afinidad **preferida**, no obligatoria | Si fuera obligatoria, con una máquina caída el nodo reubicado no tendría dónde ir (RF-06) |
| D10 | La imagen se carga directo en cada máquina (`docker save` → `k3s ctr images import`), con `imagePullPolicy: IfNotPresent` | Sin registro de imágenes (YAGNI) |
| D11 | Cluster local: k3s en contenedores con `docker compose` e **IPs fijas** | Así se probó en la investigación. Con IPs dinámicas, un agente reiniciado cambia de IP y no vuelve |
| D12 | El log persistente es opcional y se activa con `TRUCARDO_DATOS` | Sin la variable, el nodo es el del Proyecto 1 y los tests existentes no cambian (RF-17). `docker compose` y el generador la definen |
| D13 | Formato en disco: un archivo **JSONL** de sólo agregado, una operación por línea, con `fsync` antes de confirmar. La época va en un archivo aparte que se reescribe de forma atómica (archivo temporal + `os.replace`) | Biblioteca estándar (RNF-07). Una operación confirmada tiene que estar en disco. Si el proceso muere a mitad de una línea, esa última línea incompleta se descarta al leer |
| D14 | En k3s, volumen **`hostPath` por nodo** (`/var/lib/trucardo/nodo<id>`, tipo `DirectoryOrCreate`), no un PVC de `local-path` | Un PVC de `local-path` ata el Pod a su máquina: si se apaga, el Pod queda `Pending` y se rompe la reubicación (RF-05). Con `hostPath`, si el Pod se muda arranca con lo que haya en la máquina nueva y se pone al día por la red (RF-19). La ruta incluye el id para que dos nodos en la misma máquina no se pisen |
| D15 | Recuperación al estilo **Raft**: el backup informa número y época de su última operación; si no coinciden con el log del primario, recorta hasta el último punto en común y recibe el resto. La elección compara (época de la última operación, número, id) | Con disco, dos logs del mismo largo pueden ser distintos. Es la regla de coincidencia de logs de Raft, reducida a lo que necesita Trucardo (RF-18) |
| D16 | Telemetría configurada en **un solo módulo** (`nodo/telemetria.py`) con **un solo destino** OTLP. Mientras sólo haya trazas, el destino es Jaeger; al sumar métricas y logs, pasa a ser un *Collector* de OpenTelemetry que reparte a Jaeger, Prometheus y Loki | Los nodos no cambian cuando cambia el *backend*: sólo cambia una variable (RNF-03) |
| D17 | Longhorn se instala con su **manifiesto oficial de versión fija** (`kubectl apply`), sin Helm. El generador elige el almacenamiento con `--almacenamiento hostpath\|longhorn`; por defecto, `hostpath` | YAGNI: Helm sería una herramienta más para un solo paquete. La opción deja intacto el despliegue recomendado |

---

## 3. Fase 0 — Base del repositorio y forma de trabajo

### #1 Planificación y reglas de trabajo
- **Requisitos:** RNF-02, RNF-03, RNF-04, RNF-05
- **Tipo:** documentación
- **Depende de:** —
- **Qué hacer:**
  - escribir `REQUISITOS.md` y `PLAN.md`;
  - crear `registro-de-construccion/` con su plantilla;
  - versionar la skill `ub-mode` (`.claude/skills/ub-mode/` y `skills-lock.json`).
- **Criterios de aceptación:**
  - cada issue del plan existe en GitHub con el mismo número;
  - la plantilla de registro tiene todas las secciones de 1.7.
- **Tests:** no aplica (documentación). La suite del Proyecto 1 tiene que pasar igual.

### #2 Limpieza del Proyecto 1
- **Requisitos:** RF-10, RNF-06
- **Tipo:** documentación
- **Depende de:** #1
- **Qué hacer:**
  - quitar `Primer proyecto.docx` y la regla `*.docx` de `.dockerignore`, que queda sin uso;
  - reemplazar el `README.md` del Proyecto 1 por uno del proyecto de promoción: qué es, en qué estado está, cómo correrlo hoy, y cómo se trabaja (enlaces a este plan);
  - el README completo del Proyecto 1 queda accesible en el tag `proyecto1-base`, sin duplicarlo.
- **Criterios de aceptación:**
  - el repo no tiene archivos propios de la entrega del Proyecto 1;
  - el README nuevo no promete nada que todavía no exista.
- **Tests:** no aplica (documentación). La suite tiene que pasar.

### #3 Verificación automática de la suite
- **Requisitos:** RNF-01, RNF-05
- **Tipo:** infraestructura
- **Depende de:** #2
- **Qué hacer:**
  - crear un *hook* `pre-commit` en `.githooks/` que corra la suite completa y bloquee el commit si falla. Se activa una vez por clon con `git config core.hooksPath .githooks`;
  - crear un *workflow* de GitHub Actions que corra **el mismo comando** en cada PR, con Python 3.10;
  - documentar la activación del hook en el README.
- **Criterios de aceptación:**
  - un commit con un test roto es rechazado en la computadora;
  - el PR muestra la verificación en verde.
- **Tests:** verificación reproducible, sin test unitario (es configuración). El registro muestra un commit rechazado por un test roto a propósito y la verificación del PR en verde.

---

## 4. Fase 1 — Trucardo listo para ser orquestado

### #4 Arranque sin primario asumido
- **Requisitos:** RF-08, RF-10
- **Tipo:** código
- **Depende de:** #3
- **Problema:** hoy, al arrancar, el nodo de id mayor se considera primario de la época 0 (`primario=max(cluster)` en `nodo/servidor.py`). Supongamos que Kubernetes lo reinicia en menos de 3 s y todavía no hubo ninguna elección. Los backups aceptarían su latido y quedaría de primario **con el estado vacío**. Antes no pasaba porque reiniciar un nodo era manual y lento.
- **Qué hacer:** que todo nodo arranque como **backup sin primario conocido**, de modo que el vigía convoque una elección enseguida. La elección Bully ya elige al más al día y, si empatan, al de id mayor.
- **Criterios de aceptación:**
  - tres nodos que arrancan juntos terminan con **un solo** primario;
  - un nodo solo se corona;
  - un nodo reiniciado vacío, antes de que los demás noten su ausencia, **no** queda de primario y termina con el log completo.
- **Tests** (en `tests/test_membresia.py`):
  - primero, un test que **reproduce** el problema con tres nodos en proceso, igual que los tests existentes, y que falla con el código actual;
  - después, los tests de arranque;
  - ajustar los tests existentes que asuman el arranque viejo.

---

## 5. Fase 2 — Despliegue en k3s

### #5 Generador de manifiestos: un Deployment y un Service por nodo
- **Requisitos:** RF-01, RF-02, RF-07
- **Tipo:** código
- **Depende de:** #4
- **Qué hacer:**
  - crear `despliegue/manifiestos.py` con una función **pura** `manifiestos(cluster, imagen)` que devuelva la lista de objetos, y una entrada de línea de comandos que imprima JSON:

    ```bash
    python3 -m despliegue.manifiestos --imagen trucardo:local > trucardo.json
    ```

  - por cada nodo de `nodo.config.nodos()`:
    - un **Deployment** de 1 réplica, estrategia `Recreate`, con el comando `python -m nodo.servidor <id>`, la variable `TRUCARDO_NODOS` **idéntica** a la de entrada e `imagePullPolicy: IfNotPresent` (D10);
    - un **Service** llamado como el host del nodo, con sus dos puertos (D5);
  - validar en la entrada que cada host sea un nombre DNS válido para un Service. Si no lo es, error claro;
  - agregar `despliegue/` al `Dockerfile`, para que la suite corra igual en Docker.
- **Criterios de aceptación:** `kubectl apply -f trucardo.json` en el cluster local levanta los tres nodos y eligen primario (se verifica en #8).
- **Tests** (`tests/test_manifiestos.py`):
  - un Deployment y un Service por nodo;
  - estrategia `Recreate` y 1 réplica;
  - comando con el id correcto;
  - la variable `TRUCARDO_NODOS` igual a la entrada;
  - el Service se llama como el host y expone los dos puertos;
  - un host inválido da error;
  - la salida es JSON válido.

### #6 Acceso de clientes desde fuera del cluster
- **Requisitos:** RF-03
- **Tipo:** código
- **Depende de:** #5
- **Qué hacer:**
  - los Services pasan a ser `NodePort`, con la regla de D6 en **una sola** función;
  - una opción del generador imprime el valor de `TRUCARDO_NODOS` que tienen que usar los clientes externos:

    ```bash
    python3 -m despliegue.manifiestos --clientes 192.168.0.11
    ```

- **Criterios de aceptación:** desde fuera del cluster, `cliente.cliente` y `quien_es` funcionan con ese valor.
- **Tests:**
  - los puertos externos siguen la regla y caen en el rango 30000–32767;
  - el valor para clientes se puede leer con `nodo.config.nodos()` (ida y vuelta) y apunta a los puertos externos;
  - un puerto interno que se saldría del rango da error.

### #7 Tolerancia a fallas de infraestructura
- **Requisitos:** RF-04, RF-05, RF-06, RNF-08
- **Tipo:** código
- **Depende de:** #6
- **Qué hacer:** el generador agrega a cada Deployment:
  - una *liveness probe* TCP al puerto del cluster, cuyo tiempo de detección (período × fallas permitidas) sea **mayor** que `TIMEOUT_CAIDO`, calculado desde `nodo/config.py` (D7);
  - tolerancias de 10 s (D8);
  - anti-afinidad **preferida** entre nodos de Trucardo (D9).

  Además, verificar en el cluster local con qué señal Kubernetes detiene el contenedor: la imagen declara `STOPSIGNAL SIGINT`. Si hace falta, ajustarlo y anotarlo en el registro.
- **Criterios de aceptación:**
  - se verifica en #8 y #10.
- **Tests:**
  - la probe apunta al puerto del cluster;
  - su detección supera `TIMEOUT_CAIDO`, y el test **sigue siendo cierto si se cambia** `TIMEOUT_CAIDO`;
  - las tolerancias son de 10 s;
  - la afinidad es preferida y no obligatoria.

### #8 Cluster local de desarrollo
- **Requisitos:** RF-11, RNF-06
- **Tipo:** infraestructura
- **Depende de:** #7
- **Qué hacer:**
  - crear `despliegue/cluster-local/compose.yaml`: un servidor k3s y dos agentes `rancher/k3s:v1.37.2-k3s1` con **IPs fijas** (D11) y el *kubeconfig* expuesto;
  - crear un script que cargue la imagen `trucardo:local` en las tres máquinas simuladas;
  - documentar en el README los pasos: levantar el cluster, cargar la imagen, generar y aplicar los manifiestos, jugar desde afuera.
- **Criterios de aceptación:** desde cero, se levantan tres máquinas `Ready`, tres Pods de Trucardo (uno por máquina), un primario elegido y dos clientes jugando.
- **Tests:** verificación reproducible (es infraestructura), con la salida de `kubectl get nodes`, `kubectl get pods -o wide` y `quien_es` en el registro.

### #9 Despliegue en máquinas reales
- **Requisitos:** RF-03, RF-05, RNF-06
- **Tipo:** documentación
- **Depende de:** #8
- **Qué hacer:** guía en el README para tres computadoras Linux de la misma red:
  - instalar el servidor y los agentes k3s;
  - abrir los puertos 6443/TCP, 8472/UDP y 10250/TCP;
  - cargar la imagen en cada máquina, generar y aplicar los manifiestos, y jugar.
- **Criterios de aceptación:** otra persona sigue la guía sin ayuda y llega a una partida jugándose en tres máquinas.
- **Tests:** verificación reproducible en las máquinas del laboratorio o en VMs, con salidas en el registro.

### #10 Experimentos de falla en k3s
- **Requisitos:** RF-04, RF-05, RF-09, RF-12
- **Tipo:** documentación
- **Depende de:** #9
- **Qué hacer:** `experimentos/README.md` con un guion reproducible de cada caso y lo que se espera ver:
  1. borrar el Pod del primario;
  2. colgar un nodo (`kill -STOP`);
  3. apagar una máquina con un backup;
  4. apagar la máquina del primario;
  5. actualizar la versión con una partida en curso, de a un nodo;
  6. apagar el servidor k3s;
  7. **límite:** partición de red, que muestra el cerebro dividido que Kubernetes no resuelve.
- **Criterios de aceptación:** cada caso tiene la evidencia (salidas con hora y capturas) y la explicación de **por qué** pasó lo que pasó.
- **Tests:** verificación reproducible (es el propio experimento).

---

## 6. Fase 3 — Persistencia con volúmenes (recomendada)

> [!NOTE]
> **Fase recomendada.** Va después de la fase 2 y antes de las extras: los volúmenes son parte de Kubernetes, y suman a la demo el experimento del apagón total. Si el plazo no alcanza, se entrega sin esta fase y se menciona en el informe.

### #22 Log de operaciones en disco
- **Requisitos:** RF-17, RNF-07
- **Tipo:** código
- **Depende de:** #10
- **Qué hacer:**
  - crear `nodo/disco.py`, el único módulo que lee y escribe el directorio de datos (D12, D13):
    - agregar una operación al log;
    - leer todas las operaciones guardadas;
    - guardar y leer la época;
  - si está `TRUCARDO_DATOS`, el nodo guarda cada operación **antes** de confirmarla: el primario, antes de responder al cliente; un backup, antes de dar el ack;
  - al arrancar, el nodo aplica las operaciones guardadas y recupera su época, y recién después atiende pedidos.
- **Criterios de aceptación:**
  - un nodo que se detiene y vuelve con el mismo directorio tiene el mismo `ultimo_seq`, la misma época y las mismas mesas;
  - sin la variable, el comportamiento y la suite son idénticos a antes.
- **Tests** (`tests/test_disco.py`, con directorios temporales):
  - lo que se guarda se lee igual y en orden;
  - una última línea incompleta se descarta y el resto se lee;
  - la época sobrevive a un reinicio;
  - un nodo reiniciado con su directorio reconstruye las mismas mesas;
  - una operación no se confirma si no se pudo escribir;
  - sin `TRUCARDO_DATOS` no se escribe nada.

### #23 Recuperación consistente desde el disco
- **Requisitos:** RF-18, RF-20
- **Tipo:** código
- **Depende de:** #22
- **Problema:** hoy, un nodo que vuelve viene vacío y nunca contradice a nadie. Con disco puede volver con operaciones que nadie más tiene. Ejemplo: un primario confirma la operación 41 y se cae antes de replicarla; el nuevo primario, en la época 1, escribe **otra** operación 41. El viejo vuelve diciendo «estoy en la 41», nadie nota que son distintas y las réplicas divergen en silencio.
- **Qué hacer** (D15):
  - el backup informa número **y época** de su última operación en los mensajes donde hoy informa `ultimo_seq`;
  - el primario compara con su log. Si no coinciden, o si el backup va más adelante, le indica desde dónde recortar y le manda el resto en la puesta al día;
  - el backup recorta el log en disco y en memoria, reconstruye su estado desde lo que quedó y aplica lo recibido;
  - las credenciales de la elección pasan de (`ultimo_seq`, id) a (época de la última operación, `ultimo_seq`, id).
- **Criterios de aceptación:**
  - después de cualquier secuencia de caídas y vueltas con disco, los tres nodos terminan con el mismo log;
  - tras un apagón total, gana la elección el nodo con el log más actualizado y las partidas siguen.
- **Tests** (tres nodos en proceso, como en `tests/test_membresia.py`, cada uno con su directorio temporal):
  - un backup que vuelve con su disco recibe sólo las operaciones que le faltan;
  - un backup con una cola divergente la recorta y termina igual al primario;
  - un log más corto pero de época mayor gana la elección a uno más largo de época menor;
  - tras detener y volver a arrancar los tres nodos, las mesas siguen.

### #24 Un volumen por nodo en docker compose y en k3s
- **Requisitos:** RF-19
- **Tipo:** código
- **Depende de:** #23
- **Qué hacer:**
  - en `docker-compose.yml`: un volumen con nombre por nodo, montado en el directorio de `TRUCARDO_DATOS`;
  - en el generador, para cada Deployment (D14):
    - un volumen `hostPath` en `/var/lib/trucardo/nodo<id>`, tipo `DirectoryOrCreate`, armado por **una sola** función;
    - montado en el contenedor y con `TRUCARDO_DATOS` apuntando al punto de montaje, ambos tomados de la misma constante;
  - en el cluster local de #8: un volumen de Docker en `/var/lib/trucardo` de cada máquina simulada, para que el apagón total se pueda probar.
- **Criterios de aceptación:** en el cluster local, un nodo reiniciado conserva su log; uno que se muda de máquina se pone al día por la red.
- **Tests** (en `tests/test_manifiestos.py`):
  - cada Deployment tiene su volumen `hostPath`, con una ruta distinta por nodo y tipo `DirectoryOrCreate`;
  - el punto de montaje y `TRUCARDO_DATOS` coinciden;
  - no aparece ningún PVC.

### #25 Experimentos de persistencia
- **Requisitos:** RF-12, RF-19, RF-20
- **Tipo:** documentación
- **Depende de:** #24
- **Qué hacer:** sumar a `experimentos/README.md`:
  1. reiniciar un backup: vuelve con su disco y la puesta al día empieza en su última operación, no en la 0;
  2. un nodo que se muda de máquina: arranca con lo que haya en la máquina nueva y se pone al día;
  3. **apagón total:** apagar las tres máquinas en medio de una partida y volver a encenderlas;
  4. **límite:** una operación confirmada sin acks se descarta al recortar. Es el mismo problema del cerebro dividido: sin quórum, el disco no alcanza.
- **Criterios de aceptación:** cada caso tiene su evidencia y la explicación de **por qué** pasó lo que pasó.
- **Tests:** verificación reproducible (es el propio experimento).

---

## 7. Fase 4 — Observabilidad con OpenTelemetry (extra)

> [!NOTE]
> **Fase extra.** Se empieza sólo si las fases 2 y 3 están completas y queda tiempo antes de la entrega. Primero las trazas (#11 a #16), después métricas y logs (#26 a #29). Si no se llega, las issues quedan abiertas como trabajo futuro y se mencionan en el informe.

### #11 SDK de OpenTelemetry, opcional por entorno
- **Requisitos:** RF-13, RNF-07
- **Tipo:** código
- **Depende de:** #10 (y #25 si se hizo la fase 3)
- **Qué hacer:**
  - agregar las dependencias de OpenTelemetry (API, SDK y exportador OTLP por HTTP) con versión exacta;
  - crear `nodo/telemetria.py` con **un solo punto** de configuración (D16):
    - si está `OTEL_EXPORTER_OTLP_ENDPOINT`, exporta con `service.name=trucardo-nodo<id>`;
    - si no, no hace nada.
- **Criterios de aceptación:** sin la variable, el comportamiento y la suite son idénticos a antes.
- **Tests:**
  - sin la variable, los *spans* no se registran;
  - con un exportador en memoria, se registran con el `service.name` correcto.

### #12 Contexto de traza entre nodos y entre hilos
- **Requisitos:** RF-14
- **Tipo:** código
- **Depende de:** #11
- **Qué hacer:**
  - inyectar `traceparent` en el diccionario que arma `Membresia.mensaje()` y extraerlo en `despachar()`. Con esos dos puntos se cubren todos los tipos de mensaje (DRY);
  - pasar el contexto a los hilos que lanza el nodo con **un único** ayudante, que se usa en todos los lugares que crean hilos.
- **Criterios de aceptación:** un mensaje enviado dentro de un *span* genera, en el nodo que lo recibe, un *span* hijo de la misma traza, aunque se envíe desde otro hilo.
- **Tests:** con tres nodos en proceso y un exportador en memoria, el *span* del receptor tiene como padre el del emisor, en los casos sincrónico y con hilos.

### #13 Contexto de traza entre cliente y nodo (Pyro5)
- **Requisitos:** RF-14
- **Tipo:** código
- **Depende de:** #12
- **Qué hacer:** el cliente envía el contexto en una anotación de Pyro5 (`current_context.annotations`, clave de 4 letras `TRCP`) y el nodo la extrae al atender la llamada.
- **Criterios de aceptación:** una jugada del cliente y su aplicación en el primario quedan en la misma traza.
- **Tests:** con un daemon Pyro5 real en un hilo (como en `tests/test_servidor.py`), el *span* del servidor pertenece a la traza del cliente.

### #14 *Spans* de dominio
- **Requisitos:** RF-15
- **Tipo:** código
- **Depende de:** #13
- **Qué hacer:**
  - crear *spans* con nombre propio para jugada, réplica (uno por backup), elección (`ELECCION` / `COORDINADOR`) y puesta al día, con atributos de época, número de operación, sello de Lamport y rol;
  - los latidos se trazan **sólo** si son rechazados (`EPOCA_VIEJA`).
- **Criterios de aceptación:** en Jaeger, una jugada se ve como un árbol con una réplica por backup, y una elección como un árbol de desafíos.
- **Tests:**
  - una jugada replicada produce un *span* de réplica por backup, con los atributos correctos;
  - una elección produce los *spans* de elección y de coordinador;
  - los latidos normales no producen *spans*.

### #15 Jaeger en docker compose y en k3s
- **Requisitos:** RF-16
- **Tipo:** código
- **Depende de:** #14
- **Qué hacer:**
  - sumar Jaeger (`jaegertracing/jaeger` con versión fija) al `docker-compose.yml`;
  - con una opción `--telemetria`, el generador agrega:
    - el Deployment y el Service de Jaeger, con la interfaz por NodePort según D6;
    - el destino OTLP en los nodos;
    - `OTEL_RESOURCE_ATTRIBUTES` con el Pod y la máquina, tomados de la *Downward API* de Kubernetes.
- **Criterios de aceptación:** en el cluster local, cada *span* muestra `k8s.pod.name` y `k8s.node.name`.
- **Tests:**
  - sin `--telemetria`, la salida es idéntica a la de antes de esta issue;
  - con `--telemetria` aparecen Jaeger, el destino OTLP y los atributos tomados de la *Downward API*.

### #16 Experimentos de falla con trazas
- **Requisitos:** RF-12, RF-15, RF-16
- **Tipo:** documentación
- **Depende de:** #15
- **Qué hacer:** repetir los experimentos de #10 con Jaeger abierto y capturar:
  - una jugada replicada;
  - la elección tras matar al primario;
  - un nodo que cambia de máquina, visible en el atributo `k8s.node.name`;
  - el cerebro dividido: jugadas confirmadas por dos primarios de épocas distintas.
- **Criterios de aceptación:** las capturas, con su explicación, están en el registro y en `experimentos/README.md`.
- **Tests:** verificación reproducible.

### #26 Métricas de dominio
- **Requisitos:** RF-13, RF-21
- **Tipo:** código
- **Depende de:** #16
- **Qué hacer:** en `nodo/telemetria.py`, sumar el proveedor de métricas con el mismo destino OTLP (D16), y medir:
  - operaciones por tipo (contador) y latencia de confirmación (histograma);
  - época y rol de cada nodo, y `ultimo_seq` (valores instantáneos);
  - atraso de cada backup, visto desde el primario: su `ultimo_seq` menos el del backup;
  - operaciones confirmadas con menos acks de los esperados: el indicador directo del riesgo de cerebro dividido;
  - elecciones iniciadas y su duración, y latidos perdidos.
- **Criterios de aceptación:** sin destino OTLP, nada cambia. Con destino, las métricas llegan con `service.name` y atributos de nodo.
- **Tests** (con el lector de métricas en memoria del SDK):
  - una jugada replicada suma al contador de su tipo y registra una latencia;
  - el rol y la época cambian tras una elección;
  - el atraso de un backup detenido crece;
  - una operación confirmada sin acks suma a su contador.

### #27 Logs correlacionados con las trazas
- **Requisitos:** RF-13, RF-22
- **Tipo:** código
- **Depende de:** #26
- **Qué hacer:**
  - en `nodo/telemetria.py`, sumar al logger `trucardo` un manejador de OpenTelemetry, además del de consola;
  - los datos del prefijo actual (nodo, rol, época, Lamport) salen de **una sola** función, que usan tanto la consola como los atributos del log exportado (DRY con `nodo/registro.py`);
  - al tomar la issue, verificar si la API de logs de OpenTelemetry para Python es estable en la versión fijada. Si sigue siendo experimental, anotarlo en el registro.
- **Criterios de aceptación:** la salida por consola es idéntica a antes. Una línea emitida dentro de un *span* se exporta con su `trace_id`.
- **Tests:**
  - una línea emitida dentro de un *span* lleva el `trace_id` y el `span_id` de ese *span*;
  - lleva como atributos nodo, rol, época y Lamport;
  - la línea de consola no cambia;
  - sin destino OTLP no se exporta nada.

### #28 Collector, Prometheus, Loki y Grafana
- **Requisitos:** RF-21, RF-22, RF-23
- **Tipo:** código
- **Depende de:** #27
- **Qué hacer:**
  - sumar, con versión fija, un *Collector* de OpenTelemetry que recibe OTLP y reparte: trazas a Jaeger, métricas a Prometheus y logs a Loki;
  - el destino OTLP de los nodos pasa a ser el Collector: cambia **un solo** valor (D16);
  - Grafana con sus fuentes de datos (Prometheus, Loki y Jaeger) y un tablero de Trucardo, todo provisto por archivos: rol y época por nodo, atraso de cada backup, operaciones por segundo, latencia p99 y un panel de **primarios simultáneos**;
  - desde una línea de log en Grafana, un enlace a su traza en Jaeger por `trace_id`;
  - en `docker-compose.yml` y en el generador con `--telemetria`. La configuración del Collector se emite como JSON, que el Collector acepta porque YAML incluye a JSON (D2).
- **Criterios de aceptación:** con una partida en curso, el tablero muestra los tres nodos, y desde un log se llega a su traza.
- **Tests:**
  - con `--telemetria` aparecen el Collector, Prometheus, Loki y Grafana;
  - los nodos apuntan al Collector y no a Jaeger;
  - la configuración del Collector tiene las tres canalizaciones con sus destinos;
  - sin `--telemetria`, la salida no cambia.

### #29 Experimentos con métricas y logs
- **Requisitos:** RF-12, RF-21, RF-22
- **Tipo:** documentación
- **Depende de:** #28
- **Qué hacer:** repetir experimentos de #10 con el tablero abierto y capturar:
  - la caída del primario: la época sube, el rol cambia y el atraso vuelve a 0 tras la puesta al día;
  - el cerebro dividido: el panel de primarios simultáneos marca 2, y crecen las operaciones confirmadas sin acks;
  - un log como «declaro caído a N3» y el salto a su traza;
  - una comparación con `kubectl logs` y `kubectl top`: qué agrega OpenTelemetry y qué ya daba Kubernetes.
- **Criterios de aceptación:** las capturas, con su explicación, están en el registro y en `experimentos/README.md`.
- **Tests:** verificación reproducible.

---

## 8. Fase 5 — Almacenamiento replicado con Longhorn (opcional)

> [!NOTE]
> **Fase opcional**, después de OpenTelemetry. Muestra la otra forma de no perder datos: en vez de que Trucardo se ponga al día por la red, el volumen viaja con el Pod. Sirve para comparar la réplica **en la aplicación** con la réplica **en el almacenamiento**.

### #30 Volumen replicado con Longhorn
- **Requisitos:** RF-24
- **Tipo:** código
- **Depende de:** #29 (o #25 si no se hizo la fase 4)
- **Qué hacer:**
  - verificar los requisitos de Longhorn en cada máquina (`open-iscsi`) y probar si corre en el cluster local. Si no corre, esta fase se prueba sólo en máquinas reales o VMs, y se anota en el registro;
  - instalar Longhorn con su manifiesto oficial de versión fija (D17) y documentarlo en el README;
  - configurar la política de Longhorn para Pods en una máquina caída, de modo que el volumen se libere y el Pod pueda arrancar en otra. Verificar el nombre exacto del ajuste en la versión fijada;
  - en el generador, con `--almacenamiento longhorn`: un PVC por nodo (`ReadWriteOnce`, clase `longhorn`) montado en el **mismo** punto que el `hostPath` (misma constante), en lugar del `hostPath`.
- **Criterios de aceptación:** con Longhorn, un nodo reiniciado conserva su log y, por defecto, el despliegue sigue siendo el de #24.
- **Tests** (en `tests/test_manifiestos.py`):
  - con `--almacenamiento longhorn`, un PVC por nodo con clase `longhorn` y `ReadWriteOnce`, y ningún `hostPath`;
  - el punto de montaje es el mismo que con `hostPath`;
  - sin la opción, la salida es idéntica a la de #24;
  - un valor desconocido de `--almacenamiento` da error.

### #31 Experimentos: el nodo se muda con su disco
- **Requisitos:** RF-12, RF-25
- **Tipo:** documentación
- **Depende de:** #30
- **Qué hacer:** sumar a `experimentos/README.md`:
  - apagar la máquina de un backup y de un primario con Longhorn: el nodo vuelve en otra máquina **con su log** y la puesta al día es corta;
  - medir el tiempo de reubicación y compararlo con RF-05 y con `hostPath`;
  - discutir el costo: Trucardo ya replica en tres nodos y Longhorn vuelve a replicar cada volumen. En producción se elige **una** de las dos capas para replicar, y por qué.
- **Criterios de aceptación:** cada caso tiene su evidencia y la explicación de **por qué** pasó lo que pasó.
- **Tests:** verificación reproducible.

---

## 9. Fase 6 — Entrega

### #17 README final y prueba limpia desde cero
- **Requisitos:** RNF-06 y los criterios de aceptación de la entrega (sección 8 de [REQUISITOS.md](REQUISITOS.md))
- **Tipo:** documentación
- **Depende de:** #10, y la última issue de cada fase que se haya completado (#25, #29, #31)
- **Qué hacer:**
  - completar el README: qué es, arquitectura en dos capas, cómo levantarlo, experimentos, límites y créditos al Proyecto 1;
  - clonar el repo en una carpeta vacía y seguir el README **al pie de la letra**.
- **Criterios de aceptación:** la prueba desde cero funciona sin pasos que no estén escritos.
- **Tests:** verificación reproducible (la propia prueba desde cero) y la suite completa.

---

## 10. Issues agregadas durante el trabajo

Las que aparecen mientras se resuelve otra issue. Por YAGNI no se resuelven en la rama donde se descubren: se agregan acá, con su número de GitHub, y se ubican en el orden según su prioridad.

Cuando lo que se agrega es una fase entera, sus issues van en su fase y acá queda sólo la issue de replanificación que las creó.

### #18 Test de membresía intermitente
- **Requisitos:** RNF-01
- **Tipo:** código
- **Depende de:** —
- **Prioridad:** resolver **antes de #4** si vuelve a fallar. Con el *hook* de #3, un test intermitente bloquea commits correctos.
- **Problema:** `test_membresia.test_si_el_primario_deja_de_latir_los_backups_lo_detectan` falló 1 de 5 corridas, mientras se corría al mismo tiempo que se construía la imagen. Las otras 4 pasaron. Depende de tiempos reales: espera a lo sumo 3 s que los backups den por caído al primario, cuando el *timeout* configurado en el test es de ese mismo orden.
- **Qué hacer:**
  - reproducir la falla bajo carga (por ejemplo, corriendo la suite mientras otra tarea usa la CPU);
  - corregir la **causa**: que la espera del test se derive de los tiempos configurados, en lugar de ser un número fijo. No alcanza con reintentar el test (`ub-mode`, *Fix Root Causes*).
- **Criterios de aceptación:** la suite pasa 20 veces seguidas bajo carga.
- **Tests:** el propio test corregido, más la verificación de las 20 corridas en el registro.

### #21 Replanificación: volúmenes, métricas y logs, y Longhorn
- **Requisitos:** RNF-02, RNF-05
- **Tipo:** documentación
- **Depende de:** #2
- **Qué hacer:**
  - sacar de «Fuera de alcance» la persistencia del log y las métricas y logs de OpenTelemetry, y reescribir por qué el *autoscaling* no aplica;
  - agregar los requisitos RF-17 a RF-25 y las decisiones D12 a D17;
  - agregar la fase 3 (persistencia, recomendada, #22 a #25), las métricas y logs a la fase de OpenTelemetry (#26 a #29) y la fase 5 (Longhorn, opcional, #30 y #31);
  - renumerar las fases y sus etiquetas en GitHub, y actualizar calendario y estado.
- **Criterios de aceptación:**
  - cada issue nueva existe en GitHub con el mismo número que en el plan y la etiqueta de su fase;
  - ninguna referencia entre documentos quedó apuntando a una sección que cambió de número.
- **Tests:** no aplica (documentación). La suite tiene que pasar.

### #33 Regla de comentarios en el código
- **Requisitos:** RNF-04, RNF-10
- **Tipo:** documentación
- **Depende de:** #21
- **Qué hacer:**
  - agregar la regla de comentarios a los principios del plan (sección 1.1), a la definición de terminado (1.8) y como RNF-10 en los requisitos:
    - en el código nuevo, un comentario sólo cuando es imprescindible o claramente útil;
    - los comentarios existentes del Proyecto 1 no se tocan;
    - el porqué de cada cambio vive en la issue y su registro de construcción, no en comentarios.
- **Criterios de aceptación:** la regla está en el plan, en los requisitos y en la definición de terminado.
- **Tests:** no aplica (documentación). La suite tiene que pasar.

### #36 Imagen con Python 3.15
- **Requisitos:** RNF-06, RNF-07
- **Tipo:** infraestructura
- **Depende de:** #3
- **Problema:** la imagen usa Python 3.10, que dejó de recibir parches de seguridad en octubre de 2026. En las computadoras de desarrollo hay Python 3.15, así que correr la suite sin Docker prueba otra versión que la del cluster.
- **Qué hacer:**
  - `Dockerfile`: `python:3.10-slim` → `python:3.15-slim`;
  - actualizar la versión en las Restricciones de `REQUISITOS.md` y en la sección 1.4 del plan.
- **Criterios de aceptación:** la suite pasa en la imagen nueva, con el *hook* y en la verificación del PR; OpenTelemetry 1.45.2 (fase 4) se instala en la imagen nueva.
- **Tests:** verificación reproducible (es configuración): la suite completa en la imagen nueva y la instalación de OpenTelemetry.

### #38 Elección trabada entre candidatos de épocas distintas
- **Requisitos:** RF-08, RF-10
- **Tipo:** código
- **Depende de:** #4
- **Prioridad:** inmediatamente después de #4. Las elecciones al arrancar hacen más probable que dos backups queden un rato en épocas distintas.
- **Problema:** en `Eleccion._al_eleccion`, un nodo le gana a un candidato si `su_epoca < mi_epoca` **o** si sus credenciales (`ultimo_seq`, id) son mayores. Supongamos N1 en la época 2 y N2 en la 1, con el mismo `ultimo_seq`:
  - N2 le contesta «mando yo» a N1, porque tiene id mayor;
  - N1 le contesta «mando yo» a N2, porque tiene época mayor;
  - los dos se retiran a esperar un `COORDINADOR` que nadie manda;
  - al vencer `TIMEOUT_ELECCION` reintentan y se repite, porque recibir una `ELECCION` no actualiza la época del que la recibe.
  
  Sólo se destraba si alguna respuesta se pierde por *timeout*.
- **Cómo se vio:** leyendo el código, durante la #18. En 1 de 20 corridas de la suite bajo carga, `test_no_anuncia_reintento_mientras_la_eleccion_corre` contó 9 reintentos, y no se repitió en 30 corridas sueltas. **No está confirmado** que esa falla venga de acá.
- **Qué hacer:**
  - primero, un test que reproduzca la contestación cruzada con dos nodos en épocas distintas, llamando a los manejadores (determinístico);
  - después, que la comparación sea un **orden total**, igual desde los dos lados. Hay dos opciones:
    - que quien recibe una `ELECCION` de una época mayor adopte esa época antes de comparar;
    - comparar (época, `ultimo_seq`, id) como una sola tupla.
  
  Se elige en la issue, de modo que no choque con la regla de la #23.
- **Criterios de aceptación:** dos candidatos en épocas distintas terminan con un solo primario sin depender de *timeouts*.
- **Tests:**
  - el de la contestación cruzada, que tiene que fallar antes del cambio;
  - uno con dos nodos reales en épocas distintas que eligen un solo primario.

### #39 Tests de membresía que miran estados transitorios
- **Requisitos:** RNF-01
- **Tipo:** código
- **Depende de:** #38
- **Problema:** varios tests de `tests/test_membresia.py` verifican un estado **en el instante** en que se cumple otra condición, con latidos de 0,1 s. Si el cluster sigue moviéndose (otro latido, una nueva elección), fallan aunque el protocolo haga lo correcto. En la #18 se corrigieron dos tests de este tipo. Quedaron fallas aisladas:
  - `test_el_primario_depuesto_se_baja`, en «volver a entrar a la vista»: 1 de 20 corridas de la suite, con las 12 CPU ocupadas;
  - `test_tres_nodos_se_ven`: 1 de 20 corridas sin carga.
- **Qué hacer:**
  - revisar cada test de membresía y separar lo que es una **garantía** del protocolo, que se espera con `_esperar`, de lo que es un **instante**, que no se verifica;
  - reproducir cada falla antes de corregirla, y anotar en el registro qué estado tenía el cluster;
  - si alguna falla resulta ser un bug del protocolo y no del test, abrir una issue aparte.
- **Criterios de aceptación:** la suite pasa 20 veces seguidas con las 12 CPU ocupadas.
- **Tests:** los propios tests corregidos, más la verificación de las 20 corridas en el registro.

---

## 11. Calendario sugerido

| Día | Issues | Nota |
| --- | --- | --- |
| Mar 24/11 | #1, #2, #21, #33, #3, #36, #4, #5 | Planificación, limpieza, replanificación, regla de comentarios, verificación automática y Python 3.15 (hechas), y primer código |
| Mié 25/11 | #38, #39, #6, #7, #8, #9, #10 | Resto del generador, cluster local, máquinas reales y experimentos |
| Jue 26/11 | #22 a #25, #17 | Persistencia (recomendada) a primera hora; después, prueba limpia y entrega. El informe se escribe en paralelo desde el martes, con los registros como insumo |
| Después | #11 a #16, #26 a #29, #30 y #31 | Fases extra: si no entran antes de la entrega, quedan como trabajo futuro y se mencionan en el informe |

## 12. Estado

| Issue | Título | Estado |
| --- | --- | --- |
| #1 | Planificación y reglas de trabajo | ✅ |
| #2 | Limpieza del Proyecto 1 | ✅ |
| #3 | Verificación automática de la suite | ✅ |
| #4 | Arranque sin primario asumido | ✅ |
| #38 | Elección trabada entre candidatos de épocas distintas | ✅ |
| #39 | Tests de membresía que miran estados transitorios | ✅ |
| #5 | Generador de manifiestos | ✅ |
| #6 | Acceso de clientes desde fuera del cluster | ✅ |
| #7 | Tolerancia a fallas de infraestructura | ✅ |
| #8 | Cluster local de desarrollo | ⏳ |
| #9 | Despliegue en máquinas reales | ⏳ |
| #10 | Experimentos de falla en k3s | ⏳ |
| #22 | Log de operaciones en disco (recomendada) | ⏳ |
| #23 | Recuperación consistente desde el disco (recomendada) | ⏳ |
| #24 | Un volumen por nodo en compose y k3s (recomendada) | ⏳ |
| #25 | Experimentos de persistencia (recomendada) | ⏳ |
| #11 | SDK de OpenTelemetry (extra) | ⏳ |
| #12 | Contexto entre nodos e hilos (extra) | ⏳ |
| #13 | Contexto cliente → nodo (extra) | ⏳ |
| #14 | *Spans* de dominio (extra) | ⏳ |
| #15 | Jaeger en compose y k3s (extra) | ⏳ |
| #16 | Experimentos con trazas (extra) | ⏳ |
| #26 | Métricas de dominio (extra) | ⏳ |
| #27 | Logs correlacionados con las trazas (extra) | ⏳ |
| #28 | Collector, Prometheus, Loki y Grafana (extra) | ⏳ |
| #29 | Experimentos con métricas y logs (extra) | ⏳ |
| #30 | Volumen replicado con Longhorn (opcional) | ⏳ |
| #31 | Experimentos: el nodo se muda con su disco (opcional) | ⏳ |
| #17 | README final y prueba limpia | ⏳ |
| #18 | Test de membresía intermitente | ✅ |
| #21 | Replanificación: volúmenes, métricas y logs, y Longhorn | ✅ |
| #33 | Regla de comentarios en el código | ✅ |
| #36 | Imagen con Python 3.15 | ✅ |

La tabla sigue el **orden de trabajo**, no el numérico.

Esta tabla se actualiza **en el commit de cada issue**: es parte del registro.
