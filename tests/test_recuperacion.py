import contextlib
import logging
import tempfile

from nodo import disco, transporte
from nodo.cluster.protocolo import ATRASADO, DUPLICADA, ELECCION
from nodo.config import Nodo
from nodo.errores import NoPrimario
from nodo.registro import log
from nodo.servidor import ServidorTruco
from tests.test_membresia import (
    _Contar,
    _apagar,
    _armado,
    _arrancar,
    _esperar,
    _membresia,
    _primario,
    _puerto_libre,
    _todos_en,
)


def _op_crear(seq, epoca, id_mesa, id_sesion):
    return {
        "seq": seq,
        "epoca": epoca,
        "lamport": seq,
        "tipo": "crear",
        "id_sesion": id_sesion,
        "id_operacion": id_sesion,
        "datos": {"nombre": "ana", "id_mesa": id_mesa, "semilla": seq, "puntos": 15},
    }


def _cluster_con_disco(pila):
    directorios = {i: pila.enter_context(tempfile.TemporaryDirectory()) for i in (1, 2, 3)}
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2, 3)}
    membresias = {i: _arrancar(cluster, i, disco=disco.Disco(directorios[i])) for i in cluster}
    return cluster, directorios, membresias


def test_un_backup_que_vuelve_con_su_disco_recibe_solo_lo_que_le_falta():
    with contextlib.ExitStack() as pila:
        cluster, directorios, membresias = _cluster_con_disco(pila)
        desde_2 = _Contar("puesta al dia: de la op 2 a la 4")
        desde_0 = _Contar("puesta al dia: de la op 0 a la")
        recorte = _Contar("recorto el log")
        nivel = log.level
        try:
            assert _esperar(lambda: _armado(membresias))
            p = _primario(membresias)
            membresias[p].nodo.crear_partida("ana", "s1")
            membresias[p].nodo.crear_partida("beto", "s2")
            assert _esperar(lambda: _todos_en(membresias, 2))

            backup = 1 if p != 1 else 2
            membresias[backup].detener()

            membresias[p].nodo.crear_partida("caro", "s3")
            membresias[p].nodo.crear_partida("diego", "s4")
            otros = {i: m for i, m in membresias.items() if i != backup}
            assert _esperar(lambda: _todos_en(otros, 4))

            log.setLevel(logging.INFO)
            for handler in (desde_2, desde_0, recorte):
                log.addHandler(handler)

            membresias[backup] = _arrancar(cluster, backup, disco=disco.Disco(directorios[backup]))
            assert _esperar(lambda: _todos_en(membresias, 4) and (desde_2.n + desde_0.n) >= 1), \
                "el backup tiene que ponerse al dia hasta la op 4"
            assert desde_2.n >= 1, "la puesta al dia tiene que arrancar desde la op 2"
            assert desde_0.n == 0, "no tiene que reenviar el log desde la op 0"
            assert recorte.n == 0, "no tiene que recortar un prefijo que coincide"
        finally:
            for handler in (desde_2, desde_0, recorte):
                log.removeHandler(handler)
            log.setLevel(nivel)
            _apagar(membresias)


def test_un_backup_con_una_cola_divergente_la_recorta():
    with contextlib.ExitStack() as pila:
        cluster, directorios, membresias = _cluster_con_disco(pila)
        try:
            assert _esperar(lambda: _armado(membresias, 3))
            membresias[3].detener()

            vivos = {1: membresias[1], 2: membresias[2]}
            assert _esperar(lambda: _armado(vivos, 2)), \
                "sin N3, N1 y N2 tienen que elegir a N2 como primario"

            zombie = membresias[3].nodo
            try:
                zombie.crear_partida("ana", "s-zombie")
            except NoPrimario:
                pass
            else:
                assert False, "un zombie no le puede confirmar la op al cliente"
            assert len(disco.Disco(directorios[3]).operaciones()) == 1, \
                "la op no confirmada tiene que haber quedado en el disco de N3"

            membresias[2].nodo.crear_partida("beto", "s-real")
            assert _esperar(lambda: _todos_en(vivos, 1))

            membresias[3] = _arrancar(cluster, 3, disco=disco.Disco(directorios[3]))
            assert _esperar(
                lambda: _armado(membresias)
                and all(m.nodo.estado.log == membresias[_primario(membresias)].nodo.estado.log
                        for m in membresias.values())
            ), "los tres nodos tienen que converger al mismo log"

            log_primario = membresias[_primario(membresias)].nodo.estado.log
            assert len(log_primario) == 1
            assert log_primario[0]["id_sesion"] == "s-real"
            with membresias[3].nodo.lock:
                en_disco = disco.Disco(directorios[3]).operaciones()
            assert en_disco == log_primario, \
                "el disco de N3 tiene que haber recortado la op divergente"
        finally:
            _apagar(membresias)


def test_un_log_mas_corto_de_epoca_mayor_gana_la_eleccion():
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2)}
    membresias = {i: _membresia(cluster, i) for i in cluster}
    for membresia in membresias.values():
        membresia.eleccion.convocar_aparte = lambda: None

    membresias[1].nodo.estado.aplicar(_op_crear(1, 1, "m1", "s1"))
    membresias[1].nodo.estado.aplicar(_op_crear(2, 1, "m2", "s2"))
    membresias[2].nodo.estado.aplicar(_op_crear(1, 2, "m3", "s3"))

    pedido_1 = membresias[1].mensaje(
        ELECCION,
        ultimo_seq=membresias[1].nodo.estado.ultimo_seq,
        epoca_ultima=membresias[1].nodo.estado.epoca_ultima,
    )
    pedido_2 = membresias[2].mensaje(
        ELECCION,
        ultimo_seq=membresias[2].nodo.estado.ultimo_seq,
        epoca_ultima=membresias[2].nodo.estado.epoca_ultima,
    )

    respuesta_de_2 = membresias[2].eleccion._al_eleccion(pedido_1)
    respuesta_de_1 = membresias[1].eleccion._al_eleccion(pedido_2)

    assert respuesta_de_2["mando_yo"] is True, \
        "un log mas corto de epoca mayor le tiene que ganar"
    assert respuesta_de_1["mando_yo"] is False, \
        "el de epoca_ultima menor no puede contestar mando_yo"


