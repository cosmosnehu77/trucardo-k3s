import io
import ipaddress
import json
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from despliegue.manifiestos import main, manifiestos, texto_clientes
from nodo import config
from tests.test_config import _entorno

CLUSTER_TRES = "1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603"
IMAGEN = "trucardo:local"
OBSERVABILIDAD_ESPERADA = {
    "jaeger": ("jaegertracing/jaeger:2.23.0", "10.43.0.100"),
    "collector": ("otel/opentelemetry-collector:0.165.0", "10.43.0.99"),
    "prometheus": ("prom/prometheus:v3.16.0", "10.43.0.98"),
    "loki": ("grafana/loki:3.6.22", "10.43.0.97"),
    "grafana": ("grafana/grafana:13.3.2", "10.43.0.96"),
}
_COMPOSE = Path(__file__).resolve().parent.parent / "docker-compose.yml"


def _por_tipo(objetos, kind):
    return [obj for obj in objetos if obj["kind"] == kind]


def _por_nombre(objetos, kind):
    return {obj["metadata"]["name"]: obj for obj in _por_tipo(objetos, kind)}


def _imagenes_compose():
    imagenes = {}
    en_services = False
    servicio = None
    for linea in _COMPOSE.read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        if not linea.startswith(" "):
            en_services = linea.strip() == "services:"
            servicio = None
            continue
        if not en_services:
            continue
        coincide_servicio = re.match(r"^  ([a-z0-9_-]+):\s*$", linea)
        if coincide_servicio:
            servicio = coincide_servicio.group(1)
            continue
        coincide_imagen = re.match(r"^    image:\s*(\S+)", linea)
        if servicio and coincide_imagen:
            imagenes[servicio] = coincide_imagen.group(1)
    return imagenes


def test_un_deployment_y_un_service_por_nodo_ordenados_por_id():
    desordenado = "3@nodo3:9503:9603,1@nodo1:9501:9601,2@nodo2:9502:9602"
    objetos = manifiestos(desordenado, IMAGEN)
    deployments = _por_tipo(objetos, "Deployment")
    services = _por_tipo(objetos, "Service")

    assert len(objetos) == 6
    assert [d["metadata"]["name"] for d in deployments] == [
        "trucardo-nodo1",
        "trucardo-nodo2",
        "trucardo-nodo3",
    ]
    assert [s["metadata"]["name"] for s in services] == ["nodo1", "nodo2", "nodo3"]
    for i, d in enumerate(deployments, start=1):
        etiquetas = {"app": "trucardo", "nodo": str(i)}
        assert d["apiVersion"] == "apps/v1"
        assert d["metadata"]["labels"] == etiquetas
        assert d["spec"]["selector"] == {"matchLabels": etiquetas}
        assert d["spec"]["template"]["metadata"]["labels"] == etiquetas


def test_deployment_usa_recreate_y_una_replica():
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    for d in deployments:
        assert d["spec"]["replicas"] == 1
        assert d["spec"]["strategy"] == {"type": "Recreate"}


def test_contenedor_tiene_comando_imagen_politica_y_puertos():
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    for i, d in enumerate(deployments, start=1):
        contenedores = d["spec"]["template"]["spec"]["containers"]
        assert len(contenedores) == 1
        c = contenedores[0]
        assert c["name"] == "nodo"
        assert c["image"] == IMAGEN
        assert c["imagePullPolicy"] == "IfNotPresent"
        assert c["command"] == ["python", "-m", "nodo.servidor", str(i)]
        assert c["ports"] == [
            {"name": "pyro", "containerPort": 9500 + i},
            {"name": "cluster", "containerPort": 9600 + i},
        ]


