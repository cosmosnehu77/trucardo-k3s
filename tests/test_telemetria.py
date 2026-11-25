from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nodo import telemetria
from tests.test_config import _entorno


def test_sin_endpoint_no_registra_spans():
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar("trucardo-nodo1")
            with telemetria.tracer().start_as_current_span("prueba") as span:
                assert not span.is_recording()
        finally:
            telemetria.cerrar()


def test_con_exportador_en_memoria_registra_el_span_con_service_name():
    exportador = InMemorySpanExporter()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar("trucardo-nodo2", exportador)
            with telemetria.tracer().start_as_current_span("prueba") as span:
                assert span.is_recording()
            telemetria.cerrar()

            spans = exportador.get_finished_spans()
            assert len(spans) == 1
            assert spans[0].name == "prueba"
            assert spans[0].resource.attributes["service.name"] == "trucardo-nodo2"
            assert not telemetria.tracer().start_span("despues").is_recording()
        finally:
            telemetria.cerrar()


def test_con_endpoint_otlp_activa_el_sdk_con_el_nombre_del_nodo():
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:1"):
        try:
            telemetria.configurar("trucardo-nodo3")
            # No se cierra el span para que cerrar() no intente exportar a un endpoint inexistente.
            span = telemetria.tracer().start_span("prueba")
            assert span.is_recording()
            assert span.resource.attributes["service.name"] == "trucardo-nodo3"
        finally:
            telemetria.cerrar()
