# #18 — Test de membresía intermitente

| Campo | Valor |
| --- | --- |
| Issue | #18 |
| Rama | `issue-18-test-de-membresia-intermitente` |
| Requisitos | RNF-01 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Corregir la **causa** de que `test_membresia.test_si_el_primario_deja_de_latir_los_backups_lo_detectan` falle a veces. El plan decía resolverla antes de la #4 si volvía a fallar, y volvió a fallar mientras se trabajaba en la #4. La #4 se pausó: sus cambios quedaron guardados con `git stash`, sin commit.

## Qué se hizo
- **`tests/test_membresia.py`:**
  - el test ya no pide que **los dos** backups estén sin primario **al mismo tiempo**. Ahora verifica dos cosas:
    - que los dos **dejan de seguir** al primario muerto;
    - que la **primera** vez que alguno lo da por caído por el silencio ocurre **no antes** del *timeout*;
  - un ayudante nuevo, `_registrando`, envuelve `sin_primario` de cada backup y anota en qué momento lo llamó;
  - el *docstring* y el comentario del test no cambian: siguen siendo ciertos;
  - **`test_el_primario_depuesto_se_baja`**, que tenía el mismo problema y apareció al correr la suite 20 veces:
    - el estado inicial del zombi («vuelve creyéndose primario») se verifica **antes** de que empiece a escuchar. Para eso, el ayudante `_arrancar` se partió en `_armar` (construir) y `arrancar()`;
    - la época y el primario del zombi se **esperan** en vez de leerse en el instante en que pasa a backup;
    - la época se compara con la que tiene N2 **en ese momento**, no con la que tenía al ganar.
- **`PLAN.md`:**
  - la #18 queda terminada en la tabla de estado;
  - se agregan la **#38** (elección trabada entre candidatos de épocas distintas) y la **#39** (revisar los demás tests de membresía) en la sección 10, el calendario y el estado.
- **Código de Trucardo:** ningún cambio. El protocolo hacía lo correcto.

## Por qué así
- **La hipótesis de la issue era otra.** El plan suponía que la espera fija de 3 s del test quedaba corta bajo carga. Al reproducir la falla se vio que no.
- **La causa real.** Cada vez que falló, el estado final del cluster era correcto:

  ```
  N1:backup primario=2 epoca=1 | N2:primario primario=2 epoca=1 | N3 (muerto)
  ```

  La elección había terminado bien. El test, en cambio, esperaba ver a N1 y N2 **los dos** con `primario is None` en el mismo instante. Ese instante puede no existir:
  - N2 detecta el silencio primero, convoca y gana en milisegundos;
  - N1 recibe el `COORDINADOR` de N2 **antes** de que se le venza su propio *timeout*, así que pasa de «primario 3» a «primario 2» sin quedar nunca sin primario.

  El test medía un estado transitorio, no una garantía del protocolo. Bajo carga, los dos *timeouts* se separan más y la ventana se cierra más seguido.
- **Lo que garantiza el protocolo**, que es lo que el test verifica ahora:
  - ningún backup sigue al primario muerto;
  - nadie lo da por caído antes del *timeout*.
- **Alargar la espera no habría servido.** El estado que buscaba el test, a veces, no llega nunca. Reintentar el test tampoco: esconde la causa (`ub-mode`, *Fix Root Causes*).
- **`test_el_primario_depuesto_se_baja` era de la misma familia.** Falló en 2 de 30 corridas bajo carga, siempre en la línea «vuelve creyéndose primario»: cuando el test llegaba a mirar, el latido de N2 ya había bajado al zombi, que hacía lo correcto. Las líneas siguientes tenían el mismo riesgo:
  - si el zombi se baja porque le rechazan **su** latido (`degradarme`), queda unos milisegundos con `primario=None` hasta el próximo latido de N2;
  - N2 puede volver a coronarse, y subir de época, cuando le llega la elección del zombi.
- **Las detecciones se registran envolviendo el método, no consultando el estado cada tanto.** Consultando, se ve el cambio tarde, y eso haría pasar el test aunque la detección hubiera sido antes de tiempo. Envolviendo el método se anota el momento exacto.

## Tests
- **Modificado:** `test_si_el_primario_deja_de_latir_los_backups_lo_detectan`, como se explica arriba.
- **Reproducción antes del cambio**, en `main`, con 12 procesos `yes` ocupando las 12 CPU:

  ```
  40 corridas del test → 4 fallas, todas con la elección ya terminada bien
  FALLA 25 N1:b p=2 e=1 | N2:p p=2 e=1 | N3:p p=3 e=0
  ```

- **El test nuevo sigue detectando el error que importa.** Se lo corrió contra un mutante cuyos backups usan un *timeout* de 0,05 s en vez de 0,4 s:

  ```
  mutante muerto: y no antes del timeout
  ```

- **Después del cambio, el mismo test bajo carga:** 40 corridas, 0 fallas.

## Verificación
Criterio de la issue: la suite completa 20 veces seguidas, bajo carga. **No se cumplió**, y se cerró igual por decisión del equipo (ver abajo).

| Tanda | Resultado | Falla |
| --- | --- | --- |
| 20 corridas con 12 procesos `yes` ocupando las 12 CPU, sólo con el primer test corregido | 19 bien | `test_el_primario_depuesto_se_baja` («vuelve creyéndose primario») y `test_no_anuncia_reintento_mientras_la_eleccion_corre` (9 reintentos) en la misma corrida |
| 20 corridas con la misma carga, con los dos tests corregidos | 19 bien | `test_el_primario_depuesto_se_baja`, en otra línea: «y volver a entrar a la vista del primario de verdad» |
| 20 corridas sin carga artificial | 19 bien | `test_tres_nodos_se_ven`, que esta issue no tocó |

```
$ docker compose run --build --rm tests
168 tests, todo ok
```

**Decisión (24/11/2026):** se cierra la #18 con el test de la issue corregido y probado, más el del zombi. El problema resultó más amplio que un test: varios tests de membresía miran un instante, con latidos de 0,1 s. La revisión completa queda en la issue **#39**, que hereda el criterio de las 20 corridas bajo carga y va después de la #4 y la #38. La #4 cambia el arranque de esos mismos tests, así que revisarlos antes sería hacer el trabajo dos veces. Mientras tanto, el *hook* puede rechazar alrededor de 1 de cada 20 commits correctos; se vuelve a correr.
La primera tanda de 20 corridas, con sólo el primer test corregido, dio 19 bien y 1 con dos fallas:
- `test_el_primario_depuesto_se_baja`, corregido arriba;
- `test_no_anuncia_reintento_mientras_la_eleccion_corre`, con 9 anuncios de reintento. No se repitió en 30 corridas sueltas bajo carga.

## Pendientes o riesgos detectados
- **#39, revisar los demás tests de membresía** que miran estados transitorios. Hereda el criterio de las 20 corridas bajo carga.
- **#38, elección trabada.** Al buscar la causa de los 9 reintentos se encontró, leyendo el código, que dos candidatos en épocas distintas pueden contestarse «mando yo» mutuamente y quedar esperando un `COORDINADOR` que nadie manda. No está confirmado que esa haya sido la falla. Es un cambio del protocolo y no de un test, así que por YAGNI se registró como la issue **#38** en lugar de arreglarlo en esta rama.
- **La #4 (arranque con elección) agrega elecciones al arrancar.** Hay que verificarla con la misma vara: 20 corridas bajo carga. Durante el trabajo pausado de la #4 apareció una falla aislada de `test_tres_nodos_se_ven`, que no se reprodujo en 40 corridas sueltas. Se vuelve a mirar ahí.
