const OBS = {
  collector: {
    titulo: "Collector de OpenTelemetry",
    texto: "Recibe por OTLP las trazas, métricas y logs que mandan los nodos y los clientes, y reparte cada señal a su destino: las trazas a Jaeger, las métricas a Prometheus y los logs a Loki. Así los nodos sólo conocen una dirección (OTEL_EXPORTER_OTLP_ENDPOINT).",
  },
  jaeger: {
    titulo: "Jaeger",
    texto: "Guarda las trazas: cada jugada es un árbol de spans que empieza en el cliente, pasa por el primario y termina en la réplica de cada backup. El visor le pregunta por las trazas de los últimos segundos y dibuja como mensaje cada span cuyo padre es de otro servicio.",
  },
  prometheus: {
    titulo: "Prometheus",
    texto: "Guarda las métricas de dominio de cada nodo (operaciones, elecciones, latidos perdidos, atraso de los backups). Las recibe por OTLP, sin scrapear a los nodos.",
  },
  loki: {
    titulo: "Loki",
    texto: "Guarda los logs de los nodos. Cada línea lleva el trace_id del span en el que se escribió, y Grafana lo usa para saltar de un log a su traza.",
  },
  grafana: {
    titulo: "Grafana",
    texto: "El tablero «Trucardo»: primarios simultáneos, rol y época por nodo, atraso de cada backup, operaciones por segundo. Consulta a Prometheus, Loki y Jaeger; no guarda datos propios.",
  },
  visor: {
    titulo: "Visor (esta página)",
    texto: "Un Pod más, con la misma imagen que los nodos. Cada segundo lee la API de Kubernetes con una cuenta de sólo lectura (nodes y pods), le pregunta a cada nodo de Trucardo con listar_mesas y, si hay telemetría, lee las trazas de Jaeger. Sirve /api/estado y esta figura.",
  },
};

const fila = (clave, valor) => (valor === undefined || valor === null || valor === "" ? "" : `<dt>${clave}</dt><dd>${valor}</dd>`);

function podsDe(estado, componente) {
  return (estado?.pods || []).filter((p) => p.componente === componente);
}

function filasPod(pod) {
  if (!pod) return fila("Pod", "no existe");
  return fila("Pod", pod.nombre) + fila("Máquina", pod.maquina) + fila("Fase", pod.fase) + fila("Listo", pod.listo ? "sí" : "no") + fila("Reinicios", pod.reinicios) + fila("IP del Pod", pod.ip);
}

