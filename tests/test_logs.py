import io
import logging
from types import SimpleNamespace

from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nodo import registro, telemetria
from nodo.lamport import Reloj
from tests.test_config import _entorno


def _nodo():
    return SimpleNamespace(id_nodo=2, rol="backup", epoca=1, reloj=Reloj())


def _limpiar_registro():
    registro.log.handlers.clear()
    registro.log.setLevel(logging.NOTSET)
    registro.log.propagate = True


def test_log_dentro_de_un_span_lleva_su_trace_id_y_span_id():
    exportador_logs = InMemoryLogRecordExporter()
    nodo = _nodo()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar(
                "prueba",
                exportador=InMemorySpanExporter(),
                exportador_logs=exportador_logs,
            )
            registro.configurar(nodo, destino=io.StringIO(), nivel="INFO")
            with telemetria.tracer().start_as_current_span("jugada") as span:
                contexto = span.get_span_context()
                registro.log.info("hola")

            logs = exportador_logs.get_finished_logs()
            assert len(logs) == 1
            record = logs[0].log_record
            assert record.trace_id == contexto.trace_id
            assert record.span_id == contexto.span_id
            assert record.trace_id != 0
            assert record.span_id != 0
            assert record.body == "hola"
            assert logs[0].resource.attributes["service.name"] == "prueba"
        finally:
            telemetria.cerrar()
            _limpiar_registro()


def test_log_exportado_lleva_atributos_del_estado_del_nodo_en_ese_momento():
    exportador_logs = InMemoryLogRecordExporter()
    nodo = _nodo()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar(
                "prueba",
                exportador=InMemorySpanExporter(),
                exportador_logs=exportador_logs,
            )
            registro.configurar(nodo, destino=io.StringIO(), nivel="INFO")
            registro.log.info("primero")
            nodo.rol, nodo.epoca = "primario", 3
            nodo.reloj.tic()
            registro.log.info("segundo")

            logs = exportador_logs.get_finished_logs()
            assert len(logs) == 2
            primero = logs[0].log_record.attributes
            segundo = logs[1].log_record.attributes
            assert primero["trucardo.nodo"] == 2
            assert primero["trucardo.rol"] == "backup"
            assert primero["trucardo.epoca"] == 1
            assert primero["trucardo.lamport"] == 0
            assert segundo["trucardo.nodo"] == 2
            assert segundo["trucardo.rol"] == "primario"
            assert segundo["trucardo.epoca"] == 3
            assert segundo["trucardo.lamport"] == 1
        finally:
            telemetria.cerrar()
            _limpiar_registro()


def test_la_linea_de_consola_es_identica_con_y_sin_telemetria():
    nodo = _nodo()
    sin_otel = io.StringIO()
    con_otel = io.StringIO()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar("prueba")
            registro.configurar(nodo, destino=sin_otel, nivel="INFO")
            registro.log.info("operacion confirmada")

            telemetria.configurar(
                "prueba",
                exportador=InMemorySpanExporter(),
                exportador_logs=InMemoryLogRecordExporter(),
            )
            registro.configurar(nodo, destino=con_otel, nivel="INFO")
            registro.log.info("operacion confirmada")
        finally:
            telemetria.cerrar()
            _limpiar_registro()

    linea_sin = sin_otel.getvalue().strip().split(" ", 1)[1]
    linea_con = con_otel.getvalue().strip().split(" ", 1)[1]
    assert linea_con == linea_sin
    assert linea_con == "[N2│BACKUP│e=1│L=0] operacion confirmada"


def test_sin_destino_otlp_no_configura_manejador_de_logs():
    nodo = _nodo()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar("prueba")
            assert telemetria.manejador_de_logs() is None
            registro.configurar(nodo, destino=io.StringIO(), nivel="INFO")
            assert len(registro.log.handlers) == 1

            telemetria.configurar("prueba", exportador=InMemorySpanExporter())
            assert telemetria.manejador_de_logs() is None
            registro.configurar(nodo, destino=io.StringIO(), nivel="INFO")
            assert len(registro.log.handlers) == 1
        finally:
            telemetria.cerrar()
            _limpiar_registro()


def test_cerrar_saca_el_manejador_de_opentelemetry_del_logger():
    exportador_logs = InMemoryLogRecordExporter()
    nodo = _nodo()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar(
                "prueba",
                exportador=InMemorySpanExporter(),
                exportador_logs=exportador_logs,
            )
            manejador = telemetria.manejador_de_logs()
            assert manejador is not None
            registro.configurar(nodo, destino=io.StringIO(), nivel="INFO")
            assert manejador in registro.log.handlers
            assert len(registro.log.handlers) == 2

            telemetria.cerrar()
            assert telemetria.manejador_de_logs() is None
            assert manejador not in registro.log.handlers
            assert len(registro.log.handlers) == 1
        finally:
            telemetria.cerrar()
            _limpiar_registro()
