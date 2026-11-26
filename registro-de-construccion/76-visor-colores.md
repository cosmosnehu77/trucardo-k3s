# #76 — Visor en tema claro, con un color por componente y etiquetas en los mensajes

| Campo | Valor |
| --- | --- |
| Issue | #76 |
| Rama | `issue-76-visor-colores` |
| Requisitos | RF-21 |
| Fecha | 25/11/2026 |
| Autor | Nehuén García (con Claude Code) |

## Qué se pidió
Un visor con fondo blanco, un color llamativo para cada componente y para los mensajes, y una etiqueta sobre cada pulso con qué lleva y de quién a quién.

## Qué se hizo
- `visor/estado.py`: cada mensaje sacado de Jaeger trae además `seq` (el atributo `trucardo.seq` del span) y `cantidad` (las ops de una puesta al día).
- `visor/figura/build.mjs`: tema claro fijo. Una tabla `COLORES` con el color y el nombre de cada componente, que sirve para tres cosas: marcar cada pieza (`data-color`), generar el CSS y armar la leyenda del panel. A `GEO` se suman los colores y la posición de los zócalos, para que un pulso salga de un módulo.
- `visor/figura/visor.css`: los tonos de cada pieza salen de su color con `color-mix`. Las placas de los backups usan una versión tenue, y lo caído o no listo pasa a gris. El LED de la máquina queda verde si está lista y rojo si cayó, y la lámpara del primario es amarilla.
- `visor/figura/vivo.js`:
  - un pulso es un punto con el color de quien lo manda y un cartel encima; las elecciones y los coordinadores son anillos;
  - los carteles que se pisan se apilan, hasta tres niveles, y los que sobran se ocultan;
  - las rutas salen de la placa o del módulo, no del conector de la máquina;
  - los mensajes de Jaeger se reproducen con su separación real, y cada réplica sale cuando llega la jugada que la causó;
  - con telemetría, cada 5 s los nodos mandan OTLP al Collector y el Collector reparte trazas, métricas y logs.
- `visor/figura/textos.js`: la ficha de la placa describe el color y la lámpara.

## Por qué así
- **El color es de quien manda.** Con el remitente en el color y el contenido en el cartel, se sigue a cada componente sin una leyenda de tipos de mensaje.
- **Una sola tabla de colores** (DRY): la figura, el CSS, los pulsos y la leyenda salen de `COLORES`.
- **Los envíos OTLP se deducen.** Los nodos no dejan spans de la exportación; se dibujan cada 5 s porque es el intervalo de exportación de las métricas (`_INTERVALO_METRICAS_MS`) y el de las trazas por defecto del SDK.
- **Alternativa descartada:** un color por tipo de mensaje. Con doce componentes y cinco tipos, había que leer dos leyendas.

## Tests
- **Agregado:** `tests/test_visor.py::test_mensajes_dicen_que_op_llevan_y_cuantas_ops_tiene_una_puesta_al_dia`.
- **Modificado:** `test_mensajes_son_los_spans_cuyo_padre_es_de_otro_servicio`, que ahora espera los campos `seq` y `cantidad`.
- **Fallaron antes del cambio:** los mensajes no traían esos campos.

## Verificación
```
$ docker compose run --build --rm tests
...
287 tests, todo ok
```

En el cluster local, con `--telemetria --visor` y dos bots con trazas, se ven los carteles «jugada jugar op 348 · ana→N1», «réplica op 342 · N1→N2» y «OTLP · N2→collector». En `?demo`, al caer `maquina3`, la máquina queda en gris con el LED rojo y la placa de N2 pasa a color pleno. A 390 px de ancho la página no tiene scroll horizontal.

## Pendientes o riesgos detectados
- Con mucho tráfico (bots que juegan varias ops por segundo) se ocultan carteles: el punto se sigue viendo, y el mensaje queda en la lista del panel.
- Las consultas del propio visor (API de Kubernetes, `listar_mesas`, Jaeger) no se dibujan, para no tapar el resto.
