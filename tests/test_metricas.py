import time

from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nodo import telemetria
from nodo.config import Nodo
from nodo.servidor import ServidorTruco
from tests.test_config import _entorno
from tests.test_membresia import (
    LATIDO,
    _apagar,
    _cluster,
    _esperar,
    _membresia,
    _primario,
    _puerto_libre,
    _todos_en,
)
from tests.test_servidor import _id
from tests.test_trazas import _esperar_estable


def _punto(lector, nombre, atributos):
    datos = lector.get_metrics_data()
    if datos is None:
        return None
    for recurso in datos.resource_metrics:
        for alcance in recurso.scope_metrics:
            for metrica in alcance.metrics:
                if metrica.name != nombre:
                    continue
                for punto in metrica.data.data_points:
                    if dict(punto.attributes) == atributos:
                        return punto
    return None


def _valor(lector, nombre, atributos):
    punto = _punto(lector, nombre, atributos)
    return None if punto is None else punto.value


def test_una_jugada_replicada_registra_operacion_y_duracion():
    lector = InMemoryMetricReader()
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        telemetria.configurar("prueba", lector=lector)
        assert not telemetria.tracer().start_span("sin-trazas").is_recording()
        _, membresias = _cluster()
        try:
            _esperar_estable(membresias)
            p = _primario(membresias)
            sesion = _id()

            membresias[p].nodo.crear_partida("ana", sesion)
            assert _esperar(lambda: _todos_en(membresias, 1))
            # Un reintento no suma a las metricas de operaciones confirmadas.
            membresias[p].nodo.crear_partida("ana", sesion)

            datos = lector.get_metrics_data()
            assert datos.resource_metrics[0].resource.attributes["service.name"] == "prueba"
            assert _valor(lector, "trucardo.operaciones", {"trucardo.nodo": p, "tipo": "crear"}) == 1
            duracion = _punto(lector, "trucardo.confirmacion.duracion", {"trucardo.nodo": p})
            assert duracion is not None
            assert duracion.count == 1
            assert duracion.sum >= 0
            assert _valor(lector, "trucardo.operaciones.sin_acks", {"trucardo.nodo": p}) is None
            assert _valor(lector, "trucardo.ultimo_seq", {"trucardo.nodo": p}) == 1
        finally:
            telemetria.cerrar()
            _apagar(membresias)


def test_el_rol_y_la_epoca_cambian_tras_una_eleccion():
    lector = InMemoryMetricReader()
    telemetria.configurar("prueba", lector=lector)
    _, membresias = _cluster()
    try:
        _esperar_estable(membresias, 3)
        epoca_inicial = _valor(lector, "trucardo.epoca", {"trucardo.nodo": 2})
        assert _valor(lector, "trucardo.primario", {"trucardo.nodo": 3}) == 1
        assert _valor(lector, "trucardo.primario", {"trucardo.nodo": 2}) == 0
        elecciones_antes = _valor(lector, "trucardo.elecciones", {"trucardo.nodo": 2}) or 0

        membresias[3].detener()
        _esperar_estable({1: membresias[1], 2: membresias[2]}, 2)

        assert _valor(lector, "trucardo.primario", {"trucardo.nodo": 2}) == 1
        assert _valor(lector, "trucardo.primario", {"trucardo.nodo": 1}) == 0
        assert _valor(lector, "trucardo.epoca", {"trucardo.nodo": 2}) > epoca_inicial
        assert _valor(lector, "trucardo.elecciones", {"trucardo.nodo": 2}) > elecciones_antes
        duracion = _punto(
            lector, "trucardo.eleccion.duracion", {"trucardo.nodo": 2, "resultado": "gano"}
        )
        assert duracion is not None
        assert duracion.count >= 1
        assert duracion.sum >= 0
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_el_atraso_de_un_backup_detenido_crece_y_registra_latidos_perdidos():
    lector = InMemoryMetricReader()
    telemetria.configurar("prueba", lector=lector)
    _, membresias = _cluster()
    try:
        _esperar_estable(membresias, 3)
        membresias[1].detener()

        membresias[3].nodo.crear_partida("ana", _id())
        membresias[3].nodo.crear_partida("beto", _id())

        assert _esperar(
            lambda: _todos_en({2: membresias[2], 3: membresias[3]}, 2)
            and membresias[3].vivos.get(2) == 2
            and (_valor(lector, "trucardo.latidos.perdidos", {"trucardo.nodo": 3, "destino": 1}) or 0) > 0
        )

        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 3, "backup": 1}) == 2
        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 3, "backup": 2}) == 0
        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 2, "backup": 1}) is None
        assert _valor(lector, "trucardo.latidos.perdidos", {"trucardo.nodo": 3, "destino": 1}) > 0
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_operacion_confirmada_sin_acks_suma_al_contador():
    lector = InMemoryMetricReader()
    telemetria.configurar("prueba", lector=lector)
    _, membresias = _cluster()
    try:
        _esperar_estable(membresias, 3)
        membresias[1].detener()
        membresias[2].detener()

        membresias[3].nodo.crear_partida("ana", _id())

        assert _valor(lector, "trucardo.operaciones.sin_acks", {"trucardo.nodo": 3}) == 1
        assert _valor(lector, "trucardo.operaciones", {"trucardo.nodo": 3, "tipo": "crear"}) == 1
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_sin_configurar_las_funciones_de_dominio_no_fallan():
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2)}
    membresia = _membresia(cluster, 1)
    with _entorno(OTEL_EXPORTER_OTLP_ENDPOINT=None):
        try:
            telemetria.configurar("prueba")
            telemetria.observar(membresia)
            telemetria.operacion_confirmada(membresia.nodo, "crear", 0.01, acks=0, esperados=2)
            telemetria.eleccion(membresia.nodo, 0.05, "gano")
            telemetria.latido_perdido(membresia.nodo, 2)

            telemetria.configurar("prueba", exportador=InMemorySpanExporter())
            telemetria.observar(membresia)
            telemetria.operacion_confirmada(membresia.nodo, "crear", 0.01, acks=0, esperados=2)
            telemetria.eleccion(membresia.nodo, 0.05, "perdio")
            telemetria.latido_perdido(membresia.nodo, 2)
        finally:
            telemetria.cerrar()


