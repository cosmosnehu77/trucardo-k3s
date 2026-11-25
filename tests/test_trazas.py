import time

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from cliente.cliente import Cliente
from cliente.conexion import Conexion
from nodo import telemetria, transporte
from nodo.cluster.protocolo import ILEGAL, REPLICA
from nodo.config import Nodo
from nodo.lamport import Reloj
from tests.test_conexion import _nodo_pyro
from tests.test_membresia import (
    LATIDO,
    _apagar,
    _armado,
    _arrancar,
    _cluster,
    _esperar,
    _membresia,
    _primario,
    _puerto_libre,
    _todos_en,
)
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


def _esperar_estable(membresias, primario=None):
    assert _esperar(
        lambda: _armado(membresias, primario)
        and all(not m.eleccion.convocando for m in membresias.values())
    )


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
        spans = [s for s in exportador.get_finished_spans() if s.name == "receptor"]
        assert len(spans) == 1
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
    daemon, nodo = _nodo_pyro(1, primario=1)
    conexion = Conexion({1: nodo}, Reloj())
    try:
        telemetria.configurar("trucardo-nodo1", exportador)
        with telemetria.tracer().start_as_current_span("jugada"):
            creada = conexion.llamar("crear_partida", "ana", _id())

        assert "id_partida" in creada
        telemetria.cerrar()
        _verificar_hijo(exportador, "jugada", "jugada crear")
    finally:
        conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()


def test_sin_span_en_el_cliente_el_servidor_no_tiene_padre():
    exportador = InMemorySpanExporter()
    daemon, nodo = _nodo_pyro(1, primario=1)
    conexion = Conexion({1: nodo}, Reloj())
    try:
        telemetria.configurar("trucardo-nodo1", exportador)
        creada = conexion.llamar("crear_partida", "ana", _id())

        assert "id_partida" in creada
        telemetria.cerrar()
        spans = [s for s in exportador.get_finished_spans() if s.name == "jugada crear"]
        assert len(spans) == 1
        assert spans[0].parent is None
    finally:
        conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()


def test_enviar_del_cliente_abre_el_span_raiz_de_la_jugada():
    exportador = InMemorySpanExporter()
    daemon, nodo = _nodo_pyro(1, primario=1)
    cliente = Cliente({1: nodo})
    try:
        creada = cliente._llamar("crear_partida", "ana", _id())
        unida = cliente._llamar("unirse", creada["id_partida"], "beto", _id())
        vista = cliente._llamar("ver", creada["id_sesion"])
        cliente.id_sesion = creada["id_sesion"] if vista["es_mi_turno"] else unida["id_sesion"]

        telemetria.configurar("trucardo-cliente-ana", exportador)
        cliente._enviar("mazo", None)
        telemetria.cerrar()
        spans = [s for s in exportador.get_finished_spans() if s.name == "jugada mazo"]
        del_cliente = [s for s in spans if "trucardo.nodo" not in s.attributes]
        del_servidor = [s for s in spans if s.attributes.get("trucardo.nodo") == 1]
        assert len(del_cliente) == 1
        assert len(del_servidor) == 1
        assert del_cliente[0].parent is None
        assert del_servidor[0].context.trace_id == del_cliente[0].context.trace_id
        assert del_servidor[0].parent is not None
        assert del_servidor[0].parent.span_id == del_cliente[0].context.span_id
    finally:
        cliente.conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()


