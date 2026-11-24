"""Tres nodos en el mismo proceso, latiendose y eligiendose por TCP, con
tiempos cortos: latido de 0,1 s y caido a los 0,4 s."""

import logging
import socket
import time

from nodo.cluster import eleccion as eleccion_mod
from nodo import transporte
from nodo.config import Nodo
from nodo.errores import NoPrimario
from nodo.cluster import Membresia
from nodo.cluster.protocolo import ELECCION
from nodo.registro import log
from nodo.servidor import ServidorTruco

LATIDO = 0.1
TIMEOUT = 0.4
JITTER = (0.01, 0.05)   # la espera al azar antes de convocar
TIMEOUT_ELECCION = 0.5  # lo que se le da a una eleccion antes de reintentarla


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _membresia(cluster, id_nodo, jitter=JITTER, timeout_eleccion=TIMEOUT_ELECCION):
    servidor = ServidorTruco(id_nodo=id_nodo, puntos=15)
    membresia = Membresia(servidor, cluster, latido=LATIDO, timeout=TIMEOUT,
                          jitter=jitter, timeout_eleccion=timeout_eleccion)
    servidor._set_membresia(membresia)
    return membresia


def _arrancar(cluster, id_nodo, jitter=JITTER, timeout_eleccion=TIMEOUT_ELECCION):
    """Un nodo arrancado. Tambien sirve para revivir uno en el mismo puerto."""
    membresia = _membresia(cluster, id_nodo, jitter, timeout_eleccion)
    membresia.arrancar()
    return membresia


def _cluster(**tiempos):
    """Tres nodos; al arrancar eligen primario, y gana el 3."""
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2, 3)}
    return cluster, {i: _arrancar(cluster, i, **tiempos) for i in cluster}


class _Contar(logging.Handler):
    """Cuenta las lineas de log que hablan de `texto`."""

    def __init__(self, texto):
        super().__init__()
        self.texto = texto
        self.n = 0

    def emit(self, record):
        if self.texto in record.getMessage():
            self.n += 1


def _esperar(condicion, limite=3.0):
    """Espera a que la condicion se cumpla. False si no pasa a tiempo."""
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return False


def _registrando(funcion, momentos):
    def registrada():
        momentos.append(time.monotonic())
        funcion()
    return registrada


def _apagar(membresias):
    for membresia in membresias.values():
        membresia.detener()


def _primario(membresias):
    primarios = [i for i, membresia in membresias.items() if membresia.nodo.rol == "primario"]
    return primarios[0] if len(primarios) == 1 else None


def _todos_en(membresias, ultimo_seq):
    return all(membresia.nodo.estado.ultimo_seq == ultimo_seq
               for membresia in membresias.values())


# ---------- el arranque ----------


def test_un_primario_reiniciado_vacio_no_vuelve_a_mandar():
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: _primario(membresias) is not None)
        viejo = _primario(membresias)
        assert _esperar(lambda: set(membresias[viejo].vivos) == set(cluster) - {viejo})
        membresias[viejo].nodo.crear_partida("ana", "c0ffee" * 5)
        assert _esperar(lambda: _todos_en(membresias, 1)), "la op tiene que llegar a todos"

        membresias[viejo].detener()
        membresias[viejo] = _arrancar(cluster, viejo)
        assert membresias[viejo].nodo.rol == "backup", \
            "arranca con el estado vacio: no se puede creer primario"
        assert membresias[viejo].nodo.primario is None

        assert _esperar(lambda: _primario(membresias) is not None and _todos_en(membresias, 1)), \
            "tiene que quedar un solo primario y el reiniciado tiene que ponerse al dia"
    finally:
        _apagar(membresias)


def test_tres_nodos_que_arrancan_juntos_eligen_uno_solo():
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: _primario(membresias) == 3), \
            "con el mismo ultimo_seq tiene que ganar el id mayor, y uno solo"
        assert _esperar(lambda: all(m.nodo.primario == 3 for m in membresias.values()))
        assert len({m.nodo.epoca for m in membresias.values()}) == 1, \
            "todos tienen que quedar en la misma epoca"
        assert membresias[3].nodo.epoca > 0, "ganar la eleccion gasta una epoca"
    finally:
        _apagar(membresias)


