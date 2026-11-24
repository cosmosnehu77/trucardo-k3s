# #1 — Planificación y reglas de trabajo

| Campo | Valor |
| --- | --- |
| Issue | #1 |
| Rama | `issue-01-planificacion` |
| Requisitos | RNF-02, RNF-03, RNF-04, RNF-05 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Definir qué se va a construir, en qué orden y con qué reglas, antes de escribir código. Así, cualquiera de los dos puede tomar la siguiente issue sin tener que preguntar cómo se trabaja.

## Qué se hizo
- **Repositorio:** se creó `trucardo-k3s` como **copia con historia** de Trucardo. El código de partida quedó marcado con el tag `proyecto1-base`.
- **`REQUISITOS.md`:** contexto, objetivo, glosario, requisitos funcionales (RF-01 a RF-16) y no funcionales (RNF-01 a RNF-09), restricciones, fuera de alcance y criterios de aceptación de la entrega.
- **`PLAN.md`:**
  - las reglas de trabajo: ciclo de una issue, ramas con borrado con retraso, tests, commit, PR, registro y definición de terminado;
  - once decisiones de diseño transversales;
  - diecisiete issues en cinco fases, más una sección para las issues que aparezcan durante el trabajo, con calendario y tabla de estado.
- **`registro-de-construccion/00-plantilla.md`:** la plantilla de este registro.
- **Skill `ub-mode`:** instalada con el comando pedido, en modo copia, para que quede versionada con el repo:

  ```bash
  npx skills add https://github.com/unclebob/ub-mode --skill ub-mode -a claude-code -y --copy
  ```

  Quedan `.claude/skills/ub-mode/` (licencia MIT) y `skills-lock.json`, con el commit fijado `3da62bf`.
- **Issues #1 a #18 en GitHub:** las #1 a #17 se crearon con un script que lee las secciones de `PLAN.md`, para que el texto de cada issue no se escriba dos veces (DRY). La #18 se agregó al detectar un test intermitente (ver *Verificación*).

## Por qué así
- **Repo nuevo con historia, no rama de Trucardo.** Trucardo es el Proyecto 1 entregado, y su historia incluye a otro integrante que hoy está en otro grupo de promoción. Un repo aparte deja intacto lo evaluado, tiene un README propio y conserva la autoría en `git log`.
- **Requisitos separados del plan.** Los requisitos dicen **qué**; el plan dice **cómo** y **cuándo**. Cada issue cita sus requisitos por código, así se puede seguir de punta a punta.
- **Glosario de máquina / nodo** (`ub-mode`, *Model the Domain*). En este proyecto «nodo» significa dos cosas: el *Node* de Kubernetes y el nodo de Trucardo. Fijar los términos evita errores en el código y en el informe.
- **Decisiones transversales en el plan.** Las toma una vez el plan (generador en JSON, un Deployment `Recreate` por nodo, NodePort + 21000, tiempos de la probe, etc.), con su porqué, para no rediscutirlas en cada issue.
- **Issues sin código Python sin test unitario.** La regla general es un test unitario por issue de implementación. Para las de infraestructura y documentación, un test de un archivo de configuración no probaría nada útil, y `ub-mode` dice que si un test honesto no es práctico, no se escribe uno malo. En su lugar se exige una verificación reproducible en el registro.
- **Herramientas de `ub-mode` (*crapper*, *dryer*, *mutator*) no instaladas.** No está verificado que soporten Python y el plazo es de dos días (YAGNI). Sus criterios se revisan a mano.
- **Alternativas descartadas:**
  - **Kustomize o Helm:** obligan a repetir la lista de nodos fuera de `TRUCARDO_NODOS`.
  - **StatefulSet:** no se recupera solo de una máquina apagada, como se vio en la investigación de k3s.
  - **Un solo Deployment de tres réplicas:** los nodos de Trucardo tienen id y no son intercambiables.

## Tests
No aplica: la issue no cambia código Python. La suite del Proyecto 1 se corrió igual (ver *Verificación*).

## Verificación
Suite completa en Docker, cinco corridas seguidas:

```
$ docker compose run --build --rm tests     # 1.ª, mientras se construía la imagen
167 pasaron, 1 FALLARON:
  - test_membresia.test_si_el_primario_deja_de_latir_los_backups_lo_detectan
$ docker compose run --rm tests             # 2.ª a 5.ª
168 tests, todo ok      (x4)
```

El test que falló depende de tiempos reales y ya venía así del Proyecto 1: esta issue no toca código. Se registró como **#18** en la sección 8 del plan, en lugar de arreglarlo en esta rama (YAGNI: la rama es de planificación).

## Pendientes o riesgos detectados
- **#18:** el test intermitente de membresía tiene que resolverse antes de #4 si vuelve a fallar, porque el *hook* de #3 bloquearía commits correctos.
- El plazo es justo: la fase 3 (OpenTelemetry + Jaeger) está marcada como **extra** y sólo se empieza si la fase 2 queda completa.
- **Alan tiene que ser agregado como colaborador** del repositorio (falta su usuario de GitHub).
