import argparse
import ipaddress
import json
import re
import sys

from nodo import config

_APP = "trucardo"

# Kubernetes exige etiquetas DNS-1035 (max 63 caracteres) como nombre de Service.
_NOMBRE_SERVICIO = re.compile(r"^[a-z]([-a-z0-9]*[a-z0-9])?$")
_LARGO_MAXIMO_HOST = 63

# Rango por defecto de NodePort en Kubernetes.
_NODEPORT_MIN = 30000
_NODEPORT_MAX = 32767
_DESPLAZAMIENTO_NODEPORT = 21000

# k3s asigna las clusterIP al azar en 10.43.0.0/16 y deja la banda baja (las primeras 256) para IPs fijas.
_BASE_IP_SERVICIO = ipaddress.ip_address("10.43.0.100")
_RED_IP_FIJAS = ipaddress.ip_network("10.43.0.0/24")

_PROBE_FALLAS = 3
_TOLERANCIA_SEGUNDOS = 10

_VOLUMEN_DATOS = "datos"
_DIRECTORIO_DATOS = "/datos"
_DATOS_EN_LA_MAQUINA = "/var/lib/trucardo"

IMAGEN_JAEGER = "jaegertracing/jaeger:2.23.0"
_NOMBRE_JAEGER = "jaeger"
# D6 aplicada al puerto del Service: 16686 + 21000 se sale del rango NodePort.
PUERTO_INTERFAZ_JAEGER = 9686
_PUERTO_INTERFAZ_JAEGER_CONTENEDOR = 16686
_PUERTO_OTLP = 4318


def _validar_host(host):
    if len(host) > _LARGO_MAXIMO_HOST or not _NOMBRE_SERVICIO.fullmatch(host):
        raise ValueError(
            f"host invalido para un Service de Kubernetes (DNS-1035, max {_LARGO_MAXIMO_HOST}): {host!r}"
        )


def puerto_externo(puerto):
    externo = puerto + _DESPLAZAMIENTO_NODEPORT
    if not _NODEPORT_MIN <= externo <= _NODEPORT_MAX:
        raise ValueError(
            f"puerto interno {puerto} queda fuera del rango NodePort "
            f"({_NODEPORT_MIN}..{_NODEPORT_MAX}): {externo}"
        )
    return externo


def _ip_fija(desplazamiento, etiqueta):
    ip = _BASE_IP_SERVICIO + desplazamiento
    if ip not in _RED_IP_FIJAS:
        raise ValueError(
            f"{etiqueta} queda fuera de la banda de IPs fijas "
            f"({_RED_IP_FIJAS}): {ip}"
        )
    return str(ip)


def ip_servicio(nodo):
    return _ip_fija(nodo.id_nodo, f"id de nodo {nodo.id_nodo}")


def _ip_jaeger():
    return _ip_fija(0, _NOMBRE_JAEGER)


def _nodos_ordenados(texto_nodos):
    cluster = config.nodos(texto_nodos)
    return [cluster[id_nodo] for id_nodo in sorted(cluster)]


def _etiquetas(nodo):
    return {"app": _APP, "nodo": str(nodo.id_nodo)}


def _puertos(nodo):
    return {"pyro": nodo.puerto_pyro, "cluster": nodo.puerto_cluster}


def _ruta_datos(nodo):
    return f"{_DATOS_EN_LA_MAQUINA}/nodo{nodo.id_nodo}"


def _probe(nodo):
    # Trucardo decide primero y Kubernetes repara despues (D7).
    periodo = int(config.TIMEOUT_CAIDO // _PROBE_FALLAS) + 1
    return {
        "tcpSocket": {"port": _puertos(nodo)["cluster"]},
        "periodSeconds": periodo,
        "failureThreshold": _PROBE_FALLAS,
    }


def _tolerancias():
    return [
        {
            "key": clave,
            "operator": "Exists",
            "effect": "NoExecute",
            "tolerationSeconds": _TOLERANCIA_SEGUNDOS,
        }
        for clave in (
            "node.kubernetes.io/unreachable",
            "node.kubernetes.io/not-ready",
        )
    ]


def _anti_afinidad():
    return {
        "podAntiAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                    "weight": 100,
                    "podAffinityTerm": {
                        "labelSelector": {"matchLabels": {"app": _APP}},
                        "topologyKey": "kubernetes.io/hostname",
                    },
                }
            ]
        }
    }


def _etiquetas_jaeger():
    return {"app": _NOMBRE_JAEGER}


def _env_telemetria():
    return [
        {
            "name": "K8S_POD_NAME",
            "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
        },
        {
            "name": "K8S_NODE_NAME",
            "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}},
        },
        {
            "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
            "value": f"http://{_NOMBRE_JAEGER}:{_PUERTO_OTLP}",
        },
        {
            "name": "OTEL_RESOURCE_ATTRIBUTES",
            "value": "k8s.pod.name=$(K8S_POD_NAME),k8s.node.name=$(K8S_NODE_NAME)",
        },
    ]