def test_un_nodo_solo_se_corona_al_arrancar():
    cluster = {1: Nodo(1, "127.0.0.1", 0, _puerto_libre()),
               2: Nodo(2, "127.0.0.1", 0, _puerto_libre())}
    membresias = {1: _arrancar(cluster, 1)}
    try:
        assert _esperar(lambda: membresias[1].nodo.rol == "primario"), \
            "si nadie contesta, el que arranco se tiene que coronar"
        assert membresias[1].nodo.primario == 1
    finally:
        _apagar(membresias)


def test_al_arrancar_no_anuncia_un_reintento():
    contador = _Contar("reintento")
    nivel = log.level
    log.setLevel(logging.INFO)
    log.addHandler(contador)
    cluster = {1: Nodo(1, "127.0.0.1", 0, _puerto_libre())}
    membresias = {1: _arrancar(cluster, 1)}
    try:
        assert _esperar(lambda: membresias[1].nodo.rol == "primario")
        assert contador.n == 0, "la primera eleccion no es el reintento de ninguna"
    finally:
        log.removeHandler(contador)
        log.setLevel(nivel)
        _apagar(membresias)


def test_tres_nodos_se_ven():
    """El primario ve a los dos backups, y un backup sabe quien manda."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2}), "el primario ve a los dos"
        respuesta = transporte.enviar(("127.0.0.1", cluster[1].puerto_cluster),
                                      membresias[3].mensaje("QUIEN"), timeout=1.0)
        assert respuesta["rol"] == "backup"
        assert respuesta["primario"] == 3
    finally:
        _apagar(membresias)


def test_si_el_primario_deja_de_latir_los_backups_lo_detectan():
    """Se "mata" al primario: los backups lo dan por caido cuando pasa el
    timeout sin latidos, y no antes."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        detecciones = []
        for i in (1, 2):
            membresias[i].sin_primario = _registrando(membresias[i].sin_primario, detecciones)
        membresias[3].detener()
        muerto = time.monotonic()

        assert _esperar(lambda: all(membresias[i].nodo.primario != 3 for i in (1, 2))), \
            "los backups tienen que dejar de seguirlo"
        assert detecciones, "alguno lo tiene que dar por caido por el silencio"
        # el ultimo latido pudo llegar hasta un latido antes de detenerlo
        assert min(detecciones) - muerto >= TIMEOUT - LATIDO, "y no antes del timeout"
    finally:
        _apagar(membresias)


# ---------- la eleccion ----------


def test_al_caer_el_primario_gana_uno_solo():
    """Queda un solo primario nuevo, en una epoca mayor. Con el mismo
    ultimo_seq gana el id mayor."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        membresias[3].detener()

        assert _esperar(lambda: membresias[2].nodo.rol == "primario"), \
            "con el mismo ultimo_seq tiene que ganar el id mas alto"
        assert _esperar(lambda: membresias[1].nodo.primario == 2), \
            "y el perdedor lo tiene que reconocer"
        assert membresias[1].nodo.rol == "backup", "no pueden quedar dos primarios"
        assert membresias[2].nodo.epoca > 0, "ganar una eleccion gasta una epoca"
        assert membresias[1].nodo.epoca == membresias[2].nodo.epoca, \
            "y los dos tienen que quedar en la misma"
    finally:
        _apagar(membresias)


def test_si_queda_uno_solo_se_corona():
    """Caen dos de tres y el que queda se corona: no hace falta mayoria."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        epoca = membresias[1].nodo.epoca
        membresias[3].detener()
        membresias[2].detener()

        assert _esperar(lambda: membresias[1].nodo.rol == "primario"), \
            "el ultimo que queda se tiene que coronar"
        assert membresias[1].nodo.primario == 1
        assert membresias[1].nodo.epoca > epoca, "y ganar gasta una epoca"
    finally:
        _apagar(membresias)


