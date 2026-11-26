const P = GEO.P;
const svg = document.querySelector(".visor-stage svg");
const capaPulsos = svg.querySelector("[data-pulsos]");
const readout = document.querySelector("[data-readout]");
const fichaEl = document.querySelector("[data-ficha]");
const jugadoresEl = document.querySelector("[data-jugadores]");
const mensajesEl = document.querySelector("[data-mensajes]");
const quieto = matchMedia("(prefers-reduced-motion: reduce)");
const DEMO = new URLSearchParams(location.search).has("demo");
const NS = "http://www.w3.org/2000/svg";

let estado = null;
let elegido = "control";
let anterior = null;
let aguja = 0;
let agujaMeta = 0;
let turnoJugador = 0;
let vistos = new Set();
let ultimoOtlp = 0;
const feed = [];
const pulsos = [];

const at = (p) => iso(p, P);
const hora = (ms) => new Date(ms).toLocaleTimeString("es-AR", { hour12: false });

function maquinaDe(nombre) {
  const i = (estado?.maquinas || []).findIndex((m) => m.nombre === nombre);
  return i >= 0 && i < 3 ? i : -1;
}

function podListo(componente) {
  return (estado?.pods || []).find((p) => p.componente === componente && p.fase === "Running" && maquinaDe(p.maquina) >= 0) || (estado?.pods || []).find((p) => p.componente === componente && maquinaDe(p.maquina) >= 0);
}

function dondeEsta(componente) {
  const pod = podListo(componente);
  return pod ? maquinaDe(pod.maquina) : -1;
}

function marcar(el, nombre, si) {
  if (si) el.setAttribute(nombre, "");
  else el.removeAttribute(nombre);
}

function aplicar() {
  const maquinas = estado.maquinas || [];
  svg.querySelectorAll("[data-maquina]").forEach((g) => {
    const m = maquinas[Number(g.dataset.maquina)];
    marcar(g, "data-caida", !m || !m.lista);
  });

  const vivos = new Map();
  for (const pod of estado.pods || []) {
    const i = maquinaDe(pod.maquina);
    if (i < 0) continue;
    const clave = `${pod.componente}@${i}`;
    const previo = vivos.get(clave);
    if (!previo || pod.fase === "Running") vivos.set(clave, pod);
  }
  svg.querySelectorAll("[data-pod]").forEach((g) => {
    const pod = vivos.get(`${g.dataset.pod}@${g.dataset.en}`);
    marcar(g, "data-off", !pod);
    marcar(g, "data-pendiente", !!pod && pod.fase !== "Running" && pod.fase !== "Terminating");
    marcar(g, "data-terminando", !!pod && pod.fase === "Terminating");
    marcar(g, "data-noListo", !!pod && pod.fase === "Running" && !pod.listo);
  });

  const nodos = estado.nodos || [];
  const tope = Math.max(1, ...nodos.map((n) => n.ultimo_seq || 0));
  nodos.forEach((n) => {
    svg.querySelectorAll(`[data-pod="nodo${n.id}"]`).forEach((g) => {
      const primario = n.rol === "primario";
      marcar(g, "data-primario", primario);
      marcar(g, "data-mudo", !n.responde);
      const cuerpo = g.querySelector(".iso-solid");
      if (cuerpo) marcar(cuerpo, "data-lit", primario);
      const cx = GEO.machines[Number(g.dataset.en)] + GEO.cardX[n.id - 1];
      const share = n.responde ? (n.ultimo_seq || 0) / tope : 0;
      const z = 84 + 36 * Math.max(0.003, share);
      g.querySelector("[data-log]").setAttribute("d", pathOf([at([cx + 12, GEO.card.y + GEO.card.d + 0.05, 84]), at([cx + 12, GEO.card.y + GEO.card.d + 0.05, z])]));
    });
  });

  const listos = new Set((estado.pods || []).filter((p) => /^nodo\d$/.test(p.componente) && p.listo && p.fase === "Running").map((p) => p.componente)).size;
  agujaMeta = listos / 3;

  const clientes = estado.clientes || [];
  svg.querySelectorAll("[data-consola]").forEach((g) => {
    const c = clientes[Number(g.dataset.consola)];
    marcar(g, "data-vacia", !c);
    const pantalla = g.querySelector("[data-pantalla]");
    pantalla.style.opacity = !c ? "0" : c.estado === "en_juego" ? "0.8" : c.estado ? "0.35" : "0.2";
  });

  const primario = nodos.find((n) => n.rol === "primario");
  const pods = `${listos}/3 nodos listos`;
  readout.textContent = primario ? `primario N${primario.id} · época ${primario.epoca} · seq ${primario.ultimo_seq} · ${pods}` : `sin primario · ${pods}`;

  jugadoresEl.innerHTML = clientes.length
    ? clientes.map((c) => `<li><b>${c.nombre}</b> <span>${c.mesa ? `mesa ${c.mesa} · ${c.estado.replace("_", " ")}` : "visto en trazas"}</span></li>`).join("")
    : "<li><span>Nadie está jugando.</span></li>";
  mostrarFicha();
}