def _deployment(nodo, ordenados, texto_nodos, imagen, telemetria=False):
    host_aliases = [
        {"ip": ip_servicio(n), "hostnames": [n.host]}
        for n in ordenados
    ]
    env = [
        {"name": "TRUCARDO_NODOS", "value": texto_nodos},
        {"name": "TRUCARDO_DATOS", "value": _DIRECTORIO_DATOS},
    ]
    if telemetria:
        host_aliases.append({"ip": _ip_jaeger(), "hostnames": [_NOMBRE_JAEGER]})
        env.extend(_env_telemetria())
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": f"trucardo-nodo{nodo.id_nodo}",
            "labels": _etiquetas(nodo),
        },
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": _etiquetas(nodo)},
            "template": {
                "metadata": {"labels": _etiquetas(nodo)},
                "spec": {
                    "hostAliases": host_aliases,
                    "tolerations": _tolerancias(),
                    "affinity": _anti_afinidad(),
                    "volumes": [
                        {
                            "name": _VOLUMEN_DATOS,
                            "hostPath": {
                                "path": _ruta_datos(nodo),
                                "type": "DirectoryOrCreate",
                            },
                        }
                    ],
                    "containers": [
                        {
                            "name": "nodo",
                            "image": imagen,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python", "-m", "nodo.servidor", str(nodo.id_nodo)],
                            "env": env,
                            "ports": [{"name": nombre, "containerPort": puerto}
                                      for nombre, puerto in _puertos(nodo).items()],
                            "volumeMounts": [
                                {"name": _VOLUMEN_DATOS, "mountPath": _DIRECTORIO_DATOS}
                            ],
                            "livenessProbe": _probe(nodo),
                        }
                    ],
                },
            },
        },
    }


def _service(nodo):
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": nodo.host,
            "labels": _etiquetas(nodo),
        },
        "spec": {
            "type": "NodePort",
            "clusterIP": ip_servicio(nodo),
            "selector": _etiquetas(nodo),
            "ports": [
                {
                    "name": nombre,
                    "port": puerto,
                    "targetPort": puerto,
                    "nodePort": puerto_externo(puerto),
                }
                for nombre, puerto in _puertos(nodo).items()
            ],
        },
    }


def _deployment_jaeger():
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": _NOMBRE_JAEGER,
            "labels": _etiquetas_jaeger(),
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": _etiquetas_jaeger()},
            "template": {
                "metadata": {"labels": _etiquetas_jaeger()},
                "spec": {
                    "containers": [
                        {
                            "name": _NOMBRE_JAEGER,
                            "image": IMAGEN_JAEGER,
                            "imagePullPolicy": "IfNotPresent",
                            "ports": [
                                {
                                    "name": "interfaz",
                                    "containerPort": _PUERTO_INTERFAZ_JAEGER_CONTENEDOR,
                                },
                                {
                                    "name": "otlp",
                                    "containerPort": _PUERTO_OTLP,
                                },
                            ],
                        }
                    ],
                },
            },
        },
    }


def _service_jaeger():
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": _NOMBRE_JAEGER,
            "labels": _etiquetas_jaeger(),
        },
        "spec": {
            "type": "NodePort",
            "clusterIP": _ip_jaeger(),
            "selector": _etiquetas_jaeger(),
            "ports": [
                {
                    "name": "interfaz",
                    "port": PUERTO_INTERFAZ_JAEGER,
                    "targetPort": _PUERTO_INTERFAZ_JAEGER_CONTENEDOR,
                    "nodePort": puerto_externo(PUERTO_INTERFAZ_JAEGER),
                },
                {
                    "name": "otlp",
                    "port": _PUERTO_OTLP,
                    "targetPort": _PUERTO_OTLP,
                },
            ],
        },
    }


def manifiestos(texto_nodos, imagen, telemetria=False):
    ordenados = _nodos_ordenados(texto_nodos)
    for nodo in ordenados:
        _validar_host(nodo.host)

    objetos = []
    for nodo in ordenados:
        objetos.append(_deployment(nodo, ordenados, texto_nodos, imagen, telemetria=telemetria))
        objetos.append(_service(nodo))
    if telemetria:
        objetos.append(_deployment_jaeger())
        objetos.append(_service_jaeger())
    return objetos


def texto_clientes(texto_nodos, ip):
    return ",".join(
        f"{nodo.id_nodo}@{ip}:{puerto_externo(nodo.puerto_pyro)}:{puerto_externo(nodo.puerto_cluster)}"
        for nodo in _nodos_ordenados(texto_nodos)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Genera los manifiestos de Kubernetes para Trucardo en JSON."
    )
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--imagen", help="Imagen del contenedor (ej. trucardo:local)")
    modo.add_argument("--clientes", metavar="IP", help="IP del cluster para clientes externos")
    parser.add_argument(
        "--telemetria",
        action="store_true",
        help="Agrega Jaeger y la configuracion de trazas OpenTelemetry",
    )
    args = parser.parse_args(argv)

    if args.telemetria and args.clientes is not None:
        parser.error("--telemetria solo se puede usar con --imagen")

    try:
        if args.clientes is not None:
            salida = texto_clientes(config.texto_nodos(), args.clientes)
        else:
            items = manifiestos(config.texto_nodos(), args.imagen, telemetria=args.telemetria)
            salida = json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, indent=2)
    except ValueError as error:
        sys.exit(str(error))

    print(salida)


if __name__ == "__main__":
    main()
