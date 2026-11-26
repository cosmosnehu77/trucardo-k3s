# #78 — Visor: filtros para mostrar u ocultar cada tipo de mensaje

| Campo | Valor |
| --- | --- |
| Issue | #78 |
| Rama | `issue-78-visor-filtros` |
| Requisitos | RF-21 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Poder prender y apagar latidos, épocas, relojes, jugadas y lo demás, para que en la presentación se vea un tipo de mensaje por vez y no «hormigas».

## Qué se hizo
- `visor/estado.py`: cada mensaje de Jaeger trae también `lamport` (el atributo `trucardo.lamport` del span).
- `visor/figura/build.mjs`: la barra «Mostrar» arriba de la figura, con ocho interruptores: jugadas, réplicas, latidos, épocas y elecciones, telemetría, relojes de Lamport, etiquetas y cámara lenta. Cada uno tiene el color de un componente. Se suma una capa `data-relojes` al dibujo.
- `visor/figura/vivo.js`:
  - cada pulso tiene una categoría, y no se lanza si está apagada. Al apagarla, se borran también los que estaban en viaje;
  - la lista de mensajes del panel respeta los mismos filtros;
  - con «Relojes de Lamport», cada nodo muestra sobre su placa su época y su reloj (`N1 · e6 · L 113411`), y las etiquetas de los mensajes de Jaeger agregan su sello (`L 113314`);
  - «Cámara lenta» hace los viajes 2,5 veces más lentos;
  - la elección se guarda en `localStorage`, y si el navegador no deja guardarla, se usan los valores por defecto.
- `visor/figura/visor.css`: estilos de la barra y de los relojes.

## Por qué así
- **Filtrar en la página, no en el servidor.** `/api/estado` sigue trayendo todo y cada persona elige qué ver sin afectar a otra.
- **Relojes apagados por defecto.** Son útiles para explicar Lamport, pero agregan texto al dibujo.
- **La réplica lleva el mismo sello que su jugada.** El primario sella la op una vez y la réplica la viaja con ese sello, así que se ve igual en las dos etiquetas.

## Tests
- **Modificados:** los dos tests de mensajes de `tests/test_visor.py` esperan el campo `lamport`, y el de atributos verifica que una réplica con `trucardo.lamport=900` lo trae.
- **Fallaron antes del cambio:** los mensajes no traían `lamport`.

## Verificación
```
$ docker compose run --build --rm tests
...
287 tests, todo ok
```

- En `?demo`, con latidos apagados y relojes prendidos, sólo viajan las jugadas y sus réplicas, y cada placa muestra su reloj.
- En el cluster local, `/api/estado` trae la jugada y sus dos réplicas con el mismo sello (`seq 1007`, `lamport 113314`).
- La consola está limpia y la página no tiene scroll horizontal a 390 px.

## Pendientes o riesgos detectados
- En `?demo` los relojes son simulados: los tres avanzan juntos.