def test_trucardo_nodos_en_entorno_es_identico_a_la_entrada():
    entrada = "1@nodo1:9501:9601, 2@nodo2:9502:9602"
    deployments = _por_tipo(manifiestos(entrada, IMAGEN), "Deployment")

    assert len(deployments) == 2
    for d in deployments:
        env = d["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {"name": "TRUCARDO_NODOS", "value": entrada} in env


def test_la_probe_apunta_al_puerto_del_cluster():
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    for i, d in enumerate(deployments, start=1):
        probe = d["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]
        assert probe["tcpSocket"] == {"port": 9600 + i}


def test_la_probe_detecta_despues_que_trucardo():
    original = config.TIMEOUT_CAIDO
    try:
        for timeout in (0.5, 3.0, 10.0, 47.3):
            config.TIMEOUT_CAIDO = timeout
            deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")
            for d in deployments:
                probe = d["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]
                periodo = probe["periodSeconds"]
                fallas = probe["failureThreshold"]
                assert isinstance(periodo, int) and periodo >= 1
                assert isinstance(fallas, int) and fallas >= 1
                assert periodo * fallas > timeout
    finally:
        config.TIMEOUT_CAIDO = original


def test_las_tolerancias_son_de_10_segundos():
    esperadas = {
        "node.kubernetes.io/unreachable",
        "node.kubernetes.io/not-ready",
    }
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    for d in deployments:
        tolerancias = d["spec"]["template"]["spec"]["tolerations"]
        assert len(tolerancias) == 2
        assert {t["key"] for t in tolerancias} == esperadas
        for t in tolerancias:
            assert t == {
                "key": t["key"],
                "operator": "Exists",
                "effect": "NoExecute",
                "tolerationSeconds": 10,
            }


def test_la_anti_afinidad_es_preferida():
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    for d in deployments:
        anti = d["spec"]["template"]["spec"]["affinity"]["podAntiAffinity"]
        assert "requiredDuringSchedulingIgnoredDuringExecution" not in anti
        reglas = anti["preferredDuringSchedulingIgnoredDuringExecution"]
        assert len(reglas) == 1
        assert 1 <= reglas[0]["weight"] <= 100
        termino = reglas[0]["podAffinityTerm"]
        assert termino["labelSelector"] == {"matchLabels": {"app": "trucardo"}}
        assert termino["topologyKey"] == "kubernetes.io/hostname"


def test_cada_nodo_tiene_su_volumen_hostpath():
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    rutas = []
    for i, d in enumerate(deployments, start=1):
        volumenes = d["spec"]["template"]["spec"]["volumes"]
        assert len(volumenes) == 1
        assert volumenes[0]["hostPath"] == {
            "path": f"/var/lib/trucardo/nodo{i}",
            "type": "DirectoryOrCreate",
        }
        rutas.append(volumenes[0]["hostPath"]["path"])
    assert len(set(rutas)) == 3


def test_el_punto_de_montaje_y_trucardo_datos_coinciden():
    deployments = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")

    assert len(deployments) == 3
    for d in deployments:
        pod = d["spec"]["template"]["spec"]
        volumenes = {v["name"] for v in pod["volumes"]}
        contenedor = pod["containers"][0]
        montajes = contenedor["volumeMounts"]
        assert len(montajes) == 1
        montaje = montajes[0]
        assert montaje["name"] in volumenes

        entorno = {e["name"]: e["value"] for e in contenedor["env"]}
        assert "TRUCARDO_DATOS" in entorno
        assert montaje["mountPath"] == entorno["TRUCARDO_DATOS"]
        assert montaje["mountPath"].startswith("/")


def test_no_hay_ningun_pvc():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN)

    assert _por_tipo(objetos, "PersistentVolumeClaim") == []
    for d in _por_tipo(objetos, "Deployment"):
        for volumen in d["spec"]["template"]["spec"]["volumes"]:
            assert "persistentVolumeClaim" not in volumen


def test_service_usa_host_y_selector():
    services = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Service")

    assert len(services) == 3
    for i, s in enumerate(services, start=1):
        assert s["apiVersion"] == "v1"
        assert s["metadata"]["name"] == f"nodo{i}"
        assert s["spec"]["selector"] == {"app": "trucardo", "nodo": str(i)}


def test_cada_service_tiene_una_cluster_ip_fija_distinta_y_en_la_banda_baja():
    banda_baja = ipaddress.ip_network("10.43.0.0/24")
    services = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Service")

    assert len(services) == 3
    ips = [s["spec"]["clusterIP"] for s in services]
    assert ips == ["10.43.0.101", "10.43.0.102", "10.43.0.103"]
    assert len(set(ips)) == 3
    for ip in ips:
        assert ipaddress.ip_address(ip) in banda_baja


def test_los_host_aliases_tienen_todos_los_nodos_con_la_ip_de_su_service():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN)
    deployments = _por_tipo(objetos, "Deployment")
    services = _por_tipo(objetos, "Service")

    assert len(deployments) == 3
    for d in deployments:
        aliases = d["spec"]["template"]["spec"]["hostAliases"]
        assert aliases == [
            {"ip": s["spec"]["clusterIP"], "hostnames": [s["metadata"]["name"]]}
            for s in services
        ]


def test_un_id_que_no_entra_en_la_banda_da_error():
    for entrada in ("200@nodo200:9501:9601", "156@nodo156:9501:9601"):
        try:
            manifiestos(entrada, IMAGEN)
        except ValueError:
            continue
        raise AssertionError(f"entrada {entrada!r} tendria que haber dado ValueError")

    with _entorno(TRUCARDO_NODOS="200@nodo200:9501:9601"):
        try:
            main(["--imagen", IMAGEN])
        except SystemExit as salida:
            assert "200" in str(salida.code)
        else:
            raise AssertionError("un id fuera de la banda tiene que cortar el CLI con un error")


def test_los_puertos_externos_siguen_la_regla_y_caen_en_el_rango():
    services = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Service")

    assert len(services) == 3
    for i, s in enumerate(services, start=1):
        assert s["spec"]["type"] == "NodePort"
        assert s["spec"]["ports"] == [
            {"name": "pyro", "port": 9500 + i, "targetPort": 9500 + i, "nodePort": 30500 + i},
            {"name": "cluster", "port": 9600 + i, "targetPort": 9600 + i, "nodePort": 30600 + i},
        ]
        for puerto in s["spec"]["ports"]:
            assert 30000 <= puerto["nodePort"] <= 32767


def test_el_valor_para_clientes_ida_y_vuelta():
    texto = texto_clientes(CLUSTER_TRES, "192.168.0.11")
    cluster = config.nodos(texto)

    assert set(cluster) == set(config.nodos(CLUSTER_TRES))
    for id_nodo in (1, 2, 3):
        nodo = cluster[id_nodo]
        assert nodo.host == "192.168.0.11"
        assert nodo.puerto_pyro == 30500 + id_nodo
        assert nodo.puerto_cluster == 30600 + id_nodo


def test_un_puerto_interno_fuera_de_rango_da_error():
    for entrada in ("1@nodo1:12000:9601", "1@nodo1:8000:9601"):
        for llamada in (
            lambda e=entrada: manifiestos(e, IMAGEN),
            lambda e=entrada: texto_clientes(e, "192.168.0.11"),
        ):
            try:
                llamada()
            except ValueError:
                continue
            raise AssertionError(f"entrada {entrada!r} tendria que haber dado ValueError")


def test_host_invalido_da_value_error():
    for host in ("Nodo_1", "10.0.0.1", "1nodo", "nodo-", "a" * 64):
        try:
            manifiestos(f"1@{host}:9501:9601", IMAGEN)
        except ValueError:
            continue
        raise AssertionError(f"host {host!r} tendria que haber dado ValueError")


def test_host_valido_en_los_bordes():
    for host in ("a", "nodo-1", "a" * 63):
        assert _por_tipo(manifiestos(f"1@{host}:9501:9601", IMAGEN), "Service")[0]["metadata"]["name"] == host


def test_cli_con_host_invalido_termina_con_error():
    with _entorno(TRUCARDO_NODOS="1@Nodo_1:9501:9601"):
        try:
            main(["--imagen", IMAGEN])
        except SystemExit as salida:
            assert "Nodo_1" in str(salida.code)
        else:
            raise AssertionError("un host invalido tiene que cortar el CLI con un error")


def test_cli_imprime_json_valido_con_variable_de_entorno():
    buffer = io.StringIO()
    with _entorno(TRUCARDO_NODOS=CLUSTER_TRES):
        with redirect_stdout(buffer):
            main(["--imagen", IMAGEN])

    datos = json.loads(buffer.getvalue())
    assert datos == {
        "apiVersion": "v1",
        "kind": "List",
        "items": manifiestos(CLUSTER_TRES, IMAGEN),
    }


def test_cli_sin_variable_usa_default_de_config():
    buffer = io.StringIO()
    with _entorno(TRUCARDO_NODOS=None):
        with redirect_stdout(buffer):
            main(["--imagen", IMAGEN])

    datos = json.loads(buffer.getvalue())
    assert datos["apiVersion"] == "v1"
    assert datos["kind"] == "List"
    assert datos["items"] == manifiestos(config.NODOS_POR_DEFECTO, IMAGEN)


def test_cli_clientes_imprime_el_valor():
    buffer = io.StringIO()
    with _entorno(TRUCARDO_NODOS=CLUSTER_TRES):
        with redirect_stdout(buffer):
            main(["--clientes", "192.168.0.11"])

    assert buffer.getvalue() == texto_clientes(CLUSTER_TRES, "192.168.0.11") + "\n"


def test_cli_pide_imagen_o_clientes():
    for argv in ([], ["--imagen", IMAGEN, "--clientes", "1.2.3.4"]):
        with redirect_stderr(io.StringIO()):
            try:
                main(argv)
            except SystemExit as salida:
                assert salida.code != 0
            else:
                raise AssertionError(f"argv {argv!r} tendria que haber terminado con SystemExit")


def test_sin_telemetria_no_aparece_observabilidad_ni_variables_otel():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN)

    assert objetos == manifiestos(CLUSTER_TRES, IMAGEN, telemetria=False)
    assert _por_tipo(objetos, "ConfigMap") == []
    assert all(obj["metadata"]["name"] not in OBSERVABILIDAD_ESPERADA for obj in objetos)
    for d in _por_tipo(objetos, "Deployment"):
        pod = d["spec"]["template"]["spec"]
        for alias in pod["hostAliases"]:
            assert not (set(alias["hostnames"]) & set(OBSERVABILIDAD_ESPERADA))
        for c in pod["containers"]:
            for var in c["env"]:
                assert not var["name"].startswith(("OTEL_", "K8S_"))