def test_si_el_ganador_muere_en_plena_eleccion_se_reintenta():
    """El que dijo "mando yo" muere antes del COORDINADOR: el otro se vuelve
    a postular y se corona."""
    # N2 falso: contesta el primer ELECCION con "mando yo" y cierra el puerto
    preguntas = []

    def despachar(mensaje):
        if mensaje.get("tipo") == "ELECCION":
            preguntas.append(mensaje["origen"])
            falso.cerrar()
            return {"ok": True, "mando_yo": True, "ultimo_seq": 99, "epoca": 0}
        return {"ok": True}

    falso = transporte.Escucha(0, despachar, host="127.0.0.1")
    cluster = {1: Nodo(1, "127.0.0.1", 0, _puerto_libre()),
               2: Nodo(2, "127.0.0.1", 0, falso.puerto)}
    membresias = {}
    try:
        membresias[1] = _arrancar(cluster, 1)     # N2 nunca late
        intentos = []
        convocar = membresias[1].eleccion.convocar

        def contando():
            intentos.append(time.monotonic())
            return convocar()

        membresias[1].eleccion.convocar = contando

        assert _esperar(lambda: membresias[1].nodo.rol == "primario",
                        limite=TIMEOUT + 3 * TIMEOUT_ELECCION + 2), \
            f"se tiene que coronar al reintentar, y convoco {len(intentos)} vez/veces"
        assert preguntas == [1], "N2 le tuvo que decir 'mando yo' la primera vez"
        assert len(intentos) >= 2, "primero se retiro, despues reintento"
    finally:
        falso.cerrar()
        _apagar(membresias)


def test_entre_dos_coronados_de_la_misma_epoca_gana_el_id_mayor():
    """Dos coronados en la misma epoca se mandan COORDINADOR: se baja el de
    id menor, igual que con el latido."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        _apagar(membresias)     # sin hilos: los COORDINADOR los manda el test
        for i in (1, 2):
            with membresias[i].nodo.lock:
                membresias[i].nodo.rol = "primario"
                membresias[i].nodo.primario = i
                membresias[i].nodo.epoca = 1

        respuesta = membresias[2].eleccion.al_coordinador(membresias[1].mensaje("COORDINADOR"))
        assert respuesta["ok"] is False, "N2 le gana el desempate: no se baja"
        assert membresias[2].nodo.rol == "primario"

        respuesta = membresias[1].eleccion.al_coordinador(membresias[2].mensaje("COORDINADOR"))
        assert respuesta["ok"] is True, "N1 pierde el desempate: lo adopta"
        assert membresias[1].nodo.rol == "backup"
        assert membresias[1].nodo.primario == 2
    finally:
        _apagar(membresias)


def test_no_anuncia_reintento_mientras_la_eleccion_corre():
    """Una candidatura que sigue corriendo no se anuncia como reintento cada
    medio latido."""
    cluster, membresias = _cluster(jitter=(0.4, 0.4), timeout_eleccion=0.01)
    contador = _Contar("reintento")
    nivel = log.level
    log.setLevel(logging.INFO)
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        log.addHandler(contador)
        membresias[3].detener()
        assert _esperar(lambda: membresias[2].nodo.rol == "primario", limite=5.0)
        assert contador.n <= 2, (
            f"{contador.n} anuncios de reintento: el vigia esta contando una "
            f"eleccion en curso como una que no termino")
    finally:
        log.removeHandler(contador)
        log.setLevel(nivel)
        _apagar(membresias)


def test_la_eleccion_usa_el_jitter_de_la_instancia():
    """_convocar usa el jitter del nodo y no el de config."""
    cluster, membresias = _cluster()
    dormidas = []
    uniform = eleccion_mod.random.uniform

    def espiando(a, b):
        dormidas.append((a, b))
        return uniform(a, b)

    eleccion_mod.random.uniform = espiando
    try:
        membresias[3].detener()
        assert _esperar(lambda: dormidas), "no convoco nadie"
        assert set(dormidas) == {JITTER}, \
            f"durmio {sorted(set(dormidas))} y el del nodo es {JITTER}"
    finally:
        eleccion_mod.random.uniform = uniform
        _apagar(membresias)


def test_el_primario_depuesto_se_baja():
    """El primario viejo vuelve con una epoca pasada: se baja solo y adopta
    al nuevo."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        membresias[3].detener()
        assert _esperar(lambda: membresias[2].nodo.rol == "primario")
        epoca_nueva = membresias[2].nodo.epoca

        membresias[3] = _arrancar(cluster, 3)
        with membresias[3].nodo.lock:
            membresias[3].nodo.rol = "primario"
            membresias[3].nodo.primario = 3
            membresias[3].nodo.epoca = 0
        assert membresias[3].nodo.epoca < epoca_nueva, "y con una epoca vieja"

        assert _esperar(lambda: membresias[3].nodo.rol == "backup"), \
            "el zombie se tiene que bajar solo"
        assert _esperar(lambda: membresias[3].nodo.primario == 2
                        and membresias[3].nodo.epoca == membresias[2].nodo.epoca), \
            "y seguir al primario de verdad, en su epoca"
        assert _esperar(lambda: 3 in membresias[2].vivos), \
            "y volver a entrar a la vista del primario de verdad"
    finally:
        _apagar(membresias)


