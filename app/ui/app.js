// SteelCAD: interfaccia. Tutta la geometria arriva già calcolata dal motore (Python):
// qui si disegna, si seleziona e si mandano le modifiche. Niente calcoli di CAD in JS.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const DEV = new URLSearchParams(location.search).has('dev');
const num = (v, d = 1) => (v ?? 0).toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: 0 });
const kg = v => (v ?? 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

async function call(name, ...args) {
  if (!DEV) return window.pywebview.api[name](...args);
  const r = await fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args) });
  return r.json();
}

// le chiamate al motore vanno una alla volta, nell'ordine in cui le fai
let coda = Promise.resolve();
const inCoda = fn => (coda = coda.then(fn).catch(e => toast(String(e), 'err')));

let S = null;            // ultimo stato del progetto
let sceneVersion = 0;
let sel = null;          // { id, face, ids }
let hover = null;        // { id, face }
let showDims = true;
let primaVolta = true;
let nodes = [];          // nodi dello scheletro (dal motore)
let linkFrom = null;     // { st, key }: si sta collegando un nodo a un altro

// ===================================================================== viewer
const canvas = $('#c3d');
const view = $('#view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(window.devicePixelRatio);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 1, 1e7);
camera.up.set(0, 0, 1);
camera.position.set(3000, -4000, 2500);
const controls = new OrbitControls(camera, canvas);
controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN };
controls.screenSpacePanning = true;
controls.zoomToCursor = true;
const cielo = new THREE.HemisphereLight(0xffffff, 0x7d8790, 1.7);
cielo.position.set(0, 0, 1);   // il cielo sta sopra: l'asse Z
scene.add(cielo);
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(0.4, 0.6, 1);
camera.add(sun);
scene.add(camera);

const model = new THREE.Group();
const overlay = new THREE.Group();
const dimLines = new THREE.Group();
scene.add(model, overlay, dimLines);
const objs = new Map();
const EDGE = new THREE.LineBasicMaterial({ color: 0x2B3138 });
const DIM_MAT = new THREE.LineBasicMaterial({ color: 0x1F3A5F });
const C_HOVER = new THREE.Color(0x4EA1FF), C_SEL = new THREE.Color(0xFFB000);

let daRidisegnare = true;
const ridisegna = () => { daRidisegnare = true; };
controls.addEventListener('change', ridisegna);

function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
  ridisegna();
}
new ResizeObserver(resize).observe(view);

function loop() {
  requestAnimationFrame(loop);
  if (anim) stepAnim();
  if (!daRidisegnare) return;
  daRidisegnare = false;
  renderer.render(scene, camera);
  placeDims();
  placeCube();
}

function buildScene(sc) {
  for (const o of objs.values()) { o.mesh.geometry.dispose(); o.mesh.material.dispose(); o.lines.geometry.dispose(); }
  model.clear(); objs.clear();
  for (const d of sc.objects) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(d.positions, 3));
    g.setIndex(d.indices);
    g.computeVertexNormals();
    const base = new THREE.Color(d.kind === 'body' ? 0xB7BFC8 : 0xA8B1BA);
    const mat = new THREE.MeshStandardMaterial({ color: base.clone(), metalness: 0.15, roughness: 0.55,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(g, mat);
    mesh.userData.id = d.id;
    const pos = d.matrix ? new THREE.Matrix4().set(...d.matrix) : null;      // istanza di un assieme: dove sta
    const seg = [];
    for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
    const lines = new THREE.LineSegments(lg, EDGE);
    if (pos) for (const o of [mesh, lines]) { o.matrixAutoUpdate = false; o.matrix.copy(pos); o.updateMatrixWorld(true); }
    model.add(mesh, lines);
    objs.set(d.id, { data: d, mesh, lines, base, pos });
  }
  paint();
}

function faceOverlay(o, faceIndex, color) {
  const f = o.data.faces.find(x => x.index === faceIndex);
  if (!f) return;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(o.data.positions, 3));
  g.setIndex(o.data.indices.slice(f.start, f.start + f.count));
  g.computeVertexNormals();
  const m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, depthTest: true,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const ov = new THREE.Mesh(g, m);
  if (o.pos) { ov.matrixAutoUpdate = false; ov.matrix.copy(o.pos); ov.updateMatrixWorld(true); }
  overlay.add(ov);
}

function paint() {
  for (const m of overlay.children) { m.geometry.dispose(); m.material.dispose(); }
  overlay.clear();
  const selIds = new Set(sel ? (sel.ids || [sel.id]) : []);
  for (const [id, o] of objs) {
    let c = o.base;
    const intero = o.data.kind === 'member';
    if (selIds.has(id) && (intero || sel.face == null || (sel.ids && sel.ids.length > 1))) c = C_SEL;
    else if (hover && hover.id === id && (intero || hover.face == null)) c = C_HOVER;
    o.mesh.material.color.copy(c);
    o.mesh.material.emissive.setRGB(c === o.base ? 0 : 0.08, c === o.base ? 0 : 0.06, 0);
  }
  if (sel && sel.face != null && objs.has(sel.id)) faceOverlay(objs.get(sel.id), sel.face, C_SEL);
  if (sel && sel.hl && objs.has('body')) for (const i of sel.hl) faceOverlay(objs.get('body'), i, C_SEL);
  if (hover && hover.face != null && objs.has(hover.id) && !(sel && sel.id === hover.id && sel.face === hover.face))
    faceOverlay(objs.get(hover.id), hover.face, C_HOVER);
  paintEdges();
  ridisegna();
}

// --------------------------------------------------------------- bordi dove si può piegare
// Il bordo di una lamiera è una faccia spessa 1-2 mm: col mouse non si prende. Il motore manda i bordi
// liberi (lati della base senza flangia, punte delle flange): vicino al mouse si accendono, clic = flangia lì.
let bendEdges = [], hoverEdge = null, modelRadius = 100;
const edgeGroup = new THREE.Group();
scene.add(edgeGroup);
const EDGE_HOV = new THREE.MeshBasicMaterial({ color: 0xFF8C00, depthTest: false, transparent: true, opacity: 0.85 });
const EDGE_SEL = new THREE.MeshBasicMaterial({ color: 0xFFB000, depthTest: false });
function edgeMesh(e, mat) {
  const a = v3(e.a), b = v3(e.b);
  const r = Math.max(e.thickness * 0.8, modelRadius * 0.004);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, a.distanceTo(b), 10), mat);
  m.position.copy(a).add(b).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
  m.renderOrder = 10;
  return m;
}
const edgeSel = () => (sel?.id?.startsWith('edge=') ? bendEdges.find(e => 'edge=' + e.id === sel.id) : null);
function paintEdges() {
  svuota(edgeGroup);
  const s = edgeSel();
  if (s) edgeGroup.add(edgeMesh(s, EDGE_SEL));
  if (hoverEdge && hoverEdge !== s) edgeGroup.add(edgeMesh(hoverEdge, EDGE_HOV));
}
function pickEdge(ev) {
  if (!model.visible || !bendEdges.length || SK) return null;
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const scr = p => { const q = p.clone().project(camera); return [(q.x + 1) / 2 * r.width, (1 - q.y) / 2 * r.height]; };
  const corpi = [...objs.values()].map(o => o.mesh);
  let best = null;
  for (const e of bendEdges) {
    const A = v3(e.a), B = v3(e.b), a = scr(A), b = scr(B);
    const dx = b[0] - a[0], dy = b[1] - a[1], LL = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((mx - a[0]) * dx + (my - a[1]) * dy) / LL));
    const d = Math.hypot(mx - a[0] - t * dx, my - a[1] - t * dy);
    if (d > 9 || (best && d >= best.d)) continue;
    // nascosto dietro al pezzo? si guarda se il raggio verso quel punto sbatte prima contro qualcosa
    const P = A.clone().lerp(B, t), dir = P.clone().sub(camera.position), dist = dir.length();
    ray.set(camera.position, dir.normalize());
    const hit = ray.intersectObjects(corpi, false)[0];
    if (hit && hit.distance < dist - Math.max(3 * e.thickness, 1)) continue;
    best = { e, d };
  }
  return best?.e ?? null;
}
function selectEdge(e) {
  selTok++; selGen++;
  sel = { id: 'edge=' + e.id };
  hover = null;
  paint(); renderTree(); paintNodes();
  const punta = e.kind === 'tip';
  const d = punta ? ultimaPunta : ultimaFlangia;
  $('#props').innerHTML = `<h3>Flangia su questo bordo</h3><table class="grid"><tr><td>Bordo</td><td>${esc(e.label)}</td></tr></table>
    <p class="hint" style="margin:6px 0">${punta ? 'Piega sul bordo libero della flangia: la sua lunghezza resta la quota esterna fino allo spigolo della nuova piega.' : 'Lunghezza dallo spigolo esterno alla punta.'}</p>
    ${flangeFields(d, punta ? VERSI_PUNTA : VERSI_UI, POS_UI)}
    <div class="row-btns"><button class="btn primary" id="f-add">Aggiungi flangia su ${esc(e.label)}</button></div>`;
  const vai = () => {
    const f = readFlange();
    if (punta) ultimaPunta = f; else ultimaFlangia = f;
    const prima = selGen;
    inCoda(async () => {
      const r = await call('add_flange', e.feature, punta ? null : e.ref, f, punta ? e.ref : null);
      if (await apply(r)) {
        if (selGen === prima) await select(r.select);
        if (r.ask_tip_corners) askTipCorners(r.ask_tip_corners);
      }
    });
  };
  $('#f-add').onclick = vai;
  ['#f-len', '#f-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  $('#f-len').focus(); $('#f-len').select();
}

// --------------------------------------------------------------- scelta col mouse
const ray = new THREE.Raycaster();
function pick(ev) {
  if (!model.visible) return null;            // sviluppo a video: il pezzo piegato non c'è da cliccare
  const r = canvas.getBoundingClientRect();
  const p = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(p, camera);
  const hit = ray.intersectObjects([...objs.values()].map(o => o.mesh), false)[0];
  if (!hit) return null;
  const o = objs.get(hit.object.userData.id);
  let face = null;
  if (o.data.kind === 'body' || o.data.kind === 'instance') {
    const k = hit.faceIndex * 3;
    face = o.data.faces.find(f => k >= f.start && k < f.start + f.count)?.index ?? null;
  }
  return { id: o.data.id, face, name: o.data.name };
}

const tip = $('#hover-tip');
let premuto = null;
canvas.addEventListener('pointerdown', ev => {
  premuto = { x: ev.clientX, y: ev.clientY };
  if (document.activeElement?.id === 'sk-cmd-in') document.activeElement.blur();
  if (SK && SK.tool === 'select' && ev.button === 0 && !SK.pick) SK.box = { x: ev.clientX, y: ev.clientY };
});
window.addEventListener('pointermove', ev => {
  if (!SK?.box || !(ev.buttons & 1)) return;
  const r = view.getBoundingClientRect(), b = $('#sk-box');
  const x0 = Math.min(SK.box.x, ev.clientX), x1 = Math.max(SK.box.x, ev.clientX);
  const y0 = Math.min(SK.box.y, ev.clientY), y1 = Math.max(SK.box.y, ev.clientY);
  if (x1 - x0 < 5 && y1 - y0 < 5) return;
  Object.assign(b.style, { display: 'block', left: (x0 - r.left) + 'px', top: (y0 - r.top) + 'px', width: (x1 - x0) + 'px', height: (y1 - y0) + 'px' });
  b.classList.toggle('cross', ev.clientX < SK.box.x);
});
window.addEventListener('pointerup', ev => {
  if (!SK?.box) return;
  const inizio = SK.box; SK.box = null;
  $('#sk-box').style.display = 'none';
  if (Math.abs(ev.clientX - inizio.x) < 5 && Math.abs(ev.clientY - inizio.y) < 5) return;
  // da sinistra a destra: dentro del tutto; da destra a sinistra: anche toccati
  const r = canvas.getBoundingClientRect();
  const X0 = Math.min(inizio.x, ev.clientX) - r.left, X1 = Math.max(inizio.x, ev.clientX) - r.left;
  const Y0 = Math.min(inizio.y, ev.clientY) - r.top, Y1 = Math.max(inizio.y, ev.clientY) - r.top;
  const dentro = p => p[0] >= X0 && p[0] <= X1 && p[1] >= Y0 && p[1] <= Y1;
  const tocca = ev.clientX < inizio.x;
  const scr = p => { const q = v3(p).project(camera); return [(q.x + 1) / 2 * view.clientWidth, (1 - q.y) / 2 * view.clientHeight]; };
  if (!ev.shiftKey) SK.sel.clear();
  for (const l of SK.v.lines) {
    const a = scr(l.pa), b = scr(l.pb);
    const ok = tocca ? (dentro(a) || dentro(b) || [0.25, 0.5, 0.75].some(t => dentro([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]))) : dentro(a) && dentro(b);
    if (ok) SK.sel.add(l.id);
  }
  for (const c of SK.v.circles) {
    const ctr = skToLocal(v3(c.center));
    const pts = [0, 1, 2, 3].map(k => scr(skToWorld([ctr[0] + c.r * Math.cos(k * Math.PI / 2), ctr[1] + c.r * Math.sin(k * Math.PI / 2)])));
    if (tocca ? pts.some(dentro) : pts.every(dentro)) SK.sel.add(c.id);
  }
  drawSketch();
});
canvas.addEventListener('pointermove', ev => {
  if (SK) { skMove(ev); return; }
  if (ev.buttons) { tip.style.display = 'none'; return; }
  const he = pickEdge(ev);
  if (he !== hoverEdge) { hoverEdge = he; paint(); }
  if (he) {
    if (hover) { hover = null; paint(); }
    tip.textContent = `Bordo: ${he.label} · clic per piegare qui`;
    const r = view.getBoundingClientRect();
    tip.style.left = (ev.clientX - r.left + 14) + 'px';
    tip.style.top = (ev.clientY - r.top + 14) + 'px';
    tip.style.display = 'block';
    return;
  }
  const h = pick(ev);
  const cambia = (h?.id ?? null) !== (hover?.id ?? null) || (h?.face ?? null) !== (hover?.face ?? null);
  hover = h;
  if (cambia) paint();
  if (h) {
    const o = objs.get(h.id);
    const f = h.face != null ? o.data.faces.find(x => x.index === h.face) : null;
    tip.textContent = h.face != null ? `${o.data.name}: ${f?.label || 'faccia'}` : h.name;
    const r = view.getBoundingClientRect();
    tip.style.left = (ev.clientX - r.left + 14) + 'px';
    tip.style.top = (ev.clientY - r.top + 14) + 'px';
    tip.style.display = 'block';
  } else tip.style.display = 'none';
});
canvas.addEventListener('pointerleave', () => { hover = null; hoverEdge = null; tip.style.display = 'none'; paint(); });
canvas.addEventListener('pointerup', ev => {
  if (!premuto || Math.hypot(ev.clientX - premuto.x, ev.clientY - premuto.y) > 4 || ev.button !== 0) return;
  if (SK) { skClick(ev); return; }
  if (S?.mode === 'assembly' && ASM.tool) { asmClick(ev); return; }
  const he = pickEdge(ev);
  if (he) { selectEdge(he); return; }
  const h = pick(ev);
  if (h) select(h.id, h.face); else clearSelection();
});

// --------------------------------------------------------------- viste
let anim = null;
function goTo(dir, keepDir = false) {
  if (!objs.size) return;
  fitBox(new THREE.Box3().setFromObject(model), dir, keepDir);
}
function fitBox(box, dir, keepDir = false) {
  const c = box.getCenter(new THREE.Vector3());
  const rad = box.getBoundingSphere(new THREE.Sphere()).radius || 100;
  const fov = THREE.MathUtils.degToRad(camera.fov);
  let dist = rad / Math.sin(Math.min(fov, fov * camera.aspect) / 2) * 1.08;
  if (SK) {
    // nel disegno si guarda la faccia di fronte: si inquadra larghezza × altezza, non la sfera intorno
    // (una faccia lunga e bassa verrebbe minuscola)
    const ax = v3(SK.v.x_dir), ay = v3(SK.v.y_dir), xs = [], ys = [];
    for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) {
      const p = new THREE.Vector3(i ? box.max.x : box.min.x, j ? box.max.y : box.min.y, k ? box.max.z : box.min.z);
      xs.push(p.dot(ax)); ys.push(p.dot(ay));
    }
    const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
    const hf = 2 * Math.atan(Math.tan(fov / 2) * camera.aspect);
    dist = Math.max(w / 2 / Math.tan(hf / 2), h / 2 / Math.tan(fov / 2), 20) * 1.45;   // margine per casella e aiuto in basso
  }
  const d = keepDir ? camera.position.clone().sub(controls.target).normalize() : dir.clone().normalize();
  const to = { pos: c.clone().add(d.multiplyScalar(dist)), target: c };
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || primaVolta) {
    camera.position.copy(to.pos); controls.target.copy(to.target); controls.update(); ridisegna(); return;
  }
  anim = { t0: performance.now(), from: { pos: camera.position.clone(), target: controls.target.clone() }, to };
}
function stepAnim() {
  const t = Math.min(1, (performance.now() - anim.t0) / 260);
  const e = 1 - Math.pow(1 - t, 3);
  camera.position.lerpVectors(anim.from.pos, anim.to.pos, e);
  controls.target.lerpVectors(anim.from.target, anim.to.target, e);
  controls.update();
  ridisegna();
  if (t >= 1) anim = null;
}
const VISTE = {
  view_iso: new THREE.Vector3(1, -1.25, 0.9), view_top: new THREE.Vector3(0, -0.0001, 1),
  view_front: new THREE.Vector3(0, -1, 0), view_right: new THREE.Vector3(1, 0, 0),
  view_back: new THREE.Vector3(0, 1, 0), view_left: new THREE.Vector3(-1, 0, 0), view_bottom: new THREE.Vector3(0, 0.0001, -1),
};

// --------------------------------------------------------------- sviluppo e piano di lavoro
// "Spiega": al posto del pezzo piegato si vede lo sviluppo (dal motore: contorni e linee di piega),
// steso nel piano dello sketch della lamiera. Disegnando su una faccia si vede solo quella faccia, piena.
const flatGroup = new THREE.Group();
const workGroup = new THREE.Group();
flatGroup.matrixAutoUpdate = false;
scene.add(flatGroup, workGroup);
let flatView = false;
// un po' trasparenti: la griglia dello sketch si deve vedere attraverso
const FLAT_FILL = new THREE.MeshBasicMaterial({ color: 0xB7C2CD, side: THREE.DoubleSide, transparent: true, opacity: 0.6, depthWrite: false });
const WORK_FILL = new THREE.MeshBasicMaterial({ color: 0xB7C2CD, side: THREE.DoubleSide, transparent: true, opacity: 0.5, depthWrite: false });
const FLAT_EDGE = new THREE.LineBasicMaterial({ color: 0x2B3138 });
const FLAT_BEND = new THREE.LineDashedMaterial({ color: 0xC0392B, dashSize: 6, gapSize: 4 });
const FLAT_ZONE = new THREE.MeshBasicMaterial({ color: 0xE8A39A, side: THREE.DoubleSide, transparent: true, opacity: 0.45, depthWrite: false });
const svuota = g => { g.traverse(x => x.geometry?.dispose()); g.clear(); };

function buildFlat() {
  svuota(flatGroup);
  const d = S?.sheet?.data;
  if (!d || !d.outline.length || !d.plane) return false;
  const P = d.plane;
  flatGroup.matrix.makeBasis(v3(P.x), v3(P.y), v3(P.z)).setPosition(v3(P.origin));
  flatGroup.matrixWorldNeedsUpdate = true;
  const anelli = d.outline.map(p => { const q = []; for (let i = 0; i + 1 < p.length; i += 2) q.push(new THREE.Vector2(p[i], p[i + 1])); return q; });
  const area = q => q.reduce((a, p, i) => { const r = q[(i + 1) % q.length]; return a + p.x * r.y - r.x * p.y; }, 0) / 2;
  const fuori = anelli.reduce((b, l, i) => Math.abs(area(l)) > Math.abs(area(anelli[b])) ? i : b, 0);
  const forma = new THREE.Shape(anelli[fuori]);
  anelli.forEach((l, i) => { if (i !== fuori) forma.holes.push(new THREE.Path(l)); });
  flatGroup.add(new THREE.Mesh(new THREE.ShapeGeometry(forma), FLAT_FILL));
  for (const l of anelli) flatGroup.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(l.map(p => new THREE.Vector3(p.x, p.y, 0.02))), FLAT_EDGE));
  for (const z of d.bend_zones || []) {       // le strisce delle pieghe: qui non si disegna
    const g = new THREE.BufferGeometry().setFromPoints(z.map(p => new THREE.Vector3(p[0], p[1], 0.01)));
    g.setIndex([0, 1, 2, 0, 2, 3]);
    flatGroup.add(new THREE.Mesh(g, FLAT_ZONE));
  }
  for (const [a, b] of d.bend_lines) {
    const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(a[0], a[1], 0.03), new THREE.Vector3(b[0], b[1], 0.03)]), FLAT_BEND);
    ln.computeLineDistances();
    flatGroup.add(ln);
  }
  return true;
}
function flatBox() {
  const d = S.sheet.data, P = d.plane, box = new THREE.Box3();
  const w = (x, y) => v3(P.origin).addScaledVector(v3(P.x), x).addScaledVector(v3(P.y), y);
  for (const p of d.outline) for (let i = 0; i + 1 < p.length; i += 2) box.expandByPoint(w(p[i], p[i + 1]));
  return box;
}
// la faccia su cui si disegna: i suoi triangoli (dal motore) pieni, col bordo
function buildWorkFace(nome) {
  svuota(workGroup);
  const o = objs.get('body');
  if (!o || !nome) return null;
  const box = new THREE.Box3();
  for (const f of o.data.faces.filter(x => x.name === nome)) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(o.data.positions, 3));
    g.setIndex(o.data.indices.slice(f.start, f.start + f.count));
    workGroup.add(new THREE.Mesh(g, WORK_FILL));
    workGroup.add(new THREE.LineSegments(new THREE.EdgesGeometry(g, 1), FLAT_EDGE));
    const bb = new THREE.Box3();
    for (let i = f.start; i < f.start + f.count; i++) { const k = o.data.indices[i] * 3; bb.expandByPoint(new THREE.Vector3(o.data.positions[k], o.data.positions[k + 1], o.data.positions[k + 2])); }
    box.union(bb);
  }
  return box.isEmpty() ? null : box;
}
// cosa si vede: il pezzo, lo sviluppo, oppure solo la faccia di lavoro (col pezzo in trasparenza a richiesta)
function applyLook() {
  const solo = SK && (SK.v.on_face || SK.v.on_flat);
  const piatto = SK ? !!SK.v.on_flat : flatView;
  flatGroup.visible = piatto && flatGroup.children.length > 0;
  workGroup.visible = !!(SK && SK.v.on_face);
  const fantasma = !SK ? 1 : solo ? (SK.ghost ? 0.15 : 0) : 0.18;
  model.visible = !piatto || (SK && SK.ghost) ? fantasma > 0 : false;
  for (const o of objs.values()) {
    o.mesh.material.transparent = fantasma < 1; o.mesh.material.opacity = fantasma; o.mesh.material.depthWrite = fantasma >= 1;
  }
  dimLines.visible = SK ? true : !piatto;
  edgeGroup.visible = !SK && !piatto;
  dimsBox.style.display = !SK && piatto ? 'none' : '';
  nodesBox.style.display = SK || piatto ? 'none' : '';
  $('#b-unfold').hidden = !S?.sheet?.data;
  $('#b-unfold').classList.toggle('on', flatView);
  $('#b-unfold').textContent = flatView ? 'Ripiega' : 'Spiega';
  $('#flat-bar').hidden = !(flatView && !SK);
  $('#sk-ghost').hidden = !solo;
  $('#sk-ghost').classList.toggle('on', !!SK?.ghost);
  ridisegna();
}
function toggleFlat(on = !flatView) {
  if (SK) return;
  if (on && !S?.sheet?.data) { toast('Lo sviluppo c’è quando la lamiera è costruita: guarda la scheda Lamiera.', 'err'); return; }
  flatView = on;
  if (on) { buildFlat(); clearSelection(); }
  applyLook();
  if (on) fitBox(flatBox(), v3(S.sheet.data.plane.z).add(new THREE.Vector3(0, -0.0001, 0)));
  else goTo(VISTE.view_iso);
}
function flatSketch() {
  if (SK) return;
  inCoda(async () => {
    const r = await call('sketch_on_flat', S?.sheet?.feature || null);
    if (await apply(r)) { flatView = false; await enterSketch(r.sketch); }
  });
}

