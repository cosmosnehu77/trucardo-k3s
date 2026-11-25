import contextlib
import contextvars
import os
import threading

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Proveedor propio en vez de trace.set_tracer_provider: el global se fija
# una sola vez por proceso y haria que los tests dependan del orden.
_proveedor = None

# Pyro5 exige claves de 4 letras y valores bytes en annotations.
CLAVE_TRAZA = "TRCP"


def configurar(servicio, exportador=None):
    global _proveedor
    cerrar()
    if exportador is None and not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    recurso = Resource.create({"service.name": servicio})
    proveedor = TracerProvider(resource=recurso)
    destino = OTLPSpanExporter() if exportador is None else exportador
    proveedor.add_span_processor(BatchSpanProcessor(destino))
    _proveedor = proveedor


def tracer():
    if _proveedor is None:
        return trace.NoOpTracer()
    return _proveedor.get_tracer(__name__)


def cerrar():
    global _proveedor
    if _proveedor is not None:
        proveedor, _proveedor = _proveedor, None
        proveedor.shutdown()


def inyectar(mensaje):
    propagate.inject(mensaje)


def extraer(mensaje):
    return propagate.extract(mensaje)


def anotaciones():
    portador = {}
    inyectar(portador)
    traceparent = portador.get("traceparent")
    return {CLAVE_TRAZA: traceparent.encode()} if traceparent else {}


def de_anotaciones(anotaciones):
    valor = anotaciones.get(CLAVE_TRAZA)
    if not valor:
        return extraer({})
    # Pyro5 entrega un memoryview en el servidor.
    return extraer({"traceparent": bytes(valor).decode()})


def hilo(funcion, *args):
    contexto = contextvars.copy_context()
    return threading.Thread(target=contexto.run, args=(funcion, *args), daemon=True)


@contextlib.contextmanager
def span(nombre, nodo, **atributos):
    with tracer().start_as_current_span(nombre) as actual:
        actual.set_attribute("trucardo.nodo", nodo.id_nodo)
        actual.set_attribute("trucardo.rol", nodo.rol)
        actual.set_attribute("trucardo.epoca", nodo.epoca)
        for clave, valor in atributos.items():
            if valor is not None:
                actual.set_attribute(f"trucardo.{clave}", valor)
        yield actual