def test_con_telemetria_agrega_pila_de_observabilidad_con_imagenes_e_ips_fijas():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True)
    deployments = _por_nombre(objetos, "Deployment")
    services = _por_nombre(objetos, "Service")
    configmaps = _por_nombre(objetos, "ConfigMap")

    for nombre, (imagen, ip) in OBSERVABILIDAD_ESPERADA.items():
        assert nombre in deployments
        assert nombre in services
        dep = deployments[nombre]
        svc = services[nombre]
        assert dep["apiVersion"] == "apps/v1"
        assert dep["metadata"] == {"name": nombre, "labels": {"app": nombre}}
        assert dep["spec"]["replicas"] == 1
        assert dep["spec"]["selector"] == {"matchLabels": {"app": nombre}}
        assert dep["spec"]["template"]["metadata"]["labels"] == {"app": nombre}
        contenedores = dep["spec"]["template"]["spec"]["containers"]
        assert len(contenedores) == 1
        assert contenedores[0]["name"] == nombre
        assert contenedores[0]["image"] == imagen
        assert contenedores[0]["imagePullPolicy"] == "IfNotPresent"
        assert svc["apiVersion"] == "v1"
        assert svc["metadata"] == {"name": nombre, "labels": {"app": nombre}}
        assert svc["spec"]["clusterIP"] == ip
        assert svc["spec"]["selector"] == {"app": nombre}

    assert set(configmaps) == {"collector", "prometheus", "grafana"}
    assert set(configmaps["collector"]["data"]) == {"collector.json"}
    assert set(configmaps["prometheus"]["data"]) == {"prometheus.json"}
    assert set(configmaps["grafana"]["data"]) == {
        "fuentes.yaml",
        "tableros.yaml",
        "tablero-trucardo.json",
    }

    for nombre in ("collector", "prometheus", "grafana"):
        pos_cm = objetos.index(configmaps[nombre])
        pos_dep = objetos.index(deployments[nombre])
        assert pos_cm < pos_dep

    c_collector = deployments["collector"]["spec"]["template"]["spec"]["containers"][0]
    assert c_collector["args"] == ["--config=/etc/otelcol/collector.json"]
    assert any(m["mountPath"] == "/etc/otelcol" for m in c_collector["volumeMounts"])

    c_prometheus = deployments["prometheus"]["spec"]["template"]["spec"]["containers"][0]
    assert c_prometheus["args"] == [
        "--config.file=/etc/prometheus/prometheus.json",
        "--web.enable-otlp-receiver",
    ]
    assert any(m["mountPath"] == "/etc/prometheus" for m in c_prometheus["volumeMounts"])

    c_grafana = deployments["grafana"]["spec"]["template"]["spec"]["containers"][0]
    montajes_grafana = {(m["mountPath"], m.get("subPath")) for m in c_grafana["volumeMounts"]}
    assert montajes_grafana == {
        ("/etc/grafana/provisioning/datasources/fuentes.yaml", "fuentes.yaml"),
        ("/etc/grafana/provisioning/dashboards/tableros.yaml", "tableros.yaml"),
        ("/etc/grafana/tableros/tablero-trucardo.json", "tablero-trucardo.json"),
    }
    env_grafana = {e["name"]: e["value"] for e in c_grafana["env"]}
    assert env_grafana == {
        "GF_AUTH_ANONYMOUS_ENABLED": "true",
        "GF_AUTH_ANONYMOUS_ORG_ROLE": "Admin",
        "GF_AUTH_DISABLE_LOGIN_FORM": "true",
    }