// --------------------------------------------------------------- quote sul modello
const dimsBox = $('#dims');
let dimEls = [];
function buildDims() {
  for (const l of dimLines.children) l.geometry.dispose();
  dimLines.clear();
  dimsBox.innerHTML = '';
  dimEls = [];
  if (!showDims || !S) return;
  // con uno sketch aperto si vedono solo le sue quote, sfalsate nel suo piano (non verso di te)
  const lista = S.dimensions.filter(d => (SK ? d.sketch === SK.sid : !d.local));
  const box = new THREE.Box3();
  if (SK) SK.v.points.filter(p => p.id !== 'O').forEach(p => box.expandByPoint(v3(p.xyz)));
  if (box.isEmpty()) box.setFromObject(model);
  const centro = box.getCenter(new THREE.Vector3());
  const off = SK ? Math.max(4, box.getBoundingSphere(new THREE.Sphere()).radius * 0.08)
    : Math.max(20, box.getBoundingSphere(new THREE.Sphere()).radius * 0.07);
  for (const d of lista) {
    const a = new THREE.Vector3(...d.a), b = new THREE.Vector3(...d.b);
    let pa = a, pb = b;
    if (d.type !== 'diameter' && d.type !== 'radius') {
      const v = b.clone().sub(a);
      let n = new THREE.Vector3(0, 0, 1);
      if (Math.abs(v.clone().normalize().dot(n)) > 0.9) n = new THREE.Vector3(0, 1, 0);
      const perp = SK ? v3(SK.v.z_dir).cross(v).normalize() : v.clone().cross(n).normalize();
      const mid = a.clone().add(b).multiplyScalar(0.5);
      if (perp.dot(mid.clone().sub(centro)) < 0) perp.negate();
      pa = a.clone().addScaledVector(perp, off); pb = b.clone().addScaledVector(perp, off);
      const seg = [a, a.clone().addScaledVector(perp, off * 1.15), b, b.clone().addScaledVector(perp, off * 1.15), pa, pb];
      const g = new THREE.BufferGeometry().setFromPoints(seg);
      dimLines.add(new THREE.LineSegments(g, DIM_MAT));
    }
    const el = document.createElement('div');
    el.className = 'dim' + (d.type === 'diameter' || d.type === 'radius' ? ' dia' : '');
    el.innerHTML = (d.param ? `<span class="p">${esc(d.param)}</span>` : '') + esc(d.label);
    el.title = d.param ? `Quota legata al parametro ${d.param}: clicca per cambiarla` : 'Clicca per cambiare la quota';
    el.addEventListener('click', ev => { ev.stopPropagation(); editDim(el, d); });
    dimsBox.appendChild(el);
    // il diametro va sul bordo del cerchio, non al centro: se no la scritta copre il foro
    dimEls.push({ el, at: d.type === 'diameter' || d.type === 'radius' ? pb.clone() : pa.clone().add(pb).multiplyScalar(0.5) });
  }
  placeDims();
  ridisegna();
}
function placeDims() {
  const w = view.clientWidth, h = view.clientHeight;
  for (const { el, at } of [...dimEls, ...nodeEls]) {
    const p = at.clone().project(camera);
    const fuori = p.z > 1 || Math.abs(p.x) > 1.1 || Math.abs(p.y) > 1.1;
    el.style.display = fuori ? 'none' : '';
    el.style.left = ((p.x + 1) / 2 * w) + 'px';
    el.style.top = ((1 - p.y) / 2 * h) + 'px';
  }
}
function editDim(el, d) {
  if (el.classList.contains('edit')) return;
  el.classList.add('edit');
  el.innerHTML = (d.param ? `<span class="p">${esc(d.param)} =</span>` : '') + '<input>';
  const inp = el.querySelector('input');
  const mostrato = d.shown ?? d.value;
  inp.value = typeof d.expr === 'number' ? String(mostrato).replace('.', ',') : (d.param ? String(mostrato).replace('.', ',') : d.expr);
  inp.focus(); inp.select();
  let fatto = false;
  const chiudi = () => { if (!fatto) { fatto = true; buildDims(); } };
  inp.addEventListener('keydown', ev => {
    if (!ev.ctrlKey) ev.stopPropagation();
    if (ev.key === 'Escape') chiudi();
    if (ev.key === 'Enter') {
      fatto = true;
      const v = inp.value;
      inCoda(async () => { if (!await apply(await call('set_dimension', d.sketch, d.dim, v))) buildDims(); });
    }
  });
  inp.addEventListener('blur', chiudi);
}

// --------------------------------------------------------------- nodi dello scheletro
const nodesBox = $('#nodes');
let nodeEls = [];
function buildNodes() {
  nodesBox.innerHTML = '';
  nodeEls = [];
  for (const n of nodes) {
    const el = document.createElement('div');
    el.className = 'node-dot' + (n.members.length ? '' : ' free');
    el.dataset.id = n.id;
    el.title = `Nodo ${n.key}` + (n.members.length ? ` (${n.members.join(', ')})` : ' (nessuna asta)');
    el.addEventListener('click', ev => { ev.stopPropagation(); clickNode(n); });
    nodesBox.appendChild(el);
    nodeEls.push({ el, at: new THREE.Vector3(...n.xyz) });
  }
  paintNodes();
  placeDims();
}
function paintNodes() {
  for (const { el } of nodeEls) {
    const n = nodes.find(x => x.id === el.dataset.id);
    el.classList.toggle('sel', !!sel && sel.id === el.dataset.id);
    el.classList.toggle('target', !!linkFrom && n.structure === linkFrom.st && n.key !== linkFrom.key);
  }
  $('#link-hint').hidden = !linkFrom;
}
function clickNode(n) {
  if (linkFrom) {
    const da = linkFrom;
    if (n.structure !== da.st || n.key === da.key) { toast('Scegli un altro nodo della stessa struttura.', 'err'); return; }
    linkFrom = null; paintNodes();
    inCoda(async () => {
      const r = await call('add_member', da.st, da.key, n.key, null, null, da.profile || null, da.group || null);
      if (await apply(r)) await select(r.select);
    });
    return;
  }
  select(n.id);
}

// ===================================================================== dati → pannelli
async function apply(res, okMsg) {
  if (!res || !res.ok) {
    if (res && !res.cancelled) toast(res.message || 'Operazione non riuscita.', 'err');
    return false;
  }
  if (res.state) {
    S = res.state;
    renderPanels();
    if (S.scene_version !== sceneVersion) await loadScene();
    else buildDims();
    if (SK) await refreshSketch();
  }
  if (okMsg || res.message) toast(okMsg || res.message);
  return true;
}

async function loadScene() {
  const sc = await call('scene');
  sceneVersion = sc.version;
  const eraVuota = objs.size === 0;
  const raggio = () => new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere()).radius;
  const prima = eraVuota ? 0 : raggio();
  buildScene(sc);
  nodes = sc.nodes || [];
  bendEdges = sc.bend_edges || [];
  hoverEdge = null;
  modelRadius = new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere()).radius || 100;
  if (primaVolta || (eraVuota && objs.size)) { goTo(VISTE.view_iso); primaVolta = !objs.size && primaVolta; ribbonForProject(); }
  else if (objs.size && raggio() > prima * 1.15) goTo(null, true);   // il modello è cresciuto: si riadatta
  buildDims();
  buildNodes();
  if (flatView || SK?.v.on_flat) { if (!buildFlat()) flatView = false; }
  if (SK?.v.on_face) buildWorkFace(SK.v.on_face);
  applyLook();
  const esiste = id => objs.has(id) || nodes.some(n => n.id === id) || id.startsWith('flange=');
  if (sel?.id?.startsWith('edge=')) {
    const e = edgeSel();               // il bordo c'è ancora (libero)? se no la flangia l'ha preso
    if (e) selectEdge(e); else clearSelection();
  } else if (sel) {
    if ((sel.ids || [sel.id]).every(esiste)) await select(sel.id, sel.face, sel.ids, true);
    else clearSelection();
  }
}

function renderPanels() {
  const assieme = S.mode === 'assembly';
  document.body.classList.toggle('assembly', assieme);
  $('#b-back').hidden = !S.can_back;
  if (!assieme && ASM.tool) asmTool(null);
  renderTop(); renderTree(); renderParams(); renderBottom(); renderSheet(); renderTimeline();
}

function renderTop() {
  const nome = esc(S.name || 'Senza nome');
  $('#docname').innerHTML = `${S.dirty ? '<span class="dirty">● </span>' : ''}${nome}` +
    (S.path ? ` <span style="color:var(--ink-3)">— ${esc(S.path)}</span>` : ' <span style="color:var(--ink-3)">— non salvato</span>');
  for (const [b, k, t] of [['#b-undo', 'undo', 'Annulla'], ['#b-redo', 'redo', 'Ripeti']]) {
    const l = S[k][0];
    $(b).disabled = !l;
    $(b).title = l ? `${t}: ${l} (Ctrl+${k === 'undo' ? 'Z' : 'Y'})` : `Niente da ${t.toLowerCase()}`;
  }
}

const ICONE = { project: '◆', part: '▣', sketch: '✎', extrude: '▤', hole: '◯', fillet: '◜', chamfer: '◿', sheet: '▱', flange: '⌐',
  structure: '⌗', group: '▾', members: '│' };
function renderTree() {
  const selIds = new Set(sel ? (sel.ids || [sel.id]) : []);
  const nodo = n => {
    const ids = n.kind === 'members' ? n.ref : n.kind === 'structure' ? membersOf(n.ref)
      : n.kind === 'flange' ? ['flange=' + n.ref]
      : n.kind === 'sketch' ? ['sketch=' + n.ref]
      : n.kind === 'instance' ? [n.ref] : n.kind === 'mate' ? ['mate=' + n.ref]
      : ['part', 'extrude', 'hole', 'fillet', 'chamfer', 'sheet'].includes(n.kind) ? ['body'] : null;
    const cls = ['node', n.kind === 'project' ? 'root' : '', n.kind === 'group' ? 'group' : '',
      ids && ids.length ? 'clickable' : '', n.status === 'errore' ? 'err' : '',
      ids && ids.length && ids.every(i => selIds.has(i)) && n.kind !== 'structure' && !(n.kind !== 'part' && ids[0] === 'body') ? 'sel' : ''];
    const st = n.status && n.status !== 'errore' ? `<span class="st">${esc(n.status)}</span>` : '';
    const data = ids && ids.length ? ` data-ids="${esc(ids.join(','))}"` : '';
    const figli = n.children.length ? `<ul>${n.children.map(nodo).join('')}</ul>` : '';
    return `<li><div class="${cls.filter(Boolean).join(' ')}"${data} title="${esc(n.label)}"><span class="k">${iconImg(n.kind)}</span>${esc(n.label)}${st}</div>${figli}</li>`;
  };
  $('#tree').innerHTML = `<ul>${nodo(S.tree)}</ul>`;
}
function membersOf(stId) { return [...objs.keys()].filter(k => k.startsWith(stId + '/')); }
$('#tree').addEventListener('click', ev => {
  const n = ev.target.closest('.node.clickable');
  if (!n) return;
  const ids = n.dataset.ids.split(',');
  if (ids[0].startsWith('sketch=')) { enterSketch(ids[0].slice(7)); return; }
  select(ids[0], null, ids.length > 1 ? ids : null);
});

function renderParams() {
  const righe = S.parameters.map(p => {
    const espr = typeof p.value === 'string';
    return `<tr><td>${esc(p.name)}</td><td><input class="field" data-p="${esc(p.name)}" value="${esc(espr ? p.value : String(p.value).replace('.', ','))}"></td>` +
      `<td class="res">${espr && p.resolved != null ? '= ' + num(p.resolved, 2) : ''}</td></tr>`;
  }).join('');
  $('#params').innerHTML = righe +
    '<tr><td colspan="3"><input class="field" id="new-param" placeholder="Nuovo: nome = valore"></td></tr>';
}
$('#params').addEventListener('keydown', ev => {
  const t = ev.target;
  if (ev.key !== 'Enter' || t.tagName !== 'INPUT') return;
  if (t.id === 'new-param') {
    const m = t.value.match(/^\s*([A-Za-z_]\w*)\s*=\s*(.+)$/);
    if (!m) { t.classList.add('bad'); toast('Scrivi così: nome = valore, per esempio  sbalzo = 30', 'err'); return; }
    inCoda(async () => apply(await call('set_parameter', m[1], m[2])));
    return;
  }
  provaParametro(t);
});
function provaParametro(t) {
  t.dataset.tentato = t.value;
  inCoda(async () => { if (!await apply(await call('set_parameter', t.dataset.p, t.value))) t.classList.add('bad'); });
}
$('#params').addEventListener('focusout', ev => {
  const t = ev.target;
  if (t.dataset?.p === undefined) return;
  const p = S.parameters.find(x => x.name === t.dataset.p);
  const ora = typeof p.value === 'string' ? p.value : String(p.value).replace('.', ',');
  if (t.value.trim() !== ora && t.value !== t.dataset.tentato) provaParametro(t);
});

// --------------------------------------------------------------- selezione e proprietà
// ogni selezione ha un numero: se nel frattempo ne è partita un'altra (un clic più recente), la risposta
// vecchia non tocca il pannello. Se no "Aggiungi" finirebbe sulla flangia sbagliata.
// selGen cambia solo quando cambia cosa è selezionato (non quando si riseleziona la stessa cosa dopo una
// ricostruzione): serve per sapere se, mentre una modifica girava, hai cliccato altro.
let selTok = 0, selGen = 0;
async function select(id, face = null, ids = null, silenzioso = false) {
  const mio = ++selTok;
  if (!sel || sel.id !== id || sel.face !== face) selGen++;
  sel = { id, face, ids };
  paint(); renderTree(); paintNodes(); if (S) renderTimeline();
  const nome = face != null ? objs.get(id)?.data.faces?.find(x => x.index === face)?.name ?? null : null;
  const r = await call('select', id, face, nome);
  if (mio !== selTok) return;
  if (!r.ok) { if (!silenzioso) toast(r.message, 'err'); return; }
  const fi = r.selection.face?.index;
  if (fi != null && fi !== face) { sel.face = fi; paint(); }     // il pezzo era stato ricostruito nel frattempo
  if (r.selection.highlight) { sel.hl = r.selection.highlight; paint(); }
  renderProps(r.selection);
}
function clearSelection() {
  selTok++; selGen++;
  sel = null; paint(); renderTree(); paintNodes();
  $('#props').innerHTML = '<p class="empty">Clicca un pezzo nel modello o nell’albero.</p>';
}

let profili = null;
async function renderProps(s) {
  const tab = rows => `<table class="grid">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
  const quanti = sel?.ids?.length > 1 ? ` <span style="color:var(--ink-3);font-weight:400">e altre ${sel.ids.length - 1} uguali</span>` : '';
  let h = `<h3>${esc(s.title)}${quanti}</h3>${tab(s.rows)}`;
  if (!profili) profili = await call('profile_suggestions');
  if (s.kind === 'member') {
    const anc = Object.entries(s.anchors).map(([k, v]) => `<option value="${k}"${k === s.anchor ? ' selected' : ''}>${esc(v)}</option>`).join('');
    h += `<div class="group-row"><label class="lbl" for="p-prof">Profilo</label>
      <input class="field" id="p-prof" list="dl-prof" value="${esc(s.profile)}" spellcheck="false">
      <datalist id="dl-prof">${profili.map(p => `<option value="${esc(p)}">`).join('')}</datalist>
      ${s.group ? `<label class="check"><input type="checkbox" id="p-all" checked> Tutte le aste di «${esc(s.group)}»</label>` : ''}
      <label class="lbl" for="p-anc">Linea d’asse sul profilo</label>
      <select class="field" id="p-anc">${anc}</select></div>
      <div class="row-btns"><button class="btn primary" id="p-apply">Applica profilo</button>
      <button class="btn" id="p-rot" title="Ruota il profilo attorno al suo asse">Ruota di 90° (ora ${num(s.rotate)}°)</button>
      <button class="btn" id="p-flip" title="Scambia il lato da cui è appoggiato il profilo">Inverti</button></div>
      <div class="row-btns"><button class="btn danger" id="p-del" title="Canc">Elimina ${sel?.ids?.length > 1 ? sel.ids.length + ' aste' : 'asta'}</button></div>`;
  } else if (s.kind === 'instance') {
    $('#props').innerHTML = instancePanel(s);
    wireInstance(s);
    return;
  } else if (s.kind === 'mate') {
    $('#props').innerHTML = matePanel(s);
    wireMate(s);
    return;
  } else if (s.kind === 'fold') {
    $('#props').innerHTML = foldPanel(s) + faceSketchButton(s);
    wireFold(s);
    return;
  } else if (s.kind === 'flange') {
    $('#props').innerHTML = flangePanel(s) + faceSketchButton(s);
    wireFlange(s);
    return;
  } else if (s.kind === 'body' && s.flange_form) {
    $('#props').innerHTML = h + faceSketchButton(s) + newFlangePanel(s.flange_form);
    wireNewFlange(s.flange_form);
    return;
  } else if (s.kind === 'node') {
    $('#props').innerHTML = h + nodePanel(s);
    wireNode(s);
    return;
  } else if (s.commands?.length) {
    h += faceSketchButton(s);
    h += `<div class="row-btns">${s.commands.map(c => `<button class="btn" data-cmd="${esc(c.id)}">${esc(c.label)}</button>`).join('')}</div>`;
  }
  $('#props').innerHTML = h;
  if (s.kind !== 'member') return;
  const tutti = () => $('#p-all')?.checked ?? false;
  const edit = fields => inCoda(async () => apply(await call('edit_member', s.id, fields, tutti())));
  $('#p-apply').onclick = () => edit({ profile: $('#p-prof').value.trim() });
  $('#p-prof').onkeydown = ev => { if (ev.key === 'Enter') edit({ profile: $('#p-prof').value.trim() }); };
  $('#p-rot').onclick = () => edit({ rotate_by: 90 });
  $('#p-flip').onclick = () => edit({ toggle_flip: true });
  $('#p-anc').onchange = () => edit({ anchor: $('#p-anc').value });
  $('#p-del').onclick = deleteSelected;
}

function faceSketchButton(s) {
  if (!s.face?.planar || !s.face.name) return '';
  return `<div class="row-btns"><button class="btn primary" data-face-sketch="${esc(s.face.name)}">Disegna su questa faccia</button></div>`;
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-face-sketch]');
  if (!b) return;
  inCoda(async () => {
    const r = await call('sketch_on_face', b.dataset.faceSketch);
    if (await apply(r)) await enterSketch(r.sketch);
  });
});

function deleteSelected() {
  if (sel?.id?.startsWith('flange=')) {
    const [fid, flid] = sel.id.slice(7).split('/');
    clearSelection();
    inCoda(async () => apply(await call('delete_flange', fid, flid)));
    return;
  }
  if (!sel || !(sel.ids || [sel.id]).every(id => id.includes('/'))) return;
  const ids = sel.ids || [sel.id];
  clearSelection();
  inCoda(async () => apply(await call('delete_members', ids)));
}

// --------------------------------------------------------------- lamiera: flange
const opts = (o, cur) => Object.entries(o).map(([k, v]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${esc(v)}</option>`).join('');
let ultimaFlangia = { length: '30', angle: '90', direction: 'up', position: 'inside' };
function flangeFields(d, dirs, pos, p = 'f') {
  const seg = (id, o, cur) => `<div class="seg" id="${p}-${id}">${Object.entries(o).map(([k, v]) =>
    `<button type="button" data-v="${k}" class="${k === cur ? 'on' : ''}" title="${esc(SPIEGA[k + (o === VERSI_PUNTA ? '_t' : '')] || '')}">${esc(v)}</button>`).join('')}</div>`;
  return `<div class="ff">
    <label>Lunghezza<span class="inp"><input class="field" id="${p}-len" value="${esc(String(d.length ?? '').replace('.', ','))}"><i>mm</i></span></label>
    <label>Angolo<span class="inp"><input class="field" id="${p}-ang" value="${esc(String(d.angle ?? 90).replace('.', ','))}"><i>°</i></span></label></div>
    <div class="seg-row"><span>Verso</span>${seg('dir', dirs, d.direction || 'up')}</div>
    <div class="seg-row"><span>Misura</span>${seg('pos', pos, d.position || 'inside')}</div>`;
}
const VERSI_UI = { up: 'su', down: 'giù' };
// per una flangia sulla punta di un'altra: "su" continua a chiudere (verso dentro), "giù" apre verso fuori (omega)
const VERSI_PUNTA = { up: 'dentro', down: 'fuori' };
const POS_UI = { inside: 'esterna', outside: 'dal bordo' };
const SPIEGA = { up_t: 'Verso dentro: chiude, es. il bordo di una scatola', down_t: 'Verso fuori: apre, es. la tesa di un omega',
  inside: 'La lunghezza è la quota esterna, misurata dal contorno: il pezzo resta delle misure disegnate',
  outside: 'La piega parte dal bordo del contorno e la flangia sta fuori: il pezzo cresce dello spessore' };
