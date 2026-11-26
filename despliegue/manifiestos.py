import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path

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
_ALMACENAMIENTO_HOSTPATH = "hostpath"
_ALMACENAMIENTO_LONGHORN = "longhorn"
_ALMACENAMIENTOS = (_ALMACENAMIENTO_HOSTPATH, _ALMACENAMIENTO_LONGHORN)
_TAMANO_PVC = "1Gi"

IMAGEN_JAEGER = "jaegertracing/jaeger:2.23.0"
IMAGEN_COLLECTOR = "otel/opentelemetry-collector:0.165.0"
IMAGEN_PROMETHEUS = "prom/prometheus:v3.16.0"
IMAGEN_LOKI = "grafana/loki:3.6.22"
IMAGEN_GRAFANA = "grafana/grafana:13.3.2"

_DIR_OBSERVABILIDAD = Path(__file__).resolve().parent / "observabilidad"
_VOLUMEN_CONFIG = "config"
_NOMBRE_COLLECTOR = "collector"
# D6 aplicada al puerto del Service: 16686 + 21000 se sale del rango NodePort.
PUERTO_INTERFAZ_JAEGER = 9686
_PUERTO_OTLP = 4318

_NOMBRE_VISOR = "visor"
_ROL_VISOR = "trucardo-visor"
_PUERTO_VISOR = 9808
_DESPLAZAMIENTO_VISOR = -5
_NAMESPACE = "default"

_OBSERVABILIDAD = (
    {
        "nombre": "jaeger",
        "imagen": IMAGEN_JAEGER,
        "desplazamiento": 0,
        "tipo_service": "NodePort",
        "puertos_contenedor": (("interfaz", 16686), ("otlp", _PUERTO_OTLP)),
        "puertos_service": (
            ("interfaz", PUERTO_INTERFAZ_JAEGER, 16686, True),
            ("consulta", 16686, 16686, False),
            ("otlp", _PUERTO_OTLP, _PUERTO_OTLP, False),
        ),
    },
    {
        "nombre": _NOMBRE_COLLECTOR,
        "imagen": IMAGEN_COLLECTOR,
        "desplazamiento": -1,
        "tipo_service": "NodePort",
        "puertos_contenedor": (("otlp", _PUERTO_OTLP),),
        "puertos_service": (
            ("otlp", _PUERTO_OTLP, _PUERTO_OTLP, False),
            ("otlp-externo", 9318, _PUERTO_OTLP, True),
        ),
        "args": ("--config=/etc/otelcol/collector.json",),
        "config": (("collector.json", "/etc/otelcol", False),),
    },
    {
        "nombre": "prometheus",
        "imagen": IMAGEN_PROMETHEUS,
        "desplazamiento": -2,
        "tipo_service": "NodePort",
        "puertos_contenedor": (("interfaz", 9090),),
        "puertos_service": (("interfaz", 9090, 9090, True),),
        "args": (
            "--config.file=/etc/prometheus/prometheus.json",
            "--web.enable-otlp-receiver",
        ),
        "config": (("prometheus.json", "/etc/prometheus", False),),
    },
    {
        "nombre": "loki",
        "imagen": IMAGEN_LOKI,
        "desplazamiento": -3,
        "tipo_service": "ClusterIP",
        "puertos_contenedor": (("http", 3100),),
        "puertos_service": (("http", 3100, 3100, False),),
    },
    {
        "nombre": "grafana",
        "imagen": IMAGEN_GRAFANA,
        "desplazamiento": -4,
        "tipo_service": "NodePort",
        "puertos_contenedor": (("interfaz", 3000),),
        "puertos_service": (("interfaz", 9300, 3000, True),),
        "env": (
            ("GF_AUTH_ANONYMOUS_ENABLED", "true"),
            ("GF_AUTH_ANONYMOUS_ORG_ROLE", "Admin"),
            ("GF_AUTH_DISABLE_LOGIN_FORM", "true"),
        ),
        "config": (
            ("fuentes.yaml", "/etc/grafana/provisioning/datasources/fuentes.yaml", True),
            ("tableros.yaml", "/etc/grafana/provisioning/dashboards/tableros.yaml", True),
            ("tablero-trucardo.json", "/etc/grafana/tableros/tablero-trucardo.json", True),
        ),
    },
)


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


def _host_aliases_observabilidad():
    return [
        {"ip": _ip_fija(s["desplazamiento"], s["nombre"]), "hostnames": [s["nombre"]]}
        for s in _OBSERVABILIDAD
    ]


def _nodos_ordenados(texto_nodos):
    cluster = config.nodos(texto_nodos)
    return [cluster[id_nodo] for id_nodo in sorted(cluster)]


def _etiquetas(nodo):
    return {"app": _APP, "nodo": str(nodo.id_nodo)}


