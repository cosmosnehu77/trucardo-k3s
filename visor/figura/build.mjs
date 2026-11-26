import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SALIDA = join(HERE, "..", "pagina", "index.html");

const COLORES = {
  nodo1: ["#e5484d", "Nodo 1"],
  nodo2: ["#1d6fe0", "Nodo 2"],
  nodo3: ["#16a34a", "Nodo 3"],
  control: ["#7c3aed", "Plano de control"],
  collector: ["#c026d3", "Collector"],
  jaeger: ["#0891b2", "Jaeger"],
  prometheus: ["#f97316", "Prometheus"],
  loki: ["#eab308", "Loki"],
  grafana: ["#a16207", "Grafana"],
  visor: ["#27272a", "Visor"],
  red: ["#64748b", "Red"],
  clientes: ["#ec4899", "Jugadores"],
};

const WIDTH = 1120;
const HEIGHT = 660;

const PLATE = { x: -330, y: -118, w: 740, d: 262, r: 10 };
const PLATE_H = 10;
const FOOT_H = 5;

const MW = 165;
const MD = 110;
const MY = -90;
const MH = 72;
const PLINTH = 6;
const FRONT = MY + MD;
const MACHINES = [-300, -110, 80];

const CARD = { y: -53, d: 5, z0: 78, z1: 128, half: 19 };
const CARD_X = [37, 82, 127];
const SOCKET_X = [22, 46, 70, 94, 118, 142];
const SOCKET_Y = 2;
const MODULES = ["collector", "jaeger", "prometheus", "loki", "grafana", "visor"];
const JACK_X = 22;
const JACK_Z = 24;

const SWITCH = { x: -300, y: 52, w: 555, d: 34, r: 3 };
const SWITCH_H = 12;
const PORT_Y = 61;
const CHANNEL_Y = 79;

const MAT = { x: 280, y: -84, w: 116, d: 200, r: 6 };
const MAT_H = 2.5;
const HUB = { x: 352, y: -72, w: 30, d: 182, r: 3 };
const HUB_H = 12;
const CONSOLES = [-66, -24, 18, 60];
const UPLINK_HUB = [367, 100];

const DIAL = { x: -300 + 128, y: -70, r: 20, z: 150, h: 8 };
const STORE = { x: -300 + 30, y: -72, r: 11, h: 22 };
const DNS = { x: -300 + 62, y: -76, w: 16, d: 12 };

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [DIAL.x, DIAL.y - DIAL.r, DIAL.z + DIAL.h + 4], [MACHINES[2] + MW, MY, CARD.z1 + 4]],
  WIDTH,
  HEIGHT,
  { pad: 26, azimuth: 58 },
);

const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const part = (id, body, extra = "") => `<g data-part="${id}"${extra}>${body}</g>`;
const byDepth = (points) => [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const onY = (points, y) => k.pathOf(points.map(([x, z]) => at([x, y, z])));
const onX = (points, x) => k.pathOf(points.map(([y, z]) => at([x, y, z])));
const rectY = (x0, x1, z0, z1, y, r = 0.8) => k.pathOf(k.roundedPlan({ x: x0, y: z0, w: x1 - x0, d: z1 - z0, r }, 3).map(([x, z]) => at([x, y, z])), true);
const rectX = (y0, y1, z0, z1, x, r = 0.8) => k.pathOf(k.roundedPlan({ x: y0, y: z0, w: y1 - y0, d: z1 - z0, r }, 3).map(([y, z]) => at([x, y, z])), true);

function plate() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 26))) {
    out.push(S(k.cylinder(x, y, 8, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 6.2, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 6), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.4, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.55 }));
  const strip = { x: -300, y: PLATE.y + PLATE.d - 20, w: 560, d: 8, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 5, strip.x + strip.w - 5, 5, 5, strip.y + 0.8, 0.6, [2.2, 4.2], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(D([at([strip.x + 2.5, strip.y + 4, 0.6]), at([strip.x + strip.w - 2.5, strip.y + 4, 0.6])], { size: 0.45 }));
  const label = { x: 280, y: PLATE.y + PLATE.d - 22, w: 60, d: 12, r: 1.5 };
  out.push(S(k.slabOf(label, 0, 0.8, P, 3), { tone: "lo" }));
  out.push(L([3, 6, 9].map((dy) => k.lineOnTop([label.x + 5, label.y + dy], [label.x + label.w - 5 - dy * 2, label.y + dy], 0.8, P)).join(""), { tone: "faint", free: true }));
  return part("placa", out.join(""));
}

