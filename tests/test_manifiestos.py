import io
import json
from contextlib import redirect_stdout

from despliegue.manifiestos import main, manifiestos
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


def test_service_usa_host_selector_y_ambos_puertos():
    services = _por_tipo(manifiestos(CLUSTER_TRES, IMAGEN), "Service")

    assert len(services) == 3
    for i, s in enumerate(services, start=1):
        assert s["apiVersion"] == "v1"
        assert s["metadata"]["name"] == f"nodo{i}"
        assert s["spec"]["selector"] == {"app": "trucardo", "nodo": str(i)}
        assert s["spec"]["ports"] == [
            {"name": "pyro", "port": 9500 + i, "targetPort": 9500 + i},
            {"name": "cluster", "port": 9600 + i, "targetPort": 9600 + i},
        ]


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