def _puertos(nodo):
    return {"pyro": nodo.puerto_pyro, "cluster": nodo.puerto_cluster}


def _ruta_datos(nodo):
    return f"{_DATOS_EN_LA_MAQUINA}/nodo{nodo.id_nodo}"


def _nombre_pvc(nodo):
    return f"{_VOLUMEN_DATOS}-nodo{nodo.id_nodo}"


def _volumen_datos(nodo, almacenamiento):
    if almacenamiento == _ALMACENAMIENTO_LONGHORN:
        return {
            "name": _VOLUMEN_DATOS,
            "persistentVolumeClaim": {"claimName": _nombre_pvc(nodo)},
        }
    return {
        "name": _VOLUMEN_DATOS,
        "hostPath": {
            "path": _ruta_datos(nodo),
            "type": "DirectoryOrCreate",
        },
    }


def _pvc(nodo):
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": _nombre_pvc(nodo),
            "labels": _etiquetas(nodo),
        },
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "storageClassName": _ALMACENAMIENTO_LONGHORN,
            "resources": {"requests": {"storage": _TAMANO_PVC}},
        },
    }


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


def _etiquetas_servicio(nombre):
    return {"app": nombre}


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
            "value": f"http://{_NOMBRE_COLLECTOR}:{_PUERTO_OTLP}",
        },
        {
            "name": "OTEL_RESOURCE_ATTRIBUTES",
            "value": "k8s.pod.name=$(K8S_POD_NAME),k8s.node.name=$(K8S_NODE_NAME)",
        },
    ]


def _deployment(
    nodo,
    ordenados,
    texto_nodos,
    imagen,
    telemetria=False,
    almacenamiento=_ALMACENAMIENTO_HOSTPATH,
):
    host_aliases = [
        {"ip": ip_servicio(n), "hostnames": [n.host]}
        for n in ordenados
    ]
    env = [
        {"name": "TRUCARDO_NODOS", "value": texto_nodos},
        {"name": "TRUCARDO_DATOS", "value": _DIRECTORIO_DATOS},
    ]
    if telemetria:
        host_aliases.extend(_host_aliases_observabilidad())
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
                    "volumes": [_volumen_datos(nodo, almacenamiento)],
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


def _configmap_observabilidad(servicio):
    nombre = servicio["nombre"]
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": nombre,
            "labels": _etiquetas_servicio(nombre),
        },
        "data": {
            archivo: (_DIR_OBSERVABILIDAD / archivo).read_text(encoding="utf-8")
            for archivo, _, _ in servicio["config"]
        },
    }


def _deployment_observabilidad(servicio):
    nombre = servicio["nombre"]
    etiquetas = _etiquetas_servicio(nombre)
    contenedor = {
        "name": nombre,
        "image": servicio["imagen"],
        "imagePullPolicy": "IfNotPresent",
        "ports": [
            {"name": nombre_puerto, "containerPort": puerto}
            for nombre_puerto, puerto in servicio["puertos_contenedor"]
        ],
    }
    if servicio.get("args"):
        contenedor["args"] = list(servicio["args"])
    if servicio.get("env"):
        contenedor["env"] = [
            {"name": clave, "value": valor} for clave, valor in servicio["env"]
        ]

    pod_spec = {
        "hostAliases": _host_aliases_observabilidad(),
        "tolerations": _tolerancias(),
        "containers": [contenedor],
    }
    if servicio.get("config"):
        pod_spec["volumes"] = [
            {"name": _VOLUMEN_CONFIG, "configMap": {"name": nombre}}
        ]
        contenedor["volumeMounts"] = [
            (
                {"name": _VOLUMEN_CONFIG, "mountPath": ruta, "subPath": archivo}
                if con_subpath
                else {"name": _VOLUMEN_CONFIG, "mountPath": ruta}
            )
            for archivo, ruta, con_subpath in servicio["config"]
        ]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": nombre,
            "labels": etiquetas,
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": etiquetas},
            "template": {
                "metadata": {"labels": etiquetas},
                "spec": pod_spec,
            },
        },
    }


def _service_observabilidad(servicio):
    nombre = servicio["nombre"]
    etiquetas = _etiquetas_servicio(nombre)
    puertos = []
    for nombre_puerto, puerto, destino, con_nodeport in servicio["puertos_service"]:
        entrada = {"name": nombre_puerto, "port": puerto, "targetPort": destino}
        if con_nodeport:
            entrada["nodePort"] = puerto_externo(puerto)
        puertos.append(entrada)
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": nombre,
            "labels": etiquetas,
        },
        "spec": {
            "type": servicio["tipo_service"],
            "clusterIP": _ip_fija(servicio["desplazamiento"], nombre),
            "selector": etiquetas,
            "ports": puertos,
        },
    }


