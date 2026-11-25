# La eleccion Bully: quien manda cuando el primario deja de latir.

import random
import time

from nodo import telemetria
from nodo.cluster.protocolo import COORDINADOR, ELECCION, EPOCA_VIEJA
from nodo.registro import log


class Eleccion:

    def __init__(self, membresia):
        self.m = membresia
        self._convocando = False        # hay una candidatura mia corriendo

    @property
    def manejadores(self):
        return {ELECCION: self._al_eleccion,
                COORDINADOR: self.al_coordinador}

    @property
    def convocando(self):
        return self._convocando

    # ---------- postularme ----------

    def convocar_aparte(self):
        with self.m.nodo.lock:
            if self._convocando:
                return
            self._convocando = True
            self.m.eleccion_desde = time.monotonic()
        telemetria.hilo(self.convocar).start()

    def convocar(self):
        nodo = self.m.nodo
        try:
            time.sleep(random.uniform(*self.m.jitter))
            with nodo.lock:
                if self.m.detenido.is_set() or self.m.eleccion_desde is None:
                    return
                epoca_ultima = nodo.estado.epoca_ultima
                ultimo_seq = nodo.estado.ultimo_seq
                pedido = self.m.mensaje(ELECCION, ultimo_seq=ultimo_seq,
                                        epoca_ultima=epoca_ultima)
            log.info(f"arranco una eleccion (epoca_ultima {epoca_ultima}, ultimo_seq {ultimo_seq})")

            respuestas = self.m.preguntar_a_todos(pedido)
            if any(r.get("mando_yo") for r in respuestas.values()):
                log.info("me gana otro candidato: espero su COORDINADOR")
                return

            log.info(f"nadie me gana (contestaron {len(respuestas)} de "
                     f"{len(self.m.cluster) - 1}): me corono")
            self._coronarme(respuestas)
        finally:
            with nodo.lock:
                self._convocando = False

    def _coronarme(self, respuestas):
        nodo = self.m.nodo
        with nodo.lock:
            if self.m.detenido.is_set():
                return
            vistas = [nodo.epoca] + [r.get("epoca", 0) for r in respuestas.values()]
            self.m.coronarme(max(vistas) + 1,
                             {i: r.get("ultimo_seq", 0) for i, r in respuestas.items()})
            aviso = self.m.mensaje(COORDINADOR)
            epoca = nodo.epoca
        log.info(f"gano la eleccion: soy el primario de la epoca {epoca}")
        self.m.preguntar_a_todos(aviso)

    def _credenciales(self):
        return (self.m.nodo.estado.epoca_ultima,
                self.m.nodo.estado.ultimo_seq,
                self.m.nodo.id_nodo)

    # ---------- contestarle a los demas ----------

    def _al_eleccion(self, mensaje):
        suyas = (mensaje.get("epoca_ultima", 0),
                 mensaje.get("ultimo_seq", 0),
                 mensaje["origen"])

        with self.m.nodo.lock:
            mias = self._credenciales()
            le_gano = mias > suyas
            if not le_gano:
                self.m.eleccion_desde = time.monotonic()
            convocar = le_gano and not self.m.primario_vivo()
            respuesta = self.m.respuesta(mando_yo=le_gano)

        if convocar:
            self.convocar_aparte()
        return respuesta

    def al_coordinador(self, mensaje):
        origen, epoca = mensaje["origen"], mensaje.get("epoca", 0)

        with self.m.nodo.lock:
            if self.m.lo_rechazo(origen, epoca):
                return self.m.respuesta(EPOCA_VIEJA)
            self.m.adoptar_primario(origen, epoca)
            return self.m.respuesta()