function chassis(index) {
  const x0 = MACHINES[index];
  const body = { x: x0, y: MY, w: MW, d: MD, r: 4 };
  const plinth = k.insetPlan(body, 4);
  const out = [`<path class="iso-halo" d="${k.haloOf(body, 0, 2, P)}"/>`];
  out.push(S(k.slabOf(plinth, 0, PLINTH, P, 4), { tone: "lo" }));
  const vents = [];
  for (let i = 0; i < 9; i++) vents.push(rectY(x0 + 70 + i * 9, x0 + 73 + i * 9, 30, 52, FRONT, 1.2));
  const sideVents = [];
  for (let i = 0; i < 7; i++) sideVents.push(rectX(MY + 16 + i * 11, MY + 19 + i * 11, 26, 48, x0 + MW, 1.2));
  const plateLabel = rectY(x0 + 36, x0 + 62, 36, 50, FRONT, 1);
  const inner = [
    L(k.sideSeam(body, MH - 8, P, 4), { tone: "faint" }),
    L(k.sideSeam(body, PLINTH + 6, P, 4), { tone: "faint" }),
    L(vents.join("") + sideVents.join(""), { tone: "lo" }),
    L(plateLabel, { tone: "lo" }),
    L([40, 43.5].map((z) => onY([[x0 + 40, z], [x0 + 56 - (z - 40) * 2, z]], FRONT)).join(""), { tone: "faint", free: true }),
  ].join("");
  out.push(S(k.slabOf(body, PLINTH, MH - PLINTH, P, 4, 0.8), { tone: "mid", inner }));
  out.push(L(k.planOutline(k.insetPlan(body, 5), MH, P, 4), { tone: "faint" }));
  out.push(D(k.corners(body, 3.5).map(([x, y]) => at([x, y, MH])), { size: 0.5 }));
  out.push(D([at([x0 + 12, FRONT, 52])], { size: 2.2, tone: "lo" }), `<g data-led>${D([at([x0 + 12, FRONT, 52])], { size: 1.5, tone: "lit" })}</g>`);
  out.push(L(k.sideRing([x0 + 12, FRONT, 52], 3.4, "y", P, 20), { tone: "lo" }));
  const jack = { x: x0 + JACK_X - 8, y: FRONT, w: 16, d: 4, r: 1 };
  out.push(S(k.slabOf(jack, JACK_Z - 6, 12, P, 3, 0.4), { tone: "mid", inner: L(rectY(jack.x + 4, jack.x + 12, JACK_Z - 3, JACK_Z + 3, FRONT + 4), { tone: "lo" }) }));
  out.push(D([at([jack.x + 3, FRONT + 4, JACK_Z + 4]), at([jack.x + 13, FRONT + 4, JACK_Z + 4])], { size: 0.45 }));
  return out.join("");
}

function cageBack(index) {
  const x0 = MACHINES[index];
  const rail = { x: x0 + 10, y: -60, w: 145, d: 16, r: 2 };
  const out = [S(k.slabOf(rail, MH, 6, P, 3, 0.5), { tone: "mid" })];
  out.push(L(CARD_X.map((cx) => k.planOutline({ x: x0 + cx - 20, y: -54, w: 40, d: 7, r: 0.8 }, MH + 6, P, 2)).join(""), { tone: "lo" }));
  out.push(D([at([rail.x + 4, rail.y + 8, MH + 6]), at([rail.x + rail.w - 4, rail.y + 8, MH + 6])], { size: 0.45 }));
  out.push(S(k.slabOf({ x: x0 + 4, y: -62, w: 5, d: 20, r: 1 }, MH, 62, P, 3, 0.4), { tone: "mid" }));
  out.push(D([at([x0 + 6.5, -58, MH + 62]), at([x0 + 6.5, -46, MH + 62])], { size: 0.45 }));
  return out.join("");
}