def test_con_telemetria_los_nodeports_siguen_d6_y_loki_es_cluster_ip():
    services = _por_nombre(manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True), "Service")

    assert services["jaeger"]["spec"]["type"] == "NodePort"
    assert services["jaeger"]["spec"]["ports"] == [
        {"name": "interfaz", "port": 9686, "targetPort": 16686, "nodePort": 30686},
        {"name": "consulta", "port": 16686, "targetPort": 16686},
        {"name": "otlp", "port": 4318, "targetPort": 4318},
    ]

    assert services["collector"]["spec"]["type"] == "NodePort"
    puertos_collector = services["collector"]["spec"]["ports"]
    assert {"port": 4318, "targetPort": 4318} in [
        {"port": p["port"], "targetPort": p["targetPort"]} for p in puertos_collector
    ]
    externos_collector = [p for p in puertos_collector if "nodePort" in p]
    assert len(externos_collector) == 1
    assert externos_collector[0]["port"] == 9318
    assert externos_collector[0]["targetPort"] == 4318
    assert externos_collector[0]["nodePort"] == 30318

    assert services["prometheus"]["spec"]["type"] == "NodePort"
    puertos_prom = services["prometheus"]["spec"]["ports"]
    assert len(puertos_prom) == 1
    assert puertos_prom[0]["port"] == 9090
    assert puertos_prom[0]["targetPort"] == 9090
    assert puertos_prom[0]["nodePort"] == 30090

    assert services["loki"]["spec"]["type"] == "ClusterIP"
    puertos_loki = services["loki"]["spec"]["ports"]
    assert len(puertos_loki) == 1
    assert puertos_loki[0]["port"] == 3100
    assert puertos_loki[0]["targetPort"] == 3100
    assert all("nodePort" not in p for p in puertos_loki)

    assert services["grafana"]["spec"]["type"] == "NodePort"
    puertos_grafana = services["grafana"]["spec"]["ports"]
    assert len(puertos_grafana) == 1
    assert puertos_grafana[0]["port"] == 9300
    assert puertos_grafana[0]["targetPort"] == 3000
    assert puertos_grafana[0]["nodePort"] == 30300