function readFlange(p = 'f') {
  return { length: $(`#${p}-len`).value.trim(), angle: $(`#${p}-ang`).value.trim(),
    direction: $(`#${p}-dir .on`)?.dataset.v || 'up', position: $(`#${p}-pos .on`)?.dataset.v || 'inside' };
}
// i pulsanti a scelta (Verso, Misura): uno acceso alla volta, poi un evento "change" sul gruppo
document.addEventListener('click', ev => {
  const b = ev.target.closest('.seg button');
  if (!b || b.classList.contains('on')) return;
  b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
  b.parentElement.dispatchEvent(new Event('change', { bubbles: true }));
});
let ultimaPunta = { length: '20', angle: '90', direction: 'up', position: 'inside' };
function newFlangePanel(ff) {
  return `<div class="sub">Flangia su questo lato</div><p class="hint" style="margin:0 0 6px">${esc(ff.label)}: lunghezza dallo spigolo esterno alla punta.</p>
    ${flangeFields(ultimaFlangia, VERSI_UI, POS_UI)}
    <div class="row-btns"><button class="btn primary" id="f-add">Aggiungi flangia su ${esc(ff.label)}</button></div>`;
}
function wireNewFlange(ff) {
  const vai = () => {
    ultimaFlangia = readFlange();
    const prima = selGen;
    inCoda(async () => { const r = await call('add_flange', ff.feature, ff.edge, ultimaFlangia); if (await apply(r) && selGen === prima) await select(r.select); });
  };
  $('#f-add').onclick = vai;
  ['#f-len', '#f-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
}
// angoli tra i bordi piegati sulle punte (scatola bordata): visti dall'alto, un angolo della scatola
const DISEGNI_ANGOLO = {            // in chiaro il bordo del lato lungo, in scuro quello del lato corto
  long: '<rect class="a" x="4" y="4" width="52" height="14"/><rect class="b" x="42" y="18" width="14" height="38"/>',
  short: '<rect class="a" x="4" y="4" width="38" height="14"/><rect class="b" x="42" y="4" width="14" height="52"/>',
  miter: '<path class="a" d="M4 4 H56 L42 18 H4 Z"/><path class="b" d="M56 4 V56 H42 V18 Z"/>',
};
const disegnoAngolo = k => `<svg viewBox="0 0 60 60" class="corner-pic">${DISEGNI_ANGOLO[k]}</svg>`;
function askTipCorners(a) {
  modal(`<h3>Come chiudo gli angoli dei bordi?</h3>
    <p class="hint">I bordi piegati sulle punte si incontrano negli angoli della scatola. Vale per tutti gli angoli;
    puoi cambiarlo dopo dal pannello di un bordo.</p>
    <div class="choice">${Object.entries(a.modes).map(([k, v]) => `<button data-k="${k}">${disegnoAngolo(k)}${esc(v)}</button>`).join('')}</div>
    <div class="acts"><button class="btn" id="m-no">Decido dopo</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#modal-box').querySelectorAll('.choice button').forEach(b => {
      b.onclick = () => { close(); inCoda(async () => { if (await apply(await call('set_tip_corners', a.feature, b.dataset.k))) await refreshSel(); }); };
    });
  });
}
async function refreshSel() { if (sel) await select(sel.id, sel.face, sel.ids, true); }

function flangePanel(s) {
  const riga = k => (s.rows.find(r => r[0] === k) || [])[1];
  const dove = s.parent ? `sulla punta di ${s.parent}` : (riga('Lato') || '');
  const angoli = [];
  if (s.tip_corners) angoli.push(`<label class="lbl">Con ${esc(s.tip_corners.others.join(', '))} <span class="hint">(vale per tutti i bordi)</span>
    <select class="field" id="f-tipc">${opts(s.tip_corners.modes, s.tip_corners.mode)}</select></label>`);
  for (const c of s.corners) angoli.push(`<div class="corner" data-other="${esc(c.other)}">
      <label class="lbl">Con ${esc(c.other)}<select class="field" data-corner>
        <option value="open"${c.mode === 'open' ? ' selected' : ''}>aperto</option>
        <option value="over"${c.mode === 'over' ? ' selected' : ''}>chiuso, ${esc(s.flange)} copre ${esc(c.other)}</option>
        <option value="under"${c.mode === 'under' ? ' selected' : ''}>chiuso, ${esc(c.other)} copre ${esc(s.flange)}</option></select></label>
      <label class="lbl"${c.mode === 'open' ? ' hidden' : ''}>Fessura (mm, 0 = a contatto)<input class="field" data-cgap value="${esc(String(c.gap).replace('.', ','))}"></label></div>`);
  const sezAngoli = angoli.length ? `<details class="fsec"${s.tip_corners || s.corners.some(c => c.mode !== 'open') ? ' open' : ''}><summary>Angoli</summary>
    ${angoli.join('')}
    <label class="lbl">Fessura d’angolo (mm)<input class="field" id="f-gap" value="${esc(String(s.def.gap ?? 0).replace('.', ','))}"></label></details>` : '';
  const sezLinguetta = s.can_extend ? `<div class="fnote">Sulla punta di ${esc(s.parent)} c’è una linguetta: ${esc(s.flange)} può continuare sopra di lei.
    <button class="btn" id="f-ext">Prolunga sopra la linguetta</button></div>` : '';
  const sezPunta = s.tip_child ? '' : `<details class="fsec"${s.tip_form ? ' open' : ''} id="f-punta"><summary>Piega sulla punta</summary>
    <p class="hint">Una flangia sul bordo libero di ${esc(s.flange)}: bordo di scatola, omega, Z…</p>
    ${flangeFields(ultimaPunta, VERSI_PUNTA, POS_UI, 't')}
    <div class="row-btns"><button class="btn primary" id="t-add">Aggiungi sulla punta</button>
      <button class="btn" id="t-orlo" title="Risvolto a 180° (orlo): la parete resta lunga fino al bordo esterno della piega">Orlo 180°</button></div></details>`;
  const sezIncastri = s.tip_contact ? `<details class="fsec" open id="f-incastri"><summary>Incastri sulla punta</summary>
    <p class="hint">La punta di ${esc(s.flange)} appoggia su ${esc(s.tip_contact)}: linguette sulla punta e asole sull’altra faccia.</p>
    <div class="ff"><label>Quante<span class="inp"><input class="field" id="i-n" value="3"></span></label>
      <label>Larghezza<span class="inp"><input class="field" id="i-w" value="15"><i>mm</i></span></label>
      <label>Gioco<span class="inp"><input class="field" id="i-c" value="0,2"><i>mm</i></span></label>
      <label>Sporgenza<span class="inp"><input class="field" id="i-s" value="0"><i>mm</i></span></label></div>
    <div class="row-btns"><button class="btn primary" id="i-add">Crea gli incastri</button></div></details>` : '';
  const dati = s.rows.filter(r => !['Lato', 'Piegata sulla punta di'].includes(r[0]));
  return `<div class="fhead"><div><h3>Flangia ${esc(s.flange)}</h3><div class="fsub">${esc(dove)}</div></div>
      <button class="ibtn danger" id="f-del" title="Elimina la flangia (Canc)"><img src="icons/delete.svg" alt=""></button></div>
    ${flangeFields(s.def, s.parent ? VERSI_PUNTA : s.directions, POS_UI)}
    ${sezLinguetta}${sezAngoli}${sezIncastri}${sezPunta}
    <details class="fsec"><summary>Dati di piega</summary><table class="grid">${dati.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table></details>`;
}
// ===================================================================== assiemi
const ASM = { tool: null, first: null };
function asmTool(t) {
  ASM.tool = t; ASM.first = null;
  document.querySelectorAll('[data-asm-tool]').forEach(b => b.classList.toggle('on', b.dataset.asmTool === t));
  if (t) setHelp(t === 'faccia' ? 'Faccia su faccia: clic sulla faccia del pezzo che sta fermo · Esc annulla'
    : 'Foro su foro: clic sul foro del pezzo che sta fermo · Esc annulla');
  else setHelp('');
  if (!SK) $('#sk-foot').hidden = !t;                // il suggerimento in basso, anche fuori dal disegno
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-asm-tool]');
  if (b) asmTool(ASM.tool === b.dataset.asmTool ? null : b.dataset.asmTool);
});
function asmClick(ev) {
  const h = pick(ev);
  if (!h || h.face == null) { toast('Clicca una faccia di un pezzo.', 'err'); return; }
  if (!ASM.first) {
    ASM.first = { inst: h.id, face: h.face };
    sel = { id: h.id, face: h.face }; paint();
    setHelp(`${ASM.tool === 'faccia' ? 'Faccia su faccia' : 'Foro su foro'}: ora clic sul${ASM.tool === 'faccia' ? 'la faccia' : ' foro'} dell’altro pezzo · Esc annulla`);
    return;
  }
  if (h.id === ASM.first.inst) { toast('Scegli una faccia di un altro pezzo.', 'err'); return; }
  const a = ASM.first, b = { inst: h.id, face: h.face }, tipo = ASM.tool;
  asmTool(tipo);                                       // resta attivo per un altro accoppiamento
  inCoda(async () => {
    const r = await call('asm_add_mate', tipo, a, b, 0, false);
    if (await apply(r, 'Accoppiato.') && r.select) await select(r.select);
  });
}
function instancePanel(s) {
  const tab = `<table class="grid">${s.rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
  const faccia = s.face ? `<p class="hint">Faccia: ${esc(s.face.label)} (${esc(s.face.kind)})</p>` : '';
  const incastri = s.tabs_with ? `<details class="fsec" open><summary>Incastri con ${esc(s.tabs_with)}</summary>
    <p class="hint">Questa punta appoggia su ${esc(s.tabs_with)}: linguette qui e asole nell’altro pezzo (si salvano i due file).</p>
    <div class="ff"><label>Quante<span class="inp"><input class="field" id="t-n" value="3"></span></label>
      <label>Larghezza<span class="inp"><input class="field" id="t-w" value="15"><i>mm</i></span></label>
      <label>Gioco<span class="inp"><input class="field" id="t-c" value="0,2"><i>mm</i></span></label>
      <label>Sporgenza<span class="inp"><input class="field" id="t-s" value="0"><i>mm</i></span></label></div>
    <div class="row-btns"><button class="btn primary" id="t-go">Crea gli incastri</button></div></details>` : '';
  return `<div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">copia nell’assieme${s.fixed ? ' · ferma (riferimento)' : ''}</div></div>
      <button class="ibtn danger" id="a-del" title="Togli dall’assieme"><img src="icons/delete.svg" alt=""></button></div>
    ${tab}${faccia}${incastri}
    <div class="sub">Sposta (mm)</div>
    <div class="xyz"><label>X<input class="field" id="a-dx" value="0"></label><label>Y<input class="field" id="a-dy" value="0"></label><label>Z<input class="field" id="a-dz" value="0"></label></div>
    <div class="row-btns"><button class="btn" id="a-move">Sposta</button></div>
    <div class="sub">Ruota di 90°</div>
    <div class="row-btns"><button class="btn" data-rot="x">attorno a X</button><button class="btn" data-rot="y">attorno a Y</button><button class="btn" data-rot="z">attorno a Z</button></div>
    <label class="check" style="margin-top:8px"><input type="checkbox" id="a-fixed"${s.fixed ? ' checked' : ''}> Fermo (gli altri pezzi si appoggiano a lui)</label>
    <div class="row-btns"><button class="btn primary" id="a-open">Apri il pezzo</button></div>
    ${s.mates.length ? `<p class="hint">Accoppiamenti: ${esc(s.mates.join(', '))}</p>` : '<p class="hint">Nessun accoppiamento: si sposta liberamente.</p>'}`;
}
function wireInstance(s) {
  const fai = (m, ...a) => inCoda(async () => { if (await apply(await call(m, ...a))) await refreshSel(); });
  $('#a-move').onclick = () => fai('asm_move', s.id, $('#a-dx').value.trim(), $('#a-dy').value.trim(), $('#a-dz').value.trim());
  document.querySelectorAll('[data-rot]').forEach(b => { b.onclick = () => fai('asm_rotate', s.id, b.dataset.rot, 90); });
  $('#a-fixed').onchange = () => fai('asm_set', s.id, { fixed: $('#a-fixed').checked });
  $('#a-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('asm_remove', s.id))); };
  $('#a-open').onclick = () => { clearSelection(); primaVolta = true; inCoda(async () => apply(await call('asm_open_part', s.id))); };
  if ($('#t-go')) $('#t-go').onclick = () => inCoda(async () => apply(await call('asm_tabs', s.id, s.face.index,
    $('#t-n').value.trim(), $('#t-w').value.trim(), $('#t-c').value.trim(), $('#t-s').value.trim())));
}
function matePanel(s) {
  const d = s.def;
  return `<div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">${esc(s.rows[0][1])}</div></div>
      <button class="ibtn danger" id="m-del" title="Togli l’accoppiamento"><img src="icons/delete.svg" alt=""></button></div>
    <table class="grid">${s.rows.slice(1).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>
    ${d.type === 'faccia' ? `<div class="ff" style="margin-top:10px"><label>Distanza<span class="inp"><input class="field" id="m-off" value="${esc(String(d.offset).replace('.', ','))}"><i>mm</i></span></label><span></span></div>` : ''}
    <div class="row-btns"><button class="btn" id="m-flip">${d.type === 'faccia' ? 'Allinea invece di affacciare' : 'Gira dall’altra parte'}</button>
      <button class="btn" id="m-sosp">${d.off ? 'Riattiva' : 'Sospendi'}</button></div>`;
}
function wireMate(s) {
  const fai = f => inCoda(async () => { if (await apply(await call('asm_edit_mate', s.id, f))) await refreshSel(); });
  if ($('#m-off')) { $('#m-off').onkeydown = ev => { if (ev.key === 'Enter') fai({ offset: $('#m-off').value.trim() }); }; $('#m-off').onchange = () => fai({ offset: $('#m-off').value.trim() }); }
  $('#m-flip').onclick = () => fai({ flip: !s.def.flip });
  $('#m-sosp').onclick = () => fai({ off: !s.def.off });
  $('#m-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('asm_delete_mate', s.id))); };
}
// ===================================================================== tavole
async function drawingsDialog() {
  const r = await call('drawing_fields');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const c = r.fields;
  const campo = (k, l, w = '') => `<label${w}>${l}<input class="field" data-c="${k}" value="${esc(c[k] || '')}"></label>`;
  modal(`<div class="tav"><div class="tav-side"><h3>Tavole</h3>
      <div class="form">${campo('azienda', 'Azienda', ' style="grid-column:1/-1"')}${campo('disegnatore', 'Disegnatore')}${campo('numero', 'N. disegno')}
      ${campo('revisione', 'Revisione')}<label>Formato<select class="field" data-c="formato">${['A4', 'A3', 'A2'].map(f => `<option${c.formato === f ? ' selected' : ''}>${f}</option>`).join('')}</select></label>
      ${campo('note', 'Note', ' style="grid-column:1/-1"')}</div>
      ${r.assembly ? '<label class="check"><input type="checkbox" id="tav-tutte" checked> anche le tavole di tutti i pezzi (con gli sviluppi)</label>' : ''}
      <p class="hint">Azienda e disegnatore si ricordano per le prossime tavole. Viste in proiezione europea, quote d’ingombro e note dei fori automatiche.</p>
      <div class="acts"><button class="btn" id="tav-agg">Aggiorna anteprima</button></div>
      <div class="acts"><button class="btn" id="m-no">Chiudi</button><button class="btn" id="tav-dxf">Esporta DXF</button><button class="btn primary" id="tav-pdf">Esporta PDF</button></div></div>
      <div class="tav-main"><div class="tav-tabs" id="tav-tabs"></div><div class="tav-view" id="tav-view"><p class="hint">Preparo l’anteprima…</p></div></div></div>`, close => {
    const leggi = () => { const o = {}; document.querySelectorAll('#modal-box [data-c]').forEach(i => { o[i.dataset.c] = i.value.trim(); }); return o; };
    const tutte = () => !!$('#tav-tutte')?.checked;
    let fogli = [];
    const mostra = k => {
      $('#tav-view').innerHTML = fogli[k] ? fogli[k].svg.replace(/width="[\d.]+mm" height="[\d.]+mm"/, 'width="100%" height="100%"') : '';
      document.querySelectorAll('#tav-tabs button').forEach((b, i) => b.classList.toggle('on', i === k));
    };
    const anteprima = () => inCoda(async () => {
      $('#tav-view').innerHTML = '<p class="hint">Preparo l’anteprima…</p>';
      const p = await call('drawing_preview', leggi(), tutte());
      if (!p.ok) { $('#tav-view').innerHTML = `<div class="msg err">${esc(p.message)}</div>`; return; }
      fogli = p.sheets;
      $('#tav-tabs').innerHTML = fogli.map((f, i) => `<button data-i="${i}">${i + 1}. ${esc(f.title)}</button>`).join('');
      document.querySelectorAll('#tav-tabs button').forEach(b => { b.onclick = () => mostra(+b.dataset.i); });
      mostra(0);
    });
    const esporta = fmt => inCoda(async () => { const x = await call('export_drawings_dialog', fmt, leggi(), tutte()); if (!x.cancelled) toast(x.message, x.ok ? '' : 'err'); });
    $('#m-no').onclick = close;
    $('#tav-agg').onclick = anteprima;
    $('#tav-pdf').onclick = () => esporta('pdf');
    $('#tav-dxf').onclick = () => esporta('dxf');
    if ($('#tav-tutte')) $('#tav-tutte').onchange = anteprima;
    anteprima();
  });
  $('#modal-box').classList.add('wide');
}

function newAssemblyDialog() {
  modal(`<h3>Nuovo assieme</h3><div class="form"><label style="grid-column:1/-1">Nome<input class="field" id="n-name" value="Assieme"></label></div>
    <p class="hint">Poi «Inserisci pezzo» per mettere i pezzi (file .steelcad) e gli accoppiamenti per posizionarli.</p>
    <div class="acts"><button class="btn" id="n-no">Annulla</button><button class="btn primary" id="n-ok">Crea</button></div>`, close => {
    $('#n-no').onclick = close;
    $('#n-ok').onclick = () => { const n = $('#n-name').value.trim() || 'Assieme'; close(); primaVolta = true; clearSelection();
      inCoda(async () => { if (await apply(await call('new_assembly', n))) hideHome(); }); };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#n-ok').click(); if (ev.key === 'Escape') close(); };
  });
}

function foldPanel(s) {
  const d = s.def;
  return `<div class="fhead"><div><h3>Piega ${esc(s.fold)}</h3><div class="fsub">piega su linea</div></div>
      <button class="ibtn danger" id="f-del" title="Elimina la piega (la lamiera torna piana lì)"><img src="icons/delete.svg" alt=""></button></div>
    <div class="ff"><label>Angolo<span class="inp"><input class="field" id="f-ang" value="${esc(String(d.angle).replace('.', ','))}"><i>°</i></span></label><span></span></div>
    <div class="seg-row"><span>Verso</span><div class="seg" id="f-dir">${[['up', 'su'], ['down', 'giù']].map(([k, t]) => `<button type="button" data-v="${k}" class="${d.direction === k ? 'on' : ''}">${t}</button>`).join('')}</div></div>
    <div class="row-btns"><button class="btn" id="f-flip">Piega l’altra parte</button></div>
    <p class="hint">La lunghezza la calcolo io: quella che serve perché lo sviluppo resti quello disegnato.</p>
    <details class="fsec"><summary>Dati di piega</summary><table class="grid">${s.rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table></details>`;
}
function wireFold(s) {
  const edit = f => inCoda(async () => { if (await apply(await call('edit_fold', s.feature, s.fold, f))) await refreshSel(); });
  $('#f-ang').onkeydown = ev => { if (ev.key === 'Enter') edit({ angle: $('#f-ang').value.trim() }); };
  $('#f-ang').onchange = () => edit({ angle: $('#f-ang').value.trim() });
  $('#f-dir').onchange = () => edit({ direction: $('#f-dir .on').dataset.v });
  $('#f-flip').onclick = () => edit({ flip: !s.def.flip });
  $('#f-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('delete_fold', s.feature, s.fold))); };
}
function wireFlange(s) {
  // le modifiche valgono subito: Invio o uscendo dal campo, clic su Verso/Misura
  let prima = JSON.stringify(readFlange());
  const applica = () => {
    const f = readFlange();
    if (JSON.stringify(f) === prima) return;
    prima = JSON.stringify(f);
    inCoda(async () => apply(await call('edit_flange', s.feature, s.flange, f)));
  };
  ['#f-len', '#f-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') applica(); }; $(q).onchange = applica; });
  $('#f-dir').onchange = applica; $('#f-pos').onchange = applica;
  if ($('#f-gap')) {
    const gap = () => inCoda(async () => apply(await call('edit_flange', s.feature, s.flange, { gap: $('#f-gap').value.trim() })));
    $('#f-gap').onkeydown = ev => { if (ev.key === 'Enter') gap(); };
    $('#f-gap').onchange = gap;
  }
  $('#f-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('delete_flange', s.feature, s.flange))); };
  if ($('#i-add')) $('#i-add').onclick = () => inCoda(async () => apply(await call('auto_tabs', s.feature, s.flange,
    $('#i-n').value.trim(), $('#i-w').value.trim(), $('#i-c').value.trim(), $('#i-s').value.trim())));
  if ($('#f-ext')) $('#f-ext').onclick = () => inCoda(async () => { if (await apply(await call('extend_over_tab', s.feature, s.flange))) await refreshSel(); });
  if ($('#f-tipc')) $('#f-tipc').onchange = () => inCoda(async () => { if (await apply(await call('set_tip_corners', s.feature, $('#f-tipc').value))) await refreshSel(); });
  if ($('#t-add')) {
    const punta = () => {
      ultimaPunta = readFlange('t');
      const gen = selGen;
      inCoda(async () => {
        const r = await call('add_flange', s.feature, null, ultimaPunta, s.flange);
        if (await apply(r)) {
          if (selGen === gen) await select(r.select);
          if (r.ask_tip_corners) askTipCorners(r.ask_tip_corners);
        }
      });
    };
    $('#t-add').onclick = punta;
    $('#t-orlo').onclick = () => { $('#t-ang').value = '180'; if (!$('#t-len').value.trim() || $('#t-len').value === '20') $('#t-len').value = '10'; punta(); };
    ['#t-len', '#t-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') punta(); }; });
    if (s.tip_form) $('#t-len').focus();          // hai cliccato la punta: si parte da lì
  }
  document.querySelectorAll('#props .corner').forEach(div => {
    const salva = () => inCoda(async () => apply(await call('set_corner', s.feature, s.flange, div.dataset.other,
      div.querySelector('[data-corner]').value, div.querySelector('[data-cgap]').value)));
    div.querySelector('[data-corner]').onchange = salva;
    div.querySelector('[data-cgap]').onkeydown = ev => { if (ev.key === 'Enter') salva(); };
  });
}

// --------------------------------------------------------------- scheda Lamiera
function renderSheet() {
  const sh = S.sheet;
  const cut = document.querySelector('.tabs button[data-tab="cut"]');
  cut.hidden = !S.cutlist?.rows?.length;                     // la cut list serve solo con le strutture
  ribbonTabs();
  if (cut.hidden && !$('#tab-cut').hidden) document.querySelector('.tabs button[data-tab="bom"]').click();
  $('#tab-btn-sheet').hidden = !sh;
  if (!sh) { if (!$('#tab-sheet').hidden) document.querySelector('.tabs button[data-tab="bom"]').click(); return; }
  const d = sh.def, manca = new Set(sh.missing || []);
  const campo = (k, label, miss) => `<label for="t-${k}">${label}</label><input class="field${miss ? ' missing' : ''}" id="t-${k}" data-tech="${k}"
      value="${esc(d[k] == null ? '' : String(d[k]).replace('.', ','))}" placeholder="${miss ? 'manca: dato della piegatrice' : ''}">`;
  const tech = `<div class="tech">${campo('thickness', 'Spessore (mm)', false)}${campo('radius', 'Raggio interno (mm)', manca.has('raggio interno'))}
    <label for="t-method">Calcolo della piega</label><select class="field" id="t-method">${opts(sh.methods, d.method || 'k')}</select>
    ${d.method === 'bd90' ? campo('bd90', 'Deduzione a 90° (mm)', manca.has('deduzione a 90°')) : d.method === 'din6935' ? '' : campo('k', 'K-factor', manca.has('K-factor'))}</div>
    ${manca.size ? `<div class="msg err">Mancano: ${esc([...manca].join(', '))}. Sono dati della tua piegatrice: senza, le flange non si possono calcolare.</div>` : ''}
    ${sh.after.length ? `<div class="msg warn">Dopo la lamiera ci sono altre lavorazioni (${esc(sh.after.join(', '))}): lo sviluppo non le contiene.</div>` : ''}`;
  const data = sh.data;
  const pieghe = data && data.bends.length ? `<table class="grid"><thead><tr><th>Flangia</th><th>Lato</th><th class="n">L</th><th class="n">Angolo</th><th>Verso</th>
    <th class="n">R</th><th class="n">K</th><th class="n">BA</th><th class="n">BD</th></tr></thead><tbody>${data.bends.map(b => `<tr data-fl="${esc(b.flange)}">
    <td>${esc(b.flange)}</td><td>${esc(b.edge)}</td><td class="n">${num(b.length, 2)}</td><td class="n">${num(b.angle, 2)}°</td><td>${b.direction === 'up' ? 'su' : 'giù'}</td>
    <td class="n">${num(b.r, 2)}</td><td class="n">${num(b.k, 3)}</td><td class="n">${num(b.ba, 3)}</td><td class="n">${num(b.bd, 3)}</td></tr>`).join('')}</tbody></table>`
    : '<p class="empty">Nessuna piega. Clicca un fianco della lamiera nel modello per aggiungere una flangia.</p>';
  let flat = '<p class="empty">Lo sviluppo compare quando la lamiera è costruita.</p>';
  if (data && data.outline.length) {
    const xs = data.outline.flatMap(p => p.filter((_, i) => i % 2 === 0)), ys = data.outline.flatMap(p => p.filter((_, i) => i % 2 === 1));
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), m = Math.max(x1 - x0, y1 - y0) * 0.04;
    const path = data.outline.map(p => 'M' + p.map((v, i) => i % 2 ? (-v).toFixed(2) : v.toFixed(2)).join(' ').replace(/(\S+) (\S+)/g, '$1,$2 ') + 'Z').join(' ');
    const linee = data.bend_lines.map(([a, b]) => `<line class="bend" x1="${a[0]}" y1="${-a[1]}" x2="${b[0]}" y2="${-b[1]}"/>`).join('');
    flat = `<svg id="flat-svg" viewBox="${x0 - m} ${-y1 - m} ${x1 - x0 + 2 * m} ${y1 - y0 + 2 * m}" preserveAspectRatio="xMidYMid meet">
      <path class="cut" fill-rule="evenodd" d="${path}"/>${linee}</svg>
      <div class="kv"><span>Sviluppo</span><span>${num(data.flat_size[0], 2)} × ${num(data.flat_size[1], 2)} mm</span>
      <span>Area</span><span>${num(data.flat_area / 1e6, 4)} m²</span></div>
      <div class="row-btns"><button class="btn primary" data-cmd="export_dxf">Esporta sviluppo DXF…</button>
      <button class="btn" data-cmd="unfold">Spiega</button><button class="btn" data-cmd="flat_sketch">Disegna sullo sviluppo</button></div>`;
  }
  const attivo = document.activeElement?.dataset?.tech ? { k: document.activeElement.dataset.tech, v: document.activeElement.value } : null;
  $('#tab-sheet').innerHTML = `<div class="sheet-cols"><div><h4>Dati di piega</h4>${tech}</div><div><h4>Pieghe</h4>${pieghe}</div><div><h4>Sviluppo</h4>${flat}</div></div>`;
  if (attivo) {               // stavi scrivendo in un campo: il ridisegno non ti toglie quello che hai scritto
    const i = document.querySelector(`[data-tech="${attivo.k}"]`);
    if (i) { i.value = attivo.v; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
  }
  $('#sheet-badge').textContent = manca.size ? '!' : '';
  const salva = fields => inCoda(async () => apply(await call('set_sheet_tech', sh.feature, fields)));
  document.querySelectorAll('[data-tech]').forEach(i => {
    const ora = d[i.dataset.tech] == null ? '' : String(d[i.dataset.tech]).replace('.', ',');
    i.onkeydown = ev => { if (ev.key === 'Enter') salva({ [i.dataset.tech]: i.value }); };
    i.onblur = () => { if (i.value.trim() !== ora) salva({ [i.dataset.tech]: i.value }); };
  });
  $('#t-method').onchange = () => salva({ method: $('#t-method').value });
  document.querySelectorAll('#tab-sheet tr[data-fl]').forEach(tr => { tr.onclick = () => select(`flange=${sh.feature}/${tr.dataset.fl}`); });
}

let ultimaAsta = { length: '500', profile: null, group: '' };
function nodePanel(s) {
  const p = s.position;
  const cosa = { abs: 'Coordinate (mm, anche parametri)', from: `Spostamento dal nodo ${p.base}`, sketch: `Spostamento dal punto ${p.base} dello sketch` }[p.mode];
  const pos = p.mode === 'fixed' ? '<p class="hint">Il nodo è l’estremo di una linea di sketch: si sposta cambiando lo sketch.</p>'
    : `<div class="sub">Posizione</div><p class="hint" style="margin:0 0 4px">${esc(cosa)}</p><div class="xyz">${['X', 'Y', 'Z'].map((a, i) =>
      `<label>${a}<input class="field" data-xyz="${i}" value="${esc(String(p.values[i] ?? 0).replace('.', ','))}"></label>`).join('')}</div>
      <div class="row-btns"><button class="btn" id="n-move">Sposta</button></div>`;
  const tipo = s.joint.type || 'auto';
  const opt = Object.entries(s.joint_types).map(([k, v]) => `<option value="${k}"${k === tipo ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const through = s.members.map(m => `<label class="check"><input type="checkbox" data-th="${esc(m)}"${(s.joint.through || []).includes(m) ? ' checked' : ''}> ${esc(m)} passa</label>`).join('');
  const giunto = s.members.length ? `<div class="sub">Giunto</div><select class="field" id="n-joint">${opt}</select>
      <div id="n-joint-more"><div class="through" data-for="butt">${through}</div>
      <label class="lbl" data-for="angle">Angolo del taglio (°)<input class="field" id="n-angle" value="${esc(s.joint.angle ?? 0)}"></label>
      <div class="row-btns"><button class="btn" id="n-joint-ok">Applica giunto</button></div></div>` : '';
  if (!ultimaAsta.profile) ultimaAsta.profile = s.default_profile;
  const dir = ['X+', 'Y+', 'Z+', 'X-', 'Y-', 'Z-'];
  return giunto + pos + `<div class="sub">Nuova asta da qui</div>
    <div class="xyz"><label>Lunghezza<input class="field" id="n-len" value="${esc(ultimaAsta.length)}"></label>
    <label style="grid-column:span 2">Profilo<input class="field" id="n-prof" list="dl-prof2" value="${esc(ultimaAsta.profile)}" spellcheck="false"></label></div>
    <datalist id="dl-prof2">${(profili || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist>
    <label class="lbl" style="display:block;margin-top:4px">Gruppo<input class="field" id="n-group" value="${esc(ultimaAsta.group)}" placeholder="es. Montanti"></label>
    <p class="hint" style="margin:6px 0 4px">Direzione:</p>
    <div class="dirs">${dir.map(d => `<button class="btn" data-dir="${d}">${d}</button>`).join('')}</div>
    <div class="row-btns"><button class="btn" id="n-link">Collega a un altro nodo…</button></div>`;
}
function wireNode(s) {
  const more = () => {
    const t = $('#n-joint')?.value;
    if (!t) return;
    $('#n-joint-more').hidden = !['butt', 'angle'].includes(t);
    $('#n-joint-more').querySelectorAll('[data-for]').forEach(x => { x.hidden = x.dataset.for !== t; });
  };
  const giunto = () => {
    const t = $('#n-joint').value;
    const spec = { type: t };
    if (t === 'butt') spec.through = [...document.querySelectorAll('[data-th]:checked')].map(x => x.dataset.th);
    if (t === 'angle') spec.angle = $('#n-angle').value;
    inCoda(async () => apply(await call('set_joint', s.structure, s.key, spec)));
  };
  if ($('#n-joint')) {
    more();
    $('#n-joint').onchange = () => { more(); if (!['butt', 'angle'].includes($('#n-joint').value)) giunto(); };
    $('#n-joint-ok').onclick = giunto;
  }
  if ($('#n-move')) {
    const sposta = () => inCoda(async () => apply(await call('move_node', s.structure, s.key,
      [...document.querySelectorAll('[data-xyz]')].map(x => x.value))));
    $('#n-move').onclick = sposta;
    document.querySelectorAll('[data-xyz]').forEach(x => { x.onkeydown = ev => { if (ev.key === 'Enter') sposta(); }; });
  }
  const ricorda = () => { ultimaAsta = { length: $('#n-len').value.trim(), profile: $('#n-prof').value.trim(), group: $('#n-group').value.trim() }; };
  document.querySelectorAll('[data-dir]').forEach(b => {
    b.onclick = () => {
      ricorda();
      inCoda(async () => {
        const r = await call('add_member', s.structure, s.key, null, b.dataset.dir, ultimaAsta.length, ultimaAsta.profile, ultimaAsta.group || null);
        if (await apply(r)) await select(r.node);     // si continua dal nodo nuovo, come una polilinea
      });
    };
  });
  $('#n-link').onclick = () => {
    ricorda();
    linkFrom = { st: s.structure, key: s.key, profile: ultimaAsta.profile, group: ultimaAsta.group };
    paintNodes();
  };
}

// --------------------------------------------------------------- distinta, cut list, info
function renderBottom() {
  const b = S.bom;
  $('#tab-bom').innerHTML = b.length ? `<table class="grid"><thead><tr><th>Codice</th><th>Descrizione</th><th class="n">Q.tà</th>
    <th>Materiale</th><th>Profilo / spessore</th><th class="n">Peso cad. kg</th><th class="n">Peso tot. kg</th></tr></thead><tbody>
    ${b.map(r => `<tr><td>${esc(r.code)}</td><td>${esc(r.description)}</td><td class="n">${r.qty}</td><td>${esc(r.material)}</td>
      <td>${esc(r.profile || (r.thickness_mm != null ? 'sp. ' + num(r.thickness_mm) + ' mm' : ''))}</td>
      <td class="n">${kg(r.kg_each)}</td><td class="n">${kg(r.kg_total)}</td></tr>`).join('')}
    <tr class="tot"><td colspan="6">Totale</td><td class="n">${kg(S.bom_kg)}</td></tr></tbody></table>`
    : '<p class="empty">Il progetto è vuoto.</p>';

  const c = S.cutlist;
  $('#tab-cut').innerHTML = c.rows.length ? `<div class="cols"><table class="grid"><thead><tr><th>Profilo</th><th class="n">Lunghezza mm</th>
    <th>Tagli</th><th class="n">Q.tà</th><th>Gruppo</th><th class="n">kg cad.</th><th class="n">kg tot.</th></tr></thead><tbody>
    ${c.rows.map(r => `<tr data-ids="${esc(r.members.join(','))}"><td>${esc(r.profile)} ${esc(r.material)}</td><td class="n">${num(r.length_mm)}</td>
      <td>${esc(r.cuts.join(' / '))}</td><td class="n">${r.qty}</td><td>${esc(r.groups.join(', '))}</td>
      <td class="n">${kg(r.kg_each)}</td><td class="n">${kg(r.kg_total)}</td></tr>`).join('')}
    <tr class="tot"><td colspan="3">Totale</td><td class="n">${c.pieces}</td><td></td><td></td><td class="n">${kg(c.kg)}</td></tr></tbody></table>
    <table class="grid"><thead><tr><th>Per profilo</th><th class="n">Pezzi</th><th class="n">Metri</th><th class="n">kg</th></tr></thead><tbody>
    ${c.totals.map(t => `<tr><td>${esc(t.profile)} ${esc(t.material)}</td><td class="n">${t.pieces}</td>
      <td class="n">${num(t.total_length_mm / 1000, 2)}</td><td class="n">${kg(t.kg)}</td></tr>`).join('')}</tbody></table></div>`
    : '<p class="empty">Nessuna struttura in tubolare in questo progetto.</p>';

  const i = S.info;
  const kv = [['Ricostruzione', `${num(i.rebuild_ms)} ms`], ['Ricostruite / dalla cache', `${i.rebuilt} / ${i.cached}`], ['Materiale', i.material]];
  if (i.part) kv.push(['Pezzo', `${kg(i.part.mass_kg)} kg, ${i.part.size_mm.map(v => num(v)).join(' × ')} mm`]);
  kv.push(['Peso totale', `${kg(S.bom_kg)} kg`]);
  $('#tab-info').innerHTML = `<div class="kv">${kv.map(([k, v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join('')}</div>` +
    S.errors.map(e => `<div class="msg err"><b>${esc(e.id)}</b>: ${esc(e.message)}</div>`).join('') +
    S.warnings.map(w => `<div class="msg warn">${esc(w)}</div>`).join('');
  const n = S.errors.length + S.warnings.length;
  const badge = $('#info-badge');
  badge.textContent = n ? String(n) : '';
  badge.classList.toggle('err', S.errors.length > 0);
}
$('#tab-cut').addEventListener('click', ev => {
  const tr = ev.target.closest('tr[data-ids]');
  if (!tr || !tr.dataset.ids) return;
  const ids = tr.dataset.ids.split(',').filter(id => objs.has(id));
  if (ids.length) select(ids[0], null, ids.length > 1 ? ids : null);
});
document.querySelector('.tabs').addEventListener('click', ev => {
  const b = ev.target.closest('button[data-tab]');
  if (!b) return;
  for (const x of document.querySelectorAll('.tabs button')) x.classList.toggle('on', x === b);
  for (const t of ['bom', 'cut', 'sheet', 'info']) $('#tab-' + t).hidden = t !== b.dataset.tab;
});

// ===================================================================== comandi
function toast(msg, kind = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = msg;
  $('#toasts').appendChild(t);
  while ($('#toasts').children.length > 3) $('#toasts').firstChild.remove();
  setTimeout(() => t.remove(), kind === 'err' ? 7000 : 3500);
}

function modal(html, wire) {
  $('#modal-box').classList.remove('wide');
  $('#modal-box').innerHTML = html;
  $('#modal').hidden = false;
  const close = () => { $('#modal').hidden = true; };
  wire(close);
  $('#modal-box').querySelector('input, button.primary')?.focus();
}

function newDialog(iniziale = 'lamiera') {
  const MODELLI = {
    telaio: { titolo: 'Telaio / tavolo', nota: 'Telaio sopra e 4 gambe in tubolare',
      campi: [['L', 'Lunghezza', 2000], ['P', 'Profondità', 1000], ['H', 'Altezza', 900], ['profilo', 'Profilo telaio', '40x40x3'], ['gambe', 'Profilo gambe', '40x40x3']] },
    zero: { titolo: 'Da zero', nota: 'Disegni il contorno, poi lamiera o piastra', campi: [] },
    disegno: { titolo: 'Struttura da disegno', nota: 'Disegni lo scheletro, poi Crea struttura',
      campi: [['piano', 'Su quale piano disegni', 'XZ', { XZ: 'Di fronte (XZ): cancelli, spalle', XY: 'Pianta (XY): basamenti, telai a terra', YZ: 'Di fianco (YZ)' }]] },
    scaffale: { titolo: 'Scaffale', nota: 'Due spalle collegate a ogni ripiano',
      campi: [['L', 'Lunghezza', 1000], ['P', 'Profondità', 400], ['H', 'Altezza', 1800], ['ripiani', 'Ripiani (a terra e in cima compresi)', 4],
        ['montanti', 'Profilo montanti', '30x30x2'], ['traversi', 'Profilo traversi', '40x20x2']] },
    armadio: { titolo: 'Telaio armadio', nota: 'Telaio da chiudere con la lamiera',
      campi: [['L', 'Larghezza', 800], ['P', 'Profondità', 600], ['H', 'Altezza', 2000], ['ripiani', 'Livelli (sotto e sopra compresi)', 3], ['profilo', 'Profilo', '40x40x2']] },
    cancello: { titolo: 'Cancello', nota: 'Telaio e sbarre a passo uguale',
      campi: [['L', 'Larghezza', 1500], ['H', 'Altezza', 1200], ['telaio', 'Profilo telaio', '60x60x3'], ['sbarre', 'Profilo sbarre', '20x20x2'], ['passo', 'Passo sbarre', 120]] },
    vuoto: { titolo: 'Struttura nodo per nodo', nota: 'Parti da un nodo e tiri le aste', campi: [] },
    lamiera: { titolo: 'Lamiera', nota: 'Base piegata: poi clic su un lato per la flangia',
      campi: [['larghezza', 'Larghezza', 500], ['profondita', 'Profondità', 300], ['spessore', 'Spessore', 2],
        ['raggio', 'Raggio interno di piega', ''], ['k', 'K-factor', '']] },
    piastra: { titolo: 'Piastra', nota: 'Lamiera piana con foro, per DXF',
      campi: [['larghezza', 'Larghezza', 300], ['altezza', 'Altezza', 200], ['spessore', 'Spessore', 5], ['foro', 'Diametro foro', 30]] },
  };
  let kind = iniziale;
  const disegna = () => {
    const m = MODELLI[kind];
    return `<h3>Nuovo progetto</h3>
      <div class="choice">${Object.entries(MODELLI).map(([k, v]) => `<button data-k="${k}" class="${k === kind ? 'on' : ''}">${esc(v.titolo)}<small>${esc(v.nota)}</small></button>`).join('')}</div>
      <div class="form"><label style="grid-column:1/-1">Nome<input class="field" id="n-name" value="${{ telaio: 'Tavolo', piastra: 'Piastra', vuoto: 'Struttura', lamiera: 'Lamiera', zero: 'Pezzo', disegno: 'Struttura', scaffale: 'Scaffale', armadio: 'Telaio armadio', cancello: 'Cancello' }[kind]}"></label>
      ${m.campi.map(([k, l, v, scelte]) => scelte
        ? `<label style="grid-column:1/-1">${esc(l)}<select class="field" data-f="${k}">${Object.entries(scelte).map(([a, b]) => `<option value="${a}"${a === v ? ' selected' : ''}>${esc(b)}</option>`).join('')}</select></label>`
        : `<label>${esc(l)}<input class="field" data-f="${k}" value="${esc(v)}"></label>`).join('')}</div>
      ${S?.dirty ? '<div class="msg warn">Le modifiche non salvate del progetto aperto andranno perse (resta il salvataggio automatico).</div>' : ''}
      <div class="acts"><button class="btn" id="n-no">Annulla</button><button class="btn primary" id="n-ok">Crea</button></div>`;
  };
  const wire = close => {
    $('#modal-box').querySelectorAll('.choice button').forEach(b => b.onclick = () => { kind = b.dataset.k; $('#modal-box').innerHTML = disegna(); wire(close); });
    $('#n-no').onclick = close;
    $('#n-ok').onclick = () => {
      const v = { name: $('#n-name').value.trim() || MODELLI[kind].titolo };
      $('#modal-box').querySelectorAll('[data-f]').forEach(i => { v[i.dataset.f] = i.value.trim(); });
      close();
      primaVolta = true; sel = null; clearSelection();
      if (SK) exitSketch();
      inCoda(async () => {
        if (!(await apply(await call('new_project', kind, v)))) return;
        hideHome();
        if (kind === 'zero' || kind === 'disegno') await enterSketch('S1');
      });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#n-ok').click(); if (ev.key === 'Escape') close(); };
  };
  modal(disegna(), wire);
}

// Regole di lamiera: i dati della piegatrice salvati per materiale/spessore, riusati in ogni progetto
async function rulesDialog() {
  const r = await call('sheet_rules');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const fid = S?.sheet?.feature;
  const n = v => (v == null || v === '' ? '–' : String(v).replace('.', ','));
  const righe = r.rules.map(x => `<tr><td><b>${esc(x.name)}</b><br><span class="hint">${esc(x.material || '')} · sp. ${n(x.thickness)} · R ${n(x.radius)} ·
    ${x.method === 'bd90' ? 'BD90 ' + n(x.bd90) : x.method === 'din6935' ? 'DIN 6935' : 'K ' + n(x.k)}</span></td>
    <td style="white-space:nowrap">${fid ? `<button class="btn primary" data-rule-apply="${esc(x.name)}">Usa</button>` : ''}
    <button class="btn" data-rule-del="${esc(x.name)}" title="Elimina la regola">×</button></td></tr>`).join('')
    || '<tr><td class="hint">Ancora nessuna regola. Inserisci i dati di piega nella scheda Lamiera e salvali qui con un nome.</td></tr>';
  modal(`<h3>Regole di lamiera</h3>
    <p class="hint">I dati della tua piegatrice (spessore, raggio interno, K o deduzione) salvati con un nome: li riusi in ogni progetto con un clic.</p>
    <table class="grid">${righe}</table>
    ${fid ? `<div class="form" style="margin-top:12px"><label style="grid-column:1/-1">Salva i dati di piega di questa lamiera come
      <input class="field" id="r-name" placeholder="es. S235 sp. 2 – matrice V16"></label></div>` : '<p class="hint">Apri o crea una lamiera per usare o salvare una regola.</p>'}
    <div class="acts"><button class="btn" id="m-no">Chiudi</button>${fid ? '<button class="btn primary" id="r-save">Salva regola</button>' : ''}</div>`, close => {
    $('#m-no').onclick = close;
    if ($('#r-save')) $('#r-save').onclick = () => inCoda(async () => {
      const x = await call('save_sheet_rule', fid, $('#r-name').value);
      if (!x.ok) { toast(x.message, 'err'); return; }
      toast(x.message); close(); rulesDialog();
    });
    $('#modal-box').querySelectorAll('[data-rule-apply]').forEach(b => { b.onclick = () => { close(); inCoda(async () => apply(await call('apply_sheet_rule', fid, b.dataset.ruleApply), 'Regola applicata.')); }; });
    $('#modal-box').querySelectorAll('[data-rule-del]').forEach(b => { b.onclick = () => inCoda(async () => { await call('delete_sheet_rule', b.dataset.ruleDel); close(); rulesDialog(); }); });
  });
}

async function openProject(percorso) {
  const r = percorso ? await call('open_recent', percorso) : await call('open_dialog');
  if (r.recovery) {
    modal(`<h3>C’è un salvataggio automatico più recente</h3><p>Il file <b>${esc(r.path)}</b> ha un salvataggio automatico fatto dopo l’ultimo
      salvataggio. Probabilmente il programma si è chiuso prima di salvare.</p>
      <div class="acts"><button class="btn" id="r-no">Apri il file salvato</button><button class="btn primary" id="r-ok">Recupera le modifiche</button></div>`,
    close => {
      const vai = rec => { close(); primaVolta = true; clearSelection(); inCoda(async () => { if (await apply(await call('open_path', r.path, rec), rec ? 'Modifiche recuperate.' : null)) hideHome(); }); };
      $('#r-no').onclick = () => vai(false); $('#r-ok').onclick = () => vai(true);
    });
    return;
  }
  if (r.ok) { primaVolta = true; clearSelection(); }
  if (await apply(r)) hideHome();
}

// ------------------------------------------------------------- import DXF / DWG
// Lo sviluppo piano diventa una lamiera: si sceglie il contorno del pezzo (clic sull'anteprima), si danno i dati
// della piegatrice; le linee di piega diventano flange, i fori e le sagome un taglio sullo sviluppo.
async function importDialog(percorso) {
  const r = percorso ? await call('import_dxf', percorso) : await call('import_dxf_dialog');
  if (!r.ok) { if (!r.cancelled) toast(r.message, 'err'); return; }
  let giro = r.giro || null;
  const virg = v => (v === null || v === undefined ? '' : String(v).replace('.', ','));
  const regole = r.rules || [];
  const mat = r.materiale || 'S235';
  modal(`<div class="tav imp"><div class="tav-side"><h3>Importa ${esc(r.name)}</h3>
      <div class="imp-info" id="imp-info"></div>
      <div class="form">
        <label style="grid-column:1/-1">Nome<input class="field" id="imp-name" value="${esc(r.name)}"></label>
        <label>Materiale<select class="field" id="imp-mat">${r.materiali.map(m => `<option value="${esc(m.code)}"${m.code === mat ? ' selected' : ''}>${esc(m.code)}</option>`).join('')}</select></label>
        <label>Spessore<input class="field" id="imp-sp" value="${virg(r.spessore)}" placeholder="mm"></label>
        ${regole.length ? `<label style="grid-column:1/-1">Regola di piega<select class="field" id="imp-rule"><option value="">— scrivi i dati qui sotto —</option>
          ${regole.map((x, i) => `<option value="${i}">${esc(x.name)}</option>`).join('')}</select></label>` : ''}
        <label>Raggio interno<input class="field" id="imp-r" placeholder="mm"></label>
        <label>Metodo<select class="field" id="imp-met"><option value="k">K-factor</option><option value="din6935">DIN 6935</option><option value="bd90">Deduzione 90°</option></select></label>
        <label id="imp-k-l">K-factor<input class="field" id="imp-k" placeholder="es. 0,4"></label>
        <label id="imp-bd-l" hidden>Deduzione 90°<input class="field" id="imp-bd" placeholder="mm"></label>
        <label>Angolo pieghe<input class="field" id="imp-ang" value="90"></label>
        <label>Verso<select class="field" id="imp-dir"><option value="up">su</option><option value="down">giù</option></select></label>
      </div>
      <div id="imp-bends"></div>
      <p class="hint">Clic sull’anteprima per scegliere il contorno del pezzo. Le linee di piega sono la mezzeria della piega: lo sviluppo del pezzo torna uguale al disegno.</p>
      <div id="imp-msg"></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="imp-ok">Crea il pezzo</button></div></div>
      <div class="tav-main"><div class="imp-view" id="imp-view">${r.svg}</div></div></div>`, close => {
    const view = $('#imp-view');
    const mostra = () => {
      view.querySelectorAll('path.giro').forEach(p => p.classList.toggle('scelto', giro && +p.dataset.giro === giro.index));
      const utili = new Set(giro ? giro.pieghe : []);
      view.querySelectorAll('line.piega').forEach(l => l.classList.toggle('utile', utili.has(+l.dataset.piega)));
      if (!giro) {
        $('#imp-info').innerHTML = '<div class="msg warn">Scegli il contorno del pezzo sull’anteprima.</div>';
        $('#imp-bends').innerHTML = '';
        return;
      }
      const [w, h] = giro.size;
      $('#imp-info').innerHTML = `<p><b>${num(w)} × ${num(h)} mm</b> · ${giro.tagli} fori/scassi · ${giro.pieghe.length} linee di piega`
        + `${r.pieghe_tot > giro.pieghe.length ? ` <span class="hint">(${r.pieghe_tot - giro.pieghe.length} linee tratto-punto ignorate: assi o fuori dal pezzo)</span>` : ''}</p>`
        + (r.aperti ? `<p class="hint">${r.aperti} tratti del disegno non chiudono un contorno: se il pezzo non c’è, il suo contorno è aperto.</p>` : '');
      $('#imp-bends').innerHTML = giro.pieghe.length ? `<table class="imp-bt"><tr><th>Piega</th><th>Lungh.</th><th>Angolo</th><th>Verso</th></tr>
        ${giro.pieghe.map((p, i) => `<tr data-i="${i}" data-p="${p}"><td>${i + 1}</td><td>${num(giro.lunghezze[i])}</td>
          <td><input class="field" data-b="angle" placeholder="${esc($('#imp-ang').value)}"></td>
          <td><select class="field" data-b="direction"><option value="">=</option><option value="up">su</option><option value="down">giù</option></select></td></tr>`).join('')}</table>` : '';
      $('#imp-bends').querySelectorAll('tr[data-p]').forEach(tr => {
        const l = view.querySelector(`line.piega[data-piega="${tr.dataset.p}"]`);
        tr.onmouseenter = () => l?.classList.add('hl');
        tr.onmouseleave = () => l?.classList.remove('hl');
      });
    };
    view.querySelectorAll('path.giro').forEach(p => {
      p.onclick = () => inCoda(async () => {
        const x = await call('import_dxf_giro', +p.dataset.giro);
        if (!x.ok) { toast(x.message, 'err'); return; }
        giro = x.giro; mostra();
      });
    });
    const metodo = () => { $('#imp-k-l').hidden = $('#imp-met').value !== 'k'; $('#imp-bd-l').hidden = $('#imp-met').value !== 'bd90'; };
    $('#imp-met').onchange = metodo;
    if ($('#imp-rule')) $('#imp-rule').onchange = () => {
      const x = regole[+$('#imp-rule').value];
      if (!x) return;
      if (x.material && [...$('#imp-mat').options].some(o => o.value === x.material)) $('#imp-mat').value = x.material;
      if (x.thickness) $('#imp-sp').value = virg(x.thickness);
      $('#imp-r').value = virg(x.radius); $('#imp-met').value = x.method || 'k';
      $('#imp-k').value = virg(x.k); $('#imp-bd').value = virg(x.bd90); metodo();
    };
    $('#imp-ang').oninput = () => $('#imp-bends').querySelectorAll('[data-b="angle"]').forEach(i => { i.placeholder = $('#imp-ang').value; });
    $('#m-no').onclick = close;
    $('#imp-ok').onclick = () => inCoda(async () => {
      if (!giro) { $('#imp-msg').innerHTML = '<div class="msg err">Scegli prima il contorno del pezzo.</div>'; return; }
      const bends = [...$('#imp-bends').querySelectorAll('tr[data-p]')].map(tr => ({
        angle: tr.querySelector('[data-b="angle"]').value.trim(), direction: tr.querySelector('[data-b="direction"]').value }));
      const params = { name: $('#imp-name').value.trim(), material: $('#imp-mat').value, thickness: $('#imp-sp').value.trim(),
        radius: $('#imp-r').value.trim(), method: $('#imp-met').value, k: $('#imp-k').value.trim(), bd90: $('#imp-bd').value.trim(),
        angle: $('#imp-ang').value.trim(), direction: $('#imp-dir').value, bends };
      $('#imp-msg').innerHTML = '<p class="hint">Costruisco il pezzo…</p>';
      const x = await call('import_dxf_create', giro.index, params);
      if (!x.ok) { $('#imp-msg').innerHTML = `<div class="msg err">${esc(x.message)}</div>`; return; }
      close();
      primaVolta = true; sel = null; clearSelection();
      if (SK) exitSketch();
      if (await apply(x)) {
        hideHome();
        if (x.avvisi && x.avvisi.length) toast(x.avvisi.join(' · '), 'err');
      }
    });
    mostra();
  });
  $('#modal-box').classList.add('wide');
}

// ------------------------------------------------------------- pagina iniziale
async function showHome(info) {
  info = info || await call('home_info');
  if (!info.ok) return;
  if (SK) exitSketch();
  const rec = info.recent.map(x => `<div class="home-rec" data-path="${esc(x.path)}" title="${esc(x.path)}">
      <img src="icons/box.svg" alt=""><div><b>${esc(x.name)}</b><span>${esc(x.folder)}</span></div><small>${esc(x.when)}</small>
      <button class="x" data-forget="${esc(x.path)}" title="Togli dai recenti">×</button></div>`).join('')
    || '<p class="hint">Ancora nessun progetto. Quelli che apri o salvi compaiono qui.</p>';
  $('#home-recent').innerHTML = rec;
  $('#home-unsaved').innerHTML = info.unsaved ? `<div class="home-unsaved"><div><b>Lavoro non salvato</b>
      <span>Salvataggio automatico del ${esc(info.unsaved.when)}: un progetto mai salvato con un nome.</span></div>
      <button class="btn" id="home-recover">Recupera</button></div>` : '';
  $('#home-close').hidden = !!info.show;              // all'avvio non c'è un progetto da cui tornare
  $('#home').hidden = false;
  document.body.classList.add('at-home');
  $('#home').querySelectorAll('[data-new]').forEach(b => {
    b.onclick = () => (b.dataset.new === 'assieme' ? newAssemblyDialog() : b.dataset.new === 'importa' ? inCoda(importDialog) : newDialog(b.dataset.new));
  });
  $('#home-open').onclick = () => inCoda(() => openProject());
  $('#home-close').onclick = hideHome;
  $('#home').querySelectorAll('.home-rec').forEach(d => { d.onclick = ev => { if (!ev.target.closest('.x')) inCoda(() => openProject(d.dataset.path)); }; });
  $('#home').querySelectorAll('[data-forget]').forEach(b => { b.onclick = () => inCoda(async () => showHome(await call('forget_recent', b.dataset.forget))); });
  if ($('#home-recover')) $('#home-recover').onclick = () => inCoda(async () => {
    primaVolta = true; clearSelection();
    if (await apply(await call('recover_unsaved'), 'Lavoro recuperato: salvalo con un nome.')) hideHome();
  });
}
function hideHome() {
  $('#home').hidden = true;
  document.body.classList.remove('at-home');
}

const CMDS = [
  { id: 'new', label: 'Nuovo progetto…', keys: 'Ctrl+N', run: () => newDialog() },
  { id: 'home', label: 'Pagina iniziale', run: () => inCoda(() => showHome()) },
  { id: 'new_asm', label: 'Nuovo assieme…', run: newAssemblyDialog },
  { id: 'drawings', label: 'Tavole con cartiglio (PDF e disegni)…', run: () => inCoda(drawingsDialog) },
  { id: 'asm_insert', label: 'Assieme: inserisci pezzo…', run: () => inCoda(async () => { const r = await call('asm_insert_dialog'); if (await apply(r) && r.select) await select(r.select); }) },
  { id: 'asm_interf', label: 'Assieme: controlla interferenze', run: () => inCoda(async () => {
    const r = await call('asm_interferences');
    if (!r.ok) { toast(r.message, 'err'); return; }
    if (!r.interferences.length) { toast(r.message); return; }
    sel = { id: r.interferences[0].a, ids: [...new Set(r.interferences.flatMap(x => [x.a, x.b]))] }; paint(); renderTree();
    toast('Interferenze: ' + r.interferences.map(x => x.label).join(' · '), 'err');
  }) },
  { id: 'asm_back', label: 'Torna all’assieme', run: () => inCoda(async () => { primaVolta = true; clearSelection(); await apply(await call('asm_back')); }) },
  { id: 'open', label: 'Apri progetto…', keys: 'Ctrl+O', run: () => inCoda(openProject) },
  { id: 'import_dxf', label: 'Importa sviluppo DXF / DWG…', run: () => inCoda(importDialog) },
  { id: 'save', label: 'Salva', keys: 'Ctrl+S', run: () => inCoda(async () => apply(await call('save', false), 'Salvato.')) },
  { id: 'saveas', label: 'Salva con nome…', keys: 'Ctrl+Maiusc+S', run: () => inCoda(async () => apply(await call('save', true), 'Salvato.')) },
  { id: 'export_step', label: 'Esporta STEP…', run: () => inCoda(async () => apply(await call('export', 'step'))) },
  { id: 'export_dxf', label: 'Esporta DXF di taglio…', run: () => inCoda(async () => apply(await call('export', 'dxf'))) },
  { id: 'undo', label: 'Annulla', keys: 'Ctrl+Z', run: () => S?.undo[0] && inCoda(async () => apply(await call('undo'))) },
  { id: 'redo', label: 'Ripeti', keys: 'Ctrl+Y', run: () => S?.redo[0] && inCoda(async () => apply(await call('redo'))) },
  { id: 'view_iso', label: 'Vista isometrica', keys: '0', run: () => goTo(VISTE.view_iso) },
  { id: 'view_top', label: 'Vista dall’alto', keys: '7', run: () => goTo(VISTE.view_top) },
  { id: 'view_front', label: 'Vista di fronte', keys: '1', run: () => goTo(VISTE.view_front) },
  { id: 'view_right', label: 'Vista da destra', keys: '3', run: () => goTo(VISTE.view_right) },
  { id: 'fit', label: 'Adatta alla finestra', keys: 'F', run: () => (SK ? fitSketch() : goTo(null, true)) },
  { id: 'toggle_dims', label: 'Mostra/nascondi quote', keys: 'Q', run: () => { showDims = !showDims; buildDims(); } },
  { id: 'toggle_theme', label: 'Tema scuro / chiaro', run: () => applyTheme(!document.body.classList.contains('dark')) },
  { id: 'unfold', label: 'Spiega / ripiega la lamiera', keys: 'U', run: () => toggleFlat() },
  { id: 'view_back', label: 'Vista da dietro', run: () => goTo(VISTE.view_back) },
  { id: 'view_left', label: 'Vista da sinistra', run: () => goTo(VISTE.view_left) },
  { id: 'view_bottom', label: 'Vista da sotto', run: () => goTo(VISTE.view_bottom) },
  { id: 'new_sheet', label: 'Nuova lamiera…', run: () => newDialog('lamiera') },
  { id: 'new_zero', label: 'Nuovo da zero (disegna)…', run: () => newDialog('zero') },
  { id: 'new_frame', label: 'Nuovo telaio / tavolo…', run: () => newDialog('telaio') },
  { id: 'new_free', label: 'Nuova struttura libera…', run: () => newDialog('vuoto') },
  { id: 'new_plate', label: 'Nuova piastra…', run: () => newDialog('piastra') },
  { id: 'flange_help', label: 'Flangia su un bordo', run: () => {
    if (!S?.sheet?.data) { toast('Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', 'err'); return; }
    if (flatView) toggleFlat(false);
    toast('Passa col mouse su un bordo della lamiera: si accende in arancio. Clicca e scegli lunghezza e verso.');
  } },
  { id: 'contour_help', label: 'Lamiera a contorno', run: () => toast(S?.sheet?.data
    ? 'Lamiera a contorno: clicca la faccia di estremità (testata) da cui partire, «Disegna su questa faccia», disegna la sezione con la Linea partendo dallo spigolo del bordo (arancio), poi «Lamiera a contorno».'
    : 'Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', S?.sheet?.data ? '' : 'err') },
  { id: 'face_help', label: 'Disegna su una faccia', run: () => toast('Clicca una faccia piana del pezzo, poi «Disegna su questa faccia» nel pannello a destra.') },
  { id: 'member_help', label: 'Nuova asta', run: () => toast(nodes.length ? 'Clicca un nodo (pallino) del telaio: nel pannello scegli direzione e lunghezza della nuova asta.' : 'Prima serve una struttura: Telaio / tavolo o Struttura libera.', nodes.length ? '' : 'err') },
  { id: 'export_bendtable', label: 'Esporta la tabella pieghe…', run: () => inCoda(async () => apply(await call('export', 'bendtable'))) },
  { id: 'sheet_rules', label: 'Regole di lamiera…', run: () => inCoda(rulesDialog) },
  { id: 'show_cut', label: 'Mostra la cut list', run: () => { const b = document.querySelector('.tabs button[data-tab="cut"]'); b.hidden = false; b.click(); } },
  { id: 'show_bom', label: 'Mostra la distinta', run: () => document.querySelector('.tabs button[data-tab="bom"]').click() },
  { id: 'flat_sketch', label: 'Disegna sullo sviluppo (spiega)', run: flatSketch },
  { id: 'palette', label: 'Cerca comando', keys: 'Ctrl+K', run: () => openPalette() },
];
const runCmd = id => CMDS.find(c => c.id === id)?.run();

document.addEventListener('click', ev => {
  const mi = ev.target.closest('.menu-item');
  for (const m of document.querySelectorAll('.menu-item')) if (m !== mi) m.classList.remove('open');
  if (mi && ev.target.closest('.menu-item > button')) { mi.classList.toggle('open'); return; }
  const b = ev.target.closest('[data-cmd]');
  if (b && !b.disabled) { mi?.classList.remove('open'); runCmd(b.dataset.cmd); }
});
document.querySelectorAll('.menu-item').forEach(m => m.addEventListener('mouseenter', () => {
  if (document.querySelector('.menu-item.open') && !m.classList.contains('open')) {
    document.querySelectorAll('.menu-item').forEach(x => x.classList.remove('open')); m.classList.add('open');
  }
}));

// --------------------------------------------------------------- palette comandi
let palItems = [], palOn = 0;
const norm = s => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
function openPalette() {
  $('#palette').hidden = false;
  $('#pal-input').value = '';
  fillPalette();
  $('#pal-input').focus();
}
function closePalette() { $('#palette').hidden = true; }
function fillPalette() {
  const q = $('#pal-input').value;
  const m = q.match(/^\s*([A-Za-z_]\w*)\s*=\s*(.+)$/);
  palItems = [];
  if (m) {
    const esiste = S.parameters.some(p => p.name === m[1]);
    palItems.push({ label: `${esiste ? 'Imposta' : 'Nuovo parametro'} ${m[1]} = ${m[2]}`, d: 'Invio',
      run: () => inCoda(async () => apply(await call('set_parameter', m[1], m[2]))) });
  }
  const nq = norm(q.trim());
  for (const p of S?.parameters || []) {
    if (!nq || norm(p.name).includes(nq)) palItems.push({ label: `Parametro ${p.name}`, d: `ora ${typeof p.value === 'string' ? p.value : num(p.value, 3)}`,
      keep: true, run: () => { $('#pal-input').value = `${p.name} = `; fillPalette(); } });
  }
  for (const c of CMDS) if (c.id !== 'palette' && (!nq || norm(c.label).includes(nq))) palItems.push({ label: c.label, d: c.keys || '', run: c.run });
  palOn = 0;
  drawPalette();
}
function drawPalette() {
  $('#pal-list').innerHTML = palItems.map((it, i) => `<li data-i="${i}" class="${i === palOn ? 'on' : ''}">${esc(it.label)}<span class="d">${esc(it.d)}</span></li>`).join('')
    || '<li style="color:var(--ink-3)">Nessun comando con questo nome.</li>';
  $('#pal-list').querySelector('li.on')?.scrollIntoView({ block: 'nearest' });
}
function palRun(i) {
  const it = palItems[i];
  if (!it) return;
  if (!it.keep) closePalette();
  it.run();
}
$('#pal-input').addEventListener('input', fillPalette);
$('#pal-input').addEventListener('keydown', ev => {
  ev.stopPropagation();
  if (ev.key === 'ArrowDown') { palOn = Math.min(palItems.length - 1, palOn + 1); drawPalette(); ev.preventDefault(); }
  else if (ev.key === 'ArrowUp') { palOn = Math.max(0, palOn - 1); drawPalette(); ev.preventDefault(); }
  else if (ev.key === 'Enter') palRun(palOn);
  else if (ev.key === 'Escape') closePalette();
});
$('#pal-list').addEventListener('click', ev => { const li = ev.target.closest('li[data-i]'); if (li) palRun(+li.dataset.i); });
$('#palette').addEventListener('click', ev => { if (ev.target.id === 'palette') closePalette(); });

// --------------------------------------------------------------- tastiera
document.addEventListener('keydown', ev => {
  if (SK && skKey(ev)) { ev.preventDefault(); return; }
  const inCampo = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName);
  const k = ev.key.toLowerCase();
  if (ev.ctrlKey) {
    const mappa = { z: ev.shiftKey ? 'redo' : 'undo', y: 'redo', s: ev.shiftKey ? 'saveas' : 'save', o: 'open', n: 'new', k: 'palette' };
    if (mappa[k] && !(inCampo && (k === 'z' || k === 'y'))) { ev.preventDefault(); runCmd(mappa[k]); }
    return;
  }
  if (!$('#home').hidden) {                       // sulla pagina iniziale contano solo Esc e i Ctrl
    if (ev.key === 'Escape' && $('#modal').hidden && !$('#home-close').hidden) hideHome();
    else if (ev.key === 'Escape') $('#modal').hidden = true;
    return;
  }
  if (ev.key === 'Escape' && ASM.tool) { asmTool(null); sel = null; paint(); return; }
  if (ev.key === 'Escape') {
    if (!$('#modal').hidden) { $('#modal').hidden = true; return; }
    if (linkFrom) { linkFrom = null; paintNodes(); return; }
    if (inCampo) { document.activeElement.blur(); return; }
    clearSelection(); return;
  }
  if (inCampo || ev.altKey || ev.metaKey) return;
  if (ev.key === 'Delete') { ev.preventDefault(); deleteSelected(); return; }
  const tasti = { f: 'fit', 0: 'view_iso', 7: 'view_top', 1: 'view_front', 3: 'view_right', q: 'toggle_dims', u: 'unfold' };
  if (tasti[k]) { ev.preventDefault(); runCmd(tasti[k]); }
});

// ===================================================================== modalità sketch (disegno libero)
// Vista dall'alto con griglia. Linea: clic sui punti, scrivi la lunghezza + Invio, clic sul primo punto
// per chiudere, Esc per finire. Rettangolo: due angoli. Cerchio: centro e raggio (o diametro scritto).
// Seleziona: clic su una linea o un cerchio, Canc per toglierlo. Le quote nascono da sole e si cambiano.
let SK = null;
let aggancioGriglia = true;            // F9: aggancio alla griglia sì/no (si ricorda tra uno sketch e l'altro)           // { sid, v (vista dal motore), tool, pts: [{id?, xy}], cursor: {xy, id, how}, sel: Set, buf }
const skGroup = new THREE.Group();
const skGrid = new THREE.Group();
const skRubber = new THREE.Group();
scene.add(skGroup, skGrid, skRubber);
const SK_LINE = new THREE.LineBasicMaterial({ color: 0x1F5FBF });
const SK_SEL = new THREE.LineBasicMaterial({ color: 0xE09A00 });
const SK_HOV = new THREE.LineBasicMaterial({ color: 0x4EA1FF });
const SK_RUB = new THREE.LineDashedMaterial({ color: 0x1F5FBF, dashSize: 6, gapSize: 4 });
const SK_GRID1 = new THREE.LineBasicMaterial({ color: 0xD3D8DE });
const SK_GRID2 = new THREE.LineBasicMaterial({ color: 0xB4BCC5 });
const TOOLS = { line: 'Linea', rect: 'Rettangolo', circle: 'Cerchio', slot: 'Asola', arc3: 'Arco', polygon: 'Poligono', select: 'Seleziona',
  dim: 'Quota', trim: 'Taglia', extend: 'Allunga', fillet: 'Raccordo', chamfer: 'Smusso' };
const SK_CUT_FILL = new THREE.MeshBasicMaterial({ color: 0xD92D20, side: THREE.DoubleSide, depthTest: false });   // il pezzo che il Taglia toglie
// una linea spessa px pixel (in WebGL le linee sono sempre da 1 pixel): una striscia nel piano dello sketch
function fatLine(pts, px, mat) {
  const a = skScreen([0, 0]), b = skScreen([100, 0]);
  const w = px / 2 / Math.max(1e-6, Math.hypot(b[0] - a[0], b[1] - a[1]) / 100);
  const pos = [], idx = [];
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i], q = pts[Math.min(i + 1, pts.length - 1)], o = pts[Math.max(i - 1, 0)];
    let dx = q[0] - o[0], dy = q[1] - o[1];
    const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    for (const sg of [1, -1]) { const v = skToWorld([p[0] - dy * w * sg, p[1] + dx * w * sg]); pos.push(v.x, v.y, v.z); }
    if (i) { const k = 2 * i; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  const m = new THREE.Mesh(g, mat);
  m.renderOrder = 20;
  return m;
}
const SK_CONSTR = new THREE.LineDashedMaterial({ color: 0x7D8790, dashSize: 8, gapSize: 5 });
const SK_TRACK = new THREE.LineDashedMaterial({ color: 0x2E9E5B, dashSize: 3, gapSize: 3 });       // puntamento
const SK_PTS = new THREE.PointsMaterial({ color: 0x1C2228, size: 6, sizeAttenuation: false });
// tema chiaro / scuro: i colori del disegno che devono staccare dallo sfondo
const COLORI_TEMA = {
  chiaro: [[SK_LINE, 0x1F5FBF], [SK_GRID1, 0xD3D8DE], [SK_GRID2, 0xB4BCC5], [SK_PTS, 0x1C2228], [DIM_MAT, 0x1F3A5F], [FLAT_EDGE, 0x2B3138]],
  scuro: [[SK_LINE, 0x5AA0FF], [SK_GRID1, 0x262C33], [SK_GRID2, 0x353D46], [SK_PTS, 0xE1E6EB], [DIM_MAT, 0x6FA8E8], [FLAT_EDGE, 0xC9D2DB]],
};
function applyTheme(scuro) {
  document.body.classList.toggle('dark', scuro);
  for (const [m, c] of COLORI_TEMA[scuro ? 'scuro' : 'chiaro']) m.color.setHex(c);
  try { localStorage.setItem('steelcad.tema', scuro ? 'scuro' : 'chiaro'); } catch { /* niente memoria: va bene lo stesso */ }
  ridisegna();
}
const SK_REF = new THREE.LineBasicMaterial({ color: 0xC2410C });        // i bordi del pezzo
const SK_XRAY = new THREE.LineDashedMaterial({ color: 0x38BDF8, dashSize: 2, gapSize: 1.5 });   // visto attraverso
const SK_CONSTR_SEL = new THREE.LineDashedMaterial({ color: 0xE09A00, dashSize: 8, gapSize: 5 });
const AIUTI = {
  line: 'Clic sui punti · scrivi la lunghezza + Invio, oppure lunghezza<angolo (es. 100<30) · clic sul primo punto per chiudere · Esc finisce',
  rect: 'Clic su un angolo, poi sull’angolo opposto (o scrivi la misura + Invio)',
  circle: 'Clic sul centro, poi sul bordo (o scrivi il diametro + Invio)',
  slot: 'Asola: clic sul primo centro, clic sul secondo, poi muovi il mouse per la larghezza e clicca (o scrivi la larghezza + Invio)',
  arc3: 'Arco: clic sul punto di partenza, su un punto dove passa, poi sul punto di arrivo',
  polygon: 'Poligono: il numero di lati nella casella in alto · clic sul centro, poi su un vertice',
  fillet: 'Raccordo: clic sullo spigolo, oppure sulle due linee una dopo l’altra (come AutoCAD) · poi il raggio nella casella + Invio',
  chamfer: 'Smusso: clic sullo spigolo, oppure sulle due linee una dopo l’altra · poi la misura nella casella + Invio',
  select: 'Clic su linee e cerchi (Maiusc per aggiungere, doppio clic = tutto il contorno, Ctrl+A tutto) · poi i comandi',
  dim: 'Clic su una linea (lunghezza) o un cerchio (diametro) · oppure su due punti, o un punto e una linea (distanza)',
  trim: 'Taglia: passa sul pezzo da togliere (diventa rosso) e clicca · si taglia fino alle linee più vicine · Esc finisce',
  extend: 'Allunga: passa vicino all’estremità di una linea (l’allungamento tratteggiato) e clicca · Esc finisce',
};

const v3 = a => new THREE.Vector3(...a);
function skToWorld(xy) {
  const v = SK.v, o = v3(v.origin), x = v3(v.x_dir), y = v3(v.y_dir);
  return o.addScaledVector(x, xy[0]).addScaledVector(y, xy[1]);
}
function skToLocal(p) {
  const v = SK.v, d = p.clone().sub(v3(v.origin));
  return [d.dot(v3(v.x_dir)), d.dot(v3(v.y_dir))];
}
function skScreen(xy) {
  const p = skToWorld(xy).project(camera);
  return [(p.x + 1) / 2 * view.clientWidth, (1 - p.y) / 2 * view.clientHeight];
}
function skPick(ev) {
  const r = canvas.getBoundingClientRect();
  const m = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(m, camera);
  const n = v3(SK.v.z_dir), pl = new THREE.Plane(n, -n.dot(v3(SK.v.origin)));
  const hit = new THREE.Vector3();
  return ray.ray.intersectPlane(pl, hit) ? skToLocal(hit) : null;
}
function skStep() {          // passo della griglia: circa 12 px sullo schermo, arrotondato a 1-2-5
  const a = skScreen([0, 0]), b = skScreen([100, 0]);
  const pxPerMm = Math.max(1e-6, Math.hypot(b[0] - a[0], b[1] - a[1]) / 100);
  const want = 12 / pxPerMm;
  for (const s of [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]) if (s >= want) return s;
  return 1000;
}

async function enterSketch(sid) {
  const r = await call('sketch_view', sid);
  if (!r.ok) { toast(r.message, 'err'); return; }
  SK = { sid, v: r.sketch, tool: 'line', pts: [], cursor: null, sel: new Set(), buf: '', constr: false, pick: null, dimPick: [], ghost: false, grid: aggancioGriglia };
  if (flatView) flatView = false;
  clearSelection();
  controls.enableRotate = false;
  // su una faccia: quella faccia è il piano di lavoro e il resto sparisce; sullo sviluppo: si vede lo sviluppo
  const faccia = SK.v.on_face ? buildWorkFace(SK.v.on_face) : null;
  const sviluppo = SK.v.on_flat && buildFlat();
  applyLook();
  $('#sk-panel').hidden = false;
  $('#props-panel').hidden = true;
  document.body.classList.add('sketching');
  $('#rtab-sketch').hidden = false; showRibbon('sketch');
  resize();                                   // la vista è appena cresciuta (pannello in basso chiuso)
  $('#sk-foot').hidden = false;
  drawSketch();
  const pts = SK.v.points.filter(p => p.id !== 'O' || !(faccia || sviluppo)).map(p => p.xyz);
  const box = new THREE.Box3();
  if (pts.length > 1) pts.forEach(p => box.expandByPoint(v3(p)));
  else if (!faccia && !sviluppo) { box.expandByPoint(skToWorld([-50, -50])); box.expandByPoint(skToWorld([550, 350])); }
  if (faccia) box.union(faccia);
  else if (sviluppo) box.union(flatBox());
  else if (objs.size) box.union(new THREE.Box3().setFromObject(model));
  const zd = v3(SK.v.z_dir);
  if (Math.abs(zd.z) > 0.99) zd.add(new THREE.Vector3(0, -0.0001 * Math.sign(zd.z), 0));   // guardando giù/su: il nord resta in alto
  fitBox(box, zd);
  setTool(SK.v.on_face || SK.v.on_flat ? 'rect' : 'line');
  buildDims();
}
function exitSketch() {
  if (!SK) return;
  const era = SK;
  SK = null;
  // uno sketch su faccia/sviluppo lasciato vuoto non resta nell'albero
  if (era.v.on_face || era.v.on_flat) inCoda(async () => apply(await call('sketch_close', era.sid)));
  controls.enableRotate = true;
  svuota(workGroup);
  applyLook();
  $('#sk-panel').hidden = true;
  $('#props-panel').hidden = false;
  document.body.classList.remove('sketching');
  $('#rtab-sketch').hidden = true; showRibbon(schedaPrima);
  resize();
  $('#sk-foot').hidden = true;
  $('#sk-cmd').hidden = true;
  $('#sk-tip').style.display = 'none';
  $('#sk-snap').style.display = 'none';
  for (const g of [skGroup, skGrid, skRubber]) { g.traverse(x => x.geometry?.dispose()); g.clear(); }
  goTo(VISTE.view_iso);
  renderTree();
  buildDims();
}
function fitSketch() {
  const pts = SK.v.points.filter(p => p.id !== 'O').map(p => v3(p.xyz));
  const box = new THREE.Box3();
  pts.forEach(p => box.expandByPoint(p));
  SK.v.circles.forEach(c => { box.expandByPoint(v3(c.center).addScalar(c.r)); box.expandByPoint(v3(c.center).addScalar(-c.r)); });
  // sullo sviluppo o su una faccia si inquadra sempre anche quella: si disegna sopra di lei
  if (SK.v.on_flat && flatGroup.children.length) box.union(flatBox());
  else if (SK.v.on_face && workGroup.children.length) box.union(new THREE.Box3().setFromObject(workGroup));
  else if (!box.isEmpty()) box.expandByPoint(v3(SK.v.origin));
  if (box.isEmpty()) return;
  const zd = v3(SK.v.z_dir);
  if (Math.abs(zd.z) > 0.99) zd.add(new THREE.Vector3(0, -0.0001 * Math.sign(zd.z), 0));
  fitBox(box, zd);
}
// Vedi attraverso: le parti dietro e davanti alla faccia, proiettate (ci si aggancia); il pezzo si vede in trasparenza
function toggleXray() {
  if (!SK || !SK.v.on_face) return;
  const on = !SK.v.xray, sid = SK.sid;
  inCoda(async () => {
    if (!(await apply(await call('sketch_xray', sid, on)))) return;
    if (SK && SK.sid === sid) { SK.ghost = on; applyLook(); }
    toast(on ? 'Vedi attraverso: bordi e fori delle parti dietro e davanti, in azzurro tratteggiato. Ci si aggancia.' : 'Vedi attraverso spento.');
  });
}
async function refreshSketch() {
  if (!SK) return;
  const r = await call('sketch_view', SK.sid);
  if (!r.ok) { exitSketch(); return; }
  const eraVuoto = SK.v.points.length <= 1 && !SK.v.circles.length;
  SK.v = r.sketch;
  if (eraVuoto && (SK.v.points.length > 1 || SK.v.circles.length)) fitSketch();   // il primo disegno si inquadra da solo
  for (const id of [...SK.sel]) if (!SK.v.lines.some(l => l.id === id) && !SK.v.circles.some(c => c.id === id)) SK.sel.delete(id);
  drawSketch();
}
function setTool(t) {
  if (!SK) return;
  SK.tool = t; SK.pts = []; SK.buf = ''; SK.pick = null; SK.dimPick = []; SK.angs = {}; SK.cutPrev = null; SK.cutAt = null; SK.cutMsg = null;
  document.querySelectorAll('#sk-panel [data-tool], #ribbon [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t));
  $('#sk-help').textContent = AIUTI[t] + ' · destro sposta, rotella ingrandisce';
  drawRubber();
}
function setHelp(t) { $('#sk-help').textContent = t; }

function drawSketch() {
  for (const g of [skGroup, skGrid]) { g.traverse(x => x.geometry?.dispose()); g.clear(); }
  const v = SK.v;
  // griglia: 10 mm chiara, 100 mm più scura, assi dall'origine; grande quanto serve al disegno
  let ext = 300;
  for (const p of v.points) ext = Math.max(ext, Math.abs(p.xy[0]), Math.abs(p.xy[1]));
  for (const c of v.circles) ext = Math.max(ext, Math.abs(c.xc[0]) + c.r, Math.abs(c.xc[1]) + c.r);
  const lim = Math.min(5000, Math.ceil(ext * 1.6 / 100) * 100), segs1 = [], segs2 = [];
  for (let k = -lim; k <= lim; k += 10) {
    const arr = k % 100 === 0 ? segs2 : segs1;
    arr.push(skToWorld([k, -lim]), skToWorld([k, lim]), skToWorld([-lim, k]), skToWorld([lim, k]));
  }
  skGrid.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(segs1), SK_GRID1));
  skGrid.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(segs2), SK_GRID2));
  skGrid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([skToWorld([0, 0]), skToWorld([lim, 0])]), new THREE.LineBasicMaterial({ color: 0xC0392B })));
  skGrid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([skToWorld([0, 0]), skToWorld([0, lim])]), new THREE.LineBasicMaterial({ color: 0x2E8B57 })));
  skGrid.position.copy(v3(v.z_dir).multiplyScalar(-0.05));
  for (const l of v.lines) {
    const mat = SK.sel.has(l.id) ? (l.construction && !l.ref ? SK_CONSTR_SEL : SK_SEL) : SK.hover === l.id ? SK_HOV
      : l.xray ? SK_XRAY : l.ref ? SK_REF : l.construction ? SK_CONSTR : SK_LINE;
    const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints([v3(l.pa), v3(l.pb)]), mat);
    if ((l.construction && !l.ref) || l.xray) ln.computeLineDistances();
    skGroup.add(ln);
  }
  for (const c of v.circles) {
    const pts = [];
    const ctr = v3(c.center), x = v3(v.x_dir), y = v3(v.y_dir);
    for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; pts.push(ctr.clone().addScaledVector(x, c.r * Math.cos(a)).addScaledVector(y, c.r * Math.sin(a))); }
    const mat = SK.sel.has(c.id) ? SK_SEL : SK.hover === c.id ? SK_HOV : c.xray ? SK_XRAY : c.ref ? SK_REF : c.construction ? SK_CONSTR : SK_LINE;
    const cl = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat);
    if ((c.construction && !c.ref) || c.xray) cl.computeLineDistances();
    skGroup.add(cl);
    const fuori = c.hole?.tipo === 'filettato' ? ({ M3: 3, M4: 4, M5: 5, M6: 6, M8: 8, M10: 10, M12: 12, M16: 16 }[c.hole.M] || 0) / 2
      : c.hole?.tipo === 'svasato' ? Number(c.hole.D) / 2 : 0;
    if (fuori > c.r) {                                // filettatura o svasatura: un cerchio tratteggiato attorno
      const p2 = [];
      for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; p2.push(ctr.clone().addScaledVector(x, fuori * Math.cos(a)).addScaledVector(y, fuori * Math.sin(a))); }
      const ex = new THREE.Line(new THREE.BufferGeometry().setFromPoints(p2), SK_CONSTR);
      ex.computeLineDistances();
      skGroup.add(ex);
    }
  }
  for (const a of v.arcs || []) {
    const pts = [], ctr = v3(a.center), x = v3(v.x_dir), y = v3(v.y_dir);
    for (let i = 0; i <= 64; i++) { const t = a.a0 + (a.a1 - a.a0) * i / 64; pts.push(ctr.clone().addScaledVector(x, a.r * Math.cos(t)).addScaledVector(y, a.r * Math.sin(t))); }
    const mat = SK.sel.has(a.id) ? SK_SEL : SK.hover === a.id ? SK_HOV : a.xray ? SK_XRAY : a.ref ? SK_REF : a.construction ? SK_CONSTR : SK_LINE;
    const al = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat);
    if ((a.construction && !a.ref) || a.xray) al.computeLineDistances();
    skGroup.add(al);
  }
  const pg = new THREE.BufferGeometry().setFromPoints(v.points.map(p => v3(p.xyz)));
  skGroup.add(new THREE.Points(pg, SK_PTS));
  skGroup.position.copy(v3(v.z_dir).multiplyScalar(0.05));
  // in alto nel pannello: dove sei e cosa fare adesso, in parole semplici
  const libero = !v.used_by.length, suPezzo = !!(v.on_face || v.on_flat), pronto = v.ok && v.profiles > 0;
  let cls = 'todo', testo;
  if (!libero) { cls = 'ok'; testo = `Usato da ${v.used_by.join(', ')}: cambia linee o quote e il pezzo si aggiorna da solo.`; }
  else if (!v.drawn) testo = suPezzo
    ? 'Vuoto. Scegli Rettangolo o Cerchio e disegna sulla faccia. Le misure partono dall’angolo in basso a sinistra (0;0); i bordi del pezzo sono in arancio: ci si aggancia e ci si fa l’offset.'
    : 'Vuoto. Scegli Linea o Rettangolo e disegna il contorno.';
  else if (pronto) { cls = 'ok'; testo = `✓ ${v.profiles === 1 ? '1 contorno chiuso' : v.profiles + ' contorni chiusi'}: ${suPezzo ? 'premi «Taglia attraverso»' : 'crea la lamiera o la piastra'}. Per cambiare una misura, clicca la quota.`; }
  else if (v.on_sheet && !v.on_flat) { cls = 'todo'; testo = 'Spezzata aperta, da bordo a bordo della faccia (arancio): «Taglia attraverso» la chiude lungo il bordo e toglie il pezzo più piccolo; «Aggiungi materiale» se è disegnata fuori, attaccata al bordo. «Lamiera a contorno»: se parte dallo spigolo di un bordo libero diventa lamiera piegata.'; }
  else { cls = 'bad'; testo = (v.status || '').startsWith('Lo sketch') ? 'Nessun contorno chiuso: chiudi il disegno tornando sul primo punto.' : v.status; }
  $('#sk-where').textContent = 'Stai disegnando ' + (v.where || '');
  $('#sk-status').className = 'sk-state ' + cls;
  $('#sk-status').textContent = testo;
  $('#sk-selbar').hidden = !SK.sel.size;
  $('#sk-nsel').textContent = SK.sel.size === 1 ? '1 elemento' : `${SK.sel.size} elementi`;
  $('#sk-constr').classList.toggle('on', SK.constr);
  $('#rb-constr').classList.toggle('on', SK.constr);
  $('#sk-grid').classList.toggle('on', !!SK.grid);
  $('#sk-finish-box').hidden = !libero;
  for (const q of ['#sk-xray', '#rb-xray']) {
    $(q).hidden = !(SK && SK.v.on_face);
    $(q).classList.toggle('on', !!SK?.v?.xray);
  }
  $('#sk-leg-xray').hidden = !SK?.v?.xray;
  $('#sk-make').hidden = suPezzo;
  $('#sk-face').hidden = !suPezzo;
  $('#sk-boss').hidden = !!v.on_sheet;
  document.querySelectorAll('#sk-finish-box button').forEach(b => { b.disabled = !pronto; });
  $('#sk-face [data-make="cut"]').disabled = !(pronto || (suPezzo && v.drawn));
  $('#sk-make [data-make="structure"]').disabled = !v.lines.some(l => !l.construction);   // bastano linee aperte   // da bordo a bordo: la chiudo io
  for (const q of ['#sk-louver', '#sk-dimple']) { $(q).hidden = !(v.on_sheet && v.on_face); $(q).disabled = !v.drawn; }
  $('#sk-fold').hidden = !(v.on_flat || (v.on_sheet && /\/(sopra|sotto)$/.test(v.on_face || '')));
  $('#sk-fold').disabled = !v.drawn;
  $('#sk-contour').hidden = !(v.on_sheet && v.on_face);
  $('#sk-tab').hidden = !(v.on_sheet && v.on_face);
  $('#sk-tab').disabled = !v.drawn;
  $('#sk-contour').disabled = !v.drawn || !v.lines.some(l => !l.construction);
  $('.sk-legend .l-ref').parentElement.hidden = !suPezzo;
  ridisegna();
}

// cosa c'è sotto il mouse, con gli agganci: punto esistente, orizzontale/verticale, griglia
// Agganci come in AutoCAD: tra tutti i candidati vicini al mouse vince il più vicino (con un piccolo
// vantaggio per estremi, centri e incroci). Ogni aggancio ha il suo simbolo sul punto. Se non c'è niente:
// puntamento (allineato in orizzontale/verticale a un punto del disegno), poi orizzontale/verticale
// rispetto al punto prima, poi la griglia (F9 la spegne).
const AP = 11;                                     // raggio di presa, in pixel
const VANTAGGIO = { punto: 4, origine: 4, centro: 4, incrocio: 3, 'metà': 2, quadrante: 2, tangente: 1.5, perpendicolare: 1.5, sul: -3 };
function skCursor(ev) {
  const xy = skPick(ev);
  if (!xy) return null;
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const cand = [];
  const prendi = (q, tipo, extra = {}) => {
    const sq = skScreen(q), d = Math.hypot(sq[0] - mx, sq[1] - my);
    if (d < AP) cand.push({ xy: q, tipo, d, ...extra });
  };
  const centri = new Set([...SK.v.circles, ...(SK.v.arcs || [])].map(c => c.center_id));
  for (const p of SK.v.points) prendi(p.xy, p.id === 'O' ? 'origine' : centri.has(p.id) ? 'centro' : 'punto', { id: p.id });
  SK.pts.forEach((p, i) => { if (!p.id) prendi(p.xy, 'punto', { id: null, first: i === 0 }); });
  const L = SK.v.lines, tondi = roundsOf();
  for (const l of L) prendi([(l.xa[0] + l.xb[0]) / 2, (l.xa[1] + l.xb[1]) / 2], 'metà', { ref: { mid: l.id } });
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
    const q = segX(L[i].xa, L[i].xb, L[j].xa, L[j].xb);
    if (q) prendi(q, 'incrocio', { ref: { cross: [L[i].id, L[j].id], xy: q } });
  }
  for (const c of tondi) for (const l of L) for (const q of segCircle(l.xa, l.xb, c)) prendi(q, 'incrocio', { ref: { cross: [l.id, c.id], xy: q } });
  for (let i = 0; i < tondi.length; i++) for (let j = i + 1; j < tondi.length; j++)
    for (const q of circleCircle(tondi[i], tondi[j])) prendi(q, 'incrocio', { ref: { cross: [tondi[i].id, tondi[j].id], xy: q } });
  for (const c of tondi) for (let k = 0; k < 4; k++) {
    const an = k * Math.PI / 2;
    if (!angIn(an, c)) continue;
    const q = [c.xc[0] + c.r * Math.cos(an), c.xc[1] + c.r * Math.sin(an)];
    prendi(q, 'quadrante', { ref: { quad: c.id, k, xy: q }, nota: ['a destra', 'in cima', 'a sinistra', 'in fondo'][k] + ' del cerchio' });
  }
  const last = SK.pts[SK.pts.length - 1];
  if (last && SK.tool === 'line') {
    const P = last.xy;
    for (const c of tondi) {                         // tangente dal punto prima al cerchio
      const dx = P[0] - c.xc[0], dy = P[1] - c.xc[1], d = Math.hypot(dx, dy);
      if (d <= c.r + 1e-9) continue;
      const th = Math.atan2(dy, dx), al = Math.acos(c.r / d);
      for (const t of [th + al, th - al]) {
        if (!angIn(t, c)) continue;
        const q = [c.xc[0] + c.r * Math.cos(t), c.xc[1] + c.r * Math.sin(t)];
        prendi(q, 'tangente', { ref: { tan: c.id, xy: q } });
      }
    }
    for (const l of L) {                             // perpendicolare dal punto prima alla linea
      const ux = l.xb[0] - l.xa[0], uy = l.xb[1] - l.xa[1], LL = ux * ux + uy * uy || 1;
      const t = ((P[0] - l.xa[0]) * ux + (P[1] - l.xa[1]) * uy) / LL;
      if (t < -1e-9 || t > 1 + 1e-9) continue;
      const q = [l.xa[0] + ux * t, l.xa[1] + uy * t];
      if (Math.hypot(q[0] - P[0], q[1] - P[1]) > 1e-6) prendi(q, 'perpendicolare', { ref: { perp: l.id, xy: q } });
    }
  }
  for (const l of L) {                               // sulla linea (anche normali, non solo le guide)
    const ux = l.xb[0] - l.xa[0], uy = l.xb[1] - l.xa[1], LL = ux * ux + uy * uy || 1;
    const t = Math.max(0, Math.min(1, ((xy[0] - l.xa[0]) * ux + (xy[1] - l.xa[1]) * uy) / LL));
    const q = [l.xa[0] + ux * t, l.xa[1] + uy * t];
    prendi(q, 'sul', { ref: { on: l.id, xy: q }, nota: l.construction && !l.ref ? 'sulla guida' : 'sulla linea' });
  }
  for (const c of tondi) {
    const d = Math.hypot(xy[0] - c.xc[0], xy[1] - c.xc[1]) || 1;
    const q = [c.xc[0] + (xy[0] - c.xc[0]) / d * c.r, c.xc[1] + (xy[1] - c.xc[1]) / d * c.r];
    if (angIn(Math.atan2(q[1] - c.xc[1], q[0] - c.xc[0]), c)) prendi(q, 'sul', { ref: { on: c.id, xy: q }, nota: 'sul cerchio' });
  }
  if (cand.length) {
    const b = cand.reduce((m, c) => (c.d - (VANTAGGIO[c.tipo] || 0) < m.d - (VANTAGGIO[m.tipo] || 0) ? c : m));
    return { xy: b.xy, id: b.id ?? null, ref: b.ref, first: b.first, tipo: b.tipo, how: b.nota || b.tipo };
  }
  // puntamento: allineato a un punto del disegno (stessa X o stessa Y, a meno di 7 pixel)
  const sm = [mx, my];
  let tx = null, ty = null;
  for (const p of SK.v.points) {
    const sp = skScreen(p.xy);
    if (Math.abs(sp[0] - sm[0]) < 7 && (!tx || Math.abs(sp[0] - sm[0]) < tx.d)) tx = { p, d: Math.abs(sp[0] - sm[0]) };
    if (Math.abs(sp[1] - sm[1]) < 7 && (!ty || Math.abs(sp[1] - sm[1]) < ty.d)) ty = { p, d: Math.abs(sp[1] - sm[1]) };
  }
  // orizzontale/verticale rispetto al punto prima: a meno di 7 pixel dalla sua orizzontale/verticale
  const hvLast = last && (SK.tool === 'line' || (SK.tool === 'slot' && SK.pts.length === 1));
  const st = skStep();
  let q = SK.grid ? [Math.round(xy[0] / st) * st, Math.round(xy[1] / st) * st] : [xy[0], xy[1]];
  let how = SK.grid ? 'griglia' : '', tipo = null, ref = null, guide = [];
  if (hvLast) {
    const sl = skScreen(last.xy);
    if (Math.abs(sl[1] - my) < 7) { q = [q[0], last.xy[1]]; how = 'orizzontale'; tipo = 'hv'; ty = null; guide.push([last.xy, null]); }
    else if (Math.abs(sl[0] - mx) < 7) { q = [last.xy[0], q[1]]; how = 'verticale'; tipo = 'hv'; tx = null; guide.push([last.xy, null]); }
  }
  if (tx || ty) {
    if (tx) q[0] = tx.p.xy[0];
    if (ty) q[1] = ty.p.xy[1];
    tipo = 'punta';
    const da = pt => (pt.id === 'O' ? 'dall’origine' : centri.has(pt.id) ? 'dal centro' : 'dal punto');
    how = [tx && `in verticale ${da(tx.p)}`, ty && `in orizzontale ${da(ty.p)}`].filter(Boolean).join(' e ');
    ref = { track: { x: tx?.p.id || null, y: ty?.p.id || null }, xy: q };
    if (tx) guide.push([tx.p.xy, null]);
    if (ty) guide.push([ty.p.xy, null]);
  }
  guide = guide.map(([da]) => [da, q]);
  return { xy: q, id: null, ref, how, tipo, guide };
}
function circleCircle(a, b) {             // incroci tra due cerchi/archi
  const d = Math.hypot(b.xc[0] - a.xc[0], b.xc[1] - a.xc[1]);
  if (d < 1e-9 || d > a.r + b.r + 1e-9 || d < Math.abs(a.r - b.r) - 1e-9) return [];
  const aa = (a.r * a.r - b.r * b.r + d * d) / (2 * d), h = Math.sqrt(Math.max(0, a.r * a.r - aa * aa));
  const mx = a.xc[0] + aa * (b.xc[0] - a.xc[0]) / d, my = a.xc[1] + aa * (b.xc[1] - a.xc[1]) / d;
  const out = [];
  for (const sg of (h > 1e-9 ? [1, -1] : [1])) {
    const q = [mx + sg * h * (b.xc[1] - a.xc[1]) / d, my - sg * h * (b.xc[0] - a.xc[0]) / d];
    if (angIn(Math.atan2(q[1] - a.xc[1], q[0] - a.xc[0]), a) && angIn(Math.atan2(q[1] - b.xc[1], q[0] - b.xc[0]), b)) out.push(q);
  }
  return out;
}
// il simbolo dell'aggancio sul punto (come AutoCAD) e le linee di puntamento
const SIMBOLI = {
  punto: '<rect x="2" y="2" width="12" height="12"/>', origine: '<rect x="2" y="2" width="12" height="12"/><circle cx="8" cy="8" r="1.5"/>',
  centro: '<circle cx="8" cy="8" r="6"/>', 'metà': '<path d="M8 2 L14 14 L2 14 Z"/>', incrocio: '<path d="M2 2 L14 14 M14 2 L2 14"/>',
  quadrante: '<path d="M8 1 L15 8 L8 15 L1 8 Z"/>', tangente: '<circle cx="8" cy="9" r="5"/><path d="M1 3 H15"/>',
  perpendicolare: '<path d="M2 14 H14 M8 14 V2"/>', sul: '<path d="M3 3 H13 L3 13 H13 Z"/>', punta: '<path d="M8 3 V13 M3 8 H13"/>', hv: '<path d="M8 3 V13 M3 8 H13"/>',
};
function drawSnap(c) {
  const el = $('#sk-snap');
  if (!c || !c.tipo || !SIMBOLI[c.tipo]) { el.style.display = 'none'; return; }
  const sp = skScreen(c.xy);
  el.innerHTML = `<svg viewBox="0 0 16 16">${SIMBOLI[c.tipo]}</svg>`;
  el.style.left = sp[0] + 'px'; el.style.top = sp[1] + 'px'; el.style.display = 'block';
}

function drawRubber() {
  skRubber.traverse(x => x.geometry?.dispose());
  skRubber.clear();
  if (SK) updateCmd();
  const tip = $('#sk-tip');
  if (SK?.pick?.what === 'corner') { drawSnap({ tipo: 'punto', xy: SK.pick.xy }); updateCmd(); ridisegna(); return; }
  if (SK && (SK.tool === 'trim' || SK.tool === 'extend') && !SK.pick) {
    tip.style.display = 'none';
    const pv = SK.cutPrev;
    if (pv?.tool === 'trim') skRubber.add(fatLine(pv.remove, 5, SK_CUT_FILL)); else if (pv?.tool === 'extend') {
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pv.add.map(skToWorld)), SK_RUB);
      l.computeLineDistances(); skRubber.add(l);
    }
    if (SK.cutMsg && SK.cutAt) setHelp(SK.cutMsg); else setHelp(AIUTI[SK.tool] + ' · destro sposta, rotella ingrandisce');
    ridisegna();
    return;
  }
  if (SK?.pick?.what === 'offset') {
    tip.style.display = 'none';
    const pv = SK.pick.prev;
    if (pv) {
      const add = pts => { const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(skToWorld)), SK_RUB); l.computeLineDistances(); skRubber.add(l); };
      pv.lines.forEach(seg => add(seg));
      pv.circles.forEach(([cc, rr]) => { const p = []; for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; p.push([cc[0] + rr * Math.cos(a), cc[1] + rr * Math.sin(a)]); } add(p); });
    }
    ridisegna();
    return;
  }
  if (!SK || !SK.cursor) { tip.style.display = 'none'; drawSnap(null); ridisegna(); return; }
  const c = SK.cursor.xy, last = SK.pts[SK.pts.length - 1];
  const add = (pts, mat = SK_RUB) => {
    const g = new THREE.BufferGeometry().setFromPoints(pts.map(skToWorld));
    const l = new THREE.Line(g, mat); l.computeLineDistances(); skRubber.add(l);
  };
  drawSnap(SK.cursor);
  for (const [da, a] of SK.cursor.guide || []) add([da, a], SK_TRACK);
  let testo = '';
  if (SK.pick && SK.pick.base) {
    add([SK.pick.base.xy, c]);
    testo = `${num(c[0] - SK.pick.base.xy[0], 2)} ; ${num(c[1] - SK.pick.base.xy[1], 2)}`;
  } else if (SK.pick) {
    testo = '';
  } else if (SK.tool === 'line') {
    if (SK.pts.length > 1) add(SK.pts.map(p => p.xy));
    if (last) {
      add([last.xy, c]);
      const ang = Math.atan2(c[1] - last.xy[1], c[0] - last.xy[0]) * 180 / Math.PI;
      testo = `${num(Math.hypot(c[0] - last.xy[0], c[1] - last.xy[1]), 2)} mm < ${num(ang, 1)}°`;
    }
  } else if (SK.tool === 'rect' && last) {
    add([last.xy, [c[0], last.xy[1]], c, [last.xy[0], c[1]], last.xy]);
    testo = `${num(Math.abs(c[0] - last.xy[0]), 2)} × ${num(Math.abs(c[1] - last.xy[1]), 2)}`;
  } else if (SK.tool === 'arc3' && SK.pts.length === 1) {
    add([last.xy, c]);
  } else if (SK.tool === 'arc3' && SK.pts.length === 2) {
    const pts = arcThrough(SK.pts[0].xy, SK.pts[1].xy, c);
    add(pts); testo = pts.r ? `R ${num(pts.r, 2)}` : '';
  } else if (SK.tool === 'polygon' && last) {
    const n = SK.polyN || 6, r = Math.hypot(c[0] - last.xy[0], c[1] - last.xy[1]), a0 = Math.atan2(c[1] - last.xy[1], c[0] - last.xy[0]), pts = [];
    for (let i = 0; i <= n; i++) pts.push([last.xy[0] + r * Math.cos(a0 + 2 * Math.PI * i / n), last.xy[1] + r * Math.sin(a0 + 2 * Math.PI * i / n)]);
    add(pts); testo = `${n} lati · Ø ${num(2 * r, 2)}`;
  } else if (SK.tool === 'slot' && SK.pts.length === 1) {
    add([last.xy, c]); testo = `interasse ${num(Math.hypot(c[0] - last.xy[0], c[1] - last.xy[1]), 2)} mm`;
  } else if (SK.tool === 'slot' && SK.pts.length === 2) {
    const [a, b] = SK.pts.map(p => p.xy), r = slotR(c);
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), pts = [];
    for (let i = 0; i <= 24; i++) { const t = ang + Math.PI / 2 + Math.PI * i / 24; pts.push([a[0] + r * Math.cos(t), a[1] + r * Math.sin(t)]); }
    for (let i = 0; i <= 24; i++) { const t = ang - Math.PI / 2 + Math.PI * i / 24; pts.push([b[0] + r * Math.cos(t), b[1] + r * Math.sin(t)]); }
    pts.push(pts[0]); add(pts); testo = `larghezza ${num(2 * r, 2)} mm`;
  } else if (SK.tool === 'circle' && last) {
    const r = Math.hypot(c[0] - last.xy[0], c[1] - last.xy[1]), pts = [];
    for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; pts.push([last.xy[0] + r * Math.cos(a), last.xy[1] + r * Math.sin(a)]); }
    add(pts); testo = `Ø ${num(2 * r, 2)}`;
  }
  const s = skScreen(c);
  const aggancio = SK.cursor.how && SK.cursor.how !== 'griglia' ? ` · ${SK.cursor.how}` : '';
  const scritto = SK.buf ? `<b>${esc(SK.buf)}</b>_ ` : '';
  tip.innerHTML = `${scritto}${esc(testo || `${num(c[0], 2)} ; ${num(c[1], 2)}`)}${esc(aggancio)}`;
  tip.style.left = (s[0] + 14) + 'px'; tip.style.top = (s[1] + 14) + 'px'; tip.style.display = 'block';
  ridisegna();
}

function skHit(ev) {          // linea o cerchio vicino al mouse (per selezionare)
  const r = canvas.getBoundingClientRect(), m = [ev.clientX - r.left, ev.clientY - r.top];
  let best = null;
  const segDist = (p, a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L));
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  };
  const proj = p => { const q = v3(p).project(camera); return [(q.x + 1) / 2 * view.clientWidth, (1 - q.y) / 2 * view.clientHeight]; };
  for (const l of SK.v.lines) { const d = segDist(m, proj(l.pa), proj(l.pb)); if (d < 7 && (!best || d < best.d)) best = { id: l.id, d }; }
  for (const c of SK.v.circles) {
    const ctr = proj(c.center), e = proj(skToWorld([...skToLocal(v3(c.center))].map((v, i) => i === 0 ? v + c.r : v)));
    const d = Math.abs(Math.hypot(m[0] - ctr[0], m[1] - ctr[1]) - Math.hypot(e[0] - ctr[0], e[1] - ctr[1]));
    if (d < 7 && (!best || d < best.d)) best = { id: c.id, d };
  }
  const xy = skPick(ev);
  for (const a of SK.v.arcs || []) {            // vicino all'arco e dentro il suo angolo
    if (!xy) break;
    const ctr = proj(a.center), e = proj(skToWorld([a.xc[0] + a.r, a.xc[1]]));
    const d = Math.abs(Math.hypot(m[0] - ctr[0], m[1] - ctr[1]) - Math.hypot(e[0] - ctr[0], e[1] - ctr[1]));
    let t = Math.atan2(xy[1] - a.xc[1], xy[0] - a.xc[0]);
    while (t < a.a0) t += 2 * Math.PI;
    if (d < 7 && t <= a.a1 + 1e-6 && (!best || d < best.d)) best = { id: a.id, d };
  }
  return best?.id ?? null;
}

function skMove(ev) {
  if (ev.buttons) return;
  if (SK.pick?.what === 'offset') {
    if (SK.pick.stage === 'obj') { const h = skHit(ev); if (h !== SK.hover) { SK.hover = h; drawSketch(); } }
    if (SK.pick.stage === 'side') { SK.pick.mouse = skPick(ev); offPreview(); }
    return;
  }
  if (SK.pick?.what === 'axis' || (SK.tool === 'dim' && !SK.dimPick.length)) {
    const h = skHit(ev);
    if (h !== SK.hover) { SK.hover = h; drawSketch(); }
  }
  if (SK.tool === 'select') {
    const h = skHit(ev);
    if (h !== SK.hover) { SK.hover = h; drawSketch(); }
    SK.cursor = null; drawRubber();
    return;
  }
  if ((SK.tool === 'fillet' || SK.tool === 'chamfer') && (!SK.pick || SK.pick.what === 'corner2')) {
    const p = SK.pick ? null : cornerAt(ev);
    SK.cursor = p ? { xy: p.xy, id: p.id, tipo: 'punto', how: 'spigolo' } : null;
    const h = p ? null : skHit(ev);
    const hl = h && SK.v.lines.some(l => l.id === h) ? h : null;
    if (hl !== SK.hover) { SK.hover = hl; drawSketch(); }
    drawRubber(); return;
  }
  if (SK.tool === 'trim' || SK.tool === 'extend') {
    const h = skHit(ev);
    if (h !== SK.hover) { SK.hover = h; drawSketch(); }
    SK.cutAt = h ? { id: h, xy: skPick(ev) } : null;
    if (!h) { SK.cutPrev = null; drawRubber(); } else cutPreview();
    return;
  }
  SK.cursor = skCursor(ev);
  drawRubber();
}

const ptArg = p => p.id || p.ref || p.xy;
// cerchi e archi come { id, xc, r, a0, a1 } (il cerchio intero va da 0 a 2π)
function roundsOf() {
  return [...SK.v.circles.map(c => ({ id: c.id, xc: c.xc, r: c.r, a0: 0, a1: 2 * Math.PI })),
    ...(SK.v.arcs || []).map(a => ({ id: a.id, xc: a.xc, r: a.r, a0: a.a0, a1: a.a1 }))];
}
function angIn(t, c) {
  if (c.a1 - c.a0 >= 2 * Math.PI - 1e-9) return true;
  while (t < c.a0) t += 2 * Math.PI;
  while (t > c.a0 + 2 * Math.PI) t -= 2 * Math.PI;
  return t <= c.a1 + 1e-9;
}
function segCircle(a, b, c) {            // incroci di un segmento con un cerchio/arco
  const dx = b[0] - a[0], dy = b[1] - a[1], fx = a[0] - c.xc[0], fy = a[1] - c.xc[1];
  const A = dx * dx + dy * dy, B = 2 * (fx * dx + fy * dy), C = fx * fx + fy * fy - c.r * c.r, D = B * B - 4 * A * C;
  if (D < 0 || A < 1e-12) return [];
  const out = [];
  for (const sg of [-1, 1]) {
    const t = (-B + sg * Math.sqrt(D)) / (2 * A);
    if (t < -1e-9 || t > 1 + 1e-9) continue;
    const q = [a[0] + dx * t, a[1] + dy * t];
    if (angIn(Math.atan2(q[1] - c.xc[1], q[0] - c.xc[0]), c)) out.push(q);
  }
  return out;
}
// Taglia/Allunga: l'anteprima la calcola il motore (le stesse regole del comando vero)
async function cutPreview() {
  if (!SK || SK.cutBusy || !SK.cutAt) return;
  SK.cutBusy = true;
  const q = SK.cutAt, tool = SK.tool;
  const r = await call(tool === 'trim' ? 'sketch_trim_preview' : 'sketch_extend_preview', SK.sid, q.id, q.xy);
  if (!SK) return;
  SK.cutBusy = false;
  SK.cutPrev = r.ok && SK.tool === tool ? { tool, ...r } : null;
  SK.cutMsg = r.ok ? null : r.message;
  drawRubber();
  if (SK.cutAt !== q) cutPreview();
}
let ultimoRaccordo = '5', ultimoSmusso = '5';
// lo spigolo vicino al mouse: un punto dove arrivano esattamente due linee (anche se sta sopra l'origine)
function cornerAt(ev) {
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const conta = {}, bordi = {};
  for (const l of SK.v.lines) {
    const c = l.ref ? bordi : conta;
    c[l.a] = (c[l.a] || 0) + 1; c[l.b] = (c[l.b] || 0) + 1;
  }
  for (const a of SK.v.arcs || []) { conta[a.start] = 99; conta[a.end] = 99; }
  let best = null;
  for (const p of SK.v.points) {
    // uno spigolo del disegno, o uno spigolo del pezzo (due bordi arancio): quello si raccorda sul pezzo vero
    if (p.id === 'O' || !(conta[p.id] === 2 || (!conta[p.id] && bordi[p.id] === 2))) continue;
    if (!conta[p.id] && inFila(p)) continue;
    const q = skScreen(p.xy), d = Math.hypot(q[0] - mx, q[1] - my);
    if (d < 12 && (!best || d < best.d)) best = { p, d };
  }
  return best?.p || null;
}
function inFila(p) {                     // due bordi in fila: lì non c'è uno spigolo
  const xy = Object.fromEntries(SK.v.points.map(q => [q.id, q.xy]));
  const d = SK.v.lines.filter(l => l.ref && (l.a === p.id || l.b === p.id)).map(l => {
    const o = xy[l.a === p.id ? l.b : l.a]; return o && [o[0] - p.xy[0], o[1] - p.xy[1]];
  });
  if (d.length !== 2 || !d[0] || !d[1]) return false;
  return Math.abs(d[0][0] * d[1][1] - d[0][1] * d[1][0]) <= 1e-6 * Math.hypot(...d[0]) * Math.hypot(...d[1]);
}
// Raccordo/Smusso: clic sullo spigolo, oppure (come AutoCAD) sulla prima e sulla seconda linea
function cornerClick(ev) {
  const tool = SK.tool, P = SK.pick, xy = skPick(ev);
  if (P?.what === 'corner2') {
    const h = skHit(ev);
    if (!h || !SK.v.lines.some(l => l.id === h) || h === P.l1) { toast('Clicca la seconda linea.', 'err'); return; }
    SK.sel = new Set([P.l1, h]); drawSketch();
    askCorner({ what: 'corner', tool, lines: [P.l1, h], clicks: [P.c1, xy], xy });
    return;
  }
  const p = cornerAt(ev);
  if (p) { SK.sel.clear(); drawSketch(); askCorner({ what: 'corner', tool, pid: p.id, xy: p.xy }); return; }
  const h = skHit(ev);
  if (h && SK.v.lines.some(l => l.id === h)) {
    SK.pick = { what: 'corner2', tool, l1: h, c1: xy };
    SK.sel = new Set([h]); drawSketch();
    setHelp(`${tool === 'fillet' ? 'Raccordo' : 'Smusso'}: ora clic sulla seconda linea · Esc annulla`);
    return;
  }
  toast('Clicca uno spigolo (dove si incontrano due linee) oppure le due linee, una dopo l’altra.', 'err');
}
function askCorner(pick) {
  SK.pick = pick;
  updateCmd();
  const inp = $('#sk-cmd-in');
  inp.value = pick.tool === 'fillet' ? ultimoRaccordo : ultimoSmusso; inp.focus(); inp.select();
  setHelp(`${pick.tool === 'fillet' ? 'Raggio del raccordo' : 'Misura dello smusso'} nella casella in basso + Invio${pick.lines ? ' (0 = unisci le linee in uno spigolo vivo)' : ''} · Esc annulla`);
  drawRubber();
}
function cutClick(ev) {
  const h = skHit(ev), xy = skPick(ev);
  if (!h || !xy) { toast(SK.tool === 'trim' ? 'Clicca il pezzo da togliere.' : 'Clicca vicino all’estremità da allungare.', 'err'); return; }
  const sid = SK.sid, tool = SK.tool;
  SK.cutPrev = null; SK.cutAt = null; drawRubber();
  inCoda(async () => {
    await apply(await call(tool === 'trim' ? 'sketch_trim' : 'sketch_extend', sid, h, xy));
    // l'anteprima arrivata nel frattempo riguarda il disegno di prima: via (si rifà muovendo il mouse)
    if (SK) { SK.cutPrev = null; SK.cutAt = null; drawRubber(); }
  });
}
function segX(a, b, c, d) {             // incrocio di due segmenti (o null)
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-12) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  if (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9) return null;
  return [a[0] + r[0] * t, a[1] + r[1] * t];
}
function skClick(ev) {
  if (SK.pick) { skPickClick(ev); return; }
  if (SK.tool === 'dim') { skDimClick(ev); return; }
  if (SK.tool === 'trim' || SK.tool === 'extend') { cutClick(ev); return; }
  if (SK.tool === 'fillet' || SK.tool === 'chamfer') { cornerClick(ev); return; }
  if (SK.tool === 'select') {
    const h = skHit(ev);
    if (!h) SK.sel.clear(); else if (SK.sel.has(h)) SK.sel.delete(h); else { if (!ev.shiftKey) SK.sel.clear(); SK.sel.add(h); }
    drawSketch();
    return;
  }
  const c = SK.cursor || skCursor(ev);
  if (!c) return;
  skPlace(c);
}
function skPlace(c) {
  const p = { id: c.id, xy: c.xy, ref: c.ref };
  if (SK.tool === 'line') {
    if (SK.pts.length >= 3 && (c.first || (c.id && c.id === SK.pts[0].id))) { skFinish(true); return; }
    if (SK.pts.length && c.id && SK.pts.some(q => q.id === c.id)) { toast('Questo punto è già nella linea che stai disegnando.', 'err'); return; }
    SK.pts.push(p);
    if (SK.pts.length >= 2 && c.id && !SK.pts.slice(0, -1).some(q => q.id === c.id)) { skFinish(false); return; }   // agganciato a un punto che c'era: si collega lì
  } else if (SK.tool === 'rect') {
    if (!SK.pts.length) { SK.pts.push(p); }
    else { const a = SK.pts[0]; SK.pts = []; const k = SK.constr; inCoda(async () => { await apply(await call('sketch_add_rectangle', SK.sid, ptArg(a), c.xy, k)); }); }
  } else if (SK.tool === 'arc3') {
    if (SK.pts.length < 2) SK.pts.push(p);
    else {
      const [a, b] = SK.pts; SK.pts = [];
      const k = SK.constr, sid = SK.sid;
      inCoda(async () => { await apply(await call('sketch_add_arc3', sid, ptArg(a), b.xy, ptArg(p), k)); });
    }
  } else if (SK.tool === 'polygon') {
    if (!SK.pts.length) SK.pts.push(p);
    else {
      const a = SK.pts[0]; SK.pts = [];
      const k = SK.constr, sid = SK.sid, n = SK.polyN || 6;
      if (Math.hypot(c.xy[0] - a.xy[0], c.xy[1] - a.xy[1]) > 1e-6) inCoda(async () => { await apply(await call('sketch_add_polygon', sid, ptArg(a), c.xy, n, k)); });
    }
  } else if (SK.tool === 'slot') {
    if (SK.pts.length < 2) {
      if (SK.pts.length === 1 && Math.hypot(c.xy[0] - SK.pts[0].xy[0], c.xy[1] - SK.pts[0].xy[1]) < 1e-6) { toast('Il secondo centro deve essere diverso dal primo.', 'err'); return; }
      SK.pts.push(p);
    } else {
      const r = slotR(c.xy);
      if (r > 0) addSlot(r);
    }
  } else if (SK.tool === 'circle') {
    if (!SK.pts.length) { SK.pts.push(p); }
    else { const a = SK.pts[0]; SK.pts = []; const k = SK.constr; const r = Math.hypot(c.xy[0] - a.xy[0], c.xy[1] - a.xy[1]); if (r > 0) inCoda(async () => { await apply(await call('sketch_add_circle', SK.sid, ptArg(a), r, k)); }); }
  }
  SK.buf = '';
  drawRubber();
}
// asola: la larghezza è il doppio della distanza del mouse dalla linea dei centri
// l'arco per tre punti, come punti da disegnare (con il raggio)
function arcThrough(p1, p2, p3) {
  const [x1, y1] = p1, [x2, y2] = p2, [x3, y3] = p3;
  const d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2));
  if (Math.abs(d) < 1e-9) return [p1, p3];
  const ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d;
  const uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d;
  const r = Math.hypot(x1 - ux, y1 - uy);
  let a1 = Math.atan2(y1 - uy, x1 - ux), a3 = Math.atan2(y3 - uy, x3 - ux);
  const ccw = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) > 0;
  if (ccw) { while (a3 <= a1) a3 += 2 * Math.PI; } else { while (a3 >= a1) a3 -= 2 * Math.PI; }
  const pts = [];
  for (let i = 0; i <= 48; i++) { const t = a1 + (a3 - a1) * i / 48; pts.push([ux + r * Math.cos(t), uy + r * Math.sin(t)]); }
  pts.r = r;
  return pts;
}
function slotR(xy) {
  const [a, b] = SK.pts.map(p => p.xy);
  const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
  return Math.abs((xy[0] - a[0]) * dy - (xy[1] - a[1]) * dx) / L;
}
function addSlot(r) {
  const [a, b] = SK.pts; SK.pts = [];
  const k = SK.constr, sid = SK.sid;
  inCoda(async () => { await apply(await call('sketch_add_slot', sid, ptArg(a), ptArg(b), r, k)); });
  drawRubber();
}
function skFinish(closed) {
  const pts = SK.pts;
  SK.pts = []; SK.buf = '';
  drawRubber();
  if (pts.length < 2) return;
  const k = SK.constr, angs = SK.angs || {};
  SK.angs = {};
  const angoli = pts.map((_, i) => angs[i] ?? null).slice(0, closed ? pts.length : pts.length - 1);
  inCoda(async () => { await apply(await call('sketch_add_polyline', SK.sid, pts.map(ptArg), closed, k, angoli)); });
}
// lunghezza scritta: nella direzione del mouse (orizzontale/verticale se ci sei vicino)
function skTyped() {
  // "100<30": lunghezza 100 con angolo 30° dall'asse X (antiorario; negativo in senso orario)
  const m = SK.tool === 'line' && SK.buf.match(/^\s*([0-9.,]+)\s*<\s*(-?[0-9.,]+)\s*$/);
  if (m) { SK.buf = ''; skTypedAngle(parseFloat(m[1].replace(',', '.')), parseFloat(m[2].replace(',', '.'))); return; }
  // rettangolo "100x50": larghezza x altezza, verso il mouse
  const mr = SK.tool === 'rect' && SK.buf.match(/^\s*([0-9.,]+)\s*[xX*×]\s*([0-9.,]+)\s*$/);
  const rectH = mr ? parseFloat(mr[2].replace(',', '.')) : null;
  const v = parseFloat((mr ? mr[1] : SK.buf).replace(',', '.'));
  SK.buf = '';
  if (mr && !(rectH > 0)) { toast('Scrivi così: larghezza x altezza, per esempio 100x50', 'err'); return; }
  if (!(v > 0)) { toast('Scrivi un numero maggiore di zero.', 'err'); return; }
  const last = SK.pts[SK.pts.length - 1];
  if (!last) { toast('Prima clicca il punto di partenza.', 'err'); return; }
  if (SK.pick) { skPickTyped(v); return; }
  if (SK.tool === 'circle') { const a = SK.pts[0]; SK.pts = []; const k = SK.constr; inCoda(async () => { await apply(await call('sketch_add_circle', SK.sid, ptArg(a), v / 2, k)); }); drawRubber(); return; }
  if (SK.tool === 'slot') {
    if (SK.pts.length === 2) { addSlot(v / 2); return; }
    // interasse scritto: il secondo centro nella direzione del mouse (orizzontale/verticale se ci sei vicino)
    const c0 = SK.cursor?.xy || [last.xy[0] + 1, last.xy[1]];
    let ux = c0[0] - last.xy[0], uy = c0[1] - last.xy[1];
    const LL = Math.hypot(ux, uy) || 1; ux /= LL; uy /= LL;
    const an = Math.abs(Math.atan2(uy, ux) * 180 / Math.PI);
    if (an < 8 || an > 172) { ux = Math.sign(ux) || 1; uy = 0; } else if (Math.abs(an - 90) < 8) { ux = 0; uy = Math.sign(uy) || 1; }
    SK.pts.push({ id: null, xy: [last.xy[0] + ux * v, last.xy[1] + uy * v] });
    drawRubber(); return;
  }
  const c = SK.cursor?.xy || [last.xy[0] + 1, last.xy[1]];
  let dx = c[0] - last.xy[0], dy = c[1] - last.xy[1];
  const L = Math.hypot(dx, dy) || 1;
  dx /= L; dy /= L;
  const ang = Math.abs(Math.atan2(dy, dx) * 180 / Math.PI);
  if (ang < 8 || ang > 172) { dx = Math.sign(dx) || 1; dy = 0; } else if (Math.abs(ang - 90) < 8) { dx = 0; dy = Math.sign(dy) || 1; }
  const q = [Math.round((last.xy[0] + dx * v) * 1000) / 1000, Math.round((last.xy[1] + dy * v) * 1000) / 1000];
  const primo = SK.pts[0];
  if (SK.tool === 'line' && SK.pts.length >= 3 && Math.hypot(q[0] - primo.xy[0], q[1] - primo.xy[1]) < 1e-6) { skFinish(true); return; }
  if (SK.tool === 'rect') { SK.pts = []; const k = SK.constr, h = rectH ?? v; inCoda(async () => { await apply(await call('sketch_add_rectangle', SK.sid, ptArg(last), [last.xy[0] + (Math.sign(c[0] - last.xy[0]) || 1) * v, last.xy[1] + (Math.sign(c[1] - last.xy[1]) || 1) * h], k)); }); drawRubber(); return; }
  SK.pts.push({ id: null, xy: q });
  SK.cursor = { xy: q, id: null, how: 'scritto' };
  drawRubber();
}
function skTypedAngle(L, A) {
  const last = SK.pts[SK.pts.length - 1];
  if (!last) { toast('Prima clicca il punto di partenza.', 'err'); return; }
  if (!(L > 0) || !Number.isFinite(A)) { toast('Scrivi così: lunghezza<angolo, per esempio 100<30', 'err'); return; }
  const r = A * Math.PI / 180;
  const q = [Math.round((last.xy[0] + L * Math.cos(r)) * 1000) / 1000, Math.round((last.xy[1] + L * Math.sin(r)) * 1000) / 1000];
  const primo = SK.pts[0];
  SK.angs = SK.angs || {};
  SK.angs[SK.pts.length - 1] = A;                 // il tratto che parte dall'ultimo punto ha questo angolo
  if (SK.pts.length >= 3 && Math.hypot(q[0] - primo.xy[0], q[1] - primo.xy[1]) < 1e-6) { skFinish(true); return; }
  SK.pts.push({ id: null, xy: q });
  SK.cursor = { xy: q, id: null, how: 'scritto' };
  drawRubber();
}
function skKey(ev) {
  if (!SK || ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName) || !$('#modal').hidden || !$('#palette').hidden) return false;
  if (SK.pick?.what === 'offset' && SK.pick.stage === 'dist' && !ev.ctrlKey) {
    if (/^[0-9.,]$/.test(ev.key)) { SK.buf += ev.key; offHelp(); return true; }
    if (ev.key === 'Backspace') { SK.buf = SK.buf.slice(0, -1); offHelp(); return true; }
    if (ev.key === 'Enter') { offsetDist(); return true; }
  }
  if (ev.ctrlKey && ev.key.toLowerCase() === 'a') {
    SK.sel = new Set([...SK.v.lines.map(l => l.id), ...SK.v.circles.map(c => c.id)]); setTool('select'); drawSketch(); return true;
  }
  if (ev.key === 'F9') {
    SK.grid = aggancioGriglia = !SK.grid;
    toast(SK.grid ? 'Aggancio alla griglia acceso (F9)' : 'Aggancio alla griglia spento (F9)');
    drawSketch(); return true;
  }
  if (ev.ctrlKey || ev.altKey) return false;
  const k = ev.key;
  if ((/^[0-9.,]$/.test(k) || (SK.tool === 'line' && /^[<\-]$/.test(k)) || (SK.tool === 'rect' && SK.buf && /^[xX*]$/.test(k)))
      && SK.tool !== 'select' && SK.pts.length) { SK.buf += k; drawRubber(); return true; }
  if (k === 'Backspace' && SK.buf) { SK.buf = SK.buf.slice(0, -1); drawRubber(); return true; }
  if (k === 'Enter') { if (SK.buf) skTyped(); else if (SK.tool === 'line' && SK.pts.length >= 2) skFinish(false); return true; }
  if (k === 'Escape') {
    if (SK.buf) { SK.buf = ''; drawRubber(); return true; }
    if (SK.pick?.what === 'corner' || SK.pick?.what === 'corner2') { const t = SK.pick.tool; SK.pick = null; SK.sel.clear(); drawSketch(); setTool(t); return true; }
    if (SK.pick) { SK.pick = null; setTool('select'); return true; }
    if (SK.dimPick.length) { SK.dimPick = []; drawRubber(); return true; }
    if (SK.tool === 'line' && SK.pts.length >= 2) { skFinish(false); return true; }
    if (SK.pts.length) { SK.pts = []; drawRubber(); return true; }
    if (SK.sel.size) { SK.sel.clear(); drawSketch(); return true; }
    if (SK.tool === 'trim' || SK.tool === 'extend') { setTool('select'); return true; }
    exitSketch(); return true;
  }
  if (k === 'Delete' && SK.sel.size) {
    const ids = [...SK.sel]; SK.sel.clear();
    inCoda(async () => { await apply(await call('sketch_delete', SK.sid, ids)); });
    return true;
  }
  const tasti = { l: 'line', r: 'rect', c: 'circle', k: 'slot', p: 'polygon', s: 'select', d: 'dim', t: 'trim', a: 'extend' };
  if (tasti[k.toLowerCase()]) { setTool(tasti[k.toLowerCase()]); return true; }
  if (k.toLowerCase() === 'x') { SK.constr = !SK.constr; drawSketch(); return true; }
  if (k.toLowerCase() === 'g' && (SK.v.on_face || SK.v.on_flat)) { SK.ghost = !SK.ghost; applyLook(); return true; }
  if (k.toLowerCase() === 'v' && SK.v.on_face) { toggleXray(); return true; }
  if (k.toLowerCase() === 'o') { startOffset(); return true; }
  if (k.toLowerCase() === 'm' && SK.sel.size) { skAction('mirror'); return true; }
  if (['f', '0', '1', '3', '7', 'q'].includes(k.toLowerCase())) return false;
  return true;          // nient'altro deve scappare alla vista 3D mentre si disegna
}

// --------------------------------------------------------------- comandi sulla selezione
// Offset come in AutoCAD: scrivi la distanza + Invio, clic sulla linea (prende tutto il contorno collegato)
// o sul cerchio, poi clic dalla parte dove va: l'anteprima segue il mouse. Resta attivo per altri oggetti.
let ultimoOffset = '10';
function startOffset() {
  SK.pts = []; SK.buf = '';
  SK.pick = { what: 'offset', stage: 'dist', ids: SK.sel.size ? [...SK.sel] : null, dist: null, prev: null, mouse: null, busy: false };
  offHelp();
  drawRubber();
  const inp = $('#sk-cmd-in');
  inp.value = ultimoOffset; inp.focus(); inp.select();
}
function offHelp() {
  const P = SK.pick;
  updateCmd();
  if (P.stage === 'dist') setHelp('Offset: scrivi la distanza nella casella in alto e premi Invio · Esc annulla');
  else if (P.stage === 'obj') setHelp(`Offset ${P.dist}: clic sulla linea o sul cerchio da copiare (per un contorno intero: prima selezionalo con doppio clic, poi O) · Esc finisce`);
  else setHelp(`Offset ${P.dist}: muovi il mouse dalla parte dove va e clicca · Esc finisce`);
}
// Casella di comando in alto nella vista (come la riga di comando di AutoCAD): dice cosa scrivere e
// mostra quello che scrivi. Si può anche cliccare e scriverci dentro; Invio conferma.
function promptCmd() {
  const P = SK?.pick;
  if (!SK) return null;
  if (P?.what === 'corner') return P.tool === 'fillet' ? 'Raggio del raccordo' : 'Misura dello smusso';
  if (P?.what === 'offset') return P.stage === 'dist' ? 'Distanza dell’offset'
    : `Offset · ${P.stage === 'obj' ? 'clic sulla linea da copiare' : 'clic dalla parte dove va'} · distanza`;
  if ((P?.what === 'copy' || P?.what === 'move') && P.base) return 'Distanza (nella direzione del mouse)';
  if (P) return null;
  if (SK.tool === 'polygon' && !SK.pts.length) return 'Numero di lati';
  if (!SK.pts.length) return null;
  if (SK.tool === 'line') return 'Lunghezza, oppure lunghezza<angolo (es. 100<30)';
  if (SK.tool === 'rect') return 'Misure: larghezza x altezza (es. 100x50)';
  if (SK.tool === 'circle') return 'Diametro';
  if (SK.tool === 'slot') return SK.pts.length === 1 ? 'Interasse (distanza tra i centri)' : 'Larghezza dell’asola';
  if (SK.tool === 'polygon') return SK.pts.length ? null : 'Numero di lati';
  if (SK.tool === 'arc3') return null;
  return null;
}
function updateCmd() {
  const box = $('#sk-cmd'), inp = $('#sk-cmd-in'), testo = promptCmd();
  const off = SK?.pick?.what === 'offset';           // mentre fai l'offset è acceso Offset, non lo strumento di prima
  document.querySelectorAll('#sk-panel [data-tool], #ribbon [data-tool]').forEach(b => b.classList.toggle('on', !off && SK?.tool === b.dataset.tool));
  document.querySelectorAll('#sk-panel [data-act="offset"], #ribbon [data-act="offset"]').forEach(b => b.classList.toggle('on', off));
  box.hidden = !testo;
  if (!testo) { if (document.activeElement === inp) inp.blur(); return; }
  $('#sk-cmd-label').textContent = testo;
  if (document.activeElement !== inp) {
    const P = SK.pick;
    inp.value = P?.what === 'offset' && P.stage !== 'dist' ? String(P.dist).replace('.', ',')
      : !P && SK.tool === 'polygon' && !SK.pts.length ? String(SK.polyN || 6) : SK.buf;
  }
}
function cmdEnter(val) {
  const P = SK.pick;
  if (P?.what === 'corner') {
    const v = parseFloat(val.replace(',', '.'));
    if (!(v > 0 || (P.lines && v === 0))) { toast(P.lines ? 'Scrivi una misura (0 = spigolo vivo).' : 'Scrivi una misura maggiore di zero.', 'err'); return; }
    if (P.tool === 'fillet') ultimoRaccordo = val; else ultimoSmusso = val;
    SK.pick = null; SK.sel.clear();
    const sid = SK.sid;
    inCoda(async () => {
      if (P.lines) await apply(await call(P.tool === 'fillet' ? 'sketch_fillet_lines' : 'sketch_chamfer_lines', sid, P.lines[0], P.lines[1], P.clicks[0], P.clicks[1], v));
      else await apply(await call(P.tool === 'fillet' ? 'sketch_fillet' : 'sketch_chamfer', sid, P.pid, v));
    });
    setTool(P.tool);                                   // resta attivo per un altro spigolo
    return;
  }
  if (!P && SK.tool === 'polygon' && !SK.pts.length) {
    const n = parseInt(val, 10);
    if (!(n >= 3 && n <= 64)) { toast('Il poligono va da 3 a 64 lati.', 'err'); return; }
    SK.polyN = n; setHelp(`Poligono a ${n} lati: clic sul centro, poi su un vertice`);
    return;
  }
  if (P?.what === 'offset') {
    if (P.stage === 'dist') { SK.buf = val; offsetDist(); return; }
    const v = parseFloat(val.replace(',', '.'));      // cambiata a metà: vale da subito
    if (!(v > 0)) { toast('Scrivi una distanza maggiore di zero.', 'err'); return; }
    P.dist = v; ultimoOffset = String(v).replace('.', ','); P.prev = null;
    offHelp(); offPreview();
    return;
  }
  SK.buf = val;
  if (SK.buf) skTyped();
}
$('#sk-cmd-in').addEventListener('keydown', ev => {
  ev.stopPropagation();
  const inp = ev.target;
  if (ev.key === 'Escape') {
    inp.blur();
    if (SK?.pick?.what === 'corner') { const t = SK.pick.tool; SK.pick = null; SK.sel.clear(); drawSketch(); setTool(t); }
    else if (SK?.pick) { SK.pick = null; setTool('select'); } else if (SK) { SK.buf = ''; drawRubber(); }
    return;
  }
  if (ev.key !== 'Enter' || !SK) return;
  ev.preventDefault();
  const val = inp.value.trim();
  inp.blur();
  cmdEnter(val);
  updateCmd();
});
$('#sk-cmd-in').addEventListener('input', ev => { if (SK && !SK.pick) { SK.buf = ev.target.value; drawRubber(); } });

function offsetDist() {
  const P = SK.pick, testo = SK.buf || ultimoOffset;
  SK.buf = '';
  const v = parseFloat(testo.replace(',', '.'));
  if (!(v > 0)) { toast('Scrivi una distanza maggiore di zero.', 'err'); offHelp(); return; }
  ultimoOffset = String(v).replace('.', ',');
  P.dist = v;
  P.stage = P.ids ? 'side' : 'obj';
  offHelp();
}
async function offPreview() {
  const P = SK?.pick;
  if (!P || P.what !== 'offset' || P.stage !== 'side' || P.busy || !P.mouse) return;
  P.busy = true;
  const m = P.mouse;
  const r = await call('sketch_offset_side', SK.sid, P.ids, P.dist, m);
  P.busy = false;
  if (SK?.pick !== P) return;
  P.prev = r.ok ? r.preview : null;
  drawRubber();
  if (P.mouse !== m) offPreview();
}
function offsetClick(ev) {
  const P = SK.pick;
  if (P.stage === 'dist') { offsetDist(); return; }
  if (P.stage === 'obj') {
    const h = skHit(ev);
    if (!h) { toast('Clicca una linea o un cerchio.', 'err'); return; }
    P.ids = [h];                       // come AutoCAD: l'oggetto cliccato, una linea o un cerchio
    SK.sel = new Set(P.ids);
    P.stage = 'side'; P.mouse = skPick(ev);
    drawSketch(); offHelp(); offPreview();
    return;
  }
  const punto = skPick(ev);
  if (!punto) return;
  const sid = SK.sid, ids = P.ids, d = P.dist;
  // fatto: si resta nell'offset con la stessa distanza, pronti per un altro oggetto
  P.ids = null; P.prev = null; P.stage = 'obj';
  SK.sel.clear(); drawSketch(); offHelp(); drawRubber();
  inCoda(async () => {
    const r = await call('sketch_offset_side', sid, ids, d, punto);
    if (!r.ok) { toast(r.message, 'err'); return; }
    await apply(await call('sketch_offset', sid, ids, d, r.side));
  });
}

function skAction(act) {
  if (act === 'offset') { startOffset(); return; }
  const ids = [...SK.sel];
  if (!ids.length) { toast('Seleziona prima qualcosa (strumento Seleziona).', 'err'); return; }
  const sid = SK.sid;
  if (act === 'delete') { SK.sel.clear(); inCoda(async () => { await apply(await call('sketch_delete', sid, ids)); }); return; }
  if (act === 'constr') {
    const tutte = ids.every(id => (SK.v.lines.find(l => l.id === id) || SK.v.circles.find(c => c.id === id))?.construction);
    inCoda(async () => { await apply(await call('sketch_construction', sid, ids, !tutte)); });
    return;
  }
  if (act === 'hole') {
    const cerchi = ids.filter(id => SK.v.circles.some(c => c.id === id && !c.ref));
    if (!cerchi.length) { toast('Seleziona uno o più cerchi (i fori).', 'err'); return; }
    const c0 = SK.v.circles.find(c => c.id === cerchi[0]);
    const h = c0.hole || {};
    const filetti = ['M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M16'];
    modal(`<h3>Tipo di foro (${cerchi.length} ${cerchi.length === 1 ? 'cerchio' : 'cerchi'})</h3>
      <div class="choice" id="h-tipo">${[['semplice', 'Semplice', 'foro dritto'], ['svasato', 'Svasato', 'per viti a testa piana'], ['filettato', 'Filettato', 'il cerchio diventa il preforo'], ['inserto', 'Inserto', 'a pressare (PEM…)']]
        .map(([k, t, n]) => `<button data-k="${k}" class="${(h.tipo || 'semplice') === k ? 'on' : ''}">${t}<small>${n}</small></button>`).join('')}</div>
      <div class="form" id="h-sva"><label>Ø svasatura (mm)<input class="field" id="h-D" value="${esc(String(h.D ?? Math.round(c0.r * 2 * 2 * 10) / 10).replace('.', ','))}"></label>
        <label>Angolo (°)<input class="field" id="h-ang" value="${esc(String(h.angolo ?? 90))}"></label></div>
      <div class="form" id="h-fil"><label>Filettatura<select class="field" id="h-M">${filetti.map(m => `<option${(h.M || 'M6') === m ? ' selected' : ''}>${m}</option>`).join('')}</select></label>
        <p class="hint" style="grid-column:1/-1">Il diametro del cerchio diventa quello del preforo (es. M6 → Ø5). La filettatura compare nell’albero.</p></div>
      <div class="form" id="h-ins"><label>Codice inserto<input class="field" id="h-cod" value="${esc(h.codice || '')}" placeholder="es. dal catalogo del fornitore"></label>
        <label>Ø foro (mm, da catalogo)<input class="field" id="h-Di" value="${esc(h.tipo === 'inserto' ? String(h.D).replace('.', ',') : '')}"></label>
        <p class="hint" style="grid-column:1/-1">Il cerchio prende il diametro del foro; gli inserti compaiono nell’albero col loro codice.</p></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Applica</button></div>`, close => {
      let tipo = h.tipo || 'semplice';
      const mostra = () => { $('#h-sva').hidden = tipo !== 'svasato'; $('#h-fil').hidden = tipo !== 'filettato'; $('#h-ins').hidden = tipo !== 'inserto';
        document.querySelectorAll('#h-tipo button').forEach(b => b.classList.toggle('on', b.dataset.k === tipo)); };
      document.querySelectorAll('#h-tipo button').forEach(b => { b.onclick = () => { tipo = b.dataset.k; mostra(); }; });
      mostra();
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const spec = tipo === 'svasato' ? { tipo, D: $('#h-D').value.trim(), angolo: $('#h-ang').value.trim() }
          : tipo === 'filettato' ? { tipo, M: $('#h-M').value }
          : tipo === 'inserto' ? { tipo, codice: $('#h-cod').value.trim(), D: $('#h-Di').value.trim() } : null;
        close();
        inCoda(async () => { await apply(await call('sketch_hole_type', sid, cerchi, spec)); });
      };
    });
    return;
  }
  if (act === 'mirror') { SK.pick = { what: 'axis', ids }; setHelp('Specchia: clic sulla linea che fa da asse (va bene una di costruzione) · Esc annulla'); return; }
  if (act === 'copy' || act === 'move') {
    SK.pick = { what: act, ids, base: null };
    setHelp(`${act === 'copy' ? 'Copia' : 'Sposta'}: clic sul punto di partenza, poi dove va (o scrivi la distanza + Invio) · Esc annulla`);
    return;
  }
  if (act === 'pattern') {
    modal(`<h3>Serie</h3><p class="hint">Colonne lungo X e righe lungo Y, originale compreso. I passi diventano parametri (px, py): li cambi dopo e la serie segue.</p>
      <div class="form"><label>Colonne<input class="field" id="p-c" value="3"></label><label>Passo X (mm)<input class="field" id="p-px" value="50"></label>
      <label>Righe<input class="field" id="p-r" value="1"></label><label>Passo Y (mm)<input class="field" id="p-py" value="50"></label></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Crea serie</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => { const v = ['#p-c', '#p-px', '#p-r', '#p-py'].map(q => $(q).value.trim()); close();
        inCoda(async () => { await apply(await call('sketch_pattern', sid, ids, ...v)); }); };
      $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#m-ok').click(); if (ev.key === 'Escape') close(); };
    });
    return;
  }
}
function skPickClick(ev) {
  const P = SK.pick;
  if (P.what === 'offset') { offsetClick(ev); return; }
  if (P.what === 'corner') { SK.pick = null; SK.sel.clear(); cornerClick(ev); return; }
  if (P.what === 'corner2') { cornerClick(ev); return; }
  if (P.what === 'axis') {
    const h = skHit(ev);
    if (!h || !SK.v.lines.some(l => l.id === h)) { toast('Clicca una linea: sarà l’asse dello specchio.', 'err'); return; }
    SK.pick = null; setTool('select');
    inCoda(async () => { await apply(await call('sketch_mirror', SK.sid, P.ids, h)); });
    return;
  }
  const c = SK.cursor || skCursor(ev);
  if (!c) return;
  if (!P.base) { P.base = { xy: c.xy }; SK.pts = [P.base]; drawRubber(); return; }
  skPickDone(c.xy[0] - P.base.xy[0], c.xy[1] - P.base.xy[1]);
}
function skPickTyped(v) {
  const P = SK.pick;
  if (!P.base) { toast('Prima clicca il punto di partenza.', 'err'); return; }
  const c = SK.cursor?.xy || [P.base.xy[0] + 1, P.base.xy[1]];
  let dx = c[0] - P.base.xy[0], dy = c[1] - P.base.xy[1];
  const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
  const ang = Math.abs(Math.atan2(dy, dx) * 180 / Math.PI);
  if (ang < 8 || ang > 172) { dx = Math.sign(dx) || 1; dy = 0; } else if (Math.abs(ang - 90) < 8) { dx = 0; dy = Math.sign(dy) || 1; }
  skPickDone(dx * v, dy * v);
}
function skPickDone(dx, dy) {
  const P = SK.pick;
  SK.pick = null; SK.pts = []; setTool('select');
  if (Math.hypot(dx, dy) < 1e-9) { toast('Partenza e arrivo coincidono.', 'err'); return; }
  inCoda(async () => { await apply(await call(P.what === 'copy' ? 'sketch_copy' : 'sketch_move', SK.sid, P.ids, dx, dy)); });
}
// --------------------------------------------------------------- quota a mano
function skDimClick(ev) {
  const c = skCursor(ev);
  const punto = c && c.id ? c.id : null;
  const h = punto ? null : skHit(ev);
  const sid = SK.sid;
  if (!SK.dimPick.length) {
    if (punto) { SK.dimPick = [punto]; setHelp('Quota: ora clic su un altro punto o su una linea · Esc annulla'); return; }
    if (h && SK.v.circles.some(x => x.id === h)) { inCoda(async () => { await apply(await call('sketch_dimension', sid, 'diameter', [h])); }); return; }
    if (h) { inCoda(async () => { await apply(await call('sketch_dimension', sid, 'length', [h])); }); return; }
    return;
  }
  const a = SK.dimPick[0];
  SK.dimPick = []; setTool('dim');
  if (h && SK.v.lines.some(l => l.id === h)) { inCoda(async () => { await apply(await call('sketch_dimension', sid, 'pldistance', [a, h])); }); return; }
  if (!punto || punto === a) return;
  modal(`<h3>Quota tra due punti</h3><div class="choice"><button data-k="hdistance">Orizzontale</button><button data-k="vdistance">Verticale</button><button data-k="distance">Allineata</button></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#modal-box').querySelectorAll('.choice button').forEach(b => { b.onclick = () => { close(); inCoda(async () => { await apply(await call('sketch_dimension', sid, b.dataset.k, [a, punto])); }); }; });
  });
}

async function structureDialog() {
  if (!profili) profili = await call('profile_suggestions');
  const sid = SK.sid, piano = SK.v.plane;
  const versi = { XZ: { front: 'davanti (Y−)', back: 'dietro (Y+)' }, XY: { front: 'sopra (Z+)', back: 'sotto (Z−)' },
    YZ: { front: 'a destra (X+)', back: 'a sinistra (X−)' } }[piano] || { front: 'avanti', back: 'indietro' };
  const lista = (profili || []).map(x => `<option value="${esc(x)}">`).join('');
  modal(`<h3>Crea struttura</h3>
    <p class="hint">Ogni linea dello sketch (non le guide) diventa un tubolare. Se cambi lo sketch, la struttura si aggiorna.</p>
    <datalist id="dl-st">${lista}</datalist>
    <div class="form"><label>Profilo<input class="field" id="st-p" list="dl-st" value="40x40x3"></label>
      <label>Gruppo (per la distinta)<input class="field" id="st-g" value="Telaio"></label>
      <label>Quante volte (1 = solo questo)<input class="field" id="st-n" value="1"></label>
      <label>A distanza (mm)<input class="field" id="st-d" value="600"></label>
      <label>Verso<select class="field" id="st-s"><option value="back">${esc(versi.back)}</option><option value="front">${esc(versi.front)}</option></select></label>
      <label class="check" style="align-self:end"><input type="checkbox" id="st-c" checked> Collega i nodi con traversi</label>
      <label>Profilo traversi<input class="field" id="st-cp" list="dl-st" value="40x20x2"></label>
      <label>Gruppo traversi<input class="field" id="st-cg" value="Traversi"></label></div>
    <p class="hint">Esempio scaffale: disegni la spalla di fianco, «Quante volte» 2 a distanza L, collega i nodi: escono i traversi dei ripiani. La distanza diventa un parametro (D).</p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Crea struttura</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const v = { profile: $('#st-p').value.trim(), group: $('#st-g').value.trim(), copies: $('#st-n').value.trim(),
        distance: $('#st-d').value.trim(), side: $('#st-s').value, connect: $('#st-c').checked,
        connect_profile: $('#st-cp').value.trim(), connect_group: $('#st-cg').value.trim() };
      close();
      inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'structure', v), 'Struttura creata: la cut list è in basso.')) exitSketch(); });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#m-ok').click(); if (ev.key === 'Escape') close(); };
  });
}

