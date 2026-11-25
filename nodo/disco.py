import json
import os


class Disco:
    def __init__(self, directorio):
        self.directorio = os.fspath(directorio)
        os.makedirs(self.directorio, exist_ok=True)
        self._ruta_ops = os.path.join(self.directorio, "ops.jsonl")
        self._ruta_epoca = os.path.join(self.directorio, "epoca")
        self._descartar_linea_incompleta()

    def _descartar_linea_incompleta(self):
        try:
            with open(self._ruta_ops, "r+b") as archivo:
                contenido = archivo.read()
                if not contenido or contenido.endswith(b"\n"):
                    return
                # Trunca tras el ultimo salto para que el proximo agregar no se pegue a un corte.
                archivo.truncate(contenido.rfind(b"\n") + 1)
                archivo.flush()
                os.fsync(archivo.fileno())
        except FileNotFoundError:
            return

    def agregar(self, op):
        with open(self._ruta_ops, "a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(op) + "\n")
            archivo.flush()
            os.fsync(archivo.fileno())

    def operaciones(self):
        try:
            with open(self._ruta_ops, "r", encoding="utf-8") as archivo:
                return [json.loads(linea) for linea in archivo if linea.strip()]
        except FileNotFoundError:
            return []

    def _reemplazar(self, ruta, contenido):
        temporal = ruta + ".tmp"
        with open(temporal, "w", encoding="utf-8") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)

    def reescribir(self, ops):
        contenido = "".join(json.dumps(op) + "\n" for op in ops)
        self._reemplazar(self._ruta_ops, contenido)

    def guardar_epoca(self, epoca):
        self._reemplazar(self._ruta_epoca, f"{epoca}\n")

    def epoca(self):
        try:
            with open(self._ruta_epoca, "r", encoding="utf-8") as archivo:
                return int(archivo.read().strip())
        except FileNotFoundError:
            return 0


def abrir(directorio):
    return Disco(directorio) if directorio else None
