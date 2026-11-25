_ROL_SERVIDOR = "node-role.kubernetes.io/control-plane"
_PREFIJO_SERVICIO = "trucardo-"
_PREFIJO_CLIENTE = "cliente-"
_CAMPOS_MESA = ("id_mesa", "jugadores", "estado", "marcador", "numero_mano")
_CAMPOS_NODO = ("rol", "primario", "epoca", "ultimo_seq", "reloj")


def maquinas(nodos_k8s):
    lista = [_maquina(nodo) for nodo in nodos_k8s]
    return sorted(lista, key=lambda m: (m["rol"] != "servidor", m["nombre"]))


def _maquina(nodo):
    estado = nodo.get("status", {})
    direcciones = {d["type"]: d["address"] for d in estado.get("addresses", [])}
    condiciones = {c["type"]: c["status"] for c in estado.get("conditions", [])}
    etiquetas = nodo["metadata"].get("labels", {})
    return {
        "nombre": nodo["metadata"]["name"],
        "ip": direcciones.get("InternalIP"),
        "lista": condiciones.get("Ready") == "True",
        "rol": "servidor" if _ROL_SERVIDOR in etiquetas else "agente",
    }


def componente(etiquetas):
    app = etiquetas.get("app")
    if app == "trucardo":
        return f"nodo{etiquetas.get('nodo')}"
    return app


def pods(pods_k8s):
    lista = []
    for pod in pods_k8s:
        nombre_componente = componente(pod["metadata"].get("labels", {}))
        if nombre_componente is None:
            continue
        estado = pod.get("status", {})
        contenedores = estado.get("containerStatuses", [])
        lista.append({
            "nombre": pod["metadata"]["name"],
            "componente": nombre_componente,
            "maquina": pod.get("spec", {}).get("nodeName"),
            "fase": "Terminating" if pod["metadata"].get("deletionTimestamp") else estado.get("phase"),
            "listo": {c["type"]: c["status"] for c in estado.get("conditions", [])}.get("Ready") == "True",
            "reinicios": sum(c.get("restartCount", 0) for c in contenedores),
            "ip": estado.get("podIP"),
        })
    return sorted(lista, key=lambda p: p["nombre"])


def nodos_trucardo(respuestas):
    lista = []
    for id_nodo in sorted(respuestas):
        respuesta = respuestas[id_nodo]
        lista.append({"id": id_nodo, "responde": respuesta is not None,
                      **{campo: None if respuesta is None else respuesta.get(campo)
                         for campo in _CAMPOS_NODO}})
    return lista


def mesas(respuestas):
    vivas = [r for r in respuestas.values() if r is not None]
    if not vivas:
        return []
    primarios = [r for r in vivas if r["rol"] == "primario"]
    fuente = max(primarios or vivas, key=lambda r: (r["epoca"], r["ultimo_seq"]))
    return [{campo: mesa.get(campo) for campo in _CAMPOS_MESA} for mesa in fuente.get("mesas", [])]


def mensajes(trazas):
    spans = {}
    for consulta in trazas:
        if not consulta:
            continue
        for recurso in consulta.get("result", {}).get("resourceSpans", []):
            servicio = _servicio(recurso)
            for alcance in recurso.get("scopeSpans", []):
                for span in alcance.get("spans", []):
                    spans[span["spanId"]] = (servicio, span)

    lista = []
    for servicio, span in spans.values():
        padre = spans.get(span.get("parentSpanId"))
        if padre is None or padre[0] == servicio:
            continue
        lista.append({"ms": int(span["startTimeUnixNano"]) // 1_000_000,
                      "de": padre[0], "a": servicio, "tipo": span["name"]})
    return sorted(lista, key=lambda m: (m["ms"], m["a"]))


def _servicio(recurso):
    for atributo in recurso.get("resource", {}).get("attributes", []):
        if atributo["key"] == "service.name":
            return atributo["value"]["stringValue"].removeprefix(_PREFIJO_SERVICIO)
    return "?"


def clientes(lista_mesas, lista_mensajes):
    por_nombre = {}
    for mesa in lista_mesas:
        for jugador in mesa["jugadores"]:
            if jugador:
                por_nombre[jugador] = {"nombre": jugador, "mesa": mesa["id_mesa"],
                                       "estado": mesa["estado"], "trazado": False}
    for mensaje in lista_mensajes:
        for extremo in (mensaje["de"], mensaje["a"]):
            if not extremo.startswith(_PREFIJO_CLIENTE):
                continue
            nombre = extremo.removeprefix(_PREFIJO_CLIENTE)
            por_nombre.setdefault(nombre, {"nombre": nombre, "mesa": None, "estado": None,
                                           "trazado": True})
    return [por_nombre[nombre] for nombre in sorted(por_nombre)]


def armar(nodos_k8s, pods_k8s, respuestas, trazas, hora):
    lista_mesas = mesas(respuestas)
    lista_mensajes = mensajes(trazas or [])
    return {
        "hora": hora,
        "telemetria": any(consulta is not None for consulta in trazas or []),
        "maquinas": maquinas(nodos_k8s),
        "pods": pods(pods_k8s),
        "nodos": nodos_trucardo(respuestas),
        "mesas": lista_mesas,
        "clientes": clientes(lista_mesas, lista_mensajes),
        "mensajes": lista_mensajes,
    }