function mostrarFicha() {
  const f = ficha(elegido, estado, maquinaDe);
  const aviso = DEMO ? '<p class="visor-aviso">Modo demostración: los datos son simulados en el navegador.</p>' : estado && estado.kubernetes === false ? '<p class="visor-aviso">El visor no llega a la API de Kubernetes: no se ven máquinas ni Pods.</p>' : "";
  fichaEl.innerHTML = `${aviso}<h2>${f.titulo}</h2><p>${f.texto}</p>${f.vivo ? `<dl>${f.vivo}</dl>` : ""}`;
  svg.querySelectorAll("[data-elegido]").forEach((g) => g.removeAttribute("data-elegido"));
  svg.querySelector(`[data-part="${elegido}"]`)?.setAttribute("data-elegido", "");
}

const corto = (nombre) => nombre.replace(/^nodo(\d)$/, "N$1").replace(/^cliente-/, "");
const colorDe = (nombre) => GEO.colores[nombre.startsWith("cliente-") ? "clientes" : nombre] || GEO.colores.red;
const etiqueta = (texto, de, a) => `${texto} · ${corto(de)}→${corto(a)}`;

function anotar(ms, de, a, texto, fuente) {
  feed.unshift({ ms, de, a, texto, fuente });
  feed.length = Math.min(feed.length, 14);
  mensajesEl.innerHTML = feed.map((m) => `<li style="--c:${colorDe(m.de)}"><i></i><time>${hora(m.ms)}</time> <b>${m.texto}</b> ${corto(m.de)} → ${corto(m.a)}${m.fuente === "deducido" ? " <span>deducido</span>" : ""}</li>`).join("");
}

const TEXTOS_SPAN = { replica: "réplica", "puesta al dia recibida": "puesta al día", desafio: "elección", "coordinador recibido": "coordinador" };
function textoDe(m) {
  const base = TEXTOS_SPAN[m.tipo] || m.tipo;
  if (m.cantidad !== null && m.cantidad !== undefined) return `${base} · ${m.cantidad} ops`;
  return m.seq ? `${base} op ${m.seq}` : base;
}

const canal = (ax, bx) => [[ax, GEO.ports[0][1], GEO.switchTop], [ax, GEO.channelY, GEO.switchTop], [bx, GEO.channelY, GEO.switchTop], [bx, GEO.ports[0][1], GEO.switchTop]];

function entreMaquinas(a, b) {
  return [...GEO.cables[a], ...canal(GEO.ports[a][0], GEO.ports[b][0]), ...[...GEO.cables[b]].reverse()];
}

