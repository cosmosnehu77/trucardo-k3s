# #67 — El atraso de un backup se mide mal

| Campo | Valor |
| --- | --- |
| Issue | #67 |
| Rama | `issue-67-atraso-mal-medido` |
| Requisitos | RF-21 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Corregir dos errores de `trucardo.backup.atraso` que aparecieron en los experimentos de la #29:

1. **un backup del que el primario no sabe nada contaba desde la op 0.** En el caso 17, N2 informó N3 = 3662 ops de atraso, cuando le faltaban 4;
2. **un latido viejo pisaba un ack nuevo.** En el caso 16, con N1 colgado, el atraso de N2 marcaba 1.

## Qué se hizo
- **`nodo/telemetria.py`:** `_observar_atraso` observa sólo los nodos que están en `visto`.
- **`nodo/cluster/membresia.py`:** `anotar_seq` cuenta cuántas veces se anotó cada nodo (`version_seq`). `coronarme` anota con `anotar_seq`, así cuenta también.
- **`nodo/cluster/latido.py`:** `latir_a` lee esa cuenta antes de mandar el latido. Al volver, si cambió, no anota el `seq` de la respuesta.
- **`PLAN.md`:** estado de la #67.

## Por qué así
- **Lo que se anotó después de mandar el latido es más nuevo que su respuesta.** El latido viaja sin el lock, y una jugada puede anotar el ack de ese backup mientras tanto. Una cuenta por nodo detecta eso sin comparar valores.
- **No alcanza con quedarse con el mayor.** Un backup que recorta su log (#23) vuelve atrás de verdad, y el primario tiene que verlo. El segundo latido del test lo prueba: sin nada en el medio, un `seq` menor sí se anota.
- **El resto de `latir_a` no cambia.** «Entra a la vista» y la puesta al día siguen igual. Si la respuesta es vieja y difiere, se lanza una puesta al día de más, como antes: el backup la contesta con lo que tiene.
- **Cómo se trabajó:** un subagente implementador hizo los tests y el cambio, con los tests primero. El agente principal revisó el diff y verificó el criterio de aceptación en el cluster local.

## Tests
- **Agregados:**
  - `tests/test_metricas.py::test_primario_recien_coronado_no_informa_atraso_de_backup_desconocido`;
  - `tests/test_membresia.py::test_el_latido_viejo_no_pisa_un_ack_mas_nuevo`: reemplaza el envío del latido por uno que anota un ack «en vuelo» y contesta con un `seq` anterior.
- **Fallaron antes del cambio:** los dos, en su `assert`, por la razón esperada.

## Verificación
```
$ docker compose run --build --rm tests
258 tests, todo ok
```

**En el cluster local**, con la imagen nueva y un cliente automático jugando, se colgó un backup (N1) 20 s con `kill -STOP`:

```
hora      atraso N3→N1  atraso N3→N2  rol N1
11:44:26             3             0       0
11:44:31             8             0       -
11:44:36            12             0       -
11:44:41            16             0       -
11:44:46             0             0       0
```

El atraso de N2 se queda en 0. En la #29 marcaba 1 durante todo el cuelgue.

## Pendientes o riesgos detectados
Ninguno.