function makeDialog(kind) {
  if (kind === 'structure') { structureDialog(); return; }
  if (kind === 'tab') {
    const sid = SK.sid;
    inCoda(async () => { if (await apply(await call('sheet_tab', sid))) exitSketch(); });
    return;
  }
  if (kind === 'contour') {
    const sid = SK.sid;
    inCoda(async () => { if (await apply(await call('contour_flange', sid))) exitSketch(); });
    return;
  }
  if (kind === 'cut') {
    const sid = SK.sid;
    inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'cut', {}), 'Tagliato.')) exitSketch(); });
    return;
  }
  if (kind === 'fold') {
    modal(`<h3>Piega su questa linea</h3>
      <p class="hint">La linea è lo spigolo esterno della piega. Si piega la parte più piccola; lo sviluppo resta quello che hai disegnato.</p>
      <div class="ff"><label>Angolo<span class="inp"><input class="field" id="m-ang" value="90"><i>°</i></span></label><span></span></div>
      <div class="seg-row"><span>Verso</span><div class="seg" id="m-dir"><button type="button" data-v="up" class="on">su</button><button type="button" data-v="down">giù</button></div></div>
      <label class="check"><input type="checkbox" id="m-flip"> piega l’altra parte</label>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Piega</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const sid = SK.sid, ang = $('#m-ang').value.trim(), dir = $('#m-dir .on').dataset.v, flip = $('#m-flip').checked;
        close();
        inCoda(async () => { const r = await call('sheet_fold', sid, ang, dir, flip); if (await apply(r)) exitSketch(); });
      };
    });
    return;
  }
  if (kind === 'louver' || kind === 'dimple') {
    const per = kind === 'louver';
    modal(`<h3>${per ? 'Persiane' : 'Imbutiture'}</h3>
      <p class="hint">${per ? 'Ogni linea disegnata è il bordo aperto di una persiana; la cappa sale verso sinistra (guardando dal primo al secondo punto).' : 'Ogni cerchio disegnato è un’imbutitura di quel diametro, verso fuori dalla faccia.'}</p>
      <div class="form">${per ? '<label>Larghezza (mm)<input class="field" id="m-w" value="8"></label><label>Altezza (mm)<input class="field" id="m-h" value="4"></label>'
        : '<label>Profondità (mm)<input class="field" id="m-h" value="3"></label>'}</div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Crea</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const v = per ? { width: $('#m-w').value.trim(), height: $('#m-h').value.trim() } : { depth: $('#m-h').value.trim() };
        const sid = SK.sid; close();
        inCoda(async () => { if (await apply(await call('create_from_sketch', sid, kind, v))) exitSketch(); });
      };
    });
    return;
  }
  if (kind === 'boss') {
    modal(`<h3>Estrudi dalla faccia</h3><div class="form"><label>Di quanto (mm)<input class="field" id="m-d" value="10"></label></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Estrudi</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => { const sid = SK.sid, d = $('#m-d').value.trim(); close();
        inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'boss', { distance: d }))) exitSketch(); }); };
    });
    return;
  }
  const lam = kind === 'sheet';
  modal(`<h3>${lam ? 'Crea lamiera dal contorno' : 'Crea piastra dal contorno'}</h3>
    <div class="form"><label>Spessore (mm)<input class="field" id="m-sp" value="${lam ? 2 : 5}"></label>
    ${lam ? `<label>Raggio interno di piega<input class="field" id="m-r" placeholder="dato della piegatrice"></label>
    <label>K-factor<input class="field" id="m-k" placeholder="dato della piegatrice"></label>` : ''}</div>
    ${lam ? '<p class="hint">Raggio e K servono solo quando aggiungi le flange; se li lasci vuoti te li chiederà la scheda Lamiera.</p>' : ''}
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Crea</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const v = { thickness: $('#m-sp').value.trim() };
      if (lam) { v.radius = $('#m-r').value.trim(); v.k = $('#m-k').value.trim(); }
      close();
      const sid = SK.sid;
      inCoda(async () => {
        if (await apply(await call('create_from_sketch', sid, kind, v), lam ? 'Lamiera creata: clicca un fianco per aggiungere una flangia.' : 'Piastra creata.')) {
          exitSketch();
          if (lam) document.querySelector('.tabs button[data-tab="sheet"]')?.click();
        }
      });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#m-ok').click(); if (ev.key === 'Escape') close(); };
  });
}

