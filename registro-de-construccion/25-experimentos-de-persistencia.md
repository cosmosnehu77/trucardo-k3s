# #25 — Experimentos de persistencia

| Campo | Valor |
| --- | --- |
| Issue | #25 |
| Rama | `issue-25-experimentos-de-persistencia` |
| Requisitos | RF-12, RF-19, RF-20 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Sumar a `experimentos/README.md` cuatro casos, cada uno con su evidencia y la explicación de **por qué** pasó lo que pasó:

1. reiniciar un backup: vuelve con su disco y la puesta al día empieza en su última operación;
2. un nodo que se muda de máquina: arranca con lo que haya en la máquina nueva y se pone al día;
3. el apagón total;
4. el límite: una operación confirmada sin acks se descarta al recortar.

## Qué se hizo
- **`experimentos/README.md`:**
  - la sección «Persistencia», con los casos 8 a 11, en el mismo formato que los de la #10: guion, lo esperado, evidencia y porqué;
  - un comando para ver qué tiene cada máquina en disco;
  - la introducción y el caso 7 apuntan a los casos nuevos.
- **`PLAN.md`:** estado de la #25.

## Por qué así
- **La numeración sigue la de la #10** (casos 8 a 11), así el informe y la demo pueden citar «el caso 9» sin ambigüedad.
- **El caso 9 muestra el log divergente y no la mudanza simple.** La mudanza a una máquina vacía ya aparece en los casos 3 y 4, y la mudanza con un log viejo que coincide, en el caso 5. Faltaba el tercer caso, el que justifica la #23: el log que N2 dejó en `maquina2` durante la partición del caso 7 tenía 14 operaciones que nadie más tenía. Al volver N2 a esa máquina, las recortó y quedaron las 712 que coinciden.
- **El caso 11 usa una partición corta y no `kill -STOP`.** Primero se intentó colgando procesos, que es más simple, pero no se perdió nada: el kernel guarda los mensajes mientras el proceso está detenido y se los entrega al reanudarlo. Se documenta, porque es un error fácil de cometer al preparar la demo. La partición dura menos que el desalojo de Kubernetes, así N2 vuelve como el mismo Pod y el recorte se ve en su propio log.
- **El caso 10 explica por qué el primero en volver se corona solo.** En la corrida salió bien porque el primero fue el primario de antes. Pero el criterio de la elección sólo compara a los que están, y eso es parte del mismo límite que el caso 11.
- **La evidencia es de la misma corrida que la de la #10,** a continuación del caso 7. Así el log divergente del caso 9 es consecuencia real del caso 7.
- **Cómo se trabajó:**
  - los experimentos y el texto los hizo el agente principal;
  - un subagente revisor contrastó la evidencia con las salidas crudas y con el código. Se corrigió lo que encontró:
    - el guion del caso 11 decía que un jugador entrara por cada lado. Así no se reproduce, porque cada uno espera el turno del otro: los dos jugadores de una partida tienen que entrar por la máquina aislada;
    - la explicación del recorte del caso 11 decía que el primario tenía otras ops en esas posiciones. Se recortarían igual sin ellas, porque un backup sólo conserva una cola de la época del primario que le manda;
    - un `quien_es` del caso 8 estaba armado con un número de otra línea y no con la salida real, y faltaba una jugada en el caso 10;
    - el comando para ver los discos consultaba una sola máquina y fallaba si un nodo no tenía archivos todavía.

## Tests
Sin tests nuevos: es documentación (PLAN 1.4). La verificación reproducible es el propio experimento, y la evidencia está en `experimentos/README.md`.

## Verificación
```
$ docker compose run --build --rm tests
210 tests, todo ok
```

## Pendientes o riesgos detectados
- **El primero en volver de un apagón se corona solo** (caso 10). Si es un backup atrasado, los que vuelven después pierden lo que él no tenía. Resolverlo pide quórum, igual que el caso 11. Queda en el informe como límite del modelo primario-backup.
- **El log viejo de un nodo queda en cada máquina por la que pasó.** No molesta, porque la #23 lo corrige al volver, pero ocupa disco. Se borra con `docker compose down -v` en el cluster local, o con `sudo rm -rf /var/lib/trucardo` en las máquinas reales (README).
