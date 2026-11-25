import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Proveedor propio en vez de trace.set_tracer_provider: el global se fija
# una sola vez por proceso y haria que los tests dependan del orden.
_proveedor = None


def configurar(id_nodo, exportador=None):
    global _proveedor
    cerrar()
    if exportador is None and not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    recurso = Resource.create({"service.name": f"trucardo-nodo{id_nodo}"})
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