def test_con_telemetria_configmap_collector_tiene_las_tres_canalizaciones():
    configmaps = _por_nombre(manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True), "ConfigMap")
    cfg = json.loads(configmaps["collector"]["data"]["collector.json"])
    canalizaciones = cfg["service"]["pipelines"]
    exporters = cfg["exporters"]

    assert set(canalizaciones) == {"traces", "metrics", "logs"}
    destinos = {
        "traces": "jaeger",
        "metrics": "prometheus",
        "logs": "loki",
    }
    for senal, destino in destinos.items():
        nombres_exp = canalizaciones[senal]["exporters"]
        assert any(destino in exporters[nombre]["endpoint"] for nombre in nombres_exp)


def test_con_telemetria_los_nodos_apuntan_al_collector_y_declaran_downward_api():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True)
    deployments_nodos = [
        d for d in _por_tipo(objetos, "Deployment") if d["metadata"]["name"].startswith("trucardo-nodo")
    ]

    assert len(deployments_nodos) == 3
    for d in deployments_nodos:
        env = d["spec"]["template"]["spec"]["containers"][0]["env"]
        assert env[-4:] == [
            {"name": "K8S_POD_NAME", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}},
            {"name": "K8S_NODE_NAME", "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}}},
            {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": "http://collector:4318"},
            {
                "name": "OTEL_RESOURCE_ATTRIBUTES",
                "value": "k8s.pod.name=$(K8S_POD_NAME),k8s.node.name=$(K8S_NODE_NAME)",
            },
        ]


def test_la_observabilidad_tiene_las_mismas_tolerancias_que_los_nodos():
    deployments = _por_nombre(manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True), "Deployment")
    de_los_nodos = deployments["trucardo-nodo1"]["spec"]["template"]["spec"]["tolerations"]

    for nombre in OBSERVABILIDAD_ESPERADA:
        assert deployments[nombre]["spec"]["template"]["spec"]["tolerations"] == de_los_nodos