// tutto il contorno collegato a una linea (stesso tipo: normale o di costruzione)
function chainOf(h) {
  const l0 = SK.v.lines.find(l => l.id === h);
  if (!l0) return new Set([h]);
  const presi = new Set([h]);
  let cresce = true;
  while (cresce) {
    cresce = false;
    const punti = new Set(SK.v.lines.filter(l => presi.has(l.id)).flatMap(l => [l.a, l.b]));
    for (const l of SK.v.lines) if (!presi.has(l.id) && l.construction === l0.construction && (punti.has(l.a) || punti.has(l.b))) { presi.add(l.id); cresce = true; }
  }
  return presi;
}
canvas.addEventListener('dblclick', ev => {
  if (!SK || SK.tool !== 'select' || SK.pick) return;
  const h = skHit(ev);
  if (!h || !SK.v.lines.some(l => l.id === h)) return;
  SK.sel = chainOf(h); drawSketch();
});
$('#sk-panel').addEventListener('click', ev => {
  const b = ev.target.closest('button');
  if (!b || !SK) return;
  if (b.id === 'sk-constr') { SK.constr = !SK.constr; drawSketch(); return; }
  if (b.id === 'sk-grid') { SK.grid = aggancioGriglia = !SK.grid; drawSketch(); return; }
  if (b.id === 'sk-ghost') { SK.ghost = !SK.ghost; applyLook(); return; }
  if (b.id === 'sk-xray') { toggleXray(); return; }
  if (b.dataset.act) { skAction(b.dataset.act); return; }
  if (b.dataset.tool) setTool(b.dataset.tool);
  else if (b.dataset.make) makeDialog(b.dataset.make);
  else if (b.id === 'sk-done') exitSketch();
});

