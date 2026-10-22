// SteelCAD: interfaccia. Tutta la geometria arriva già calcolata dal motore (Python):
// qui si disegna, si seleziona e si mandano le modifiche. Niente calcoli di CAD in JS.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { Line2 } from './vendor/lines/Line2.js';
import { LineGeometry } from './vendor/lines/LineGeometry.js';
import { LineMaterial } from './vendor/lines/LineMaterial.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const DEV = new URLSearchParams(location.search).has('dev');
const num = (v, d = 1) => (v ?? 0).toLocaleString('it-IT', { maximumFractionDigits: d, minimumFractionDigits: 0 });
const kg = v => (v ?? 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// cosa dire mentre si aspetta (le chiamate che non sono qui: «Sto lavorando…»)
const ATTESA = {
  scene: 'Preparo il 3D…', open_path: 'Apro il progetto…', open_project_dialog: 'Apro il progetto…', save: 'Salvo…',
  asm_edit_mate: 'Ricalcolo l’assieme…', asm_trascina_mate: 'Sposto i pezzi…', asm_add_mate: 'Accoppio i pezzi…',
  asm_delete_mate: 'Ricalcolo l’assieme…', asm_move: 'Ricalcolo l’assieme…', asm_rotate: 'Ricalcolo l’assieme…',
  asm_insert: 'Inserisco il pezzo…', asm_insert_dialog: 'Inserisco il pezzo…', asm_insert_libreria: 'Preparo la viteria…',
  asm_interferences: 'Controllo le interferenze…', asm_open_part: 'Apro il pezzo…', asm_back: 'Torno all’assieme…',
  asm_set_finitura: 'Cambio la finitura…', asm_set_acquisto: 'Aggiorno la distinta…', asm_new_part: 'Preparo il pezzo nuovo…',
  create_from_sketch: 'Costruisco il pezzo…', add_flange: 'Piego…', edit_flange: 'Piego…', add_edge_dress: 'Raccordo gli spigoli…',
  import_step: 'Spiego lo STEP…', import_step_dialog: 'Spiego lo STEP…', import_dxf: 'Leggo il DXF…', import_dxf_dialog: 'Leggo il DXF…',
  export: 'Esporto…', export_drawings_dialog: 'Preparo le tavole…', drawing_preview: 'Preparo le tavole…', prepara: 'Preparo i file…',
  undo: 'Annullo…', redo: 'Rifaccio…', unfold: 'Spiego la lamiera…', fold_frames: 'Preparo l’animazione…',
};
let attesaN = 0, attesaTimer = null, attesaT0 = 0, attesaTick = null;
function attesaInizio(name) {
  attesaN++;
  if (attesaN > 1) return;
  attesaT0 = performance.now();
  clearTimeout(attesaTimer);
  attesaTimer = setTimeout(() => {                 // solo se dura più di un attimo: niente lampeggi
    const box = document.getElementById('attesa');
    if (!box || attesaN === 0) return;
    document.getElementById('att-cosa').textContent = ATTESA[name] || 'Sto lavorando…';
    box.hidden = false; document.body.classList.add('in-attesa');
    attesaTick = setInterval(() => {
      const s = (performance.now() - attesaT0) / 1000;
      document.getElementById('att-tempo').textContent = s >= 2 ? `${Math.floor(s)} s` : '';
    }, 250);
  }, 250);
}
function attesaFine() {
  attesaN = Math.max(0, attesaN - 1);
  if (attesaN) return;
  clearTimeout(attesaTimer); clearInterval(attesaTick);
  const box = document.getElementById('attesa');
  if (box) { box.hidden = true; document.getElementById('att-tempo').textContent = ''; }
  document.body.classList.remove('in-attesa');
}
async function call(name, ...args) {
  attesaInizio(name);
  try {
    if (!DEV) return await window.pywebview.api[name](...args);
    const r = await fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args) });
    return await r.json();
  } finally {
    attesaFine();
  }
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
const camera = new THREE.PerspectiveCamera(15, 1, 1, 1e7);   // prospettiva leggera: con 35° le gambe di un telaio sembravano aperte a ventaglio
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
const ING_MAT = new THREE.LineDashedMaterial({ color: 0x8A6A1F, dashSize: 6, gapSize: 4 });
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

const matOf = o => Array.isArray(o.mesh.material) ? o.mesh.material[0] : o.mesh.material;
// i pezzi attorno quando un pezzo si apre (o nasce) dall'assieme: si vedono in trasparenza, non si cliccano
const CTX_MAT = new THREE.MeshStandardMaterial({ color: 0x8FA3B8, metalness: 0.1, roughness: 0.7, transparent: true,
  opacity: 0.22, depthWrite: false });
const CTX_EDGE = new THREE.LineBasicMaterial({ color: 0x8FA3B8, transparent: true, opacity: 0.45 });
let ctxGeo = [];
function buildScene(sc) {
  for (const o of objs.values()) { o.mesh.geometry.dispose(); matOf(o).dispose(); o.lines.geometry.dispose(); }
  for (const g of ctxGeo) g.dispose();
  ctxGeo = [];
  model.clear(); objs.clear();
  for (const d of sc.objects) {
    if (d.kind === 'context') {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(d.positions, 3)); g.setIndex(d.indices); g.computeVertexNormals();
      const seg = [];
      for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
      const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
      const mesh = new THREE.Mesh(g, CTX_MAT), lines = new THREE.LineSegments(lg, CTX_EDGE);
      const pos = new THREE.Matrix4().set(...d.matrix);
      for (const o of [mesh, lines]) { o.matrixAutoUpdate = false; o.matrix.copy(pos); o.updateMatrixWorld(true); o.raycast = () => {}; }
      model.add(mesh, lines); ctxGeo.push(g, lg);
      continue;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(d.positions, 3));
    g.setIndex(d.indices);
    g.computeVertexNormals();
    const base = new THREE.Color(d.look?.color || (d.kind === 'body' ? 0xB7BFC8 : 0xA8B1BA));
    const mat = new THREE.MeshStandardMaterial({ color: base.clone(), metalness: d.look?.metal ?? 0.15, roughness: d.look?.rough ?? 0.55,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(g, mat);
    mesh.userData.id = d.id;
    const pos = d.matrix ? new THREE.Matrix4().set(...d.matrix) : null;      // istanza di un assieme: dove sta
    const seg = [];
    for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
    const lines = new THREE.LineSegments(lg, EDGE);
    const extra = [];
    if (d.marks?.length) {                            // marcature laser: chiare sui pezzi scuri, scure sui chiari
      const sm = [];
      for (const e of d.marks) for (let i = 0; i + 5 < e.length; i += 3) sm.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
      const mg = new THREE.BufferGeometry(); mg.setAttribute('position', new THREE.Float32BufferAttribute(sm, 3));
      const hsl = base.getHSL({});
      extra.push(new THREE.LineSegments(mg, new THREE.LineBasicMaterial({ color: hsl.l < 0.45 ? 0xE5E7EB : 0x1F2937 })));
    }
    if (pos) for (const o of [mesh, lines, ...extra]) { o.matrixAutoUpdate = false; o.matrix.copy(pos); o.updateMatrixWorld(true); }
    model.add(mesh, lines, ...extra);
    objs.set(d.id, { data: d, mesh, lines, base, pos, extra });
  }
  if (ESPLOSO > 0) esplodi(ESPLOSO);
  paint();
}

// ---- vista esplosa: ogni pezzo spostato dal centro dell'assieme in proporzione (solo a video, l'assieme non cambia)
let ESPLOSO = 0;
function esplodi(f) {
  ESPLOSO = f;
  const ist = [...objs.values()].filter(o => o.data.kind === 'instance' && o.pos);
  if (!ist.length) return;
  const centri = ist.map(o => { o.mesh.geometry.computeBoundingBox(); return o.mesh.geometry.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(o.pos); });
  const C = centri.reduce((a, b) => a.add(b), new THREE.Vector3()).multiplyScalar(1 / centri.length);
  ist.forEach((o, i) => {
    const d = centri[i].clone().sub(C).multiplyScalar(f);
    const M = new THREE.Matrix4().makeTranslation(d.x, d.y, d.z).multiply(o.pos);
    for (const x of [o.mesh, o.lines, ...(o.extra || [])]) { x.matrix.copy(M); x.updateMatrixWorld(true); }
  });
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
    matOf(o).color.copy(c);
    matOf(o).emissive.setRGB(c === o.base ? 0 : 0.08, c === o.base ? 0 : 0.06, 0);
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
// ---- raccordo / smusso sugli spigoli del pezzo (piastre, pezzi pieni): si cliccano gli spigoli, poi Invio
let DRESS = null;
const DRESS_MAT = new THREE.LineBasicMaterial({ color: 0xFFB000, depthTest: false });
const DRESS_HOV = new THREE.LineBasicMaterial({ color: 0x4EA1FF, depthTest: false });
function dressTool(kind) {
  if (DRESS?.group) model.remove(DRESS.group);
  DRESS = kind ? { kind, scelti: [], hover: null, group: new THREE.Group() } : null;
  if (DRESS) model.add(DRESS.group);
  $('#sk-foot').hidden = !DRESS;
  if (DRESS) dressHelp(); else setHelp('');
  paint();
}
function dressHelp() {
  const n = DRESS.scelti.length, nome = DRESS.kind === 'fillet' ? 'Raccordo' : 'Smusso';
  setHelp(`${nome}: clic sugli spigoli da ${DRESS.kind === 'fillet' ? 'arrotondare' : 'smussare'} (si accendono)` +
    (n ? ` · ${n} scelt${n === 1 ? 'o' : 'i'}: Invio per la misura` : '') + ' · Esc annulla');
}
function pickBodyEdge(ev) {                          // lo spigolo del pezzo sotto il mouse, e il punto più vicino
  const o = objs.get('body');
  if (!o) return null;
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const scr = p => { const q = p.clone().project(camera); return [(q.x + 1) / 2 * r.width, (1 - q.y) / 2 * r.height]; };
  let best = null;
  o.data.edges.forEach((e, k) => {
    for (let i = 0; i + 5 < e.length; i += 3) {
      const A = new THREE.Vector3(e[i], e[i + 1], e[i + 2]), B = new THREE.Vector3(e[i + 3], e[i + 4], e[i + 5]);
      const a = scr(A), b = scr(B), dx = b[0] - a[0], dy = b[1] - a[1], LL = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((mx - a[0]) * dx + (my - a[1]) * dy) / LL));
      const d = Math.hypot(mx - a[0] - t * dx, my - a[1] - t * dy);
      if (d > 8 || (best && d >= best.d)) continue;
      const P = A.clone().lerp(B, t), dir = P.clone().sub(camera.position), dist = dir.length();
      ray.set(camera.position, dir.normalize());
      const hit = ray.intersectObjects([o.mesh], false)[0];
      if (hit && hit.distance < dist - 0.5) continue;  // dietro al pezzo
      best = { k, d, p: [P.x, P.y, P.z] };
    }
  });
  return best;
}
function dressDraw() {
  DRESS.group.clear();
  const o = objs.get('body');
  const linea = (k, mat) => {
    const e = o.data.edges[k], pts = [];
    for (let i = 0; i + 2 < e.length; i += 3) pts.push(new THREE.Vector3(e[i], e[i + 1], e[i + 2]));
    DRESS.group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
  };
  for (const c of DRESS.scelti) linea(c.k, DRESS_MAT);
  if (DRESS.hover != null && !DRESS.scelti.some(c => c.k === DRESS.hover)) linea(DRESS.hover, DRESS_HOV);
  paint();
}
function dressMove(ev) {
  const h = pickBodyEdge(ev);
  const k = h ? h.k : null;
  if (k !== DRESS.hover) { DRESS.hover = k; dressDraw(); }
}
function dressClick(ev) {
  const h = pickBodyEdge(ev);
  if (!h) { toast('Clicca proprio su uno spigolo (si accende in blu).', 'err'); return; }
  const i = DRESS.scelti.findIndex(c => c.k === h.k);
  if (i >= 0) DRESS.scelti.splice(i, 1); else DRESS.scelti.push(h);
  dressHelp(); dressDraw();
}
function dressFine() {
  if (!DRESS?.scelti.length) { toast('Scegli almeno uno spigolo.', 'err'); return; }
  const kind = DRESS.kind, punti = DRESS.scelti.map(c => c.p), ultimo = DRESS.ultimo || (kind === 'fillet' ? '5' : '1');
  modal(`<h3>${kind === 'fillet' ? 'Raccordo' : 'Smusso'} su ${punti.length} spigol${punti.length === 1 ? 'o' : 'i'}</h3>
    <div class="form"><label>${kind === 'fillet' ? 'Raggio' : 'Misura (a 45°)'}<span class="inp"><input class="field" id="dr-v" value="${esc(ultimo)}"><i>mm</i></span></label><span></span></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fatto</button></div>`, close => {
    $('#m-no').onclick = close;
    const vai = () => {
      const v = $('#dr-v').value.trim(); close();
      dressTool(null);
      inCoda(async () => { const r = await call('add_edge_dress', kind, punti, v); await apply(r, r.message); });
    };
    $('#m-ok').onclick = vai;
    $('#dr-v').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
    $('#dr-v').select();
  });
}
// piega sul bordo laterale di una parete: altezza, angolo, verso dentro/fuori. Nuova (dal bordo cliccato) o già fatta
let ultimaBordo = { length: '20', angle: '90', direction: 'up' };
function pannelloPiegaBordo(e, fatta = null) {
  const libero = fatta ? fatta.kind === 'edgeflange' : e.kind === 'libero';
  const [flange, end] = libero ? [null, null] : (fatta ? [fatta.flange, fatta.end] : e.ref.split('/'));
  const feature = fatta ? fatta.feature : e.feature;
  const d = fatta ? fatta.def : ultimaBordo;
  $('#props').innerHTML = `<h3>${fatta ? 'Piega sul bordo' : 'Piega su questo bordo'}</h3>
    <p class="hint" style="margin:6px 0">${libero ? 'Altezza fuori tutto dallo spigolo esterno; la piega parte dal bordo.'
      : 'Verso dentro a 90°: la parete che pieghi dopo su quel lato sale e resta dentro (gioco 0,2 mm).'}</p>
    ${flangeFields(d, VERSI_PUNTA, POS_UI)}
    ${libero ? `<div class="ff"><label>Gioco all’inizio<span class="inp"><input class="field" id="f-t0" value="${esc(String(d.trim0 ?? '').replace('.', ','))}" placeholder="auto"><i>mm</i></span></label>
      <label>Gioco alla fine<span class="inp"><input class="field" id="f-t1" value="${esc(String(d.trim1 ?? '').replace('.', ','))}" placeholder="auto"><i>mm</i></span></label></div>
      <p class="hint" style="margin:2px 0 6px">Vuoto: se la piega tocca un’altra parete si accorcia da sola in quell’angolo.</p>` : ''}
    <div class="row-btns"><button class="btn primary" id="f-add">${fatta ? 'Cambia' : 'Aggiungi piega'}</button></div>
    ${fatta ? '<div class="fp-fine"><button class="link danger" id="f-del" title="Canc">Togli questa piega</button></div>' : ''}`;
  $('#f-pos').closest('.seg-row').style.display = 'none';      // «Misura» qui non serve
  const vai = () => {
    const f = readFlange();
    if (libero) { f.trim0 = $('#f-t0').value.trim(); f.trim1 = $('#f-t1').value.trim(); }
    if (!fatta) ultimaBordo = f;
    inCoda(async () => {
      const r = libero ? (fatta ? await call('edit_edge_flange', feature, f) : await call('add_edge_flange', e.face, e.ea, e.eb, f))
        : await call('set_ear', feature, flange, end, true, f);
      if (await apply(r) && r.select) await select(r.select);
    });
  };
  $('#f-add').onclick = vai;
  ['#f-len', '#f-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  if (fatta) $('#f-del').onclick = () => (libero ? confermaElimina('sheet_edge_flange', feature, 'Piega sul bordo')
    : confermaElimina('flange', `${feature}/${flange}/${end}`, 'Piega sul bordo'));
  else { $('#f-len').focus(); $('#f-len').select(); }
}
function selectEdge(e) {
  selTok++; selGen++;
  sel = { id: 'edge=' + e.id };
  hover = null;
  aggiornaLayout();
  paint(); renderTree(); paintNodes();
  if (e.kind === 'side' || e.kind === 'libero') { pannelloPiegaBordo(e); return; }
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
  if (SK && ev.button === 0 && ((SK.tool === 'select' && !SK.pick) || SK.pick?.stage === 'sel')) SK.box = { x: ev.clientX, y: ev.clientY };
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
  // un tratto taglia il riquadro? (un estremo dentro, oppure attraversa uno dei quattro lati)
  const incrocia = (p, q, r1, r2) => {
    const d = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    return d(p, q, r1) * d(p, q, r2) <= 0 && d(r1, r2, p) * d(r1, r2, q) <= 0;
  };
  const angoli = [[X0, Y0], [X1, Y0], [X1, Y1], [X0, Y1]];
  const taglia = (p, q) => dentro(p) || dentro(q) || angoli.some((c, i) => incrocia(p, q, c, angoli[(i + 1) % 4]));
  // spezzata a video: da sinistra a destra va presa tutta dentro, da destra a sinistra basta che un tratto tocchi
  const prendi = (id, pts) => {
    const ok = tocca ? pts.some((p, i) => i > 0 && taglia(pts[i - 1], p)) : pts.every(dentro);
    if (ok) SK.sel.add(id);
  };
  const giro = (centro, r, a0, a1, n) => {
    const ctr = skToLocal(v3(centro));
    return Array.from({ length: n + 1 }, (_, k) => {
      const t = a0 + (a1 - a0) * k / n;
      return scr(skToWorld([ctr[0] + r * Math.cos(t), ctr[1] + r * Math.sin(t)]));
    });
  };
  if (!ev.shiftKey && SK.pick?.stage !== 'sel') SK.sel.clear();   // scegliendo per Copia/Sposta la finestra aggiunge
  for (const l of SK.v.lines) prendi(l.id, [scr(l.pa), scr(l.pb)]);
  for (const c of SK.v.circles) prendi(c.id, giro(c.center, c.r, 0, 2 * Math.PI, 32));
  // archi: i mezzi tondi delle asole e i raccordi (prima la finestra non li prendeva mai)
  for (const a of SK.v.arcs) prendi(a.id, giro(a.center, a.r, a.a0, a.a1, 16));
  drawSketch();
});
canvas.addEventListener('pointermove', ev => {
  if (SK) { skMove(ev); return; }
  if (MIS && !ev.buttons) { misMove(ev); return; }
  if (DRESS && !ev.buttons) { dressMove(ev); return; }
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
  if (MIS) { misClick(ev); return; }
  if (DRESS) { dressClick(ev); return; }
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
function fitBox(box, dir, keepDir = false, subito = false) {
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
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || primaVolta || subito) {
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
// pieno (21/10: trasparente, la griglia sotto ci si mischiava e faceva i quadretti); spinto un filo indietro, così le
// linee del disegno che stanno sullo stesso piano restano sempre davanti
const FLAT_FILL = new THREE.MeshBasicMaterial({ color: 0xB7C2CD, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
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
  // più pezzi (le forme divise in pezzi): ogni contorno che non sta dentro un altro è un pezzo, quelli dentro sono fori
  const dentro = (p, q) => { let c = false; for (let i = 0, j = q.length - 1; i < q.length; j = i++) if ((q[i].y > p.y) !== (q[j].y > p.y) && p.x < (q[j].x - q[i].x) * (p.y - q[i].y) / (q[j].y - q[i].y) + q[i].x) c = !c; return c; };
  const ordine = anelli.map((l, i) => i).sort((a, b) => Math.abs(area(anelli[b])) - Math.abs(area(anelli[a])));
  const pezzi = [];
  for (const i of ordine) {
    const l = anelli[i];
    const fuori = [...pezzi].reverse().find(f => dentro(l[0], f.anello));
    if (fuori && !fuori.foro) fuori.forma.holes.push(new THREE.Path(l));
    else pezzi.push({ anello: l, forma: new THREE.Shape(l), foro: false });
  }
  for (const p of pezzi) flatGroup.add(new THREE.Mesh(new THREE.ShapeGeometry(p.forma), FLAT_FILL));
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
  if (threadGroup) threadGroup.visible = !piatto && !solo;
  svasatureKo.visible = !piatto && !solo;
  workGroup.visible = !!(SK && SK.v.on_face);
  const fantasma = !SK ? 1 : solo ? (SK.ghost ? 0.15 : 0) : 0.18;
  model.visible = !piatto || (SK && SK.ghost) ? fantasma > 0 : false;
  for (const o of objs.values()) {
    matOf(o).transparent = fantasma < 1; matOf(o).opacity = fantasma; matOf(o).depthWrite = fantasma >= 1;
  }
  dimLines.visible = SK ? true : !piatto;
  edgeGroup.visible = !SK && !piatto;
  dimsBox.style.display = !SK && piatto ? 'none' : '';
  nodesBox.style.display = SK || piatto ? 'none' : '';
  $('#b-unfold').hidden = !S?.sheet?.data;
  $('#b-unfold').classList.toggle('on', flatView);
  $('#b-unfold').textContent = flatView ? 'Ripiega' : 'Spiega';
  $('#flat-bar').hidden = !(flatView && !SK);
  $('#flat-bar [data-cmd="flat_sketch"]')?.toggleAttribute('hidden', !!S?.sheet?.shape);   // coni e raccordi: niente disegno sullo sviluppo
  $('#sk-ghost').hidden = !solo;
  $('#sk-ghost').classList.toggle('on', !!SK?.ghost);
  ridisegna();
}
// Spiega / Ripiega con l'animazione: il pezzo si apre sulle sue pieghe (passi calcolati dal motore), poi lo sviluppo
async function animaPiega(apri) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const o = objs.get('body');
  if (!o) return;
  const r = await call('fold_frames', 5);
  if (!r.ok || !r.frames?.length) return;
  const g = new THREE.Group();
  g.matrixAutoUpdate = false; g.matrix.copy(model.matrixWorld);
  scene.add(g);
  const passi = r.frames.map(f => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.positions, 3));
    geo.setIndex(f.indices); geo.computeVertexNormals();
    const m = new THREE.Mesh(geo, o.mesh.material); m.visible = false; g.add(m); return m;
  });
  const vediModello = model.visible, vediSviluppo = flatGroup.visible;
  model.visible = false; flatGroup.visible = false;
  for (const m of apri ? passi : [...passi].reverse()) {
    m.visible = true; ridisegna();
    await new Promise(res => setTimeout(res, 110));
    m.visible = false;
  }
  scene.remove(g); passi.forEach(m => m.geometry.dispose());
  model.visible = vediModello; flatGroup.visible = vediSviluppo;
}
async function toggleFlat(on = !flatView, anima = false) {   // animazione spenta (21/10: troppo lenta, «era meglio prima»)
  if (SK) return;
  if (on && !S?.sheet?.data) { toast('Lo sviluppo c’è quando la lamiera è costruita: guarda la scheda Lamiera.', 'err'); return; }
  if (on) { clearSelection(); if (anima) await animaPiega(true); }
  else if (anima) {                                   // si ripiega guardandolo di sbieco, se no dall'alto non si vede salire
    goTo(VISTE.view_iso);
    await new Promise(res => setTimeout(res, 280));
    flatView = false; applyLook();
    await animaPiega(false);
  }
  flatView = on;
  if (on) buildFlat();
  applyLook();
  if (on) fitBox(flatBox(), v3(S.sheet.data.plane.z).add(new THREE.Vector3(0, -0.0001, 0)));
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
// i fori filettati si vedono filettati: al posto della parete liscia del preforo una superficie a spirale col passo
// della filettatura, dal preforo (cresta) al diametro nominale (fondo). Solo a video: il pezzo per il laser resta col
// preforo, il filetto si fa col maschio.
const HIDE_MAT = new THREE.MeshBasicMaterial({ visible: false });
let threadGroup = null;
let markGroup = null;
const MARK_MAT = new THREE.LineBasicMaterial({ color: 0x5B21B6 });
function buildMarks(list) {                         // marcature laser: i tratti sopra la faccia
  if (markGroup) { markGroup.traverse(o => o.geometry?.dispose()); model.remove(markGroup); }
  markGroup = new THREE.Group();
  for (const s of list || []) markGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(s.map(q => new THREE.Vector3(...q))), MARK_MAT));
  model.add(markGroup);
}
function buildThreads(list) {
  if (threadGroup) { threadGroup.traverse(o => { o.geometry?.dispose(); }); model.remove(threadGroup); }
  threadGroup = new THREE.Group();
  const body = objs.get('body');
  if (body && list?.length) {                       // la parete liscia del foro non si disegna (si clicca ancora)
    const nascoste = new Set(list.flatMap(t => t.faces || []));
    const g = body.mesh.geometry; g.clearGroups();
    const fs = [...body.data.faces].sort((a, b) => a.start - b.start);
    for (const f of fs) g.addGroup(f.start, f.count, nascoste.has(f.index) ? 1 : 0);
    if (!Array.isArray(body.mesh.material)) body.mesh.material = [body.mesh.material, HIDE_MAT];  // matOf() dà il primo
  }
  for (const t of list || []) {
    const c = new THREE.Vector3(...t.c), n = new THREE.Vector3(...t.n).normalize();
    const a = Math.abs(n.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
    const u = a.clone().cross(n).normalize(), w = n.clone().cross(u).normalize();
    const NA = 48, P = t.passo || 1, NZ = Math.min(4000, Math.max(8, Math.ceil(t.len / P * 10)));
    const pos = [], idx = [];
    for (let j = 0; j <= NZ; j++) {
      const z = 0.05 + (t.len - 0.1) * j / NZ;      // appena dentro: sulla faccia non si vede l'anello del filetto
      for (let i = 0; i <= NA; i++) {
        const g = i / NA * Math.PI * 2;
        const fr = ((z / P - i / NA) % 1 + 1) % 1, tri = 1 - Math.abs(2 * fr - 1);
        const vic = Math.min(1, z / P, (t.len - z) / P);  // all'imbocco e in fondo il filetto si chiude sul preforo
        const r = t.r0 + (t.r - t.r0) * tri * vic;
        const p = c.clone().addScaledVector(n, z).addScaledVector(u, r * Math.cos(g)).addScaledVector(w, r * Math.sin(g));
        pos.push(p.x, p.y, p.z);
      }
    }
    for (let j = 0; j < NZ; j++) for (let i = 0; i < NA; i++) {
      const k = j * (NA + 1) + i;
      idx.push(k, k + 1, k + NA + 1, k + 1, k + NA + 2, k + NA + 1);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setIndex(idx); geo.computeVertexNormals();
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xB7BFC8, metalness: 0.15, roughness: 0.55, side: THREE.DoubleSide }));
    m.raycast = () => {};                            // si clicca la parete del foro (nascosta), non la spirale
    threadGroup.add(m);
  }
  model.add(threadGroup);
}
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
    el.className = 'dim' + (d.type === 'diameter' || d.type === 'radius' ? ' dia' : '') + (d.driven ? ' rif' : '');
    el.innerHTML = (d.param ? `<span class="p">${esc(d.param)}</span>` : '') + esc(d.label);
    el.title = d.driven ? 'Quota di riferimento: la misura la decide il pezzo (si aggiorna da sola)'
      : d.param ? `Quota legata al parametro ${d.param}: clicca per cambiarla` : 'Clicca per cambiare la quota';
    el.addEventListener('click', ev => { ev.stopPropagation(); if (d.driven) toast(el.title); else editDim(el, d); });
    dimsBox.appendChild(el);
    // il diametro va sul bordo del cerchio, non al centro: se no la scritta copre il foro
    dimEls.push({ el, d, at: d.type === 'diameter' || d.type === 'radius' ? pb.clone() : pa.clone().add(pb).multiplyScalar(0.5) });
  }
  if (!SK) quoteIngombro();
  placeDims();
  ridisegna();
}
// l'ingombro totale del pezzo (o dell'assieme): tre quote sugli spigoli della scatola che lo contiene, lungo X, Y e Z
function quoteIngombro() {
  const box = new THREE.Box3();
  model.updateMatrixWorld(true);
  model.traverse(o => { if (o.isMesh && o.visible && o.geometry) box.expandByObject(o); });
  if (box.isEmpty()) return;
  const mn = box.min, mx = box.max, sz = box.getSize(new THREE.Vector3());
  const off = Math.max(30, box.getBoundingSphere(new THREE.Sphere()).radius * 0.16);
  const lati = [
    // misura, da, a, verso cui si sposta la quota
    [sz.x, new THREE.Vector3(mn.x, mn.y, mn.z), new THREE.Vector3(mx.x, mn.y, mn.z), new THREE.Vector3(0, -1, 0), 'larghezza (X)'],
    [sz.y, new THREE.Vector3(mx.x, mn.y, mn.z), new THREE.Vector3(mx.x, mx.y, mn.z), new THREE.Vector3(1, 0, 0), 'profondità (Y)'],
    [sz.z, new THREE.Vector3(mn.x, mn.y, mn.z), new THREE.Vector3(mn.x, mn.y, mx.z), new THREE.Vector3(-1, -1, 0).normalize(), 'altezza (Z)'],
  ];
  for (const [mis, a, b, dir, nome] of lati) {
    if (mis < 0.05) continue;
    const pa = a.clone().addScaledVector(dir, off), pb = b.clone().addScaledVector(dir, off);
    const g = new THREE.BufferGeometry().setFromPoints([a, a.clone().addScaledVector(dir, off * 1.1), b, b.clone().addScaledVector(dir, off * 1.1), pa, pb]);
    dimLines.add(new THREE.LineSegments(g, ING_MAT).computeLineDistances());
    const el = document.createElement('div');
    el.className = 'dim ing';
    el.textContent = num(Math.round(mis * 10) / 10);
    el.title = `Ingombro totale, ${nome}: ${num(Math.round(mis * 10) / 10)} mm`;
    el.addEventListener('click', ev => { ev.stopPropagation(); toast(el.title); });
    dimsBox.appendChild(el);
    dimEls.push({ el, d: null, at: pa.clone().add(pb).multiplyScalar(0.5) });
  }
}
function placeDims() {
  const w = view.clientWidth, h = view.clientHeight;
  for (const { el, at } of [...dimEls, ...nodeEls, ...(misEls || [])]) {
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
      inCoda(async () => {
        if (!await apply(await call('set_dimension', d.sketch, d.dim, v))) { buildDims(); return; }
        if (SK && SK.v.points.some(q => { const p = v3(q.xyz).project(camera); return Math.abs(p.x) > 0.95 || Math.abs(p.y) > 0.95; })) fitSketch();
      });
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
    if (S.scene_version !== sceneVersion && S.mode === 'assembly' && S.geo && S.geo === geoCaricata && S.poses) {
      spostaPezzi(S.poses);                         // si è mosso solo qualcosa: niente scena intera
      sceneVersion = S.scene_version;
    } else if (S.scene_version !== sceneVersion) await loadScene();
    else buildDims();
    if (SK) await refreshSketch();
  }
  if (okMsg || res.message) toast(okMsg || res.message);
  return true;
}