def test_con_telemetria_todos_los_pods_tienen_host_aliases_de_observabilidad():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True)
    deployments = _por_tipo(objetos, "Deployment")
    services = _por_nombre(objetos, "Service")

    aliases_obs = {
        (services[nombre]["spec"]["clusterIP"], nombre) for nombre in OBSERVABILIDAD_ESPERADA
    }
    aliases_nodos = {
        (services[f"nodo{i}"]["spec"]["clusterIP"], f"nodo{i}") for i in (1, 2, 3)
    }

    assert len(deployments) == 3 + len(OBSERVABILIDAD_ESPERADA)
    for d in deployments:
        aliases = {
            (a["ip"], host)
            for a in d["spec"]["template"]["spec"]["hostAliases"]
            for host in a["hostnames"]
        }
        if d["metadata"]["name"].startswith("trucardo-nodo"):
            assert aliases == aliases_nodos | aliases_obs
        else:
            assert aliases == aliases_obs


def test_las_imagenes_coinciden_con_docker_compose():
    from despliegue.manifiestos import (
        IMAGEN_COLLECTOR,
        IMAGEN_GRAFANA,
        IMAGEN_JAEGER,
        IMAGEN_LOKI,
        IMAGEN_PROMETHEUS,
    )

    esperadas = {
        "jaeger": IMAGEN_JAEGER,
        "collector": IMAGEN_COLLECTOR,
        "prometheus": IMAGEN_PROMETHEUS,
        "loki": IMAGEN_LOKI,
        "grafana": IMAGEN_GRAFANA,
    }
    en_compose = _imagenes_compose()
    deployments = _por_nombre(manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True), "Deployment")

    for nombre, imagen in esperadas.items():
        assert en_compose[nombre] == imagen
        assert deployments[nombre]["spec"]["template"]["spec"]["containers"][0]["image"] == imagen


def test_cli_con_telemetria_imprime_json_con_observabilidad():
    buffer = io.StringIO()
    with _entorno(TRUCARDO_NODOS=CLUSTER_TRES):
        with redirect_stdout(buffer):
            main(["--imagen", IMAGEN, "--telemetria"])

    datos = json.loads(buffer.getvalue())
    assert datos == {
        "apiVersion": "v1",
        "kind": "List",
        "items": manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True),
    }
    nombres = {item["metadata"]["name"] for item in datos["items"]}
    assert set(OBSERVABILIDAD_ESPERADA) <= nombres


def test_cli_clientes_con_telemetria_termina_con_error():
    err = io.StringIO()
    with redirect_stderr(err):
        try:
            main(["--clientes", "192.168.0.11", "--telemetria"])
        except SystemExit as salida:
            assert salida.code != 0
        else:
            raise AssertionError("--clientes con --telemetria tendria que haber terminado con SystemExit")
    linea_error = err.getvalue().strip().splitlines()[-1]
    assert "--telemetria" in linea_error and "--imagen" in linea_error


def test_con_longhorn_emite_un_pvc_por_nodo_y_ningun_hostpath():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, almacenamiento="longhorn")
    pvcs = _por_tipo(objetos, "PersistentVolumeClaim")
    deployments = _por_tipo(objetos, "Deployment")

    assert len(pvcs) == 3
    assert len(deployments) == 3
    for i, (pvc, d) in enumerate(zip(pvcs, deployments), start=1):
        nombre_pvc = f"datos-nodo{i}"
        assert pvc["apiVersion"] == "v1"
        assert pvc["metadata"] == {
            "name": nombre_pvc,
            "labels": {"app": "trucardo", "nodo": str(i)},
        }
        assert pvc["spec"] == {
            "accessModes": ["ReadWriteOnce"],
            "storageClassName": "longhorn",
            "resources": {"requests": {"storage": "1Gi"}},
        }
        assert objetos.index(pvc) < objetos.index(d)

        volumenes = d["spec"]["template"]["spec"]["volumes"]
        assert volumenes == [
            {"name": "datos", "persistentVolumeClaim": {"claimName": nombre_pvc}}
        ]
        assert all("hostPath" not in v for v in volumenes)


