import io
import ipaddress
import json
from contextlib import redirect_stderr, redirect_stdout

from despliegue.manifiestos import main, manifiestos, texto_clientes
from nodo import config
from tests.test_config import _entorno

CLUSTER_TRES = "1@nodo1:9501:9601,2@nodo2:9502:9602,3@nodo3:9503:9603"
IMAGEN = "trucardo:local"


def _por_tipo(objetos, kind):
    return [obj for obj in objetos if obj["kind"] == kind]


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
