import os
import tempfile

from nodo import config, disco
from nodo.cluster.protocolo import ATRASADO
from nodo.servidor import ServidorTruco
from tests.test_config import _entorno


def _op(seq, tipo="crear", id_sesion="s1", datos=None):
    return {
        "seq": seq,
        "epoca": 0,
        "lamport": seq,
        "tipo": tipo,
        "id_sesion": id_sesion,
        "id_operacion": f"op-{seq}",
        "datos": datos or {},
    }


def _sin_reloj(vista):
    return {clave: valor for clave, valor in vista.items() if clave != "reloj"}


def test_lo_guardado_se_lee_igual_y_en_orden():
    with tempfile.TemporaryDirectory() as directorio:
        almacen = disco.Disco(directorio)
        assert almacen.operaciones() == []

        ops = [
            _op(1, "crear", "s1", {"nombre": "ana", "id_mesa": "m1", "semilla": 1, "puntos": 15}),
            _op(2, "unirse", "s2", {"nombre": "beto", "id_mesa": "m1"}),
            _op(3, "jugar", "s1", {"carta": [1, "espada"]}),
        ]
        for op in ops:
            almacen.agregar(op)

        assert disco.Disco(directorio).operaciones() == ops


def test_un_backup_guarda_la_replica_antes_del_ack():
    primario = ServidorTruco(id_nodo=1, puntos=15)
    entrada = primario.crear_partida("ana", "s1")
    primario.unirse(entrada["id_partida"], "beto", "s2")

    with tempfile.TemporaryDirectory() as directorio:
        backup = ServidorTruco(id_nodo=2, puntos=15, primario=1, disco=disco.Disco(directorio))
        for op in primario.estado.log:
            assert backup._atiendo_replica(op) is None

        assert disco.Disco(directorio).operaciones() == primario.estado.log
        reiniciado = ServidorTruco(id_nodo=2, puntos=15, primario=1, disco=disco.Disco(directorio))
        assert reiniciado.estado.ultimo_seq == primario.estado.ultimo_seq
        assert reiniciado.estado.log == primario.estado.log


def test_una_ultima_linea_incompleta_se_descarta():
    with tempfile.TemporaryDirectory() as directorio:
        almacen = disco.Disco(directorio)
        op1, op2, op3 = _op(1), _op(2), _op(3)
        almacen.agregar(op1)
        almacen.agregar(op2)

        ruta_ops = os.path.join(directorio, "ops.jsonl")
        with open(ruta_ops, "ab") as archivo:
            archivo.write(b'{"seq": 3, "tipo": "jugar"')

        reabierto = disco.Disco(directorio)
        assert reabierto.operaciones() == [op1, op2]

        reabierto.agregar(op3)
        assert disco.Disco(directorio).operaciones() == [op1, op2, op3]


def test_la_epoca_sobrevive_a_un_reinicio():
    with tempfile.TemporaryDirectory() as directorio:
        almacen = disco.Disco(directorio)
        assert almacen.epoca() == 0
        almacen.guardar_epoca(3)
        assert disco.Disco(directorio).epoca() == 3

    with tempfile.TemporaryDirectory() as directorio:
        servidor = ServidorTruco(id_nodo=1, puntos=15, disco=disco.Disco(directorio))
        servidor.epoca = 4
        reiniciado = ServidorTruco(id_nodo=1, puntos=15, disco=disco.Disco(directorio))
        assert reiniciado.epoca == 4


def test_un_nodo_reiniciado_reconstruye_las_mismas_mesas():
    with tempfile.TemporaryDirectory() as directorio:
        servidor = ServidorTruco(id_nodo=1, puntos=15, disco=disco.Disco(directorio))
        servidor.epoca = 2
        entrada = servidor.crear_partida("ana", "s1")
        servidor.unirse(entrada["id_partida"], "beto", "s2")

        activo = "s1" if servidor.ver("s1")["es_mi_turno"] else "s2"
        carta = servidor.ver(activo)["mis_cartas"][0]
        servidor.jugar_carta(activo, carta, "op-1")

        ultimo_seq_antes = servidor.estado.ultimo_seq
        epoca_antes = servidor.epoca
        log_antes = list(servidor.estado.log)
        vista_s1_antes = _sin_reloj(servidor.ver("s1"))
        vista_s2_antes = _sin_reloj(servidor.ver("s2"))

        reiniciado = ServidorTruco(id_nodo=1, puntos=15, disco=disco.Disco(directorio))
        assert reiniciado.estado.ultimo_seq == ultimo_seq_antes == 3
        assert reiniciado.epoca == epoca_antes == 2
        assert reiniciado.estado.log == log_antes
        assert _sin_reloj(reiniciado.ver("s1")) == vista_s1_antes
        assert _sin_reloj(reiniciado.ver("s2")) == vista_s2_antes


def test_una_operacion_no_se_confirma_si_no_se_pudo_escribir():
    def fallar(op):
        raise OSError("disco lleno")

    with tempfile.TemporaryDirectory() as directorio:
        almacen = disco.Disco(directorio)
        servidor = ServidorTruco(id_nodo=1, puntos=15, disco=almacen)
        almacen.agregar = fallar

        try:
            servidor.crear_partida("ana", "s1")
        except OSError:
            pass
        else:
            raise AssertionError("crear_partida tendria que haber fallado con OSError")

        assert servidor.estado.ultimo_seq == 0
        assert servidor.estado.mesas == {}

    primario = ServidorTruco(id_nodo=1, puntos=15)
    primario.crear_partida("ana", "s1")
    op = primario.estado.log[0]

    with tempfile.TemporaryDirectory() as directorio:
        almacen = disco.Disco(directorio)
        backup = ServidorTruco(id_nodo=2, puntos=15, primario=1, disco=almacen)
        almacen.agregar = fallar

        assert backup._atiendo_replica(op) == ATRASADO
        assert backup.estado.ultimo_seq == 0
        assert backup.estado.mesas == {}


def test_sin_trucardo_datos_no_se_escribe_nada():
    with _entorno(TRUCARDO_DATOS=None):
        assert config.directorio_datos() is None
        assert disco.abrir(config.directorio_datos()) is None

    with tempfile.TemporaryDirectory() as directorio:
        with _entorno(TRUCARDO_DATOS=directorio):
            assert config.directorio_datos() == directorio
            assert isinstance(disco.abrir(config.directorio_datos()), disco.Disco)

    with tempfile.TemporaryDirectory() as directorio, _entorno(TRUCARDO_DATOS=None):
        antes = os.getcwd()
        os.chdir(directorio)
        try:
            servidor = ServidorTruco(id_nodo=1, puntos=15,
                                     disco=disco.abrir(config.directorio_datos()))
            entrada = servidor.crear_partida("ana", "s1")
            servidor.unirse(entrada["id_partida"], "beto", "s2")
            activo = "s1" if servidor.ver("s1")["es_mi_turno"] else "s2"
            servidor.jugar_carta(activo, servidor.ver(activo)["mis_cartas"][0], "op-1")
        finally:
            os.chdir(antes)

        assert servidor.disco is None
        assert servidor.estado.ultimo_seq == 3
        assert os.listdir(directorio) == []