def test_el_latido_rechazado_igual_entra_al_reloj():
    """Una respuesta que dice que no tambien es un mensaje: su lamport entra
    al reloj."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        membresias[3].detener()     # sin sus hilos: el latido lo manda el test
        # N2 en una epoca mayor y con el reloj lejos: rechaza el latido de N3
        with membresias[2].nodo.lock:
            membresias[2].nodo.epoca = 9
        membresias[2].nodo.reloj.recibir(500)

        membresias[3].latido.latir_a(2, 0)

        assert membresias[3].nodo.rol == "backup", \
            "el rechazo lo tiene que bajar, que es la rama que estamos probando"
        assert membresias[3].nodo.reloj.valor > 500, \
            (f"el reloj quedo en {membresias[3].nodo.reloj.valor}: no absorbio "
             f"el lamport de la respuesta rechazada")
    finally:
        _apagar(membresias)


# ---------- la replica ----------


def test_el_zombie_que_replica_se_entera_y_se_baja():
    """Un primario viejo atiende una jugada y al replicarla lo rechazan: se
    baja, no la confirma, y los backups no la aplican."""
    cluster, membresias = _cluster()
    try:
        assert _esperar(lambda: set(membresias[3].vivos) == {1, 2})
        membresias[3].detener()     # sin sus hilos: que se entere por la replica
        for i in (1, 2):
            with membresias[i].nodo.lock:
                membresias[i].nodo.epoca = 5

        zombie = membresias[3].nodo
        try:
            zombie.crear_partida("ana", "c0ffee" * 5)
        except NoPrimario:
            pass
        else:
            assert False, "un zombie no le puede confirmar la op al cliente"
        assert zombie.rol == "backup", "se tiene que bajar"
        assert zombie.epoca >= 5, "y adoptar la epoca de los que lo rechazaron"
        assert all(membresias[i].nodo.estado.ultimo_seq == 0 for i in (1, 2)), \
            "los backups no pueden aplicar la op de un zombie"
    finally:
        _apagar(membresias)


# ---------- eleccion entre epocas distintas ----------


def test_dos_candidatos_de_epocas_distintas_no_se_contestan_mando_yo_los_dos():
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2)}
    membresias = {i: _membresia(cluster, i) for i in cluster}
    for membresia in membresias.values():
        membresia.eleccion.convocar_aparte = lambda: None

    membresias[1].nodo.epoca = 2
    membresias[2].nodo.epoca = 1

    pedido_1 = membresias[1].mensaje(ELECCION, ultimo_seq=membresias[1].nodo.estado.ultimo_seq)
    pedido_2 = membresias[2].mensaje(ELECCION, ultimo_seq=membresias[2].nodo.estado.ultimo_seq)

    respuesta_de_2 = membresias[2].eleccion._al_eleccion(pedido_1)
    respuesta_de_1 = membresias[1].eleccion._al_eleccion(pedido_2)

    assert respuesta_de_1["mando_yo"] is True, "el de epoca mayor le tiene que ganar"
    assert respuesta_de_2["mando_yo"] is False, "el de epoca menor no le puede contestar mando_yo"


def test_dos_nodos_en_epocas_distintas_eligen_un_solo_primario():
    cluster = {i: Nodo(i, "127.0.0.1", 0, _puerto_libre()) for i in (1, 2)}
    membresias = {i: _arrancar(cluster, i, timeout_eleccion=30) for i in cluster}
    try:
        assert _esperar(lambda: _primario(membresias) is not None
                        and all(m.nodo.primario == _primario(membresias)
                                and not m.eleccion.convocando
                                for m in membresias.values()))
        for i, epoca in ((2, 3), (1, 5)):
            with membresias[i].nodo.lock:
                membresias[i].nodo.rol = "backup"
                membresias[i].sin_primario()
                membresias[i].nodo.epoca = epoca
        for i in (1, 2):
            membresias[i].eleccion.convocar_aparte()

        assert _esperar(lambda: _primario(membresias) is not None
                        and all(m.nodo.primario == _primario(membresias)
                                for m in membresias.values()),
                        limite=3), "tiene que quedar un solo primario reconocido por los dos"
    finally:
        _apagar(membresias)
