# #6 — Acceso de clientes desde fuera del cluster

| Campo | Valor |
| --- | --- |
| Issue | #6 |
| Rama | `issue-06-acceso-de-clientes-externos` |
| Requisitos | RF-03 |
| Fecha | 24/11/2026 |
| Autor | Nehuén García (con Claude Code y subagentes Gemini en Herdr) |

## Qué se pidió
Que los clientes puedan jugar desde fuera del cluster. Los Services pasan a `NodePort` con la regla de D6 en una sola función, y el generador imprime el `TRUCARDO_NODOS` que tienen que usar los clientes externos.

## Qué se hizo
- **`despliegue/manifiestos.py`:**
  - `puerto_externo(puerto)` es la **única** función que conoce la regla de D6: puerto interno + 21000. Si el resultado cae fuera del rango de NodePort (30000–32767), da `ValueError` con el puerto interno y el rango;
  - los Services son `type: NodePort` y cada puerto lleva su `nodePort`, calculado con `puerto_externo`;
  - `texto_clientes(texto_nodos, ip)`, pura, arma el valor para los clientes: cada nodo apunta a la IP dada y a sus puertos externos;
  - el CLI pide `--imagen` **o** `--clientes IP`, uno de los dos y obligatorio:

    ```bash
    python3 -m despliegue.manifiestos --clientes 192.168.0.11
    ```

  - `_nodos_ordenados` parsea y ordena por id. La usan `manifiestos` y `texto_clientes`, en lugar de repetirlo.
- **`tests/test_manifiestos.py`:** ver *Tests*.
- **`PLAN.md`:** estado de la #6.

## Por qué así
- **Una función para la regla (D6, DRY).** El Service y el valor para clientes calculan el puerto externo con la misma función, así que no pueden desincronizarse.
- **Al cliente le alcanza con su propio `TRUCARDO_NODOS`.** El cliente arma `host:puerto_pyro` desde su lista y sigue al primario por **id** (`cliente/conexion.py`), nunca por una dirección que le pase el nodo. Pyro escucha en `0.0.0.0`. Por eso no hizo falta tocar el cliente ni el nodo: sólo darle la IP de una máquina y los puertos externos.
- **También se expone el puerto del cluster.** Los clientes usan sólo el de Pyro, pero D6 fija la regla para los dos, y `nodo.config.nodos()` exige los dos puertos para que el valor se pueda leer.
- **La IP no se valida en el generador.** La valida `nodos()` cuando el cliente la lee (YAGNI).
- **Cómo se trabajó:**
  - un subagente implementador escribió primero los tests y después el código, con la especificación de arriba;
  - el diff se revisó contra PLAN 1.1 antes de aceptarlo;
  - la prueba de aceptación se hizo aparte (ver *Verificación*).

## Tests
- **Agregados** (`tests/test_manifiestos.py`):
  - `test_los_puertos_externos_siguen_la_regla_y_caen_en_el_rango`: Services `NodePort`, con 30500+i y 30600+i, dentro del rango;
  - `test_el_valor_para_clientes_ida_y_vuelta`: `nodo.config.nodos()` lee el valor para clientes con los mismos ids, la IP dada y los puertos externos;
  - `test_un_puerto_interno_fuera_de_rango_da_error`: 12000 (se pasa) y 8000 (no llega) dan `ValueError`, tanto en los manifiestos como en el valor para clientes;
  - `test_cli_clientes_imprime_el_valor`;
  - `test_cli_pide_imagen_o_clientes`: sin ninguno de los dos, o con los dos, el CLI termina con error.
- **Modificado:** `test_service_usa_host_selector_y_ambos_puertos` pasa a llamarse `test_service_usa_host_y_selector`. Los puertos quedan en el test nuevo, para no verificarlos dos veces.
- **Los tests nuevos fallaron antes del cambio** por la razón esperada:

  ```
  ImportError: cannot import name 'texto_clientes' from 'despliegue.manifiestos'
  ```

## Verificación
```
$ docker compose run --build --rm tests
189 tests, todo ok
```

**Prueba de aceptación, simulada.** Se usó un k3s efímero (`rancher/k3s:v1.37.2-k3s1` en Docker, IP de la máquina 172.17.0.2). Los clientes corrieron en contenedores **fuera** del cluster:

```
$ kubectl get svc
nodo1   NodePort   10.43.44.217   9501:30501/TCP,9601:30601/TCP
nodo2   NodePort   10.43.46.26    9502:30502/TCP,9602:30602/TCP
nodo3   NodePort   10.43.33.174   9503:30503/TCP,9603:30603/TCP

$ python3 -m despliegue.manifiestos --clientes 172.17.0.2
1@172.17.0.2:30501:30601,2@172.17.0.2:30502:30602,3@172.17.0.2:30503:30603
```

- **`quien_es`** con ese valor ve a los tres nodos, con N3 de primario.
- **`cliente.cliente leo`** y **`cliente.cliente beto`**, cada uno en su contenedor, entraron a la misma mesa (`eb50de`) y la partida arrancó:

  ```
  leo:   Estas en la mesa eb50de · Esperando a que se sume el rival...
  beto:  Estas en la mesa eb50de · beto 0 vs 0 leo · a 15 · mano 1 · es mano el rival
  ```

- Las dos operaciones (crear y sumarse) quedaron replicadas en los tres nodos:

  ```
  │ 1    │ 172.17.0.2:30501 │ BACKUP   │ 3 │ 1 │ 2 │
  │ 2    │ 172.17.0.2:30502 │ BACKUP   │ 3 │ 1 │ 2 │
  │ 3    │ 172.17.0.2:30503 │ PRIMARIO │ 3 │ 1 │ 2 │
  ```

  Las columnas son: nodo, dirección, rol, primario, época y `ultimo_seq`.

## Pendientes o riesgos detectados
- **Una sola IP en el valor para clientes.** Si esa máquina se apaga, los clientes pierden el acceso aunque el cluster siga vivo, porque NodePort responde en cualquier máquina pero el cliente conoce una sola. La opción acepta una IP, como pide la issue. Repartir los nodos entre varias IPs se puede evaluar en la #9 o la #10, con máquinas reales.
