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
    const seg = [];
    for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
    const lines = new THREE.LineSegments(lg, EDGE);
    model.add(mesh, lines);
    objs.set(d.id, { data: d, mesh, lines, base });
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
  overlay.add(new THREE.Mesh(g, m));
}

function paint() {
  for (const m of overlay.children) { m.geometry.dispose(); m.material.dispose(); }
  overlay.clear();
  const selIds = new Set(sel ? (sel.ids || [sel.id]) : []);
  for (const [id, o] of objs) {
    let c = o.base;
    const intero = o.data.kind === 'member';
    if (selIds.has(id) && (intero || sel.face == null)) c = C_SEL;
    else if (hover && hover.id === id && (intero || hover.face == null)) c = C_HOVER;
    o.mesh.material.color.copy(c);
    o.mesh.material.emissive.setRGB(c === o.base ? 0 : 0.08, c === o.base ? 0 : 0.06, 0);
  }
  if (sel && sel.face != null && objs.has(sel.id)) faceOverlay(objs.get(sel.id), sel.face, C_SEL);
  if (sel && sel.hl && objs.has('body')) for (const i of sel.hl) faceOverlay(objs.get('body'), i, C_SEL);
  if (hover && hover.face != null && objs.has(hover.id) && !(sel && sel.id === hover.id && sel.face === hover.face))
    faceOverlay(objs.get(hover.id), hover.face, C_HOVER);
  ridisegna();
}

// --------------------------------------------------------------- scelta col mouse
const ray = new THREE.Raycaster();
function pick(ev) {
  const r = canvas.getBoundingClientRect();
  const p = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(p, camera);
  const hit = ray.intersectObjects([...objs.values()].map(o => o.mesh), false)[0];
  if (!hit) return null;
  const o = objs.get(hit.object.userData.id);
  let face = null;
  if (o.data.kind === 'body') {
    const k = hit.faceIndex * 3;
    face = o.data.faces.find(f => k >= f.start && k < f.start + f.count)?.index ?? null;
  }
  return { id: o.data.id, face, name: o.data.name };
}