def test_con_longhorn_el_punto_de_montaje_es_el_mismo_que_con_hostpath():
    deps_hostpath = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Deployment")
    deps_longhorn = _por_tipo(
        manifiestos(CLUSTER_TRES, IMAGEN, almacenamiento="longhorn"), "Deployment"
    )

    assert len(deps_longhorn) == len(deps_hostpath) == 3
    for dh, dl in zip(deps_hostpath, deps_longhorn):
        ch = dh["spec"]["template"]["spec"]["containers"][0]
        cl = dl["spec"]["template"]["spec"]["containers"][0]
        assert cl["volumeMounts"] == ch["volumeMounts"]
        env_h = {e["name"]: e["value"] for e in ch["env"]}
        env_l = {e["name"]: e["value"] for e in cl["env"]}
        assert env_l["TRUCARDO_DATOS"] == env_h["TRUCARDO_DATOS"]
        assert cl["volumeMounts"][0]["mountPath"] == env_l["TRUCARDO_DATOS"]


def test_con_longhorn_y_telemetria_combina_pvc_y_observabilidad():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True, almacenamiento="longhorn")
    pvcs = _por_tipo(objetos, "PersistentVolumeClaim")
    deployments = _por_tipo(objetos, "Deployment")

    assert len(pvcs) == 3
    assert len(deployments) == 3 + len(OBSERVABILIDAD_ESPERADA)
    assert set(OBSERVABILIDAD_ESPERADA) <= {d["metadata"]["name"] for d in deployments}
    for d in deployments:
        for volumen in d["spec"]["template"]["spec"].get("volumes", []):
            assert "hostPath" not in volumen


def test_sin_almacenamiento_la_salida_es_identica_a_hostpath():
    assert manifiestos(CLUSTER_TRES, IMAGEN) == manifiestos(
        CLUSTER_TRES, IMAGEN, almacenamiento="hostpath"
    )
    assert manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True) == manifiestos(
        CLUSTER_TRES, IMAGEN, telemetria=True, almacenamiento="hostpath"
    )

    sin_opcion = io.StringIO()
    con_hostpath = io.StringIO()
    with _entorno(TRUCARDO_NODOS=CLUSTER_TRES):
        with redirect_stdout(sin_opcion):
            main(["--imagen", IMAGEN])
        with redirect_stdout(con_hostpath):
            main(["--imagen", IMAGEN, "--almacenamiento", "hostpath"])
    assert sin_opcion.getvalue() == con_hostpath.getvalue()


def test_cli_con_almacenamiento_longhorn_imprime_json_con_pvcs():
    buffer = io.StringIO()
    with _entorno(TRUCARDO_NODOS=CLUSTER_TRES):
        with redirect_stdout(buffer):
            main(["--imagen", IMAGEN, "--almacenamiento", "longhorn"])

    datos = json.loads(buffer.getvalue())
    assert datos == {
        "apiVersion": "v1",
        "kind": "List",
        "items": manifiestos(CLUSTER_TRES, IMAGEN, almacenamiento="longhorn"),
    }


def test_almacenamiento_desconocido_da_error():
    try:
        manifiestos(CLUSTER_TRES, IMAGEN, almacenamiento="nfs")
    except ValueError:
        pass
    else:
        raise AssertionError("almacenamiento desconocido tendria que haber dado ValueError")

    err = io.StringIO()
    with redirect_stderr(err):
        try:
            main(["--imagen", IMAGEN, "--almacenamiento", "nfs"])
        except SystemExit as salida:
            assert salida.code != 0
        else:
            raise AssertionError("--almacenamiento nfs tendria que haber terminado con SystemExit")
    linea_error = err.getvalue().strip().splitlines()[-1]
    assert "hostpath" in linea_error and "longhorn" in linea_error