def test_una_jugada_replicada_genera_span_en_primario_y_en_cada_backup():
    exportador = InMemorySpanExporter()
    cluster, membresias = _cluster()
    try:
        _esperar_estable(membresias)
        p = _primario(membresias)

        telemetria.configurar("prueba", exportador)
        membresias[p].nodo.crear_partida("ana", _id())
        assert _esperar(lambda: _todos_en(membresias, 1))
        telemetria.cerrar()

        spans = exportador.get_finished_spans()
        jugadas = [s for s in spans if s.name == "jugada crear"]
        assert len(jugadas) == 1
        jugada = jugadas[0]
        assert jugada.attributes["trucardo.nodo"] == p
        assert jugada.attributes["trucardo.rol"] == "primario"
        assert jugada.attributes["trucardo.epoca"] == membresias[p].nodo.epoca
        assert jugada.attributes["trucardo.seq"] == 1
        assert jugada.attributes["trucardo.lamport"] > 0

        replicas = [s for s in spans if s.name == "replica"]
        assert len(replicas) == 2
        for replica in replicas:
            assert replica.context.trace_id == jugada.context.trace_id
            assert replica.parent is not None
            assert replica.parent.span_id == jugada.context.span_id
            assert replica.attributes["trucardo.seq"] == jugada.attributes["trucardo.seq"]
            assert replica.attributes["trucardo.lamport"] == jugada.attributes["trucardo.lamport"]
            assert replica.attributes["trucardo.epoca"] == jugada.attributes["trucardo.epoca"]
            assert replica.attributes["trucardo.rol"] == "backup"
            assert "trucardo.motivo" not in replica.attributes
        assert {r.attributes["trucardo.nodo"] for r in replicas} == set(cluster) - {p}
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_un_reintento_marca_reintento_y_no_lleva_seq():
    exportador = InMemorySpanExporter()
    daemon, nodo = _nodo_pyro(1, primario=1)
    conexion = Conexion({1: nodo}, Reloj())
    try:
        sesion = _id()
        conexion.llamar("crear_partida", "ana", sesion)

        telemetria.configurar("prueba", exportador)
        conexion.llamar("crear_partida", "ana", sesion)
        telemetria.cerrar()

        jugadas = [s for s in exportador.get_finished_spans() if s.name == "jugada crear"]
        assert len(jugadas) == 1
        assert jugadas[0].attributes.get("trucardo.reintento") is True
        assert "trucardo.seq" not in jugadas[0].attributes
    finally:
        conexion._soltar()
        telemetria.cerrar()
        daemon.shutdown()


