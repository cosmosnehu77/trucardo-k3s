from visor import estado


def _nodo_k8s(nombre, ip, lista=True, servidor=False):
    etiquetas = {"kubernetes.io/hostname": nombre}
    if servidor:
        etiquetas["node-role.kubernetes.io/control-plane"] = "true"
    return {
        "metadata": {"name": nombre, "labels": etiquetas},
        "status": {
            "addresses": [{"type": "InternalIP", "address": ip},
                          {"type": "Hostname", "address": nombre}],
            "conditions": [{"type": "Ready", "status": "True" if lista else "Unknown"}],
        },
    }


def _pod_k8s(nombre, etiquetas, maquina, fase="Running", listo=True, reinicios=0, borrandose=False):
    metadata = {"name": nombre, "labels": etiquetas}
    if borrandose:
        metadata["deletionTimestamp"] = "2026-11-25T10:00:00Z"
    return {
        "metadata": metadata,
        "spec": {"nodeName": maquina},
        "status": {
            "phase": fase,
            "podIP": "10.42.0.7",
            "conditions": [{"type": "Ready", "status": "True" if listo else "False"}],
            "containerStatuses": [{"ready": listo, "restartCount": reinicios}],
        },
    }


def _respuesta(rol, primario, epoca, ultimo_seq, mesas=()):
    return {"rol": rol, "primario": primario, "soy_yo": rol == "primario",
            "epoca": epoca, "ultimo_seq": ultimo_seq, "reloj": 40, "mesas": list(mesas)}


def _mesa(id_mesa, jugadores, estado_mesa="en_juego"):
    return {"id_mesa": id_mesa, "jugadores": jugadores, "estado": estado_mesa,
            "marcador": [3, 5], "numero_mano": 2, "puntos_para_ganar": 15,
            "creada_en": 1, "ganador": None}


def _span(servicio, id_span, padre, nombre, inicio_ns):
    return servicio, {"traceId": "t1", "spanId": id_span, "parentSpanId": padre,
                      "name": nombre, "startTimeUnixNano": str(inicio_ns)}


def _trazas(*spans):
    por_servicio = {}
    for servicio, span in spans:
        por_servicio.setdefault(servicio, []).append(span)
    return {"result": {"resourceSpans": [
        {"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": servicio}}]},
         "scopeSpans": [{"spans": lista}]}
        for servicio, lista in por_servicio.items()
    ]}}


def test_maquinas_pone_primero_al_servidor_y_marca_las_caidas():
    nodos = [_nodo_k8s("maquina3", "172.30.0.13", lista=False),
             _nodo_k8s("maquina2", "172.30.0.12"),
             _nodo_k8s("maquina1", "172.30.0.11", servidor=True)]

    assert estado.maquinas(nodos) == [
        {"nombre": "maquina1", "ip": "172.30.0.11", "lista": True, "rol": "servidor"},
        {"nombre": "maquina2", "ip": "172.30.0.12", "lista": True, "rol": "agente"},
        {"nombre": "maquina3", "ip": "172.30.0.13", "lista": False, "rol": "agente"},
    ]


def test_componente_reconoce_nodos_observabilidad_y_visor_e_ignora_el_resto():
    assert estado.componente({"app": "trucardo", "nodo": "2"}) == "nodo2"
    assert estado.componente({"app": "jaeger"}) == "jaeger"
    assert estado.componente({"app": "visor"}) == "visor"
    assert estado.componente({"k8s-app": "kube-dns"}) is None


def test_pods_resume_maquina_fase_listo_y_reinicios():
    lista = [_pod_k8s("trucardo-nodo1-abc", {"app": "trucardo", "nodo": "1"}, "maquina2", reinicios=2),
             _pod_k8s("trucardo-nodo3-viejo", {"app": "trucardo", "nodo": "3"}, "maquina1", borrandose=True),
             _pod_k8s("coredns-xyz", {"k8s-app": "kube-dns"}, "maquina1"),
             _pod_k8s("grafana-q", {"app": "grafana"}, "maquina3", fase="Pending", listo=False)]

    assert estado.pods(lista) == [
        {"nombre": "grafana-q", "componente": "grafana", "maquina": "maquina3",
         "fase": "Pending", "listo": False, "reinicios": 0, "ip": "10.42.0.7"},
        {"nombre": "trucardo-nodo1-abc", "componente": "nodo1", "maquina": "maquina2",
         "fase": "Running", "listo": True, "reinicios": 2, "ip": "10.42.0.7"},
        {"nombre": "trucardo-nodo3-viejo", "componente": "nodo3", "maquina": "maquina1",
         "fase": "Terminating", "listo": True, "reinicios": 0, "ip": "10.42.0.7"},
    ]


def test_nodos_trucardo_marca_a_los_que_no_responden():
    respuestas = {2: _respuesta("backup", 3, 4, 120), 1: None,
                  3: _respuesta("primario", 3, 4, 120)}

    assert estado.nodos_trucardo(respuestas) == [
        {"id": 1, "responde": False, "rol": None, "primario": None,
         "epoca": None, "ultimo_seq": None, "reloj": None},
        {"id": 2, "responde": True, "rol": "backup", "primario": 3,
         "epoca": 4, "ultimo_seq": 120, "reloj": 40},
        {"id": 3, "responde": True, "rol": "primario", "primario": 3,
         "epoca": 4, "ultimo_seq": 120, "reloj": 40},
    ]


