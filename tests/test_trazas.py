from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nodo import telemetria, transporte
from tests.test_membresia import _apagar, _cluster


def _registrar_prueba(membresia):
    def al_prueba(mensaje):
        with telemetria.tracer().start_as_current_span("receptor"):
            return membresia.respuesta()

    membresia._manejadores["PRUEBA"] = al_prueba


def _verificar_hijo(exportador):
    spans = {span.name: span for span in exportador.get_finished_spans()}
    emisor = spans["emisor"]
    receptor = spans["receptor"]
    assert receptor.context.trace_id == emisor.context.trace_id
    assert receptor.parent is not None
    assert receptor.parent.span_id == emisor.context.span_id


def test_contexto_se_propaga_entre_nodos():
    exportador = InMemorySpanExporter()
    _, membresias = _cluster()
    try:
        telemetria.configurar(1, exportador)
        _registrar_prueba(membresias[2])

        with telemetria.tracer().start_as_current_span("emisor"):
            respuesta = transporte.enviar(
                membresias[1].direccion(2),
                membresias[1].mensaje("PRUEBA"),
                timeout=1.0,
            )

        assert respuesta["ok"] is True
        telemetria.cerrar()
        _verificar_hijo(exportador)
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_contexto_se_propaga_entre_nodos_desde_otro_hilo():
    exportador = InMemorySpanExporter()
    _, membresias = _cluster()
    try:
        telemetria.configurar(1, exportador)
        _registrar_prueba(membresias[2])
        respuestas = []

        def enviar():
            respuestas.append(transporte.enviar(
                membresias[1].direccion(2),
                membresias[1].mensaje("PRUEBA"),
                timeout=1.0,
            ))

        with telemetria.tracer().start_as_current_span("emisor"):
            hilo = telemetria.hilo(enviar)
            hilo.start()
            hilo.join(timeout=2.0)

        assert not hilo.is_alive()
        assert len(respuestas) == 1 and respuestas[0]["ok"] is True
        telemetria.cerrar()
        _verificar_hijo(exportador)
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_sin_span_emisor_el_receptor_no_tiene_padre():
    exportador = InMemorySpanExporter()
    _, membresias = _cluster()
    try:
        telemetria.configurar(1, exportador)
        _registrar_prueba(membresias[2])

        respuesta = transporte.enviar(
            membresias[1].direccion(2),
            membresias[1].mensaje("PRUEBA"),
            timeout=1.0,
        )

        assert respuesta["ok"] is True
        telemetria.cerrar()
        spans = exportador.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "receptor"
        assert spans[0].parent is None
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_hilo_propaga_contexto_es_daemon_y_no_arranca_solo():
    exportador = InMemorySpanExporter()
    try:
        telemetria.configurar(1, exportador)
        visto = []

        def correr(valor):
            visto.append((valor, trace.get_current_span().get_span_context()))

        with telemetria.tracer().start_as_current_span("emisor") as emisor:
            hilo = telemetria.hilo(correr, "ok")
            assert hilo.daemon is True
            assert not hilo.is_alive()
            assert visto == []
            hilo.start()
            hilo.join(timeout=2.0)
            esperado = emisor.get_span_context()

        assert not hilo.is_alive()
        assert visto == [("ok", esperado)]
    finally:
        telemetria.cerrar()