function cageFront(index) {
  const x0 = MACHINES[index];
  const out = [S(k.slabOf({ x: x0 + 156, y: -62, w: 5, d: 20, r: 1 }, MH, 62, P, 3, 0.4), { tone: "mid" })];
  out.push(D([at([x0 + 158.5, -58, MH + 62]), at([x0 + 158.5, -46, MH + 62])], { size: 0.45 }));
  return out.join("");
}

function card(node, index) {
  const cx = MACHINES[index] + CARD_X[node - 1];
  const front = CARD.y + CARD.d;
  const plan = { x: cx - CARD.half, y: CARD.y, w: CARD.half * 2, d: CARD.d, r: 1 };
  const inner = [
    L(rectY(cx - 15, cx - 1, 88, 100, front, 1), { tone: "lo" }),
    L([92, 95, 98].map((z) => onY([[cx - 13, z], [cx - 3 - (z - 92), z]], front)).join(""), { tone: "faint", free: true }),
    L(onY([[cx + 12, 84], [cx + 12, 120]], front), { tone: "faint" }),
    L(onY([[cx + 9, 84], [cx + 15, 84]], front) + onY([[cx + 9, 120], [cx + 15, 120]], front), { tone: "lo" }),
  ].join("");
  const out = [S(k.slabOf(plan, CARD.z0, CARD.z1 - CARD.z0, P, 2, 0.4), { tone: "hi", inner })];
  out.push(`<path class="iso-line" data-tone="lit" data-log d="${onY([[cx + 12, 84], [cx + 12, 84.1]], front + 0.05)}" style="stroke-width:2.2"/>`);
  out.push(D([at([cx - 11, front, 117])], { size: 2.4, tone: "lo" }), `<g data-lamp>${D([at([cx - 11, front, 117])], { size: 1.7, tone: "lit" })}</g>`);
  out.push(L(k.sideRing([cx - 11, front, 117], 3.6, "y", P, 20), { tone: "lo" }));
  out.push(D([81, 81, 81, 81, 81, 81, 81].map((z, i) => at([cx - 15 + i * 5, front, z])), { size: 0.55, tone: "mid" }));
  out.push(D([at([cx - 16, front, 125]), at([cx + 16, front, 125])], { size: 0.45 }));
  out.push(S(k.slabOf({ x: cx - 16, y: CARD.y - 1, w: 9, d: 7, r: 1 }, CARD.z1, 3.5, P, 2, 0.3), { tone: "mid" }));
  out.push(S(k.slabOf({ x: cx + 7, y: CARD.y - 1, w: 9, d: 7, r: 1 }, CARD.z1, 3.5, P, 2, 0.3), { tone: "mid" }));
  return part(`carta-${node}-${index}`, out.join(""), ` data-pod="nodo${node}" data-color="nodo${node}" data-en="${index}" data-off`);
}

function socket(x, y) {
  return S(k.cylinder(x, y, 8.5, MH, 1.6, P, 28), { tone: "lo" }) + L(k.ring(x, y, 6, MH + 1.6, P, 24), { tone: "faint" });
}