let geoCaricata = null;
function spostaPezzi(pose) {                        // le copie dell'assieme al loro posto nuovo, senza ridisegnarle
  for (const [id, m] of Object.entries(pose || {})) {
    const o = objs.get(id);
    if (!o) continue;
    o.pos = new THREE.Matrix4().set(...m);
    o.data.matrix = m;
    for (const x of [o.mesh, o.lines, ...(o.extra || [])]) { x.matrix.copy(o.pos); x.updateMatrixWorld(true); }
  }
  if (ESPLOSO > 0) esplodi(ESPLOSO); else paint();
}
async function loadScene() {
  attesaInizio('scene');
  try { await caricaScena(); } finally { attesaFine(); }
}
async function caricaScena() {
  const sc = await call('scene');
  if ((sc.objects || []).length > 30) {             // tanti pezzi: l'attesa si vede subito, poi si costruisce
    document.getElementById('att-cosa').textContent = 'Preparo il 3D…';
    document.getElementById('attesa').hidden = false; document.body.classList.add('in-attesa');
    await new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
  }
  geoCaricata = S?.mode === 'assembly' ? S.geo : null;
  sceneVersion = sc.version;
  const eraVuota = objs.size === 0;
  const raggio = () => new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere()).radius;
  const prima = eraVuota ? 0 : raggio();
  buildScene(sc);
  buildThreads(sc.threads);
  buildSvasatureKo(sc.svasature_ko);
  buildMarks(sc.marks);
  nodes = sc.nodes || [];
  bendEdges = sc.bend_edges || [];
  hoverEdge = null;
  modelRadius = new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere()).radius || 100;
  if (primaVolta || (eraVuota && objs.size)) { goTo(VISTE.view_iso); primaVolta = !objs.size && primaVolta; ribbonForProject(); }
  else if (objs.size && raggio() > prima * 1.15) goTo(null, true);   // il modello è cresciuto: si riadatta
  buildDims();
  buildNodes();
  aggiornaComandi();                 // i comandi dipendono anche da nodi e pezzi della scena
  if (flatView || SK?.v.on_flat) { if (!buildFlat()) flatView = false; }
  if (MIS) MIS.cand = misCandidati();
  disegnaMisure();
  if (SK?.v.on_face) buildWorkFace(SK.v.on_face);
  applyLook();
  const esiste = id => objs.has(id) || nodes.some(n => n.id === id) || id.startsWith('flange=') || id.startsWith('pb=');
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
  renderTop(); renderTree(); renderParams(); renderBottom(); renderSheet(); aggiornaComandi();
  aggiornaLayout();
  if (!sel && !SK) $('#props').innerHTML = '';
}
// il pannello a destra si apre solo quando c'è qualcosa di selezionato (le proprietà); i comandi stanno nella barra in alto
function aggiornaLayout() {
  const chiuso = !sel || !!SK;
  if (document.body.classList.contains('senza-destra') === chiuso) return;
  document.body.classList.toggle('senza-destra', chiuso);
  requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
}

function renderTop() {
  const nome = esc(S.name || 'Senza nome');
  const bp = $('#b-prepara');
  const vuoto = !S.tree?.children?.length && !S.cutlist?.rows?.length && S.mode !== 'assembly';
  bp.hidden = vuoto;
  bp.textContent = S.mode === 'assembly' || (S.cutlist?.rows?.length && !S.sheet) ? 'Prepara per l’officina' : 'Prepara per il laser';
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
    const ids = n.kind === 'members' ? n.ref : n.kind === 'structure' ? ['struct=' + n.ref]
      : n.kind === 'flange' ? ['flange=' + n.ref] : n.kind === 'sheet_edge_flange' ? ['pb=' + n.ref] : n.kind === 'sheet_miter' ? ['tt=' + n.ref]
      : n.kind === 'sketch' ? ['sketch=' + n.ref]
      : n.kind === 'instance' ? [n.ref] : n.kind === 'mate' ? ['mate=' + n.ref] : n.kind === 'assembly' ? ['assieme']
      : ['part', 'extrude', 'hole', 'fillet', 'chamfer', 'sheet'].includes(n.kind) ? ['body'] : null;
    const cls = ['node', n.kind === 'project' ? 'root' : '', n.kind === 'group' ? 'group' : '', n.status === 'disattivata' ? 'spenta' : '',
      ids && ids.length ? 'clickable' : '', n.status === 'errore' ? 'err' : '',
      ids && ids.length && ids.every(i => selIds.has(i)) && n.kind !== 'structure' && !(n.kind !== 'part' && ids[0] === 'body') ? 'sel' : ''];
    const st = n.status && n.status !== 'errore' ? `<span class="st">${esc(n.status)}</span>` : '';
    const data = (ids && ids.length ? ` data-ids="${esc(ids.join(','))}"` : '') + (n.ref && typeof n.ref === 'string' ? ` data-kind="${esc(n.kind)}" data-ref="${esc(n.ref)}"` : '');
    const figli = n.children.length ? `<ul>${n.children.map(nodo).join('')}</ul>` : '';
    return `<li><div class="${cls.filter(Boolean).join(' ')}"${data} title="${esc(n.label)}"><span class="k">${iconImg(n.kind)}</span>${esc(n.label)}${st}</div>${figli}</li>`;
  };
  $('#tree').innerHTML = `<ul>${nodo(S.tree)}</ul>`;
}
// tasto destro su una voce dell'albero: modifica, rinomina, disattiva, elimina, perché è rossa (21/10)
const VOCI_MENU = { modifica: 'Modifica', rinomina: 'Rinomina…', serie: 'Ripeti in serie…', disattiva: 'Disattiva (non farla, senza cancellarla)',
  attiva: 'Attiva', elimina: 'Elimina…', perche: 'Perché è rossa?' };
// Elimina con la conferma: cosa sparisce insieme (i disegni sopra, i tagli che li usano), poi tutto in un colpo
async function confermaElimina(kind, ref, titolo, dip = null) {
  if (dip === null) { const m = await call('tree_menu', kind, ref); dip = m.ok ? (m.dipendenti || []) : []; }
  modal(`<h3>Elimina</h3><p>${esc(titolo)}</p>
    ${dip.length ? `<p class="hint" style="color:var(--warn)">Spariscono anche ${dip.length === 1 ? 'questa voce, che la usa' : `queste ${dip.length} voci, che la usano`}:</p><ul class="lista-dip">${dip.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : ''}
    <p class="hint">Si può tornare indietro con Annulla (Ctrl+Z).</p>
    <div class="acts"><button class="btn" id="m-no">No</button><button class="btn danger" id="m-ok">Elimina${dip.length ? ` (${dip.length + 1})` : ''}</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => { close(); clearSelection(); inCoda(async () => { const r2 = await call('tree_action', kind, ref, 'elimina'); await apply(r2, r2.message); }); };
  });
}
function chiudiMenuAlbero() { document.getElementById('menu-albero')?.remove(); }
$('#tree').addEventListener('contextmenu', ev => {
  const n = ev.target.closest('.node[data-ref]');
  if (!n || S?.mode === 'assembly') return;
  ev.preventDefault();
  chiudiMenuAlbero();
  const kind = n.dataset.kind, ref = n.dataset.ref, titolo = n.title;
  inCoda(async () => {
    const m = await call('tree_menu', kind, ref);
    if (!m.ok) { toast(m.message, 'err'); return; }
    const box = document.createElement('div');
    box.id = 'menu-albero'; box.className = 'menu-albero';
    box.innerHTML = m.voci.map(v => `<button data-v="${v}"${v === 'elimina' ? ' class="danger"' : ''}>${VOCI_MENU[v]}</button>`).join('');
    document.body.appendChild(box);
    const r = box.getBoundingClientRect();
    box.style.left = Math.min(ev.clientX, innerWidth - r.width - 8) + 'px';
    box.style.top = Math.min(ev.clientY, innerHeight - r.height - 8) + 'px';
    box.onclick = e => {
      const v = e.target.closest('button')?.dataset.v;
      if (!v) return;
      chiudiMenuAlbero();
      if (v === 'modifica') { if (m.sketch) enterSketch(m.sketch); else if (m.seleziona) select(m.seleziona); return; }
      if (v === 'perche') { toast(m.errore, 'err'); return; }
      if (v === 'rinomina') {
        modal(`<h3>Rinomina</h3><div class="form"><label style="grid-column:1/-1">Nome<input class="field" id="rn-n" value="${esc(m.nome || '')}" placeholder="${esc(titolo)}"></label></div>
          <p class="hint">Vuoto = il nome che dà il programma.</p>
          <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Rinomina</button></div>`, close => {
          $('#m-no').onclick = close;
          $('#m-ok').onclick = () => { const nome = $('#rn-n').value; close(); inCoda(async () => apply(await call('tree_action', kind, ref, 'rinomina', nome))); };
          $('#rn-n').focus(); $('#rn-n').select();
          $('#modal-box').onkeydown = e2 => { if (e2.key === 'Enter') $('#m-ok').click(); if (e2.key === 'Escape') close(); };
        });
        return;
      }
      if (v === 'elimina') { confermaElimina(kind, ref, titolo, m.dipendenti || []); return; }
      if (v === 'serie') {
        modal(`<h3>Ripeti in serie</h3><p class="hint">${esc(titolo)}: tutto il suo disegno ripetuto a griglia, originale compreso. Colonne lungo X e righe lungo Y del disegno (X verso destra, Y verso l’alto guardando la faccia). I passi diventano misure (px, py) che cambi dopo.</p>
          <div class="form"><label>Colonne<input class="field" id="se-c" value="3"></label><label>Passo X<span class="inp"><input class="field" id="se-px" value="50"><i>mm</i></span></label>
          <label>Righe<input class="field" id="se-r" value="1"></label><label>Passo Y<span class="inp"><input class="field" id="se-py" value="50"><i>mm</i></span></label></div>
          <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Ripeti</button></div>`, close => {
          $('#m-no').onclick = close;
          $('#m-ok').onclick = () => { const v = ['#se-c', '#se-px', '#se-r', '#se-py'].map(q => $(q).value.trim()); close();
            inCoda(async () => { const r2 = await call('feature_serie', ref, ...v); await apply(r2, r2.message); }); };
          $('#modal-box').onkeydown = e2 => { if (e2.key === 'Enter') $('#m-ok').click(); if (e2.key === 'Escape') close(); };
        });
        return;
      }
      inCoda(async () => apply(await call('tree_action', kind, ref, v)));   // disattiva / attiva
    };
  });
});
document.addEventListener('pointerdown', ev => { if (!ev.target.closest('#menu-albero')) chiudiMenuAlbero(); });
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') chiudiMenuAlbero(); });
function membersOf(stId) { return [...objs.keys()].filter(k => k.startsWith(stId + '/')); }
$('#tree').addEventListener('click', ev => {
  const n = ev.target.closest('.node.clickable');
  if (!n) return;
  const ids = n.dataset.ids.split(',');
  if (ids[0].startsWith('sketch=')) { enterSketch(ids[0].slice(7)); return; }
  select(ids[0], null, ids.length > 1 ? ids : null);
});

