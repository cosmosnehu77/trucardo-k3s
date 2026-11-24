# #39 — Tests de membresía que miran estados transitorios

| Campo | Valor |
| --- | --- |
| Issue | #39 |
| Rama | `issue-39-tests-de-membresia-transitorios` |
| Requisitos | RNF-01 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Revisar los tests de `tests/test_membresia.py` para separar lo que es una **garantía** del protocolo (que se espera con `_esperar`) de lo que es un **instante** transitorio (que no se verifica), reproducir las fallas bajo carga antes de corregirlas y pasar la suite 20 veces seguidas con las 12 CPU ocupadas.

## Qué se hizo
- **`tests/test_membresia.py`:**
  - un ayudante nuevo, `_armado(membresias, primario=None)`, verifica que haya un único primario (o el esperado), que todos los nodos lo sigan en la misma época y que el primario vea en `vivos` al resto del diccionario recibido;
  - `_armado` reemplaza la espera `set(membresias[3].vivos) == {1, 2}` como precondición de «cluster armado» en todos los tests que la usaban (`test_si_el_primario_deja_de_latir_los_backups_lo_detectan`, `test_al_caer_el_primario_gana_uno_solo`, `test_si_queda_uno_solo_se_corona`, `test_entre_dos_coronados_de_la_misma_epoca_gana_el_id_mayor`, `test_no_anuncia_reintento_mientras_la_eleccion_corre`, `test_el_primario_depuesto_se_baja`, `test_el_latido_rechazado_igual_entra_al_reloj` y `test_el_zombie_que_replica_se_entera_y_se_baja`), y también unifica la espera en `test_dos_nodos_en_epocas_distintas_eligen_un_solo_primario`. No se reemplaza en `test_tres_nodos_se_ven`, donde ver a los dos backups es justamente lo que se verifica;
  - **`test_tres_nodos_se_ven`:** después de ver a los dos backups en `vivos`, la consulta `QUIEN` a N1 pasa a esperarse con `_esperar` hasta que N1 responda como backup de N3;
  - **`test_el_primario_depuesto_se_baja`:**
    - verifica la garantía del protocolo en vez de exigir que N2 siga siendo el primario: que el zombi deje de mandar en su época vieja y que el cluster quede `_armado` con N3 en una época mayor o igual a la nueva;
    - su *docstring* se corrigió lo mínimo («adopta al nuevo» → «adopta la epoca nueva») por quedar falso (excepción de la regla de comentarios, PLAN 1.1);
  - **otros tres instantes corregidos por lectura**, al revisar el módulo test por test:
    - `test_un_primario_reiniciado_vacio_no_vuelve_a_mandar`: `primario is None` → `primario != viejo`;
    - `test_tres_nodos_que_arrancan_juntos_eligen_uno_solo` y `test_al_caer_el_primario_gana_uno_solo`: el rol y la época de todos los nodos pasan a esperarse dentro de `_esperar` con `_armado`, en lugar de leerse sueltos afuera;
    - `test_si_el_ganador_muere_en_plena_eleccion_se_reintenta`: construye el nodo con `_membresia`, instala el espía sobre `eleccion.convocar` y recién después llama a `arrancar()`.
- **Código de Trucardo:** ningún cambio. El protocolo hacía lo correcto.

## Por qué así
- **La causa de las fallas reproducidas: `vivos` se llena antes del `COORDINADOR`.** En `Eleccion._coronarme`, el ganador llena `vivos` con quienes contestaron su `ELECCION` **antes** de mandar el `COORDINADOR`. Por eso `set(membresias[3].vivos) == {1, 2}` se vuelve cierta en el instante en que N3 se corona, cuando N1 y N2 todavía tienen `primario=None` y `epoca=0`:
  - `test_tres_nodos_se_ven` le preguntaba `QUIEN` a N1 en ese hueco y recibía `primario=None`;
  - `test_si_el_primario_deja_de_latir_los_backups_lo_detectan` mataba a N3 antes de que los backups llegaran a seguirlo: como nunca tuvieron primario, nunca llamaban a `sin_primario` y `detecciones` quedaba vacía.
