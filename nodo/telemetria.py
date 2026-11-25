import contextlib
import contextvars
import logging
import os
import threading

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_INTERVALO_METRICAS_MS = 5000
# Cubos en segundos: los por defecto del SDK estan pensados para milisegundos.
_CUBOS_SEGUNDOS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

# Proveedor propio en vez de trace.set_tracer_provider: el global se fija
# una sola vez por proceso y haria que los tests dependan del orden.
_proveedor = None
_proveedor_metricas = None
_instrumentos = None
_proveedor_logs = None
_manejador_logs = None
_membresias = []

# Pyro5 exige claves de 4 letras y valores bytes en annotations.
CLAVE_TRAZA = "TRCP"


def _observar_nodos(extractor):
    def callback(_opciones):
        observaciones = []
        for membresia in list(_membresias):
            with membresia.nodo.lock:
                if membresia.detenido.is_set():
                    continue
                valor = extractor(membresia.nodo)
                id_nodo = membresia.nodo.id_nodo
            observaciones.append(Observation(valor, {"trucardo.nodo": id_nodo}))
        return observaciones

    return callback


def _observar_atraso(_opciones):
    observaciones = []
    for membresia in list(_membresias):
        with membresia.nodo.lock:
            if membresia.detenido.is_set() or membresia.nodo.rol != "primario":
                continue
            id_nodo = membresia.nodo.id_nodo
            ultimo_seq = membresia.nodo.estado.ultimo_seq
            visto = dict(membresia.visto)
            otros = [otro for otro in membresia.cluster if otro != id_nodo]
        for otro in otros:
            atraso = max(0, ultimo_seq - visto.get(otro, 0))
            observaciones.append(
                Observation(atraso, {"trucardo.nodo": id_nodo, "backup": otro})
            )
    return observaciones


def _crear_instrumentos(meter):
    meter.create_observable_gauge("trucardo.epoca", callbacks=[_observar_nodos(lambda n: n.epoca)])
    meter.create_observable_gauge(
        "trucardo.primario",
        callbacks=[_observar_nodos(lambda n: 1 if n.rol == "primario" else 0)],
    )
    meter.create_observable_gauge(
        "trucardo.ultimo_seq", callbacks=[_observar_nodos(lambda n: n.estado.ultimo_seq)]
    )
    meter.create_observable_gauge("trucardo.backup.atraso", callbacks=[_observar_atraso])
    return {
        "operaciones": meter.create_counter("trucardo.operaciones"),
        "confirmacion_duracion": meter.create_histogram(
            "trucardo.confirmacion.duracion",
            unit="s",
            explicit_bucket_boundaries_advisory=_CUBOS_SEGUNDOS,
        ),
        "sin_acks": meter.create_counter("trucardo.operaciones.sin_acks"),
        "elecciones": meter.create_counter("trucardo.elecciones"),
        "eleccion_duracion": meter.create_histogram(
            "trucardo.eleccion.duracion",
            unit="s",
            explicit_bucket_boundaries_advisory=_CUBOS_SEGUNDOS,
        ),
        "latidos_perdidos": meter.create_counter("trucardo.latidos.perdidos"),
    }


def configurar(servicio, exportador=None, lector=None, exportador_logs=None):
    global _proveedor, _proveedor_metricas, _instrumentos, _proveedor_logs, _manejador_logs
    cerrar()
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if exportador is None and lector is None and exportador_logs is None and not endpoint:
        return
    recurso = Resource.create({"service.name": servicio})
    if exportador is not None or endpoint:
        proveedor = TracerProvider(resource=recurso)
        destino = OTLPSpanExporter() if exportador is None else exportador
        proveedor.add_span_processor(BatchSpanProcessor(destino))
        _proveedor = proveedor
    if lector is not None or endpoint:
        origen = (
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
                export_interval_millis=_INTERVALO_METRICAS_MS,
            )
            if lector is None
            else lector
        )
        _proveedor_metricas = MeterProvider(resource=recurso, metric_readers=[origen])
        _instrumentos = _crear_instrumentos(_proveedor_metricas.get_meter(__name__))
    if exportador_logs is not None or endpoint:
        proveedor_logs = LoggerProvider(resource=recurso)
        procesador = (
            BatchLogRecordProcessor(OTLPLogExporter())
            if exportador_logs is None
            else SimpleLogRecordProcessor(exportador_logs)
        )
        proveedor_logs.add_log_record_processor(procesador)
        _proveedor_logs = proveedor_logs
        _manejador_logs = LoggingHandler(logger_provider=proveedor_logs)


def tracer():
    if _proveedor is None:
        return trace.NoOpTracer()
    return _proveedor.get_tracer(__name__)


def manejador_de_logs():
    return _manejador_logs


def cerrar():
    global _proveedor, _proveedor_metricas, _instrumentos, _proveedor_logs, _manejador_logs
    if _proveedor is not None:
        proveedor, _proveedor = _proveedor, None
        proveedor.shutdown()
    if _proveedor_metricas is not None:
        proveedor, _proveedor_metricas, _instrumentos = _proveedor_metricas, None, None
        proveedor.shutdown()
    if _manejador_logs is not None:
        manejador, _manejador_logs = _manejador_logs, None
        logging.getLogger("trucardo").removeHandler(manejador)
    if _proveedor_logs is not None:
        proveedor, _proveedor_logs = _proveedor_logs, None
        proveedor.shutdown()
    _membresias.clear()


def observar(membresia):
    if _proveedor_metricas is None:
        return
    _membresias.append(membresia)


def operacion_confirmada(nodo, tipo, segundos, acks=None, esperados=None):
    instrumentos = _instrumentos
    if instrumentos is None:
        return
    base = {"trucardo.nodo": nodo.id_nodo}
    instrumentos["operaciones"].add(1, {**base, "tipo": tipo})
    instrumentos["confirmacion_duracion"].record(segundos, base)
    if acks is not None and acks < esperados:
        instrumentos["sin_acks"].add(1, base)


def eleccion(nodo, segundos, resultado):
    instrumentos = _instrumentos
    if instrumentos is None:
        return
    base = {"trucardo.nodo": nodo.id_nodo}
    instrumentos["elecciones"].add(1, base)
    instrumentos["eleccion_duracion"].record(segundos, {**base, "resultado": resultado})


def latido_perdido(nodo, destino):
    instrumentos = _instrumentos
    if instrumentos is None:
        return
    instrumentos["latidos_perdidos"].add(
        1, {"trucardo.nodo": nodo.id_nodo, "destino": destino}
    )


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