def test_mesas_salen_del_primario_de_mayor_epoca():
    viejo = _respuesta("primario", 1, 3, 90, [_mesa("aaa", ["leo", None], "esperando_rival")])
    nuevo = _respuesta("primario", 2, 4, 95, [_mesa("aaa", ["leo", "beto"])])
    atrasado = _respuesta("backup", 2, 4, 80, [])

    assert estado.mesas({1: viejo, 2: nuevo, 3: atrasado}) == [
        {"id_mesa": "aaa", "jugadores": ["leo", "beto"], "estado": "en_juego",
         "marcador": [3, 5], "numero_mano": 2},
    ]


def test_mesas_sin_primario_usan_el_log_mas_adelantado():
    adelantado = _respuesta("backup", None, 4, 95, [_mesa("bbb", ["ana", "juan"])])
    atrasado = _respuesta("backup", None, 4, 80, [])

    assert [m["id_mesa"] for m in estado.mesas({1: atrasado, 2: adelantado, 3: None})] == ["bbb"]
    assert estado.mesas({1: None}) == []


def test_mensajes_son_los_spans_cuyo_padre_es_de_otro_servicio():
    trazas = _trazas(
        _span("trucardo-cliente-leo", "c1", "", "jugada jugar", 1_000_000_000),
        _span("trucardo-nodo3", "n3", "c1", "jugada jugar", 1_002_000_000),
        _span("trucardo-nodo3", "n3b", "n3", "aplicar", 1_003_000_000),
        _span("trucardo-nodo1", "r1", "n3", "replica", 1_004_000_000),
        _span("trucardo-nodo2", "r2", "n3", "replica", 1_005_000_000),
    )

    assert estado.mensajes([trazas]) == [
        {"ms": 1002, "de": "cliente-leo", "a": "nodo3", "tipo": "jugada jugar"},
        {"ms": 1004, "de": "nodo3", "a": "nodo1", "tipo": "replica"},
        {"ms": 1005, "de": "nodo3", "a": "nodo2", "tipo": "replica"},
    ]


def test_mensajes_no_repite_un_span_que_aparece_en_dos_consultas():
    trazas = _trazas(
        _span("trucardo-nodo2", "p", "", "eleccion", 5_000_000),
        _span("trucardo-nodo3", "d", "p", "desafio", 6_000_000),
    )

    assert len(estado.mensajes([trazas, trazas, None])) == 1


def test_clientes_junta_jugadores_de_las_mesas_y_de_las_trazas():
    mesas = [{"id_mesa": "aaa", "jugadores": ["leo", "beto"], "estado": "en_juego"},
             {"id_mesa": "bbb", "jugadores": ["ana", None], "estado": "esperando_rival"}]
    mensajes = [{"ms": 1, "de": "cliente-zoe", "a": "nodo3", "tipo": "jugada ver"}]

    assert estado.clientes(mesas, mensajes) == [
        {"nombre": "ana", "mesa": "bbb", "estado": "esperando_rival", "trazado": False},
        {"nombre": "beto", "mesa": "aaa", "estado": "en_juego", "trazado": False},
        {"nombre": "leo", "mesa": "aaa", "estado": "en_juego", "trazado": False},
        {"nombre": "zoe", "mesa": None, "estado": None, "trazado": True},
    ]


def test_armar_junta_todo_y_dice_si_hay_telemetria():
    instantanea = estado.armar(
        nodos_k8s=[_nodo_k8s("maquina1", "172.30.0.11", servidor=True)],
        pods_k8s=[_pod_k8s("trucardo-nodo1-a", {"app": "trucardo", "nodo": "1"}, "maquina1")],
        respuestas={1: _respuesta("primario", 1, 1, 7, [_mesa("aaa", ["leo", "beto"])])},
        trazas=None,
        hora=1700000000.5,
    )

    assert instantanea["hora"] == 1700000000.5
    assert instantanea["telemetria"] is False
    assert instantanea["maquinas"][0]["nombre"] == "maquina1"
    assert instantanea["pods"][0]["componente"] == "nodo1"
    assert instantanea["nodos"][0]["rol"] == "primario"
    assert [c["nombre"] for c in instantanea["clientes"]] == ["beto", "leo"]
    assert instantanea["mensajes"] == []


def test_si_jaeger_no_contesta_ninguna_consulta_no_hay_telemetria():
    instantanea = estado.armar(nodos_k8s=[], pods_k8s=[], respuestas={1: None},
                               trazas=[None, None], hora=1.0)

    assert instantanea["telemetria"] is False
    assert instantanea["mensajes"] == []


def test_un_pod_en_una_maquina_caida_no_esta_listo_aunque_su_contenedor_diga_que_si():
    pod = _pod_k8s("trucardo-nodo1-a", {"app": "trucardo", "nodo": "1"}, "maquina3")
    pod["status"]["conditions"] = [{"type": "Ready", "status": "False"}]

    assert estado.pods([pod])[0]["listo"] is False
