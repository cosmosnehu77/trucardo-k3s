# El objeto remoto que usan los clientes, por Pyro5.
#
#   python3 -m nodo.servidor [id_nodo]
#
# Cada pedido se convierte en una op que pasa por EstadoServicio.aplicar(), y
# esa op es lo que se replica. Solo atiende el primario: un backup contesta
# NoPrimario diciendo quien manda. Todo metodo recibe al final el reloj de
# Lamport del que pide.

import random
import sys
import threading
import uuid

import Pyro5.api
import Pyro5.callcontext
from opentelemetry import context

from nodo import config, disco, registro, telemetria
from nodo.cluster.protocolo import AL_DIA, ATRASADO, DUPLICADA, ILEGAL
from nodo.errores import NoPrimario
from nodo.estado import EstadoServicio
from nodo.historial import armar_historial, resumir_mesas
from nodo.lamport import Reloj
from nodo.cluster import Membresia
from nodo.registro import log
from nodo.vista import armar_vista

NOMBRE_OBJETO = "truco"

# Un hilo por pedido; la exclusion mutua la da ServidorTruco.lock.
Pyro5.config.SERVERTYPE = "thread"


@Pyro5.api.expose
class ServidorTruco:
    def __init__(self, id_nodo=1, puntos=None, primario=None, disco=None):
        self.id_nodo = id_nodo
        self.puntos = config.puntos() if puntos is None else puntos
        self.reloj = Reloj()
        self.__membresia = None     # por aca salen las replicas; la conecta main()
        # Todo acceso al estado va con este lock. Es reentrante porque los
        # metodos publicos lo toman y llaman a _atender(), que lo vuelve a tomar.
        self.lock = threading.RLock()
        self.disco = disco

        # Lo propio de este nodo, que no se replica. Sin primario, el nodo es
        # el suyo (un solo nodo).
        self.primario = id_nodo if primario is None else primario
        self.rol = "primario" if self.primario == id_nodo else "backup"
        self._epoca = 0

        self.estado = EstadoServicio()      # lo que se replica
        if disco is not None:
            self.estado = self._reconstruir(self.disco.operaciones())
            self._epoca = disco.epoca()

    @property
    def epoca(self):
        return self._epoca

    @epoca.setter
    def epoca(self, valor):
        if self.disco is not None and valor != self._epoca:
            self.disco.guardar_epoca(valor)
        self._epoca = valor

    def _reconstruir(self, ops):
        estado = EstadoServicio()
        for op in ops:
            estado.aplicar(op)
        return estado

    def _recortar(self, cantidad):
        log.warning(f"recorto el log de la op {self.estado.ultimo_seq} a la {cantidad}: "
                    f"diverge del primario")
        conservadas = self.estado.log[:cantidad]
        if self.disco is not None:
            self.disco.reescribir(conservadas)
        self.estado = self._reconstruir(conservadas)

    def _aplicar(self, op):
        self.estado.aplicar(op)
        if self.disco is not None:
            try:
                self.disco.agregar(op)
            except OSError as error:
                log.error(f"no pude guardar la op {op['seq']} en disco: {error}")
                self.estado = self._reconstruir(self.disco.operaciones())
                raise

    def _set_membresia(self, membresia):
        self.__membresia = membresia

    def quien_es_primario(self, lamport=0):
        self.reloj.recibir(lamport)
        return self._quien()

    def _quien(self):
        with self.lock:
            return {"primario": self.primario, "soy_yo": self.rol == "primario",
                    "rol": self.rol, "epoca": self.epoca,
                    "ultimo_seq": self.estado.ultimo_seq, "reloj": self.reloj.valor}

    def _exigir_primario(self):
        with self.lock:
            if self.rol != "primario":
                raise NoPrimario(self.primario)

    # ---------- entrar a una partida ----------

    def existe_sesion_anterior(self, nombre, lamport=0):
        with self.lock:
            return self.estado.buscar_sesion_por_nombre(nombre)

    def crear_partida(self, nombre, id_sesion, lamport=0):
        with self.lock:
            # lo que no es determinista se decide aca y viaja resuelto en la op
            datos = {"nombre": nombre, "id_mesa": self._id_mesa_libre(),
                     "semilla": random.randrange(1, 10 ** 9), "puntos": self.puntos}
            self._atender("crear", id_sesion, id_sesion, lamport, datos)
            return self._entrada(id_sesion)

    def unirse(self, id_partida, nombre, id_sesion, lamport=0):
        #Sienta al jugador 2 y arranca la partida.
        with self.lock:
            self._atender("unirse", id_sesion, id_sesion, lamport,
                          {"nombre": nombre, "id_mesa": id_partida})
            return self._entrada(id_sesion)

    def listar_partidas(self, lamport=0):
        with self.lock:
            self.reloj.recibir(lamport)
            self._exigir_primario()
            libres = sorted((mesa for mesa in self.estado.mesas.values() if not mesa.completa),
                            key=lambda mesa: (mesa.creada_en, mesa.id))
            return [{"id_partida": mesa.id, "creada_por": mesa.nombres.get(1)}
                    for mesa in libres]

    # ---------- seguir una partida desde afuera ----------

    def listar_mesas(self, lamport=0):
        with self.lock:
            self.reloj.recibir(lamport)
            return {"mesas": resumir_mesas(self.estado),
                    "nodo": self.id_nodo, **self._quien()}

    def historial(self, id_mesa, desde=0, lamport=0):
        #El log de una mesa.
        with self.lock:
            self.reloj.recibir(lamport)
            return {**armar_historial(self.estado, id_mesa, desde),
                    "nodo": self.id_nodo, **self._quien()}

    def _id_mesa_libre(self):
        while True:
            id_mesa = uuid.uuid4().hex[:6]
            if id_mesa not in self.estado.mesas:
                return id_mesa

    # ---------- jugar ----------

    def ver(self, id_sesion, lamport=0):
        with self.lock:
            self.reloj.recibir(lamport)
            self._exigir_primario()
            return self._vista(id_sesion)

    def jugar_carta(self, id_sesion, carta, id_operacion, lamport=0):
        return self._jugada("jugar", id_sesion, id_operacion, lamport, {"carta": list(carta)})

    def cantar(self, id_sesion, canto, id_operacion, lamport=0):
        return self._jugada("cantar", id_sesion, id_operacion, lamport, {"canto": canto})

    def responder(self, id_sesion, quiere, id_operacion, lamport=0):
        return self._jugada("responder", id_sesion, id_operacion, lamport,
                            {"quiere": bool(quiere)})

    def irse_al_mazo(self, id_sesion, id_operacion, lamport=0):
        return self._jugada("mazo", id_sesion, id_operacion, lamport, {})

    def _jugada(self, tipo, id_sesion, id_operacion, lamport, datos):
        with self.lock:
            sello = self._atender(tipo, id_sesion, id_operacion, lamport, datos)
            return self._vista(id_sesion, sello)

    # ---------- toda operacion pasa por aca ----------

    def _atender(self, tipo, id_sesion, id_operacion, lamport, datos):
        """Aplica y replica una operacion, y devuelve su sello. Si es un
        reintento (mismo id_operacion), devuelve el sello de la primera vez
        sin aplicarla de nuevo."""
        token = context.attach(
            telemetria.de_anotaciones(Pyro5.callcontext.current_context.annotations)
        )
        try:
            with telemetria.span(f"jugada {tipo}", self) as actual:
                with self.lock:
                    self.reloj.recibir(lamport)
                    self._exigir_primario()
                    if self.estado.ya_aplicada(id_sesion, id_operacion):
                        sesion = self.estado.sesion(id_sesion)
                        actual.set_attribute("trucardo.reintento", True)
                        log.info(f"reintento de {sesion.nombre} ({str(id_operacion)[:8]}): "
                                 f"ya estaba aplicada, no se aplica dos veces")
                        return sesion.ultima_operacion[1]

                    op = {"seq": self.estado.ultimo_seq + 1, "epoca": self.epoca,
                          "lamport": self.reloj.tic(), "tipo": tipo, "id_sesion": id_sesion,
                          "id_operacion": id_operacion, "datos": datos}
                    actual.set_attribute("trucardo.seq", op["seq"])
                    actual.set_attribute("trucardo.lamport", op["lamport"])

                    self._aplicar(op)

                    replicas = ""
                    if self.__membresia is not None:
                        respuestas = self.__membresia.replica.replicar(op)
                        if self.rol != "primario":
                            # replicando me entere de que ya no mando: no se confirma
                            raise NoPrimario(None)
                        al_dia = sum(1 for r in respuestas.values() if r.get("ok"))
                        replicas = f" · la tienen {al_dia}/{len(respuestas)} de los que contestaron"

                    sesion = self.estado.sesion(id_sesion)
                    log.info(f"op {op['seq']} · {tipo} · {sesion.nombre} · "
                             f"mesa {sesion.id_mesa}{replicas}")
                    return op["lamport"]
        finally:
            context.detach(token)

    # ---------- el otro lado: lo que me replica el primario ----------

    def _atiendo_replica(self, op, previa=None):
        with self.lock:
            motivo = self._aplicar_replica(op, previa)
            if motivo is None:
                sesion = self.estado.sesion(op["id_sesion"])
                log.info(f"op {op['seq']} · {op['tipo']} · {sesion.nombre} · "
                         f"mesa {sesion.id_mesa}")
            return motivo

    def _atiendo_puesta_al_dia(self, ops, desde, epoca):
        """Aplica en orden las ops que me faltaban. Devuelve None si con eso
        quedo al dia, o el motivo por el que se corto."""
        with self.lock:
            if desde > self.estado.ultimo_seq:
                return ATRASADO
            inicio = self.estado.ultimo_seq
            for op in ops:
                seq = op.get("seq", 0) if isinstance(op, dict) else 0
                # Como en Raft, solo se recorta ante una op distinta: la puesta
                # al dia pudo calcularse antes de una REPLICA que ya confirme.
                if 0 < seq <= self.estado.ultimo_seq and self.estado.log[seq - 1] != op:
                    self._recortar(seq - 1)
                motivo = self._aplicar_replica(op)
                if motivo not in AL_DIA:
                    log.warning(f"la puesta al dia se corto en la op "
                                f"{op.get('seq') if isinstance(op, dict) else op!r}: {motivo}")
                    return motivo
            # Lo que sigue a lo recibido solo puede ser del primario actual.
            fin = desde + len(ops)
            if self.estado.ultimo_seq > fin and self.estado.log[fin]["epoca"] != epoca:
                self._recortar(fin)
            log.info(f"puesta al dia: de la op {inicio} a la {self.estado.ultimo_seq}")
            return None

    def _aplicar_replica(self, op, previa=None):
        if not isinstance(op, dict) or "seq" not in op or op["seq"] < 1:
            return ILEGAL
        if op["seq"] <= self.estado.ultimo_seq:
            return DUPLICADA if self.estado.log[op["seq"] - 1] == op else ATRASADO
        if op["seq"] > self.estado.ultimo_seq + 1:
            return ATRASADO
        if previa is not None and previa != self.estado.epoca_ultima:
            return ATRASADO

        try:
            self._aplicar(op)
        except OSError:
            return ATRASADO
        except Exception as error:
            log.warning(f"no pude aplicar la op {op['seq']}: {error}")
            return ILEGAL
        return None

    # ---------- respuestas ----------

    def _vista(self, id_sesion, sello=None):
        sesion = self.estado.sesion(id_sesion)
        vista = armar_vista(self.estado.mesa(sesion.id_mesa), sesion, self.reloj)
        if sello is not None:
            vista["sello"] = sello
        return vista

    def _entrada(self, id_sesion):
        sesion = self.estado.sesion(id_sesion)
        return {"id_partida": sesion.id_mesa, "id_sesion": id_sesion,
                "reloj": self.reloj.valor}