function puntoDe(componente) {
  const i = dondeEsta(componente);
  if (i < 0) return null;
  const nodo = /^nodo(\d)$/.exec(componente);
  if (nodo) return { i, p: [GEO.machines[i] + GEO.cardX[nodo[1] - 1] - 11, GEO.card.y + GEO.card.d, 117] };
  const modulo = GEO.modules.indexOf(componente);
  return modulo < 0 ? null : { i, p: [GEO.machines[i] + GEO.socketX[modulo], GEO.socketY, GEO.moduleTop] };
}

function salida({ i, p }) {
  const jack = GEO.cables[i][0];
  return [p, [p[0], p[1], GEO.mh + 1], [p[0], GEO.front, GEO.mh + 1], [p[0], GEO.front, jack[2]], jack];
}

function ruta(de, a) {
  const o = puntoDe(de);
  const d = puntoDe(a);
  if (!o || !d) return null;
  if (o.i === d.i) {
    const alto = Math.max(o.p[2], d.p[2]) + 18;
    return [o.p, [o.p[0], o.p[1], alto], [d.p[0], d.p[1], alto], d.p];
  }
  return [...salida(o), ...entreMaquinas(o.i, d.i), ...salida(d).reverse()];
}

function rutaCliente(c, nodo) {
  const d = puntoDe(nodo);
  if (!d || c < 0 || c > 3) return null;
  const consola = GEO.consoles[c];
  const porHub = [[GEO.hubX, consola[consola.length - 1][1], GEO.hubTop], [GEO.hubX, GEO.uplink[0][1], GEO.hubTop]];
  const top = GEO.switchTop;
  const alCanal = [[GEO.uplinkPort[0] - 6, GEO.channelY, top], [GEO.ports[0][0], GEO.channelY, top], [GEO.ports[0][0], GEO.ports[0][1], top]];
  const entrada = [...consola, ...porHub, ...GEO.uplink, ...alCanal, ...[...GEO.cables[0]].reverse()];
  return [...entrada, ...(d.i === 0 ? [] : entreMaquinas(0, d.i)), ...salida(d).reverse()];
}

