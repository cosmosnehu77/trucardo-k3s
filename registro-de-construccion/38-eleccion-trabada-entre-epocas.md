# #38 — Elección trabada entre candidatos de épocas distintas

| Campo | Valor |
| --- | --- |
| Issue | #38 |
| Rama | `issue-38-eleccion-trabada-entre-epocas` |
| Requisitos | RF-08, RF-10 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que dos candidatos en épocas distintas no se contesten «mando yo» mutuamente. Con N1 en la época 2 y N2 en la 1, N2 le ganaba a N1 por id y N1 le ganaba a N2 por época. Los dos se retiraban a esperar un `COORDINADOR` que nadie mandaba, y la elección sólo se destrababa si se perdía alguna respuesta.

## Qué se hizo
- **`nodo/cluster/eleccion.py`:** las credenciales pasan a ser la tupla `(epoca, ultimo_seq, id)`. `_al_eleccion` compara la suya con la del candidato **como una sola tupla**: `le_gano = mias > suyas`. Desaparece la regla aparte `su_epoca < mi_epoca`.
- **`tests/test_membresia.py`:**
  - dos tests nuevos, en la sección «eleccion entre epocas distintas»;
  - un ayudante `_membresia`, que arma un nodo sin arrancarlo. `_arrancar` lo usa, y el test determinístico también, para no repetir el armado (DRY).
- **`PLAN.md`:** estado de la #38.

## Por qué así
- **La tupla es un orden total.** Los dos lados comparan lo mismo con la misma regla, así que entre dos candidatos siempre exactamente uno le gana al otro. Es la misma forma que ya usa `_le_cedo` para los `COORDINADOR` y los latidos: `(epoca, id)`.
- **No choca con la #23 (D15).** La #23 cambia las credenciales a `(época de la última operación, ultimo_seq, id)`. Con esta issue la forma de la tupla ya es esa: la #23 sólo reemplaza la época actual por la de la última operación, en `_credenciales` y en el mensaje.
- **No cambia lo que ya se decidía.** Antes la época mayor ya ganaba siempre (desde un lado). Ahora gana igual, pero desde los dos lados. Entre nodos de la misma época sigue decidiendo (`ultimo_seq`, id), como antes.
- **Alternativa descartada:** que quien recibe una `ELECCION` de época mayor adopte esa época antes de comparar. No alcanza si los dos pedidos se cruzan: el de época menor manda su `ELECCION` antes de adoptar la otra, el de época mayor le contesta «mando yo», y el cruce se repite. Además, adoptar la época de un candidato que todavía no ganó mezcla «quién se postula» con «quién manda», que hoy separa `lo_rechazo`.

## Tests
- **Agregados:**
  - `test_dos_candidatos_de_epocas_distintas_no_se_contestan_mando_yo_los_dos`: determinístico, sin red. Arma dos nodos en las épocas 2 y 1 con el mismo `ultimo_seq` y llama a `_al_eleccion` de cada uno con la `ELECCION` del otro. Sólo el de época 2 puede contestar «mando yo».
  - `test_dos_nodos_en_epocas_distintas_eligen_un_solo_primario`: dos nodos reales que, ya con primario elegido, quedan sin primario en las épocas 5 y 3 y convocan a la vez. Con `timeout_eleccion` de 30 s, tienen que quedar con un solo primario reconocido por los dos en menos de 3 s: así no se puede destrabar por *timeout*.
- **Los dos fallaron antes del cambio** por la razón esperada:

  ```
  FALLA test_dos_candidatos_de_epocas_distintas_no_se_contestan_mando_yo_los_dos -> el de epoca menor no le puede contestar mando_yo
  FALLA test_dos_nodos_en_epocas_distintas_eligen_un_solo_primario -> tiene que quedar un solo primario reconocido por los dos
  ```

  Y después del cambio:

  ```
  ok    test_dos_candidatos_de_epocas_distintas_no_se_contestan_mando_yo_los_dos
  ok    test_dos_nodos_en_epocas_distintas_eligen_un_solo_primario
  ```

## Verificación
```
$ docker compose run --build --rm tests
174 tests, todo ok
```

Cinco corridas más, seguidas y sin carga:

```
$ docker compose run --rm tests        # x5
174 tests, todo ok                     # las 5 corridas
```

La verificación bajo carga (20 corridas con las 12 CPU ocupadas) es el criterio de la #39, que sigue a esta.

## Pendientes o riesgos detectados
- **Época actual en lugar de época de la última operación.** Un backup que adoptó una época nueva pero todavía no recibió la puesta al día le gana a uno de época anterior con más operaciones. Sin disco esas operaciones no estaban confirmadas por el primario nuevo, así que no se pierde nada confirmado. Con disco, la #23 lo resuelve al pasar a la época de la última operación.
- La falla aislada de `test_no_anuncia_reintento_mientras_la_eleccion_corre` vista en la #18 (9 reintentos) es compatible con este bug, pero no está confirmado que viniera de acá. La revisión de los tests de membresía sigue en la #39.