// ===================================================================== barra a schede (stile SolidCraft)
let schedaPrima = 'lamiera';
function showRibbon(t) {
  document.querySelectorAll('.rtabs button').forEach(b => b.classList.toggle('on', b.dataset.rtab === t));
  document.querySelectorAll('.rbody').forEach(b => { b.hidden = b.dataset.rbody !== t; });
}
$('#ribbon').addEventListener('click', ev => {
  const tab = ev.target.closest('.rtabs button');
  if (tab) { showRibbon(tab.dataset.rtab); if (tab.dataset.rtab !== 'sketch') schedaPrima = tab.dataset.rtab; return; }
  const b = ev.target.closest('.rb');
  if (!b || b.disabled) return;
  if (b.dataset.cmd) return;                         // ci pensa il gestore generale dei data-cmd
  if (!SK) return;
  if (b.id === 'rb-constr') { SK.constr = !SK.constr; drawSketch(); return; }
  if (b.id === 'rb-xray') { toggleXray(); return; }
  if (b.dataset.skdone) { exitSketch(); return; }
  if (b.dataset.act) { skAction(b.dataset.act); return; }
  if (b.dataset.tool) setTool(b.dataset.tool);
});
// la scheda giusta per il progetto aperto
// si vedono solo le schede che servono al progetto aperto (tutte se è ancora un disegno vuoto)
function ribbonTabs() {
  const assieme = S?.mode === 'assembly';
  document.querySelector('.rtabs [data-rtab="assieme"]').hidden = !assieme;
  if (assieme) {
    for (const k of ['lamiera', 'strutture', 'piastra']) document.querySelector(`.rtabs [data-rtab="${k}"]`).hidden = true;
    if (schedaPrima !== 'assieme' && !SK) { schedaPrima = 'assieme'; showRibbon('assieme'); }
    return { assieme: true };
  }
  if (schedaPrima === 'assieme') schedaPrima = 'lamiera';
  const usa = { lamiera: !!S?.sheet, strutture: !!(S?.cutlist?.rows?.length || nodes.length),
    piastra: !S?.sheet && JSON.stringify(S?.tree || {}).includes('"kind":"extrude"') };
  const nessuna = !Object.values(usa).some(Boolean);
  for (const [k, v] of Object.entries(usa)) document.querySelector(`.rtabs [data-rtab="${k}"]`).hidden = !(v || nessuna);
  if (!SK && document.querySelector(`.rtabs [data-rtab="${schedaPrima}"]`)?.hidden) {
    schedaPrima = Object.keys(usa).find(k => usa[k]) || 'lamiera';
    showRibbon(schedaPrima);
  }
  return usa;
}
function ribbonForProject() {
  if (SK) return;
  const usa = ribbonTabs();
  const t = Object.keys(usa).find(k => usa[k]) || (schedaPrima !== 'sketch' ? schedaPrima : 'lamiera');
  schedaPrima = t; showRibbon(t);
}
// ---------------------------------------------------------------- storia delle operazioni (timeline)
const ICONA_TIPO = { instance: 'box', mate: 'joint', assembly: 'joint', sketch: 'sketch', sheet: 'box', flange: 'flange', sheet_cut: 'cut', extrude: 'extrude', hole: 'hole', fillet: 'fillet',
  chamfer: 'chamfer', structure: 'joint', members: 'line', part: 'box', group: 'list', project: 'box' };