def _rbac_visor():
    return [
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": _NOMBRE_VISOR, "labels": _etiquetas_servicio(_NOMBRE_VISOR)},
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {"name": _ROL_VISOR},
            "rules": [{"apiGroups": [""], "resources": ["nodes", "pods"], "verbs": ["get", "list"]}],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {"name": _ROL_VISOR},
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": _ROL_VISOR},
            "subjects": [{"kind": "ServiceAccount", "name": _NOMBRE_VISOR, "namespace": _NAMESPACE}],
        },
    ]


def _deployment_visor(ordenados, texto_nodos, imagen, telemetria):
    etiquetas = _etiquetas_servicio(_NOMBRE_VISOR)
    host_aliases = [{"ip": ip_servicio(n), "hostnames": [n.host]} for n in ordenados]
    env = [{"name": "TRUCARDO_NODOS", "value": texto_nodos}]
    if telemetria:
        host_aliases.extend(_host_aliases_observabilidad())
        env.append({"name": "VISOR_JAEGER", "value": "http://jaeger:16686"})
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": _NOMBRE_VISOR, "labels": etiquetas},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": etiquetas},
            "template": {
                "metadata": {"labels": etiquetas},
                "spec": {
                    "serviceAccountName": _NOMBRE_VISOR,
                    "hostAliases": host_aliases,
                    "tolerations": _tolerancias(),
                    "containers": [
                        {
                            "name": _NOMBRE_VISOR,
                            "image": imagen,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python", "-m", "visor.servidor"],
                            "env": env,
                            "ports": [{"name": "web", "containerPort": _PUERTO_VISOR}],
                        }
                    ],
                },
            },
        },
    }


def _service_visor():
    etiquetas = _etiquetas_servicio(_NOMBRE_VISOR)
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": _NOMBRE_VISOR, "labels": etiquetas},
        "spec": {
            "type": "NodePort",
            "clusterIP": _ip_fija(_DESPLAZAMIENTO_VISOR, _NOMBRE_VISOR),
            "selector": etiquetas,
            "ports": [{"name": "web", "port": _PUERTO_VISOR, "targetPort": _PUERTO_VISOR,
                       "nodePort": puerto_externo(_PUERTO_VISOR)}],
        },
    }


def manifiestos(texto_nodos, imagen, telemetria=False, almacenamiento=_ALMACENAMIENTO_HOSTPATH,
                visor=False):
    if almacenamiento not in _ALMACENAMIENTOS:
        raise ValueError(f"almacenamiento desconocido: {almacenamiento!r}")
    ordenados = _nodos_ordenados(texto_nodos)
    for nodo in ordenados:
        _validar_host(nodo.host)

    objetos = []
    for nodo in ordenados:
        if almacenamiento == _ALMACENAMIENTO_LONGHORN:
            objetos.append(_pvc(nodo))
        objetos.append(
            _deployment(
                nodo,
                ordenados,
                texto_nodos,
                imagen,
                telemetria=telemetria,
                almacenamiento=almacenamiento,
            )
        )
        objetos.append(_service(nodo))
    if telemetria:
        for servicio in _OBSERVABILIDAD:
            if servicio.get("config"):
                objetos.append(_configmap_observabilidad(servicio))
            objetos.append(_deployment_observabilidad(servicio))
            objetos.append(_service_observabilidad(servicio))
    if visor:
        objetos.extend(_rbac_visor())
        objetos.append(_deployment_visor(ordenados, texto_nodos, imagen, telemetria))
        objetos.append(_service_visor())
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
        help="Agrega la pila de observabilidad OpenTelemetry",
    )
    parser.add_argument(
        "--almacenamiento",
        choices=_ALMACENAMIENTOS,
        default=None,
        help="Tipo de almacenamiento de datos por nodo (por defecto: hostpath)",
    )
    parser.add_argument(
        "--visor",
        action="store_true",
        help="Agrega el visor en vivo de la arquitectura (NodePort 30808)",
    )
    args = parser.parse_args(argv)

    if args.telemetria and args.clientes is not None:
        parser.error("--telemetria solo se puede usar con --imagen")
    if args.almacenamiento is not None and args.clientes is not None:
        parser.error("--almacenamiento solo se puede usar con --imagen")
    if args.visor and args.clientes is not None:
        parser.error("--visor solo se puede usar con --imagen")

    try:
        if args.clientes is not None:
            salida = texto_clientes(config.texto_nodos(), args.clientes)
        else:
            items = manifiestos(
                config.texto_nodos(),
                args.imagen,
                telemetria=args.telemetria,
                almacenamiento=args.almacenamiento or _ALMACENAMIENTO_HOSTPATH,
                visor=args.visor,
            )
            salida = json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, indent=2)
    except ValueError as error:
        sys.exit(str(error))

    print(salida)


if __name__ == "__main__":
    main()
