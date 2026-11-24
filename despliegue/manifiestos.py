import argparse
import json
import re
import sys

from nodo import config

# Kubernetes exige etiquetas DNS-1035 (max 63 caracteres) como nombre de Service.
_NOMBRE_SERVICIO = re.compile(r"^[a-z]([-a-z0-9]*[a-z0-9])?$")
_LARGO_MAXIMO_HOST = 63


def _validar_host(host):
    if len(host) > _LARGO_MAXIMO_HOST or not _NOMBRE_SERVICIO.fullmatch(host):
        raise ValueError(
            f"host invalido para un Service de Kubernetes (DNS-1035, max {_LARGO_MAXIMO_HOST}): {host!r}"
        )


def _etiquetas(nodo):
    return {"app": "trucardo", "nodo": str(nodo.id_nodo)}


def _puertos(nodo):
    return {"pyro": nodo.puerto_pyro, "cluster": nodo.puerto_cluster}


def _deployment(nodo, texto_nodos, imagen):
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
                    "containers": [
                        {
                            "name": "nodo",
                            "image": imagen,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python", "-m", "nodo.servidor", str(nodo.id_nodo)],
                            "env": [{"name": "TRUCARDO_NODOS", "value": texto_nodos}],
                            "ports": [{"name": nombre, "containerPort": puerto}
                                      for nombre, puerto in _puertos(nodo).items()],
                        }
                    ]
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
            "selector": _etiquetas(nodo),
            "ports": [{"name": nombre, "port": puerto, "targetPort": puerto}
                      for nombre, puerto in _puertos(nodo).items()],
        },
    }


def manifiestos(texto_nodos, imagen):
    cluster = config.nodos(texto_nodos)
    ordenados = [cluster[id_nodo] for id_nodo in sorted(cluster)]
    for nodo in ordenados:
        _validar_host(nodo.host)

    objetos = []
    for nodo in ordenados:
        objetos.append(_deployment(nodo, texto_nodos, imagen))
        objetos.append(_service(nodo))
    return objetos


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Genera los manifiestos de Kubernetes para Trucardo en JSON."
    )
    parser.add_argument("--imagen", required=True, help="Imagen del contenedor (ej. trucardo:local)")
    args = parser.parse_args(argv)

    try:
        items = manifiestos(config.texto_nodos(), args.imagen)
    except ValueError as error:
        sys.exit(str(error))

    salida = {"apiVersion": "v1", "kind": "List", "items": items}
    print(json.dumps(salida, indent=2))


if __name__ == "__main__":
    main()
