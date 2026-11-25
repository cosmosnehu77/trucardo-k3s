# Los logs del nodo, con un prefijo que dice quien habla y en que estado:
#
#     18:42:07 [N2│PRIMARIO│e=0│L=37] ...     id, rol, epoca y reloj de Lamport

import logging
import os

from nodo import telemetria

log = logging.getLogger("trucardo")


def estado(nodo):
    return {
        "nodo": nodo.id_nodo,
        "rol": nodo.rol,
        "epoca": nodo.epoca,
        "lamport": nodo.reloj.valor,
    }


class _Prefijo(logging.Filter):

    def __init__(self, nodo):
        super().__init__()
        self.nodo = nodo

    def filter(self, record):
        datos = estado(self.nodo)
        record.prefijo = (f"N{datos['nodo']}│{datos['rol'].upper()}│"
                          f"e={datos['epoca']}│L={datos['lamport']}")
        return True


class _AtributosNodo(logging.Filter):

    def __init__(self, nodo):
        super().__init__()
        self.nodo = nodo

    def filter(self, record):
        for clave, valor in estado(self.nodo).items():
            setattr(record, f"trucardo.{clave}", valor)
        return True


def configurar(nodo, destino=None, nivel=None):
    consola = logging.StreamHandler(destino)
    consola.addFilter(_Prefijo(nodo))
    consola.setFormatter(logging.Formatter("%(asctime)s [%(prefijo)s] %(message)s",
                                           datefmt="%H:%M:%S"))
    manejadores = []
    manejador_otel = telemetria.manejador_de_logs()
    if manejador_otel is not None:
        manejador_otel.filters[:] = [
            f for f in manejador_otel.filters if not isinstance(f, _AtributosNodo)
        ]
        manejador_otel.addFilter(_AtributosNodo(nodo))
        manejadores.append(manejador_otel)
    manejadores.append(consola)
    log.handlers[:] = manejadores
    log.setLevel((nivel or os.environ.get("LOG_NIVEL", "INFO")).upper())
    log.propagate = False
    return log