function module(name, index) {
  const x = MACHINES[index] + SOCKET_X[MODULES.indexOf(name)];
  const y = SOCKET_Y;
  const z = MH + 1.6;
  const out = [];
  if (name === "collector") {
    out.push(S(k.cylinder(x, y, 6.6, z, 4, P, 28, 0.4), { tone: "hi" }));
    out.push(S(k.cylinder(x, y, 4.2, z + 4, 4, P, 24), { tone: "hi" }));
    out.push(S(k.cylinder(x, y, 2.4, z + 8, 7, P, 20, 0.3), { tone: "hi" }));
    out.push(L(k.ring(x, y, 1.2, z + 15, P, 16), { tone: "lo" }));
  } else if (name === "jaeger") {
    const plan = { x: x - 6.5, y: y - 6.5, w: 13, d: 13, r: 1.5 };
    out.push(S(k.slabOf(plan, z, 11, P, 3, 0.5), { tone: "hi", inner: L(k.sideSeam(plan, z + 4, P, 3), { tone: "faint" }) }));
    out.push(S(k.cylinder(x, y, 3.8, z + 11, 2.4, P, 24), { tone: "mid" }));
    out.push(L(k.ring(x, y, 2.2, z + 13.4, P, 20), { tone: "lo" }), D([at([x, y, z + 13.4])], { size: 0.7, tone: "hi" }));
  } else if (name === "prometheus") {
    out.push(S(k.cylinder(x, y, 6.4, z, 15, P, 32, 0.5), { tone: "hi", inner: L([4, 8, 12].map((h) => k.sideArc(x, y, 6.4, z + h, P, 20)).join(""), { tone: "faint" }) }));
    out.push(L(k.ring(x, y, 3.6, z + 15, P, 24), { tone: "lo" }));
  } else if (name === "loki") {
    [0, 5, 10].forEach((h) => out.push(S(k.cylinder(x, y, 6.6 - h * 0.08, z + h, 3.4, P, 28, 0.3), { tone: "hi" })));
    out.push(S(k.cylinder(x, y, 1.6, z + 13.4, 2.6, P, 16), { tone: "mid" }));
  } else if (name === "grafana") {
    out.push(S(k.cylinder(x, y, 6.8, z, 6, P, 32, 0.5), { tone: "hi" }));
    const ticks = k.radialTicks(x, y, 5.6, 16, 4, z + 6, [1, 2], P, -Math.PI * 0.75, Math.PI * 1.5);
    out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
    out.push(L(k.lineOnTop([x, y], [x + 3.2, y - 2.6], z + 6, P), { tone: "hi", free: "end" }), D([at([x, y, z + 6])], { size: 0.6, tone: "hi" }));
  } else if (name === "visor") {
    const plan = { x: x - 7, y: y - 5, w: 14, d: 10, r: 1.5 };
    out.push(S(k.slabOf(plan, z, 9, P, 3, 0.5), { tone: "hi" }));
    out.push(S(k.slabOf(k.insetPlan(plan, 2), z + 9, 0.6, P, 3), { tone: "lo", crease: "none" }));
    out.push(D(k.dotGrid(x - 3.5, y - 1.5, 4, 2, 2.3, z + 9.6, P), { size: 0.35, tone: "mid" }));
  }
  return part(`modulo-${name}-${index}`, out.join(""), ` data-pod="${name}" data-color="${name}" data-en="${index}" data-off`);
}