// le misure del progetto: la sigla (W, sp…) con il nome in chiaro. Se il progetto nasce da un modello
// (cancello, cono…) le misure si cambiano dal riquadro del modello a destra: qui restano tra le avanzate.
let eraModello = null;
function renderParams() {
  const righe = S.parameters.map(p => {
    const espr = typeof p.value === 'string';
    const nome = p.label && p.label.toLowerCase() !== p.name.toLowerCase() ? `<small>${esc(p.label)}</small>` : '';
    return `<tr><td title="${esc(p.label || p.name)}"><b>${esc(p.name)}</b>${nome}</td><td><input class="field" data-p="${esc(p.name)}" value="${esc(espr ? p.value : String(p.value).replace('.', ','))}"></td>` +
      `<td class="res">${espr && p.resolved != null ? '= ' + num(p.resolved, 2) : ''}</td></tr>`;
  }).join('');
  $('#params').innerHTML = righe || '<tr><td class="hint">Nessuna misura con nome.</td></tr>';
  const modello = !!S.from_template;
  $('#params-panel').classList.toggle('tpl', modello);
  $('#params-tpl').hidden = !modello;
  if (modello !== eraModello) {            // solo quando cambia il progetto: se l'hai aperto a mano resta aperto
    $('#params-box').open = !modello;
    $('#params-new').open = modello;
    eraModello = modello;
  }
}
$('#params-panel').addEventListener('keydown', ev => {
  const t = ev.target;
  if (ev.key !== 'Enter' || t.tagName !== 'INPUT') return;
  if (t.id === 'new-param') {
    const m = t.value.match(/^\s*([A-Za-z_]\w*)\s*=\s*(.+)$/);
    if (!m) { t.classList.add('bad'); toast('Scrivi così: nome = valore, per esempio  sbalzo = 30', 'err'); return; }
    t.classList.remove('bad');
    inCoda(async () => { if (await apply(await call('set_parameter', m[1], m[2]))) t.value = ''; });
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
  paint(); renderTree(); paintNodes();
  const nome = face != null ? objs.get(id)?.data.faces?.find(x => x.index === face)?.name ?? null : null;
  const r = await call('select', id, face, nome);
  if (mio !== selTok) return;
  if (!r.ok) { if (!silenzioso) toast(r.message, 'err'); return; }
  const fi = r.selection.face?.index;
  if (fi != null && fi !== face) { sel.face = fi; paint(); }     // il pezzo era stato ricostruito nel frattempo
  if (r.selection.highlight) { sel.hl = r.selection.highlight; paint(); }
  if (r.selection.kind === 'structure') { sel.ids = r.selection.members; paint(); }
  if (r.selection.kind === 'assembly') { sel.ids = [...objs.keys()]; paint(); }
  renderProps(r.selection);
  aggiornaLayout();
}
function clearSelection() {
  selTok++; selGen++;
  togliAnteprimaForo();
  sel = null; paint(); renderTree(); paintNodes();
  $('#props').innerHTML = '';
  aggiornaLayout();
}

async function disegnaSopra(aiuto) {
  // la faccia di sopra del pezzo: lì si disegnano fori, tagli, persiane
  const facce = objs.get('body')?.data?.faces || [];
  const f = facce.find(x => x.name === `${S.sheet?.feature}/sopra`) || facce.find(x => /\/fine$/.test(x.name || ''));
  if (!f) { toast('Clicca la faccia su cui lavorare, poi «Disegna su questa faccia».'); return; }
  const r = await call('sketch_on_face', f.name);
  if (await apply(r)) { await enterSketch(r.sketch); if (aiuto) toast(aiuto); }
}
// taglio di testa inclinato (a 45° per i cassoni a cornice): i campi, nella finestra nuova e nel pannello
function campiTesta(d, cls = 'form') {
  const opt = (v, l, cur) => `<option value="${v}"${v === cur ? ' selected' : ''}>${l}</option>`;
  return `<div class="${cls}">
    <label>Angolo<span class="inp"><input class="field" id="tt-ang" value="${esc(String(d.angle).replace('.', ','))}"><i>°</i></span></label>
    <label>Gioco di saldatura (totale)<span class="inp"><input class="field" id="tt-gap" value="${esc(String(d.gap).replace('.', ','))}"><i>mm</i></span></label>
    <label>Teste<select class="field" id="tt-end">${opt('entrambe', 'tutte e due', d.end)}${opt('inizio', 'solo all’inizio', d.end)}${opt('fine', 'solo alla fine', d.end)}</select></label>
    <label>Lato che resta lungo<select class="field" id="tt-side">${opt('fuori', 'il fondo (le pieghe vanno dentro)', d.side)}${opt('dentro', 'il lato delle pieghe', d.side)}</select></label></div>
    <p class="hint">Un piano unico taglia tutte le facce e le pieghe: passa per lo spigolo esterno della testa, così due pezzi tagliati uguali combaciano nell’angolo. Il gioco è il totale tra i due pezzi: ognuno si accorcia della metà.</p>`;
}
const leggiTesta = () => ({ angle: $('#tt-ang').value.trim(), gap: $('#tt-gap').value.trim(), end: $('#tt-end').value, side: $('#tt-side').value });
function tagliaTesta() {
  if (!S?.sheet?.data) { toast('Il taglio di testa si fa su una lamiera piegata: prima fai le pieghe.', 'err'); return; }
  modal(`<h3>Taglio di testa a 45°</h3>${campiTesta({ angle: 45, gap: 0, end: 'entrambe', side: 'fuori' })}
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Taglia</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => { const v = leggiTesta(); close(); inCoda(async () => { const r = await call('add_end_miter', v); if (await apply(r) && r.select) await select(r.select); }); };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#m-ok').click(); if (ev.key === 'Escape') close(); };
    $('#tt-gap').focus(); $('#tt-gap').select();
  });
}
function pannelloTesta(s) {
  $('#props').innerHTML = `<div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">${esc(s.feature)}</div></div>
      <button class="ibtn danger" id="tt-del" title="Elimina il taglio"><img src="icons/delete.svg" alt=""></button></div>
    ${s.rows.length ? `<table class="grid">${s.rows.map(r => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join('')}</table>` : ''}
    ${campiTesta(s.def, 'ff')}<div class="row-btns"><button class="btn primary" id="tt-ok">Applica</button></div>`;
  const vai = () => inCoda(async () => { const r = await call('edit_end_miter', s.feature, leggiTesta()); if (await apply(r) && r.select) await select(r.select); });
  $('#tt-ok').onclick = vai;
  ['#tt-ang', '#tt-gap'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  $('#tt-del').onclick = () => confermaElimina('sheet_miter', s.feature, 'Taglio di testa');
}
function azione(id) {
  const t = (m, k) => toast(m, k || '');
  const sel1 = async q => { await select(q); };
  switch (id) {
    case 'piega': runCmd('flange_help'); return;
    case 'tipo_foro': t('Clicca un foro sul pezzo: a destra scegli svasato o filettato. I fori nuovi: «Su una faccia», Cerchio, poi «Togli materiale».'); return;
    case 'taglia': inCoda(() => disegnaSopra('Disegna la parte da togliere partendo da un bordo, poi «Togli materiale».')); return;
    case 'forme': inCoda(() => disegnaSopra('Una linea per ogni persiana, un cerchio per ogni bugna; poi Altro → Persiane o Imbutiture.')); return;
    case 'contorno': inCoda(() => disegnaSopra()); return;
    case 'linguetta': inCoda(() => disegnaSopra('Disegna la linguetta partendo da un bordo e tornando sullo stesso bordo, poi «Aggiungi materiale».')); return;
    case 'piegatrice': showTab('sheet', true); return;
    case 'regole': runCmd('sheet_rules'); return;
    case 'sviluppo': runCmd('unfold'); return;
    case 'piega_linea': runCmd('flat_sketch'); return;
    case 'profilo': runCmd('contour_help'); return;
    case 'testa': tagliaTesta(); return;
    case 'orlo': t('Clicca la piega da ripiegare: nel suo pannello apri «Piega sulla punta» e scegli 180°.'); return;
    case 'angoli': t('Clicca una delle due pieghe che si incontrano: nel pannello trovi gli angoli.'); return;
    case 'parametri': { const d = $('#params-box'); if (d) { d.open = true; d.scrollIntoView({ block: 'nearest' }); } t('Le misure collegate sono a sinistra, sotto «Misure».'); return; }
    case 'misure': if (S.sheet?.shape) inCoda(() => sel1('body')); else if (S.cutlist?.rows?.length) inCoda(() => sel1('struct=ST1'));
      else { const d = $('#params-box'); if (d) d.open = true; t('Le misure sono a sinistra: cambia il numero e premi Invio.'); } return;
    case 'tubo': t('Clicca un’asta nel modello: nel pannello scegli il tubo (anche per tutte le aste uguali).'); return;
    case 'asta': runCmd('member_help'); return;
    case 'giunti': t('Clicca un pallino in un angolo: nel pannello scegli come si uniscono i tubi.'); return;
    case 'raccordo3d': dressTool('fillet'); return;
    case 'smusso3d': dressTool('chamfer'); return;
    default: return;
  }
}
$('#props').addEventListener('click', ev => { const b = ev.target.closest('[data-azione]'); if (b) azione(b.dataset.azione); });

// ------------------------------------------------------------- prepara per il laser / l'officina
async function preparaDialog() {
  const info = await call('prepara_info');
  if (!info.ok) { toast(info.message, 'err'); return; }
  let cartella = info.cartella;
  const c = info.controllo;
  const voci = info.voci.map(v => `<label class="${v.si ? '' : 'no'}" title="${v.si ? '' : esc('Non disponibile: ' + (v.motivo || ''))}">
      <input type="checkbox" data-voce="${v.id}" ${v.scelta ? 'checked' : ''} ${v.si ? '' : 'disabled'}>
      <span><b>${esc(v.titolo)}</b><span>${esc(v.desc)}</span><small>${v.si ? esc(v.file) : esc('Non disponibile: ' + (v.motivo || ''))}</small></span></label>`).join('');
  modal(`<h3>Cosa ti serve?</h3>
    ${c ? `<div class="prep-ok${c.ok ? '' : ' no'}">${c.ok ? '<b>Il pezzo è a posto per il laser.</b> ' : '<b>Attenzione:</b> '}${esc(c.ok ? 'Contorno chiuso, fori e pieghe controllati.' : c.testo)}</div>` : ''}
    <div class="prep-voci">${voci}</div>
    <div class="prep-dove">Si salvano in <b id="prep-dir">${esc(cartella)}</b> <button class="link" id="prep-cambia">Cambia cartella</button></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary big" id="m-ok">Salva i file</button></div>`, close => {
    $('#modal-box').classList.add('prepara');
    const conta = () => {
      const n = document.querySelectorAll('#modal-box [data-voce]:checked').length;
      $('#m-ok').textContent = n ? `Salva ${n === 1 ? 'il file' : `i ${n} file`}` : 'Scegli cosa ti serve';
      $('#m-ok').disabled = !n;
    };
    document.querySelectorAll('#modal-box [data-voce]').forEach(i => { i.onchange = conta; });
    conta();
    $('#m-no').onclick = close;
    $('#prep-cambia').onclick = () => inCoda(async () => { const r = await call('scegli_cartella'); if (r.ok) { cartella = r.cartella; $('#prep-dir').textContent = cartella; } });
    $('#m-ok').onclick = () => {
      const scelte = [...document.querySelectorAll('#modal-box [data-voce]:checked')].map(i => i.dataset.voce);
      close();
      inCoda(async () => {
        const r = await call('prepara', cartella, scelte);
        if (!r.ok) { toast(r.message || 'Non riuscito.', 'err'); return; }
        toast(r.message);
        await call('apri_cartella', r.cartella);
      });
    };
  });
}

let profili = null;
async function renderProps(s) {
  togliAnteprimaForo();
  const tab = rows => `<table class="grid">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
  const quanti = sel?.ids?.length > 1 && s.kind !== 'structure' ? ` <span style="color:var(--ink-3);font-weight:400">e altre ${sel.ids.length - 1} uguali</span>` : '';
  let h = `<h3>${esc(s.title)}${quanti}</h3>${tab(s.rows)}`;
  if (!profili) profili = await call('profile_suggestions');
  if (s.kind === 'structure' || (s.kind === 'body' && s.template)) {
    const t = s.template, idf = s.kind === 'structure' ? s.id : s.tpl_id;
    const forma = s.kind === 'body';
    h += t ? `<div class="sub">${esc(t.title)}: ${forma ? 'misure' : 'misure e profili'}</div><p class="hint" style="margin:0 0 6px">Cambia e premi Applica: ${forma ? 'il pezzo e lo sviluppo si rifanno.' : 'la struttura si rifà. Le aste ritoccate a mano restano.'}</p>
      <div class="form st-tpl">${t.fields.map(([k, l, v, scelte]) => scelte
        ? `<label class="lbl">${esc(l)}<select class="field" data-tf="${esc(k)}">${Object.entries(scelte).map(([a, b]) => `<option value="${a}"${a === v ? ' selected' : ''}>${esc(b)}</option>`).join('')}</select></label>`
        : `<label class="lbl">${esc(l)}<input class="field" data-tf="${esc(k)}" ${forma ? '' : 'list="dl-prof"'} value="${esc(String(v ?? '').replace('.', ','))}"></label>`).join('')}</div>
      <datalist id="dl-prof">${profili.map(p => `<option value="${esc(p)}">`).join('')}</datalist>
      <div class="row-btns"><button class="btn primary" id="tpl-apply">Applica</button></div>`
      : '<p class="hint">Struttura disegnata: le misure si cambiano dallo sketch (clic sullo sketch nell’albero), il profilo cliccando le aste.</p>';
    if (s.forma) h += formaPanel(s.forma);
    $('#props').innerHTML = h;
    if (s.forma) wireForma(s);
    if (t) {
      const vai = () => {
        const v = {};
        document.querySelectorAll('[data-tf]').forEach(i => { v[i.dataset.tf] = i.value.trim(); });
        inCoda(async () => { if (await apply(await call('structure_template_apply', idf, v), forma ? 'Pezzo rifatto con le misure nuove.' : 'Struttura rifatta con le misure nuove.')) await select(forma ? 'body' : 'struct=' + idf); });
      };
      $('#tpl-apply').onclick = vai;
      document.querySelectorAll('input[data-tf]').forEach(i => { i.onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
    }
    return;
  }
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
  } else if (s.kind === 'assembly') {
    $('#props').innerHTML = `<div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">tutto l’assieme</div></div></div>
      <table class="grid">${s.rows.map(r => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join('')}</table>
      <div class="sub">Ruota tutto l’assieme di 90°</div>
      <div class="row-btns"><button class="btn" data-rotall="x">attorno a X</button><button class="btn" data-rotall="y">attorno a Y</button><button class="btn" data-rotall="z">attorno a Z</button></div>
      <p class="hint">Gira tutti i pezzi insieme: gli accoppiamenti restano come sono. Per guardarlo da un altro lato invece trascina col tasto sinistro.</p>`;
    document.querySelectorAll('[data-rotall]').forEach(b => {
      b.onclick = () => inCoda(async () => { if (await apply(await call('asm_rotate_all', b.dataset.rotall, 90))) await refreshSel(); });
    });
    return;
  } else if (s.kind === 'mate') {
    $('#props').innerHTML = matePanel(s);
    wireMate(s);
    return;
  } else if (s.kind === 'fold') {
    $('#props').innerHTML = foldPanel(s) + faceSketchButton(s);
    wireFold(s);
    return;
  } else if (s.kind === 'endmiter') {
    pannelloTesta(s);
    return;
  } else if (s.kind === 'sidebend' || s.kind === 'edgeflange') {
    pannelloPiegaBordo(null, s);
    if (s.face) $('#props').insertAdjacentHTML('beforeend', faceSketchButton(s));   // e ci si disegna sopra
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
  } else if (s.kind === 'body' && s.foro) {
    $('#props').innerHTML = h + foroPanel(s.foro);
    wireForo(s.foro);
    return;
  } else if (s.kind === 'body') {
    h += faceSketchButton(s);              // esporta, spiega, sviluppo: sono nella barra in alto
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

// Forma da sezioni (tramoggia): i pezzi con l'ingombro e, spigolo per spigolo, piega o saldatura
function formaPanel(f) {
  const pezzi = f.pezzi.map(p => `<tr><td><b>${esc(p.nome)}</b></td><td>${p.pieghe} pieghe</td><td>${num(p.ingombro[0], 0)} × ${num(p.ingombro[1], 0)}</td>
    <td>${p.nel_foglio ? '✓' : '<span style="color:var(--err)">fuori foglio</span>'}</td></tr>`).join('');
  const nomeScelta = { piega: 'piega', saldatura: 'saldatura', taglio: 'taglio' };
  const spigoli = f.spigoli.filter(x => x.scelta !== 'taglio').map(x => `<tr><td title="${esc(x.key)}">${esc(x.nome)}</td>
    <td>${num(x.lung, 0)}</td><td>${num(x.angolo, 1)}°</td>
    <td><select class="field" data-spigolo="${esc(x.key)}">
      <option value="auto"${x.scelto_da !== 'te' ? ' selected' : ''}>${x.scelto_da === 'te' ? 'proposta' : 'proposta: ' + nomeScelta[x.scelta]}</option>
      <option value="piega"${x.scelto_da === 'te' && x.scelta === 'piega' ? ' selected' : ''}>piega</option>
      <option value="saldatura"${x.scelto_da === 'te' && x.scelta === 'saldatura' ? ' selected' : ''}>saldatura</option></select></td></tr>`).join('');
  return `<div class="sub">Pezzi da tagliare e piegare</div>
    <table class="grid">${pezzi}</table>
    <p class="hint" style="margin:4px 0">Saldature: <b>${num(f.saldature_m, 2)} m</b>${f.giunti_m ? ` · giunti dei bordi ${num(f.giunti_m, 2)} m` : ''} · foglio ${num(f.foglio[0], 0)} × ${num(f.foglio[1], 0)}</p>
    ${(f.avvisi || []).map(a => `<div class="msg warn">${esc(a)}</div>`).join('')}
    <details class="forma-spigoli"><summary>Spigoli: piega o saldatura</summary>
    <table class="grid forma-sp"><tr><th>Spigolo</th><th>mm</th><th>angolo</th><th></th></tr>${spigoli}</table></details>`;
}
function wireForma(s) {
  document.querySelectorAll('[data-spigolo]').forEach(el => {
    el.onchange = () => inCoda(async () => {
      const aperto = !!document.querySelector('.forma-spigoli[open]');
      const r = await call('set_shape_edge', s.tpl_id, el.dataset.spigolo, el.value);
      if (await apply(r)) { await select('body'); if (aperto) document.querySelector('.forma-spigoli')?.setAttribute('open', ''); }
    });
  });
}

function faceSketchButton(s) {
  if (!s.face?.planar || !s.face.name) return '';
  return `<div class="row-btns"><button class="btn" data-face-sketch="${esc(s.face.name)}">Disegna su questa faccia</button></div>`;
}
// ------------------------------------------------------------- un foro cliccato sul pezzo: semplice, svasato, filettato
// Come in ogni CAD: clic sulla parete del foro, a destra il tipo. Vale per il cerchio che l'ha fatto (e, se vuoi, per
// tutti i fori uguali dello stesso disegno).
const FILETTI_M = ['M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M16'];
function foroPanel(fo) {
  const h = fo.hole || {}, tipo = h.tipo || 'semplice', n = fo.uguali.length;
  const sv = `<div class="ff"><label>Ø svasatura<span class="inp"><input class="field" id="h-D" value="${esc(String(h.D ?? Math.round(fo.d * 2 * 10) / 10).replace('.', ','))}"><i>mm</i></span></label>
    <label>Angolo della punta<span class="inp"><input class="field" id="h-ang" value="${esc(String(h.angolo ?? 90))}"><i>°</i></span></label></div>
    <p class="hint" id="h-prof"></p>`;
  const fi = `<div class="ff"><label>Filettatura<select class="field" id="h-M">${FILETTI_M.map(m => `<option${(h.M || 'M6') === m ? ' selected' : ''}>${m}</option>`).join('')}</select></label><span></span></div>
    <p class="hint">Il foro diventa il preforo (M5 → Ø4,2) e la filettatura resta segnata sul pezzo.</p>`;
  const ins = `<div class="ff"><label>Codice inserto<input class="field" id="h-cod" value="${esc(h.codice || '')}"></label>
    <label>Ø foro (catalogo)<span class="inp"><input class="field" id="h-Di" value="${esc(h.tipo === 'inserto' ? String(h.D).replace('.', ',') : '')}"><i>mm</i></span></label></div>`;
  return `<div class="foro-p" data-tipo="${tipo}">
    <div class="fo-scelta" id="h-tipo">${[['semplice', 'Semplice'], ['svasato', 'Svasato'], ['filettato', 'Filettato'], ['inserto', 'Inserto']]
      .map(([k, l]) => `<button type="button" data-k="${k}" class="${tipo === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    <div id="h-sva"${tipo === 'svasato' ? '' : ' hidden'}>${sv}</div><div id="h-fil"${tipo === 'filettato' ? '' : ' hidden'}>${fi}</div>
    <div id="h-ins"${tipo === 'inserto' ? '' : ' hidden'}>${ins}</div>
    ${n > 1 ? `<label class="check"><input type="checkbox" id="h-tutti" checked> anche gli altri ${n - 1} fori Ø${esc(virgola(Math.round(fo.d * 100) / 100))} di questo disegno</label>` : ''}
    <div class="row-btns"><button class="btn primary" id="h-ok">Applica</button></div>
    <div class="row-btns"><button class="btn" id="h-vite" title="Salva il pezzo, apre un assieme e ci mette la vite in questo foro">Metti una vite in questo foro…</button></div></div>`;
}
// anteprima della svasatura sul pezzo mentre scrivi: il cono com'è, rosso se va più giù dello spessore (21/10)
const anteprimaForo = new THREE.Group();
scene.add(anteprimaForo);
const SVA_OK = new THREE.MeshBasicMaterial({ color: 0xFFB000, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthTest: false });
const SVA_NO = new THREE.MeshBasicMaterial({ color: 0xE5484D, transparent: true, opacity: 0.85, side: THREE.DoubleSide, depthTest: false });
// le svasature impossibili: sul pezzo il loro cono in rosso (il foro è stato fatto dritto)
const svasatureKo = new THREE.Group();
model.add(svasatureKo);
function buildSvasatureKo(lista) {
  svasatureKo.traverse(x => x.geometry?.dispose()); svasatureKo.clear();
  if (svasatureKo.parent !== model) model.add(svasatureKo);      // la scena nuova svuota il modello
  for (const s of lista || []) {
    const dentro = v3(s.n).normalize();
    const m = new THREE.Mesh(new THREE.CylinderGeometry(s.D / 2, s.d / 2, s.h, 48, 1, true), SVA_NO);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dentro.clone().negate());
    m.position.copy(v3(s.c)).addScaledVector(dentro, s.h / 2);
    m.renderOrder = 20;
    svasatureKo.add(m);
  }
}
function togliAnteprimaForo() { anteprimaForo.traverse(x => x.geometry?.dispose()); anteprimaForo.clear(); ridisegna(); }
function mostraAnteprimaForo(fo, tipo) {
  togliAnteprimaForo();
  const testo = $('#h-prof');
  if (tipo !== 'svasato' || !fo.centri) { if (testo) testo.textContent = ''; return; }
  const D = parseFloat($('#h-D').value.replace(',', '.')), ang = parseFloat($('#h-ang').value.replace(',', '.'));
  if (!(D > fo.d) || !(ang > 0 && ang < 180)) {
    testo.textContent = !(D > fo.d) ? `Il Ø della svasatura deve essere più grande del foro (Ø${virgola(Math.round(fo.d * 100) / 100)}).` : 'Angolo tra 1 e 179°.';
    testo.style.color = '#E5484D'; return;
  }
  const h = (D - fo.d) / 2 / Math.tan(ang * Math.PI / 360), t = fo.spessore;
  const troppo = t != null && h > t + 1e-6;
  testo.textContent = `Profonda ${virgola(Math.round(h * 100) / 100)} mm` + (t != null ? (troppo ? ` · più dello spessore (${virgola(t)}): riduci il Ø o apri l’angolo` : ` su ${virgola(t)} di spessore`) : '');
  testo.style.color = troppo ? '#E5484D' : '';
  const dentro = v3(fo.dentro).normalize();
  const tutti = $('#h-tutti')?.checked ? fo.uguali : [fo.cerchio];
  for (const k of tutti) {
    const c = fo.centri[k];
    if (!c) continue;
    const g = new THREE.CylinderGeometry(D / 2, fo.d / 2, h, 48, 1, true);   // sopra (y+) il Ø grande, sulla faccia
    const m = new THREE.Mesh(g, troppo ? SVA_NO : SVA_OK);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dentro.clone().negate());
    m.position.copy(v3(c)).addScaledVector(dentro, h / 2);
    m.renderOrder = 20;
    anteprimaForo.add(m);
  }
  ridisegna();
}
// una vite nel foro cliccato, direttamente dal pezzo: si sceglie la vite, il programma fa l'assieme (22/10)
async function viteDalPezzo(fo) {
  const r = await call('libreria_catalogo');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const cat = r.catalogo, sva = fo.hole?.tipo === 'svasato';
  const viti = Object.entries(cat).filter(([k]) => k.startsWith('vite') || k === 'rivetto');
  const misuraPer = c => c.misure.reduce((m, x) => (Math.abs(parseFloat(String(x).replace('M', '').replace(',', '.')) - fo.d) <
    Math.abs(parseFloat(String(m).replace('M', '').replace(',', '.')) - fo.d) ? x : m), c.misure[0]);
  const opz = (lst, v) => lst.map(x => `<option${String(x) === String(v) ? ' selected' : ''}>${esc(String(x))}</option>`).join('');
  const nomeServe = !S?.path;
  modal(`<h3>Vite in questo foro</h3>
    <p class="hint">Il pezzo si salva, si apre un assieme nuovo con il pezzo e la vite già nel foro${sva ? ' (seduta nella svasatura)' : ''}.</p>
    <div class="form">${nomeServe ? `<label style="grid-column:1/-1">Nome del pezzo (si salva in Documenti/SteelCAD)<input class="field" id="vp-n" value="${esc(S?.name || 'Pezzo')}"></label>` : ''}
      <label style="grid-column:1/-1">Cosa<select class="field" id="vp-t">${viti.map(([k, c]) => `<option value="${k}"${k === (sva ? 'vite_tspei' : 'vite_tcei') ? ' selected' : ''}>${esc(c.nome)}</option>`).join('')}</select></label>
      <label>Misura<select class="field" id="vp-m"></select></label><label>Lunghezza<select class="field" id="vp-l"></select></label></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Metti la vite</button></div>`, close => {
    const rifai = () => {
      const c = cat[$('#vp-t').value];
      $('#vp-m').innerHTML = opz(c.misure, misuraPer(c));
      $('#vp-l').innerHTML = opz(c.lunghezze, c.lunghezze[Math.floor(c.lunghezze.length / 3)]);
    };
    $('#vp-t').onchange = rifai; rifai();
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const tipo = $('#vp-t').value, misura = $('#vp-m').value, L = cat[tipo].lunghezze.length ? +$('#vp-l').value : null;
      const nome = $('#vp-n')?.value || '';
      close();
      inCoda(async () => {
        const r2 = await call('viti_dal_pezzo', nome, fo.centri[fo.cerchio], fo.dentro, fo.d, tipo, misura, L);
        if (await apply(r2, r2.message) && r2.select) await select(r2.select);
      });
    };
  });
}
function wireForo(fo) {
  let tipo = fo.hole?.tipo || 'semplice';
  if ($('#h-vite')) $('#h-vite').onclick = () => viteDalPezzo(fo);
  const vedi = () => mostraAnteprimaForo(fo, tipo);
  document.querySelectorAll('#h-tipo button').forEach(b => { b.onclick = () => {
    tipo = b.dataset.k;
    document.querySelectorAll('#h-tipo button').forEach(x => x.classList.toggle('on', x === b));
    $('#h-sva').hidden = tipo !== 'svasato'; $('#h-fil').hidden = tipo !== 'filettato'; $('#h-ins').hidden = tipo !== 'inserto';
    vedi();
  }; });
  ['#h-D', '#h-ang'].forEach(q => { $(q).oninput = vedi; });
  if ($('#h-tutti')) $('#h-tutti').onchange = vedi;
  vedi();
  $('#h-ok').onclick = () => {
    const spec = tipo === 'svasato' ? { tipo, D: $('#h-D').value.trim(), angolo: $('#h-ang').value.trim() }
      : tipo === 'filettato' ? { tipo, M: $('#h-M').value }
      : tipo === 'inserto' ? { tipo, codice: $('#h-cod').value.trim(), D: $('#h-Di').value.trim() } : null;
    const cerchi = $('#h-tutti')?.checked ? fo.uguali : [fo.cerchio];
    inCoda(async () => { await apply(await call('sketch_hole_type', fo.sketch, cerchi, spec)); });
  };
}

// ------------------------------------------------------------- fori e asole, senza sketch
// Come si segnano sul pezzo: misura, centro dal bordo sinistro e dal bordo davanti (fuori tutto), e se serve una
// fila. A sinistra la faccia vista da sopra con l'anteprima; un clic nel disegno sposta il foro lì.
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-face-sketch]');
  if (!b) return;
  inCoda(async () => {
    const r = await call('sketch_on_face', b.dataset.faceSketch);
    if (await apply(r)) await enterSketch(r.sketch);
  });
});

