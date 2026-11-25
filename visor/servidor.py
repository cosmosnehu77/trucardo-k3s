import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from nodo import config
from visor import estado, fuentes

PUERTO = 9808
PERIODO = 1.0
PAGINA = Path(__file__).resolve().parent / "pagina" / "index.html"


class Visor:
    def __init__(self, cluster, jaeger=None, kubernetes=None):
        self.cluster = cluster
        self.jaeger = jaeger
        self.kubernetes = kubernetes or fuentes.Kubernetes()
        self._servicios = [f"trucardo-nodo{id_nodo}" for id_nodo in sorted(cluster)]
        self._lock = threading.Lock()
        self._ultima = None

    def actualizar(self):
        try:
            nodos_k8s, pods_k8s = self.kubernetes.nodos(), self.kubernetes.pods()
            error_k8s = None
        except OSError as error:
            nodos_k8s, pods_k8s, error_k8s = [], [], str(error)
        trazas = fuentes.trazas_jaeger(self.jaeger, self._servicios) if self.jaeger else None
        instantanea = estado.armar(nodos_k8s, pods_k8s, fuentes.respuestas_trucardo(self.cluster),
                                   trazas, time.time())
        instantanea["kubernetes"] = self.kubernetes.disponible and error_k8s is None
        with self._lock:
            self._ultima = json.dumps(instantanea).encode()

    def ultima(self):
        with self._lock:
            return self._ultima

    def seguir(self):
        while True:
            desde = time.monotonic()
            self.actualizar()
            time.sleep(max(0.0, PERIODO - (time.monotonic() - desde)))


def manejador(visor):
    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/estado":
                cuerpo, tipo = visor.ultima() or b"{}", "application/json"
            elif self.path in ("/", "/index.html"):
                cuerpo, tipo = PAGINA.read_bytes(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    return Manejador


def main():
    try:
        cluster = config.nodos()
    except ValueError as error:
        sys.exit(f"TRUCARDO_NODOS invalido: {error}")
    visor = Visor(cluster, jaeger=os.environ.get("VISOR_JAEGER"))
    threading.Thread(target=visor.seguir, daemon=True).start()
    servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO), manejador(visor))
    print(f"visor en http://0.0.0.0:{PUERTO}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