function serverHead() {
  const out = [];
  const store = [];
  store.push(S(k.cylinder(STORE.x, STORE.y, STORE.r + 2, MH, 2, P, 32), { tone: "lo" }));
  store.push(S(k.cylinder(STORE.x, STORE.y, STORE.r, MH + 2, STORE.h, P, 40, 0.6), { tone: "hi", inner: L([6, 12, 18].map((h) => k.sideArc(STORE.x, STORE.y, STORE.r, MH + 2 + h, P, 28)).join(""), { tone: "faint" }) }));
  store.push(L(k.ring(STORE.x, STORE.y, STORE.r - 3, MH + 2 + STORE.h, P, 32), { tone: "lo" }));
  store.push(D([at([STORE.x, STORE.y, MH + 2 + STORE.h])], { size: 0.8, tone: "mid" }));
  out.push(part("almacen", store.join(""), ' data-color="control"'));
  const dnsPlan = { x: DNS.x - DNS.w / 2, y: DNS.y - DNS.d / 2, w: DNS.w, d: DNS.d, r: 1.5 };
  const dns = [S(k.slabOf(dnsPlan, MH, 12, P, 3, 0.5), { tone: "hi", inner: L(k.sideSeam(dnsPlan, MH + 5, P, 3), { tone: "faint" }) })];
  dns.push(D(k.dotGrid(DNS.x - 4.5, DNS.y - 2, 4, 2, 3, MH + 12, P), { size: 0.4, tone: "mid" }));
  out.push(part("coredns", dns.join(""), ' data-color="control"'));
  const dial = [];
  dial.push(S(k.slabOf({ x: DIAL.x - 9, y: DIAL.y - 9, w: 18, d: 18, r: 2 }, MH, 4, P, 3, 0.5), { tone: "mid" }));
  dial.push(D(k.corners({ x: DIAL.x - 9, y: DIAL.y - 9, w: 18, d: 18 }, 2.6).map(([x, y]) => at([x, y, MH + 4])), { size: 0.45 }));
  dial.push(S(k.cylinder(DIAL.x, DIAL.y, 3.2, MH + 4, DIAL.z - MH - 6, P, 20), { tone: "mid", crease: "none", inner: L([100, 124].map((z) => k.sideArc(DIAL.x, DIAL.y, 3.2, z, P, 12)).join(""), { tone: "faint" }) }));
  dial.push(S(k.slabOf({ x: DIAL.x - 5, y: DIAL.y - 5, w: 10, d: 10, r: 1.5 }, DIAL.z - 4, 4, P, 3), { tone: "mid" }));
  dial.push(S(k.cylinder(DIAL.x, DIAL.y, DIAL.r, DIAL.z, DIAL.h, P, 64, 0.8), { tone: "hi", crease: "lo" }));
  const top = DIAL.z + DIAL.h;
  dial.push(L(k.knurl(DIAL.x, DIAL.y, DIAL.r, top - 3.4, top, 80, P, 0.3), { tone: "lo" }));
  dial.push(L(k.sideArc(DIAL.x, DIAL.y, DIAL.r, top - 3.4, P, 40), { tone: "faint" }));
  dial.push(L(k.ring(DIAL.x, DIAL.y, DIAL.r - 2.2, top, P, 64), { tone: "lo" }));
  const ticks = k.radialTicks(DIAL.x, DIAL.y, DIAL.r - 3, 15, 5, top, [1.4, 3.2], P, DIAL_FROM, DIAL_SPAN);
  dial.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  dial.push(L(needleAt(1), { tone: "faint", free: "start" }).replace("<path", '<path data-deseado'));
  dial.push(`<path class="iso-line" data-tone="lit" data-free="start" data-aguja d="${needleAt(0)}" style="stroke-width:1.1"/>`);
  dial.push(L(k.ring(DIAL.x, DIAL.y, 1.8, top, P, 16), { tone: "mid" }), D([at([DIAL.x, DIAL.y, top + 0.1])], { size: 0.8, tone: "hi" }));
  out.push(part("control", dial.join(""), ' data-color="control"'));
  return out.join("");
}

const DIAL_FROM = -Math.PI * 0.6;
const DIAL_SPAN = Math.PI * 1.2;
const DIAL_TOP = DIAL.z + DIAL.h;
function needleAt(share) {
  const angle = DIAL_FROM + DIAL_SPAN * share;
  const tip = [DIAL.x + Math.sin(angle) * (DIAL.r - 5), DIAL.y - Math.cos(angle) * (DIAL.r - 5)];
  const tail = [DIAL.x - Math.sin(angle) * 3.4, DIAL.y + Math.cos(angle) * 3.4];
  return k.lineOnTop(tail, tip, DIAL_TOP + 0.2, P);
}