- **No es un bug del protocolo.** Los backups adoptan al primario con el `COORDINADOR` o, a más tardar, con el próximo latido. En el primario, `vivos` significa «a quién replico», y quien acaba de contestar la elección está vivo. Lo que fallaba era usar `vivos` en los tests como «el cluster ya está armado»; `_armado` expresa esa condición completa en un solo lugar (DRY).
- **`test_el_primario_depuesto_se_baja`: quién gana después depende del instante.** Por lectura de código sobre la falla vista en la #18 (1 de 20 bajo carga, en «volver a entrar a la vista»), cuando el zombi N3 se baja por `EPOCA_VIEJA` queda con `primario=None`. Si su vigía convoca antes de recibir un latido de N2, como tiene el mismo `ultimo_seq`, le gana a N2 por id (Bully): N3 pasa a ser primario de una época nueva y N2 queda de backup con `vivos` vacío, así que `3 in membresias[2].vivos` nunca se cumple. Es la situación y no el protocolo: ya estaba anotada como inofensiva en la #4 («elecciones de más»). El test ahora pide la garantía, no quién gana.
- **Revisión test por test (garantía vs. instante).** Con ayuda de un subagente explorador se revisó el resto del archivo y se corrigieron, por lectura y sin reproducir, los tres casos donde todavía se leía un instante:
  - en `test_un_primario_reiniciado_vacio_no_vuelve_a_mandar`, un latido del primario vigente puede llegar entre `_arrancar` y el `assert`: lo que garantiza el arranque es que el reiniciado no vuelva a creerse primario (`!= viejo`), no que siga con `None`;
  - en `test_tres_nodos_que_arrancan_juntos_eligen_uno_solo` y `test_al_caer_el_primario_gana_uno_solo`, leer el rol o la época fuera de `_esperar` asume que todos convergen en el mismo paso;
  - en `test_si_el_ganador_muere_en_plena_eleccion_se_reintenta`, instalar el espía de `convocar` después de `_arrancar` podía perder la primera convocatoria si el hilo del vigía corría antes.
- **Alternativa descartada (YAGNI):** tocar `test_no_anuncia_reintento_mientras_la_eleccion_corre` más allá de su precondición (`_armado`). No falló en ninguna corrida, así que no se reescribe sin reproducir una falla.

## Tests
- **Modificados:** los tests de `tests/test_membresia.py` detallados en *Qué se hizo*, junto con el ayudante `_armado`. No se agregaron tests nuevos: la issue corrige tests existentes que miraban estados transitorios.
- **Reproducción antes del cambio** (código de `main` con la #38), en 20 corridas del módulo `test_membresia` con 12 procesos `yes` ocupando las 12 CPU: **4 fallas**:
  - `test_tres_nodos_se_ven`: 2/20 (`AssertionError` sin mensaje, en la respuesta a `QUIEN`);
  - `test_si_el_primario_deja_de_latir_los_backups_lo_detectan`: 2/20 («alguno lo tiene que dar por caido por el silencio»).

  `test_el_primario_depuesto_se_baja` no falló en esas 20 corridas.
- **Foto del cluster al fallar:** envolviendo `_apagar` del módulo para fotografiar a los nodos antes de apagarlos, se corrieron 60 rondas de esos dos tests bajo carga. Hubo **6 fallas** (3 y 3), las 6 con **el mismo estado**:

  ```
  N1:backup primario=None epoca=0 | N2:backup primario=None epoca=0 | N3:primario epoca=1 vivos=[1, 2]
  ```

## Verificación
Suite sin carga:

```
174 tests, todo ok
```

Criterio de aceptación: la suite completa, **20 veces seguidas con 12 procesos `yes` ocupando las 12 CPU**:

```
$ docker compose run --rm tests        # x20, con la carga corriendo
174 tests, todo ok                     # las 20 corridas
```

## Pendientes o riesgos detectados
- **Ningún pendiente nuevo de protocolo.**
- **Riesgos señalados por el explorador y no abiertos como issue:**
  - `latir_a` usa un *timeout* igual al intervalo de latido (0,1 s en los tests, 1 s en producción): bajo carga, un backup puede salir y volver a entrar a `vivos`. No afecta la corrección porque `vivos` se recompone en el próximo latido y ningún test exige que se mantenga estable sin latidos en el medio;
  - la reelección del primario depuesto que vuelve y gana por id es propia de Bully y ya estaba anotada en la #4 («elecciones de más»).
- **Hipótesis sin confirmar:** en `test_no_anuncia_reintento_mientras_la_eleccion_corre`, el explorador señaló que el contador escucha el logger compartido y podría contar reintentos de N1. Como no falló en ninguna corrida, quedó sin tocar (YAGNI).