function deleteSelected() {
  if (sel?.id?.startsWith('flange=') && sel.id.split('/').length === 3 || sel?.id?.startsWith('pb=')) {
    const kind = sel.id.startsWith('pb=') ? 'sheet_edge_flange' : 'flange', ref = sel.id.startsWith('pb=') ? sel.id.slice(3) : sel.id.slice(7);
    confermaElimina(kind, ref, 'Piega sul bordo');
    return;
  }
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
  const icona = k => (k === 'up' ? '<svg viewBox="0 0 36 28" aria-hidden="true"><path d="M2 24h22V4"/></svg>'
    : k === 'down' ? '<svg viewBox="0 0 36 28" aria-hidden="true"><path d="M2 4h22v20"/></svg>' : '');
  const seg = (id, o, cur) => `<div class="seg big" id="${p}-${id}">${Object.entries(o).map(([k, v]) =>
    `<button type="button" data-v="${k}" class="${k === cur ? 'on' : ''}" title="${esc(SPIEGA[k + (o === VERSI_PUNTA ? '_t' : '')] || '')}">${id === 'dir' ? icona(k) : ''}${esc(v)}</button>`).join('')}</div>`;
  const ang = String(d.angle ?? 90).replace('.', ',');
  return `<div class="fp-pic" id="${p}-pic">${profiloPiega(d)}</div>
    <div class="fp-riga"><span>Quanto è alta</span><div class="fp-len">
      <button type="button" class="pm" data-pm="-1" data-for="${p}-len" aria-label="Un millimetro in meno">−</button>
      <span class="inp"><input class="field" id="${p}-len" value="${esc(String(d.length ?? '').replace('.', ','))}"><i>mm</i></span>
      <button type="button" class="pm" data-pm="1" data-for="${p}-len" aria-label="Un millimetro in più">+</button></div></div>
    <div class="fp-riga"><span>Angolo</span><div class="fp-ang">${[90, 45, 135].map(a => `<button type="button" class="chip${ang === String(a) ? ' on' : ''}"
      data-ang="${a}" data-for="${p}-ang">${a}°</button>`).join('')}<span class="inp"><input class="field" id="${p}-ang" value="${esc(ang)}" aria-label="Angolo"><i>°</i></span></div></div>
    <div class="seg-row"><span>Verso</span>${seg('dir', dirs, d.direction || 'up')}</div>
    <div class="seg-row"><span>Misura</span>${seg('pos', pos, d.position || 'inside')}</div>`;
}
// il profilo della piega visto di fianco: la base, la piega con la sua altezza e l'angolo
function profiloPiega(d) {
  const a = (parseFloat(String(d.angle ?? 90).replace(',', '.')) || 90) * Math.PI / 180;
  const giu = (d.direction || 'up') === 'down' ? 1 : -1;
  const x0 = 170, y0 = giu < 0 ? 112 : 38, L = 78;
  const ux = Math.cos(a), uy = giu * Math.sin(a);
  const x1 = x0 + ux * L, y1 = y0 + uy * L;
  const [nx, ny] = giu < 0 ? [-uy, ux] : [uy, -ux];                 // dalla parte di fuori della piega
  const o = 15, lx = (x0 + x1) / 2 + nx * 34, ly = (y0 + y1) / 2 + ny * 34 + 6;
  let bx = -1 + ux, by = uy;                                      // dentro l'angolo: la bisettrice tra base e piega
  const bl = Math.hypot(bx, by) || 1; bx /= bl; by /= bl;
  const f = v => v.toFixed(1);
  const len = esc(String(d.length ?? '').replace('.', ','));
  return `<svg viewBox="0 0 300 150" role="img" aria-label="Profilo della piega">
    <path class="pz" d="M40 ${y0}H${x0}L${f(x1)} ${f(y1)}"/>
    <path class="q" d="M${f(x0 + nx * o)} ${f(y0 + ny * o)}L${f(x1 + nx * o)} ${f(y1 + ny * o)}"/>
    <text class="qt" x="${f(lx)}" y="${f(ly)}">${len}</text>
    <text class="at" x="${f(x0 + bx * 34)}" y="${f(y0 + by * 34 + 5)}">${esc(String(d.angle ?? 90).replace('.', ','))}°</text></svg>`;
}
document.addEventListener('click', ev => {
  const pm = ev.target.closest('[data-pm]'), ch = ev.target.closest('[data-ang]');
  const b = pm || ch;
  if (!b) return;
  const i = document.getElementById(b.dataset.for);
  if (!i) return;
  if (pm) { const v = parseFloat(i.value.replace(',', '.')) || 0; i.value = String(Math.max(1, Math.round((v + +pm.dataset.pm) * 100) / 100)).replace('.', ','); }
  else { i.value = ch.dataset.ang; b.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === b)); }
  i.dispatchEvent(new Event('input', { bubbles: true }));
  i.dispatchEvent(new Event('change', { bubbles: true }));
});
// il disegno segue quello che scrivi o scegli
document.addEventListener('input', ev => { if (/^[a-z]+-(len|ang)$/.test(ev.target.id || '')) ridisegnaProfilo(ev.target.id.split('-')[0]); });
document.addEventListener('change', ev => { if (ev.target.closest?.('.seg')) ridisegnaProfilo(ev.target.closest('.seg').id.split('-')[0]); });
function ridisegnaProfilo(p) {
  const box = document.getElementById(`${p}-pic`);
  if (!box || !document.getElementById(`${p}-len`)) return;
  const d = readFlange(p);
  box.innerHTML = profiloPiega(d);
  document.querySelectorAll(`[data-for="${p}-ang"].chip`).forEach(c => c.classList.toggle('on', c.dataset.ang === d.angle.replace(',', '.')));
}
const VERSI_UI = { up: 'In su', down: 'In giù' };
// per una flangia sulla punta di un'altra: "su" continua a chiudere (verso dentro), "giù" apre verso fuori (omega)
const VERSI_PUNTA = { up: 'Verso dentro', down: 'Verso fuori' };
const POS_UI = { inside: 'Fuori tutto', outside: 'Dal bordo' };
// il lato di una piega in parole di officina
const LATI = { 'lato sotto': 'davanti', 'lato sopra': 'dietro', 'lato destro': 'a destra', 'lato sinistro': 'a sinistra' };
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
      <button class="btn" id="t-orlo" title="Risvolto a 180° (orlo): la parete resta lunga fino al bordo esterno della piega">Orlo 180°</button>
      <button class="btn" id="t-gradino" title="Gradino (joggle): la parete si sposta di poco e continua parallela, per sovrapporre due lamiere a filo">Gradino…</button></div></details>`;
  const sezIncastri = s.tip_contact ? `<details class="fsec" open id="f-incastri"><summary>Incastri sulla punta</summary>
    <p class="hint">La punta di ${esc(s.flange)} appoggia su ${esc(s.tip_contact)}: linguette sulla punta e asole sull’altra faccia.</p>
    <div class="ff"><label>Quante<span class="inp"><input class="field" id="i-n" value="3"></span></label>
      <label>Larghezza<span class="inp"><input class="field" id="i-w" value="15"><i>mm</i></span></label>
      <label>Gioco<span class="inp"><input class="field" id="i-c" value="0,2"><i>mm</i></span></label>
      <label>Sporgenza<span class="inp"><input class="field" id="i-s" value="0"><i>mm</i></span></label></div>
    <div class="row-btns"><button class="btn primary" id="i-add">Crea gli incastri</button></div></details>` : '';
  const dati = s.rows.filter(r => !['Lato', 'Piegata sulla punta di'].includes(r[0]));
  const lato = riga('Lato') || '';
  const titolo = s.parent ? (Math.abs(+s.def.angle) >= 170 ? 'Orlo' : 'Piega sulla punta') : `Piega ${LATI[lato] || lato}`;
  const sotto = s.parent ? `sulla piega ${s.parent}` : (riga('Larghezza') ? `bordo da ${riga('Larghezza')}` : '');
  return `<div class="fhead" data-flangia="${esc(s.flange)}"><div><h3>${esc(titolo)}</h3><div class="fsub">${esc(sotto)} <span class="fid">${esc(s.flange)}</span></div></div></div>
    ${flangeFields(s.def, s.parent ? VERSI_PUNTA : (s.directions?.up ? VERSI_UI : s.directions), POS_UI)}
    ${sezLinguetta}${sezAngoli}${sezIncastri}${sezPunta}
    ${rigaPiega(dati)}
    <div class="fp-fine"><button class="link danger" id="f-del" title="Canc">Togli questa piega</button>
      <button class="btn primary big" id="f-fatto">Fatto</button></div>`;
}
// i dati di piega stanno in un posto solo (la scheda Lamiera in basso): qui un riassunto e "cambia"
function rigaPiega(righe = []) {
  const d = S?.sheet?.def || {}, pd = S?.bend_default || {};
  const n = v => (v == null || v === '' ? '?' : String(v).replace('.', ','));
  const calcolo = d.method === 'bd90' ? `deduzione 90° ${n(d.bd90)}` : d.method === 'din6935' ? 'DIN 6935' : `K ${n(d.k)}`;
  const predef = (d.method || 'k') === 'k' && d.radius != null && +d.radius === +pd.radius && +d.k === +pd.k ? ' (predefinito)' : '';
  const altre = righe.filter(r => !['Piega', 'BA / BD'].includes(r[0]));
  return `${altre.length ? `<table class="grid" style="margin-top:8px">${altre.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>` : ''}
    <p class="piega-riga">Piega: R ${esc(n(d.radius))}, ${esc(calcolo)}${predef} · <a href="#" data-piega-cambia title="Apre la scheda Lamiera in basso: spessore, raggio, K">cambia</a></p>`;
}
document.addEventListener('click', ev => {
  if (!ev.target.closest('[data-piega-cambia]')) return;
  ev.preventDefault();
  showTab('sheet', true);
});
// ===================================================================== assiemi
const ASM = { tool: null, clic: [] };
// ogni accoppiamento: il nome e cosa cliccare, nell'ordine (il pezzo fermo prima); misura = parte dal valore che c'è
const MATE_UI = {
  faccia: { nome: 'Faccia su faccia', clic: ['la faccia del pezzo che sta fermo', 'la faccia dell’altro pezzo'], val: 0 },
  asse: { nome: 'Foro su foro', clic: ['il foro del pezzo che sta fermo', 'il foro dell’altro pezzo'], val: 0 },
  distanza: { nome: 'Distanza', clic: ['una faccia del pezzo che sta fermo', 'la faccia dell’altro pezzo'], val: null },
  angolo: { nome: 'Angolo', clic: ['una faccia del pezzo che sta fermo', 'una faccia dell’altro pezzo'], val: null },
  tangente: { nome: 'Tangente', clic: ['la faccia (o il tubo) del pezzo che sta fermo', 'il tubo (o la faccia) dell’altro pezzo'], val: 0 },
  parallelo: { nome: 'Parallele', clic: ['una faccia (o un tubo) del pezzo che sta fermo', 'una faccia (o un tubo) dell’altro pezzo'], val: 0 },
  perpendicolare: { nome: 'Perpendicolari', clic: ['una faccia (o un tubo) del pezzo che sta fermo', 'una faccia (o un tubo) dell’altro pezzo'], val: 0 },
  centra: { nome: 'In mezzo', clic: ['un lato del pezzo che sta fermo (es. un’ala dell’U)', 'il lato opposto dello stesso pezzo', 'una faccia del pezzo da centrare', 'la sua faccia opposta'], val: 0 },
  blocca: { nome: 'Blocca', clic: ['il pezzo che sta fermo', 'il pezzo da bloccare'], val: 0 },
  spigolo: { nome: 'Spigolo su spigolo', clic: ['uno spigolo dritto del pezzo che sta fermo', 'lo spigolo dell’altro pezzo'], val: 0, spigoli: [true, true] },
  spigolo_faccia: { nome: 'Spigolo su faccia', clic: ['la faccia del pezzo che sta fermo', 'lo spigolo dritto dell’altro pezzo'], val: 0, spigoli: [false, true] },
  cono: { nome: 'Cono su cono', clic: ['la svasatura del foro', 'la testa conica della vite'], val: 0 },
  testa: { nome: 'Testa a testa', clic: ['la faccia a 45° del pezzo che sta fermo', 'la faccia a 45° dell’altro pezzo (la stessa parete)'], val: null },
};
function asmHelp() {
  const u = MATE_UI[ASM.tool], k = ASM.clic.length;
  setHelp(`${u.nome}${u.clic.length > 2 ? ` (${k + 1} di ${u.clic.length})` : ''}: ${k ? 'ora ' : ''}clic su ${u.clic[k]} · Esc annulla`);
}
function asmTool(t) {
  ASM.tool = t; ASM.clic = [];
  document.querySelectorAll('[data-asm-tool]').forEach(b => b.classList.toggle('on', b.dataset.asmTool === t));
  if (t) asmHelp(); else setHelp('');
  if (!SK) $('#sk-foot').hidden = !t;                // il suggerimento in basso, anche fuori dal disegno
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-asm-tool]');
  if (b) asmTool(ASM.tool === b.dataset.asmTool ? null : b.dataset.asmTool);
});
// STEP del cliente → lamiera con lo sviluppo (K della piegatrice, si può cambiare)
function stepDialog() {
  const k = S?.bend_default?.k ?? 0.33;
  modal(`<h3>Apri STEP di una lamiera</h3>
    <p class="hint">Riconosco spessore e pieghe e spiego il pezzo: lo sviluppo con il K che usi tu (non quello del cliente). Se il pezzo non è una lamiera piegata (angolare, assieme, forme speciali) te lo dico invece di darti uno sviluppo sbagliato.</p>
    <div class="form"><label>K-factor<input class="field" id="st-k" value="${esc(String(k).replace('.', ','))}"></label><span></span></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Scegli il file STEP…</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const kk = $('#st-k').value.trim(); close();
      inCoda(async () => {
        const r = await call('import_step_dialog', kk);
        if (r.cancelled) return;
        primaVolta = true; clearSelection();
        if (await apply(r, r.message)) hideHome();
      });
    };
  });
}
async function viteriaDialog() {
  if (S?.mode !== 'assembly') { toast('La viteria si mette negli assiemi.', 'err'); return; }
  const r = await call('libreria_catalogo');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const cat = r.catalogo, foro = sel?.id && sel.face != null && objs.get(sel.id)?.data.kind === 'instance' ? { inst: sel.id, face: sel.face } : null;
  const opz = (lst, v) => lst.map(x => `<option${String(x) === String(v) ? ' selected' : ''}>${esc(String(x))}</option>`).join('');
  const ultimo = viteriaDialog.ultimo || { tipo: 'vite_tcei', misura: 'M6', L: 20 };
  modal(`<h3>Viteria</h3>
    <p class="hint">Dalle norme ISO: il pezzo si fa la prima volta e poi si riusa (Documenti/SteelCAD/Libreria). In distinta va tra gli acquisti.</p>
    <div class="form"><label style="grid-column:1/-1">Cosa<select class="field" id="vt-t">${Object.entries(cat).map(([k, c]) => `<option value="${k}"${k === ultimo.tipo ? ' selected' : ''}>${esc(c.nome)}</option>`).join('')}</select></label>
      <label>Misura<select class="field" id="vt-m"></select></label><label id="vt-lw">Lunghezza<select class="field" id="vt-l"></select></label></div>
    ${foro ? '<label class="check"><input type="checkbox" id="vt-f" checked> nel foro che hai cliccato</label>' : '<p class="hint">Per metterla in un foro: clicca prima il foro, poi «Viteria».</p>'}
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Inserisci</button></div>`, close => {
    const rifai = () => {
      const c = cat[$('#vt-t').value];
      $('#vt-m').innerHTML = opz(c.misure, c.misure.includes(ultimo.misura) ? ultimo.misura : c.misure[Math.floor(c.misure.length / 2)]);
      $('#vt-l').innerHTML = opz(c.lunghezze, c.lunghezze.includes(+ultimo.L) ? ultimo.L : c.lunghezze[Math.floor(c.lunghezze.length / 3)]);
      $('#vt-lw').hidden = !c.lunghezze.length;
    };
    $('#vt-t').onchange = rifai; rifai();
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const tipo = $('#vt-t').value, misura = $('#vt-m').value, L = cat[tipo].lunghezze.length ? +$('#vt-l').value : null;
      viteriaDialog.ultimo = { tipo, misura, L: L || ultimo.L };
      const dove = $('#vt-f')?.checked ? foro : null;
      close();
      inCoda(async () => { const r2 = await call('asm_insert_libreria', tipo, misura, L, dove); if (await apply(r2, r2.message) && r2.select) await select(r2.select); });
    };
  });
}
function pickInstEdge(ev) {                          // lo spigolo di una copia dell'assieme sotto il mouse (punto nel mondo)
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const scr = p => { const q = p.clone().project(camera); return [(q.x + 1) / 2 * r.width, (1 - q.y) / 2 * r.height]; };
  const corpi = [...objs.values()].map(o => o.mesh);
  let best = null;
  for (const o of objs.values()) {
    if (o.data.kind !== 'instance') continue;
    for (const e of o.data.edges) for (let i = 0; i + 5 < e.length; i += 3) {
      const A = new THREE.Vector3(e[i], e[i + 1], e[i + 2]), B = new THREE.Vector3(e[i + 3], e[i + 4], e[i + 5]);
      if (o.pos) { A.applyMatrix4(o.pos); B.applyMatrix4(o.pos); }
      const a = scr(A), b = scr(B), dx = b[0] - a[0], dy = b[1] - a[1], LL = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((mx - a[0]) * dx + (my - a[1]) * dy) / LL));
      const d = Math.hypot(mx - a[0] - t * dx, my - a[1] - t * dy);
      if (d > 8 || (best && d >= best.d)) continue;
      const P = A.clone().lerp(B, t), dir = P.clone().sub(camera.position), dist = dir.length();
      ray.set(camera.position, dir.normalize());
      const hit = ray.intersectObjects(corpi, false)[0];
      if (hit && hit.distance < dist - 0.5) continue;
      best = { id: o.data.id, d, p: [P.x, P.y, P.z] };
    }
  }
  return best;
}
function asmClick(ev) {
  const u0 = MATE_UI[ASM.tool], k0 = ASM.clic.length;
  let h, c;
  if (u0.spigoli?.[k0 < u0.clic.length / 2 ? 0 : 1]) {
    h = pickInstEdge(ev);
    if (!h) { toast('Clicca proprio su uno spigolo dritto (la linea del bordo).', 'err'); return; }
    c = { inst: h.id, edge_pt: h.p };
  } else {
    h = pick(ev);
    if (!h || h.face == null) { toast('Clicca una faccia di un pezzo.', 'err'); return; }
    c = { inst: h.id, face: h.face };
  }
  const u = u0, k = k0;
  const daFermo = k < u.clic.length / 2;                // le prime metà dei clic sono sul pezzo fermo
  if (k > 0 && daFermo && h.id !== ASM.clic[0].inst) { toast('Questa faccia va scelta sullo stesso pezzo di prima.', 'err'); return; }
  if (!daFermo && h.id === ASM.clic[0].inst) { toast('Scegli una faccia di un altro pezzo.', 'err'); return; }
  if (k > u.clic.length / 2 && h.id !== ASM.clic[u.clic.length / 2].inst) { toast('Questa faccia va scelta sullo stesso pezzo di prima.', 'err'); return; }
  ASM.clic.push(c);
  if (ASM.clic.length < u.clic.length) { sel = c.face != null ? { id: h.id, face: h.face } : { id: h.id }; paint(); asmHelp(); return; }
  const cc = ASM.clic, tipo = ASM.tool;
  const [a, a2, b, b2] = cc.length === 4 ? cc : [cc[0], null, cc[1], null];
  asmTool(tipo);                                       // resta attivo per un altro accoppiamento
  inCoda(async () => {
    const r = await call('asm_add_mate', tipo, a, b, u.val, false, a2, b2);
    if (await apply(r, 'Accoppiato.') && r.select) {
      await select(r.select);
      if (u.val === null) setTimeout(() => { const c = $('#m-off') || $('#m-ang'); if (c) { c.focus(); c.select(); } }, 60);   // a pannello pronto
    }
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
    ${(s.movimenti || []).map((m, k) => {
      const v = m.valore, lo = m.campo === 'angle' ? 0 : Math.floor(Math.min(v - 200, -2)), hi = m.campo === 'angle' ? 180 : Math.ceil(v + 200);
      return `<div class="sub">${esc(m.nome)}</div>
        <div class="ff"><label>${m.campo === 'angle' ? 'Angolo' : 'Quanto'}<span class="inp"><input class="field" id="mv-v${k}" value="${esc(String(Math.round(v * 10) / 10).replace('.', ','))}"><i>${m.campo === 'angle' ? '°' : 'mm'}</i></span></label><span></span></div>
        <input type="range" id="mv-s${k}" min="${lo}" max="${hi}" step="1" value="${v}" style="width:100%" title="Trascina: il pezzo si muove">`;
    }).join('')}
    <div class="sub">Sposta (mm)</div>
    <div class="xyz"><label>X<input class="field" id="a-dx" value="0"></label><label>Y<input class="field" id="a-dy" value="0"></label><label>Z<input class="field" id="a-dz" value="0"></label></div>
    <div class="row-btns"><button class="btn" id="a-move">Sposta</button></div>
    <div class="sub">Ruota di 90°</div>
    <div class="row-btns"><button class="btn" data-rot="x">attorno a X</button><button class="btn" data-rot="y">attorno a Y</button><button class="btn" data-rot="z">attorno a Z</button></div>
    <label class="check" style="margin-top:8px"><input type="checkbox" id="a-fixed"${s.fixed ? ' checked' : ''}> Fermo (gli altri pezzi si appoggiano a lui)</label>
    ${s.acquisto ? '' : `<div class="ff"><label>Finitura<select class="field" id="a-fin">${[['grezzo', 'Grezzo'], ['zincato', 'Zincato'], ['inox', 'Inox spazzolato'], ['verniciato', 'Verniciato RAL']].map(([k, l]) => `<option value="${k}"${(s.finitura?.tipo || 'grezzo') === k ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
      <label${s.finitura?.tipo === 'verniciato' ? '' : ' hidden'} id="a-ral-w">RAL<input class="field" id="a-ral" list="ral-lista" value="${esc(s.finitura?.ral || '')}" placeholder="es. 7035"></label></div>
      <datalist id="ral-lista">${['1003', '1013', '1023', '2004', '3000', '3002', '3020', '5010', '5012', '5015', '6005', '6018', '7016', '7021', '7035', '7037', '7040', '9005', '9006', '9010', '9016'].map(x => `<option value="${x}">`).join('')}</datalist>`}
    <label class="check"><input type="checkbox" id="a-acq"${s.acquisto ? ' checked' : ''}> Da acquistare (guide, viti, utensili…): in distinta, niente DXF</label>
    ${s.acquisto ? `<div class="ff"><label style="grid-column:1/-1">Descrizione<input class="field" id="a-acq-d" value="${esc(s.acquisto.descrizione || '')}"></label>
      <label>Codice<input class="field" id="a-acq-c" value="${esc(s.acquisto.codice || '')}"></label>
      <label>Fornitore<input class="field" id="a-acq-f" value="${esc(s.acquisto.fornitore || '')}"></label></div>` : ''}
    <div class="row-btns"><button class="btn primary" id="a-open">Apri il pezzo</button></div>
    ${s.face && s.face.kind === 'piana' ? `<div class="row-btns"><button class="btn primary" id="a-nuovo">Nuovo pezzo su questa faccia</button></div>
      <p class="hint">Disegni sul piano di questa faccia, con i bordi dei pezzi che ci stanno: per una lamiera che li collega.</p>` : ''}
    ${s.mates.length ? `<p class="hint">Accoppiamenti: ${esc(s.mates.join(', '))}</p>` : '<p class="hint">Nessun accoppiamento: si sposta liberamente.</p>'}`;
}
function wireInstance(s) {
  const fai = (m, ...a) => inCoda(async () => { if (await apply(await call(m, ...a))) await refreshSel(); });
  $('#a-move').onclick = () => fai('asm_move', s.id, $('#a-dx').value.trim(), $('#a-dy').value.trim(), $('#a-dz').value.trim());
  document.querySelectorAll('[data-rot]').forEach(b => { b.onclick = () => fai('asm_rotate', s.id, b.dataset.rot, 90); });
  $('#a-fixed').onchange = () => fai('asm_set', s.id, { fixed: $('#a-fixed').checked });
  (s.movimenti || []).forEach((m, k) => cursoreMovimento($('#mv-s' + k), $('#mv-v' + k), m.id, m.campo));
  const acq = () => ({ descrizione: $('#a-acq-d')?.value || '', codice: $('#a-acq-c')?.value || '', fornitore: $('#a-acq-f')?.value || '' });
  $('#a-acq').onchange = () => fai('asm_set_acquisto', s.id, $('#a-acq').checked ? acq() : null);
  if ($('#a-fin')) {
    const fin = () => ({ tipo: $('#a-fin').value, ral: $('#a-ral').value.trim() });
    $('#a-fin').onchange = () => { $('#a-ral-w').hidden = $('#a-fin').value !== 'verniciato';
      if ($('#a-fin').value !== 'verniciato' || $('#a-ral').value.trim()) fai('asm_set_finitura', s.id, fin()); else $('#a-ral').focus(); };
    $('#a-ral').onchange = () => fai('asm_set_finitura', s.id, fin());
  }
  ['#a-acq-d', '#a-acq-c', '#a-acq-f'].forEach(id => { if ($(id)) $(id).onchange = () => fai('asm_set_acquisto', s.id, acq()); });
  $('#a-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('asm_remove', s.id))); };
  $('#a-open').onclick = () => { clearSelection(); primaVolta = true; inCoda(async () => apply(await call('asm_open_part', s.id))); };
  if ($('#a-nuovo')) $('#a-nuovo').onclick = () => modal(`<h3>Nuovo pezzo su questa faccia</h3>
      <p class="hint">Lo disegni sul piano della faccia, vedendo gli altri pezzi; tornando all’assieme si monta da solo.</p>
      <div class="form"><label style="grid-column:1/-1">Nome<input class="field" id="np-nome" value="Lamiera di collegamento"></label></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Disegna</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#np-nome').select();
    const vai = () => {
      const nome = $('#np-nome').value.trim(); close(); clearSelection(); primaVolta = true;
      inCoda(async () => { const r = await call('asm_new_part', s.id, s.face.index, nome); if (await apply(r, r.message) && r.sketch) await enterSketch(r.sketch); });
    };
    $('#m-ok').onclick = vai;
    $('#np-nome').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
  });
  if ($('#t-go')) $('#t-go').onclick = () => inCoda(async () => apply(await call('asm_tabs', s.id, s.face.index,
    $('#t-n').value.trim(), $('#t-w').value.trim(), $('#t-c').value.trim(), $('#t-s').value.trim())));
}
// il campo del valore e il pulsante «gira» di ogni accoppiamento (niente = non serve)
const MATE_CAMPO = { faccia: 'Distanza', distanza: 'Distanza', tangente: 'Gioco', centra: 'Fuori centro', testa: 'Gioco di saldatura' };
const MATE_GIRA = { faccia: ['Allinea invece di affacciare', 'Affaccia invece di allineare'], distanza: ['Allinea invece di affacciare', 'Affaccia invece di allineare'],
  asse: ['Gira dall’altra parte'], parallelo: ['Gira dall’altra parte'], angolo: ['Angolo dall’altra parte'], tangente: ['Dall’altra parte'] };
function matePanel(s) {
  const d = s.def, v = x => esc(String(Math.round(x * 1000) / 1000).replace('.', ','));
  const gira = MATE_GIRA[d.type];
  return `<div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">${esc(s.rows[0][1])}</div></div>
      <button class="ibtn danger" id="m-del" title="Togli l’accoppiamento"><img src="icons/delete.svg" alt=""></button></div>
    <table class="grid">${s.rows.slice(1).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>
    ${MATE_CAMPO[d.type] ? `<div class="ff" style="margin-top:10px"><label>${MATE_CAMPO[d.type]}<span class="inp"><input class="field" id="m-off" value="${v(d.offset)}"><i>mm</i></span></label><span></span></div>
      ${d.type === 'distanza' ? `<input type="range" id="m-slide" min="${Math.floor(Math.min(0, d.offset - 200))}" max="${Math.ceil(d.offset + 200)}" step="1" value="${d.offset}" style="width:100%" title="Trascina: il pezzo si muove">` : ''}` : ''}
    ${d.type === 'angolo' ? `<div class="ff" style="margin-top:10px"><label>Angolo<span class="inp"><input class="field" id="m-ang" value="${v(d.angle)}"><i>°</i></span></label><span></span></div>
      <input type="range" id="m-slide" min="0" max="180" step="1" value="${d.angle}" style="width:100%" title="Trascina: il pezzo gira">
      <p class="hint">0° = una faccia contro l’altra, 90° = a squadra.</p>` : ''}
    <div class="row-btns">${gira ? `<button class="btn" id="m-flip">${gira[d.flip && gira[1] ? 1 : 0]}</button>` : ''}
      <button class="btn" id="m-sosp">${d.off ? 'Riattiva' : 'Sospendi'}</button></div>`;
}
function wireMate(s) {
  const fai = f => inCoda(async () => { if (await apply(await call('asm_edit_mate', s.id, f))) await refreshSel(); });
  if ($('#m-off')) { $('#m-off').onkeydown = ev => { if (ev.key === 'Enter') fai({ offset: $('#m-off').value.trim() }); }; $('#m-off').onchange = () => fai({ offset: $('#m-off').value.trim() }); }
  if ($('#m-ang')) { $('#m-ang').onkeydown = ev => { if (ev.key === 'Enter') fai({ angle: $('#m-ang').value.trim() }); }; $('#m-ang').onchange = () => fai({ angle: $('#m-ang').value.trim() }); }
  if ($('#m-flip')) $('#m-flip').onclick = () => fai({ flip: !s.def.flip });
  if ($('#m-slide')) cursoreMovimento($('#m-slide'), $('#m-off') || $('#m-ang'), s.id, s.def.type === 'angolo' ? 'angle' : 'offset');
  $('#m-sosp').onclick = () => fai({ off: !s.def.off });
  $('#m-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('asm_delete_mate', s.id))); };
}
// il cursore che muove un pezzo: mentre lo trascini si spostano i pezzi già disegnati (una chiamata alla volta);
// lasciato, la modifica si registra una volta (annulla torna a prima)
function cursoreMovimento(slider, box, mid, campo) {
  let inVolo = false, ultimo = null;
  const manda = async () => {
    if (inVolo || ultimo === null) return;
    inVolo = true; const val = ultimo; ultimo = null;
    const r = await call('asm_trascina_mate', mid, campo, String(val), false);
    if (r.ok) spostaPezzi(r.pose);
    inVolo = false;
    if (ultimo !== null) manda();
  };
  slider.oninput = ev => { ultimo = ev.target.value; if (box) box.value = String(ultimo).replace('.', ','); manda(); };
  slider.onchange = ev => {
    const val = ev.target.value;
    inCoda(async () => {
      while (inVolo) await new Promise(r => setTimeout(r, 30));
      const r = await call('asm_trascina_mate', mid, campo, String(val), true);
      if (await apply(r)) await refreshSel();
    });
  };
  if (box) box.onchange = () => { slider.value = box.value.replace(',', '.'); slider.onchange({ target: slider }); };
}
// il riquadro «Stai disegnando…» aperto o chiuso: si ricorda (solo su questo PC)
function skPanelAperto() { try { return localStorage.getItem('steelcad.skPanel') === 'aperto'; } catch { return false; } }
$('#sk-where-box').addEventListener('click', () => {
  const aperto = $('#sk-panel').classList.toggle('chiuso') === false;
  try { localStorage.setItem('steelcad.skPanel', aperto ? 'aperto' : 'chiuso'); } catch { /* niente memoria: va bene lo stesso */ }
  $('#sk-where-fr').textContent = aperto ? '▾' : '▸';
});

// ===================================================================== Quota (misura) dappertutto
// 22/10, Stefano: «un tasto quota dappertutto, anche negli assiemi». Due clic = distanza; un clic sul bordo di un foro
// = diametro. Ci si aggancia a vertici, metà degli spigoli dritti, centri di fori e archi (pezzo, sviluppo, assieme).
// Le quote restano a video (per file aperto, in questa sessione); tasto destro su una quota per toglierla.
let MIS = null;                                    // { a: punto, cand: [...], hover }
const MISURE = new Map();                          // file -> [{ a, b, tipo, testo }]
const misGroup = new THREE.Group();
scene.add(misGroup);
const MIS_MAT = new THREE.LineBasicMaterial({ color: 0xFFB000, depthTest: false });
const MIS_RUB = new THREE.LineDashedMaterial({ color: 0xFFB000, dashSize: 4, gapSize: 3, depthTest: false });
var misEls = [];                                   // var: placeDims la legge già prima di qui
const misBox = document.createElement('div');
misBox.id = 'mis-box';
document.getElementById('dims').after(misBox);
const misSnap = document.createElement('div');
misSnap.id = 'mis-snap';
misBox.after(misSnap);
const chiaveMis = () => (S?.path || S?.name || 'nuovo') + (S?.mode === 'assembly' ? '#asm' : '');
const quoteDi = () => { const k = chiaveMis(); if (!MISURE.has(k)) MISURE.set(k, []); return MISURE.get(k); };

function misCandidati() {
  const out = [], visti = new Set();
  const metti = (p, tipo, extra = {}) => {
    const k = `${tipo}:${p.x.toFixed(3)},${p.y.toFixed(3)},${p.z.toFixed(3)}`;
    if (visti.has(k)) return;
    visti.add(k); out.push({ p, tipo, ...extra });
  };
  const daPolilinea = (pts) => {
    if (pts.length < 2) return;
    const chiusa = pts.length > 8 && pts[0].distanceTo(pts[pts.length - 1]) < 1e-3;
    if (chiusa) {                                   // un cerchio intero (l'ultimo punto è il primo: non si conta due volte)
      const giro = pts.slice(0, -1);
      const c = giro.reduce((s, q) => s.add(q), new THREE.Vector3()).multiplyScalar(1 / giro.length);
      const r = giro.reduce((s, q) => s + q.distanceTo(c), 0) / giro.length;
      if (giro.every(q => Math.abs(q.distanceTo(c) - r) < Math.max(0.02 * r, 0.05))) { metti(c, 'centro', { r, giro: pts }); cuciture.push(pts[0]); return; }
    }
    if (pts.length > 4) {                           // un arco: il suo centro (tre punti)
      const a = pts[0], b = pts[Math.floor(pts.length / 2)], c = pts[pts.length - 1];
      const ab = b.clone().sub(a), ac = c.clone().sub(a), n = ab.clone().cross(ac);
      if (n.lengthSq() > 1e-9) {
        const cc = ac.clone().multiplyScalar(ab.lengthSq()).sub(ab.clone().multiplyScalar(ac.lengthSq())).cross(n).multiplyScalar(1 / (2 * n.lengthSq()));
        const centro = a.clone().add(cc), r = centro.distanceTo(a);
        if (pts.every(q => Math.abs(q.distanceTo(centro) - r) < Math.max(0.02 * r, 0.05))) { archi.push({ centro, r, pts }); return; }
      }
    }
    metti(pts[0], 'vertice'); metti(pts[pts.length - 1], 'vertice');
    if (pts.length === 2) metti(pts[0].clone().add(pts[1]).multiplyScalar(0.5), 'metà', { capi: [pts[0], pts[1]] });
  };
  const cuciture = [];                              // il punto dove il motore «chiude» un cerchio: non è un vertice vero
  // gli archi: quelli con lo stesso centro e raggio sono pezzi dello stesso cerchio (il motore spezza i cerchi in due):
  // un cerchio intero ha solo il centro; un arco vero anche i suoi due estremi
  const archi = [];
  const chiudiArchi = () => {
    const gruppi = [];
    for (const a of archi) {
      const g = gruppi.find(x => x.centro.distanceTo(a.centro) < 1e-3 && Math.abs(x.r - a.r) < 1e-3);
      if (g) { g.pezzi.push(a); g.giro = g.giro.concat(a.pts); } else gruppi.push({ centro: a.centro, r: a.r, pezzi: [a], giro: [...a.pts] });
    }
    for (const g of gruppi) {
      const lungo = g.pezzi.reduce((s, a) => s + a.pts.slice(1).reduce((t, q, i) => t + q.distanceTo(a.pts[i]), 0), 0);
      metti(g.centro, 'centro', { r: g.r, giro: g.giro });
      if (lungo < 2 * Math.PI * g.r * 0.98) for (const a of g.pezzi) { metti(a.pts[0], 'vertice'); metti(a.pts[a.pts.length - 1], 'vertice'); }
    }
    archi.length = 0;
    // via i vertici sulle cuciture dei cerchi e le metà della linea di cucitura dei fori (non sono spigoli veri)
    for (let i = out.length - 1; i >= 0; i--) {
      const c = out[i];
      const suCucitura = p => cuciture.some(q => q.distanceTo(p) < 1e-3);
      if ((c.tipo === 'vertice' && suCucitura(c.p)) || (c.tipo === 'metà' && c.capi && c.capi.every(suCucitura))) out.splice(i, 1);
    }
  };
  if (flatView && !SK && S?.sheet?.data) {                  // lo sviluppo a video
    flatGroup.updateMatrixWorld(true);
    const M = flatGroup.matrixWorld, d = S.sheet.data;
    for (const anello of d.outline) {
      const pts = [];
      for (let i = 0; i + 1 < anello.length; i += 2) pts.push(new THREE.Vector3(anello[i], anello[i + 1], 0).applyMatrix4(M));
      if (pts.length > 2) pts.push(pts[0].clone());
      if (pts.length > 8) daPolilinea(pts);
      for (let i = 0; i + 1 < pts.length; i++) daPolilinea([pts[i], pts[i + 1]]);
    }
    for (const [a, b] of d.bend_lines) daPolilinea([new THREE.Vector3(a[0], a[1], 0).applyMatrix4(M), new THREE.Vector3(b[0], b[1], 0).applyMatrix4(M)]);
    chiudiArchi();
    return out;
  }
  for (const o of objs.values()) {
    if (!o.mesh.visible || !o.data.edges) continue;
    o.mesh.updateMatrixWorld(true);
    const M = o.mesh.matrixWorld;
    for (const e of o.data.edges) {
      const pts = [];
      for (let i = 0; i + 2 < e.length; i += 3) pts.push(new THREE.Vector3(e[i], e[i + 1], e[i + 2]).applyMatrix4(M));
      daPolilinea(pts);
    }
    chiudiArchi();                                  // per pezzo: i cerchi di due copie non si mescolano
  }
  return out;
}
function misStart() {
  if (SK) { toast('Nel disegno c’è già la Quota del disegno (tasto D).'); return; }
  MIS = { a: null, cand: misCandidati(), hover: null };
  document.querySelectorAll('[data-cmd="misura"]').forEach(b => b.classList.add('on'));
  setHelp('Quota: clic sul primo punto (vertice, metà, centro) e sul secondo · clic sul bordo di un foro = diametro · tasto destro su una quota per toglierla · Esc finisce');
  $('#sk-foot').hidden = false;
}
function misStop() {
  MIS = null;
  document.querySelectorAll('[data-cmd="misura"]').forEach(b => b.classList.remove('on'));
  misSnap.style.display = 'none';
  setHelp(''); if (!SK && !DRESS) $('#sk-foot').hidden = true;
  disegnaMisure();
}
function misTrova(ev) {
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const scr = p => { const q = p.clone().project(camera); return [(q.x + 1) / 2 * r.width, (1 - q.y) / 2 * r.height, q.z]; };
  let best = null;
  for (const c of MIS.cand) {
    const [x, y, z] = scr(c.p);
    if (z > 1) continue;
    const d = Math.hypot(x - mx, y - my) - (c.tipo === 'metà' ? -3 : 0);          // vertici e centri prima delle metà
    if (d < 12 && (!best || d < best.d)) best = { ...c, d };
  }
  if (best) return best;
  for (const c of MIS.cand) {                     // sul bordo di un foro: il diametro
    if (c.tipo !== 'centro' || !c.giro) continue;
    for (let i = 0; i + 1 < c.giro.length; i++) {
      const [ax, ay] = scr(c.giro[i]), [bx, by] = scr(c.giro[i + 1]);
      const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((mx - ax) * dx + (my - ay) * dy) / L));
      if (Math.hypot(mx - ax - t * dx, my - ay - t * dy) < 6) return { p: c.p, tipo: 'cerchio', r: c.r, giro: c.giro };
    }
  }
  const h = pick(ev);                             // nessun aggancio: il punto sotto il mouse sulla superficie
  if (h) {
    const rr = canvas.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(((ev.clientX - rr.left) / rr.width) * 2 - 1, -((ev.clientY - rr.top) / rr.height) * 2 + 1), camera);
    const hit = ray.intersectObjects([...objs.values()].map(o => o.mesh), false)[0];
    if (hit) return { p: hit.point.clone(), tipo: 'punto' };
  }
  return null;
}
const NOMI_AGGANCIO = { vertice: 'vertice', 'metà': 'metà dello spigolo', centro: 'centro', cerchio: 'bordo del foro: clic = diametro', punto: 'sulla faccia' };
function misMove(ev) {
  MIS.hover = misTrova(ev);
  const h = MIS.hover, r = view.getBoundingClientRect();
  if (h) {
    const q = h.p.clone().project(camera);
    misSnap.style.display = 'block';
    misSnap.style.left = ((q.x + 1) / 2 * r.width) + 'px'; misSnap.style.top = ((1 - q.y) / 2 * r.height) + 'px';
    misSnap.className = 'mis-' + (h.tipo === 'metà' ? 'meta' : h.tipo);
    tip.textContent = MIS.a ? `${num(MIS.a.p.distanceTo(h.p), 2)} mm · ${NOMI_AGGANCIO[h.tipo]}` : NOMI_AGGANCIO[h.tipo];
    tip.style.left = (ev.clientX - r.left + 14) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px'; tip.style.display = 'block';
  } else { misSnap.style.display = 'none'; tip.style.display = 'none'; }
  disegnaMisure();
}
function misClick(ev) {
  const h = MIS.hover || misTrova(ev);
  if (!h) return;
  if (h.tipo === 'cerchio' && !MIS.a) {
    const lontano = h.giro.reduce((m, q) => (q.distanceTo(h.giro[0]) > m.distanceTo(h.giro[0]) ? q : m), h.giro[0]);
    quoteDi().push({ a: h.giro[0].toArray(), b: lontano.toArray(), testo: 'Ø' + num(2 * h.r, 2) });
    disegnaMisure(); return;
  }
  if (!MIS.a) { MIS.a = h; disegnaMisure(); return; }
  const a = MIS.a.p, b = h.p, d = a.distanceTo(b);
  if (d < 1e-6) return;
  const dx = Math.abs(b.x - a.x), dy = Math.abs(b.y - a.y), dz = Math.abs(b.z - a.z);
  quoteDi().push({ a: a.toArray(), b: b.toArray(), testo: num(d, 2), dett: `ΔX ${num(dx, 2)} · ΔY ${num(dy, 2)} · ΔZ ${num(dz, 2)}` });
  MIS.a = null;
  disegnaMisure();
}
function disegnaMisure() {
  misGroup.traverse(x => x.geometry?.dispose()); misGroup.clear();
  misBox.innerHTML = ''; misEls = [];
  const lista = SK ? [] : quoteDi();
  lista.forEach((q, k) => {
    const a = new THREE.Vector3(...q.a), b = new THREE.Vector3(...q.b);
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), MIS_MAT); l.renderOrder = 30; misGroup.add(l);
    for (const p of [a, b]) {
      const g = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.6, modelRadius * 0.004), 10, 8), new THREE.MeshBasicMaterial({ color: 0xFFB000, depthTest: false }));
      g.position.copy(p); g.renderOrder = 30; misGroup.add(g);
    }
    const el = document.createElement('div');
    el.className = 'dim mis'; el.textContent = q.testo; el.title = (q.dett ? q.dett + '\n' : '') + 'Tasto destro: togli questa quota';
    el.oncontextmenu = ev => { ev.preventDefault(); quoteDi().splice(k, 1); disegnaMisure(); };
    misBox.appendChild(el);
    misEls.push({ el, at: a.clone().add(b).multiplyScalar(0.5) });
  });
  if (MIS?.a && MIS.hover) {
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([MIS.a.p, MIS.hover.p]), MIS_RUB);
    l.computeLineDistances(); l.renderOrder = 30; misGroup.add(l);
  }
  placeDims(); ridisegna();
}
function misTogliTutte() { quoteDi().length = 0; disegnaMisure(); }
document.addEventListener('keydown', ev => {
  if (!MIS || ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
  if (ev.key === 'Escape') { ev.stopPropagation(); ev.preventDefault(); if (MIS.a) { MIS.a = null; disegnaMisure(); } else misStop(); }
}, true);

// ===================================================================== tavole
async function drawingsDialog() {
  const r = await call('drawing_fields');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const c = r.fields;
  const campo = (k, l, w = '') => `<label${w}>${l}<input class="field" data-c="${k}" value="${esc(c[k] || '')}"></label>`;
  modal(`<div class="tav"><div class="tav-side"><h3>Tavole</h3>
      <div class="form">${campo('azienda', 'Azienda', ' style="grid-column:1/-1"')}${campo('disegnatore', 'Disegnatore')}${campo('numero', 'N. disegno')}
      ${campo('revisione', 'Revisione')}<label>Formato<select class="field" data-c="formato">${['A4', 'A3', 'A2'].map(f => `<option${c.formato === f ? ' selected' : ''}>${f}</option>`).join('')}</select></label>
      <label>Scala<select class="field" data-c="scala_fissa">${['auto', '2:1', '1:1', '1:2', '1:2,5', '1:5', '1:10', '1:20'].map(x => `<option${(c.scala_fissa || 'auto') === x ? ' selected' : ''}>${x}</option>`).join('')}</select></label>
      <label>Quote dei fori<select class="field" data-c="quote_fori">${['sì', 'no'].map(x => `<option${(c.quote_fori || 'sì') === x ? ' selected' : ''}>${x}</option>`).join('')}</select></label>
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
    // il formato cambia l'impaginazione: l'anteprima si rifà subito, così il PDF è uguale a quello che vedi
    document.querySelector('#modal-box [data-c="formato"]')?.addEventListener('change', anteprima);
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
    <div class="sub">Bumping (raggio grande a colpi)</div>
    <div class="ff"><label>Colpi<input class="field" id="f-colpi" value="${esc(String(d.bump?.colpi ?? ''))}" placeholder="vuoto = piega normale"></label>
      <label>Raggio grande<span class="inp"><input class="field" id="f-rg" value="${esc(String(d.bump?.raggio ?? '').replace('.', ','))}"><i>mm</i></span></label></div>
    ${s.colpi?.length ? `<p class="hint" style="margin:4px 0">Battuta dei colpi (dalla linea, nello sviluppo): ${s.colpi.map(c => num(c, 1)).join(' · ')} mm</p>` : ''}
    <p class="hint">La lunghezza la calcolo io: quella che serve perché lo sviluppo resti quello disegnato.</p>
    ${rigaPiega(s.rows.filter(r => r[0] !== 'Piega su linea'))}`;
}
function wireFold(s) {
  const edit = f => inCoda(async () => { if (await apply(await call('edit_fold', s.feature, s.fold, f))) await refreshSel(); });
  $('#f-ang').onkeydown = ev => { if (ev.key === 'Enter') edit({ angle: $('#f-ang').value.trim() }); };
  $('#f-ang').onchange = () => edit({ angle: $('#f-ang').value.trim() });
  $('#f-dir').onchange = () => edit({ direction: $('#f-dir .on').dataset.v });
  $('#f-flip').onclick = () => edit({ flip: !s.def.flip });
  const bump = () => edit({ bump: $('#f-colpi').value.trim() ? { colpi: $('#f-colpi').value.trim(), raggio: $('#f-rg').value.trim() } : null });
  ['#f-colpi', '#f-rg'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') bump(); }; $(q).onchange = bump; });
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
  $('#f-fatto').onclick = () => { applica(); clearSelection(); };
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
    $('#t-gradino').onclick = () => {
      const sp = String(S?.sheet?.data?.thickness ?? 2).replace('.', ',');
      modal(`<h3>Gradino sulla punta di ${esc(s.flange)}</h3>
        <p class="hint">La parete si sposta di poco e continua parallela: due lamiere si sovrappongono a filo (di solito il gradino è lo spessore).</p>
        <div class="form"><label>Di quanto si sposta<span class="inp"><input class="field" id="g-h" value="${sp}"><i>mm</i></span></label>
          <label>Verso<select class="field" id="g-v"><option value="dentro">verso dentro</option><option value="fuori">verso fuori</option></select></label>
          <label>Angolo del tratto inclinato<span class="inp"><input class="field" id="g-a" value="45"><i>°</i></span></label>
          <label>Lunghezza dopo il gradino<span class="inp"><input class="field" id="g-l" value="20"><i>mm</i></span></label></div>
        <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fai il gradino</button></div>`, close => {
        $('#m-no').onclick = close;
        $('#m-ok').onclick = () => {
          const v = ['#g-h', '#g-a', '#g-l'].map(q => $(q).value.trim()), verso = $('#g-v').value;
          close();
          inCoda(async () => { const r = await call('gradino', s.feature, s.flange, v[0], v[1], v[2], verso); if (await apply(r, r.message)) await refreshSel(); });
        };
      });
    };
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
  if (cut.hidden && !$('#tab-cut').hidden) showTab('bom');
  $('#tab-btn-sheet').hidden = !sh;
  if (!sh) { if (!$('#tab-sheet').hidden) showTab('bom'); return; }
  const d = sh.def, manca = new Set(sh.missing || []);
  // lo spessore può essere un parametro (sp): si vede il valore, e cambiandolo cambia il parametro
  const parSp = typeof d.thickness === 'string' ? S.parameters.find(p => p.name === d.thickness) : null;
  const vede = k => (k === 'thickness' && parSp ? parSp.resolved ?? parSp.value : d[k]);
  const campo = (k, label, miss) => `<label for="t-${k}">${label}</label><input class="field${miss ? ' missing' : ''}" id="t-${k}" data-tech="${k}"
      value="${esc(vede(k) == null ? '' : String(vede(k)).replace('.', ','))}" placeholder="${miss ? 'manca: dato della piegatrice' : ''}">`;
  const tech = `<div class="tech">${campo('thickness', parSp ? `Spessore (mm) <small title="È il parametro ${esc(parSp.name)}: cambiandolo qui cambia anche lui">= ${esc(parSp.name)}</small>` : 'Spessore (mm)', false)}${campo('radius', 'Raggio interno (mm)', manca.has('raggio interno'))}
    <label for="t-method">Calcolo della piega</label><select class="field" id="t-method">${opts(sh.methods, d.method || 'k')}</select>
    ${d.method === 'bd90' ? campo('bd90', 'Deduzione a 90° (mm)', manca.has('deduzione a 90°')) : d.method === 'din6935' ? '' : campo('k', 'K-factor', manca.has('K-factor'))}</div>
    ${manca.size ? `<div class="msg err">Mancano: ${esc([...manca].join(', '))}. Sono dati della tua piegatrice: senza, le flange non si possono calcolare.</div>` : ''}
    ${sh.after.length ? `<div class="msg warn">Dopo la lamiera ci sono altre lavorazioni (${esc(sh.after.join(', '))}): lo sviluppo non le contiene.</div>` : ''}`;
  const data = sh.data;
  const pieghe = data && data.bend_rows ? (data.bend_rows.length ? `<table class="grid"><thead><tr><th>Piega</th><th class="n">Angolo</th><th class="n">Linea mm</th><th class="n">Correzione mm</th></tr></thead><tbody>
    ${data.bend_rows.map(b => `<tr><td>P${b.n}</td><td class="n">${num(b.angle, 2)}°</td><td class="n">${num(b.length, 1)}</td><td class="n">${b.correction == null ? '' : num(b.correction, 3)}</td></tr>`).join('')}</tbody></table>
    <p class="hint">Correzione totale ${num(data.shape_info?.correzione_totale || 0, 2)} mm, già messa nello sviluppo.</p>`
    : `<p class="hint">Calandrato: nessuna piega. Corona con raggi ${num(data.shape_info?.raggio_grande, 2)} e ${num(data.shape_info?.raggio_piccolo, 2)} mm, settore ${num(data.shape_info?.angolo_settore, 3)}°.</p>`)
    : data && data.bends.length ? `<table class="grid"><thead><tr><th>Flangia</th><th>Lato</th><th class="n">L</th><th class="n">Angolo</th><th>Verso</th>
    <th class="n" title="Raggio interno di piega (mm)">Raggio</th><th class="n" title="K-factor: dove sta la fibra neutra nello spessore">K</th><th class="n" title="Allungamento (BA): lunghezza della fibra neutra nella piega, mm">Allung.</th><th class="n" title="Detrazione (BD): quanto si toglie alla somma delle quote esterne, mm">Detraz.</th></tr></thead><tbody>${data.bends.map(b => `<tr data-fl="${esc(b.flange)}">
    <td>${esc(b.flange)}</td><td>${esc(b.edge)}</td><td class="n">${num(b.length, 2)}</td><td class="n">${num(b.angle, 2)}°</td><td>${b.position === 'outside' && b.parent !== undefined && String(b.flange).match(/\/u[01]$|^PB/) ? (b.direction === 'up' ? 'dentro' : 'fuori') : (b.direction === 'up' ? 'su' : 'giù')}</td>
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
      <p class="hint">Per esportarlo: <b>Esporta</b> nella barra in alto.</p>`;
  }
  const attivo = document.activeElement?.dataset?.tech ? { k: document.activeElement.dataset.tech, v: document.activeElement.value } : null;
  $('#tab-sheet').innerHTML = `<div class="sheet-cols"><div><h4>Dati di piega</h4>${tech}</div><div><h4>Pieghe</h4>${pieghe}</div><div><h4>Sviluppo</h4>${flat}</div></div>`;
  if (attivo) {               // stavi scrivendo in un campo: il ridisegno non ti toglie quello che hai scritto
    const i = document.querySelector(`[data-tech="${attivo.k}"]`);
    if (i) { i.value = attivo.v; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
  }
  $('#sheet-badge').textContent = manca.size ? '!' : '';
  const salva = fields => inCoda(async () => apply(parSp && 'thickness' in fields
    ? await call('set_parameter', parSp.name, fields.thickness) : await call('set_sheet_tech', sh.feature, fields)));
  document.querySelectorAll('[data-tech]').forEach(i => {
    const ora = vede(i.dataset.tech) == null ? '' : String(vede(i.dataset.tech)).replace('.', ',');
    i.onkeydown = ev => { if (ev.key === 'Enter') salva({ [i.dataset.tech]: i.value }); };
    i.onblur = () => { if (i.value.trim() !== ora) salva({ [i.dataset.tech]: i.value }); };
  });
  $('#t-method').onchange = () => salva({ method: $('#t-method').value });
  document.querySelectorAll('#tab-sheet tr[data-fl]').forEach(tr => {   // le pieghe su un bordo libero sono «PB…»
    tr.onclick = () => select(tr.dataset.fl.startsWith('PB') ? `pb=${tr.dataset.fl}` : `flange=${sh.feature}/${tr.dataset.fl}`);
  });
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
  // la barretta del pannello chiuso: quante righe e quanti kg, e se c'è qualcosa da guardare
  const sum = [b.length ? `Distinta: ${b.length === 1 ? '1 riga' : b.length + ' righe'} · ${kg(S.bom_kg)} kg` : 'Distinta vuota'];
  if (S.sheet?.missing?.length) sum.push('Lamiera: mancano dati di piega');
  if (n) sum.push(`${n} ${n === 1 ? 'avviso' : 'avvisi'}`);
  $('#bottom-sum').textContent = sum.join(' · ');
}
// pannello in basso: chiuso è una barretta col riassunto; si apre al clic. Si ricorda aperto/chiuso.
let bassoAperto = false;
try { bassoAperto = localStorage.getItem('steelcad.pannello') === 'aperto'; } catch { /* va bene chiuso */ }
function setBottom(aperto) {
  bassoAperto = aperto;
  document.body.classList.toggle('bottom-closed', !aperto);
  $('#bottom-arrow').textContent = aperto ? '▾' : '▴';
  $('#bottom-toggle').title = aperto ? 'Chiudi il pannello in basso (più spazio al 3D)' : 'Apri il pannello in basso';
  try { localStorage.setItem('steelcad.pannello', aperto ? 'aperto' : 'chiuso'); } catch { /* niente */ }
}
function showTab(t, apri = false) {
  for (const x of document.querySelectorAll('.tabs button[data-tab]')) x.classList.toggle('on', x.dataset.tab === t);
  for (const k of ['bom', 'cut', 'sheet', 'info']) $('#tab-' + k).hidden = k !== t;
  if (apri && !bassoAperto) setBottom(true);
}
setBottom(bassoAperto);
$('#bottom-toggle').addEventListener('click', () => setBottom(!bassoAperto));
$('#tab-cut').addEventListener('click', ev => {
  const tr = ev.target.closest('tr[data-ids]');
  if (!tr || !tr.dataset.ids) return;
  const ids = tr.dataset.ids.split(',').filter(id => objs.has(id));
  if (ids.length) select(ids[0], null, ids.length > 1 ? ids : null);
});
document.querySelector('.tabs').addEventListener('click', ev => {
  const b = ev.target.closest('button[data-tab]');
  if (!b) return;
  showTab(b.dataset.tab, true);
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
  $('#modal-box').classList.remove('wide', 'nuovo');
  $('#modal-box').innerHTML = html;
  $('#modal').hidden = false;
  const close = () => { $('#modal').hidden = true; };
  wire(close);
  $('#modal-box').querySelector('input, button.primary')?.focus();
}

const virgola = v => (v === null || v === undefined ? '' : String(v).replace('.', ','));
// dalla pagina iniziale (daHome) la finestra mostra solo il tipo scelto e le sue misure; da Ctrl+N anche
// la scelta del tipo, con gli stessi nomi e gruppi della pagina iniziale
// ------------------------------------------------------------- pezzo nuovo: le misure sul disegno
// Ogni misura ha una lettera sul disegno e la stessa lettera accanto alla casella; sotto, a parole, cosa viene
// fuori (calcolato dal motore mentre si scrive). Raggio, K e passo delle pieghe stanno in "Altro".
const DISEGNI = (() => {
  const b = (x, y, l) => `<g class="lt"><circle cx="${x}" cy="${y}" r="15"/><text x="${x}" y="${y + 6}">${l}</text></g>`;
  const qo = (x1, x2, y) => `<path class="q" d="M${x1} ${y}H${x2}M${x1} ${y - 7}v14M${x2} ${y - 7}v14"/>`;
  const qv = (x, y1, y2) => `<path class="q" d="M${x} ${y1}V${y2}M${x - 7} ${y1}h14M${x - 7} ${y2}h14"/>`;
  const svg = c => `<svg viewBox="0 0 520 380" role="img" aria-label="Disegno con le misure">${c}</svg>`;
  const scaff = (chiuso) => svg(`<g class="ln">
      <rect x="150" y="50" width="200" height="280"/>${chiuso ? '' : ''}
      <path d="M150 120h200M150 190h200M150 260h200"/><path d="M350 50l60-28v280l-60 28M150 50l60-28h200"/></g>
      ${qo(150, 350, 355)}${b(250, 355, 'A')}<path class="q" d="M362 62l60-28M357 52l10 20M417 24l10 20"/>${b(410, 58, 'B')}${qv(115, 50, 330)}${b(115, 190, 'C')}
      <text class="nota" x="232" y="160">D piani</text>`);
  return {
    lamiera: svg(`<g class="ln"><path class="pz" d="M70 230l230 80 160-110-230-70z"/><path d="M70 230v12l230 80v-12M300 322l160-110v-12"/></g>
      <path class="q" d="M62 262l230 80M58 250l8 24M288 330l8 24"/>${b(170, 318, 'A')}
      <path class="q" d="M318 336l160-110M306 330l20 12M466 220l20 12"/>${b(410, 300, 'B')}
      <path class="q" d="M50 230v12"/>${b(30, 236, 'C')}`),
    piastra: svg(`<g class="ln"><rect class="pz" x="90" y="60" width="300" height="220"/><circle cx="240" cy="170" r="34"/>
      <rect class="pz" x="430" y="60" width="18" height="220"/></g>
      ${qo(90, 390, 315)}${b(240, 315, 'A')}${qv(55, 60, 280)}${b(55, 170, 'B')}
      <path class="q" d="M206 170h68"/>${b(240, 120, 'C')}${qo(430, 448, 315)}${b(439, 345, 'D')}`),
    telaio: svg(`<g class="ln"><path d="M80 120l250 60 140-70-250-50z"/><path d="M80 120v190M330 180v190M470 110v190M220 60v150"/></g>
      <path class="q" d="M70 330l250 60"/>${b(190, 372, 'A')}<path class="q" d="M345 392l140-70"/>${b(430, 372, 'B')}
      ${qv(40, 120, 310)}${b(40, 215, 'C')}`),
    scaffale: scaff(false),
    armadio: scaff(true),
    cancello: svg(`<g class="ln"><rect class="pz" x="60" y="60" width="400" height="240"/><rect x="72" y="72" width="376" height="216"/>
      <path d="M110 72v216M150 72v216M190 72v216M230 72v216M270 72v216M310 72v216M350 72v216M390 72v216M430 72v216"/></g>
      ${qo(60, 460, 335)}${b(260, 335, 'A')}${qv(28, 60, 300)}${b(28, 180, 'B')}${qo(150, 190, 40)}${b(170, 40, 'C')}`),
    cono: svg(`<g class="ln"><path class="pz" d="M180 70h160l80 240H100z"/><ellipse cx="260" cy="70" rx="80" ry="12"/></g>
      ${qo(100, 420, 345)}${b(260, 345, 'A')}${qo(180, 340, 35)}${b(260, 35, 'B')}${qv(455, 70, 310)}${b(455, 190, 'C')}`),
    tramoggia: svg(`<g class="ln"><path class="pz" d="M70 300l170 50 210-80-170-40z"/><ellipse cx="270" cy="90" rx="70" ry="22"/>
      <path d="M70 300L200 90M240 350L270 112M450 270L340 90M280 230L240 70"/></g>
      <path class="q" d="M62 330l170 50"/>${b(140, 358, 'A')}<path class="q" d="M248 380l210-80"/>${b(370, 352, 'B')}
      <path class="q" d="M200 52h140"/>${b(270, 40, 'C')}${qv(490, 90, 270)}${b(490, 180, 'D')}`),
  };
})();

function newDialog(iniziale = 'lamiera', daHome = false) {
  // campi: k = parametro del modello, l = come si chiama, v = valore proposto, lettera sul disegno,
  // scelte = elenco, prof = un tubo/profilo (con i suggerimenti), altro = sotto "Altro" (chiuso)
  const BD = S?.bend_default || {};
  // raggio e K: in "Altro" se ci sono già quelli della piegatrice (Regole), se no in vista perché vanno scritti
  const conPiegatrice = BD.radius != null && BD.k != null;
  const piega = [{ k: 'raggio', l: 'Raggio interno di piega', v: virgola(BD.radius), altro: conPiegatrice, unit: 'mm' },
    { k: 'k', l: 'K-factor', v: virgola(BD.k), altro: conPiegatrice }];
  const RIF = { esterno: 'fuori tutto (finite)', interno: 'dentro', asse: 'in asse lamiera' };
  const MODELLI = {
    lamiera: { titolo: 'Lamiera', nota: 'Un rettangolo dello spessore che vuoi: se serve lo pieghi dopo, cliccando i bordi.', nome: 'Lamiera',
      campi: [{ k: 'larghezza', l: 'Larghezza', v: 500, lettera: 'A' }, { k: 'profondita', l: 'Profondità', v: 300, lettera: 'B' },
        { k: 'spessore', l: 'Spessore', v: 2, lettera: 'C' }, ...piega] },
    piastra: { titolo: 'Piastra piana', nota: 'Piastra con un foro; gli altri fori li aggiungi dopo.', nome: 'Piastra',
      campi: [{ k: 'larghezza', l: 'Larghezza', v: 300, lettera: 'A' }, { k: 'altezza', l: 'Altezza', v: 200, lettera: 'B' },
        { k: 'foro', l: 'Diametro del foro', v: 30, lettera: 'C' }, { k: 'spessore', l: 'Spessore', v: 5, lettera: 'D' }] },
    zero: { titolo: 'Una forma disegnata', nota: 'Disegni il contorno con le linee; poi diventa lamiera o piastra.', nome: 'Pezzo', campi: [] },
    telaio: { titolo: 'Telaio o banco', nota: 'Misure in asse dei tubi: sotto vedi il fuori tutto.', nome: 'Banco',
      campi: [{ k: 'L', l: 'Lunghezza', v: 2000, lettera: 'A' }, { k: 'P', l: 'Profondità', v: 1000, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 900, lettera: 'C' }, { k: 'profilo', l: 'Tubo del telaio', v: '40x40x3', prof: true },
        { k: 'gambe', l: 'Tubo delle gambe', v: '40x40x3', prof: true }] },
    scaffale: { titolo: 'Scaffale o telaio', nota: 'Scaffali e telai per armadi. Misure in asse dei tubi: sotto vedi il fuori tutto. Tubi uguali? Scrivi lo stesso nei due campi.', nome: 'Scaffale',
      campi: [{ k: 'L', l: 'Larghezza', v: 1000, lettera: 'A' }, { k: 'P', l: 'Profondità', v: 400, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 1800, lettera: 'C' }, { k: 'ripiani', l: 'Quanti piani (a terra e in cima compresi)', v: 4, lettera: 'D' },
        { k: 'montanti', l: 'Tubo dei montanti', v: '30x30x2', prof: true }, { k: 'traversi', l: 'Tubo dei traversi', v: '40x20x2', prof: true }] },
    armadio: { titolo: 'Telaio per armadio', nota: 'Misure in asse dei tubi: sotto vedi il fuori tutto.', nome: 'Telaio armadio',
      campi: [{ k: 'L', l: 'Larghezza', v: 800, lettera: 'A' }, { k: 'P', l: 'Profondità', v: 600, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 2000, lettera: 'C' }, { k: 'ripiani', l: 'Quanti livelli (sotto e sopra compresi)', v: 3, lettera: 'D' },
        { k: 'profilo', l: 'Tubo', v: '40x40x2', prof: true }] },
    cancello: { titolo: 'Cancello', nota: 'Misure in asse dei tubi: sotto vedi il fuori tutto.', nome: 'Cancello',
      campi: [{ k: 'L', l: 'Larghezza', v: 1500, lettera: 'A' }, { k: 'H', l: 'Altezza', v: 1200, lettera: 'B' },
        { k: 'passo', l: 'Distanza tra le sbarre, circa', v: 120, lettera: 'C' },
        { k: 'telaio', l: 'Tubo del telaio', v: '60x60x3', prof: true }, { k: 'sbarre', l: 'Tubo delle sbarre', v: '20x20x2', prof: true }] },
    disegno: { titolo: 'Struttura disegnata da te', nota: 'Tracci le linee dello scheletro: diventano tubi.', nome: 'Struttura',
      campi: [{ k: 'piano', l: 'Da dove la guardi mentre la disegni', v: 'XZ',
        scelte: { XZ: 'Di fronte: cancelli, spalle, portali', XY: 'Dall’alto: basamenti, telai a terra', YZ: 'Di fianco' } }] },
    cono: { titolo: 'Cono o tronco di cono', nota: 'Misure finite del pezzo.', nome: 'Tronco di cono',
      campi: [{ k: 'D1', l: 'Diametro grande', v: 400, lettera: 'A' }, { k: 'D2', l: 'Diametro piccolo (0 = a punta)', v: 200, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 300, lettera: 'C' }, { k: 'spessore', l: 'Spessore', v: 2 },
        { k: 'modo', l: 'Come lo fai', v: 'press', scelte: { press: 'a pieghe, con la piegatrice', rolled: 'calandrato' } },
        { k: 'riferimento', l: 'Le misure sono', v: 'esterno', scelte: RIF },
        { k: 'passo', l: 'Distanza tra le pieghe sul bordo (vuoto = dal raggio)', v: '', altro: true, unit: 'mm' }, ...piega] },
    tramoggia: { titolo: 'Raccordo quadro-tondo', nota: 'Misure finite del pezzo.', nome: 'Raccordo quadro-tondo',
      campi: [{ k: 'A', l: 'Lato lungo della base', v: 600, lettera: 'A' }, { k: 'B', l: 'Lato corto della base', v: 400, lettera: 'B' },
        { k: 'D', l: 'Diametro del tondo', v: 250, lettera: 'C' }, { k: 'H', l: 'Altezza', v: 300, lettera: 'D' },
        { k: 'spessore', l: 'Spessore', v: 2 },
        { k: 'ex', l: 'Tondo spostato di lato (X)', v: 0, altro: true, unit: 'mm' }, { k: 'ey', l: 'Tondo spostato avanti/dietro (Y)', v: 0, altro: true, unit: 'mm' },
        { k: 'rif_base', l: 'Misure della base', v: 'esterno', scelte: RIF, altro: true }, { k: 'rif_tondo', l: 'Misure del tondo', v: 'esterno', scelte: RIF, altro: true },
        { k: 'passo', l: 'Distanza tra le pieghe sul tondo (vuoto = dal raggio)', v: '', altro: true, unit: 'mm' }, ...piega] },
    tramoggia_cassone: { titolo: 'Tramoggia con cassone', nota: 'Cassone e tramoggia a falde, divisa in pezzi da piegare (più pieghe possibile nel foglio).', nome: 'Tramoggia',
      campi: [{ k: 'A', l: 'Bocca: lato A', v: 1000, lettera: 'A' }, { k: 'B', l: 'Bocca: lato B', v: 1000, lettera: 'B' },
        { k: 'Hc', l: 'Altezza del cassone (0 = solo tramoggia)', v: 700 }, { k: 'a', l: 'Scarico: lato a', v: 250 }, { k: 'b', l: 'Scarico: lato b', v: 250 },
        { k: 'Ht', l: 'Altezza della tramoggia', v: 700 }, { k: 'spessore', l: 'Spessore', v: 3 },
        { k: 'bordo', l: 'Bordo in alto (0 = niente)', v: 40, altro: true, unit: 'mm' },
        { k: 'angoli_bordo', l: 'Angoli dei bordi', v: 'aperti', scelte: { aperti: 'aperti (scasso, più pieghe)', 45: 'a 45° (da saldare)' }, altro: true },
        { k: 'flangia', l: 'Flangia allo scarico (0 = niente)', v: 0, altro: true, unit: 'mm' }, { k: 'smusso', l: 'Angoli smussati (0 = vivi)', v: 0, altro: true, unit: 'mm' },
        { k: 'ex', l: 'Scarico spostato di lato (X)', v: 0, altro: true, unit: 'mm' }, { k: 'ey', l: 'Scarico spostato avanti/dietro (Y)', v: 0, altro: true, unit: 'mm' },
        { k: 'riferimento', l: 'Le misure sono', v: 'esterno', scelte: RIF },
        { k: 'divisione', l: 'Divisione in pezzi', v: 'auto', scelte: { auto: 'automatica (meno saldature)', verticali: 'pieghe sugli spigoli verticali', tramoggia: 'pieghe sugli spigoli della tramoggia', lati: 'un pezzo per lato' }, altro: true },
        { k: 'foglio', l: 'Foglio', v: '1500x3000', altro: true }, ...piega] },
    vuoto: { titolo: 'Struttura nodo per nodo', nota: 'Parti da un nodo e tiri le aste.', nome: 'Struttura', campi: [] },
  };
  const GRUPPI = [['Lamiera', ['lamiera', 'zero']], ['Forme', ['cono', 'tramoggia', 'tramoggia_cassone']],
    ['Strutture', ['telaio', 'scaffale', 'cancello', 'disegno', 'vuoto']]];
  let kind = iniziale in MODELLI ? iniziale : 'lamiera';
  const numerico = c => !c.scelte && !c.prof && typeof c.v === 'number';
  const casella = c => {
    const lettera = c.lettera ? `<span class="nl">${c.lettera}</span>` : '<span class="nl vuota"></span>';
    if (c.scelte) return `<label class="nc">${lettera}<span class="nt">${esc(c.l)}</span><select class="field" data-f="${c.k}">${Object.entries(c.scelte)
      .map(([a, t]) => `<option value="${a}"${a === c.v ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
    return `<label class="nc">${lettera}<span class="nt">${esc(c.l)}</span><span class="nv"><input class="field" data-f="${c.k}" value="${esc(virgola(c.v))}"
      ${c.prof ? 'list="n-profili"' : ''} autocomplete="off">${numerico(c) || c.unit ? `<small>${c.unit || (c.k === 'ripiani' ? '' : 'mm')}</small>` : ''}</span></label>`;
  };
  const disegna = () => {
    const m = MODELLI[kind];
    const visibili = m.campi.filter(c => !c.altro), altri = m.campi.filter(c => c.altro);
    const scelta = daHome ? '' : `<div class="n-kinds choice">${GRUPPI.map(([g, ks]) => `<span>${g}</span>${ks.map(k =>
      `<button data-k="${k}" class="${k === kind ? 'on' : ''}">${esc(MODELLI[k].titolo)}</button>`).join('')}`).join('')}</div>`;
    const pic = DISEGNI[kind];
    const riassuntoPiega = altri.some(c => c.k === 'raggio') && conPiegatrice ? `Piegatrice: R ${esc(virgola(BD.radius) || '?')} · K ${esc(virgola(BD.k) || '?')}` : 'Altre misure';
    return `<h3>${daHome ? 'Nuovo: ' + esc(m.titolo) : 'Nuovo pezzo'}</h3>${scelta}
      <div class="n-main${pic ? '' : ' senza'}">
        ${pic ? `<div class="n-pic">${pic}</div>` : ''}
        <div class="n-campi">
          <p class="hint">${esc(m.nota)}</p>
          <label class="nc"><span class="nl vuota"></span><span class="nt">Nome del lavoro</span><span class="nv"><input class="field" id="n-name" value="${esc(m.nome)}"></span></label>
          ${visibili.map(casella).join('')}
          ${altri.length ? `<details class="n-altro"><summary>${riassuntoPiega}</summary>${altri.map(casella).join('')}</details>` : ''}
          <div class="n-ris" id="n-ris"></div>
        </div>
      </div>
      <datalist id="n-profili"></datalist>
      ${S?.dirty ? '<div class="msg warn">Il lavoro aperto ha modifiche non salvate: restano nel salvataggio automatico.</div>' : ''}
      <div class="acts"><button class="btn" id="n-no">Annulla</button><button class="btn primary big" id="n-ok">Crea ${esc(m.titolo.toLowerCase())}</button></div>`;
  };
  const valori = () => {
    const v = { name: $('#n-name').value.trim() || MODELLI[kind].nome };
    $('#modal-box').querySelectorAll('[data-f]').forEach(i => { v[i.dataset.f] = i.value.trim(); });
    return v;
  };
  // le caselle numeriche: una lettera o una virgola sbagliata si vede subito, senza il messaggio del motore
  const controlla = () => {
    let ok = true;
    for (const c of MODELLI[kind].campi.filter(numerico)) {
      const i = $(`#modal-box [data-f="${c.k}"]`);
      const giusto = /^\s*-?\d+([.,]\d+)?\s*$/.test(i.value);
      i.closest('.nc').classList.toggle('bad', !giusto);
      ok = ok && giusto;
    }
    return ok;
  };
  let timer = null, giro = 0;
  const riassunto = () => {
    clearTimeout(timer);
    const box = $('#n-ris');
    if (!box) return;
    if (!MODELLI[kind].campi.length || kind === 'disegno') { box.innerHTML = ''; return; }
    if (!controlla()) { box.className = 'n-ris warn'; box.textContent = 'Scrivi un numero nelle caselle segnate in rosso.'; return; }
    const mio = ++giro;
    timer = setTimeout(async () => {
      const r = await call('new_project_preview', kind, valori());
      if (mio !== giro || !$('#n-ris')) return;
      if (r.text) { box.className = 'n-ris ok'; box.textContent = r.text; } else if (r.warning) { box.className = 'n-ris warn'; box.textContent = r.warning; } else box.innerHTML = '';
    }, 350);
  };
  const wire = close => {
    $('#modal-box').classList.add('nuovo');
    $('#modal-box').querySelectorAll('.n-kinds button').forEach(b => b.onclick = () => { kind = b.dataset.k; $('#modal-box').innerHTML = disegna(); wire(close); });
    call('profile_suggestions').then(l => { const d = $('#n-profili'); if (d && Array.isArray(l)) d.innerHTML = l.map(x => `<option value="${esc(x)}">`).join(''); });
    $('#modal-box').querySelectorAll('[data-f]').forEach(i => { i.oninput = riassunto; i.onchange = riassunto; });
    riassunto();
    $('#n-no').onclick = close;
    $('#n-ok').onclick = () => {
      if (MODELLI[kind].campi.length && !controlla()) { riassunto(); return; }
      const v = valori();
      close();
      primaVolta = true; sel = null; clearSelection();
      if (SK) exitSketch();
      inCoda(async () => {
        if (!(await apply(await call('new_project', kind, v)))) return;
        hideHome();
        if (kind === 'zero' || kind === 'disegno') await enterSketch('S1');
        if (['scaffale', 'armadio', 'cancello', 'telaio'].includes(kind)) await select('struct=ST1');
        if (['cono', 'tramoggia', 'tramoggia_cassone'].includes(kind)) await select('body');
      });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter' && ev.target.tagName !== 'SUMMARY') $('#n-ok').click(); if (ev.key === 'Escape') close(); };
    setTimeout(() => { const f = $('#modal-box [data-f]'); if (f) { f.focus(); f.select?.(); } }, 30);
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
    <div class="sub">Predefinito per ogni lamiera nuova</div>
    <div class="form"><label>Raggio interno (mm)<input class="field" id="d-r" value="${n(r.default?.radius).replace('–', '')}"></label>
      <label>K-factor<input class="field" id="d-k" value="${n(r.default?.k).replace('–', '')}"></label></div>
    <div class="row-btns"><button class="btn" id="d-save">Salva come predefinito</button></div>
    <div class="sub">Regole salvate</div>
    <table class="grid">${righe}</table>
    ${fid ? `<div class="form" style="margin-top:12px"><label style="grid-column:1/-1">Salva i dati di piega di questa lamiera come
      <input class="field" id="r-name" placeholder="es. S235 sp. 2 – matrice V16"></label></div>` : '<p class="hint">Apri o crea una lamiera per usare o salvare una regola.</p>'}
    <div class="acts"><button class="btn" id="m-no">Chiudi</button>${fid ? '<button class="btn primary" id="r-save">Salva regola</button>' : ''}</div>`, close => {
    $('#m-no').onclick = close;
    $('#d-save').onclick = () => inCoda(async () => {
      const x = await call('set_bend_default', { radius: $('#d-r').value.trim(), method: 'k', k: $('#d-k').value.trim() });
      toast(x.message, x.ok ? '' : 'err');
      if (x.ok) { S.bend_default = x.default; close(); rulesDialog(); }
    });
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
      const vai = rec => { close(); primaVolta = true; clearSelection(); inCoda(async () => { if (await apply(await call('open_path', r.path, rec), rec ? 'Modifiche recuperate.' : null)) { hideHome(); fotoAnteprima(S.path); } }); };
      $('#r-no').onclick = () => vai(false); $('#r-ok').onclick = () => vai(true);
    });
    return;
  }
  if (r.ok) { primaVolta = true; clearSelection(); }
  if (await apply(r)) { hideHome(); fotoAnteprima(S.path); }
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
        <label>Raggio interno<input class="field" id="imp-r" placeholder="mm" value="${virg(S?.bend_default?.radius)}"></label>
        <label>Metodo<select class="field" id="imp-met"><option value="k">K-factor</option><option value="din6935">DIN 6935</option><option value="bd90">Deduzione 90°</option></select></label>
        <label id="imp-k-l">K-factor<input class="field" id="imp-k" placeholder="es. 0,4" value="${virg(S?.bend_default?.k)}"></label>
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
  // i lavori recenti con l'anteprima vera (scattata dall'app quando il lavoro è stato aperto o salvato)
  const rec = info.recent.slice(0, 8).map(x => `<div class="home-rec" data-path="${esc(x.path)}" title="${esc(x.path)}">
      <span class="pic">${x.thumb ? `<img src="${x.thumb}" alt="">` : `<img class="icona" src="icons/${x.assembly ? 'joint' : 'box'}.svg" alt="">`}</span>
      <div><b>${esc(x.name)}</b><small>${esc(x.when)}${x.assembly ? ' · assieme' : ''}</small></div>
      <button class="x" data-forget="${esc(x.path)}" title="Togli dai recenti" aria-label="Togli dai recenti">×</button></div>`).join('')
    || '<p class="hint">Ancora nessun lavoro. Quelli che apri o salvi compaiono qui, con l’anteprima.</p>';
  $('#home-recent').innerHTML = rec;
  $('#home-unsaved').innerHTML = info.unsaved ? `<div class="home-unsaved"><div><b>Hai un lavoro non salvato</b>
      <span>lasciato ${esc(info.unsaved.when)}: riprendilo e salvalo con un nome.</span></div>
      <button class="btn primary" id="home-recover">Riprendilo</button></div>` : '';
  $('#home-close').hidden = !!info.show;              // all'avvio non c'è un lavoro a cui tornare
  $('#home').hidden = false;
  document.body.classList.add('at-home');
  // prima la scelta grande (lamiera, struttura, cono), poi sotto il tipo, con le foto
  const scegli = cat => {
    $('#home').querySelectorAll('.home-cat').forEach(b => b.classList.toggle('on', b.dataset.cat === cat));
    $('#home').querySelectorAll('.home-tipi').forEach(s => { s.hidden = s.dataset.of !== cat; });
    const s = $(`#home .home-tipi[data-of="${cat}"]`);
    if (s) s.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };
  $('#home').querySelectorAll('.home-cat').forEach(b => { b.onclick = () => scegli(b.classList.contains('on') ? null : b.dataset.cat); });
  scegli(null);
  $('#home').querySelectorAll('[data-new]').forEach(b => {
    b.onclick = () => (b.dataset.new === 'assieme' ? newAssemblyDialog() : b.dataset.new === 'importa' ? inCoda(importDialog)
      : b.dataset.new === 'step' ? stepDialog() : newDialog(b.dataset.new, true));
  });
  $('#home').querySelectorAll('[data-altro="importa"]').forEach(b => { b.onclick = () => inCoda(importDialog); });
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

// l'anteprima del lavoro per la pagina iniziale: la vista 3D di adesso, ritagliata attorno al pezzo
async function fotoAnteprima(percorso) {
  try {
    if (!percorso || !objs.size) return;
    const box = new THREE.Box3().setFromObject(model);
    if (box.isEmpty()) return;
    renderer.render(scene, camera);
    const W = canvas.width, H = canvas.height;
    let x0 = W, y0 = H, x1 = 0, y1 = 0;
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
      const v = new THREE.Vector3(x, y, z).project(camera);
      const px = (v.x + 1) / 2 * W, py = (1 - v.y) / 2 * H;
      x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
    }
    const m = 0.04 * Math.max(x1 - x0, y1 - y0);
    x0 = Math.max(0, x0 - m); y0 = Math.max(0, y0 - m); x1 = Math.min(W, x1 + m); y1 = Math.min(H, y1 + m);
    if (x1 - x0 < 4 || y1 - y0 < 4) return;
    const out = document.createElement('canvas');
    out.width = 320; out.height = 240;
    const k = Math.min(out.width / (x1 - x0), out.height / (y1 - y0));
    const w = (x1 - x0) * k, h = (y1 - y0) * k;
    out.getContext('2d').drawImage(canvas, x0, y0, x1 - x0, y1 - y0, (out.width - w) / 2, (out.height - h) / 2, w, h);
    await call('save_thumbnail', percorso, out.toDataURL('image/png'));
  } catch (e) { /* l'anteprima è una comodità: se non riesce, pazienza */ }
}

const CMDS = [
  { id: 'new', label: 'Nuovo progetto…', keys: 'Ctrl+N', run: () => newDialog() },
  { id: 'home', label: 'Pagina iniziale', run: () => inCoda(() => showHome()) },
  { id: 'new_asm', label: 'Nuovo assieme…', run: newAssemblyDialog },
  { id: 'drawings', label: 'Tavole con cartiglio (PDF e disegni)…', run: () => inCoda(drawingsDialog) },
  { id: 'prepara', label: 'Prepara per il laser / l’officina (DXF, pieghe, disegni, STEP)…', run: () => inCoda(preparaDialog) },
  { id: 'asm_insert', label: 'Assieme: inserisci pezzo…', run: () => inCoda(async () => { const r = await call('asm_insert_dialog'); if (await apply(r) && r.select) await select(r.select); }) },
  { id: 'asm_esploso', label: 'Assieme: vista esplosa (apri / chiudi)', run: () => {
    if (S?.mode !== 'assembly') { toast('La vista esplosa è degli assiemi.', 'err'); return; }
    const da = ESPLOSO, a = ESPLOSO > 0 ? 0 : 0.8, t0 = performance.now();
    const passo = t => { const k = Math.min(1, (t - t0) / 450); esplodi(da + (a - da) * (1 - (1 - k) ** 3)); if (k < 1) requestAnimationFrame(passo); };
    requestAnimationFrame(passo);
    document.querySelector('#ribbon [data-cmd="asm_esploso"]')?.classList.toggle('on', a > 0);
  } },
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
  { id: 'import_step', label: 'Apri STEP di una lamiera (fa lo sviluppo)…', run: () => stepDialog() },
  { id: 'save', label: 'Salva', keys: 'Ctrl+S', run: () => inCoda(async () => { if (await apply(await call('save', false), 'Salvato.')) fotoAnteprima(S.path); }) },
  { id: 'saveas', label: 'Salva con nome…', keys: 'Ctrl+Maiusc+S', run: () => inCoda(async () => { if (await apply(await call('save', true), 'Salvato.')) fotoAnteprima(S.path); }) },
  { id: 'export_step', label: 'Esporta STEP…', run: () => inCoda(async () => apply(await call('export', 'step'))) },
  { id: 'asm_viteria', label: 'Viteria: viti, dadi, rondelle, rivetti (norme ISO)…', run: () => inCoda(viteriaDialog) },
  { id: 'export_bom', label: 'Distinta materiali in Excel (con gli acquisti)…', run: () => inCoda(async () => apply(await call('export', 'bom'))) },
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
  { id: 'misura', label: 'Quota: misura tra due punti, diametro di un foro', keys: 'M', run: () => (MIS ? misStop() : misStart()) },
  { id: 'misura_via', label: 'Togli tutte le quote misurate', run: () => misTogliTutte() },
  { id: 'view_back', label: 'Vista da dietro', run: () => goTo(VISTE.view_back) },
  { id: 'view_left', label: 'Vista da sinistra', run: () => goTo(VISTE.view_left) },
  { id: 'view_bottom', label: 'Vista da sotto', run: () => goTo(VISTE.view_bottom) },
  { id: 'new_sheet', label: 'Nuova lamiera…', run: () => newDialog('lamiera') },
  { id: 'new_zero', label: 'Nuovo da zero (disegna)…', run: () => newDialog('zero') },
  { id: 'new_frame', label: 'Nuovo telaio / tavolo…', run: () => newDialog('telaio') },
  { id: 'new_free', label: 'Nuova struttura libera…', run: () => newDialog('vuoto') },
  { id: 'flange_help', label: 'Flangia su un bordo', run: () => {
    if (!S?.sheet?.data) { toast('Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', 'err'); return; }
    if (flatView) toggleFlat(false);
    toast('Passa col mouse su un bordo della lamiera: si accende in arancio. Clicca e scegli lunghezza e verso.');
  } },
  { id: 'contour_help', label: 'Lamiera a contorno', run: () => toast(S?.sheet?.data
    ? 'Lamiera a contorno: clicca la faccia di estremità (testata) da cui partire, «Disegna su questa faccia», disegna la sezione con la Linea partendo dallo spigolo del bordo (arancio), poi Altro → «Lamiera a contorno».'
    : 'Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', S?.sheet?.data ? '' : 'err') },
  { id: 'face_help', label: 'Disegna su una faccia', run: () => toast('Clicca una faccia piana del pezzo, poi «Disegna su questa faccia» nel pannello a destra.') },
  { id: 'member_help', label: 'Nuova asta', run: () => toast(nodes.length ? 'Clicca un nodo (pallino) del telaio: nel pannello scegli direzione e lunghezza della nuova asta.' : 'Prima serve una struttura: Telaio / tavolo o Struttura libera.', nodes.length ? '' : 'err') },
  { id: 'export_bendtable', label: 'Esporta la tabella pieghe…', run: () => inCoda(async () => apply(await call('export', 'bendtable'))) },
  { id: 'sheet_rules', label: 'Regole di lamiera…', run: () => inCoda(rulesDialog) },
  { id: 'show_cut', label: 'Mostra la cut list', run: () => { document.querySelector('.tabs button[data-tab="cut"]').hidden = false; showTab('cut', true); } },
  { id: 'show_bom', label: 'Mostra la distinta', run: () => showTab('bom', true) },
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
// Senza ricerca il menu mostra solo i comandi che hanno senso adesso; cercando per nome compaiono tutti
function comandoUtile(c) {
  if (['asm_insert', 'asm_interf'].includes(c.id)) return S?.mode === 'assembly';
  if (c.id === 'asm_back') return !!S?.can_back;
  if (c.id === 'member_help') return nodes.length > 0;
  return true;
}
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
    if (!nq || norm(p.name).includes(nq) || norm(p.label || '').includes(nq)) palItems.push({ label: `Parametro ${p.name}${p.label ? ' (' + p.label + ')' : ''}`, d: `ora ${typeof p.value === 'string' ? p.value : num(p.value, 3)}`,
      keep: true, run: () => { $('#pal-input').value = `${p.name} = `; fillPalette(); } });
  }
  for (const c of CMDS) if (c.id !== 'palette' && (nq ? norm(c.label).includes(nq) : comandoUtile(c))) palItems.push({ label: c.label, d: c.keys || '', run: c.run });
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
  if (ev.key === 'Escape' && document.querySelector('.menu-item.open')) {
    document.querySelectorAll('.menu-item.open').forEach(m => m.classList.remove('open'));
    return;
  }
  if (!$('#home').hidden) {                       // sulla pagina iniziale contano solo Esc e i Ctrl
    if (ev.key === 'Escape' && $('#modal').hidden && !$('#home-close').hidden) hideHome();
    else if (ev.key === 'Escape') $('#modal').hidden = true;
    return;
  }
  if (ev.key === 'Escape' && ASM.tool) { asmTool(null); sel = null; paint(); return; }
  if (DRESS && $('#modal').hidden) {
    if (ev.key === 'Escape') { dressTool(null); return; }
    if (ev.key === 'Enter') { ev.preventDefault(); dressFine(); return; }
  }
  if (ev.key === 'Escape') {
    if (!$('#modal').hidden) { $('#modal').hidden = true; return; }
    if (linkFrom) { linkFrom = null; paintNodes(); return; }
    if (inCampo) { document.activeElement.blur(); return; }
    clearSelection(); return;
  }
  if (inCampo || ev.altKey || ev.metaKey) return;
  if (ev.key === 'Delete') { ev.preventDefault(); deleteSelected(); return; }
  const tasti = { f: 'fit', 0: 'view_iso', 7: 'view_top', 1: 'view_front', 3: 'view_right', q: 'toggle_dims', u: 'unfold', m: 'misura' };
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
const SK_SCIOLTA = new THREE.LineBasicMaterial({ color: 0xE5484D });   // non chiude nessun contorno: non conta
const SK_HOV = new THREE.LineBasicMaterial({ color: 0x4EA1FF });
const SK_RUB = new THREE.LineDashedMaterial({ color: 0x1F5FBF, dashSize: 6, gapSize: 4 });
const SK_ANTEPRIMA = new THREE.LineDashedMaterial({ color: 0xFFB000, dashSize: 5, gapSize: 3 });   // dove andrà la copia
// la griglia non scrive la profondità e si disegna per prima: dove c'è il pezzo (pieno) non si vede
const SK_GRID1 = new THREE.LineBasicMaterial({ color: 0xD3D8DE, depthWrite: false });
const SK_GRID2 = new THREE.LineBasicMaterial({ color: 0xB4BCC5, depthWrite: false });
const TOOLS = { line: 'Linea', rect: 'Rettangolo', circle: 'Cerchio', slot: 'Asola', arc3: 'Arco', polygon: 'Poligono', select: 'Seleziona',
  dim: 'Quota', trim: 'Accorcia', extend: 'Allunga', fillet: 'Raccordo', chamfer: 'Smusso' };
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
  if (!DEV) call('set_titlebar', getComputedStyle($('#top')).backgroundColor.replace(/rgb\((\d+), (\d+), (\d+)\)/, (_, r, g, b) => '#' + [r, g, b].map(x => (+x).toString(16).padStart(2, '0')).join('')));
  for (const [m, c] of COLORI_TEMA[scuro ? 'scuro' : 'chiaro']) m.color.setHex(c);
  try { localStorage.setItem('steelcad.tema', scuro ? 'scuro' : 'chiaro'); } catch { /* niente memoria: va bene lo stesso */ }
  if (SK) drawSketch();                     // le linee spesse prendono il colore nuovo
  ridisegna();
}
const SK_REF = new THREE.LineBasicMaterial({ color: 0xC2410C });        // i bordi del pezzo
const SK_TESTO = new THREE.LineBasicMaterial({ color: 0x7C3AED });      // testi da marcare
const SK_XRAY = new THREE.LineDashedMaterial({ color: 0x38BDF8, dashSize: 2, gapSize: 1.5 });
// sullo sviluppo: la linea di piega e i bordi della sua striscia, guide arancio tratteggiate (ci si aggancia e si quota)
const SK_PIEGA = new THREE.LineDashedMaterial({ color: 0xC0392B, dashSize: 6, gapSize: 3 });
const SK_PIEGA_BORDO = new THREE.LineDashedMaterial({ color: 0xC2410C, dashSize: 2, gapSize: 2 });   // visto attraverso
const SK_CONSTR_SEL = new THREE.LineDashedMaterial({ color: 0xE09A00, dashSize: 8, gapSize: 5 });
let lineeSpesse = true;
const SPESSORE = new Map();          // materiale sottile -> pixel
const GROSSI = new Map();            // materiale sottile -> materiale spesso (stesso colore, aggiornato ogni volta)
SPESSORE.set(SK_CONSTR, 1.8); SPESSORE.set(SK_CONSTR_SEL, 2.2); SPESSORE.set(SK_REF, 2.2); SPESSORE.set(SK_XRAY, 1.6);
SPESSORE.set(SK_TESTO, 2); SPESSORE.set(SK_SEL, 3.2); SPESSORE.set(SK_HOV, 3.2);
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
  trim: 'Accorcia: passa sul pezzo di linea da togliere (diventa rosso) e clicca · si taglia fino alle linee più vicine · Esc finisce',
  extend: 'Allunga: passa vicino all’estremità di una linea (l’allungamento tratteggiato) e clicca · Esc finisce',
  text: 'Testo: clic dove comincia (in basso a sinistra), poi scrivi il testo e l’altezza · per marcarlo col laser: «Marca col laser»',
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
  aggiornaLayout();
  if (flatView) flatView = false;
  clearSelection();
  controls.enableRotate = false;
  // su una faccia: quella faccia è il piano di lavoro e il resto sparisce; sullo sviluppo: si vede lo sviluppo
  const faccia = SK.v.on_face ? buildWorkFace(SK.v.on_face) : null;
  const sviluppo = SK.v.on_flat && buildFlat();
  applyLook();
  $('#sk-panel').hidden = true;                // «Stai disegnando…»: tolto (21/10, «solo un fastidio»)
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
  aggiornaLayout();
  // uno sketch su faccia/sviluppo lasciato vuoto non resta nell'albero
  if (era.v.on_face || era.v.on_flat) inCoda(async () => apply(await call('sketch_close', era.sid)));
  controls.enableRotate = true;
  svuota(workGroup);
  applyLook();
  $('#sk-panel').hidden = true;
  $('#props-panel').hidden = false;
  document.body.classList.remove('sketching');
  document.body.classList.remove('disegno-attivo');
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
function fitSketch(subito = false) {
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
  fitBox(box, zd, false, subito);
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
  // il primo disegno si inquadra da solo, di colpo: con lo scorrimento il clic dopo (l'inizio della forma seguente)
  // cadeva a vista in movimento e andava perso o altrove (21/10, «il primo clic non viene preso»)
  if (eraVuoto && (SK.v.points.length > 1 || SK.v.circles.length)) { fitSketch(true); SK.cursor = null; }
  for (const id of [...SK.sel]) if (!SK.v.lines.some(l => l.id === id) && !SK.v.circles.some(c => c.id === id) && !(SK.v.texts || []).some(t => t.id === id)) SK.sel.delete(id);
  drawSketch();
}
function setTool(t) {
  if (!SK) return;
  SK.tool = t; SK.pts = []; SK.buf = ''; SK.pick = null; SK.dimPick = []; SK.angs = {}; SK.cutPrev = null; SK.cutAt = null; SK.cutMsg = null;
  // con un comando di disegno in mano i clic passano attraverso le caselle delle quote (prima la casella sotto al
  // mouse si prendeva il clic e il punto «non veniva preso», 21/10); con Seleziona e Quota si cliccano
  document.body.classList.toggle('disegno-attivo', !['select', 'dim'].includes(t));
  document.querySelectorAll('#sk-panel [data-tool], #ribbon [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t));
  $('#sk-help').textContent = AIUTI[t] + ' · destro sposta, rotella ingrandisce';
  drawRubber();
}
function setHelp(t) { $('#sk-help').textContent = t; }

// le linee del disegno spesse (le linee normali di WebGL sono sempre di 1 pixel: sullo sfondo scuro si vedevano poco,
// 21/10). Ogni linea diventa una Line2 con lo stesso colore e tratteggio; lo spessore in pixel per tipo di linea.
function ingrossa(gruppo) {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  for (const ln of [...gruppo.children]) {
    if (!ln.isLine || ln.isLine2) continue;
    const m = ln.material;
    let g = GROSSI.get(m);
    if (!g) {
      g = new LineMaterial({ linewidth: SPESSORE.get(m) ?? 2.6, dashed: !!m.isLineDashedMaterial, dashSize: m.dashSize ?? 3,
        gapSize: m.gapSize ?? 1, depthTest: m.depthTest, transparent: m.transparent, opacity: m.opacity ?? 1 });
      GROSSI.set(m, g);
    }
    g.color.copy(m.color);
    g.resolution.set(w, h);
    const p = ln.geometry.getAttribute('position'), xyz = [];
    for (let i = 0; i < p.count; i++) xyz.push(p.getX(i), p.getY(i), p.getZ(i));
    const geo = new LineGeometry(); geo.setPositions(xyz);
    const l2 = new Line2(geo, g);
    if (g.dashed) l2.computeLineDistances();
    l2.renderOrder = ln.renderOrder;
    gruppo.remove(ln); ln.geometry.dispose();
    gruppo.add(l2);
  }
}
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
  skGrid.children.forEach(c => { c.renderOrder = -1; c.material.depthWrite = false; });   // prima di tutto, sotto al pezzo
  for (const l of v.lines) {
    const mat = SK.sel.has(l.id) ? (l.construction && !l.ref ? SK_CONSTR_SEL : SK_SEL) : SK.hover === l.id ? SK_HOV
      : l.xray ? SK_XRAY : l.piega ? (l.piega === 'centro' ? SK_PIEGA : SK_PIEGA_BORDO) : l.ref ? SK_REF : l.construction ? SK_CONSTR : (SK.v.sciolte || []).includes(l.id) ? SK_SCIOLTA : SK_LINE;
    const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints([v3(l.pa), v3(l.pb)]), mat);
    if ((l.construction && !l.ref) || l.xray || l.piega) ln.computeLineDistances();
    skGroup.add(ln);
  }
  for (const t of v.texts || []) {                  // testi da marcare: i tratti delle lettere
    const mat = SK.sel.has(t.id) ? SK_SEL : SK.hover === t.id ? SK_HOV : SK_TESTO;
    for (const s of t.strokes) skGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(s.map(q => v3(q))), mat));
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
    const mat = SK.sel.has(a.id) ? SK_SEL : SK.hover === a.id ? SK_HOV : a.xray ? SK_XRAY : a.ref ? SK_REF : a.construction ? SK_CONSTR : (SK.v.sciolte || []).includes(a.id) ? SK_SCIOLTA : SK_LINE;
    const al = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat);
    if ((a.construction && !a.ref) || a.xray) al.computeLineDistances();
    skGroup.add(al);
  }
  if (lineeSpesse) ingrossa(skGroup);
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
  else if (pronto) { cls = 'ok'; testo = `✓ ${v.profiles === 1 ? '1 contorno chiuso' : v.profiles + ' contorni chiusi'}: ${suPezzo ? 'premi «Togli materiale» per fare il foro' : 'crea la lamiera o la piastra'}. Per cambiare una misura, clicca la quota.`;
    if (v.sciolte?.length) { cls = 'todo'; testo += ' ⚠ ' + v.status; } }
  else if (v.on_sheet && !v.on_flat) { cls = 'todo'; testo = 'Linea aperta da bordo a bordo (arancio): «Togli materiale» la chiude lungo il bordo e toglie il pezzo più piccolo; «Aggiungi materiale» se è disegnata fuori, attaccata al bordo. Se parte dallo spigolo di un bordo libero: Altro → «Lamiera a contorno» la fa diventare lamiera piegata.'; }
  else { cls = 'bad'; testo = (v.status || '').startsWith('Lo sketch') ? 'Nessun contorno chiuso: chiudi il disegno tornando sul primo punto.' : v.status; }
  $('#sk-where').textContent = 'Stai disegnando ' + (v.where || '');
  $('#sk-status').className = 'sk-state ' + cls;
  $('#sk-status').textContent = testo;
  // un problema nel disegno (contorno aperto, vincoli doppi…): una riga rossa in basso, solo quando c'è
  const problema = cls === 'bad' || testo.includes('⚠');
  $('#sk-problema').hidden = !problema;
  $('#sk-problema').textContent = problema ? testo.replace('✓ ', '') : '';
  $('#sk-panel').classList.toggle('chiuso', !skPanelAperto() && !problema);
  $('#sk-where-fr').textContent = $('#sk-panel').classList.contains('chiuso') ? '▸' : '▾';
  document.querySelectorAll('#sk-selbar [data-act]:not([data-act="offset"]):not([data-act="copy"]):not([data-act="move"]):not([data-act="mirror"])').forEach(b => { b.disabled = !SK.sel.size; });
  $('#rb-constr').classList.toggle('on', SK.constr);
  $('#sk-grid').classList.toggle('on', !!SK.grid);
  $('#sk-finish-box').hidden = !libero;
  $('#rb-xray').hidden = !(SK && SK.v.on_face);
  $('#rb-xray').classList.toggle('on', !!SK?.v?.xray);
  $('#sk-leg-xray').hidden = !SK?.v?.xray;
  $('#sk-make').hidden = suPezzo;
  $('#sk-face').hidden = !suPezzo;
  $('#sk-boss').hidden = !!v.on_sheet;
  document.querySelectorAll('#sk-finish-box [data-make]').forEach(b => { b.disabled = !pronto; });
  $('#sk-face [data-make="cut"]').disabled = !(pronto || (suPezzo && v.drawn - (v.texts || []).length));
  $('#sk-mark').disabled = !(v.texts || []).length;
  $('#sk-make [data-make="revolve"]').disabled = !(pronto && v.lines.some(l => l.construction && !l.ref));
  $('#sk-mark').classList.toggle('primary', !!(v.texts || []).length && !v.profiles);
  $('#sk-make [data-make="structure"]').disabled = !v.lines.some(l => !l.construction);
  $('#sk-make [data-make="profilo"]').disabled = !(v.lines.some(l => !l.construction) || v.arcs.some(a => !a.construction));   // bastano linee aperte   // da bordo a bordo: la chiudo io
  for (const q of ['#sk-louver', '#sk-dimple']) { $(q).hidden = !(v.on_sheet && v.on_face); $(q).disabled = !v.drawn; }
  $('#sk-fold').hidden = !(v.on_flat || (v.on_sheet && /\/(sopra|sotto)$/.test(v.on_face || '')));
  // sullo sviluppo si disegna quasi sempre per piegare: lì la piega è un pulsante grande, altrove sta in Altro
  $('#sk-fold-big').hidden = !v.on_flat; $('#sk-fold-big').disabled = !v.drawn;
  if (v.on_flat) $('#sk-fold').hidden = true;
  $('#sk-face [data-make="cut"]').classList.toggle('primary', !v.on_flat);
  $('#sk-fold').disabled = !v.drawn;
  $('#sk-contour').hidden = !(v.on_sheet && v.on_face);
  $('#sk-tab').hidden = !((v.on_sheet && v.on_face) || v.on_flat);
  $('#sk-tab').disabled = !v.drawn;
  $('#sk-contour').disabled = !v.drawn || !v.lines.some(l => !l.construction);
  $('.sk-legend .l-ref').parentElement.hidden = !suPezzo;
  // "Altro" solo se dentro c'è qualcosa; i pulsanti spenti dicono perché
  $('#sk-more').hidden = [...document.querySelectorAll('#sk-more .drop button')].every(b => b.hidden);
  const perche = !v.drawn ? 'prima disegna qualcosa' : !pronto ? 'il contorno non è chiuso: torna sul primo punto' : '';
  document.querySelectorAll('#sk-finish-box [data-make]').forEach(b => {
    if (b.dataset.title === undefined) b.dataset.title = b.title || '';
    b.title = b.disabled ? `Non disponibile: ${['structure', 'profilo'].includes(b.dataset.make) ? 'disegna almeno una linea' : perche || 'serve un contorno chiuso'}` : b.dataset.title;
  });
  gruppiVuoti();
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

function anteprimaCopia(ids, dx, dy, add) {
  const dentro = new Set(ids), sp = p => { const q = skToLocal(v3(p)); return [q[0] + dx, q[1] + dy]; };
  for (const l of SK.v.lines) if (dentro.has(l.id)) add([sp(l.pa), sp(l.pb)], SK_ANTEPRIMA);
  for (const c of SK.v.circles) if (dentro.has(c.id)) {
    const p = []; for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; p.push([c.xc[0] + dx + c.r * Math.cos(a), c.xc[1] + dy + c.r * Math.sin(a)]); }
    add(p, SK_ANTEPRIMA);
  }
  for (const a of SK.v.arcs || []) if (dentro.has(a.id)) {
    const p = []; for (let i = 0; i <= 48; i++) { const t = a.a0 + (a.a1 - a.a0) * i / 48; p.push([a.xc[0] + dx + a.r * Math.cos(t), a.xc[1] + dy + a.r * Math.sin(t)]); }
    add(p, SK_ANTEPRIMA);
  }
  for (const t of SK.v.texts || []) if (dentro.has(t.id)) for (const s of t.strokes) add(s.map(sp), SK_ANTEPRIMA);
}
// lo specchio della selezione sull'asse A-B (coordinate dello sketch), per l'anteprima
function anteprimaSpecchio(ids, A, B, add) {
  const L = Math.hypot(B[0] - A[0], B[1] - A[1]), ux = (B[0] - A[0]) / L, uy = (B[1] - A[1]) / L;
  const rf = q => { const t = (q[0] - A[0]) * ux + (q[1] - A[1]) * uy, fx = A[0] + ux * t, fy = A[1] + uy * t; return [2 * fx - q[0], 2 * fy - q[1]]; };
  const loc = p => skToLocal(v3(p));
  const dentro = new Set(ids);
  for (const l of SK.v.lines) if (dentro.has(l.id)) add([rf(loc(l.pa)), rf(loc(l.pb))], SK_ANTEPRIMA);
  for (const c of SK.v.circles) if (dentro.has(c.id)) {
    const p = []; for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; p.push(rf([c.xc[0] + c.r * Math.cos(a), c.xc[1] + c.r * Math.sin(a)])); }
    add(p, SK_ANTEPRIMA);
  }
  for (const a of SK.v.arcs || []) if (dentro.has(a.id)) {
    const p = []; for (let i = 0; i <= 48; i++) { const t = a.a0 + (a.a1 - a.a0) * i / 48; p.push(rf([a.xc[0] + a.r * Math.cos(t), a.xc[1] + a.r * Math.sin(t)])); }
    add(p, SK_ANTEPRIMA);
  }
}
// specchia, primo clic: se il cursore sta «sulla linea» (non su un punto, una metà, un incrocio) la linea è l'asse
function asseSotto(c, ev) {
  if (c && (c.id || (c.ref && !c.ref.on))) return null;
  const h = skHit(ev);
  return h && SK.v.lines.some(l => l.id === h) ? h : null;
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
  if (SK.pick?.what === 'mirror' && SK.pick.stage !== 'sel') {
    let A = null, B = null;
    if (SK.pick.base) { A = SK.pick.base.xy; B = c; add([A, B], SK_TRACK); }
    else if (SK.hover) { const l = SK.v.lines.find(x => x.id === SK.hover); if (l) { A = l.xa; B = l.xb; } }
    if (A && B && Math.hypot(B[0] - A[0], B[1] - A[1]) > 1e-6) {
      anteprimaSpecchio(SK.pick.ids, A, B, add);
      const ang = ((Math.atan2(B[1] - A[1], B[0] - A[0]) * 180 / Math.PI) + 360) % 180;
      testo = SK.pick.base ? `asse ${num(ang, 1)}°` : 'asse: questa linea';
    }
  } else if (SK.pick && SK.pick.base) {
    add([SK.pick.base.xy, c]);
    const dx = c[0] - SK.pick.base.xy[0], dy = c[1] - SK.pick.base.xy[1];
    testo = `${num(dx, 2)} ; ${num(dy, 2)}`;
    if (SK.pick.what === 'copy' || SK.pick.what === 'move') anteprimaCopia(SK.pick.ids, dx, dy, add);
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
  for (const t of SK.v.texts || []) {
    for (const s of t.strokes) for (let i = 1; i < s.length; i++) {
      const d = segDist(m, proj(s[i - 1]), proj(s[i]));
      if (d < 6 && (!best || d < best.d)) best = { id: t.id, d };
    }
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
  if ((SK.pick?.what === 'copy' || SK.pick?.what === 'move' || SK.pick?.what === 'mirror') && SK.pick.stage !== 'sel') {
    SK.cursor = skCursor(ev);
    if (SK.pick.what === 'mirror' && !SK.pick.base) {            // sopra una linea: sarà l'asse
      const h = asseSotto(SK.cursor, ev);
      if (h !== SK.hover) { SK.hover = h; drawSketch(); }
    }
    drawRubber(); return;
  }
  if (SK.tool === 'select' || SK.pick?.stage === 'sel') {
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
  } else if (SK.tool === 'text') {
    const sid = SK.sid;
    const ultimo = SK.lastText || { text: '', h: 5, angle: 0, come: '' };
    modal(`<h3>Testo</h3>
      <div class="form"><label style="grid-column:1/-1">Testo<input class="field" id="tx-t" value="${esc(ultimo.text)}" placeholder="es. PP-001 · Ø10 · LATO A"></label>
        <label style="grid-column:1/-1">Come<select class="field" id="tx-c">
          <option value=""${!ultimo.come ? ' selected' : ''}>Marcato col laser (non buca, layer MARK)</option>
          <option value="saira"${ultimo.come === 'saira' ? ' selected' : ''}>Tagliato passante, lettere grosse (Saira Stencil)</option>
          <option value="allerta"${ultimo.come === 'allerta' ? ' selected' : ''}>Tagliato passante, lettere sottili (Allerta Stencil)</option></select></label>
        <label>Altezza<span class="inp"><input class="field" id="tx-h" value="${esc(String(ultimo.h).replace('.', ','))}"><i>mm</i></span></label>
        <label>Angolo<span class="inp"><input class="field" id="tx-a" value="${esc(String(ultimo.angle).replace('.', ','))}"><i>°</i></span></label></div>
      <p class="hint" id="tx-hint"></p>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Metti il testo</button></div>`, close => {
      $('#m-no').onclick = close;
      const spiega = () => { $('#tx-hint').textContent = $('#tx-c').value
        ? 'Lettere stencil a contorno chiuso, coi ponticelli (le isole di O, A, B… non cadono): poi «Togli materiale».'
        : 'Il laser lo segna in una passata (lettere a tratto singolo): poi «Marca col laser».'; };
      $('#tx-c').onchange = spiega; spiega();
      const vai = () => {
        const t = $('#tx-t').value, h = $('#tx-h').value.trim(), a = $('#tx-a').value.trim() || '0', come = $('#tx-c').value;
        if (!t.trim()) { toast('Scrivi il testo.', 'err'); return; }
        SK.lastText = { text: t, h, angle: a, come };
        close();
        inCoda(async () => { await apply(await call('sketch_add_text', sid, ptArg(p), t, h, a, come || null)); });
      };
      $('#m-ok').onclick = vai;
      $('#tx-t').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
      $('#tx-t').focus();
    });
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
  if (k === 'Enter' && SK.pick?.stage === 'sel') {
    if (!SK.sel.size) { toast(SK.pick.what === 'mirror' ? 'Prima clicca quello da specchiare.' : 'Prima clicca quello da copiare.', 'err'); return true; }
    skScegliPoiBase(SK.pick); return true;
  }
  if (k === 'Enter') { if (SK.buf) skTyped(); else if (SK.tool === 'line' && SK.pts.length >= 2) skFinish(false); return true; }
  if (k === 'Escape') {
    if (SK.buf) { SK.buf = ''; drawRubber(); return true; }
    if (SK.pick?.what === 'corner' || SK.pick?.what === 'corner2') { const t = SK.pick.tool; SK.pick = null; SK.sel.clear(); drawSketch(); setTool(t); return true; }
    if (SK.pick) { SK.pick = null; setTool('select'); return true; }
    if (SK.dimPick.length) { SK.dimPick = []; drawRubber(); return true; }
    if (SK.tool === 'line' && SK.pts.length >= 2) { skFinish(false); return true; }
    if (SK.pts.length) { SK.pts = []; drawRubber(); return true; }
    if (SK.sel.size) { SK.sel.clear(); drawSketch(); return true; }
    // come negli altri CAD: il primo Esc spegne lo strumento (quota, linea, cerchio…), il secondo esce dallo sketch
    if (SK.tool && SK.tool !== 'select') { setTool('select'); return true; }
    exitSketch(); return true;
  }
  if (k === 'Delete' && SK.sel.size) {
    const ids = [...SK.sel]; SK.sel.clear();
    inCoda(async () => { await apply(await call('sketch_delete', SK.sid, ids)); });
    return true;
  }
  const tasti = { l: 'line', r: 'rect', c: 'circle', k: 'slot', p: 'polygon', s: 'select', d: 'dim', t: 'trim', a: 'extend' };
  if (tasti[k.toLowerCase()]) { setTool(tasti[k.toLowerCase()]); return true; }
  if (k.toLowerCase() === 'x') { costruzione(); return true; }
  if (k.toLowerCase() === 'g' && (SK.v.on_face || SK.v.on_flat)) { SK.ghost = !SK.ghost; applyLook(); return true; }
  if (k.toLowerCase() === 'v' && SK.v.on_face) { toggleXray(); return true; }
  if (k.toLowerCase() === 'o') { startOffset(); return true; }
  if (k.toLowerCase() === 'm') { skAction('mirror'); return true; }
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

// Costruzione: con una selezione la trasforma in guida (o la rimette normale), senza selezione cambia il modo di disegno
function costruzione() {
  if (SK.sel.size) { skAction('constr'); return; }
  SK.constr = !SK.constr;
  drawSketch();
}

// Copia / Sposta come in AutoCAD (21/10): comando → scegli cosa (clic, doppio clic = contorno, finestra) → Invio →
// punto di partenza con gli agganci → dove va, con l'anteprima attaccata al mouse. La copia resta attiva per altre
// copie fino a Esc; lo spostamento finisce dopo il clic.
const AIUTO_SCEGLI = { copy: 'Copia', move: 'Sposta', mirror: 'Specchia' };
function skScegliPoiBase(P) {
  P.stage = 'base'; P.ids = [...SK.sel]; P.base = null;
  if (P.what === 'mirror') {
    setHelp('Specchia: clicca una linea che fa da asse, oppure due punti dell’asse (la metà di un bordo si aggancia) · Esc annulla');
    drawRubber(); return;
  }
  setHelp(`${AIUTO_SCEGLI[P.what]}: clic sul punto di partenza (gli agganci si accendono) · Esc annulla`);
  drawRubber();
}
function skAction(act) {
  if (act === 'offset') { startOffset(); return; }
  if ((act === 'copy' || act === 'move' || act === 'mirror')) {
    SK.pts = []; SK.cursor = null;
    if (SK.sel.size) { SK.pick = { what: act }; skScegliPoiBase(SK.pick); return; }
    SK.pick = { what: act, stage: 'sel', ids: [], base: null };
    setHelp(`${AIUTO_SCEGLI[act]}: clic su quello da copiare (doppio clic = il contorno intero, o una finestra) · Invio quando hai scelto · Esc annulla`
      .replace('da copiare', act === 'move' ? 'da spostare' : act === 'mirror' ? 'da specchiare' : 'da copiare'));
    drawSketch();
    return;
  }
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
  if (P.what === 'mirror' && P.stage !== 'sel') {
    const c = SK.cursor || skCursor(ev);
    const fine = asse => {
      SK.pick = null; SK.pts = []; SK.hover = null; setTool('select');
      inCoda(async () => { await apply(await call('sketch_mirror', SK.sid, P.ids, asse)); });
    };
    if (!P.base) {
      const h = asseSotto(c, ev);
      if (h) { fine(h); return; }                                // clic su una linea: è l'asse
      if (!c) return;
      P.base = { xy: c.xy, arg: ptArg({ id: c.id, xy: c.xy, ref: c.ref }) };
      SK.pts = [P.base];
      setHelp('Specchia: secondo punto dell’asse (vedi l’anteprima) · Esc annulla');
      drawRubber(); return;
    }
    if (!c) return;
    if (Math.hypot(c.xy[0] - P.base.xy[0], c.xy[1] - P.base.xy[1]) < 1e-6) { toast('Il secondo punto dell’asse coincide col primo.', 'err'); return; }
    fine([P.base.arg, ptArg({ id: c.id, xy: c.xy, ref: c.ref })]);
    return;
  }
  if (P.stage === 'sel') {
    const h = skHit(ev);
    if (h) { if (SK.sel.has(h)) SK.sel.delete(h); else SK.sel.add(h); drawSketch(); }
    return;
  }
  const c = SK.cursor || skCursor(ev);
  if (!c) return;
  if (!P.base) {
    P.base = { xy: c.xy }; SK.pts = [P.base];
    setHelp(`${AIUTO_SCEGLI[P.what] || 'Copia'}: clic dove va (vedi l’anteprima), o scrivi la distanza + Invio · ${P.what === 'copy' ? 'altre copie: altri clic · ' : ''}Esc finisce`);
    drawRubber(); return;
  }
  skPickDone(c.xy[0] - P.base.xy[0], c.xy[1] - P.base.xy[1]);
}
function skPickTyped(v) {
  const P = SK.pick;
  if (P.what === 'mirror') { toast('Lo specchio vuole l’asse: clicca una linea o due punti.', 'err'); return; }
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
  if (Math.hypot(dx, dy) < 1e-9) { toast('Partenza e arrivo coincidono.', 'err'); return; }
  if (P.what === 'copy') {                          // come AutoCAD: si resta in Copia, stessa partenza, altre copie
    SK.buf = '';
    inCoda(async () => { await apply(await call('sketch_copy', SK.sid, P.ids, dx, dy)); drawRubber(); });
    return;
  }
  SK.pick = null; SK.pts = []; setTool('select');
  inCoda(async () => { await apply(await call(P.what === 'copy' ? 'sketch_copy' : 'sketch_move', SK.sid, P.ids, dx, dy)); });
}
// --------------------------------------------------------------- quota a mano
function skDimClick(ev) {
  const c = skCursor(ev);
  const punto = c && c.id ? c.id : null;
  const h = punto ? null : skHit(ev);
  const sid = SK.sid;
  // come in ogni CAD: dopo il clic si scrive subito la misura (anche se la quota c'era già)
  const quota = (kind, refs) => inCoda(async () => {
    const r = await call('sketch_dimension', sid, kind, refs);
    if (!await apply(r) || !r.dim || r.guidata) return;
    const x = dimEls.find(e => e.d && e.d.sketch === sid && e.d.dim === r.dim);
    if (x) { x.el.style.display = ''; editDim(x.el, x.d); }
  });
  if (!SK.dimPick.length) {
    if (punto) { SK.dimPick = [punto]; setHelp('Quota: ora clic su un altro punto o su una linea · Esc annulla'); return; }
    if (h && SK.v.circles.some(x => x.id === h)) { quota('diameter', [h]); return; }
    if (h && SK.v.arcs?.some(x => x.id === h)) { quota('radius', [h]); return; }
    if (h) { quota('length', [h]); return; }
    return;
  }
  const a = SK.dimPick[0];
  SK.dimPick = []; setTool('dim');
  if (h && SK.v.lines.some(l => l.id === h)) { quota('pldistance', [a, h]); return; }
  if (!punto || punto === a) return;
  modal(`<h3>Quota tra due punti</h3><div class="choice"><button data-k="hdistance">Orizzontale</button><button data-k="vdistance">Verticale</button><button data-k="distance">Allineata</button></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#modal-box').querySelectorAll('.choice button').forEach(b => { b.onclick = () => { close(); quota(b.dataset.k, [a, punto]); }; });
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
  if (kind === 'revolve') {
    const sid = SK.sid, pezzo = !!S?.body || objs.has('body');
    modal(`<h3>Rivoluzione</h3>
      <p class="hint">Il contorno chiuso gira attorno alla linea di costruzione (l’asse). Disegna solo metà sezione, da una parte dell’asse.</p>
      <div class="form"><label>Angolo<span class="inp"><input class="field" id="rv-a" value="360"><i>°</i></span></label><span></span></div>
      ${pezzo ? '<label class="check"><input type="checkbox" id="rv-t"> togli dal pezzo (una gola, un incavo) invece di aggiungere</label>' : ''}
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fai girare</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const v = { angle: $('#rv-a').value.trim() || '360', togli: $('#rv-t')?.checked ? 1 : '' };
        close();
        inCoda(async () => { const r = await call('create_from_sketch', sid, 'revolve', v); if (await apply(r, r.message)) exitSketch(); });
      };
    });
    return;
  }
  if (kind === 'mark') {
    const sid = SK.sid;
    inCoda(async () => { const r = await call('create_from_sketch', sid, 'mark', {}); if (await apply(r, r.message)) exitSketch(); });
    return;
  }
  if (kind === 'cut') {
    const sid = SK.sid;
    inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'cut', {}), 'Tagliato.')) exitSketch(); });
    return;
  }
  if (kind === 'fold') {
    // più linee = pieghe in serie (calandratura a colpi, "bumping"): si scrive l'angolo totale, si divide per i colpi
    const n = SK.v.lines.filter(l => !l.ref && !l.construction && !l.xray).length;
    const serie = n > 1;
    modal(`<h3>${serie ? `${n} pieghe in serie (a colpi)` : 'Piega su questa linea'}</h3>
      <p class="hint">${serie ? `Ogni linea è un colpo di piega. La parte più grande resta ferma, le altre strisce girano tutte dallo stesso verso. Lo sviluppo resta quello che hai disegnato.`
        : 'La linea è lo spigolo esterno della piega. Si piega la parte più piccola; lo sviluppo resta quello che hai disegnato.'}</p>
      <div class="ff"><label>${serie ? 'Angolo totale della curva' : 'Angolo'}<span class="inp"><input class="field" id="m-ang" value="90"><i>°</i></span></label><span class="hint" id="m-colpo"></span></div>
      <div class="seg-row"><span>Verso</span><div class="seg" id="m-dir"><button type="button" data-v="up" class="on">su</button><button type="button" data-v="down">giù</button></div></div>
      ${serie ? '' : `<label class="check"><input type="checkbox" id="m-flip"> piega l’altra parte</label>
      <details class="bump"><summary>Bumping: raggio grande a colpi</summary>
        <p class="hint">Tanti colpi piccoli a passo costante, con il punzone normale: il raggio grande senza calandra. Vuoto = piega normale.</p>
        <div class="ff"><label>Colpi<input class="field" id="m-colpi" placeholder="es. 15"></label>
        <label>Raggio grande (interno)<span class="inp"><input class="field" id="m-rg" placeholder="es. 200"><i>mm</i></span></label></div></details>`}
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Piega</button></div>`, close => {
      const colpo = () => { const t = parseFloat($('#m-ang').value.replace(',', '.')); return isFinite(t) ? Math.round(t / n * 1000) / 1000 : null; };
      const scrivi = () => { if (serie) { const c = colpo(); $('#m-colpo').textContent = c == null ? '' : `= ${String(c).replace('.', ',')}° per ogni colpo (${n} colpi)`; } };
      $('#m-ang').oninput = scrivi; scrivi();
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const sid = SK.sid, dir = $('#m-dir .on').dataset.v, flip = !serie && $('#m-flip').checked;
        const ang = serie ? String(colpo() ?? '') : $('#m-ang').value.trim();
        const bump = !serie && $('#m-colpi').value.trim() ? { colpi: $('#m-colpi').value.trim(), raggio: $('#m-rg').value.trim() } : null;
        close();
        inCoda(async () => { const r = await call('sheet_fold', sid, ang, dir, flip, bump); if (await apply(r)) exitSketch(); });
      };
    });
    return;
  }
  if (kind === 'profilo') {
    // profilo estruso in lamiera: gli archi diventano colpi (bumping)
    const sid = SK.sid, BD = S?.bend_default || {};
    const archi = SK.v.arcs.filter(a => !a.construction && !a.ref).length;
    modal(`<h3>Estrudi in lamiera</h3>
      <p class="hint">Il profilo disegnato (aperto) diventa lamiera piegata: ogni spigolo è una piega${archi ? `, ogni arco (qui ${archi}) si fa a colpi (bumping)` : ''}. La linea disegnata è la faccia interna: lo spessore va dalla parte esterna.</p>
      <div class="ff"><label>Lunghezza (di quanto estrudere)<span class="inp"><input class="field" id="pf-L" value="1000"><i>mm</i></span></label>
        <label>Spessore<span class="inp"><input class="field" id="pf-sp" value="${esc(virgola(S?.parameters?.find?.(p => p.name === 'sp')?.value) || '3')}"><i>mm</i></span></label></div>
      ${archi ? `<div class="ff"><label>Colpi per ogni arco<span class="inp"><input class="field" id="pf-colpi" placeholder="vuoto = uno ogni 20 mm"></span></label><span></span></div>` : ''}
      <div class="ff"><label>Raggio del punzone<span class="inp"><input class="field" id="pf-r" value="${esc(virgola(BD.radius) || '')}"><i>mm</i></span></label>
        <label>K-factor<span class="inp"><input class="field" id="pf-k" value="${esc(virgola(BD.k) || '')}"></span></label></div>
      <label class="check"><input type="checkbox" id="pf-gira"> lo spessore va dall’altra parte (la linea è la faccia esterna)</label>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Estrudi in lamiera</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const v = { lunghezza: $('#pf-L').value.trim(), spessore: $('#pf-sp').value.trim(), colpi: $('#pf-colpi')?.value.trim() || '',
          raggio: $('#pf-r').value.trim(), k: $('#pf-k').value.trim(), gira: $('#pf-gira').checked };
        close();
        inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'profilo', v))) exitSketch(); });
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
          if (lam) showTab('sheet', true);
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
  if (!SK || (SK.tool !== 'select' || SK.pick) && SK.pick?.stage !== 'sel') return;
  const h = skHit(ev);
  if (!h || !SK.v.lines.some(l => l.id === h)) return;
  if (SK.pick?.stage === 'sel') { for (const x of chainOf(h)) SK.sel.add(x); } else SK.sel = chainOf(h);
  drawSketch();
});

// ===================================================================== barra a schede (stile SolidCraft)
let schedaPrima = 'lamiera';
// Esporta: un pulsante solo con il menu; si vedono le voci che hanno senso per il pezzo aperto
const VOCI_ESPORTA = [['drawings', 'Tavole PDF con cartiglio…'], ['export_dxf', 'DXF di taglio…'],
  ['export_bendtable', 'Tabella pieghe (per la piegatrice)…'], ['export_step', 'STEP (modello 3D)…'],
  ['export_bom', 'Distinta materiali (Excel)…']];
document.querySelectorAll('.rgroup[data-esporta]').forEach(g => g.insertAdjacentHTML('beforebegin',
  `<div class="rgroup"><div class="rbtns"><button class="rb" data-cmd="misura" title="Quota: due clic = distanza; clic sul bordo di un foro = diametro (M)"><img src="icons/dimension.svg" alt=""><span>Quota</span></button></div><div class="rname">Misura</div></div>`));
document.querySelectorAll('.rgroup[data-esporta]').forEach(g => {
  g.innerHTML = `<div class="rbtns"><div class="menu-item rmenu"><button class="rb rb-export" title="Esporta: tavole, DXF di taglio, tabella pieghe, STEP">
    <img src="icons/export.svg" alt=""><span>Esporta ▾</span></button><div class="drop">${VOCI_ESPORTA.map(([c, l]) =>
    `<button data-cmd="${c}">${l}</button>`).join('')}</div></div></div><div class="rname">Esporta</div>`;
});
// perché un comando adesso non si può usare (null = si può)
function motivoNo(cmd) {
  const lam = !!S?.sheet?.data, asm = S?.mode === 'assembly';
  const piastra = !S?.sheet && JSON.stringify(S?.tree || {}).includes('"kind":"extrude"');
  switch (cmd) {
    case 'export_dxf': return asm ? 'negli assiemi si esporta pezzo per pezzo' : lam || piastra ? null : 'serve una lamiera o una piastra';
    case 'export_bendtable': return lam && ((S.sheet.data.bends || []).length || (S.sheet.data.bend_rows || []).length) ? null : 'nessuna piega';
    case 'export_step': case 'drawings': return objs.size || asm ? null : 'il progetto è vuoto';
    case 'export_bom': return asm ? null : 'la distinta materiali si fa da un assieme';
    case 'flange_help': case 'contour_help': case 'unfold': case 'flat_sketch': return lam ? null : 'prima serve una lamiera (Nuovo → Lamiera)';
    case 'member_help': return nodes.length ? null : 'prima serve una struttura (Nuovo → Telaio, Scaffale…)';
    default: return null;
  }
}
// i pulsanti del ribbon: spenti col motivo nel suggerimento; le voci di Esporta e del menu File che non
// servono non si vedono; su coni e raccordi niente comandi della lamiera piegata
function aggiornaComandi() {
  const forma = !!S?.sheet?.shape;
  // profili a colpi e lamiere da STEP hanno le facce dei tratti: ci si disegna sopra (fori, tagli, marcature)
  const conFacce = ['profilo', 'step'].includes(S?.sheet?.data?.shape_info?.kind);
  document.querySelectorAll('#ribbon .rb[data-cmd]').forEach(b => {
    if (b.dataset.title === undefined) b.dataset.title = b.title || '';
    const no = motivoNo(b.dataset.cmd);
    b.disabled = !!no;
    b.title = no ? `${b.dataset.title} · Non disponibile: ${no}` : b.dataset.title;
    if (b.hasAttribute('data-no-shape')) b.hidden = forma && !(conFacce && b.dataset.cmd === 'face_help');
  });
  document.querySelectorAll('#ribbon .rb[data-serve="lam"]').forEach(b => {
    if (b.dataset.title === undefined) b.dataset.title = b.title || '';
    b.disabled = !S?.sheet?.data; b.title = b.disabled ? `${b.dataset.title} · Non disponibile: prima serve una lamiera` : b.dataset.title;
    if (b.hasAttribute('data-no-shape')) b.hidden = forma;
  });
  document.querySelectorAll('.rmenu .drop [data-cmd]').forEach(b => { b.hidden = !!motivoNo(b.dataset.cmd); });
  document.querySelectorAll('#top .drop [data-cmd^="export_"]').forEach(b => {
    const no = motivoNo(b.dataset.cmd);
    b.disabled = !!no; b.title = no ? 'Non disponibile: ' + no : '';
  });
  gruppiVuoti();
}
// un gruppo del ribbon senza pulsanti visibili sparisce, nome compreso
function gruppiVuoti() {
  document.querySelectorAll('#ribbon .rgroup').forEach(g => {
    const bs = g.querySelectorAll('.rbtns .rb');
    g.hidden = bs.length > 0 && [...bs].every(b => b.hidden);
  });
}
function showRibbon(t) {
  document.querySelectorAll('.rtabs button').forEach(b => b.classList.toggle('on', b.dataset.rtab === t));
  document.querySelectorAll('.rbody').forEach(b => { b.hidden = b.dataset.rbody !== t; });
}
$('#ribbon').addEventListener('click', ev => {
  const tab = ev.target.closest('.rtabs button');
  if (tab) { showRibbon(tab.dataset.rtab); if (tab.dataset.rtab !== 'sketch') schedaPrima = tab.dataset.rtab; return; }
  const mk = ev.target.closest('[data-make]');
  if (mk) { mk.closest('.menu-item')?.classList.remove('open'); if (SK && !mk.disabled) makeDialog(mk.dataset.make); return; }
  const b = ev.target.closest('.rb');
  if (!b || b.disabled) return;
  if (b.dataset.cmd) return;                         // ci pensa il gestore generale dei data-cmd
  if (b.dataset.azione) { azione(b.dataset.azione); return; }
  if (!SK) return;
  if (b.id === 'sk-grid') { SK.grid = aggancioGriglia = !SK.grid; drawSketch(); return; }
  if (b.id === 'rb-constr') { costruzione(); return; }
  if (b.id === 'rb-xray') { toggleXray(); return; }
  if (b.id === 'sk-ghost') { SK.ghost = !SK.ghost; applyLook(); return; }
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
    piastra: !S?.sheet && /"kind":"(extrude|revolve)"/.test(JSON.stringify(S?.tree || {})) };
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
const ICONA_TIPO = { instance: 'box', mate: 'joint', assembly: 'joint', sketch: 'sketch', sheet: 'box', flange: 'flange', sheet_cut: 'cut', sheet_miter: 'cut', extrude: 'extrude', revolve: 'refold', hole: 'hole', fillet: 'fillet',
  chamfer: 'chamfer', structure: 'joint', members: 'line', part: 'box', group: 'list', project: 'box' };
const iconImg = k => `<img src="icons/${ICONA_TIPO[k] || 'box'}.svg" alt="">`;
// (la barra "Storia" in basso è stata tolta: ripeteva l'albero, senza tornare indietro a un passo)
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
// ------------------------------------------------------------------------------ intro
const INTRO_T0 = performance.now();
const INTRO_MIN = 1800;
let introChiusa = false;
function introStato(testo, quanto) {
  const el = document.querySelector('#intro');
  if (!el || introChiusa) return;
  el.querySelector('.intro-stato').textContent = testo;
  el.querySelector('.intro-barra i').style.width = Math.round(quanto * 100) + '%';
}
function introVia(subito = false) {
  const el = document.querySelector('#intro');
  if (!el || introChiusa) return;
  introChiusa = true;
  el.classList.add('via');
  setTimeout(() => el.remove(), subito ? 50 : 500);
}
async function introFine() {
  if (new URLSearchParams(location.search).get('intro') === 'fermo') { introStato('Pronto', 1); return; }   // per le foto
  const resta = INTRO_MIN - (performance.now() - INTRO_T0);
  if (resta > 0) await new Promise(ok => setTimeout(ok, resta));
  introStato('Pronto', 1);
  await new Promise(ok => setTimeout(ok, 180));
  introVia();
}
(() => {
  const q = new URLSearchParams(location.search);
  if (q.has('dev') && !q.has('intro')) { introChiusa = false; introVia(true); return; }
  const salta = () => introVia();
  document.querySelector('#intro')?.addEventListener('click', salta);
  window.addEventListener('keydown', function prima() { window.removeEventListener('keydown', prima); salta(); });
  introStato('Avvio del motore CAD…', 0.18);
})();

async function start() {
  let tema = 'scuro';                              // scuro di partenza: pesa meno sugli occhi
  try { tema = localStorage.getItem('steelcad.tema') || 'scuro'; } catch { /* va bene il predefinito */ }
  applyTheme(tema === 'scuro');
  introStato('Collego il motore geometrico…', 0.45);
  S = await call('state');
  if (S?.version) { const v = document.querySelector('#intro .intro-versione'); if (v) v.textContent = 'versione ' + S.version; }
  introStato('Preparo l’interfaccia…', 0.7);
  renderPanels();
  await loadScene();
  setInterval(() => call('autosave'), 60000);
  const casa = await call('home_info');
  if (casa.ok && casa.show) await showHome(casa);
  introStato('Pronto', 0.95);
  requestAnimationFrame(loop);
  introFine();
  window.__steelcad = { ready: true, runCmd: id => runCmd(id), get state() { return S; }, get sceneVersion() { return sceneVersion; }, get nodes() { return nodes; }, get sketch() { return SK; },
    objs, select, camera, controls, skScreen: xy => skScreen(xy), get mis() { return MIS; }, lineeSpesse: on => { lineeSpesse = on; if (SK) drawSketch(); }, toScreen: p => { const q = v3(p).project(camera); return [(q.x + 1) / 2 * canvas.clientWidth, (1 - q.y) / 2 * canvas.clientHeight]; }, enterSketch, exitSketch, apply, toast, hideHome, THREE, get bendEdges() { return bendEdges; },
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
