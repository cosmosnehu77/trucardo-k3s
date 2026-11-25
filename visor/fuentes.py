import json
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from cliente.conexion import preguntar

_CUENTA = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_API = "https://kubernetes.default.svc"
_TIMEOUT = 2.0
# Las trazas de un mensaje tardan unos segundos en llegar a Jaeger (lote del SDK + Collector).
VENTANA_TRAZAS = 20.0


def _leer_json(url, cabeceras=None, contexto=None):
    pedido = urllib.request.Request(url, headers=cabeceras or {})
    with urllib.request.urlopen(pedido, timeout=_TIMEOUT, context=contexto) as respuesta:
        return json.load(respuesta)


class Kubernetes:
    def __init__(self, cuenta=_CUENTA, api=_API):
        self.disponible = (cuenta / "token").exists()
        if not self.disponible:
            return
        self._api = api
        self._contexto = ssl.create_default_context(cafile=str(cuenta / "ca.crt"))
        self._cuenta = cuenta
        self._namespace = (cuenta / "namespace").read_text().strip()

    def _get(self, ruta):
        # El token se relee en cada pedido porque kubelet lo rota.
        token = (self._cuenta / "token").read_text().strip()
        datos = _leer_json(self._api + ruta, {"Authorization": f"Bearer {token}"}, self._contexto)
        return datos.get("items", [])

    def nodos(self):
        return self._get("/api/v1/nodes") if self.disponible else []

    def pods(self):
        return self._get(f"/api/v1/namespaces/{self._namespace}/pods") if self.disponible else []


def respuestas_trucardo(cluster):
    with ThreadPoolExecutor(max_workers=len(cluster)) as hilos:
        futuros = {id_nodo: hilos.submit(preguntar, nodo, "listar_mesas")
                   for id_nodo, nodo in cluster.items()}
        return {id_nodo: futuro.result() for id_nodo, futuro in futuros.items()}


def _rfc3339(segundos):
    return datetime.fromtimestamp(segundos, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def trazas_jaeger(base, servicios, ahora=None):
    ahora = time.time() if ahora is None else ahora
    resultado = []
    for servicio in servicios:
        consulta = urllib.parse.urlencode({
            "query.service_name": servicio,
            "query.start_time_min": _rfc3339(ahora - VENTANA_TRAZAS),
            "query.start_time_max": _rfc3339(ahora + 1),
            "query.num_traces": 40,
        })
        try:
            resultado.append(_leer_json(f"{base}/api/v3/traces?{consulta}"))
        except (OSError, ValueError):
            resultado.append(None)
    return resultado
