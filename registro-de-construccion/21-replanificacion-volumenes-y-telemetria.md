# #21 — Replanificación: volúmenes, métricas y logs, y Longhorn

| Campo | Valor |
| --- | --- |
| Issue | #21 |
| Rama | `issue-21-replanificacion-volumenes-y-telemetria` |
| Requisitos | RNF-02, RNF-05 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Revisar tres puntos de «Fuera de alcance» de los requisitos:
- **Persistencia del log en volúmenes:** pasa a ser la opción recomendada.
- **Métricas y logs de OpenTelemetry:** se suman a la fase extra.
- **Longhorn:** un volumen que viaja con el Pod, como fase opcional después de OpenTelemetry.

Lo único que se descarta es el *autoscaling*, porque no aplica.

## Qué se hizo
- **`REQUISITOS.md`:**
  - contexto y objetivo con las fases nuevas;
  - glosario: *volumen*, *log persistente* y *telemetría*;
  - requisitos nuevos:
    - **RF-17 a RF-20**, persistencia;
    - **RF-21 a RF-23**, métricas, logs y Collector;
    - **RF-24 y RF-25**, Longhorn;
  - RF-13 pasa de «trazas opcionales» a «telemetría opcional»;
  - RNF-03 suma dos fuentes únicas: el directorio de datos y el destino de la telemetría;
  - una restricción nueva: Longhorn necesita `open-iscsi`;
  - «Fuera de alcance»:
    - salen la persistencia y las métricas y logs;
    - el *autoscaling* queda en una fila propia, con sus cuatro razones;
    - se suma «otros almacenamientos en red»;
  - criterios de entrega: el apagón total, si se hizo la fase recomendada.
- **`PLAN.md`:**
  - decisiones **D12 a D17**: variable `TRUCARDO_DATOS`, formato JSONL con `fsync`, `hostPath` por nodo, regla de recuperación al estilo Raft, telemetría en un solo módulo con un solo destino, y Longhorn sin Helm;
  - **fase 3 nueva**, persistencia (recomendada): #22 a #25;
  - la **fase 4**, ex fase 3, pasa a ser «Observabilidad»:
    - suma #26 a #29;
    - #11 crea `nodo/telemetria.py` en lugar de `nodo/trazas.py`;
    - la opción del generador de #15 pasa a llamarse `--telemetria`;
  - **fase 5 nueva**, Longhorn (opcional): #30 y #31;
  - la entrega pasa a ser la **fase 6**;
  - las secciones 8 a 10 pasan a ser 10 a 12;
  - calendario y tabla de estado actualizados.
- **`README.md`:** el resumen menciona la fase recomendada y las extras.
- **GitHub:**
  - etiquetas renombradas: `fase-3-extra` → `fase-4-extra` y `fase-4` → `fase-6`. Al renombrarlas, las issues existentes las conservan;
  - etiquetas nuevas: `fase-3` y `fase-5-opcional`;
  - issues **#21 a #31** creadas desde las secciones del plan.

## Por qué así
- **Persistencia antes que OpenTelemetry.** Los volúmenes son parte de Kubernetes, que es el tema; OpenTelemetry es un agregado. Además, suman el experimento más claro para la demo: el apagón total.
- **`hostPath` por nodo y no un PVC de `local-path` (D14).** El PVC ata el Pod a su máquina: si se apaga, el Pod queda `Pending` y se pierde la reubicación, que es lo que muestra el proyecto. Con `hostPath`, si el Pod se muda, se pone al día por la red como hoy.
- **La regla de recuperación es parte de la issue y no un detalle (D15).** Persistir es fácil; lo difícil es volver con datos viejos sin contradecir al primario. Sin la comparación de (número, época), un nodo que vuelve con una operación que nadie confirmó hace divergir las réplicas en silencio. Es la regla de coincidencia de logs de Raft, que conecta el proyecto con el tema de etcd.
- **La elección compara primero la época.** Hoy compara (`ultimo_seq`, id), y eso alcanza mientras un nodo que vuelve viene vacío. Con disco, un log más largo puede venir de una época vieja: la regla de Raft compara primero la época de la última operación.
- **Un solo módulo y un solo destino de telemetría (D16, DRY).**
  - `nodo/telemetria.py` en lugar de `nodo/trazas.py`, porque va a configurar las tres señales.
  - El Collector se suma recién con las métricas (#28). Mientras haya sólo trazas, el destino directo a Jaeger alcanza (YAGNI). Cuando aparece, cambia un solo valor.
- **Se renombraron cosas todavía no implementadas.** Cambiar `nodo/trazas.py` y `--trazas` ahora es gratis; cambiarlos después de #11 y #15 costaría una issue de *refactor*.
- **El *autoscaling* se descarta con razones.**
  - Las escrituras pasan todas por el primario.
  - Los nodos tienen identidad, y la elección depende de ella.
  - Achicar mata nodos.
  - El HPA mide CPU, y Trucardo casi no la usa.
  
  Queda como trabajo futuro el caso en que sí aplicaría: un enrutador sin estado delante de varios grupos de tres nodos.
- **Longhorn como comparación.** Trucardo ya replica en la aplicación; Longhorn replica en el almacenamiento. El experimento de #31 discute por qué en producción se elige una sola de las dos capas.
- **Los códigos de requisito no se renumeran.** Las issues ya publicadas citan RF-13 a RF-16; renumerar rompería esas referencias.
- **Alternativas descartadas:**
  - Agregar la persistencia en la sección de issues agregadas: es una fase entera, con orden propio.
  - Renumerar las issues de OpenTelemetry para que el plan quede en orden numérico: GitHub no permite cambiar números.

## Tests
No aplica: la issue no cambia código Python.

Verificación reproducible: que las issues nuevas existan con el número y las etiquetas del plan (ver *Verificación*).

## Verificación
```
$ python3 crear_issues_21.py PLAN.md          # lee las secciones ### #21 a #31 del plan
https://github.com/cosmosnehu77/trucardo-k3s/issues/21
...
https://github.com/cosmosnehu77/trucardo-k3s/issues/31
$ gh issue list --state all --json number,title,labels
21 Replanificación: volúmenes, métricas y logs, y Longhorn [fase-0, tipo:documentacion]
22–25 [fase-3]   26–29 [fase-4-extra]   30–31 [fase-5-opcional]
11–16 [fase-4-extra]   17 [fase-6]
$ docker compose run --rm tests
168 tests, todo ok
```

El script verifica que cada issue creada reciba el número que tiene en el plan. Las issues #11, #15 y #17 se actualizaron con su texto nuevo del plan: el nombre `nodo/telemetria.py`, la opción `--telemetria` y las dependencias de la entrega.

## Pendientes o riesgos detectados
- **El plazo.** La fase recomendada queda para el jueves 26 a primera hora. Si la fase 2 se atrasa, se entrega sin persistencia y se menciona en el informe.
- **Longhorn y el cluster local.** Puede no correr en k3s dentro de contenedores; #30 lo verifica primero.
- **La API de logs de OpenTelemetry para Python** puede seguir siendo experimental; #27 lo verifica al empezar.