function ficha(id, estado, maquinaDe) {
  const [tipo, a, b] = id.split("-");
  if (tipo === "carta") {
    const nodo = (estado?.nodos || []).find((n) => n.id === Number(a));
    const pods = podsDe(estado, `nodo${a}`);
    const pod = pods.find((p) => maquinaDe(p.maquina) === Number(b)) || pods[0];
    return {
      titulo: `Nodo ${a} de Trucardo`,
      texto: "Un proceso nodo.servidor dentro de un Pod. Kubernetes lo crea y lo reubica, pero quién manda lo deciden los nodos entre ellos: el primario atiende las jugadas, escribe cada operación en su disco con fsync, la replica a los backups y late cada 1 s. Si un backup pasa 3 s sin latido, arranca una elección Bully que compara (época, último seq, id). La placa del primario tiene su color pleno y la lámpara amarilla encendida; las de los backups, el color tenue. La barra muestra cuánto del log tiene.",
      vivo: nodo
        ? fila("Responde", nodo.responde ? "sí" : "no") + fila("Rol", nodo.rol) + fila("Cree que el primario es", nodo.primario === null ? "?" : nodo.primario) + fila("Época", nodo.epoca) + fila("Último seq", nodo.ultimo_seq) + fila("Reloj de Lamport", nodo.reloj) + filasPod(pod)
        : filasPod(pod),
    };
  }
  if (tipo === "modulo") {
    const pod = podsDe(estado, a).find((p) => maquinaDe(p.maquina) === Number(b)) || podsDe(estado, a)[0];
    return { ...OBS[a], vivo: filasPod(pod) };
  }
  if (tipo === "maquina") {
    const m = (estado?.maquinas || [])[Number(a)];
    const aca = (estado?.pods || []).filter((p) => m && p.maquina === m.nombre).map((p) => p.componente).join(", ");
    return {
      titulo: m ? `Máquina ${m.nombre}` : "Lugar libre",
      texto: m && m.rol === "servidor"
        ? "El servidor k3s: además de correr Pods como cualquier máquina, tiene el plano de control (la API, el scheduler, los controladores y el almacén de estado) y CoreDNS. Si se apaga, los Pods que ya corren siguen, pero nadie puede volver a crear los que se caen."
        : "Un agente k3s: corre Pods y su kubelet renueva cada 10 s un lease con el servidor. Si deja de hacerlo por unos 40 s, el servidor la marca NotReady; pasados los 10 s de tolerancia, sus Pods se crean de nuevo en otra máquina.",
      vivo: m ? fila("Rol", m.rol) + fila("IP", m.ip) + fila("Ready", m.lista ? "sí" : "no") + fila("Pods acá", aca || "ninguno") : fila("Estado", "no hay una máquina en este lugar"),
    };
  }
  if (tipo === "control") {
    const listos = new Set((estado?.pods || []).filter((p) => /^nodo\d$/.test(p.componente) && p.listo && p.fase === "Running").map((p) => p.componente)).size;
    return {
      titulo: "Plano de control: estado deseado contra real",
      texto: "La aguja es la cantidad de nodos de Trucardo con su Pod listo, y la raya fija marca los deseados (un Deployment de una réplica por nodo). Los controladores comparan los dos todo el tiempo y actúan sobre la diferencia: si la aguja baja, crean el Pod que falta. La liveness probe por TCP es más lenta que la detección de Trucardo, para que primero elija Trucardo y después repare Kubernetes.",
      vivo: fila("Listos", `${listos} de 3`) + fila("Tolerancia a máquina caída", "10 s") + fila("Estrategia", "Recreate"),
    };
  }
  if (tipo === "almacen") {
    return { titulo: "Almacén de estado del cluster", texto: "Con un único servidor, k3s guarda el estado del cluster (lo pedido y lo que hay) en SQLite a través de kine, en lugar de etcd. Todo pasa por la API del servidor: los controladores leen y escriben acá, nunca se hablan entre ellos.", vivo: "" };
  }
  if (tipo === "coredns") {
    return { titulo: "CoreDNS", texto: "El DNS del cluster. En k3s corre una sola réplica, en el servidor: al apagarlo, los nodos no podían resolver nodo1, nodo2 y nodo3 y quedaban dos primarios. Por eso cada Service tiene una IP fija (10.43.0.101 en adelante) escrita en el /etc/hosts de cada Pod con hostAliases, y Trucardo no depende de este módulo.", vivo: "" };
  }
  if (tipo === "switch" || tipo === "cable" || tipo === "placa") {
    return {
      titulo: tipo === "placa" ? "El banco: una red local" : "La red entre máquinas",
      texto: "Las tres máquinas están en la misma red. Entre Pods de máquinas distintas, Flannel encapsula el tráfico en VXLAN (puerto 8472/udp), así cada Pod tiene su IP en 10.42.0.0/16. Por acá viajan los latidos y las réplicas del primario a los backups, y las jugadas que entran por NodePort a una máquina y kube-proxy reenvía a la máquina del primario.",
      vivo: fila("Máquinas", (estado?.maquinas || []).map((m) => `${m.nombre} (${m.ip})`).join(", ")),
    };
  }
  if (tipo === "consola" || tipo === "hub" || tipo === "uplink" || tipo === "mesa") {
    const jugador = tipo === "consola" ? (estado?.clientes || [])[Number(a)] : null;
    const mesa = jugador ? (estado?.mesas || []).find((m) => m.id_mesa === jugador.mesa) : null;
    return {
      titulo: jugador ? `Jugador ${jugador.nombre}` : "Clientes",
      texto: "Los clientes corren fuera del cluster y entran por NodePort: el puerto de cada nodo más 21000, en la IP de una máquina. El cliente le habla al primario por Pyro5; si el que contesta no es el primario, lo redirige, y si nadie contesta, reintenta durante 25 s. Las consolas se encienden con los jugadores que el primario tiene sentados en una mesa.",
      vivo: jugador
        ? fila("Mesa", jugador.mesa) + fila("Estado", jugador.estado) + fila("Marcador", mesa ? mesa.marcador.join(" a ") : "") + fila("Mano", mesa?.numero_mano) + fila("Visto en trazas", jugador.trazado ? "sí" : "no")
        : fila("Jugadores", (estado?.clientes || []).map((c) => c.nombre).join(", ") || "ninguno"),
    };
  }
  return { titulo: "", texto: "", vivo: "" };
}