def test_tras_apagar_los_tres_las_mesas_siguen():
    with contextlib.ExitStack() as pila:
        cluster, directorios, membresias = _cluster_con_disco(pila)
        try:
            assert _esperar(lambda: _armado(membresias))
            p = _primario(membresias)
            entrada = membresias[p].nodo.crear_partida("ana", "s1")
            id_mesa = entrada["id_partida"]
            membresias[p].nodo.unirse(id_mesa, "beto", "s2")
            assert _esperar(lambda: _todos_en(membresias, 2))

            _apagar(membresias)
            membresias = {i: _arrancar(cluster, i, disco=disco.Disco(directorios[i]))
                          for i in cluster}

            assert _esperar(lambda: _armado(membresias) and _todos_en(membresias, 2)), \
                "los tres tienen que volver con sus dos ops y elegir primario"
            assert all(id_mesa in m.nodo.estado.mesas for m in membresias.values())

            primario = membresias[_primario(membresias)].nodo
            vista_1 = primario.ver("s1")
            vista_2 = primario.ver("s2")
            activo, vista = ("s1", vista_1) if vista_1["es_mi_turno"] else ("s2", vista_2)
            primario.jugar_carta(activo, vista["mis_cartas"][0], "op-3")

            assert _esperar(lambda: _todos_en(membresias, 3)), \
                "la jugada tras el apagon tiene que replicarse a todos"
        finally:
            _apagar(membresias)


def test_una_replica_distinta_a_la_mia_no_cuenta_como_ack():
    backup = ServidorTruco(id_nodo=2, puntos=15, primario=1)
    op_x = _op_crear(1, 1, "m1", "s1")
    op_y = _op_crear(1, 2, "m2", "s2")
    op_2 = _op_crear(2, 2, "m3", "s3")

    assert backup._atiendo_replica(op_x, previa=0) is None
    assert backup._atiendo_replica(op_y, previa=0) == ATRASADO
    assert backup._atiendo_replica(op_x, previa=0) == DUPLICADA
    assert backup._atiendo_replica(op_2, previa=2) == ATRASADO
    assert backup.estado.log == [op_x]


def test_una_puesta_al_dia_vieja_no_recorta_lo_ya_confirmado():
    """Una puesta al dia calculada antes de una REPLICA puede llegar despues:
    lo que coincide no se recorta."""
    backup = ServidorTruco(id_nodo=2, puntos=15, primario=1)
    ops = [_op_crear(seq, 1, f"m{seq}", f"s{seq}") for seq in (1, 2, 3)]
    for op in ops:
        assert backup._atiendo_replica(op) is None

    assert backup._atiendo_puesta_al_dia(ops[1:2], 1, 1) is None
    assert backup.estado.log == ops


def test_una_cola_de_otra_epoca_que_el_primario_no_tiene_se_recorta():
    backup = ServidorTruco(id_nodo=2, puntos=15, primario=1)
    ops = [_op_crear(seq, 1, f"m{seq}", f"s{seq}") for seq in (1, 2)]
    for op in ops:
        assert backup._atiendo_replica(op) is None

    assert backup._atiendo_puesta_al_dia(ops[:1], 0, 2) is None
    assert backup.estado.log == ops[:1]


def _dos_primarios_de_la_misma_epoca():
    """N1 y N2 se coronaron los dos en la epoca 5, aislados: la op 2 de cada uno
    es distinta. La op 3 del primario crea la mesa que el backup ya tiene."""
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2)}
    primario, backup = _membresia(cluster, 1), _membresia(cluster, 2)
    primario.nodo.rol, backup.nodo.rol = "primario", "backup"
    primario.nodo.primario = backup.nodo.primario = 1
    primario.nodo.epoca = backup.nodo.epoca = 5
    for op in (_op_crear(1, 5, "m1", "s1"), _op_crear(2, 5, "m2", "s2")):
        primario.nodo.estado.aplicar(op)
    for op in (_op_crear(1, 5, "m1", "s1"), _op_crear(2, 5, "m3", "s-aislado")):
        backup.nodo.estado.aplicar(op)
    escucha = transporte.Escucha(cluster[2].puerto_cluster, backup.despachar)
    return primario, backup, escucha


def test_un_backup_que_diverge_en_la_misma_epoca_recibe_el_log_entero():
    primario, backup, escucha = _dos_primarios_de_la_misma_epoca()
    try:
        primario.nodo.estado.aplicar(_op_crear(3, 5, "m3", "s3"))

        primario.replica._poner_al_dia(2, 2, 5)

        assert backup.nodo.estado.log == primario.nodo.estado.log
    finally:
        escucha.cerrar()


def test_una_replica_ilegal_dispara_la_puesta_al_dia_del_log_entero():
    primario, backup, escucha = _dos_primarios_de_la_misma_epoca()
    try:
        with primario.nodo.lock:
            primario.nodo.estado.aplicar(_op_crear(3, 5, "m3", "s3"))
            primario.replica.replicar(primario.nodo.estado.log[-1])

        assert _esperar(lambda: backup.nodo.estado.log == primario.nodo.estado.log), \
            "el backup tiene que terminar con el log del primario"
    finally:
        escucha.cerrar()