const iconImg = k => `<img src="icons/${ICONA_TIPO[k] || 'box'}.svg" alt="">`;
function renderTimeline() {
  const voci = [];
  const giro = n => {
    if (['sketch', 'sheet', 'flange', 'sheet_cut', 'extrude', 'hole', 'fillet', 'chamfer', 'structure'].includes(n.kind)) voci.push(n);
    if (n.kind !== 'structure') n.children.forEach(giro);
  };
  giro(S.tree);
  const selIds = new Set(sel ? (sel.ids || [sel.id]) : []);
  $('#tl-items').innerHTML = voci.map(n => {
    const id = n.kind === 'flange' ? 'flange=' + n.ref : n.kind === 'sketch' ? 'sketch=' + n.ref : n.kind === 'structure' ? 'st=' + n.ref : 'body';
    const cls = ['tl', n.status === 'errore' ? 'err' : '', selIds.has(id) && id !== 'body' ? 'sel' : ''].filter(Boolean).join(' ');
    return `<button class="${cls}" data-tl="${esc(id)}" title="${esc(n.label)}">${iconImg(n.kind)}</button>`;
  }).join('');
}
$('#tl-items').addEventListener('click', ev => {
  const b = ev.target.closest('[data-tl]');
  if (!b) return;
  const id = b.dataset.tl;
  if (id.startsWith('sketch=')) { enterSketch(id.slice(7)); return; }
  if (id.startsWith('st=')) { const ids = membersOf(id.slice(3)); if (ids.length) select(ids[0], null, ids); return; }
  select(id);
});
// ---------------------------------------------------------------- riga di comando: apre la palette
// ---------------------------------------------------------------- cubo delle viste: ruota con la camera
function placeCube() {
  const e = camera.matrixWorldInverse.elements;          // dal mondo alla vista (colonne)
  const R = (i, j) => e[j * 4 + i];
  const M = (i, j) => (i === 1 ? -R(i, j) : R(i, j));       // lo schermo ha la y in giù
  $('#cube').style.transform = `matrix3d(${M(0, 0)},${M(1, 0)},${M(2, 0)},0,${M(0, 1)},${M(1, 1)},${M(2, 1)},0,${M(0, 2)},${M(1, 2)},${M(2, 2)},0,0,0,0,1)`;
}
(function buildCube() {
  const h = 30;
  // per ogni faccia: normale, direzione "giù" del testo, nel mondo (Z in su)
  const F = { pz: [[0, 0, 1], [0, -1, 0]], nz: [[0, 0, -1], [0, 1, 0]], ny: [[0, -1, 0], [0, 0, -1]], py: [[0, 1, 0], [0, 0, -1]],
    px: [[1, 0, 0], [0, 0, -1]], nx: [[-1, 0, 0], [0, 0, -1]] };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  document.querySelectorAll('#cube .cf').forEach(el => {
    const [n, v] = F[el.dataset.f], u = cross(n, v);
    const t = [0, 1, 2].map(i => n[i] * h - u[i] * h - v[i] * h + (i < 2 ? h : 0));
    el.style.transformOrigin = '0 0';
    el.style.transform = `matrix3d(${u[0]},${u[1]},${u[2]},0,${v[0]},${v[1]},${v[2]},0,${n[0]},${n[1]},${n[2]},0,${t[0]},${t[1]},${t[2]},1)`;
    el.addEventListener('click', () => runCmd(el.dataset.view));
  });
  $('#cube').style.transformOrigin = `${h}px ${h}px 0`;
})();