def main():
    id_nodo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    try:
        cluster = config.nodos()
        if id_nodo not in cluster:
            sys.exit(f"el nodo {id_nodo} no esta en TRUCARDO_NODOS (estan: {sorted(cluster)})")
        servidor = ServidorTruco(id_nodo, disco=disco.abrir(config.directorio_datos()))
    except ValueError as error:
        sys.exit(f"configuracion invalida: {error}")
    yo = cluster[id_nodo]
    registro.configurar(servidor)
    telemetria.configurar(f"trucardo-nodo{id_nodo}")

    membresia = Membresia(servidor, cluster)
    servidor._set_membresia(membresia)
    try:
        membresia.arrancar()
    except OSError as error:
        sys.exit(f"no puedo escuchar en el puerto del cluster {yo.puerto_cluster}: {error}. "
                 f"Si dice 'Address already in use', hay otro nodo con ese puerto.")

    daemon = Pyro5.api.Daemon(host="0.0.0.0", port=yo.puerto_pyro)
    daemon.register(servidor, NOMBRE_OBJETO)
    log.info(f"escuchando en PYRO:{NOMBRE_OBJETO}@<tu-ip>:{yo.puerto_pyro} "
             f"· cluster en el puerto {yo.puerto_cluster} · mesas a {servidor.puntos} puntos")
    log.info(f"nodos {sorted(cluster)} · arranco de backup y sin primario: se elige uno "
             f"(gana el mas al dia y, si empatan, el de id mayor)")
    log.info("Ctrl+C para salir.")
    try:
        daemon.requestLoop()
    except KeyboardInterrupt:
        log.info("chau.")
    finally:
        membresia.detener()
        telemetria.cerrar()


if __name__ == "__main__":
    main()