def test_cli_clientes_con_almacenamiento_termina_con_error():
    for valor in ("hostpath", "longhorn"):
        err = io.StringIO()
        with redirect_stderr(err):
            try:
                main(["--clientes", "192.168.0.11", "--almacenamiento", valor])
            except SystemExit as salida:
                assert salida.code != 0
            else:
                raise AssertionError(
                    f"--clientes con --almacenamiento {valor} tendria que haber terminado con SystemExit"
                )
        linea_error = err.getvalue().strip().splitlines()[-1]
        assert "--almacenamiento" in linea_error and "--imagen" in linea_error


def test_sin_visor_no_hay_objetos_de_visor_ni_rbac():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True)

    assert "visor" not in _por_nombre(objetos, "Deployment")
    assert not _por_tipo(objetos, "ServiceAccount")
    assert not _por_tipo(objetos, "ClusterRole")


def test_el_visor_lee_nodos_y_pods_con_una_cuenta_de_solo_lectura():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, visor=True)

    cuenta = _por_nombre(objetos, "ServiceAccount")["visor"]
    rol = _por_nombre(objetos, "ClusterRole")["trucardo-visor"]
    enlace = _por_nombre(objetos, "ClusterRoleBinding")["trucardo-visor"]
    assert rol["rules"] == [{"apiGroups": [""], "resources": ["nodes", "pods"],
                             "verbs": ["get", "list"]}]
    assert enlace["roleRef"]["name"] == "trucardo-visor"
    assert enlace["subjects"][0]["name"] == cuenta["metadata"]["name"]
    assert enlace["subjects"][0]["namespace"] == "default"


def test_el_visor_corre_en_la_imagen_de_trucardo_y_conoce_a_los_nodos():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, visor=True)

    pod = _por_nombre(objetos, "Deployment")["visor"]["spec"]["template"]["spec"]
    contenedor = pod["containers"][0]
    entorno = {e["name"]: e.get("value") for e in contenedor["env"]}
    assert pod["serviceAccountName"] == "visor"
    assert contenedor["image"] == IMAGEN
    assert contenedor["command"] == ["python", "-m", "visor.servidor"]
    assert entorno["TRUCARDO_NODOS"] == CLUSTER_TRES
    assert "VISOR_JAEGER" not in entorno
    assert {a["hostnames"][0] for a in pod["hostAliases"]} == {"nodo1", "nodo2", "nodo3"}
    assert pod["tolerations"] == _por_nombre(objetos, "Deployment")["trucardo-nodo1"]["spec"]["template"]["spec"]["tolerations"]


def test_el_visor_se_publica_por_nodeport_con_la_regla_de_puertos():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, visor=True)

    service = _por_nombre(objetos, "Service")["visor"]
    assert service["spec"]["type"] == "NodePort"
    assert service["spec"]["clusterIP"] == "10.43.0.95"
    assert service["spec"]["ports"] == [
        {"name": "web", "port": 9808, "targetPort": 9808, "nodePort": 30808}
    ]


def test_con_telemetria_el_visor_lee_las_trazas_de_jaeger():
    objetos = manifiestos(CLUSTER_TRES, IMAGEN, telemetria=True, visor=True)

    pod = _por_nombre(objetos, "Deployment")["visor"]["spec"]["template"]["spec"]
    entorno = {e["name"]: e.get("value") for e in pod["containers"][0]["env"]}
    assert entorno["VISOR_JAEGER"] == "http://jaeger:16686"
    assert "jaeger" in {a["hostnames"][0] for a in pod["hostAliases"]}


def test_cli_con_visor_imprime_json_con_el_visor():
    with _entorno(TRUCARDO_NODOS=CLUSTER_TRES):
        salida = io.StringIO()
        with redirect_stdout(salida):
            main(["--imagen", IMAGEN, "--visor"])
    nombres = {obj["metadata"]["name"] for obj in json.loads(salida.getvalue())["items"]}
    assert {"visor", "trucardo-visor"} <= nombres


def test_cli_clientes_con_visor_termina_con_error():
    with redirect_stderr(io.StringIO()):
        try:
            main(["--clientes", "192.168.0.11", "--visor"])
        except SystemExit as salida:
            assert salida.code != 0
        else:
            raise AssertionError("tenía que terminar con error")
