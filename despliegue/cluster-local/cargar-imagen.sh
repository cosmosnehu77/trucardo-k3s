#!/bin/sh
set -eu

imagen="${1:-trucardo:local}"
dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
compose="$dir/compose.yaml"

servicios=$(docker compose -f "$compose" ps --services)
if [ -z "$servicios" ]; then
    echo "No hay máquinas levantadas en $compose." >&2
    exit 1
fi
for servicio in $servicios; do
    printf 'Cargando %s en %s...\n' "$imagen" "$servicio"
    docker save "$imagen" | docker compose -f "$compose" exec -T "$servicio" ctr images import -
done