def test_una_eleccion_produce_eleccion_desafios_y_coordinador():
    exportador = InMemorySpanExporter()
    telemetria.configurar("prueba", exportador)
    cluster, membresias = _cluster()
    try:
        _esperar_estable(membresias)
        p = _primario(membresias)
        telemetria.cerrar()

        spans = exportador.get_finished_spans()
        elecciones = [s for s in spans if s.name == "eleccion"]
        ganadoras = [
            s for s in elecciones
            if s.attributes.get("trucardo.resultado") == "gano"
            and s.attributes.get("trucardo.nodo") == p
        ]
        assert len(ganadoras) >= 1
        ganadora = ganadoras[-1]
        assert "trucardo.ultimo_seq" in ganadora.attributes
        assert "trucardo.epoca_ultima" in ganadora.attributes

        elecciones_por_id = {s.context.span_id: s for s in elecciones}
        desafios = [s for s in spans if s.name == "desafio"]
        assert len(desafios) >= 2
        for desafio in desafios:
            assert desafio.parent is not None
            assert desafio.parent.span_id in elecciones_por_id
            padre = elecciones_por_id[desafio.parent.span_id]
            assert desafio.context.trace_id == padre.context.trace_id
            assert "trucardo.candidato" in desafio.attributes
            assert isinstance(desafio.attributes.get("trucardo.le_gano"), bool)

        coordinadores = [
            s for s in spans
            if s.name == "coordinador"
            and s.parent is not None
            and s.parent.span_id == ganadora.context.span_id
        ]
        assert len(coordinadores) == 1
        coord = coordinadores[0]
        assert coord.context.trace_id == ganadora.context.trace_id
        assert coord.attributes["trucardo.nodo"] == p
        assert coord.attributes["trucardo.rol"] == "primario"

        recibidos = [
            s for s in spans
            if s.name == "coordinador recibido"
            and s.parent is not None
            and s.parent.span_id == coord.context.span_id
        ]
        assert len(recibidos) == 2
        for recibido in recibidos:
            assert recibido.context.trace_id == coord.context.trace_id
            assert recibido.attributes["trucardo.primario"] == p
            assert recibido.attributes["trucardo.aceptado"] is True
        assert {r.attributes["trucardo.nodo"] for r in recibidos} == set(cluster) - {p}
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_una_puesta_al_dia_genera_span_en_primario_y_en_backup():
    exportador = InMemorySpanExporter()
    cluster, membresias = _cluster()
    try:
        _esperar_estable(membresias, 3)
        membresias[1].detener()
        membresias[3].nodo.crear_partida("ana", _id())
        assert _esperar(
            lambda: _todos_en({2: membresias[2], 3: membresias[3]}, 1)
            and membresias[3].vivos.get(2) == 1
            and not membresias[3].replica._poniendo_al_dia
        )

        telemetria.configurar("prueba", exportador)
        membresias[1] = _arrancar(cluster, 1)
        assert _esperar(
            lambda: _todos_en(membresias, 1)
            and not membresias[3].replica._poniendo_al_dia
        )
        telemetria.cerrar()

        spans = exportador.get_finished_spans()
        enviadas = [s for s in spans if s.name == "puesta al dia"]
        assert len(enviadas) >= 1
        enviada = enviadas[0]
        assert enviada.attributes["trucardo.nodo"] == 3
        assert enviada.attributes["trucardo.rol"] == "primario"
        assert enviada.attributes["trucardo.destino"] == 1
        assert enviada.attributes["trucardo.desde"] == 0
        assert enviada.attributes["trucardo.cantidad"] == 1

        recibidas = [
            s for s in spans
            if s.name == "puesta al dia recibida"
            and s.parent is not None
            and s.parent.span_id == enviada.context.span_id
        ]
        assert len(recibidas) == 1
        recibida = recibidas[0]
        assert recibida.context.trace_id == enviada.context.trace_id
        assert recibida.attributes["trucardo.nodo"] == 1
        assert recibida.attributes["trucardo.rol"] == "backup"
        assert recibida.attributes["trucardo.desde"] == 0
        assert recibida.attributes["trucardo.cantidad"] == 1
        assert "trucardo.motivo" not in recibida.attributes
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_los_latidos_normales_no_producen_spans():
    exportador = InMemorySpanExporter()
    _, membresias = _cluster()
    try:
        _esperar_estable(membresias)
        time.sleep(LATIDO)

        telemetria.configurar("prueba", exportador)
        time.sleep(5 * LATIDO)
        telemetria.cerrar()

        assert exportador.get_finished_spans() == ()
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_un_latido_rechazado_produce_span_con_epoca_nueva():
    exportador = InMemorySpanExporter()
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (2, 3)}
    membresias = {2: _arrancar(cluster, 2), 3: _membresia(cluster, 3)}
    try:
        assert _esperar(lambda: membresias[2].nodo.rol == "primario")
        with membresias[2].nodo.lock:
            membresias[2].nodo.epoca = 9
        membresias[3].coronarme(epoca=1, vivos={2: 0})

        telemetria.configurar("prueba", exportador)
        membresias[3].latido.latir_a(2, 0)
        telemetria.cerrar()

        rechazados = [s for s in exportador.get_finished_spans() if s.name == "latido rechazado"]
        assert len(rechazados) == 1
        span = rechazados[0]
        assert span.attributes["trucardo.nodo"] == 3
        assert span.attributes["trucardo.rol"] == "primario"
        assert span.attributes["trucardo.destino"] == 2
        assert span.attributes["trucardo.epoca_nueva"] == 9
        assert span.attributes["trucardo.epoca"] == 1
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_replica_con_op_invalida_no_falla_y_registra_motivo():
    exportador = InMemorySpanExporter()
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2)}
    backup = _membresia(cluster, 1)
    primario = _membresia(cluster, 2)
    try:
        telemetria.configurar("prueba", exportador)
        respuesta = backup.replica._a_las_replicas(primario.mensaje(REPLICA, op="basura"))
        telemetria.cerrar()

        assert respuesta["motivo"] == ILEGAL
        replicas = [s for s in exportador.get_finished_spans() if s.name == "replica"]
        assert len(replicas) == 1
        assert replicas[0].attributes["trucardo.motivo"] == ILEGAL
        assert "trucardo.seq" not in replicas[0].attributes
        assert "trucardo.lamport" not in replicas[0].attributes
    finally:
        telemetria.cerrar()
