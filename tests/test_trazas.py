from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from cliente.cliente import Cliente
from cliente.conexion import Conexion
from nodo import telemetria, transporte
from nodo.lamport import Reloj
from nodo.servidor import NOMBRE_OBJETO
from tests.test_conexion import _nodo_pyro
from tests.test_membresia import _apagar, _cluster
from tests.test_servidor import _id


def _registrar_prueba(membresia):
    def al_prueba(mensaje):
        with telemetria.tracer().start_as_current_span("receptor"):
            return membresia.respuesta()

    membresia._manejadores["PRUEBA"] = al_prueba


def _verificar_hijo(exportador, padre="emisor", hijo="receptor"):
    spans = {span.name: span for span in exportador.get_finished_spans()}
    emisor = spans[padre]
    receptor = spans[hijo]
    assert receptor.context.trace_id == emisor.context.trace_id
    assert receptor.parent is not None
    assert receptor.parent.span_id == emisor.context.span_id


def _envolver_aplicar(servidor):
    aplicar_original = servidor._aplicar

    def aplicar_con_span(op):
        with telemetria.tracer().start_as_current_span("aplicar"):
            return aplicar_original(op)

    servidor._aplicar = aplicar_con_span


def _primario_pyro():
    daemon, nodo = _nodo_pyro(1, primario=1)
    _envolver_aplicar(daemon.objectsById[NOMBRE_OBJETO])
    return daemon, nodo


def test_contexto_se_propaga_entre_nodos():
    exportador = InMemorySpanExporter()
    _, membresias = _cluster()
    try:
        telemetria.configurar("trucardo-nodo1", exportador)
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
        telemetria.configurar("trucardo-nodo1", exportador)
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
        telemetria.configurar("trucardo-nodo1", exportador)
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
        telemetria.configurar("trucardo-nodo1", exportador)
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


def test_anotaciones_transporta_y_reconstruye_el_contexto():
    exportador = InMemorySpanExporter()
    try:
        telemetria.configurar("trucardo-cliente-ana", exportador)
        assert telemetria.anotaciones() == {}
        assert not trace.get_current_span(telemetria.de_anotaciones({})).get_span_context().is_valid

        with telemetria.tracer().start_as_current_span("jugada") as jugada:
            anot = telemetria.anotaciones()
            esperado = jugada.get_span_context()

        assert set(anot) == {"TRCP"}
        assert isinstance(anot["TRCP"], bytes)
        reconstruido = trace.get_current_span(telemetria.de_anotaciones(anot)).get_span_context()
        assert reconstruido.trace_id == esperado.trace_id
        assert reconstruido.span_id == esperado.span_id
    finally:
        telemetria.cerrar()


def test_contexto_se_propaga_del_cliente_al_servidor():
    exportador = InMemorySpanExporter()
    daemon, nodo = _primario_pyro()
    conexion = Conexion({1: nodo}, Reloj())
    try:
        telemetria.configurar("trucardo-nodo1", exportador)
        with telemetria.tracer().start_as_current_span("jugada"):
            creada = conexion.llamar("crear_partida", "ana", _id())

        assert "id_partida" in creada
        telemetria.cerrar()
        _verificar_hijo(exportador, "jugada", "aplicar")
    finally:
        conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()


def test_sin_span_en_el_cliente_el_servidor_no_tiene_padre():
    exportador = InMemorySpanExporter()
    daemon, nodo = _primario_pyro()
    conexion = Conexion({1: nodo}, Reloj())
    try:
        telemetria.configurar("trucardo-nodo1", exportador)
        creada = conexion.llamar("crear_partida", "ana", _id())

        assert "id_partida" in creada
        telemetria.cerrar()
        spans = exportador.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "aplicar"
        assert spans[0].parent is None
    finally:
        conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()


def test_enviar_del_cliente_abre_el_span_raiz_de_la_jugada():
    exportador = InMemorySpanExporter()
    daemon, nodo = _primario_pyro()
    cliente = Cliente({1: nodo})
    try:
        creada = cliente._llamar("crear_partida", "ana", _id())
        unida = cliente._llamar("unirse", creada["id_partida"], "beto", _id())
        vista = cliente._llamar("ver", creada["id_sesion"])
        cliente.id_sesion = creada["id_sesion"] if vista["es_mi_turno"] else unida["id_sesion"]

        telemetria.configurar("trucardo-cliente-ana", exportador)
        cliente._enviar("mazo", None)
        telemetria.cerrar()
        _verificar_hijo(exportador, "jugada mazo", "aplicar")
    finally:
        cliente.conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()