// ===================================================================== avvio
async function start() {
  let tema = 'scuro';                              // scuro di partenza: pesa meno sugli occhi
  try { tema = localStorage.getItem('steelcad.tema') || 'scuro'; } catch { /* va bene il predefinito */ }
  applyTheme(tema === 'scuro');
  S = await call('state');
  renderPanels();
  await loadScene();
  setInterval(() => call('autosave'), 60000);
  const casa = await call('home_info');
  if (casa.ok && casa.show) await showHome(casa);
  requestAnimationFrame(loop);
  window.__steelcad = { ready: true, get state() { return S; }, get sceneVersion() { return sceneVersion; }, get nodes() { return nodes; }, get sketch() { return SK; },
    objs, select, camera, skScreen: xy => skScreen(xy), enterSketch, exitSketch, apply, toast, hideHome, THREE, get bendEdges() { return bendEdges; },
    get look() { return { model: model.visible, flat: flatGroup.visible, work: workGroup.visible && workGroup.children.length > 0 }; } };
}
// Diretta (?dev&live): uno script costruisce il progetto sul motore e qui si vede ogni passo
async function liveLoop() {
  for (;;) {
    let r;
    try { r = await call('live_next'); } catch (e) { await new Promise(ok => setTimeout(ok, 1000)); continue; }
    if (!r || !r.ok) { await new Promise(ok => setTimeout(ok, 500)); continue; }
    for (const ev of r.events) {
      try {
        if (ev.type === 'toast') toast(ev.text, ev.kind || '');
        else if (ev.type === 'refresh') {
          if (ev.nuovo) { primaVolta = true; clearSelection(); }
          if (SK && ev.sketch !== SK.sid) exitSketch();
          await apply({ ok: true, state: await call('state') });
          hideHome();
          if (ev.sketch && !SK) await enterSketch(ev.sketch);
          if (ev.key) document.dispatchEvent(new KeyboardEvent('keydown', { key: ev.key, bubbles: true }));
        }
      } catch (e) { console.error(e); }
    }
    await call('live_ack', r.n);
    if (r.end) break;
  }
}
if (DEV) { start(); if (new URLSearchParams(location.search).has('live')) setTimeout(liveLoop, 500); }
else if (window.pywebview?.api) start();
else window.addEventListener('pywebviewready', start, { once: true });