function switchBar() {
  const out = [S(k.slabOf(SWITCH, 0, SWITCH_H, P, 3, 0.6), { tone: "mid", inner: L(k.sideSeam(SWITCH, 4, P, 3), { tone: "faint" }) })];
  const channel = { x: SWITCH.x + 6, y: CHANNEL_Y - 2.5, w: SWITCH.w - 12, d: 5, r: 1 };
  out.push(S(k.slabOf(channel, SWITCH_H, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(channel.x + 4, channel.x + channel.w - 4, 6, 5, channel.y + 0.6, SWITCH_H + 0.6, [1.6, 3], P);
  out.push(L(ticks.minor, { tone: "faint" }), L(ticks.major, { tone: "lo" }));
  const ports = MACHINES.map((x0) => x0 + JACK_X);
  ports.forEach((px, i) => {
    const plan = { x: px - 6, y: PORT_Y - 4, w: 12, d: 8, r: 1 };
    out.push(S(k.slabOf(plan, SWITCH_H, 1, P, 2), { tone: "lo" }));
    out.push(L(k.planOutline(k.insetPlan(plan, 2), SWITCH_H + 1, P, 2), { tone: "faint" }));
    out.push(`<g data-enlace="${i}">${D([at([px + 10, PORT_Y, SWITCH_H])], { size: 1.1, tone: "lo" })}</g>`);
  });
  for (let i = 0; i < 6; i++) out.push(L(rectY(SWITCH.x + 400 + i * 7, SWITCH.x + 404 + i * 7, 3, 9, SWITCH.y + SWITCH.d, 1), { tone: "lo" }));
  out.push(D(k.corners(SWITCH, 3).map(([x, y]) => at([x, y, SWITCH_H])), { size: 0.45 }));
  const endJack = { x: SWITCH_END[0], y: SWITCH_END[1] - 6, w: 3, d: 12, r: 0.8 };
  out.push(S(k.slabOf(endJack, 2.5, 7, P, 2, 0.3), { tone: "mid", inner: L(rectX(endJack.y + 3, endJack.y + 9, 4, 8, endJack.x + 3), { tone: "lo" }) }));
  out.push(`<g data-enlace="3">${D([at([SWITCH_END[0], SWITCH_END[1] + 9, 9])], { size: 1.1, tone: "lo" })}</g>`);
  return part("switch", out.join(""), ' data-color="red"');
}

const jackFront = (index) => [MACHINES[index] + JACK_X, FRONT + 4, JACK_Z];
const cableRoute = (index) => {
  const x = MACHINES[index] + JACK_X;
  return [jackFront(index), [x, FRONT + 18, JACK_Z], [x, PORT_Y - 2, SWITCH_H + 10], [x, PORT_Y, SWITCH_H + 1]];
};

function cable(index) {
  const points = cableRoute(index).map(at);
  return part(`cable-${index}`, k.wireSvg(points[0], points[points.length - 1], { via: points.slice(1, -1), tone: "mid", size: 1.1 }), ' data-color="red"');
}

function clientMat() {
  const out = [S(k.slabOf(MAT, 0, MAT_H, P, 6, 0.5), { tone: "lo" })];
  out.push(L(k.planOutline(k.insetPlan(MAT, 4), MAT_H, P, 6), { tone: "faint" }));
  return part("mesa", out.join(""));
}

function hub() {
  const out = [S(k.slabOf(HUB, MAT_H, HUB_H, P, 3, 0.5), { tone: "mid", inner: L(k.sideSeam(HUB, MAT_H + 4, P, 3), { tone: "faint" }) })];
  const top = MAT_H + HUB_H;
  [UPLINK_HUB[1]].forEach((y) => {
    const plan = { x: HUB.x + 7, y: y - 4, w: 16, d: 8, r: 1 };
    out.push(S(k.slabOf(plan, top, 1, P, 2), { tone: "lo" }));
    out.push(L(k.planOutline(k.insetPlan(plan, 2), top + 1, P, 2), { tone: "faint" }));
  });
  out.push(D(k.corners(HUB, 3).map(([x, y]) => at([x, y, top])), { size: 0.45 }));
  return part("hub", out.join(""), ' data-color="red"');
}

const consoleRoute = (i) => [[331, CONSOLES[i] + 15, MAT_H + 4], [HUB.x, CONSOLES[i] + 15, MAT_H + 4]];
const SWITCH_END = [SWITCH.x + SWITCH.w, PORT_Y + 8, 6];
const uplinkRoute = () => [[UPLINK_HUB[0], UPLINK_HUB[1], MAT_H + HUB_H + 1], [UPLINK_HUB[0], UPLINK_HUB[1], MAT_H + HUB_H + 9], [UPLINK_HUB[0] - 6, UPLINK_HUB[1], MAT_H + HUB_H + 9], [SWITCH_END[0] + 14, SWITCH_END[1], 6], [SWITCH_END[0] + 3, SWITCH_END[1], 6]];

function consoleUnit(i) {
  const y = CONSOLES[i];
  const base = { x: 288, y, w: 43, d: 32, r: 2.5 };
  const out = [`<path class="iso-halo" d="${k.haloOf(base, MAT_H, 1, P)}"/>`];
  out.push(S(k.slabOf(base, MAT_H, 6, P, 3, 0.6), { tone: "mid" }));
  out.push(D(k.dotGrid(295, y + 10, 8, 4, 4, MAT_H + 6, P), { size: 0.55, tone: "lo" }));
  const screen = { x: 291, y: y + 1.5, w: 37, d: 4, r: 1 };
  const front = screen.y + screen.d;
  out.push(S(k.slabOf(screen, MAT_H + 6, 24, P, 2, 0.4), { tone: "hi", inner: L(rectY(294, 325, MAT_H + 10, MAT_H + 27, front, 1.5), { tone: "lo" }) }));
  out.push(`<path class="iso-fill" data-pantalla d="${rectY(295, 324, MAT_H + 11, MAT_H + 26, front + 0.05, 1.2)}" style="fill:var(--anatomy-lit);opacity:0"/>`);
  out.push(D([at([326, front, MAT_H + 8])], { size: 1, tone: "lo" }));
  const route = consoleRoute(i).map(at);
  out.push(k.wireSvg(route[0], route[route.length - 1], { via: route.slice(1, -1), tone: "lo", size: 0.9 }));
  return part(`consola-${i}`, out.join(""), ` data-consola="${i}" data-color="clientes"`);
}

function uplink() {
  const points = uplinkRoute().map(at);
  return part("uplink", k.wireSvg(points[0], points[points.length - 1], { via: points.slice(1, -1), tone: "mid", size: 1.1 }), ' data-color="red"');
}

const body = [plate()];
MACHINES.forEach((_, index) => {
  const pieces = [chassis(index), cageBack(index)];
  if (index === 0) pieces.push(serverHead());
  pieces.push([1, 2, 3].map((node) => card(node, index)).join(""));
  pieces.push(cageFront(index));
  pieces.push(SOCKET_X.map((sx) => socket(MACHINES[index] + sx, SOCKET_Y)).join(""));
  pieces.push(MODULES.map((name) => module(name, index)).join(""));
  body.push(part(`maquina-${index}`, pieces.join(""), ` data-maquina="${index}"`));
});
body.push(switchBar(), MACHINES.map((_, index) => cable(index)).join(""), clientMat(), hub());
body.push(CONSOLES.map((_, i) => consoleUnit(i)).join(""), uplink(), `<g data-relojes></g><g data-pulsos></g>`);

const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label: "Banco con tres gabinetes en fila: las máquinas del cluster k3s. Cada gabinete tiene una jaula con tres bahías para las placas de los nodos de Trucardo y una fila de zócalos para los módulos de observabilidad y el visor. El primero lleva el plano de control: un dial que marca los Pods listos contra los deseados, el almacén de estado y CoreDNS. Delante corre el switch de la red, y a la derecha una mesa con las consolas de los jugadores conectadas por un hub.",
  body,
});

const toWorld = (route) => route.map((p) => p.map((v) => Math.round(v * 100) / 100));
const GEO = {
  P,
  machines: MACHINES,
  cardX: CARD_X,
  card: CARD,
  dial: { ...DIAL, top: DIAL_TOP, from: DIAL_FROM, span: DIAL_SPAN },
  cables: MACHINES.map((_, i) => toWorld(cableRoute(i))),
  ports: MACHINES.map((x0) => [x0 + JACK_X, PORT_Y, SWITCH_H + 1]),
  channelY: CHANNEL_Y,
  switchTop: SWITCH_H + 0.6,
  uplinkPort: [SWITCH_END[0] + 3, SWITCH_END[1], SWITCH_END[2]],
  uplink: toWorld(uplinkRoute()),
  consoles: CONSOLES.map((_, i) => toWorld(consoleRoute(i))),
  hubTop: MAT_H + HUB_H + 1,
  hubX: HUB.x + 15,
  front: FRONT + 4,
  mh: MH,
  socketX: SOCKET_X,
  socketY: SOCKET_Y,
  modules: MODULES,
  moduleTop: MH + 18,
  colores: Object.fromEntries(Object.entries(COLORES).map(([clave, [color]]) => [clave, color])),
};

const CSS = Object.entries(COLORES).map(([clave, [color]]) => `.visor [data-color="${clave}"]{--c:${color}}`).join("") + readFileSync(join(HERE, "visor.css"), "utf8");
const VIVO = readFileSync(join(HERE, "vivo.js"), "utf8");
const TEXTOS = readFileSync(join(HERE, "textos.js"), "utf8");
const kitScript = readFileSync(join(HERE, "kit", "iso-kit.mjs"), "utf8").replace(/^export /gm, "");

const plateBody = k.plateHtml({
  fig: "Trucardo en k3s",
  title: "Arquitectura en vivo",
  hint: "Clic en una pieza para ver qué hace",
  readout: "conectando…",
  keys: [
    { mark: "lit", label: "Lámpara del primario y LED de máquina lista" },
    { mark: "raised", label: "Pods con el color de su componente: el primario, pleno; los backups, tenues" },
    { mark: "dim", label: "En gris: máquina caída o Pod que todavía no está listo" },
  ],
  caption: "Cada placa aparece en el gabinete donde Kubernetes puso su Pod, y la barra de cada placa es cuánto del log tiene respecto del más adelantado. El dial del servidor marca cuántos nodos de Trucardo están listos (deseados: 3). Cada mensaje viaja con el color de quien lo manda y una etiqueta con qué lleva y de quién a quién. Con telemetría, las llamadas entre servicios salen de las trazas de Jaeger; sin ella, los latidos se deducen del rol y las réplicas, del avance de ultimo_seq. Los envíos OTLP al Collector se dibujan cada 5 s, que es cada cuánto exportan los nodos.",
  body: `<div class="iso-stage visor-stage" tabindex="0" aria-label="Arquitectura de Trucardo en k3s; cada pieza se puede elegir con clic">${svg}</div>`,
});

const FILTROS = [
  ["jugadas", "Jugadas", "clientes"],
  ["replicas", "Réplicas", "nodo1"],
  ["latidos", "Latidos", "nodo2"],
  ["epocas", "Épocas y elecciones", "control"],
  ["telemetria", "Telemetría", "collector"],
  ["relojes", "Relojes de Lamport", "visor"],
  ["etiquetas", "Etiquetas", "red"],
  ["lenta", "Cámara lenta", "red"],
];
const filtros = `<fieldset class="visor-filtros"><legend>Mostrar</legend>${FILTROS.map(([clave, nombre, color]) => `<label data-color="${color}"><input type="checkbox" data-filtro="${clave}">${nombre}</label>`).join("")}</fieldset>`;
const leyenda = Object.entries(COLORES).map(([clave, [, nombre]]) => `<li data-color="${clave}"><i></i>${nombre}</li>`).join("");
const page = `<div class="visor">${filtros}${plateBody}<section class="visor-panel"><article class="visor-ficha" data-ficha aria-live="polite"></article><aside class="visor-lado"><h2>Colores</h2><ul class="visor-colores">${leyenda}</ul><h2>Jugadores</h2><ul data-jugadores></ul><h2>Mensajes</h2><ol data-mensajes></ol></aside></section></div>`;
const html = k.pageHtml({ title: "Visor de Trucardo", theme: "light", body: page, width: 1180, script: `${kitScript}\nconst GEO = ${JSON.stringify(GEO)};\n${TEXTOS}\n${VIVO}` })
  .replace("</style>", `${CSS}</style>`)
  .replace('<html lang="en">', '<html lang="es">');
writeFileSync(SALIDA, html);
console.log("escribí", SALIDA);