def test_los_histogramas_usan_cubos_en_segundos():
    lector = InMemoryMetricReader()
    nodo = ServidorTruco(id_nodo=1)
    telemetria.configurar("prueba", lector=lector)
    try:
        telemetria.operacion_confirmada(nodo, "crear", 0.02)
        telemetria.eleccion(nodo, 0.02, "gano")

        for nombre, atributos in (
            ("trucardo.confirmacion.duracion", {"trucardo.nodo": 1}),
            ("trucardo.eleccion.duracion", {"trucardo.nodo": 1, "resultado": "gano"}),
        ):
            punto = _punto(lector, nombre, atributos)
            assert punto is not None
            assert sum(punto.bucket_counts) == 1
            indice = punto.bucket_counts.index(1)
            assert indice < len(punto.explicit_bounds)
            assert punto.explicit_bounds[indice] < 0.1
    finally:
        telemetria.cerrar()


def test_tras_una_jugada_replicada_el_atraso_es_cero_sin_esperar_latido():
    lector = InMemoryMetricReader()
    telemetria.configurar("prueba", lector=lector)
    _, membresias = _cluster()
    try:
        _esperar_estable(membresias, 3)
        for m in membresias.values():
            m.timeout = 60.0
        membresias[3].intervalo_latido = 60.0
        # Deja terminar cualquier latido corto en vuelo antes de operar.
        time.sleep(LATIDO * 1.5)

        membresias[3].nodo.crear_partida("ana", _id())

        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 3, "backup": 1}) == 0
        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 3, "backup": 2}) == 0
    finally:
        telemetria.cerrar()
        _apagar(membresias)


def test_primario_recien_coronado_no_informa_atraso_de_backup_desconocido():
    lector = InMemoryMetricReader()
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2, 3)}
    primario = _membresia(cluster, 2)
    telemetria.configurar("prueba", lector=lector)
    try:
        telemetria.observar(primario)
        primario.coronarme(epoca=1, vivos={1: 0})
        primario.nodo.estado.aplicar({
            "seq": 1, "epoca": 1, "lamport": 1, "tipo": "crear",
            "id_sesion": "s1", "id_operacion": "s1",
            "datos": {"nombre": "ana", "id_mesa": "m1", "semilla": 1, "puntos": 15},
        })

        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 2, "backup": 3}) is None
        assert _valor(lector, "trucardo.backup.atraso", {"trucardo.nodo": 2, "backup": 1}) == 1
    finally:
        telemetria.cerrar()