function lanzar(camino, { de, texto, r = 2.4, forma = "punto", retraso = 0 }) {
  if (!camino || quieto.matches) return 0;
  const pts = camino.map(at);
  const largos = [0];
  for (let i = 1; i < pts.length; i++) largos.push(largos[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = largos[largos.length - 1];
  const color = colorDe(de);
  const el = document.createElementNS(NS, "g");
  el.setAttribute("class", "visor-pulso");
  el.setAttribute("data-forma", forma);
  el.style.opacity = "0";
  el.innerHTML = `<g><rect rx="3" height="12" y="-${r + 15}" style="stroke:${color}"/><text y="-${r + 6}" text-anchor="middle"></text></g><circle r="${r}" style="${forma === "anillo" ? `stroke:${color}` : `fill:${color}`}"/>`;
  el.querySelector("text").textContent = texto;
  capaPulsos.appendChild(el);
  const ancho = el.querySelector("text").getComputedTextLength() + 10;
  el.querySelector("rect").setAttribute("width", ancho.toFixed(1));
  el.querySelector("rect").setAttribute("x", (-ancho / 2).toFixed(1));
  const dur = Math.min(2600, 700 + total * 2.2);
  pulsos.push({ el, cartel: el.firstChild, ancho, alto: 0, pts, largos, total, inicio: performance.now() + retraso, dur });
  correr();
  return retraso + dur;
}

let cuadro = 0;
function paso(ahora) {
  for (let i = pulsos.length - 1; i >= 0; i--) {
    const p = pulsos[i];
    const t = (ahora - p.inicio) / p.dur;
    if (t < 0) continue;
    if (t >= 1) {
      p.el.remove();
      pulsos.splice(i, 1);
      continue;
    }
    const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const d = e * p.total;
    let k = 1;
    while (k < p.largos.length - 1 && p.largos[k] < d) k++;
    const tramo = p.largos[k] - p.largos[k - 1] || 1;
    const u = (d - p.largos[k - 1]) / tramo;
    const x = p.pts[k - 1][0] + (p.pts[k][0] - p.pts[k - 1][0]) * u;
    const y = p.pts[k - 1][1] + (p.pts[k][1] - p.pts[k - 1][1]) * u;
    p.x = x;
    p.y = y;
    p.el.setAttribute("transform", `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
    p.el.style.opacity = String(Math.min(1, t * 8, (1 - t) * 8));
  }
  apilarCarteles(ahora);
  const dt = 1 / 60;
  aguja += quieto.matches ? agujaMeta - aguja : (agujaMeta - aguja) * (1 - Math.exp(-dt / 0.35));
  if (Math.abs(agujaMeta - aguja) < 0.001) aguja = agujaMeta;
  svg.querySelector("[data-aguja]").setAttribute("d", agujaEn(aguja));
  cuadro = pulsos.length || aguja !== agujaMeta ? requestAnimationFrame(paso) : 0;
}
function apilarCarteles(ahora) {
  const puestos = [];
  for (const p of pulsos) {
    if (p.x === undefined || ahora < p.inicio) continue;
    let meta = 0;
    while (puestos.some((q) => Math.abs(q.x - p.x) < (q.ancho + p.ancho) / 2 + 2 && Math.abs(q.y + q.meta - (p.y + meta)) < 13)) meta -= 13;
    const oculto = meta < -26;
    if (!oculto) puestos.push({ x: p.x, y: p.y, ancho: p.ancho, meta });
    p.alto += (Math.max(meta, -26) - p.alto) * 0.3;
    p.cartel.setAttribute("transform", `translate(0 ${p.alto.toFixed(1)})`);
    p.cartel.style.opacity = oculto ? "0" : "1";
  }
}

const correr = () => {
  if (!cuadro) cuadro = requestAnimationFrame(paso);
};

function agujaEn(share) {
  const d = GEO.dial;
  const ang = d.from + d.span * share;
  const punta = [d.x + Math.sin(ang) * (d.r - 5), d.y - Math.cos(ang) * (d.r - 5)];
  const cola = [d.x - Math.sin(ang) * 3.4, d.y + Math.cos(ang) * 3.4];
  return lineOnTop(cola, punta, d.top + 0.2, P);
}

function mensajes() {
  const nodos = estado.nodos || [];
  const primario = nodos.find((n) => n.rol === "primario");
  const ahora = Date.now();
  const backups = nodos.filter((n) => primario && n.id !== primario.id && n.responde);
  backups.forEach((n, k) => lanzar(ruta(`nodo${primario.id}`, `nodo${n.id}`), { de: `nodo${primario.id}`, texto: etiqueta("latido", `nodo${primario.id}`, `nodo${n.id}`), r: 1.7, retraso: k * 350 }));

  const antes = anterior && (anterior.nodos || []).find((n) => primario && n.id === primario.id);
  if (primario && antes && antes.epoca !== primario.epoca) {
    backups.forEach((n, k) => lanzar(ruta(`nodo${primario.id}`, `nodo${n.id}`), { de: `nodo${primario.id}`, texto: etiqueta(`coordinador · época ${primario.epoca}`, `nodo${primario.id}`, `nodo${n.id}`), forma: "anillo", retraso: 200 + k * 350 }));
    anotar(ahora, `nodo${primario.id}`, "todos", `coordinador · época ${primario.epoca}`, "deducido");
  }
  if (!primario && nodos.some((n) => n.responde)) {
    for (const n of nodos) for (const m of nodos) if (n.responde && m.id > n.id) lanzar(ruta(`nodo${n.id}`, `nodo${m.id}`), { de: `nodo${n.id}`, texto: etiqueta("elección", `nodo${n.id}`, `nodo${m.id}`), forma: "anillo" });
  }

  if (estado.telemetria) {
    if (ahora - ultimoOtlp >= 5000) {
      ultimoOtlp = ahora;
      nodos.filter((n) => n.responde).forEach((n, k) => lanzar(ruta(`nodo${n.id}`, "collector"), { de: `nodo${n.id}`, texto: etiqueta("OTLP", `nodo${n.id}`, "collector"), r: 2, retraso: k * 300 }));
      [["jaeger", "trazas"], ["prometheus", "métricas"], ["loki", "logs"]].forEach(([destino, que], k) => lanzar(ruta("collector", destino), { de: "collector", texto: etiqueta(que, "collector", destino), r: 2, retraso: 1800 + k * 300 }));
    }
    const nuevos = (estado.mensajes || []).filter((m) => {
      const clave = `${m.ms}|${m.de}|${m.a}|${m.tipo}`;
      if (vistos.has(clave)) return false;
      vistos.add(clave);
      return !!anterior;
    });
    const llegada = {};
    for (const m of nuevos) {
      const texto = textoDe(m);
      const retraso = Math.min(2000, m.ms - nuevos[0].ms);
      anotar(m.ms, m.de, m.a, texto, "traza");
      if (m.de.startsWith("cliente-")) llegada[m.seq] = lanzar(rutaCliente((estado.clientes || []).findIndex((c) => c.nombre === m.de.slice(8)), m.a), { de: m.de, texto: etiqueta(texto, m.de, m.a), r: 2.8, retraso });
      else lanzar(ruta(m.de, m.a), { de: m.de, texto: etiqueta(texto, m.de, m.a), forma: /elección|coordinador/.test(texto) ? "anillo" : "punto", retraso: Math.max(retraso, llegada[m.seq] || 0) });
    }
    if (vistos.size > 4000) vistos = new Set([...vistos].slice(-2000));
    return;
  }

  const antesPrim = anterior && (anterior.nodos || []).find((n) => n.rol === "primario");
  if (!primario || !antesPrim || antesPrim.epoca !== primario.epoca) return;
  const desde = antesPrim.ultimo_seq || 0;
  const nuevas = Math.min(3, (primario.ultimo_seq || 0) - desde);
  const jugando = (estado.clientes || []).map((c, i) => ({ c, i })).filter(({ c, i }) => c.estado === "en_juego" && i < 4);
  const yo = `nodo${primario.id}`;
  for (let r = 0; r < nuevas; r++) {
    const op = desde + r + 1;
    const quien = jugando.length ? jugando[turnoJugador++ % jugando.length] : null;
    if (quien) {
      const de = `cliente-${quien.c.nombre}`;
      lanzar(rutaCliente(quien.i, yo), { de, texto: etiqueta(`jugada op ${op}`, de, yo), r: 2.8, retraso: r * 500 });
      anotar(ahora, de, yo, `jugada op ${op}`, "deducido");
    }
    backups.forEach((n, k) => lanzar(ruta(yo, `nodo${n.id}`), { de: yo, texto: etiqueta(`réplica op ${op}`, yo, `nodo${n.id}`), retraso: r * 500 + 1200 + k * 350 }));
  }
}

async function pedir() {
  if (DEMO) return simular();
  const respuesta = await fetch("api/estado", { cache: "no-store" });
  return respuesta.json();
}

async function ciclo() {
  try {
    const nuevo = await pedir();
    if (nuevo && nuevo.hora) {
      anterior = estado;
      estado = nuevo;
      aplicar();
      mensajes();
      correr();
    }
  } catch (error) {
    readout.textContent = "sin conexión con el visor";
  }
  setTimeout(ciclo, 1000);
}

let sobre = null;
svg.addEventListener("pointermove", (ev) => {
  const g = ev.target.closest("[data-part]");
  if (g === sobre) return;
  sobre?.removeAttribute("data-sobre");
  sobre = g;
  g?.setAttribute("data-sobre", "");
});
svg.addEventListener("pointerleave", () => {
  sobre?.removeAttribute("data-sobre");
  sobre = null;
});
svg.addEventListener("click", (ev) => {
  const g = ev.target.closest("[data-part]");
  if (!g) return;
  elegido = g.dataset.part;
  mostrarFicha();
});

const demo = { t0: Date.now(), seq: 412, epoca: 6, primario: 3, mudanza: null };
function simular() {
  const s = (Date.now() - demo.t0) / 1000;
  const ciclo = s % 60;
  const cae = ciclo > 22 && ciclo < 48;
  const lugar = { nodo1: "maquina2", nodo2: "maquina1", nodo3: "maquina3", collector: "maquina2", jaeger: "maquina3", prometheus: "maquina1", loki: "maquina3", grafana: "maquina1", visor: "maquina2" };
  const victima = "maquina3";
  const caidos = cae ? Object.keys(lugar).filter((c) => lugar[c] === victima) : [];
  const pods = [];
  for (const [comp, maq] of Object.entries(lugar)) {
    if (caidos.includes(comp) && ciclo > 30) {
      const nueva = comp === "nodo3" || comp === "loki" ? "maquina2" : "maquina1";
      pods.push({ nombre: `${comp}-viejo`, componente: comp, maquina: maq, fase: "Terminating", listo: false, reinicios: 0, ip: null });
      pods.push({ nombre: `${comp}-nuevo`, componente: comp, maquina: nueva, fase: ciclo > 34 ? "Running" : "Pending", listo: ciclo > 36, reinicios: 0, ip: "10.42.2.9" });
    } else {
      pods.push({ nombre: `${comp}-7f9c`, componente: comp, maquina: maq, fase: "Running", listo: !caidos.includes(comp), reinicios: 0, ip: "10.42.0.12" });
    }
  }
  if (cae && demo.primario === 3 && ciclo > 26) {
    demo.primario = 2;
    demo.epoca += 1;
  }
  if (!cae && demo.primario === 2 && ciclo < 2) demo.primario = 3;
  demo.seq += Math.random() < 0.6 ? 1 : 0;
  const nodo3Vivo = !cae || ciclo > 36;
  const nodos = [1, 2, 3].map((id) => {
    const responde = id !== 3 || nodo3Vivo;
    const huerfano = cae && ciclo > 22 && ciclo <= 26;
    return { id, responde, rol: responde ? (id === demo.primario && !huerfano ? "primario" : "backup") : null, primario: responde ? (huerfano ? null : demo.primario) : null, epoca: responde ? demo.epoca : null, ultimo_seq: responde ? demo.seq - (id === 3 && cae ? 6 : 0) : null, reloj: responde ? 900 + demo.seq * 3 : null };
  });
  const mesas = [{ id_mesa: "a41f2c", jugadores: ["leo", "beto"], estado: "en_juego", marcador: [7, 9], numero_mano: 5 }, { id_mesa: "c09e11", jugadores: ["ana", null], estado: "esperando_rival", marcador: [0, 0], numero_mano: 0 }];
  return {
    hora: Date.now() / 1000,
    kubernetes: true,
    telemetria: false,
    maquinas: [{ nombre: "maquina1", ip: "172.30.0.11", lista: true, rol: "servidor" }, { nombre: "maquina2", ip: "172.30.0.12", lista: true, rol: "agente" }, { nombre: "maquina3", ip: "172.30.0.13", lista: !cae, rol: "agente" }],
    pods,
    nodos,
    mesas,
    clientes: [{ nombre: "ana", mesa: "c09e11", estado: "esperando_rival", trazado: false }, { nombre: "beto", mesa: "a41f2c", estado: "en_juego", trazado: false }, { nombre: "leo", mesa: "a41f2c", estado: "en_juego", trazado: false }],
    mensajes: [],
  };
}

new IntersectionObserver((entradas) => {
  if (entradas[entradas.length - 1].isIntersecting) correr();
}).observe(svg);
ciclo();