const tip = $('#hover-tip');
let premuto = null;
canvas.addEventListener('pointerdown', ev => { premuto = { x: ev.clientX, y: ev.clientY }; });
canvas.addEventListener('pointermove', ev => {
  if (SK) { skMove(ev); return; }
  if (ev.buttons) { tip.style.display = 'none'; return; }
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
canvas.addEventListener('pointerleave', () => { hover = null; tip.style.display = 'none'; paint(); });
canvas.addEventListener('pointerup', ev => {
  if (!premuto || Math.hypot(ev.clientX - premuto.x, ev.clientY - premuto.y) > 4 || ev.button !== 0) return;
  if (SK) { skClick(ev); return; }
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
  const dist = rad / Math.sin(Math.min(fov, fov * camera.aspect) / 2) * 1.08;
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
};

// --------------------------------------------------------------- quote sul modello
const dimsBox = $('#dims');
let dimEls = [];
function buildDims() {
  for (const l of dimLines.children) l.geometry.dispose();
  dimLines.clear();
  dimsBox.innerHTML = '';
  dimEls = [];
  if (!showDims || !S) return;
  const box = new THREE.Box3().setFromObject(model);
  const centro = box.getCenter(new THREE.Vector3());
  const off = Math.max(20, box.getBoundingSphere(new THREE.Sphere()).radius * 0.07);
  for (const d of S.dimensions) {
    const a = new THREE.Vector3(...d.a), b = new THREE.Vector3(...d.b);
    let pa = a, pb = b;
    if (d.type !== 'diameter') {
      const v = b.clone().sub(a);
      let n = new THREE.Vector3(0, 0, 1);
      if (Math.abs(v.clone().normalize().dot(n)) > 0.9) n = new THREE.Vector3(0, 1, 0);
      const perp = v.clone().cross(n).normalize();
      const mid = a.clone().add(b).multiplyScalar(0.5);
      if (perp.dot(mid.clone().sub(centro)) < 0) perp.negate();
      pa = a.clone().addScaledVector(perp, off); pb = b.clone().addScaledVector(perp, off);
      const seg = [a, a.clone().addScaledVector(perp, off * 1.15), b, b.clone().addScaledVector(perp, off * 1.15), pa, pb];
      const g = new THREE.BufferGeometry().setFromPoints(seg);
      dimLines.add(new THREE.LineSegments(g, DIM_MAT));
    }
    const el = document.createElement('div');
    el.className = 'dim';
    el.innerHTML = (d.param ? `<span class="p">${esc(d.param)}</span>` : '') + esc(d.label);
    el.title = d.param ? `Quota legata al parametro ${d.param}: clicca per cambiarla` : 'Clicca per cambiare la quota';
    el.addEventListener('click', ev => { ev.stopPropagation(); editDim(el, d); });
    dimsBox.appendChild(el);
    // il diametro va sul bordo del cerchio, non al centro: se no la scritta copre il foro
    dimEls.push({ el, at: d.type === 'diameter' ? pb.clone() : pa.clone().add(pb).multiplyScalar(0.5) });
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
  inp.value = typeof d.expr === 'number' ? String(d.value).replace('.', ',') : (d.param ? String(d.value).replace('.', ',') : d.expr);
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
  if (primaVolta || (eraVuota && objs.size)) { goTo(VISTE.view_iso); primaVolta = !objs.size && primaVolta; }
  else if (objs.size && raggio() > prima * 1.15) goTo(null, true);   // il modello è cresciuto: si riadatta
  buildDims();
  buildNodes();
  const esiste = id => objs.has(id) || nodes.some(n => n.id === id) || id.startsWith('flange=');
  if (sel) {
    if ((sel.ids || [sel.id]).every(esiste)) await select(sel.id, sel.face, sel.ids, true);
    else clearSelection();
  }
}

function renderPanels() {
  renderTop(); renderTree(); renderParams(); renderBottom(); renderSheet();
}

function renderTop() {
  const nome = esc(S.name || 'Senza nome');
  $('#docname').innerHTML = `${S.dirty ? '<span class="dirty">● </span>' : ''}${nome}` +
    (S.path ? ` <span style="color:var(--ink-3)">— ${esc(S.path)}</span>` : ' <span style="color:var(--ink-3)">— non salvato</span>');
  for (const [b, m, k, t] of [['#b-undo', '#m-undo', 'undo', 'Annulla'], ['#b-redo', '#m-redo', 'redo', 'Ripeti']]) {
    const l = S[k][0];
    $(b).disabled = !l; $(m).disabled = !l;
    $(b).title = l ? `${t}: ${l}` : `Niente da ${t.toLowerCase()}`;
    $(m).firstChild.textContent = l ? `${t}: ${l}` : t;
  }
  const i = S.info;
  $('#status').textContent = `Ricostruito in ${num(i.rebuild_ms)} ms (${i.rebuilt} ricostruite, ${i.cached} dalla cache) · ` +
    'sinistro ruota, destro sposta, rotella ingrandisce';
}

const ICONE = { project: '◆', part: '▣', sketch: '✎', extrude: '▤', hole: '◯', fillet: '◜', chamfer: '◿', sheet: '▱', flange: '⌐',
  structure: '⌗', group: '▾', members: '│' };
function renderTree() {
  const selIds = new Set(sel ? (sel.ids || [sel.id]) : []);
  const nodo = n => {
    const ids = n.kind === 'members' ? n.ref : n.kind === 'structure' ? membersOf(n.ref)
      : n.kind === 'flange' ? ['flange=' + n.ref]
      : n.kind === 'sketch' ? ['sketch=' + n.ref]
      : ['part', 'extrude', 'hole', 'fillet', 'chamfer', 'sheet'].includes(n.kind) ? ['body'] : null;
    const cls = ['node', n.kind === 'project' ? 'root' : '', n.kind === 'group' ? 'group' : '',
      ids && ids.length ? 'clickable' : '', n.status === 'errore' ? 'err' : '',
      ids && ids.length && ids.every(i => selIds.has(i)) && n.kind !== 'structure' && !(n.kind !== 'part' && ids[0] === 'body') ? 'sel' : ''];
    const st = n.status && n.status !== 'errore' ? `<span class="st">${esc(n.status)}</span>` : '';
    const data = ids && ids.length ? ` data-ids="${esc(ids.join(','))}"` : '';
    const figli = n.children.length ? `<ul>${n.children.map(nodo).join('')}</ul>` : '';
    return `<li><div class="${cls.filter(Boolean).join(' ')}"${data} title="${esc(n.label)}"><span class="k">${ICONE[n.kind] || '·'}</span>${esc(n.label)}${st}</div>${figli}</li>`;
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
async function select(id, face = null, ids = null, silenzioso = false) {
  sel = { id, face, ids };
  paint(); renderTree(); paintNodes();
  const r = await call('select', id, face);
  if (!r.ok) { if (!silenzioso) toast(r.message, 'err'); return; }
  if (r.selection.highlight) { sel.hl = r.selection.highlight; paint(); }
  renderProps(r.selection);
}
function clearSelection() {
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
  } else if (s.kind === 'flange') {
    $('#props').innerHTML = h + flangePanel(s);
    wireFlange(s);
    return;
  } else if (s.kind === 'body' && s.flange_form) {
    $('#props').innerHTML = h + newFlangePanel(s.flange_form);
    wireNewFlange(s.flange_form);
    return;
  } else if (s.kind === 'node') {
    $('#props').innerHTML = h + nodePanel(s);
    wireNode(s);
    return;
  } else if (s.commands?.length) {
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
function flangeFields(d, dirs, pos) {
  return `<div class="xyz"><label>Lunghezza (esterna)<input class="field" id="f-len" value="${esc(String(d.length ?? '').replace('.', ','))}"></label>
    <label>Angolo (°)<input class="field" id="f-ang" value="${esc(String(d.angle ?? 90).replace('.', ','))}"></label>
    <label>Verso<select class="field" id="f-dir">${opts(dirs, d.direction || 'up')}</select></label></div>
    <label class="lbl" style="display:block;margin-top:6px">Posizione<select class="field" id="f-pos">${opts(pos, d.position || 'inside')}</select></label>`;
}
const VERSI_UI = { up: 'su', down: 'giù' };
const POS_UI = { inside: 'quota esterna sul contorno', outside: 'piega dal bordo, flangia fuori' };
function readFlange() {
  return { length: $('#f-len').value.trim(), angle: $('#f-ang').value.trim(), direction: $('#f-dir').value, position: $('#f-pos').value };
}
function newFlangePanel(ff) {
  return `<div class="sub">Flangia su questo lato</div><p class="hint" style="margin:0 0 6px">${esc(ff.label)}: lunghezza dallo spigolo esterno alla punta.</p>
    ${flangeFields(ultimaFlangia, VERSI_UI, POS_UI)}
    <div class="row-btns"><button class="btn primary" id="f-add">Aggiungi flangia</button></div>`;
}
function wireNewFlange(ff) {
  const vai = () => {
    ultimaFlangia = readFlange();
    inCoda(async () => { const r = await call('add_flange', ff.feature, ff.edge, ultimaFlangia); if (await apply(r)) await select(r.select); });
  };
  $('#f-add').onclick = vai;
  ['#f-len', '#f-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
}
function flangePanel(s) {
  const fori = s.holes.map((h, i) => `<div class="h">Ø${esc(h.d)} a u ${esc(h.u)}, v ${esc(h.v)}<button class="btn" data-hdel="${i}" title="Togli il foro">×</button></div>`).join('')
    || '<p class="hint" style="margin:0">Nessun foro.</p>';
  return `<div class="sub">Flangia</div>${flangeFields(s.def, s.directions, s.positions)}
    <label class="lbl" style="display:block;margin-top:6px">Fessura d’angolo (mm)<input class="field" id="f-gap" value="${esc(String(s.def.gap ?? 0).replace('.', ','))}"></label>
    <div class="row-btns"><button class="btn primary" id="f-apply">Applica</button><button class="btn danger" id="f-del">Elimina flangia</button></div>
    <div class="sub">Fori sulla flangia</div><div class="holes">${fori}</div>
    <p class="hint" style="margin:6px 0 4px">u lungo il lato, v dallo spigolo esterno verso la punta.</p>
    <div class="xyz"><label>u<input class="field" id="h-u" value="50"></label><label>v<input class="field" id="h-v" value="15"></label>
    <label>Ø<input class="field" id="h-d" value="8"></label></div>
    <div class="row-btns"><button class="btn" id="h-add">Aggiungi foro</button></div>`;
}
function wireFlange(s) {
  const applica = () => inCoda(async () => apply(await call('edit_flange', s.feature, s.flange, { ...readFlange(), gap: $('#f-gap').value.trim() })));
  $('#f-apply').onclick = applica;
  ['#f-len', '#f-ang', '#f-gap'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') applica(); }; });
  $('#f-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('delete_flange', s.feature, s.flange))); };
  $('#h-add').onclick = () => inCoda(async () => apply(await call('add_flange_hole', s.feature, s.flange, $('#h-u').value, $('#h-v').value, $('#h-d').value)));
  document.querySelectorAll('[data-hdel]').forEach(b => { b.onclick = () => inCoda(async () => apply(await call('delete_flange_hole', s.feature, s.flange, +b.dataset.hdel))); });
}

// --------------------------------------------------------------- scheda Lamiera
function renderSheet() {
  const sh = S.sheet;
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
      <div class="row-btns"><button class="btn primary" data-cmd="export_dxf">Esporta sviluppo DXF…</button></div>`;
  }
  $('#tab-sheet').innerHTML = `<div class="sheet-cols"><div><h4>Dati di piega</h4>${tech}</div><div><h4>Pieghe</h4>${pieghe}</div><div><h4>Sviluppo</h4>${flat}</div></div>`;
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
  $('#modal-box').innerHTML = html;
  $('#modal').hidden = false;
  const close = () => { $('#modal').hidden = true; };
  wire(close);
  $('#modal-box').querySelector('input, button.primary')?.focus();
}

function newDialog() {
  const MODELLI = {
    telaio: { titolo: 'Telaio / tavolo', nota: 'Telaio sopra e 4 gambe in tubolare',
      campi: [['L', 'Lunghezza', 2000], ['P', 'Profondità', 1000], ['H', 'Altezza', 900], ['profilo', 'Profilo telaio', '40x40x3'], ['gambe', 'Profilo gambe', '40x40x3']] },
    zero: { titolo: 'Da zero', nota: 'Disegni il contorno, poi lamiera o piastra', campi: [] },
    vuoto: { titolo: 'Struttura libera', nota: 'Parti da un nodo e tira le aste', campi: [] },
    lamiera: { titolo: 'Lamiera', nota: 'Base piegata: poi clic su un lato per la flangia',
      campi: [['larghezza', 'Larghezza', 500], ['profondita', 'Profondità', 300], ['spessore', 'Spessore', 2],
        ['raggio', 'Raggio interno di piega', ''], ['k', 'K-factor', '']] },
    piastra: { titolo: 'Piastra', nota: 'Lamiera piana con foro, per DXF',
      campi: [['larghezza', 'Larghezza', 300], ['altezza', 'Altezza', 200], ['spessore', 'Spessore', 5], ['foro', 'Diametro foro', 30]] },
  };
  let kind = 'telaio';
  const disegna = () => {
    const m = MODELLI[kind];
    return `<h3>Nuovo progetto</h3>
      <div class="choice">${Object.entries(MODELLI).map(([k, v]) => `<button data-k="${k}" class="${k === kind ? 'on' : ''}">${esc(v.titolo)}<small>${esc(v.nota)}</small></button>`).join('')}</div>
      <div class="form"><label style="grid-column:1/-1">Nome<input class="field" id="n-name" value="${{ telaio: 'Tavolo', piastra: 'Piastra', vuoto: 'Struttura', lamiera: 'Lamiera', zero: 'Pezzo' }[kind]}"></label>
      ${m.campi.map(([k, l, v]) => `<label>${esc(l)}<input class="field" data-f="${k}" value="${esc(v)}"></label>`).join('')}</div>
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
        if (await apply(await call('new_project', kind, v)) && kind === 'zero') await enterSketch('S1');
      });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#n-ok').click(); if (ev.key === 'Escape') close(); };
  };
  modal(disegna(), wire);
}

async function openProject() {
  const r = await call('open_dialog');
  if (r.recovery) {
    modal(`<h3>C’è un salvataggio automatico più recente</h3><p>Il file <b>${esc(r.path)}</b> ha un salvataggio automatico fatto dopo l’ultimo
      salvataggio. Probabilmente il programma si è chiuso prima di salvare.</p>
      <div class="acts"><button class="btn" id="r-no">Apri il file salvato</button><button class="btn primary" id="r-ok">Recupera le modifiche</button></div>`,
    close => {
      const vai = rec => { close(); primaVolta = true; clearSelection(); inCoda(async () => apply(await call('open_path', r.path, rec), rec ? 'Modifiche recuperate.' : null)); };
      $('#r-no').onclick = () => vai(false); $('#r-ok').onclick = () => vai(true);
    });
    return;
  }
  if (r.ok) { primaVolta = true; clearSelection(); }
  await apply(r);
}

const CMDS = [
  { id: 'new', label: 'Nuovo progetto…', keys: 'Ctrl+N', run: newDialog },
  { id: 'open', label: 'Apri progetto…', keys: 'Ctrl+O', run: () => inCoda(openProject) },
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
  { id: 'fit', label: 'Adatta alla finestra', keys: 'F', run: () => goTo(null, true) },
  { id: 'toggle_dims', label: 'Mostra/nascondi quote', keys: 'Q', run: () => { showDims = !showDims; buildDims(); } },
  { id: 'palette', label: 'Cerca comando', keys: 'Ctrl+K', run: () => openPalette() },
];
const runCmd = id => CMDS.find(c => c.id === id)?.run();

document.addEventListener('click', ev => {
  const mi = ev.target.closest('.menu-item');
  for (const m of document.querySelectorAll('.menu-item')) if (m !== mi) m.classList.remove('open');
  if (mi && ev.target.parentElement === mi) { mi.classList.toggle('open'); return; }
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
  if (ev.key === 'Escape') {
    if (!$('#modal').hidden) { $('#modal').hidden = true; return; }
    if (linkFrom) { linkFrom = null; paintNodes(); return; }
    if (inCampo) { document.activeElement.blur(); return; }
    clearSelection(); return;
  }
  if (inCampo || ev.altKey || ev.metaKey) return;
  if (ev.key === 'Delete') { ev.preventDefault(); deleteSelected(); return; }
  const tasti = { f: 'fit', 0: 'view_iso', 7: 'view_top', 1: 'view_front', 3: 'view_right', q: 'toggle_dims' };
  if (tasti[k]) { ev.preventDefault(); runCmd(tasti[k]); }
});

// ===================================================================== modalità sketch (disegno libero)
// Vista dall'alto con griglia. Linea: clic sui punti, scrivi la lunghezza + Invio, clic sul primo punto
// per chiudere, Esc per finire. Rettangolo: due angoli. Cerchio: centro e raggio (o diametro scritto).
// Seleziona: clic su una linea o un cerchio, Canc per toglierlo. Le quote nascono da sole e si cambiano.
let SK = null;           // { sid, v (vista dal motore), tool, pts: [{id?, xy}], cursor: {xy, id, how}, sel: Set, buf }
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
const TOOLS = { line: 'Linea', rect: 'Rettangolo', circle: 'Cerchio', select: 'Seleziona' };

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
  SK = { sid, v: r.sketch, tool: 'line', pts: [], cursor: null, sel: new Set(), buf: '' };
  clearSelection();
  controls.enableRotate = false;
  for (const o of objs.values()) { o.mesh.material.transparent = true; o.mesh.material.opacity = 0.18; o.mesh.material.depthWrite = false; }
  nodesBox.style.display = 'none';
  $('#sk-bar').hidden = false;
  drawSketch();
  const pts = SK.v.points.map(p => p.xyz);
  const box = new THREE.Box3();
  if (pts.length > 1) pts.forEach(p => box.expandByPoint(v3(p)));
  else { box.expandByPoint(skToWorld([-50, -50])); box.expandByPoint(skToWorld([550, 350])); }
  if (objs.size) box.union(new THREE.Box3().setFromObject(model));
  fitBox(box, VISTE.view_top);
  setTool('line');
}
function exitSketch() {
  if (!SK) return;
  SK = null;
  controls.enableRotate = true;
  for (const o of objs.values()) { o.mesh.material.transparent = false; o.mesh.material.opacity = 1; o.mesh.material.depthWrite = true; }
  nodesBox.style.display = '';
  $('#sk-bar').hidden = true;
  $('#sk-tip').style.display = 'none';
  for (const g of [skGroup, skGrid, skRubber]) { g.traverse(x => x.geometry?.dispose()); g.clear(); }
  goTo(VISTE.view_iso);
  renderTree();
}
async function refreshSketch() {
  if (!SK) return;
  const r = await call('sketch_view', SK.sid);
  if (!r.ok) { exitSketch(); return; }
  SK.v = r.sketch;
  for (const id of [...SK.sel]) if (!SK.v.lines.some(l => l.id === id) && !SK.v.circles.some(c => c.id === id)) SK.sel.delete(id);
  drawSketch();
}
function setTool(t) {
  if (!SK) return;
  SK.tool = t; SK.pts = []; SK.buf = '';
  document.querySelectorAll('#sk-bar [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t));
  drawRubber();
}

function drawSketch() {
  for (const g of [skGroup, skGrid]) { g.traverse(x => x.geometry?.dispose()); g.clear(); }
  const v = SK.v;
  // griglia: 10 mm chiara, 100 mm più scura, assi dall'origine
  const lim = 3000, segs1 = [], segs2 = [];
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
    const mat = SK.sel.has(l.id) ? SK_SEL : SK.hover === l.id ? SK_HOV : SK_LINE;
    skGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([v3(l.pa), v3(l.pb)]), mat));
  }
  for (const c of v.circles) {
    const pts = [];
    const ctr = v3(c.center), x = v3(v.x_dir), y = v3(v.y_dir);
    for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; pts.push(ctr.clone().addScaledVector(x, c.r * Math.cos(a)).addScaledVector(y, c.r * Math.sin(a))); }
    const mat = SK.sel.has(c.id) ? SK_SEL : SK.hover === c.id ? SK_HOV : SK_LINE;
    skGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
  }
  const pg = new THREE.BufferGeometry().setFromPoints(v.points.map(p => v3(p.xyz)));
  skGroup.add(new THREE.Points(pg, new THREE.PointsMaterial({ color: 0x1C2228, size: 6, sizeAttenuation: false })));
  skGroup.position.copy(v3(v.z_dir).multiplyScalar(0.05));
  $('#sk-status').textContent = v.status;
  $('#sk-status').classList.toggle('bad', !v.ok);
  const libero = !v.used_by.length;
  $('#sk-make').hidden = !libero;
  ridisegna();
}

// cosa c'è sotto il mouse, con gli agganci: punto esistente, orizzontale/verticale, griglia
function skCursor(ev) {
  const xy = skPick(ev);
  if (!xy) return null;
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  let best = null;
  const cand = [...SK.v.points.map(p => ({ id: p.id, xy: p.xy })), ...SK.pts.filter(p => !p.id).map(p => ({ id: null, first: p === SK.pts[0], xy: p.xy }))];
  for (const p of cand) {
    const s = skScreen(p.xy), d = Math.hypot(s[0] - mx, s[1] - my);
    if (d < 10 && (!best || d < best.d)) best = { ...p, d };
  }
  if (best) return { xy: best.xy, id: best.id, how: best.id === 'O' ? 'origine' : 'punto', first: best.first };
  const st = skStep();
  let q = [Math.round(xy[0] / st) * st, Math.round(xy[1] / st) * st];
  let how = 'griglia';
  const last = SK.pts[SK.pts.length - 1];
  if (last && SK.tool === 'line') {
    const dx = xy[0] - last.xy[0], dy = xy[1] - last.xy[1];
    const ang = Math.abs(Math.atan2(dy, dx) * 180 / Math.PI);
    if (ang < 4 || ang > 176) { q = [q[0], last.xy[1]]; how = 'orizzontale'; }
    else if (Math.abs(ang - 90) < 4) { q = [last.xy[0], q[1]]; how = 'verticale'; }
  }
  return { xy: q, id: null, how };
}

function drawRubber() {
  skRubber.traverse(x => x.geometry?.dispose());
  skRubber.clear();
  const tip = $('#sk-tip');
  if (!SK || !SK.cursor) { tip.style.display = 'none'; ridisegna(); return; }
  const c = SK.cursor.xy, last = SK.pts[SK.pts.length - 1];
  const add = pts => {
    const g = new THREE.BufferGeometry().setFromPoints(pts.map(skToWorld));
    const l = new THREE.Line(g, SK_RUB); l.computeLineDistances(); skRubber.add(l);
  };
  let testo = '';
  if (SK.tool === 'line') {
    if (SK.pts.length > 1) add(SK.pts.map(p => p.xy));
    if (last) { add([last.xy, c]); testo = `${num(Math.hypot(c[0] - last.xy[0], c[1] - last.xy[1]), 2)} mm`; }
  } else if (SK.tool === 'rect' && last) {
    add([last.xy, [c[0], last.xy[1]], c, [last.xy[0], c[1]], last.xy]);
    testo = `${num(Math.abs(c[0] - last.xy[0]), 2)} × ${num(Math.abs(c[1] - last.xy[1]), 2)}`;
  } else if (SK.tool === 'circle' && last) {
    const r = Math.hypot(c[0] - last.xy[0], c[1] - last.xy[1]), pts = [];
    for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; pts.push([last.xy[0] + r * Math.cos(a), last.xy[1] + r * Math.sin(a)]); }
    add(pts); testo = `Ø ${num(2 * r, 2)}`;
  }
  const s = skScreen(c);
  const aggancio = SK.cursor.how !== 'griglia' ? ` · ${SK.cursor.how}` : '';
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
  return best?.id ?? null;
}

function skMove(ev) {
  if (ev.buttons) return;
  if (SK.tool === 'select') {
    const h = skHit(ev);
    if (h !== SK.hover) { SK.hover = h; drawSketch(); }
    SK.cursor = null; drawRubber();
    return;
  }
  SK.cursor = skCursor(ev);
  drawRubber();
}

const ptArg = p => p.id || p.xy;
function skClick(ev) {
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
  const p = { id: c.id, xy: c.xy };
  if (SK.tool === 'line') {
    if (SK.pts.length >= 3 && (c.first || (c.id && c.id === SK.pts[0].id))) { skFinish(true); return; }
    if (SK.pts.length && c.id && SK.pts.some(q => q.id === c.id)) { toast('Questo punto è già nella linea che stai disegnando.', 'err'); return; }
    SK.pts.push(p);
    if (SK.pts.length >= 2 && c.id && !SK.pts.slice(0, -1).some(q => q.id === c.id)) { skFinish(false); return; }   // agganciato a un punto che c'era: si collega lì
  } else if (SK.tool === 'rect') {
    if (!SK.pts.length) { SK.pts.push(p); }
    else { const a = SK.pts[0]; SK.pts = []; inCoda(async () => { await apply(await call('sketch_add_rectangle', SK.sid, ptArg(a), c.xy)); }); }
  } else if (SK.tool === 'circle') {
    if (!SK.pts.length) { SK.pts.push(p); }
    else { const a = SK.pts[0]; SK.pts = []; const r = Math.hypot(c.xy[0] - a.xy[0], c.xy[1] - a.xy[1]); if (r > 0) inCoda(async () => { await apply(await call('sketch_add_circle', SK.sid, ptArg(a), r)); }); }
  }
  SK.buf = '';
  drawRubber();
}
function skFinish(closed) {
  const pts = SK.pts;
  SK.pts = []; SK.buf = '';
  drawRubber();
  if (pts.length < 2) return;
  inCoda(async () => { await apply(await call('sketch_add_polyline', SK.sid, pts.map(ptArg), closed)); });
}
// lunghezza scritta: nella direzione del mouse (orizzontale/verticale se ci sei vicino)
function skTyped() {
  const v = parseFloat(SK.buf.replace(',', '.'));
  SK.buf = '';
  if (!(v > 0)) { toast('Scrivi un numero maggiore di zero.', 'err'); return; }
  const last = SK.pts[SK.pts.length - 1];
  if (!last) { toast('Prima clicca il punto di partenza.', 'err'); return; }
  if (SK.tool === 'circle') { const a = SK.pts[0]; SK.pts = []; inCoda(async () => { await apply(await call('sketch_add_circle', SK.sid, ptArg(a), v / 2)); }); drawRubber(); return; }
  const c = SK.cursor?.xy || [last.xy[0] + 1, last.xy[1]];
  let dx = c[0] - last.xy[0], dy = c[1] - last.xy[1];
  const L = Math.hypot(dx, dy) || 1;
  dx /= L; dy /= L;
  const ang = Math.abs(Math.atan2(dy, dx) * 180 / Math.PI);
  if (ang < 8 || ang > 172) { dx = Math.sign(dx) || 1; dy = 0; } else if (Math.abs(ang - 90) < 8) { dx = 0; dy = Math.sign(dy) || 1; }
  const q = [Math.round((last.xy[0] + dx * v) * 1000) / 1000, Math.round((last.xy[1] + dy * v) * 1000) / 1000];
  const primo = SK.pts[0];
  if (SK.tool === 'line' && SK.pts.length >= 3 && Math.hypot(q[0] - primo.xy[0], q[1] - primo.xy[1]) < 1e-6) { skFinish(true); return; }
  if (SK.tool === 'rect') { SK.pts = []; inCoda(async () => { await apply(await call('sketch_add_rectangle', SK.sid, ptArg(last), [last.xy[0] + (Math.sign(c[0] - last.xy[0]) || 1) * v, last.xy[1] + (Math.sign(c[1] - last.xy[1]) || 1) * v])); }); drawRubber(); return; }
  SK.pts.push({ id: null, xy: q });
  SK.cursor = { xy: q, id: null, how: 'scritto' };
  drawRubber();
}
function skKey(ev) {
  if (!SK || ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName) || !$('#modal').hidden || !$('#palette').hidden) return false;
  if (ev.ctrlKey || ev.altKey) return false;
  const k = ev.key;
  if (/^[0-9.,]$/.test(k) && SK.tool !== 'select' && SK.pts.length) { SK.buf += k; drawRubber(); return true; }
  if (k === 'Backspace' && SK.buf) { SK.buf = SK.buf.slice(0, -1); drawRubber(); return true; }
  if (k === 'Enter') { if (SK.buf) skTyped(); else if (SK.tool === 'line' && SK.pts.length >= 2) skFinish(false); return true; }
  if (k === 'Escape') {
    if (SK.buf) { SK.buf = ''; drawRubber(); return true; }
    if (SK.tool === 'line' && SK.pts.length >= 2) { skFinish(false); return true; }
    if (SK.pts.length) { SK.pts = []; drawRubber(); return true; }
    if (SK.sel.size) { SK.sel.clear(); drawSketch(); return true; }
    exitSketch(); return true;
  }
  if (k === 'Delete' && SK.sel.size) {
    const ids = [...SK.sel]; SK.sel.clear();
    inCoda(async () => { await apply(await call('sketch_delete', SK.sid, ids)); });
    return true;
  }
  const tasti = { l: 'line', r: 'rect', c: 'circle', s: 'select' };
  if (tasti[k.toLowerCase()]) { setTool(tasti[k.toLowerCase()]); return true; }
  if (['f', '0', '1', '3', '7', 'q'].includes(k.toLowerCase())) return false;
  return true;          // nient'altro deve scappare alla vista 3D mentre si disegna
}

function makeDialog(kind) {
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

$('#sk-bar').addEventListener('click', ev => {
  const b = ev.target.closest('button');
  if (!b || !SK) return;
  if (b.dataset.tool) setTool(b.dataset.tool);
  else if (b.dataset.make) makeDialog(b.dataset.make);
  else if (b.id === 'sk-done') exitSketch();
});

// ===================================================================== avvio
async function start() {
  S = await call('state');
  renderPanels();
  await loadScene();
  setInterval(() => call('autosave'), 60000);
  requestAnimationFrame(loop);
  window.__steelcad = { ready: true, get state() { return S; }, get nodes() { return nodes; }, get sketch() { return SK; },
    objs, select, camera, skScreen: xy => skScreen(xy), enterSketch };
}
if (DEV) start();
else if (window.pywebview?.api) start();
else window.addEventListener('pywebviewready', start, { once: true });
