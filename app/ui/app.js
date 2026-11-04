// SteelCAD: interfaccia. Tutta la geometria arriva già calcolata dal motore (Python):
// qui si disegna, si seleziona e si mandano le modifiche. Niente calcoli di CAD in JS.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { Line2 } from './vendor/lines/Line2.js';
import { LineGeometry } from './vendor/lines/LineGeometry.js';
import { LineMaterial } from './vendor/lines/LineMaterial.js';
import { LineSegments2 } from './vendor/lines/LineSegments2.js';
import { LineSegmentsGeometry } from './vendor/lines/LineSegmentsGeometry.js';

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
  asm_scassi: 'Faccio gli scassi…', asm_set_finitura: 'Cambio la finitura…', asm_set_acquisto: 'Aggiorno la distinta…', asm_new_part: 'Preparo il pezzo nuovo…',
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
      document.getElementById('att-tempo').textContent = s >= 12 ? `${Math.floor(s)} s · è un lavoro pesante, ancora un momento`
        : s >= 2 ? `${Math.floor(s)} s` : '';
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
let ultimaChiamata = null;                          // per ripetere la stessa chiamata con la soluzione di un errore
async function call(name, ...args) {
  if (!/^(state|scene|select|autosave|update_check|anteprima|anteprima_maglia|save_thumbnail|.*_preview|libreria_catalogo|asm_fori_uguali|tree_menu|drawing_fields)$/.test(name)) ultimaChiamata = [name, args];
  const attende = !/^live_/.test(name);             // la diretta aspetta il passo dopo: non è «Sto lavorando»
  if (attende) attesaInizio(name);
  try {
    if (!DEV) return await window.pywebview.api[name](...args);
    const r = await fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args) });
    return await r.json();
  } finally {
    if (attende) attesaFine();
  }
}

// le chiamate al motore vanno una alla volta, nell'ordine in cui le fai
let coda = Promise.resolve();
let inCorso = 0;                                     // quanti comandi in coda adesso
const inCoda = fn => { inCorso++; return (coda = coda.then(fn).catch(e => toast(String(e), 'err')).finally(() => { inCorso--; })); };
// 29/10: le tavole si preparano quando il programma è fermo (4 s senza mouse né tasti, niente in coda): aprendole
// sono già pronte. Il motore le fa solo se è libero, quindi non passano mai davanti a quello che fai
let ultimaAttivita = Date.now(), tavolePronte = null;
for (const t of ['pointerdown', 'keydown', 'wheel']) window.addEventListener(t, () => { ultimaAttivita = Date.now(); }, true);
setInterval(() => {
  if (!S || SK || PROVA || inCorso || Date.now() - ultimaAttivita < 4000) return;
  if (!S.tree?.children?.length && S.mode !== 'assembly') return;
  const v = `${S.path || S.name}:${sceneVersion}`;
  if (v === tavolePronte) return;
  tavolePronte = v;
  chiamaMuto('prepara_tavole').then(r => { if (r?.interrotto && tavolePronte === v) tavolePronte = null; }).catch(() => {});   // fermata: si riprova
}, 1500);

let S = null;            // ultimo stato del progetto
let sceneVersion = 0;
let sel = null;          // { id, face, ids }
let selForo = null;      // il foro o il taglio cliccato sul pezzo (dal pannello): Canc lo toglie
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
// luce da studio (23/10, «polish»): un ambiente con pannelli di luce per i riflessi dei metalli, resa fotografica
// dei colori, poca luce diretta (dà il verso alle facce) e un'ombra morbida a terra sotto il pezzo
renderer.toneMapping = THREE.LinearToneMapping;     // lineare: i colori RAL restano pieni (ACES li sbiadiva)
renderer.toneMappingExposure = 1.0;            // 04/11: tema chiaro, il pezzo grigio acciaio chiaro
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.VSMShadowMap;
function ambienteStudio() {
  const pm = new THREE.PMREMGenerator(renderer);
  const st = new THREE.Scene();
  const stanza = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial({ color: 0x5c636c, side: THREE.BackSide }));
  stanza.scale.set(24, 24, 16);
  st.add(stanza);
  const pannello = (w, h, x, y, z, forza) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(forza, forza, forza), side: THREE.DoubleSide }));
    m.position.set(x, y, z); m.lookAt(0, 0, 0); st.add(m);
  };
  pannello(10, 6, 0, 0, 7.8, 2.4);         // il grande pannello sopra (z in su)
  pannello(6, 4, -11.8, -4, 3, 3.2);       // di lato, da sinistra davanti
  pannello(5, 3, 10, 8, 2, 1.4);           // controluce, dietro a destra
  pannello(14, 1.2, 0, -11.8, -3, 1.8);    // una striscia bassa davanti: il riflesso sugli spigoli
  const env = pm.fromScene(st, 0.035).texture;
  pm.dispose();
  return env;
}
scene.environment = ambienteStudio();
const cielo = new THREE.HemisphereLight(0xffffff, 0x8E98A3, 1.0);   // 04/11: pareti più chiare (grigio acciaio chiaro)
cielo.position.set(0, 0, 1);   // il cielo sta sopra: l'asse Z
scene.add(cielo);
const sun = new THREE.DirectionalLight(0xffffff, 1.15);
sun.position.set(0.4, 0.6, 1);
camera.add(sun);
scene.add(camera);
// l'ombra a terra: una luce dall'alto solo per l'ombra, su un piano che prende solo l'ombra, appena sotto il pezzo
const luceOmbra = new THREE.DirectionalLight(0xffffff, 0.0001);
luceOmbra.castShadow = true;
luceOmbra.shadow.mapSize.set(2048, 2048);
luceOmbra.shadow.radius = 14;
luceOmbra.shadow.blurSamples = 16;
luceOmbra.shadow.bias = -0.0005;
const suolo = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.22, transparent: true, depthWrite: false }));
suolo.receiveShadow = true;
suolo.renderOrder = -2;
suolo.raycast = () => {};
scene.add(luceOmbra, luceOmbra.target, suolo);
function aggiornaSuolo() {
  const box = new THREE.Box3();
  model.traverse(o => { if (o.isMesh && o.visible && o.geometry) box.expandByObject(o); });
  if (box.isEmpty()) { suolo.visible = false; return; }
  const c = box.getCenter(new THREE.Vector3()), sz = box.getSize(new THREE.Vector3());
  const r = Math.max(sz.x, sz.y, sz.z, 1);
  const su = camera.up.clone().normalize();
  if (Math.abs(su.z) > 0.9999) {
    suolo.quaternion.identity();
    suolo.position.set(c.x, c.y, box.min.z - r * 0.004);
    suolo.scale.set(sz.x + r * 1.6, sz.y + r * 1.6, 1);
    luceOmbra.position.set(c.x - r * 0.55, c.y - r * 0.75, box.max.z + r * 1.6);   // di sbieco: l'ombra si vede di lato
    luceOmbra.target.position.set(c.x, c.y, box.min.z);
  } else {                                       // pezzo aperto dall'assieme: il pavimento è quello dell'assieme
    const q = [];
    for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1])
      q.push(new THREE.Vector3(i ? box.max.x : box.min.x, j ? box.max.y : box.min.y, k ? box.max.z : box.min.z).sub(c).dot(su));
    const giu = Math.min(...q), su_ = Math.max(...q);
    const a = new THREE.Vector3(1, 0, 0).applyQuaternion(new THREE.Quaternion().setFromUnitVectors(Z_SU, su));
    const b = su.clone().cross(a);
    suolo.quaternion.setFromUnitVectors(Z_SU, su);
    suolo.position.copy(c).addScaledVector(su, giu - r * 0.004);
    suolo.scale.set(r * 2.6, r * 2.6, 1);
    luceOmbra.position.copy(c).addScaledVector(a, -r * 0.55).addScaledVector(b, -r * 0.75).addScaledVector(su, su_ + r * 1.6);
    luceOmbra.target.position.copy(c).addScaledVector(su, giu);
  }
  luceOmbra.target.updateMatrixWorld();
  const cam = luceOmbra.shadow.camera;
  cam.left = -r * 1.1; cam.right = r * 1.1; cam.top = r * 1.1; cam.bottom = -r * 1.1;
  cam.near = r * 0.5; cam.far = r * 4 + sz.z;
  cam.updateProjectionMatrix();
  luceOmbra.shadow.needsUpdate = true;
  ridisegna();
}

const model = new THREE.Group();
const overlay = new THREE.Group();
let SCASSI = null;                              // le sagome degli scassi da far vedere sul pezzo scelto nell'assieme
const dimLines = new THREE.Group();
scene.add(model, overlay, dimLines);
const objs = new Map();
const EDGE = new THREE.LineBasicMaterial({ color: 0x2B3138 });
// 04/11: il plexiglass (look.opacity dal servizio) si vede come un vetro: trasparente, lucido, spigoli più leggeri
const EDGE_VETRO = new THREE.LineBasicMaterial({ color: 0x6F93AD, transparent: true, opacity: 0.7 });
function vetro(mat, look) {
  if (look?.opacity == null) return false;
  mat.transparent = true; mat.opacity = look.opacity; mat.depthWrite = false; mat.userData.vetro = look.opacity;
  mat.envMapIntensity = 1.4;                      // il riflesso dello studio sulla lastra
  return true;
}
const opacitaPiena = m => m.userData?.vetro ?? 1;
const DIM_MAT = new THREE.LineBasicMaterial({ color: 0x3A4A5C });
// 04/11: l'ingombro col colore delle quote (l'ambra è solo «da guardare»); si riconosce dal tratteggio e da ⤢
const ING_MAT = new THREE.LineDashedMaterial({ color: 0x3A4A5C, dashSize: 6, gapSize: 4 });
const C_HOVER = new THREE.Color(0x6E9BFF), C_SEL = new THREE.Color(0xFFB21A);   // passaggio del mouse blu chiaro, selezione gialla (04/11)
// 28/10: un pezzo giallo/arancio selezionato in ambra non si distingue: lì la selezione è blu, e i suoi spigoli si accendono
const C_SEL_BLU = new THREE.Color(0x2F7DE1);
const EDGE_SCELTO = new THREE.LineBasicMaterial({ color: 0x1E90FF });
const comeSel = c => { const a = {}, b = {}; c.getHSL(a); C_SEL.getHSL(b); return Math.abs(a.h - b.h) < 0.09 && a.s > 0.35; };

let daRidisegnare = true;
const ridisegna = () => { daRidisegnare = true; };
controls.addEventListener('change', ridisegna);

// 28/10: nei suggerimenti dei pulsanti anche il tasto rapido, dove c'è (preso dall'elenco dei comandi)
function tastiNeiSuggerimenti() {
  const tasti = Object.fromEntries((typeof CMDS !== 'undefined' ? CMDS : []).filter(c => c.keys).map(c => [c.id, c.keys]));
  document.querySelectorAll('[data-cmd][title]').forEach(b => {
    const k = tasti[b.dataset.cmd];
    if (k && !b.title.includes(`(${k})`) && !b.title.includes(k + ')')) b.title += ` (${k})`;
  });
}
// il pannello di sinistra (28/10): «deve essere collassabile o comunque da rimpicciolire». Larghezza e chiuso si
// ricordano; doppio clic sul bordo = larghezza normale
(function pannelloSinistra() {
  const leggi = k => { try { return localStorage.getItem(k); } catch { return null; } };
  const scrivi = (k, v) => { try { localStorage.setItem(k, v); } catch { /* va bene così */ } };
  const metti = w => { w = Math.max(190, Math.min(560, Math.round(w))); document.body.style.setProperty('--larg-sx', w + 'px'); return w; };
  const w0 = parseFloat(leggi('radius.sx.larg'));
  if (w0) metti(w0);
  if (leggi('radius.sx.chiuso') === '1') document.body.classList.add('sx-chiuso');
  const chiudi = on => { document.body.classList.toggle('sx-chiuso', on); scrivi('radius.sx.chiuso', on ? '1' : '0'); };
  document.getElementById('sx-chiudi').onclick = ev => { ev.stopPropagation(); chiudi(true); };
  document.getElementById('sx-apri').onclick = () => chiudi(false);
  const m = document.getElementById('sx-maniglia');
  m.addEventListener('pointerdown', ev => {
    ev.preventDefault(); m.setPointerCapture(ev.pointerId); document.body.classList.add('sx-trascina');
    const muovi = e => metti(e.clientX);
    const fine = e => { m.removeEventListener('pointermove', muovi); m.removeEventListener('pointerup', fine);
      document.body.classList.remove('sx-trascina'); scrivi('radius.sx.larg', metti(e.clientX)); };
    m.addEventListener('pointermove', muovi); m.addEventListener('pointerup', fine);
  });
  m.addEventListener('dblclick', () => { metti(270); scrivi('radius.sx.larg', 270); });
})();

// 28/10: in tutti i campi di numeri si possono scrivere conti (500/2+10), il risultato si vede mentre scrivi e diventa
// il valore quando confermi (Invio, o uscendo dal campo); con la rotellina, nel campo dove scrivi, il numero cresce o cala
(function campiNumerici() {
  const ESPR = /^[\d\s.,+\-*/()×]+$/;          // niente «x»: 40x40x3 è un profilo, non un conto
  const eConto = v => ESPR.test(v) && /\d\s*[+*/×]\s*[\d(]|\d\s*-\s*[\d(]|\)/.test(v.trim());
  const calcola = v => {
    const s = v.replace(/,/g, '.').replace(/×/g, '*');
    if (!/^[\d\s.+\-*/()]+$/.test(s)) return null;
    try { const r = Function(`"use strict"; return (${s})`)(); return Number.isFinite(r) ? Math.round(r * 1000) / 1000 : null; } catch { return null; }
  };
  const testo = n => String(n).replace('.', ',');
  const adatto = el => el && el.tagName === 'INPUT' && (!el.type || el.type === 'text') && !el.closest('#sk-cmd, .dd-tab, #tav-ed .te-lato, #te-sel') && !el.dataset.c && !el.list && !/ral|nome|name|cod|desc|forn|cerca|testo|tx-t|lt-n/i.test(el.id || '');
  let tip = null;
  const mostra = (el, r) => {
    if (!tip) { tip = document.createElement('div'); tip.id = 'conto-tip'; document.body.appendChild(tip); }
    if (r === null) { tip.hidden = true; return; }
    const b = el.getBoundingClientRect();
    tip.textContent = '= ' + testo(r); tip.hidden = false;
    tip.style.left = (b.right - tip.offsetWidth - 6) + 'px'; tip.style.top = (b.top - 24) + 'px';
  };
  const chiudi = el => {
    if (tip) tip.hidden = true;
    if (!adatto(el) || !eConto(el.value)) return;
    const r = calcola(el.value);
    if (r !== null) { el.value = testo(r); el.dispatchEvent(new Event('input', { bubbles: true })); }
  };
  document.addEventListener('input', e => { const el = e.target; if (adatto(el)) mostra(el, eConto(el.value) ? calcola(el.value) : null); }, true);
  document.addEventListener('keydown', e => { if (e.key === 'Enter' && adatto(e.target)) chiudi(e.target); }, true);
  document.addEventListener('change', e => chiudi(e.target), true);
  document.addEventListener('focusout', e => chiudi(e.target), true);
  document.addEventListener('wheel', e => {
    const el = e.target;
    if (!adatto(el) || document.activeElement !== el) return;
    const v = parseFloat(String(el.value).replace(',', '.'));
    if (!Number.isFinite(v) || !/^-?\d+([.,]\d+)?$/.test(el.value.trim())) return;
    e.preventDefault();
    const passo = e.shiftKey ? 10 : e.altKey ? 0.1 : 1;
    const n = Math.round((v + (e.deltaY < 0 ? passo : -passo)) * 1000) / 1000;
    el.value = testo(n);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    clearTimeout(el._ruota); el._ruota = setTimeout(() => el.dispatchEvent(new Event('change', { bubbles: true })), 450);
  }, { passive: false, capture: true });
})();

// 04/11 notte (occhio): un progetto appena aperto o creato si inquadra; se subito dopo la vista cambia misura (si chiude
// la pagina iniziale, compaiono la barra dei comandi o il cassetto) si inquadra di nuovo: prima a 1366 i pezzi restavano
// piccoli in un angolo, con la vista del progetto di prima
let appenaInquadrato = 0;
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
  if (performance.now() - appenaInquadrato < 1500 && !SK && !anim && objs.size)
    fitBox(new THREE.Box3().setFromObject(model), null, true, true);
  ridisegna();
}
new ResizeObserver(resize).observe(view);

function loop() {
  requestAnimationFrame(loop);
  if (anim) stepAnim();
  if (!daRidisegnare) return;
  daRidisegnare = false;
  suolo.visible = model.visible && !SK && !flatView && objs.size > 0;   // l'ombra solo col pezzo 3D a video
  renderer.render(scene, camera);
  placeDims();
  placeCube();
  placeBarra();
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
  // 03/11 (collaudo): il cartellino del mouse era ancora quello del progetto di prima («L 40×40×4 · 920» su un
  // cancello 60×40) finché non si muoveva il mouse: con la scena nuova si toglie, al prossimo movimento torna giusto
  hover = null; hoverEdge = null;
  const cartellino = document.getElementById('hover-tip');
  if (cartellino) { cartellino.style.display = 'none'; cartellino.textContent = ''; }
  interfPulisci();                                 // le interferenze di prima non valgono più
  if (ESPLOSO && !sc.objects.some(d => d.kind === 'instance')) {   // fuori dall'assieme: niente esploso né il suo pannello
    ESPLOSO = 0; esplosoPannello(false); document.querySelector('#ribbon [data-cmd="asm_esploso"]')?.classList.remove('on');
  }
  if (saldGroup) model.add(saldGroup);             // le saldature restano sul pezzo
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
    const base = new THREE.Color(d.look?.color || (d.kind === 'body' ? 0xCBD1D8 : 0xBAC2CA));   // grigio acciaio chiaro
    const mat = new THREE.MeshStandardMaterial({ color: base.clone(), metalness: d.look?.metal ?? 0.15, roughness: d.look?.rough ?? 0.55,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    mat.envMapIntensity = 0.45 + 0.8 * mat.metalness;    // i riflessi dello studio: pieni sui metalli, leggeri sulle vernici
    const lastra = vetro(mat, d.look);
    const mesh = new THREE.Mesh(g, mat);
    mesh.castShadow = !lastra;                         // il vetro non fa l'ombra piena
    mesh.userData.id = d.id;
    const pos = d.matrix ? new THREE.Matrix4().set(...d.matrix) : null;      // istanza di un assieme: dove sta
    const seg = [];
    for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
    const lines = new THREE.LineSegments(lg, lastra ? EDGE_VETRO : EDGE);
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
  if (typeof applicaVisibilita === 'function') applicaVisibilita();
  paint();
}

// ---- vista esplosa: ogni pezzo spostato dal centro dell'assieme in proporzione (solo a video, l'assieme non cambia).
// 29/10, «quando lo esplodo non si capisce niente» (pannello a doppia pelle): i pezzi uno dentro l'altro hanno quasi
// lo stesso centro e si spostavano insieme. Quelli che dopo lo spostamento dal centro si sovrappongono ancora si
// aprono a strati, in fila, nella direzione in cui il loro gruppo è più sottile (lo spessore della parete)
let ESPLOSO = 0, pianoEspl = null;
function pianoEsploso(ist) {
  const chiave = ist.map(o => o.mesh.uuid + ':' + o.pos.elements.map(x => x.toFixed(2)).join(',')).join('|');
  if (pianoEspl?.chiave === chiave) return pianoEspl;
  const scatole = ist.map(o => { o.mesh.geometry.computeBoundingBox(); return o.mesh.geometry.boundingBox.clone().applyMatrix4(o.pos); });
  const centri = scatole.map(b => b.getCenter(new THREE.Vector3()));
  const C = centri.reduce((a, b) => a.clone().add(b), new THREE.Vector3()).multiplyScalar(1 / centri.length);
  const radiale = centri.map(c => c.clone().sub(C));
  const F = 0.8;                                    // a esploso aperto: chi si sovrappone ancora va a strati
  const dopo = scatole.map((b, i) => b.clone().translate(radiale[i].clone().multiplyScalar(F)).expandByScalar(-0.5));
  const capo = ist.map((_, i) => i);
  const trova = i => (capo[i] === i ? i : (capo[i] = trova(capo[i])));
  const vol = b => { const v = b.getSize(new THREE.Vector3()); return Math.max(v.x, 1) * Math.max(v.y, 1) * Math.max(v.z, 1); };
  // solo le lastre (pareti, pelli, vetri, cornici: sottili rispetto alle altre due misure), con lo spessore nello
  // stesso verso: cassetti, mobili e telai restano come prima
  const lastra = scatole.map(b => {
    const v = b.getSize(new THREE.Vector3()), m = [['x', v.x], ['y', v.y], ['z', v.z]].sort((a, c) => a[1] - c[1]);
    return m[0][1] <= 0.2 * m[1][1] ? m[0][0] : null;
  });
  if (ist.length <= 400) {                          // uno dentro l'altro: per più di metà del più piccolo, anche dopo
    for (let i = 0; i < ist.length; i++) for (let j = i + 1; j < ist.length; j++) {
      if (!lastra[i] || lastra[i] !== lastra[j]) continue;
      if (dopo[i].isEmpty() || dopo[j].isEmpty() || !dopo[i].intersectsBox(dopo[j])) continue;
      const comune = dopo[i].clone().intersect(dopo[j]);
      if (vol(comune) > 0.5 * Math.min(vol(dopo[i]), vol(dopo[j]))) capo[trova(i)] = trova(j);
    }
  }
  const gruppi = {};
  ist.forEach((_, i) => (gruppi[trova(i)] = gruppi[trova(i)] || []).push(i));
  const strato = ist.map(() => new THREE.Vector3());
  for (const g of Object.values(gruppi)) {
    if (g.length < 2 || g.length > 8) continue;     // un gruppo grande è un mobile intero: resta com'era
    const tutto = new THREE.Box3();
    g.forEach(i => tutto.union(scatole[i]));
    const dim = tutto.getSize(new THREE.Vector3());
    const ax = dim.x <= dim.y && dim.x <= dim.z ? 'x' : dim.y <= dim.z ? 'y' : 'z';
    const passo = 0.25 * Math.max(dim.x, dim.y, dim.z) / F;
    // in fila dalla faccia di partenza (la pelle esterna di una parete parte da fuori: il centro la metteva dietro al vetro)
    const fila = [...g].sort((a, b) => (scatole[a].min[ax] - scatole[b].min[ax]) || (scatole[a].max[ax] - scatole[b].max[ax]));
    fila.forEach((i, k) => { strato[i][ax] = (k - (fila.length - 1) / 2) * passo; });
  }
  pianoEspl = { chiave, spost: radiale.map((r, i) => r.add(strato[i])) };
  return pianoEspl;
}
// 04/11: aperta la vista esplosa, a destra quanto aprirla e «Chiudi l'esploso»
function esplosoPannello(on) {
  document.getElementById('esploso-pan')?.remove();
  if (!on) return;
  clearSelection();
  const el = document.createElement('div');
  el.id = 'esploso-pan'; el.className = 'pannello-cmd';
  el.innerHTML = `<div class="pc-testa"><h3>Vista esplosa</h3><p>I pezzi si allontanano dal centro per vedere come si montano. Solo a video: l’assieme non cambia</p></div>
    <div class="pc-corpo"><section class="sezione"><h4>Quanto aprire</h4>
      <input type="range" class="cursore" id="esp-quanto" min="0.1" max="2" step="0.05" value="0.8" aria-label="Quanto aprire">
      <div class="riga"><span>Poco</span><span class="testo-2">Tanto</span></div>
      <p class="hint">Nelle tavole c’è il foglio dell’esploso con l’ordine di montaggio (Esporta, Tavole PDF).</p></section></div>
    <div class="pc-fondo"><button class="btn primary big" id="esp-chiudi">Chiudi l’esploso</button></div>`;
  document.body.appendChild(el);
  $('#esp-quanto').oninput = ev => esplodi(+ev.target.value);
  $('#esp-chiudi').onclick = () => runCmd('asm_esploso');
}
function esplodi(f) {
  ESPLOSO = f;
  const ist = [...objs.values()].filter(o => o.data.kind === 'instance' && o.pos);
  if (!ist.length) return;
  const { spost } = pianoEsploso(ist);
  ist.forEach((o, i) => {
    const d = spost[i].clone().multiplyScalar(f);
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
    const intero = o.data.kind === 'member' || o.data.kind === 'accessorio';
    const scelto = selIds.has(id) && (intero || sel.face == null || (sel.ids && sel.ids.length > 1));
    if (scelto) c = comeSel(o.base) ? C_SEL_BLU : C_SEL;
    else if (hover && hover.id === id && (intero || hover.face == null)) c = C_HOVER;
    matOf(o).color.copy(c);
    matOf(o).emissive.setRGB(c === o.base ? 0 : 0.08, c === o.base ? 0 : 0.06, c === C_SEL_BLU ? 0.12 : 0);
    if (o.lines) {                                 // gli spigoli del pezzo scelto, accesi: si vede anche se è dello stesso colore
      if (!o.lineeMat) o.lineeMat = o.lines.material;
      o.lines.material = scelto && S?.mode === 'assembly' ? EDGE_SCELTO : o.lineeMat;
    }
  }
  if (sel && sel.face != null && objs.has(sel.id)) faceOverlay(objs.get(sel.id), sel.face, C_SEL);
  if (sel && sel.hl && objs.has('body')) for (const i of sel.hl) faceOverlay(objs.get('body'), i, C_SEL);
  if (hover && hover.face != null && objs.has(hover.id) && !(sel && sel.id === hover.id && sel.face === hover.face))
    faceOverlay(objs.get(hover.id), hover.face, C_HOVER);
  paintScassi();
  paintEdges();
  ridisegna();
}

// --------------------------------------------------------------- bordi dove si può piegare
// Il bordo di una lamiera è una faccia spessa 1-2 mm: col mouse non si prende. Il motore manda i bordi
// liberi (lati della base senza flangia, punte delle flange): vicino al mouse si accendono, clic = flangia lì.
let bendEdges = [], hoverEdge = null, modelRadius = 100;
const edgeGroup = new THREE.Group();
scene.add(edgeGroup);
const EDGE_HOV = new THREE.MeshBasicMaterial({ color: 0x3F7BFF, depthTest: false, transparent: true, opacity: 0.85 });
const EDGE_SEL = new THREE.MeshBasicMaterial({ color: 0xFFB21A, depthTest: false });
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
  for (const e of PIEGA?.bordi || []) edgeGroup.add(edgeMesh(e, EDGE_SEL));     // i bordi scelti per «Piega i bordi»
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
    best = { e, d, P };
  }
  pickEdge.P = best?.P ?? null;                   // il punto del bordo più vicino al mouse
  return best?.e ?? null;
}
// ---- raccordo / smusso sugli spigoli del pezzo (piastre, pezzi pieni): si cliccano gli spigoli, poi Invio
let DRESS = null;
const DRESS_MAT = new THREE.LineBasicMaterial({ color: 0xFFB21A, depthTest: false });
const DRESS_HOV = new THREE.LineBasicMaterial({ color: 0x6E9BFF, depthTest: false });
function dressTool(kind) {
  if (DRESS?.group) model.remove(DRESS.group);
  DRESS = kind ? { kind, scelti: [], hover: null, group: new THREE.Group() } : null;
  if (DRESS) model.add(DRESS.group);
  $('#sk-foot').hidden = !DRESS;
  if (DRESS) dressHelp(); else setHelp('');
  paint();
}
function dressHelp() {
  const n = DRESS.scelti.length, nome = { fillet: 'Raccordo', chamfer: 'Smusso', weld: 'Saldatura' }[DRESS.kind];
  setHelp(`${nome}: clic sugli spigoli da ${{ fillet: 'arrotondare', chamfer: 'smussare', weld: 'saldare' }[DRESS.kind]} (si accendono)` +
    (n ? ` · ${n} scelt${n === 1 ? 'o' : 'i'}: Invio per ${DRESS.kind === 'weld' ? 'tipo e misura' : 'la misura'}` : '') + ' · Esc annulla');
}
// 28/10: anche nell'assieme (gli spigoli di tutte le copie, al loro posto): lì si saldano i pezzi tra loro.
// p: il punto nelle coordinate della scena (del pezzo, per il pezzo aperto); pl: lo stesso nel pezzo della copia
function pickBodyEdge(ev) {                          // lo spigolo sotto il mouse, e il punto più vicino
  const tutti = S?.mode === 'assembly' ? [...objs.values()].filter(o => o.data.kind === 'instance' && o.mesh.visible && o.data.edges)
    : [objs.get('body')].filter(Boolean);
  if (!tutti.length) return null;
  const r = canvas.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const scr = p => { const q = p.clone().project(camera); return [(q.x + 1) / 2 * r.width, (1 - q.y) / 2 * r.height]; };
  const maglie = tutti.map(o => o.mesh);
  let best = null;
  for (const o of tutti) {
    const W = o.mesh.matrixWorld, M = o.mesh.matrix;
    o.data.edges.forEach((e, k) => {
      for (let i = 0; i + 5 < e.length; i += 3) {
        const Al = new THREE.Vector3(e[i], e[i + 1], e[i + 2]), Bl = new THREE.Vector3(e[i + 3], e[i + 4], e[i + 5]);
        const A = Al.clone().applyMatrix4(W), B = Bl.clone().applyMatrix4(W);
        const a = scr(A), b = scr(B), dx = b[0] - a[0], dy = b[1] - a[1], LL = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((mx - a[0]) * dx + (my - a[1]) * dy) / LL));
        const d = Math.hypot(mx - a[0] - t * dx, my - a[1] - t * dy);
        if (d > 8 || (best && d >= best.d)) continue;
        const P = A.clone().lerp(B, t), dir = P.clone().sub(camera.position), dist = dir.length();
        ray.set(camera.position, dir.normalize());
        const hit = ray.intersectObjects(maglie, false)[0];
        if (hit && hit.distance < dist - 0.5) continue;  // dietro a un pezzo
        const Pl = Al.clone().lerp(Bl, t), Pm = Pl.clone().applyMatrix4(M);
        best = { id: o.data.id, k, d, p: [Pm.x, Pm.y, Pm.z], pl: [Pl.x, Pl.y, Pl.z] };
      }
    });
  }
  return best;
}
function dressDraw() {
  DRESS.group.clear();
  const linea = (h, mat) => {
    const o = objs.get(h.id);
    if (!o) return;
    const e = o.data.edges[h.k], pts = [];
    for (let i = 0; i + 2 < e.length; i += 3) pts.push(new THREE.Vector3(e[i], e[i + 1], e[i + 2]).applyMatrix4(o.mesh.matrix));
    DRESS.group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
  };
  const uguale = (a, b) => a && b && a.id === b.id && a.k === b.k;
  for (const c of DRESS.scelti) linea(c, DRESS_MAT);
  if (DRESS.hover && !DRESS.scelti.some(c => uguale(c, DRESS.hover))) linea(DRESS.hover, DRESS_HOV);
  paint();
}
function dressMove(ev) {
  const h = pickBodyEdge(ev);
  const v = DRESS.hover;
  if ((h?.id ?? null) !== (v?.id ?? null) || (h?.k ?? null) !== (v?.k ?? null)) { DRESS.hover = h ? { id: h.id, k: h.k } : null; dressDraw(); }
}
function dressClick(ev) {
  const h = pickBodyEdge(ev);
  if (!h) { toast('Avvicinati a uno spigolo finché si accende in blu, poi clicca.'); return; }
  const i = DRESS.scelti.findIndex(c => c.id === h.id && c.k === h.k);
  if (i >= 0) DRESS.scelti.splice(i, 1); else DRESS.scelti.push(h);
  dressHelp(); dressDraw();
}
let ultimaSaldatura = { tipo: 'angolo', a: '4' };
function dressFine() {
  if (!DRESS?.scelti.length) { toast('Scegli almeno uno spigolo.', 'err'); return; }
  if (DRESS.kind === 'weld') {                     // saldatura: tipo e misura, poi sul pezzo e in distinta
    const punti = S?.mode === 'assembly' ? DRESS.scelti.map(c => ({ inst: c.id, p: c.pl })) : DRESS.scelti.map(c => c.p), q = ultimaSaldatura;
    modal(`<h3>Saldatura su ${punti.length} spigol${punti.length === 1 ? 'o' : 'i'}</h3>
      <div class="form"><label>Tipo<select class="field" id="sw-tipo">${[['angolo', 'D’angolo (a gola)'], ['V', 'Di testa a V'], ['I', 'Di testa a I']].map(([v, t]) =>
        `<option value="${v}"${q.tipo === v ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
      <label>Misura<span class="inp"><input class="field" id="sw-a" value="${esc(q.a)}" placeholder="es. 4"><i>mm</i></span></label></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Aggiungi la saldatura</button></div>`, close => {
      $('#m-no').onclick = close;
      const vai = () => {
        ultimaSaldatura = { tipo: $('#sw-tipo').value, a: $('#sw-a').value.trim() };
        close(); dressTool(null);
        inCoda(async () => { const r = await call('add_saldatura', punti, ultimaSaldatura); await apply(r, r.message); });
      };
      $('#m-ok').onclick = vai;
      $('#sw-a').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
      $('#sw-a').select();
    });
    return;
  }
  const kind = DRESS.kind, punti = DRESS.scelti.map(c => c.p), ultimo = DRESS.ultimo || (kind === 'fillet' ? '5' : '1');
  modal(`<h3>${kind === 'fillet' ? 'Raccordo' : 'Smusso'} su ${punti.length} spigol${punti.length === 1 ? 'o' : 'i'}</h3>
    <div class="form"><label>${kind === 'fillet' ? 'Raggio' : 'Misura (a 45°)'}<span class="inp"><input class="field" id="dr-v" value="${esc(ultimo)}"><i>mm</i></span></label><span></span></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">${kind === 'fillet' ? 'Raccorda' : 'Smussa'}</button></div>`, close => {
    $('#m-no').onclick = close;
    const vai = () => {
      const v = $('#dr-v').value.trim(); close();
      dressTool(null);
      inCoda(async () => { const r = await call('add_edge_dress', kind, punti, v); await apply(r, r.message); });
    };
    $('#m-ok').onclick = vai;
    $('#dr-v').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
    conAnteprima('add_edge_dress', () => [kind, punti, $('#dr-v').value.trim()]);
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
  // 04/11 (regola 2): cos'è, cosa puoi fare, i campi, il pulsante blu in fondo
  $('#props').innerHTML = pannelloLam({ titolo: fatta ? 'Piega sul bordo' : 'Piega su questo bordo',
    cose: libero ? 'altezza fuori tutto dallo spigolo esterno' : 'sul fianco della piega, verso dentro',
    azioni: fatta ? [...azioniFaccia(fatta).slice(0, 3), azioneLam('delete', 'Togli questa piega', 'id="f-del"', 'danger', 'Canc')] : [],
    corpo: `${libero ? '' : '<p class="hint">Verso dentro a 90°: la parete che pieghi dopo su quel lato sale e resta dentro (gioco 0,2 mm).</p>'}
    ${flangeFields(d, VERSI_PUNTA, POS_UI)}
    ${libero ? `<details class="fsec"${d.trim0 || d.trim1 ? ' open' : ''}><summary>Gioco agli angoli</summary><div class="ff"><label>Gioco all’inizio<span class="inp"><input class="field" id="f-t0" value="${esc(String(d.trim0 ?? '').replace('.', ','))}" placeholder="auto"><i>mm</i></span></label>
      <label>Gioco alla fine<span class="inp"><input class="field" id="f-t1" value="${esc(String(d.trim1 ?? '').replace('.', ','))}" placeholder="auto"><i>mm</i></span></label></div>
      <p class="hint">Vuoto: se la piega tocca un’altra parete si accorcia da sola in quell’angolo.</p></details>` : ''}`,
    fine: `<button class="btn primary big" id="f-add">${fatta ? 'Cambia la piega' : 'Aggiungi la piega'}</button>` });
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
  const campi = () => { const f = readFlange(); if (libero) { f.trim0 = $('#f-t0').value.trim(); f.trim1 = $('#f-t1').value.trim(); } return f; };
  if (libero) anteprimaPannello(fatta ? 'edit_edge_flange' : 'add_edge_flange', () => (fatta ? [feature, campi()] : [e.face, e.ea, e.eb, campi()]));
  else anteprimaPannello('set_ear', () => [feature, flange, end, true, campi()]);
}
function selectEdge(e) {
  selTok++; selGen++;
  if ($('#modal').hidden) anteprimaVia();
  sel = { id: 'edge=' + e.id };
  hover = null;
  aggiornaLayout();
  paint(); renderTree(); paintNodes();
  if (e.kind === 'side' || e.kind === 'libero') { pannelloPiegaBordo(e); return; }
  const punta = e.kind === 'tip';
  const d = punta ? ultimaPunta : ultimaFlangia;
  // 29/10: la barretta sul bordo; la piega si fa subito con l'ultima lunghezza, poi si cambia la sua quota sul pezzo
  if (MINI.dove && performance.now() - MINI.dove.t < 2500) {
    sel.soloMini = true; aggiornaLayout();
    MINI.ancora = MINI.dove.p ? MINI.dove.p.clone() : v3(e.a).lerp(v3(e.b), 0.5);
    MINI.dove = null; MINI.s = null;
    togliQuote();
    const versi = punta ? VERSI_PUNTA : VERSI_UI;
    const prova = verso => on => (on ? anteprima('add_flange', () => [e.feature, punta ? null : e.ref, { ...d, direction: verso }, punta ? e.ref : null], null) : anteprimaVia());
    const piega = verso => {
      anteprimaVia();
      const f = { ...d, direction: verso };
      if (punta) ultimaPunta = f; else ultimaFlangia = f;
      schedaCalcola(true);
      const chi = 'edge=' + e.id;
      inCoda(async () => {
        const r = await call('add_flange', e.feature, punta ? null : e.ref, f, punta ? e.ref : null);
        if (await apply(r)) {
          // 03/11: se mentre la piega si faceva hai cliccato altro, resta quello che hai cliccato (vince l'ultimo clic).
          // Il bordo piegato sparisce col pezzo nuovo (la selezione si svuota): allora si passa alla flangia nuova
          if (!sel || sel.id === chi) { MINI.nuova = true; if (r.select) await select(r.select); }   // la flangia nuova, con le sue quote
          if (r.ask_tip_corners) askTipCorners(r.ask_tip_corners);
          toast(`Piega ${virgola(f.length)} mm ${versi[verso].toLowerCase()}: clicca «${virgola(f.length)}» sul pezzo per cambiarla.`);
        } else schedaCalcola(false);
      });
    };
    barretta(punta ? 'Punta della flangia' : `Bordo ${latoOfficina(e.label)}`, [
      ['flange', `Piega ${versi.up.toLowerCase()}`, () => piega('up'), '', prova('up')],
      ['fold', `Piega ${versi.down.toLowerCase()}`, () => piega('down'), '', prova('down')],
      ['pattern_rect', 'Piega anche altri bordi (tutti uguali)', () => { anteprimaVia(); nascondiMini(); pieghePiuBordi(e); }]],
    { chi: 'edge=' + e.id, scritte: true, piu: () => { nascondiMini(); MINI.dove = null; selectEdge(e); } });
    return;                                        // il pannello completo solo con «⋯»
  }
  $('#props').innerHTML = pannelloLam({ titolo: 'Flangia su questo bordo', cose: `bordo: ${esc(pieghePerNome(e.label, e.feature))}`,
    azioni: [azioneLam('pattern_rect', 'Piega anche altri bordi', 'id="f-piu-bordi"', '', 'Più bordi insieme, tutti uguali (una vaschetta)')],
    corpo: `<p class="hint">${punta ? 'Piega sul bordo libero della flangia: la sua lunghezza resta la quota esterna fino allo spigolo della nuova piega.' : 'Lunghezza dallo spigolo esterno alla punta.'}</p>
    ${flangeFields(d, punta ? VERSI_PUNTA : VERSI_UI, POS_UI)}`,
    fine: `<button class="btn primary big" id="f-add">Aggiungi flangia su ${esc(pieghePerNome(e.label, e.feature))}</button>` });
  $('#f-piu-bordi').onclick = () => { anteprimaVia(); pieghePiuBordi(e); };
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
  anteprimaPannello('add_flange', () => [e.feature, punta ? null : e.ref, readFlange(), punta ? e.ref : null]);
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
  // da che parte guarda la faccia cliccata (per le aste: su quale faccia del tubo si disegna)
  const normal = hit.face ? hit.face.normal.clone().transformDirection(hit.object.matrixWorld).toArray() : null;
  return { id: o.data.id, face, name: o.data.name, normal, point: hit.point.clone() };
}
let ultimoClic = null;                        // l'ultima cosa cliccata nel 3D, con la normale della faccia

const tip = $('#hover-tip');
let premuto = null;
let destroGiu = null;
canvas.addEventListener('pointerdown', ev => { if (ev.button === 2) destroGiu = [ev.clientX, ev.clientY]; }, true);
// 04/11 (percorso D, Appoggia): al clic il cartellino del mouse sparisce, se no resta sopra il pezzo appena spostato
canvas.addEventListener('pointerdown', () => { tip.style.display = 'none'; }, true);
canvas.addEventListener('contextmenu', ev => {
  ev.preventDefault();
  if (S?.mode !== 'assembly' || SK || !destroGiu || Math.hypot(ev.clientX - destroGiu[0], ev.clientY - destroGiu[1]) > 5) return;
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2((ev.clientX - r.left) / r.width * 2 - 1, -(ev.clientY - r.top) / r.height * 2 + 1), camera);
  const maglie = [...objs.values()].filter(o => o.data.kind === 'instance' && o.mesh.visible).map(o => o.mesh);
  const hit = ray.intersectObjects(maglie, false)[0];
  const o = hit && [...objs.values()].find(x => x.mesh === hit.object);
  if (o) menuPezzoAssieme(o.data.id, ev.clientX, ev.clientY);
});
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
  if (FORO && !$('#modal').hidden && $('#fo-corpo')) { foroMove(ev); return; }
  if (PIEGA && !$('#modal').hidden && $('#pg-corpo')) { piegaMove(ev); return; }
  const he = pickEdge(ev);
  if (he !== hoverEdge) { hoverEdge = he; paint(); }
  if (he) {
    if (hover) { hover = null; paint(); }
    tip.textContent = `Bordo ${pieghePerNome(latoOfficina(he.label), he.feature)}: clic per piegare qui`;
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
  if (PUNTO && h && h.id === PUNTO.id && $('#p-punto-q')) {
    const q = puntoMisura(h.point);
    puntoSegno(q);
    tip.textContent = `A ${virgola(q)} ${PUNTO.vert ? 'da terra' : 'dall’inizio'} · clic: prendi questa misura`;
    const r = view.getBoundingClientRect();
    tip.style.left = (ev.clientX - r.left + 14) + 'px';
    tip.style.top = (ev.clientY - r.top + 14) + 'px';
    tip.style.display = 'block';
    return;
  }
  if (h) {
    const o = objs.get(h.id);
    const f = h.face != null ? o.data.faces.find(x => x.index === h.face) : null;
    tip.textContent = h.face != null ? (o.data.kind === 'instance' && f?.label ? f.label : `${o.data.name}: ${(f?.label || 'faccia').replace(/ di "[^"]*"$/, '')}`) : h.name;   // 04/11: il nome una volta sola
    // il cartellino di un tubo: il nome da officina in grassetto, sotto tubo e lunghezza (notte 03/11)
    const parti = h.face == null && o.data.kind === 'member' ? String(h.name || '').split(' — ') : [];
    tip.classList.toggle('t-cartellino', parti.length > 1);
    if (parti.length > 1) tip.innerHTML = `<b>${esc(parti[0])}</b><span>${esc(parti.slice(1).join(' ').replace(' · ', ', lungo '))} mm</span>`;
    if (sel && sel.id === h.id && sel.face === h.face && MINI.s?.kind === 'flange' && !MINI.faccia) tip.textContent += ' · clic ancora: la faccia';
    const r = view.getBoundingClientRect();
    tip.style.left = (ev.clientX - r.left + 14) + 'px';
    tip.style.top = (ev.clientY - r.top + 14) + 'px';
    tip.style.display = 'block';
  } else tip.style.display = 'none';
});
canvas.addEventListener('pointerleave', () => { hover = null; hoverEdge = null; tip.style.display = 'none'; paint(); });
canvas.addEventListener('pointerup', ev => {
  if (!premuto || Math.hypot(ev.clientX - premuto.x, ev.clientY - premuto.y) > 4 || ev.button !== 0) return;
  if (SK) { if ($('#modal').hidden || !$('#modal').classList.contains('laterale')) skClick(ev); return; }   // con l'anteprima aperta il clic non disegna (si gira il 3D)
  if (FORO && !$('#modal').hidden && $('#fo-corpo')) { foroClic(ev); return; }   // finestra del foro: clic = dove va, o un'altra faccia
  if (PIEGA && !$('#modal').hidden && $('#pg-corpo')) { piegaClic(ev); return; }
  if (ANGOLI && !$('#modal').hidden && $('#ag-corpo')) return;                      // «Angoli tondi»: si cliccano i cerchi   // «Piega i bordi»: clic = un bordo in più o in meno
  if (MIS) { misClick(ev); return; }
  if (DRESS) { dressClick(ev); return; }
  if (S?.mode === 'assembly' && ASM.tool) { asmClick(ev); return; }
  const he = pickEdge(ev);
  if (he) { MINI.dove = { p: pickEdge.P, t: performance.now() }; selectEdge(he); return; }
  const h = pick(ev);
  ultimoClic = h;
  if (TRAV && h && objs.get(h.id)?.data?.kind === 'member') { cliccaTraverso(h.id); return; }
  if (PUNTO && h && h.id === PUNTO.id && $('#p-punto-q')) { puntoPreso(h.point); return; }
  if (DIVSCEGLI && h && objs.get(h.id)?.data?.kind === 'member') { DIVSCEGLI = false; passoTubi(null); ultimoClic = h; inCoda(async () => { await select(h.id); await iniziaDividi({ id: h.id }); }); return; }
  if (DIVSCEGLI) { DIVSCEGLI = false; passoTubi(null); }
  MINI.dove = { p: h?.point ?? null, t: performance.now(), id: h?.id };      // la barretta compare qui
  // secondo clic sulla stessa flangia: la sua faccia (disegna, fora, taglia lì)
  if (h && sel && sel.id === h.id && sel.face === h.face && MINI.s?.kind === 'flange' && !MINI.faccia && document.getElementById('mini-barra')) {
    MINI.faccia = true; miniBarra(MINI.s); return;
  }
  if (h) select(h.id, h.face); else clearSelection();
});

// Traverso tra due tubi (22/10): clic sul primo, clic sul secondo, poi altezza da terra e «anche dietro»
let TRAV = null;
function iniziaTraverso(primo = null) {
  if (!S?.cutlist?.rows?.length) { toast('Prima serve una struttura.', 'err'); return; }
  TRAV = { primo, secondo: null };
  if (primo) { sel = { id: primo, ids: [primo] }; paint(); }
  pannelloTraverso();
}
function finisciTraverso() { TRAV = null; passoTubi(null); clearSelection(); }
function cliccaTraverso(id) {
  if (!TRAV.primo) TRAV.primo = id;
  else if (id !== TRAV.primo) TRAV.secondo = id;
  sel = { id, ids: [TRAV.primo, TRAV.secondo].filter(Boolean) };
  paint();
  if (TRAV.primo && TRAV.secondo) {
    // in piedi o sdraiati, e la misura «in mezzo» (03/11: per metterlo in mezzo si toglievano 15 mm a mano)
    const [st, a] = TRAV.primo.split('/'), b = TRAV.secondo.split('/')[1];
    chiamaMuto('traverso_info', st, a, b).then(r => { if (TRAV && r.ok) { TRAV.info = r; pannelloTraverso(); } });
  }
  pannelloTraverso();
}
function pannelloTraverso() {
  const nome = id => objs.get(id)?.data?.name?.split(' — ')[0] || 'tubo';
  apriPannelloTubi();
  const pronto = TRAV.primo && TRAV.secondo;
  passoTubi(!TRAV.primo ? 'Clicca il primo tubo, per esempio una gamba' : !TRAV.secondo ? `Ora clicca il secondo tubo (il primo è «${nome(TRAV.primo)}»)`
    : 'Scrivi a che misura va il traverso, a destra', pronto ? [['Invio', 'aggiungi'], ['Esc', 'annulla']] : [['Esc', 'annulla']]);
  // 04/11 notte (attriti, E 7): il primo tubo è del telaio sopra: la croce si fa prima con «Dividi»
  if (TRAV.primo && !TRAV.secondo && tuboDaDividere(TRAV.primo)) {
    passoTubi('Ora clicca il secondo tubo');          // corta: accanto c'è il consiglio (il primo è già giallo)
    consiglioDividi(TRAV.primo, true);
  }
  const inPiedi = pronto && (TRAV.info ? TRAV.info.in_piedi : [TRAV.primo, TRAV.secondo].every(id => /^(Gamba|Montante|Sbarra)/.test(nome(id))));
  const rif = TRAV.rif || (inPiedi ? 'sotto' : 'centro');
  const scelte = inPiedi ? [['sotto', 'Sotto il tubo'], ['meta', 'A metà tubo'], ['sopra', 'Sopra il tubo']]
    : [['centro', 'Al centro del tubo'], ['bordo', 'Al bordo del tubo']];
  $('#props').innerHTML = `<div class="t-pan"><h3>Nuovo traverso</h3>
    <p class="t-cose">${pronto ? `Tra «${esc(nome(TRAV.primo))}» e «${esc(nome(TRAV.secondo))}»` : 'Clicca due tubi nel disegno: il traverso va tra loro.'}</p>
    ${pronto ? `<section class="sezione"><label class="lbl" for="tr-q">${inPiedi ? 'Altezza da terra' : 'Distanza dall’inizio del tubo, da sinistra o da davanti'}</label>
    <div class="t-in-riga"><span class="campo-unita"><input class="field" id="tr-q" value="${esc(TRAV.q || '400')}"><i>mm</i></span>
      <button class="btn" id="tr-mezzo" title="Scrive la misura che lo mette in mezzo">${inPiedi ? 'A metà altezza' : 'In mezzo'}</button></div>
    <div class="sub">La misura arriva</div>
    <div class="seg">${scelte.map(([k, t]) => `<button class="btn${rif === k ? ' on' : ''}" data-rif="${k}">${t}</button>`).join('')}</div></section>
    <section class="sezione"><label class="lbl">Tubo<input class="field" id="tr-prof" list="dl-prof" value="${esc(TRAV.prof || TRAV.info?.profilo || ultimaAsta.profile || '40x40x3')}"></label>
    <datalist id="dl-prof">${(profili || []).map(p => `<option value="${esc(p)}">`).join('')}</datalist>
    <label class="check"><input type="checkbox" id="tr-dietro" ${TRAV.dietro === false ? '' : 'checked'}> Anche il gemello dall’altra parte, alla stessa misura</label></section>
    <div class="t-piede"><button class="btn" id="tr-no">Annulla</button><button class="btn primary" id="tr-ok">Aggiungi il traverso</button></div>`
    : '<div class="t-piede"><button class="btn" id="tr-no">Annulla</button></div>'}</div>`;
  $('#tr-no').onclick = () => { anteprimaVia(); finisciTraverso(); };
  const tieni = () => { TRAV.q = $('#tr-q').value; TRAV.prof = $('#tr-prof').value; TRAV.dietro = $('#tr-dietro').checked; };
  document.querySelectorAll('[data-rif]').forEach(b => { b.onclick = () => { tieni(); TRAV.rif = b.dataset.rif; pannelloTraverso(); }; });
  if (!pronto) return;
  $('#tr-mezzo').onclick = () => {
    tieni();
    if (TRAV.info) TRAV.q = String(TRAV.info.mezzo).replace('.', ',');
    TRAV.rif = inPiedi ? 'meta' : 'centro';
    pannelloTraverso();
  };
  const argomenti = () => {
    const st = TRAV.primo.split('/')[0], a = TRAV.primo.split('/')[1], b = TRAV.secondo.split('/')[1];
    return [st, a, b, $('#tr-q').value.trim(), rif, $('#tr-prof').value.trim(), $('#tr-dietro').checked, ''];
  };
  const vai = () => {
    const args = argomenti(), dietro = args[6];
    inCoda(async () => {
      const r = await call('add_traverso', ...args);
      if (!r.ok && dietro && /altra parte/.test(r.message || '')) { toast(r.message, 'err'); return; }
      if (await apply(r)) { anteprimaVia(); TRAV = null; passoTubi(null); await select(r.select); }
    });
  };
  $('#tr-ok').onclick = vai;
  $('#tr-q').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
  anteprimaPannello('add_traverso', argomenti);
  $('#tr-q').focus(); $('#tr-q').select();
}

// DIVIDI (03/11, il telaio 807 × 725 × 795 di Stefano: «complicatissimo, il contrario di intuitivo»): clic su un tubo
// del fianco o del telaio sopra → in quante parti → montanti e traversi a filo del lato, quadri uguali. Dove si
// incrociano uno passa intero e l'altro si taglia in due (come in officina)
let DIV = null, DIVSCEGLI = false;
// il lato proposto da Dividi, colorato nel 3D (03/11: «evidenzia il lato proposto»): un velo giallo coi bordi
let latoMesh = null;
function latoAcceso(rett) {
  if (latoMesh) { scene.remove(latoMesh); latoMesh.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); }); latoMesh = null; }
  if (rett?.length === 4) {
    const p = rett.map(v3), g = new THREE.BufferGeometry().setFromPoints([p[0], p[1], p[2], p[0], p[2], p[3]]);
    latoMesh = new THREE.Group();
    latoMesh.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0xFFB21A, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false })));
    latoMesh.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(p), new THREE.LineBasicMaterial({ color: 0xFFB21A })));
    latoMesh.renderOrder = 40;
    scene.add(latoMesh);
  }
  ridisegna();
}
async function iniziaDividi(s) {
  const [st, mid] = s.id.split('/');
  // prima il lato che hai cliccato: la faccia del tubo che guardava verso di te (il sopra del tubo → il telaio
  // sopra; il davanti del tubo → il davanti). Il lato proposto si accende nel 3D
  const n = ultimoClic?.id === s.id ? ultimoClic.normal : null;
  const r = await chiamaMuto('dividi_info', st, mid, n);
  if (!r.ok) { toast(r.message, 'err'); return; }
  const f = r.facce[0];
  // «uguale anche dall'altra parte» già spuntato per i fianchi (di solito sono uguali); davanti e dietro no
  DIV = { st, mid, info: r, faccia: f.key, u: '2', v: '2', mu: '', mv: '', rif: 'centro', opposta: !!f.opposta && /sinistra|destra/.test(f.key), chiudi: false, prof: r.profilo };
  pannelloDividi();
}
function dividiArgomenti() {
  const leggi = k => {
    const n = DIV[k];
    if (n === 'mis') {
      const misure = ($(`#dv-m${k}`)?.value || '').split(/[\s;]+/).map(x => x.trim()).filter(Boolean);
      return misure.length ? { misure, rif: DIV.rif } : null;
    }
    return n === '1' ? null : { parti: +n };
  };
  return [DIV.st, DIV.mid, DIV.faccia, leggi('u'), leggi('v'), !!$('#dv-opp')?.checked, $('#dv-prof')?.value.trim() || DIV.prof, !!$('#dv-chiudi')?.checked];
}
function pannelloDividi() {
  const f = DIV.info.facce.find(x => x.key === DIV.faccia);
  apriPannelloTubi();
  if (f.tubi?.length) { sel = { id: `${DIV.st}/${DIV.mid}`, ids: f.tubi.filter(id => objs.has(id)) }; paint(); }   // il lato che si divide, acceso
  latoAcceso(f.rett);                                // e il lato colorato nel 3D (si vede anche con l'anteprima)
  const sopra = !f.in_piedi;
  // come si chiama ogni direzione sul lato scelto (in piedi: montanti e traversi; sopra: da davanti a dietro…)
  const lungoX = f.key === 'davanti' || f.key === 'dietro' || sopra;
  const nomeU = sopra ? 'Tubi da davanti a dietro' : 'Montanti (in piedi)';
  const nomeV = sopra ? 'Tubi da sinistra a destra' : 'Traversi (sdraiati)';
  const daU = lungoX ? 'da sinistra' : 'da davanti', daV = sopra ? 'da davanti' : 'da terra';
  const quanto = k => k === 'u' ? (lungoX ? 'larghezza' : 'profondità') : (sopra ? 'profondità' : 'altezza');
  const riga = (k, nome, lung, da) => `<section class="sezione"><h4>${nome}</h4><p class="hint">Dividono ${quanto(k)} ${virgola(lung)} mm</p>
    <div class="seg">${[['1', 'No'], ['2', 'In 2'], ['3', 'In 3'], ['4', 'In 4'], ['mis', 'A misura']].map(([x, t]) => `<button class="btn${DIV[k] === x ? ' on' : ''}" data-dv${k}="${x}">${t}</button>`).join('')}</div>
    ${DIV[k] === 'mis' ? `<label class="lbl" for="dv-m${k}">A che misura ${da} (mm; più tubi: 300 600)</label><input class="field" id="dv-m${k}" value="${esc(DIV['m' + k])}" placeholder="es. 265">` : ''}</section>`;
  const misura = DIV.u === 'mis' || DIV.v === 'mis';
  passoTubi('Scegli in quante parti, guarda l’anteprima e premi «Dividi»');
  $('#props').innerHTML = `<div class="t-pan"><h3>Dividi il lato</h3>
    <p class="t-cose">Montanti e traversi a filo del lato, con i quadri uguali. Dove si incrociano, uno passa intero e l’altro è tagliato in due.</p>
    <section class="sezione"><h4>Quale lato</h4>${DIV.info.facce.length > 1 ? `<div class="seg">${DIV.info.facce.map(x => `<button class="btn${x.key === DIV.faccia ? ' on' : ''}" data-dvf="${x.key}">${esc(x.label)}</button>`).join('')}</div>` : `<div class="riga"><span>${esc(f.label)}</span></div>`}</section>
    ${riga('u', nomeU, f.u, daU)}${riga('v', nomeV, f.v, daV)}
    ${misura ? `<section class="sezione"><h4>La misura arriva</h4><div class="seg">${[['centro', 'Al centro del tubo'], ['bordo', 'Al bordo del tubo']].map(([k, t]) => `<button class="btn${DIV.rif === k ? ' on' : ''}" data-dvr="${k}">${t}</button>`).join('')}</div></section>` : ''}
    <section class="sezione"><label class="lbl">Tubo<input class="field" id="dv-prof" list="dl-prof" value="${esc(DIV.prof)}"></label>
    <datalist id="dl-prof">${(profili || []).map(p => `<option value="${esc(p)}">`).join('')}</datalist>
    ${f.opposta ? `<label class="check"><input type="checkbox" id="dv-opp" ${DIV.opposta ? 'checked' : ''}> Uguale anche ${esc(f.opposta)}</label>` : ''}
    ${f.aperti ? `<label class="check"><input type="checkbox" id="dv-chiudi" ${DIV.chiudi ? 'checked' : ''}> ${esc(f.aperti)}</label>` : ''}</section>
    <div class="t-piede"><button class="btn" id="dv-no">Annulla</button><button class="btn primary" id="dv-ok">Dividi</button></div></div>`;
  const tieni = () => {
    DIV.opposta = !!$('#dv-opp')?.checked; DIV.chiudi = !!$('#dv-chiudi')?.checked; DIV.prof = $('#dv-prof').value.trim();
    if ($('#dv-mu')) DIV.mu = $('#dv-mu').value;
    if ($('#dv-mv')) DIV.mv = $('#dv-mv').value;
  };
  const rifai = fn => b => { b.onclick = () => { tieni(); fn(b); pannelloDividi(); }; };
  document.querySelectorAll('[data-dvf]').forEach(rifai(b => { DIV.faccia = b.dataset.dvf; DIV.opposta = !!DIV.info.facce.find(x => x.key === DIV.faccia)?.opposta && /sinistra|destra/.test(DIV.faccia); }));
  document.querySelectorAll('[data-dvu]').forEach(rifai(b => { DIV.u = b.dataset.dvu; }));
  document.querySelectorAll('[data-dvv]').forEach(rifai(b => { DIV.v = b.dataset.dvv; }));
  document.querySelectorAll('[data-dvr]').forEach(rifai(b => { DIV.rif = b.dataset.dvr; }));
  $('#dv-no').onclick = () => { anteprimaVia(); latoAcceso(null); passoTubi(null); const id = `${DIV.st}/${DIV.mid}`; DIV = null; select(id); };
  const vai = () => {
    const args = dividiArgomenti();
    inCoda(async () => {
      const r = await call('dividi', ...args);
      if (await apply(r, r.message)) { anteprimaVia(); latoAcceso(null); passoTubi(null); DIV = null; await select(r.select); }
    });
  };
  $('#dv-ok').onclick = vai;
  document.querySelectorAll('#props input.field').forEach(i => { i.onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  anteprimaPannello('dividi', dividiArgomenti);
  const campo = $('#dv-mu') || $('#dv-mv');
  if (campo) campo.focus();
}

// PIEDI e TAPPI (03/11): «sotto le gambe una piastra 80×80 sp. 6 con 4 fori, o il piedino regolabile; sulle teste
// libere il tappo». Un pannello, una scelta, su tutte le gambe (o teste) in un colpo, con l'anteprima in azzurro
let PIEDI = null;
async function pannelloPiedi(st, cosa, testa = '') {
  const r = await chiamaMuto('piedi_info', st);
  if (!r.ok) { toast(r.message, 'err'); return; }
  const p = r.piedi || r.proposta, t = r.tappi;
  PIEDI = { st, cosa, testa, info: r, tipo: r.piedi ? (r.piedi.tipo || 'piastra') : 'piastra', fori: String(p.fori ?? 4),
    misura: p.misura || 'M10', tappo: t ? (t.tipo || 'plastica') : 'plastica', v: { ...r.proposta, ...(r.piedi || {}), sp_t: t?.sp ?? 3 } };
  disegnaPiedi();
}
function piediArgomenti() {
  const P = PIEDI, val = id => ($(id)?.value || '').trim().replace(',', '.');
  if (P.cosa === 'tappi') return [P.st, P.tappo === 'lamierino' ? { tipo: 'lamierino', sp: val('#pd-spt') } : { tipo: 'plastica' }];
  if (P.tipo === 'piedino') return [P.st, { tipo: 'piedino', misura: P.misura }];
  return [P.st, { tipo: 'piastra', lato: val('#pd-lato'), sp: val('#pd-sp'), fori: +P.fori, foro: val('#pd-foro'), dal_bordo: val('#pd-bordo') }];
}
function disegnaPiedi() {
  const P = PIEDI, r = P.info, v = P.v;
  const seg = (k, scelte) => `<div class="seg">${scelte.map(([x, t]) => `<button class="btn${P[k] === x ? ' on' : ''}" data-pd-${k}="${x}">${t}</button>`).join('')}</div>`;
  const campo = (id, l, val) => `<label class="lbl">${l}<span class="campo-unita"><input class="field" id="${id}" value="${esc(String(val ?? '').replace('.', ','))}"><i>mm</i></span></label>`;
  let h = `<div class="t-pan">${P.testa}`;
  if (P.cosa === 'piedi') {
    h += `${P.testa ? '<h4 class="t-titoletto">Piedi</h4>' : '<h3>Piedi sotto le gambe</h3>'}
      <p class="t-cose">Su tutte le ${r.gambe} gambe a terra. In azzurro come vengono.</p>
      <section class="sezione">${seg('tipo', [['piastra', 'Piastra coi fori'], ['piedino', 'Piedino regolabile']])}
      ${P.tipo === 'piastra' ? `<div class="t-campi">${campo('pd-lato', 'Lato', v.lato)}${campo('pd-sp', 'Spessore', v.sp)}</div></section>
        <section class="sezione"><h4>Fori</h4>${seg('fori', [['0', 'Senza'], ['2', '2 in diagonale'], ['4', '4 negli angoli']])}
        ${P.fori !== '0' ? `<div class="t-campi">${campo('pd-foro', 'Ø fori', v.foro)}${campo('pd-bordo', 'Dal bordo', v.dal_bordo)}</div>` : ''}
        <p class="hint">La piastra va sotto la gamba, centrata: l’altezza fuori tutto cresce dello spessore.</p></section>`
      : `</section><section class="sezione"><h4>Vite</h4>${seg('misura', r.piedini.map(x => [x, x]))}
        <p class="hint">Sotto ogni gamba un lamierino sp. 5 con la madrevite, e il piedino (da comprare: va in distinta).</p></section>`}
      <div class="t-piede">${r.piedi ? '<button class="btn danger" id="pd-via">Togli i piedi</button>' : ''}<button class="btn" id="pd-no">Annulla</button><button class="btn primary" id="pd-ok">${r.piedi ? 'Cambia i piedi' : 'Metti i piedi'}</button></div>`;
  } else {
    h += `${P.testa ? '<h4 class="t-titoletto">Tappi</h4>' : '<h3>Tappi sulle teste dei tubi</h3>'}
      <p class="t-cose">${r.teste ? `Su tutte le ${r.teste} teste aperte dei tubi (tagliate dritte, che non battono contro niente).` : 'Non ci sono teste di tubo aperte.'}</p>
      <section class="sezione">${seg('tappo', [['plastica', 'Tappo in plastica'], ['lamierino', 'Lamierino saldato']])}
      ${P.tappo === 'lamierino' ? `<div class="t-campi">${campo('pd-spt', 'Spessore', v.sp_t)}</div>` : '<p class="hint">Da comprare: va in distinta con la misura del tubo.</p>'}</section>
      <div class="t-piede">${r.tappi ? '<button class="btn danger" id="pd-via">Togli i tappi</button>' : ''}<button class="btn" id="pd-no">Annulla</button><button class="btn primary" id="pd-ok">${r.tappi ? 'Cambia i tappi' : 'Metti i tappi'}</button></div>`;
  }
  h += '</div>';
  $('#props').innerHTML = h;
  const tieni = () => { for (const [id, k] of [['#pd-lato', 'lato'], ['#pd-sp', 'sp'], ['#pd-foro', 'foro'], ['#pd-bordo', 'dal_bordo'], ['#pd-spt', 'sp_t']]) if ($(id)) v[k] = $(id).value; };
  for (const k of ['tipo', 'fori', 'misura', 'tappo']) document.querySelectorAll(`[data-pd-${k}]`).forEach(b => {
    b.onclick = () => { tieni(); P[k] = b.getAttribute(`data-pd-${k}`); disegnaPiedi(); };
  });
  const metodo = P.cosa === 'piedi' ? 'set_piedi' : 'set_tappi';
  const fine = async r2 => { if (await apply(r2, r2.message)) { anteprimaVia(); PIEDI = null; await select('struct=' + P.st); } };
  $('#pd-ok').onclick = () => inCoda(async () => fine(await call(metodo, ...piediArgomenti())));
  $('#pd-no').onclick = () => { anteprimaVia(); PIEDI = null; clearSelection(); };
  if ($('#pd-via')) $('#pd-via').onclick = () => inCoda(async () => fine(await call(metodo, P.st, null)));
  document.querySelectorAll('#props input.field').forEach(i => { i.onkeydown = ev => { if (ev.key === 'Enter') $('#pd-ok').click(); }; });
  anteprimaPannello(metodo, piediArgomenti);
}

// una sagoma nuova nella struttura: si sceglie da dove la si guarda, poi si disegna
function sagomaNuova() {
  modal(`<h3>Disegna la sagoma</h3><p class="hint">Ogni linea diventa un tubo. Poi la puoi ripetere dietro e collegare.</p>
    <div class="form"><label class="tutta-riga">Da dove la guardi mentre la disegni<select class="field" id="sg-p">
    <option value="XZ">Di fronte: fianchi, portali, cancelli</option><option value="YZ">Di fianco</option><option value="XY">Dall’alto: basamenti, telai a terra</option></select></label></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Disegna la sagoma</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const piano = $('#sg-p').value;
      close();
      inCoda(async () => { const r = await call('sagoma_nuova', piano); if (await apply(r)) await enterSketch(r.sketch); });
    };
  }, { stretta: true });
}
function faiTubiDialog() {
  const sid = SK.sid;
  // «dietro» dipende da come guardi la sagoma: di fronte → dietro, dall'alto → sopra, di fianco → di lato
  const z = SK.v?.z_dir || [0, -1, 0];
  const [dove, misura] = Math.abs(z[2]) > 0.9 ? ['sopra', 'Altezza'] : Math.abs(z[0]) > 0.9 ? ['di fianco', 'Larghezza'] : ['dietro', 'Profondità'];
  const tubo = esc(ultimaAsta.profile || '40x40x3');
  modal(`<h3>Fai i tubi</h3>
    <p class="hint">Ogni linea della sagoma diventa un tubo. Misure fuori tutto. In azzurro nel disegno vedi cosa viene fuori.</p>
    <div class="ft-form">
      <label class="ft-riga"><span>Tubo della sagoma</span><input class="field" id="ft-p" list="dl-prof" value="${tubo}"></label>
      <label class="ft-check"><input type="checkbox" id="ft-r" checked> Fai anche il lato ${dove}, uguale</label>
      <div class="ft-dentro" id="ft-rr">
        <label class="ft-riga"><span>${misura} fuori tutto</span><span class="ft-mm"><input class="field" id="ft-d" value="1000"><i>mm</i></span></label>
        <label class="ft-check"><input type="checkbox" id="ft-c" checked> Traversi tra i due lati, in ogni angolo</label>
        <label class="ft-riga" id="ft-cr"><span>Tubo dei traversi</span><input class="field" id="ft-cp" list="dl-prof" value="${tubo}"></label>
      </div>
    </div>
    <datalist id="dl-prof">${(profili || []).map(p => `<option value="${esc(p)}">`).join('')}</datalist>
    <div class="ant-stato" id="ft-ant"></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fai i tubi</button></div>`, close => {
    $('#modal').classList.add('laterale');
    const valori = () => ({ profile: $('#ft-p').value.trim(), ripeti: $('#ft-r').checked ? 1 : '', distanza: $('#ft-d').value.trim(),
      collega: $('#ft-r').checked && $('#ft-c').checked ? 1 : '', collega_profile: $('#ft-cp').value.trim() });
    const aggiorna = () => {
      $('#ft-rr').hidden = !$('#ft-r').checked;
      $('#ft-cr').hidden = !$('#ft-c').checked;
      anteprima('fai_tubi', () => [sid, valori()], $('#ft-ant'), { vista: 'iso' });
    };
    $('#modal-box').querySelectorAll('input').forEach(i => { i.oninput = aggiorna; i.onchange = aggiorna; });
    aggiorna();
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const v = valori();
      close();
      inCoda(async () => { const r = await call('fai_tubi', sid, v); if (await apply(r, r.message)) exitSketch(); });
    };
  });
}

// --------------------------------------------------------------- viste
let anim = null;
// 30/10 (porta ugelli): un pezzo aperto dall'assieme si guarda girato come nell'assieme, con l'alto dell'assieme e dal
// punto da cui lo guardavi; tornando all'assieme, lo stesso al contrario. Il pezzo dentro non cambia: è solo la vista.
const Z_SU = new THREE.Vector3(0, 0, 1);
let vistaDaRiprendere = null;                   // la direzione della vista nel mondo da cui si arriva
function rotContesto() {
  const R = S?.mode !== 'assembly' && S?.contesto_R;
  return R ? new THREE.Matrix3().set(...R.flat()) : null;
}
const nelPezzo = v => { const R = rotContesto(); return R ? v.clone().applyMatrix3(R.transpose()).normalize() : v.clone(); };
const nelMondo = v => { const R = rotContesto(); return R ? v.clone().applyMatrix3(R).normalize() : v.clone(); };
function altoVista() { return nelPezzo(Z_SU); }
function vistaIso() { return nelPezzo(VISTE.view_iso.clone().normalize()); }
function dirCamera() { return camera.position.clone().sub(controls.target).normalize(); }
function vistaIniziale() {
  const v = vistaDaRiprendere;
  vistaDaRiprendere = null;
  return v ? nelPezzo(v) : vistaIso();
}
function apriPezzoAssieme(id) {
  clearSelection(); primaVolta = true;
  vistaDaRiprendere = dirCamera();
  inCoda(async () => { const r = await call('asm_open_part', id); if (!r.ok) vistaDaRiprendere = null; await apply(r); });
}
function tornaAllAssieme() {
  inCoda(async () => {
    primaVolta = true; clearSelection();
    vistaDaRiprendere = nelMondo(dirCamera());
    const r = await call('asm_back');
    if (!r.ok) vistaDaRiprendere = null;
    await apply(r);
  });
}
function goTo(dir, keepDir = false) {
  if (!objs.size) return;
  fitBox(new THREE.Box3().setFromObject(model), dir, keepDir);
}
// 03/11 (collaudo tubi): la parte della vista che si vede davvero. Il pannello di destra (e la finestra di lato) stanno
// SOPRA la vista e in basso c'è la barretta Inquadra/Quote: Inquadra e il centraggio usano solo il rettangolo libero,
// altrimenti il modello finisce mezzo sotto il pannello. In pixel della vista: {l, r, t, b}
function areaLibera() {
  const vr = canvas.getBoundingClientRect();
  const A = { l: 0, r: vr.width, t: 0, b: vr.height };
  const sopra = [];
  if (!document.body.classList.contains('senza-destra')) sopra.push($('#right'));
  // chiuso, il pannello si riapre al primo clic su un pezzo o un angolo: nel 3D il suo posto si tiene libero lo stesso,
  // così il modello non ci finisce sotto e la vista non deve saltare quando si apre
  else if (!SK) A.r = Math.min(A.r, vr.width - 320);
  sopra.push(document.querySelector('#modal.laterale .modal-box'));
  for (const el of sopra) {
    if (!el || !el.offsetWidth) continue;
    const r = el.getBoundingClientRect();
    if (r.left > vr.left + vr.width / 2 && r.left < vr.right) A.r = Math.min(A.r, r.left - vr.left - 10);
  }
  const nb = $('#navbar');
  if (nb?.offsetHeight) { const r = nb.getBoundingClientRect(); if (r.top > vr.top + vr.height / 2) A.b = Math.min(A.b, r.top - vr.top - 6); }
  if (A.r - A.l < 200) { A.l = 0; A.r = vr.width; }            // finestra minuscola: meglio tutta la vista
  if (A.b - A.t < 150) { A.t = 0; A.b = vr.height; }
  return A;
}
// lo spostamento del disegno messo dall'ultimo Inquadra (senza finestre aperte): chiusa un'anteprima si torna a questo
let spostaBase = null;
function applicaSposta(s) {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (s && (Math.abs(s.x) > 0.5 || Math.abs(s.y) > 0.5)) camera.setViewOffset(w, h, s.x, s.y, w, h);
  else if (camera.view?.enabled) camera.clearViewOffset();
  ridisegna();
}
// il punto (nel mondo) cade nella parte libera della vista, con un margine per le frecce intorno? Se la vista sta ancora
// andando verso un'inquadratura nuova, si guarda dove arriverà
function dentroVista(p, margine = 0) {
  const pos = camera.position.clone(), tg = controls.target.clone();
  if (anim) { camera.position.copy(anim.to.pos); camera.lookAt(anim.to.target); camera.updateMatrixWorld(); }
  const q = p.clone().project(camera);
  if (anim) { camera.position.copy(pos); camera.lookAt(tg); camera.updateMatrixWorld(); }
  const A = areaLibera(), x = (q.x + 1) / 2 * canvas.clientWidth, y = (1 - q.y) / 2 * canvas.clientHeight;
  return q.z < 1 && x > A.l + margine && x < A.r - margine && y > A.t + margine && y < A.b - margine;
}
function fitBox(box, dir, keepDir = false, subito = false, tutto3d = false) {
  const c = box.getCenter(new THREE.Vector3());
  const rad = box.getBoundingSphere(new THREE.Sphere()).radius || 100;
  const fov = THREE.MathUtils.degToRad(camera.fov);
  let dist = rad / Math.sin(Math.min(fov, fov * camera.aspect) / 2) * 1.08;
  if (!SK || tutto3d) {
    // solo la parte libera della vista: il centro del modello va nel suo centro
    const A = areaLibera(), W = canvas.clientWidth || 1, H = canvas.clientHeight || 1;
    const tv = Math.tan(fov / 2) * (A.b - A.t) / H, to = Math.tan(fov / 2) * camera.aspect * (A.r - A.l) / W;
    dist = rad / Math.sin(Math.atan(Math.min(tv, to))) * 1.08;
    const sposta = { x: W / 2 - (A.l + A.r) / 2, y: H / 2 - (A.t + A.b) / 2 };
    applicaSposta(sposta);
    if (!document.querySelector('#modal.laterale .modal-box')?.offsetWidth) spostaBase = sposta;
  } else { applicaSposta(null); spostaBase = null; }
  if (SK && !tutto3d) {
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
  if (Math.abs(d.dot(camera.up)) > 0.9999) {     // guardando lungo l'alto la vista non sa dov'è il nord: un filo di lato
    const lato = Math.abs(camera.up.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
    d.addScaledVector(lato.cross(camera.up).cross(camera.up).normalize(), 0.0001).normalize();
  }
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
    const m = matOf(o), pieno = opacitaPiena(m);       // il vetro resta trasparente anche fuori dal disegno
    m.transparent = fantasma < 1 || pieno < 1; m.opacity = fantasma * pieno; m.depthWrite = fantasma >= 1 && pieno >= 1;
  }
  dimLines.visible = SK ? true : !piatto;
  edgeGroup.visible = !SK && !piatto;
  dimsBox.style.display = !SK && piatto ? 'none' : '';
  nodesBox.style.display = SK || piatto ? 'none' : '';
  $('#b-unfold').hidden = !S?.sheet?.data;
  $('#b-unfold').classList.toggle('on', flatView);
  $('#b-unfold').textContent = flatView ? 'Ripiega' : 'Spiega';
  $('#flat-bar').hidden = !(flatView && !SK);
  // 04/11 sera: sullo sviluppo «Spiega» della barra è acceso (col colore della modalità), come gli altri comandi in uso
  document.querySelectorAll('#ribbon .rb[data-cmd="unfold"]').forEach(b => b.classList.toggle('on', !!flatView && !SK));
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
    goTo(vistaIso());
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
  // le quote ripetute (le copie di una serie) una volta sola: «10 ×300»
  // notte 03/11: in una struttura (cancello, scaffale) le quote calcolate dal modello (la posizione di ogni sbarra,
  // «tf+2*g+…») facevano un mucchio di numeri uno sull'altro: nel 3D restano solo quelle con un nome (L, H, P…)
  const formula = d => !SK && !d.param && typeof d.expr === 'string' && /[a-z]/i.test(d.expr) && S.cutlist?.rows?.length && !S.sheet;
  const lista = S.dimensions.filter(d => (SK ? d.sketch === SK.sid : !d.local) && !d.in_gruppo && !formula(d));
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
    // 03/11: il passo della Serie si chiama «passo» (non «px1»); le misure con nome (W, P…) restano col loro nome
    const sigla = !d.param ? '' : /^p[xy]\d+$/.test(d.param) ? 'passo' : /^off\d+$/.test(d.param) ? 'distanza' : d.param;
    el.innerHTML = (d.param ? `<span class="p">${esc(sigla)}</span>` : '') + esc(d.label) + (d.gruppo ? `<span class="n">×${d.gruppo.length}</span>` : '');
    el.title = d.driven ? 'Quota di riferimento: la misura la decide il pezzo (si aggiorna da sola)'
      : d.param ? `Quota legata a «${d.param_label || d.param}»: clicca per cambiarla`
      : d.gruppo ? `La stessa quota su ${d.gruppo.length} elementi uguali: cambiandola si cambiano tutti` : 'Clicca per cambiare la quota';
    el.addEventListener('click', ev => {
      ev.stopPropagation();
      if (d.driven) { toast(el.title); return; }
      if (SK && !['select', 'dim'].includes(SK.tool)) setTool('select');    // cambi la quota: il comando si chiude
      editDim(el, d);
    });
    // tasto destro: la quota si toglie (la misura torna libera, il disegno resta dov'è)
    el.title += ' · tasto destro: togli la quota';
    el.addEventListener('contextmenu', ev => {
      ev.preventDefault(); ev.stopPropagation();
      inCoda(async () => { const r = await call('sketch_delete_dimension', d.sketch, d.dim); if (await apply(r)) toast('Quota tolta: quella misura è libera.', 'ok', { label: 'Annulla', fn: () => runCmd('undo') }); });
    });
    dimsBox.appendChild(el);
    // il diametro va sul bordo del cerchio, non al centro: se no la scritta copre il foro
    dimEls.push({ el, d, quota: true, a: pa.clone(), b: pb.clone(), at: d.type === 'diameter' || d.type === 'radius' ? pb.clone() : pa.clone().add(pb).multiplyScalar(0.5) });
  }
  if (!SK) quoteIngombro();
  placeDims();
  ridisegna();
}
// l'ingombro totale del pezzo (o dell'assieme): tre quote sugli spigoli della scatola che lo contiene, lungo X, Y e Z
function quoteIngombro() {
  const box = new THREE.Box3();
  model.updateMatrixWorld(true);
  // 04/11 notte (attriti, D 15): un pezzo aperto dall'assieme ha attorno gli altri pezzi, trasparenti: l'ingombro è
  // quello del pezzo (la staffa 100 × 80), non dell'assieme (88 × 300 × 200)
  model.traverse(o => { if (o.isMesh && o.visible && o.geometry && o.material !== CTX_MAT) box.expandByObject(o); });
  if (box.isEmpty()) return;
  const mn = box.min, mx = box.max, sz = box.getSize(new THREE.Vector3());
  const off = Math.max(30, box.getBoundingSphere(new THREE.Sphere()).radius * 0.16);
  const lati = [
    // misura, da, a, verso cui si sposta la quota
    [sz.x, new THREE.Vector3(mn.x, mn.y, mn.z), new THREE.Vector3(mx.x, mn.y, mn.z), new THREE.Vector3(0, -1, 0), 'larghezza (X)'],
    [sz.y, new THREE.Vector3(mx.x, mn.y, mn.z), new THREE.Vector3(mx.x, mx.y, mn.z), new THREE.Vector3(1, 0, 0), 'profondità (Y)'],
    [sz.z, new THREE.Vector3(mn.x, mn.y, mn.z), new THREE.Vector3(mn.x, mn.y, mx.z), new THREE.Vector3(-1, -1, 0).normalize(), 'altezza (Z)'],
  ];
  // un ingombro uguale a una quota del pezzo già a video (W 500 e 500) è la stessa misura due volte: resta quella che si cambia
  const assi = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
  const doppia = (k, mis) => (S?.dimensions || []).some(d => {
    if (d.local || d.type === 'diameter' || d.type === 'radius') return false;
    const v = new THREE.Vector3(...d.b).sub(new THREE.Vector3(...d.a));
    return Math.abs(v.length() - mis) < 0.05 && Math.abs(Math.abs(v.normalize().dot(assi[k])) - 1) < 1e-3;
  });
  for (const [k, [mis, a, b, dir, nome]] of lati.entries()) {
    if (mis < 0.05 || doppia(k, mis)) continue;
    const pa = a.clone().addScaledVector(dir, off), pb = b.clone().addScaledVector(dir, off);
    const g = new THREE.BufferGeometry().setFromPoints([a, a.clone().addScaledVector(dir, off * 1.1), b, b.clone().addScaledVector(dir, off * 1.1), pa, pb]);
    dimLines.add(new THREE.LineSegments(g, ING_MAT).computeLineDistances());
    const el = document.createElement('div');
    el.className = 'dim ing';
    el.textContent = num(Math.round(mis * 10) / 10);
    el.title = `Ingombro totale, ${nome}: ${num(Math.round(mis * 10) / 10)} mm`;
    el.addEventListener('click', ev => { ev.stopPropagation(); toast(el.title); });
    dimsBox.appendChild(el);
    dimEls.push({ el, d: null, quota: true, a: pa.clone(), b: pb.clone(), at: pa.clone().add(pb).multiplyScalar(0.5) });
  }
}
// 24/10: le etichette si spostano con «translate» (lo fa la scheda video, senza rifare l'impaginazione della pagina)
// e solo se si sono mosse; con tante quote (una serie di 300 fori: 600 etichette) mentre giri la vista si nascondono
// e tornano appena ti fermi
let inMoto = false;
controls.addEventListener('start', () => { inMoto = true; });
controls.addEventListener('end', () => { inMoto = false; ridisegna(); });
const _pv = new THREE.Vector3();
function placeDims() {
  const w = view.clientWidth, h = view.clientHeight;
  const tante = dimEls.length + nodeEls.length + (misEls?.length || 0) > 150;
  const via = inMoto && tante;
  // i contenitori presi così: placeDims può girare prima che il resto del file abbia dichiarato nodesBox e misBox
  for (const box of [dimsBox, $('#nodes'), $('#mis-box')]) if (box) box.style.visibility = via ? 'hidden' : '';
  if (via) return;
  for (const o of [...dimEls, ...nodeEls, ...(misEls || []), ...(interfEls || [])]) {
    const p = _pv.copy(o.at).project(camera), el = o.el;
    const fuori = p.z > 1 || Math.abs(p.x) > 1.1 || Math.abs(p.y) > 1.1;
    if (o.fuori !== fuori) { el.style.display = fuori ? 'none' : ''; o.fuori = fuori; }
    if (fuori) continue;
    const x = Math.round((p.x + 1) / 2 * w * 2) / 2, y = Math.round((1 - p.y) / 2 * h * 2) / 2;
    if (o.x !== x || o.y !== y) {
      if (o.x === undefined) { el.style.left = '0px'; el.style.top = '0px'; }
      if (!o.quota) el.style.translate = `${x}px ${y}px`;      // le quote le mette sbrogliaQuote, qui sotto
      o.x = x; o.y = y;
    }
  }
  sbrogliaQuote(w, h);
  // le frecce: a 70 px dal pallino, nella direzione in cui va il tubo vista sullo schermo
  for (const { el, at, v } of frecceEls) {
    const p = at.clone().project(camera), q = at.clone().add(v).project(camera);
    let dx = (q.x - p.x) * w, dy = -(q.y - p.y) * h;
    const l = Math.hypot(dx, dy);
    if (l < 1e-6) { dx = 0; dy = 0; } else { dx *= 70 / l; dy *= 70 / l; }
    el.style.display = p.z > 1 ? 'none' : '';
    el.style.left = ((p.x + 1) / 2 * w + dx) + 'px';
    el.style.top = ((1 - p.y) / 2 * h + dy) + 'px';
    el.style.setProperty('--ang', Math.atan2(dy, dx) + 'rad');      // la punta arancio guarda dove va il tubo
  }
}
// 04/11 (ritocchi): le etichette delle quote non si coprono. Due quote sulla stessa linea (180 e 200 di una catena)
// si scostano lungo la loro linea; due quote uguali nello stesso punto (i fori simmetrici: 20 e 20) ne mostrano una;
// una quota lunga 0 (due punti uniti) non dice niente a chi guarda e non si mostra
const _qa = new THREE.Vector3(), _qb = new THREE.Vector3();
function sbrogliaQuote(w, h) {
  const fatti = [];
  // quanto è grande ogni etichetta e dove sta rispetto al suo punto (le diametrali stanno accanto al cerchio):
  // misurato una volta sola, tutte insieme (una sola impaginazione)
  const nuove = dimEls.filter(o => o.quota && !o.fuori && o.x !== undefined && o.w === undefined);
  if (nuove.length) {
    for (const o of nuove) { o.el.style.translate = `${o.x}px ${o.y}px`; o.tx = o.x; o.ty = o.y; }
    const vr = dimsBox.getBoundingClientRect();
    for (const o of nuove) {
      const r = o.el.getBoundingClientRect();
      o.ox = r.left - vr.left - o.x; o.oy = r.top - vr.top - o.y; o.w = r.width; o.h = r.height;
      o.dia = o.el.classList.contains('dia'); o.zero = !o.dia && o.a.distanceTo(o.b) < 1e-6;
    }
  }
  const scatola = (o, x, y) => [x + o.ox, y + o.oy, x + o.ox + o.w, y + o.oy + o.h];
  const M = 8;                       // lo spazio minimo tra due etichette: «180  200», non «180·200»
  const tocca = (r, q) => r[0] < q[2] + M && q[0] < r[2] + M && r[1] < q[3] + 2 && q[1] < r[3] + 2;
  for (const o of dimEls) {
    if (!o.quota || o.fuori || o.x === undefined || o.w === undefined) continue;
    const el = o.el;
    if (el.classList.contains('edit')) { el.style.translate = `${o.x}px ${o.y}px`; o.tx = o.x; o.ty = o.y; continue; }
    let nascondi = o.zero, x = o.x, y = o.y;
    // la direzione della linea di quota sullo schermo: lì si scosta l'etichetta (le diametrali salgono)
    let dx = 0, dy = -1;
    if (!o.dia) {
      _qa.copy(o.a).project(camera); _qb.copy(o.b).project(camera);
      const vx = (_qb.x - _qa.x) * w / 2, vy = -(_qb.y - _qa.y) * h / 2, l = Math.hypot(vx, vy);
      if (l > 1e-6) { dx = vx / l; dy = vy / l; }
    }
    const orizz = Math.abs(dx) >= Math.abs(dy);
    for (let k = 0; !nascondi && k < 8; k++) {
      const r = scatola(o, x, y), q = fatti.find(f => tocca(r, f.r));
      if (!q) break;
      if (Math.abs(q.o.x - o.x) < 1.5 && Math.abs(q.o.y - o.y) < 1.5 && q.o.el.textContent === el.textContent) { nascondi = true; break; }
      // di quanto spostarsi per uscire dall'altra, lungo la linea (in avanti se si sta già più avanti)
      if (orizz) { const avanti = (r[0] + r[2]) >= (q.r[0] + q.r[2]); const t = avanti ? q.r[2] - r[0] + M + 1 : -(r[2] - q.r[0] + M + 1); x += t; y += dy / (dx || 1) * t * (dx ? 1 : 0); }
      else { const avanti = (r[1] + r[3]) >= (q.r[1] + q.r[3]); const t = avanti ? q.r[3] - r[1] + 3 : -(r[3] - q.r[1] + 3); y += t; x += dx / (dy || 1) * t; }
    }
    if (o.via !== nascondi) { el.style.visibility = nascondi ? 'hidden' : ''; o.via = nascondi; }
    if (nascondi) continue;
    if (o.tx !== x || o.ty !== y) { el.style.translate = `${x}px ${y}px`; o.tx = x; o.ty = y; }
    fatti.push({ o, r: scatola(o, x, y) });
  }
}
function editDim(el, d) {
  if (el.classList.contains('edit')) return;
  el.classList.add('edit');
  el.innerHTML = (d.param ? `<span class="p">${esc(d.param_label || d.param)} =</span>` : '') + '<input>';
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
    el.title = n.nome || 'Angolo';
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
  const lh = $('#link-hint');
  if (linkFrom && !lh.querySelector('.t-passo')) lh.innerHTML = '<span class="t-passo">Clicca l’angolo dove arriva il tubo nuovo</span><span class="g-tasto"><kbd>Esc</kbd> annulla</span>';
  lh.hidden = !linkFrom;
  buildFrecce();
}
// Le frecce intorno all'angolo scelto (22/10): Su, Giù, Avanti, Dietro, Destra, Sinistra. Clic = tubo nuovo da lì,
// con lunghezza e tubo scritti nel pannello. Al posto di X+ Y- Z+.
const FRECCE = [['su', 'Su', [0, 0, 1]], ['giu', 'Giù', [0, 0, -1]], ['avanti', 'Avanti', [0, -1, 0]],
  ['dietro', 'Dietro', [0, 1, 0]], ['destra', 'Destra', [1, 0, 0]], ['sinistra', 'Sinistra', [-1, 0, 0]]];
let frecceEls = [];
function buildFrecce() {
  for (const { el } of frecceEls) el.remove();
  frecceEls = [];
  const n = sel && nodes.find(x => x.id === sel.id);
  if (!n || SK || linkFrom) return;            // mentre scegli l'angolo da unire le frecce non servono
  for (const [dir, testo, v] of FRECCE) {
    const el = document.createElement('button');
    el.className = 'freccia-3d';
    el.innerHTML = `<svg class="t-punta" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 7H11.5M8 3.5L11.5 7 8 10.5"/></svg>${testo}`;
    el.title = `Tubo nuovo verso ${testo.toLowerCase()}`;
    el.addEventListener('click', ev => { ev.stopPropagation(); tuboDaFreccia(n, dir); });
    nodesBox.appendChild(el);
    frecceEls.push({ el, at: new THREE.Vector3(...n.xyz), v: new THREE.Vector3(...v).multiplyScalar(10) });
  }
  placeDims();
  frecceLibere();
}
// 04/11 (ritocchi): le frecce non finiscono sotto le barre in basso (Inquadra/Quote/Tema, la riga «prossimo passo»,
// col cassetto aperto la vista è bassa): se toccano, la vista sale quel tanto che basta, con lo stesso movimento di Inquadra
const BARRE_BASSE = '#navbar, #trav-hint, #link-hint, #asm-passo, #prova-barra, #sk-foot';
function frecceLibere(prove = 0) {
  if (!frecceEls.length || SK) return;
  if (anim) { if (prove < 6) setTimeout(() => frecceLibere(prove + 1), 300); return; }
  const vr = view.getBoundingClientRect();
  let fondo = vr.bottom;
  for (const el of document.querySelectorAll(BARRE_BASSE)) {
    if (el.hidden || !el.offsetHeight) continue;
    const r = el.getBoundingClientRect();
    if (r.top > vr.top + vr.height / 2 && r.top < fondo && r.left < vr.right && r.right > vr.left) fondo = r.top;
  }
  let giu = -Infinity, su = Infinity;
  for (const { el } of frecceEls) {
    if (el.style.display === 'none') continue;
    const r = el.getBoundingClientRect();
    giu = Math.max(giu, r.bottom); su = Math.min(su, r.top);
  }
  if (giu === -Infinity) return;
  let dy = giu - (fondo - 8);                             // di quanto le frecce devono salire
  if (dy <= 0) return;
  dy = Math.min(dy, Math.max(0, su - (vr.top + 8)));     // senza farne uscire altre di sopra
  if (dy < 2) return;
  const at = frecceEls[0].at;
  const dietro = new THREE.Vector3().subVectors(at, camera.position).dot(camera.getWorldDirection(new THREE.Vector3()));
  const mmPerPx = 2 * Math.max(dietro, 1) * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) / vr.height;
  const sposta = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion).multiplyScalar(-dy * mmPerPx);
  const to = { pos: camera.position.clone().add(sposta), target: controls.target.clone().add(sposta) };
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { camera.position.copy(to.pos); controls.target.copy(to.target); controls.update(); ridisegna(); return; }
  anim = { t0: performance.now(), from: { pos: camera.position.clone(), target: controls.target.clone() }, to };
}
function tuboDaFreccia(n, dir) {
  ricordaTubo();
  inCoda(async () => {
    const r = await call('tubo_da_angolo', n.structure, n.key, dir, ultimaAsta.length, ultimaAsta.profile || null, ultimaAsta.nome || '');
    ultimaAsta.nome = '';
    if (!(await apply(r))) return;
    await select(r.node);                         // si continua dal capo del tubo nuovo
    // il capo del tubo è uscito dalla vista: si riquadra tutto, così le frecce si vedono
    // (03/11: conta solo la parte libera della vista, il pannello di destra ci sta sopra; margine per le frecce)
    const capo = nodes.find(x => x.id === r.node);
    if (capo && !dentroVista(new THREE.Vector3(...capo.xyz), 90)) { goTo(null, true); setTimeout(placeDims, 450); }
  });
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
    if (res && !res.cancelled && (res.soluzioni?.length || res.evidenzia)) mostraErrore(res);   // 28/10: dove e come uscirne
    else if (res && !res.cancelled) toast(res.message || 'Operazione non riuscita.', 'err');
    return false;
  }
  if (res.state) {
    S = res.state;
    renderPanels();
    if (S.scene_version !== sceneVersion && S.mode === 'assembly' && S.geo && S.geo === geoCaricata && S.poses) {
      interfPulisci();                              // le interferenze in rosso erano di prima che si muovesse
      spostaPezzi(S.poses);                         // si è mosso solo qualcosa: niente scena intera
      sceneVersion = S.scene_version;
      camera.up.copy(altoVista());
      if (vistaDaRiprendere) goTo(vistaIniziale());
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
  if (!SK) buildDims();                              // 03/11: l'ingombro (450 → 300) segue i pezzi spostati
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
  aggiornaSuolo();
  buildThreads(sc.threads);
  buildSvasatureKo(sc.svasature_ko);
  buildMarks(sc.marks);
  nodes = sc.nodes || [];
  bendEdges = sc.bend_edges || [];
  hoverEdge = null;
  modelRadius = new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere()).radius || 100;
  camera.up.copy(altoVista());
  if (primaVolta || (eraVuota && objs.size)) {
    goTo(vistaIniziale()); primaVolta = !objs.size && primaVolta; ribbonForProject();
    if (objs.size) appenaInquadrato = performance.now();
  }
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
    // cliccato mentre il pezzo si rifaceva: torna la stessa barretta, non il pannello completo
    if (e && sel.soloMini && MINI.ancora) MINI.dove = { p: MINI.ancora.clone(), t: performance.now() };
    if (e) selectEdge(e); else clearSelection();
  } else if (sel) {
    // 03/11: la faccia col nome di quando l'hai cliccata: il suo numero nel pezzo rifatto può essere un'altra faccia
    // (cliccando un altro lato mentre la piega si costruiva, il pannello finiva sulla «Scatola»)
    if ((sel.ids || [sel.id]).every(esiste)) await select(sel.id, sel.face, sel.ids, true, sel.nome);
    else clearSelection();
  }
}

let visPercorso = null;
// 28/10: la storia dei passi; un clic e il pezzo torna com'era lì (i passi dopo restano, in grigio, finché non cambi)
function renderStoria() {
  const st = S?.storia, box = document.getElementById('storia-panel');
  if (!box) return;
  box.hidden = !st || !st.passi.length;
  if (box.hidden) return;
  document.getElementById('storia-n').textContent = st.qui < st.passi.length ? `passo ${st.qui} di ${st.passi.length}` : `${st.passi.length} ${st.passi.length === 1 ? 'passo' : 'passi'}`;
  const voci = [['Com’era all’apertura', 0], ...st.passi.map((t, i) => [t, i + 1])];
  const el = document.getElementById('storia');
  el.innerHTML = voci.map(([t, pos]) => `<button data-pos="${pos}" class="${pos === st.qui ? 'qui' : pos > st.qui ? 'dopo' : ''}" title="${esc(t)}"><span>${esc(t)}</span></button>`).join('');
  el.querySelector('.qui')?.scrollIntoView({ block: 'nearest' });
  el.onclick = e => {
    const b = e.target.closest('[data-pos]');
    if (!b || +b.dataset.pos === st.qui) return;
    clearSelection();
    inCoda(async () => apply(await call('history_goto', +b.dataset.pos)));
  };
}
function renderPanels() {
  const assieme = S.mode === 'assembly';
  if ((assieme ? S.path || S.name : null) !== visPercorso) {      // un altro assieme: si vede tutto di nuovo
    visPercorso = assieme ? S.path || S.name : null;
    VIS.nascosti.clear(); VIS.trasparenti.clear(); VIS.solo = null;
  }
  document.body.classList.toggle('assembly', assieme);
  aggiornaModo();
  $('#b-back').hidden = !S.can_back;
  if (!assieme && ASM.tool) asmTool(null);
  if (!assieme && APP.el) appoggiaChiudi(false);     // uscito dall'assieme col pannello di Appoggia aperto
  renderTop(); renderTree(); renderParams(); renderBottom(); renderSheet(); aggiornaComandi(); renderStoria();
  aggiornaLayout();
  if (!sel && !SK) $('#props').innerHTML = '';
  passoAssieme();
}
// 04/11 notte (attriti, D 12): appena creato l'assieme i pezzi sono a fianco e non si sa cosa fare: una riga «prossimo
// passo» in basso, finché non c'è un accoppiamento (o la chiudi). Durante Appoggia & c. parla la loro barra
const ASM_PASSO_CHIUSO = new Set();
function passoAssieme() {
  let b = document.getElementById('asm-passo');
  const chi = S?.path || S?.name || '', ist = S?.instances || [];
  const mostra = S?.mode === 'assembly' && ist.length >= 2 && ist.some(i => !i.fixed) && !SK && !ASM.tool && !APP.el && !VAN.el
    && !JSON.stringify(S.tree || {}).includes('"kind":"mate"') && !ASM_PASSO_CHIUSO.has(chi);
  if (!mostra) { if (b) b.hidden = true; return; }
  if (!b) {
    b = document.createElement('div'); b.id = 'asm-passo';
    b.innerHTML = `<span class="t-passo">Metti i pezzi al loro posto:</span><button type="button" class="btn piccolo" id="asm-passo-ok"><img src="icons/appoggia.svg" alt="">Appoggia</button>`
      + `<button type="button" class="btn piccolo" id="asm-passo-vano"><img src="icons/vano.svg" alt="">Metti nel vano</button>`
      + `<span class="t-poi">poi clic sul pezzo e su dove va</span><button type="button" class="asm-passo-x" title="Chiudi" aria-label="Chiudi">×</button>`;
    $('#trav-hint').after(b);
    b.querySelector('#asm-passo-ok').onclick = () => asmTool('appoggia');
    b.querySelector('#asm-passo-vano').onclick = () => asmTool('vano');
    b.querySelector('.asm-passo-x').onclick = () => { ASM_PASSO_CHIUSO.add(S?.path || S?.name || ''); b.hidden = true; };
  }
  b.hidden = false;
}
// il pannello a destra si apre solo quando c'è qualcosa di selezionato (le proprietà); i comandi stanno nella barra in alto
function aggiornaLayout() {
  const chiuso = !sel || !!SK || !!sel.soloMini;
  if (document.body.classList.contains('senza-destra') === chiuso) return;
  document.body.classList.toggle('senza-destra', chiuso);          // sopra la vista: la vista non cambia misura
}

function renderTop() {
  const nome = esc(S.name || 'Senza nome');
  const bp = $('#b-prepara');
  const vuoto = !S.tree?.children?.length && !S.cutlist?.rows?.length && S.mode !== 'assembly';
  bp.hidden = vuoto;
  bp.textContent = S.mode === 'assembly' || (S.cutlist?.rows?.length && !S.sheet) ? 'Prepara per l’officina' : 'Prepara per il laser';
  // 03/11: in alto solo il nome (il percorso intero nel suggerimento); sul pezzo un clic e lo cambi
  const dn = $('#docname'), pezzo = S.mode !== 'assembly';
  if (!dn.querySelector('input')) {
    dn.innerHTML = `${S.dirty ? '<span class="dirty">● </span>' : ''}<span class="nome">${nome}</span>` +
      (S.path ? '' : ' <span class="doc-stato">— non salvato</span>');
    dn.classList.toggle('rinomina', pezzo);
    dn.title = (S.name || 'Senza nome') + (S.dirty ? ' (modificato)' : '') + '\n' + (S.path || 'Non ancora salvato') + (pezzo ? '\nClic: cambia il nome del pezzo' : '');
  }
  for (const [b, k, t] of [['#b-undo', 'undo', 'Annulla'], ['#b-redo', 'redo', 'Ripeti']]) {
    const l = S[k][0];
    $(b).disabled = !l;
    $(b).title = l ? `${t}: ${l} (Ctrl+${k === 'undo' ? 'Z' : 'Y'})` : (k === 'undo' ? 'Niente da annullare' : 'Niente da ripetere');
  }
}
// il nome del pezzo in alto: clic = campo, Invio salva il nome (vale per file, distinta, tavole e DXF), Esc lascia stare
function nomeInAlto() {
  const dn = $('#docname');
  if (!S || S.mode === 'assembly' || dn.querySelector('input')) return;
  dn.innerHTML = `<input class="field" id="doc-nome" value="${esc(S.name || '')}" aria-label="Nome del pezzo" spellcheck="false">`;
  const i = $('#doc-nome');
  i.focus(); i.select();
  let fatto = false;
  const fine = ok => {
    if (fatto) return;
    fatto = true;
    const v = i.value.trim();
    dn.innerHTML = '';
    renderTop();
    if (ok && v && v !== S.name) inCoda(async () => { await apply(await call('rinomina_pezzo', v)); renderTree(); });
  };
  i.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') fine(true); if (e.key === 'Escape') fine(false); };
  i.onblur = () => fine(true);
}
$('#docname').addEventListener('click', nomeInAlto);
// 03/11: il primo «Salva» di un pezzo nuovo chiede come si chiama (col nome che ha già, pronto da riscrivere);
// poi la finestra di Windows parte con quel nome
function salvaPezzo(conNome) {
  if (conNome || S.path || S.mode === 'assembly') {
    inCoda(async () => { if (await apply(await call('save', !!conNome), 'Salvato.')) fotoAnteprima(S.path); });
    return;
  }
  modal(`<h3>Salva il pezzo</h3>
    <div class="form"><label>Come si chiama il pezzo<input class="field" id="sv-nome" value="${esc(S.name || '')}" spellcheck="false"></label></div>
    <p class="hint">Il nome va nella distinta, nel cartiglio delle tavole e nel nome del DXF. Poi scegli la cartella.</p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Salva…</button></div>`, close => {
    const i = $('#sv-nome');
    i.focus(); i.select();
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const v = i.value.trim();
      if (!v) { i.focus(); return; }
      close();
      inCoda(async () => {
        if (v !== S.name) { const r = await call('rinomina_pezzo', v); if (!(await apply(r))) return; }
        if (await apply(await call('save', false), 'Salvato.')) fotoAnteprima(S.path);
      });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#m-ok').click(); if (ev.key === 'Escape') close(); };
  }, { stretta: true });
}

const ICONE = { project: '◆', part: '▣', sketch: '✎', extrude: '▤', hole: '◯', fillet: '◜', chamfer: '◿', sheet: '▱', flange: '⌐',
  structure: '⌗', group: '▾', members: '│' };
// 29/10, «l'albero pulito»: le voci con dentro il loro disegno (e i «Disegni non usati») si aprono con la freccina;
// gli sketch vuoti si vedono solo mentre ci lavori
const APERTI = new Set();
const chiaveNodo = n => `${n.kind}:${n.ref}`;
const contieneSketch = (n, sid) => (n.kind === 'sketch' && n.ref === sid) || n.children.some(c => contieneSketch(c, sid));
// l'etichetta di una voce dell'albero: se va a capo, non stacca il numero dalla sua unità né «= 6 mm» dal suo nome
const etichettaAlbero = t => esc(t).replace(/(\d) (mm|°|kg)/g, '$1&nbsp;$2').replace(/ = (\S+)/g, '&nbsp;=&nbsp;$1');
function renderTree() {
  if (document.activeElement?.classList?.contains('nome-albero')) return;      // mentre scrivi il nome di un pezzo
  const selIds = new Set(sel ? (sel.ids || [sel.id]) : []);
  const nodo = n => {
    if (n.vuoto && !(SK && contieneSketch(n, SK.sid))) return '';
    const ids = n.kind === 'members' ? n.ref : n.kind === 'structure' ? ['struct=' + n.ref]
      : n.kind === 'flange' ? ['flange=' + n.ref] : n.kind === 'sheet_edge_flange' ? ['pb=' + n.ref] : n.kind === 'sheet_miter' ? ['tt=' + n.ref]
      : n.kind === 'sketch' ? ['sketch=' + n.ref]
      : n.kind === 'instance' ? [n.ref] : n.kind === 'mate' ? ['mate=' + n.ref] : n.kind === 'assembly' ? ['assieme']
      : ['part', 'extrude', 'hole', 'fillet', 'chamfer', 'sheet'].includes(n.kind) ? ['body'] : null;
    const cls = ['node', n.kind === 'project' ? 'root' : '', n.kind === 'group' ? 'group' : '', n.status === 'disattivata' ? 'spenta' : '',
      ids && ids.length ? 'clickable' : '', n.status === 'errore' ? 'err' : '',
      ids && ids.length && ids.every(i => selIds.has(i)) && n.kind !== 'structure' && !(n.kind !== 'part' && ids[0] === 'body') ? 'sel' : ''];
    // 04/11: «fisso» (il pezzo fermo dell'assieme) è un'informazione, non un allarme: grigio col lucchetto
    // 04/11 notte (occhio): solo il lucchetto, piccolo a destra; «fisso» scritto passando col mouse (il nome resta su una riga)
    const st = n.status === 'fisso' ? `<span class="st fisso" title="Fisso: il pezzo fermo, gli altri si appoggiano a lui" aria-label="fisso"><img src="icons/c_fix.svg" alt="fisso"></span>`
      : n.status && n.status !== 'errore' ? `<span class="st">${esc(n.status)}</span>` : '';
    const conta = S.mode === 'assembly' && n.kind === 'group' && n.children.length ? `<span class="n-conta">${n.children.length}</span>` : '';
    const data = (ids && ids.length ? ` data-ids="${esc(ids.join(','))}"` : '') + (n.ref && typeof n.ref === 'string' ? ` data-kind="${esc(n.kind)}" data-ref="${esc(n.ref)}"` : '');
    let figli = n.children.length ? `<ul>${n.children.map(nodo).join('')}</ul>` : '';
    let freccia = '';
    if (n.chiuso && figli) {
      const aperto = APERTI.has(chiaveNodo(n)) || (SK && contieneSketch(n, SK.sid));
      freccia = `<button class="freccia" data-apri="${esc(chiaveNodo(n))}" title="${aperto ? 'Chiudi' : 'Apri: il suo disegno'}">${aperto ? '▾' : '▸'}</button>`;
      if (!aperto) figli = '';
      cls.push('apribile');
    }
    let occhio = '';
    if (n.kind === 'instance') {                     // 28/10: l'occhio per nascondere, e come si vede adesso
      const vede = VIS.solo ? VIS.solo.has(n.ref) : !VIS.nascosti.has(n.ref);
      if (!vede) cls.push('nascosto');
      if (VIS.trasparenti.has(n.ref)) cls.push('trasp');
      occhio = `<button class="occhio${vede ? '' : ' via'}" data-occhio="${esc(n.ref)}" title="${vede ? 'Nascondi' : 'Mostra'} (tasto destro: altre scelte)">👁</button>`;
    }
    const q = n.qta > 1 ? `<span class="n-q">× ${n.qta}</span>` : '';
    return `<li><div class="${cls.filter(Boolean).join(' ')}"${data} title="${esc(n.label)}"><span class="k">${n.kind === 'mate' && iconaMate(n.tipo) ? `<img src="icons/${iconaMate(n.tipo)}.svg" alt="">` : iconImg(n.kind)}</span><span class="lb">${etichettaAlbero(n.label)}</span>${q}${conta}${st}${occhio}${freccia}</div>${figli}</li>`;
  };
  // 28/10: nell'assieme le copie dello stesso pezzo (3 o più) stanno in un gruppo «Nome × n» che si apre
  let albero = S.tree;
  if (S.mode === 'assembly' && S.tree) {
    const file = Object.fromEntries((S.instances || []).map(i => [i.id, i.file]));
    const pezzo = Object.fromEntries((S.instances || []).map(i => [i.file, i.pezzo]));   // 29/10: il gruppo col nome del pezzo
    const figli = [], gruppi = {};
    for (const c of S.tree.children) {
      if (c.kind !== 'instance') { figli.push(c); continue; }
      const k = file[c.ref] || c.ref;
      (gruppi[k] = gruppi[k] || []).push(c);
      if (gruppi[k].length === 1) figli.push({ _gruppo: k });
    }
    albero = { ...S.tree, children: figli.flatMap(c => {
      if (!c._gruppo) return [c];
      const g = gruppi[c._gruppo];
      if (g.length < 3) return g;
      return [{ label: pezzo[c._gruppo] || g[0].label.replace(/\s*\(\d+\)$/, ''), kind: 'members', ref: g.map(x => x.ref), qta: g.length, status: null, children: g }];
    }) };
  }
  const cerca = ($('#tree-cerca')?.value || '').trim().toLowerCase();
  const filtra = n => {                              // con la ricerca: le voci che contengono il testo (e i loro gruppi)
    if (!cerca || n.kind === 'assembly' || n.kind === 'project') return { ...n, children: n.children.map(filtra).filter(Boolean) };
    const figli = n.children.map(filtra).filter(Boolean);
    return String(n.label).toLowerCase().includes(cerca) || figli.length ? { ...n, children: figli } : null;
  };
  const molti = S.mode === 'assembly' && (S.instances || []).length > 6;
  const prima = document.activeElement?.id === 'tree-cerca';
  $('#tree').innerHTML = (molti ? `<input class="field tree-cerca" id="tree-cerca" placeholder="Cerca un pezzo…" value="${esc(cerca)}">` : '')
    + `<ul>${nodo(filtra(albero) || albero)}</ul>`;
  if (molti) {
    const inp = $('#tree-cerca');
    inp.oninput = () => renderTree();
    if (prima) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
  }
}
// tasto destro su una voce dell'albero: modifica, rinomina, disattiva, elimina, perché è rossa (21/10)
const VOCI_MENU = { modifica: 'Modifica', rinomina: 'Rinomina…', serie: 'Ripeti in serie…', disattiva: 'Disattiva (non farla, senza cancellarla)',
  attiva: 'Attiva', elimina: 'Elimina…', perche: 'Perché è rossa?' };
// Elimina con la conferma: cosa sparisce insieme (i disegni sopra, i tagli che li usano), poi tutto in un colpo
async function confermaElimina(kind, ref, titolo, dip = null) {
  if (dip === null) { const m = await call('tree_menu', kind, ref); dip = m.ok ? (m.dipendenti || []) : []; }
  // 04/11: la domanda col nome di cosa sparisce; il pulsante rosso dice quante voci toglie
  modal(`<h3>Eliminare «${esc(titolo)}»?</h3>
    ${dip.length ? `<div class="msg warn">Sparisce anche ${dip.length === 1 ? 'questa voce, che la usa' : `quello che la usa (${dip.length} voci)`}:</div><ul class="lista-dip">${dip.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : ''}
    <p class="hint">Se cambi idea: Annulla in alto (Ctrl+Z) lo rimette.</p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn danger" id="m-ok">${dip.length ? `Elimina ${dip.length + 1} voci` : 'Elimina'}</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => { close(); clearSelection(); inCoda(async () => { const r2 = await call('tree_action', kind, ref, 'elimina'); await apply(r2, r2.message); }); };
  }, { stretta: true });
}
function chiudiMenuAlbero() { document.getElementById('menu-albero')?.remove(); }
// 03/11: il nome del pezzo nell'assieme si cambia con doppio clic sulla voce (vale per le copie, la distinta, le tavole)
const nomeSenzaCopia = t => String(t || '').replace(/\s*\(\d+\)$/, '');
function rinominaPezzo(iid, nome) {
  const nuovo = String(nome || '').trim();
  if (!nuovo) return;
  inCoda(async () => { const r = await call('asm_rinomina', iid, nuovo); if (await apply(r, r.message) && r.select) await select(r.select, null, null, true); });
}
// il doppio clic si conta a mano: il primo clic sceglie il pezzo e ridisegna l'elenco, e il «dblclick» del browser
// (che vuole due clic sullo stesso elemento) non arrivava
let clicAlbero = { ref: null, t: 0 };
$('#tree').addEventListener('click', ev => {
  const el = ev.target.closest('.node[data-kind="instance"]');
  if (!el || S?.mode !== 'assembly' || ev.target.closest('input, .occhio, [data-apri]')) return;
  const t = performance.now(), doppio = clicAlbero.ref === el.dataset.ref && t - clicAlbero.t < 450;
  clicAlbero = { ref: el.dataset.ref, t: doppio ? 0 : t };
  if (!doppio) return;
  ev.stopPropagation(); ev.preventDefault();
  setTimeout(() => { const n = document.querySelector(`#tree .node[data-kind="instance"][data-ref="${CSS.escape(clicAlbero.ref || el.dataset.ref)}"]`); if (n) iniziaRinomina(n); }, 30);
}, true);
function iniziaRinomina(el) {
  if (el.querySelector('input')) return;
  const iid = el.dataset.ref, ist = (S.instances || []).find(i => i.id === iid);
  if (!ist) return;
  const prima = nomeSenzaCopia(ist.name);
  const inp = document.createElement('input');
  inp.className = 'field nome-albero'; inp.value = prima; inp.setAttribute('aria-label', 'Nome del pezzo');
  [...el.childNodes].filter(n => n.nodeType === 3 || n.classList?.contains('lb')).forEach(n => n.remove());   // il testo della voce: al suo posto il campo
  el.querySelector('.k').after(inp);
  inp.focus(); inp.select();
  let fatto = false;
  const fine = ok => { if (fatto) return; fatto = true; inp.classList.remove('nome-albero'); if (ok && inp.value.trim() && inp.value.trim() !== prima) rinominaPezzo(iid, inp.value); else renderTree(); };
  inp.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') fine(true); if (e.key === 'Escape') fine(false); };
  inp.onblur = () => fine(true);
  inp.onclick = e => e.stopPropagation();
}
// 28/10: nell'assieme i pezzi si nascondono, si isolano, si fanno trasparenti (solo a video, il file non cambia):
// per lavorare sul fondo del cassone si tolgono di mezzo le pareti
const VIS = { nascosti: new Set(), trasparenti: new Set(), solo: null };
function applicaVisibilita() {
  for (const o of objs.values()) {
    if (o.data.kind !== 'instance') continue;
    const id = o.data.id, vede = VIS.solo ? VIS.solo.has(id) : !VIS.nascosti.has(id);
    for (const x of [o.mesh, o.lines, ...(o.extra || [])]) if (x) x.visible = vede;
    const m = matOf(o), tr = VIS.trasparenti.has(id), pieno = opacitaPiena(m);
    const voluta = tr ? Math.min(0.22, pieno) : pieno;
    if (m.transparent !== voluta < 1 || m.opacity !== voluta) {
      m.transparent = voluta < 1; m.opacity = voluta; m.depthWrite = voluta >= 1; m.needsUpdate = true;
    }
  }
  ridisegna();
}
function visibilitaVia() { VIS.nascosti.clear(); VIS.trasparenti.clear(); VIS.solo = null; applicaVisibilita(); renderTree(); }
function menuPezzoAssieme(id, x, y) {
  chiudiMenuAlbero();
  const ist = (S.instances || []).find(i => i.id === id);
  if (!ist) return;
  const nascosto = VIS.solo ? !VIS.solo.has(id) : VIS.nascosti.has(id), tr = VIS.trasparenti.has(id);
  const qualcosa = VIS.nascosti.size || VIS.trasparenti.size || VIS.solo;
  const voci = [['apri', 'Apri il pezzo'], [nascosto ? 'mostra' : 'nascondi', nascosto ? 'Mostra' : 'Nascondi'],
    ['solo', 'Mostra solo questo'], [tr ? 'opaco' : 'trasparente', tr ? 'Non più trasparente' : 'Trasparente'],
    ...(qualcosa ? [['tutti', 'Mostra tutti i pezzi']] : [])];
  const box = document.createElement('div');
  box.id = 'menu-albero'; box.className = 'menu-albero';
  box.innerHTML = `<div class="ma-tit">${esc(ist.name)}</div>` + voci.map(([v, t]) => `<button data-v="${v}">${t}</button>`).join('');
  document.body.appendChild(box);
  const r = box.getBoundingClientRect();
  box.style.left = Math.min(x, innerWidth - r.width - 8) + 'px';
  box.style.top = Math.min(y, innerHeight - r.height - 8) + 'px';
  box.onclick = e => {
    const v = e.target.closest('button')?.dataset.v;
    if (!v) return;
    chiudiMenuAlbero();
    if (v === 'apri') { apriPezzoAssieme(id); return; }
    if (v === 'nascondi') { if (VIS.solo) VIS.solo.delete(id); else VIS.nascosti.add(id); if (sel && (sel.ids || [sel.id]).includes(id)) clearSelection(); }
    if (v === 'mostra') { if (VIS.solo) VIS.solo.add(id); else VIS.nascosti.delete(id); }
    if (v === 'solo') { VIS.solo = new Set([id]); VIS.nascosti.clear(); }
    if (v === 'trasparente') VIS.trasparenti.add(id);
    if (v === 'opaco') VIS.trasparenti.delete(id);
    if (v === 'tutti') { visibilitaVia(); return; }
    applicaVisibilita(); renderTree();
  };
}
$('#tree').addEventListener('contextmenu', ev => {
  const n = ev.target.closest('.node[data-kind="instance"]');
  if (!n || S?.mode !== 'assembly') return;
  ev.preventDefault(); ev.stopImmediatePropagation();
  menuPezzoAssieme(n.dataset.ref, ev.clientX, ev.clientY);
}, true);
$('#tree').addEventListener('click', ev => {
  const f = ev.target.closest('[data-apri]');
  if (!f) return;
  ev.stopPropagation(); ev.preventDefault();
  const k = f.dataset.apri;
  if (APERTI.has(k)) APERTI.delete(k); else APERTI.add(k);
  renderTree();
}, true);
$('#tree').addEventListener('click', ev => {
  const o = ev.target.closest('.occhio');
  if (!o) return;
  ev.stopPropagation(); ev.preventDefault();
  const id = o.dataset.occhio;
  const vede = VIS.solo ? VIS.solo.has(id) : !VIS.nascosti.has(id);
  if (VIS.solo) { if (vede) VIS.solo.delete(id); else VIS.solo.add(id); } else if (vede) VIS.nascosti.add(id); else VIS.nascosti.delete(id);
  applicaVisibilita(); renderTree();
}, true);
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
        modal(`<h3>Rinomina</h3><div class="form"><label class="tutta-riga">Nome<input class="field" id="rn-n" value="${esc(m.nome || '')}" placeholder="${esc(titolo)}"></label></div>
          <p class="hint">Vuoto = il nome che dà il programma.</p>
          <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Rinomina</button></div>`, close => {
          $('#m-no').onclick = close;
          $('#m-ok').onclick = () => { const nome = $('#rn-n').value; close(); inCoda(async () => apply(await call('tree_action', kind, ref, 'rinomina', nome))); };
          $('#rn-n').focus(); $('#rn-n').select();
          $('#modal-box').onkeydown = e2 => { if (e2.key === 'Enter') $('#m-ok').click(); if (e2.key === 'Escape') close(); };
        }, { stretta: true });
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
          conAnteprima('feature_serie', () => [ref, ...['#se-c', '#se-px', '#se-r', '#se-py'].map(q => $(q).value.trim())]);
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
function renderMateriale() {
  const box = $('#mat-riga');
  if (!box) return;
  const lst = S?.materiali || [];
  box.hidden = !lst.length || S.mode === 'assembly';
  if (box.hidden) return;
  box.innerHTML = `<label>Materiale<select class="field" id="mat-sel">${lst.map(m =>
    `<option value="${esc(m.code)}"${m.code === S.materiale ? ' selected' : ''}>${esc(m.nome)}</option>`).join('')}</select></label>`;
  $('#mat-sel').onchange = () => inCoda(async () => { const r = await call('set_material', $('#mat-sel').value); await apply(r, r.message); });
}
function renderParams() {
  renderMateriale();
  const righe = S.parameters.map(p => {
    const espr = typeof p.value === 'string';
    const nome = p.label && p.label.toLowerCase() !== p.name.toLowerCase() ? `<small>${esc(p.label)}</small>` : '';
    // 03/11: i parametri nati dai comandi (la Serie, l'offset) col loro nome da officina; la sigla resta per le formule
    if (p.auto && p.label) return `<tr><td title="Nelle formule si scrive ${esc(p.name)}"><b>${esc(p.label)}</b><small>nelle formule: ${esc(p.name)}</small></td><td><input class="field" data-p="${esc(p.name)}" value="${esc(espr ? p.value : String(p.value).replace('.', ','))}"></td>` +
      `<td class="res">${espr && p.resolved != null ? '= ' + num(p.resolved, 2) : ''}</td></tr>`;
    // 03/11: anche le misure normali col nome per esteso in grande (Larghezza, Spessore…); la sigla piccola sotto, per le formule
    if (p.label && p.label.toLowerCase() !== p.name.toLowerCase())
      return `<tr><td title="${esc(p.label)}: nelle formule si scrive ${esc(p.name)}"><b>${esc(p.label.replace(/ (\S{1,2})$/, String.fromCharCode(160) + '$1'))}</b><small>nelle formule: ${esc(p.name)}</small></td><td><input class="field" data-p="${esc(p.name)}" value="${esc(espr ? p.value : String(p.value).replace('.', ','))}"></td>` +
        `<td class="res">${espr && p.resolved != null ? '= ' + num(p.resolved, 2) : ''}</td></tr>`;
    return `<tr><td title="${esc(p.label || p.name)}"><b>${esc(p.name)}</b>${nome}</td><td><input class="field" data-p="${esc(p.name)}" value="${esc(espr ? p.value : String(p.value).replace('.', ','))}"></td>` +
      `<td class="res">${espr && p.resolved != null ? '= ' + num(p.resolved, 2) : ''}</td></tr>`;
  }).join('');
  // 03/11: raggio e K della piegatrice accanto alle misure della lamiera (prima solo nella scheda in basso, da trovare)
  const sh = S.sheet, d = sh?.def || {}, manca = new Set(sh?.missing || []);
  const riga = (k, sig, nome, miss) => `<tr><td title="${esc(nome)} (dato della piegatrice; vale per tutte le pieghe)"><b>${esc(nome)}</b><small>dato della piegatrice</small></td>
    <td><input class="field${miss ? ' missing' : ''}" data-tech-sx="${k}" value="${esc(d[k] == null ? '' : String(d[k]).replace('.', ','))}" placeholder="${miss ? 'manca' : ''}"></td><td class="res"></td></tr>`;
  const piega = sh ? riga('radius', 'R', 'Raggio di piega', manca.has('raggio interno'))
    + (d.method === 'bd90' ? riga('bd90', 'BD', 'Deduzione a 90°', manca.has('deduzione a 90°')) : d.method === 'din6935' ? '' : riga('k', 'K', 'Fattore K', manca.has('K-factor'))) : '';
  $('#params').innerHTML = (righe + piega) || '<tr><td class="hint">Nessuna misura con nome.</td></tr>';
  document.querySelectorAll('[data-tech-sx]').forEach(i => {
    const ora = i.value, salva = () => inCoda(async () => apply(await call('set_sheet_tech', sh.feature, { [i.dataset.techSx]: i.value })));
    i.onkeydown = ev => { if (ev.key === 'Enter') { ev.stopPropagation(); salva(); } };
    i.onblur = () => { if (i.value.trim() !== ora) salva(); };
  });
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
  inCoda(async () => { if (!await apply(await call('set_parameter', t.dataset.p, t.value))) t.classList.add('bad'); else inquadraSeServe(); });
}
// 04/11 notte (attriti, B 4): cambiata una misura a sinistra, il pezzo usciva dalla vista (o restava un puntino in un
// angolo) e serviva «Inquadra». Adesso, solo in quei casi, la vista si riadatta da sola, dolcemente, dalla stessa parte
function inquadraSeServe() {
  requestAnimationFrame(() => {
    if (SK || MIS || !objs.size || anim) return;
    const box = new THREE.Box3().setFromObject(model);
    if (box.isEmpty()) return;
    const A = areaLibera(), W = canvas.clientWidth, H = canvas.clientHeight;
    let fuori = false, x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const X of [box.min.x, box.max.x]) for (const Y of [box.min.y, box.max.y]) for (const Z of [box.min.z, box.max.z]) {
      const q = new THREE.Vector3(X, Y, Z).project(camera);
      if (q.z > 1) { fuori = true; continue; }
      const x = (q.x + 1) / 2 * W, y = (1 - q.y) / 2 * H;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
      if (x < A.l - 2 || x > A.r + 2 || y < A.t - 2 || y > A.b + 2) fuori = true;
    }
    const piccolo = Math.max((x1 - x0) / (A.r - A.l), (y1 - y0) / (A.b - A.t)) < 0.35;   // un terzo della vista, nei due versi
    if (fuori || piccolo) goTo(null, true);
  });
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
async function select(id, face = null, ids = null, silenzioso = false, nomeNoto = null) {
  const mio = ++selTok;
  puntoVia();                                        // il segno del punto sul tubo di prima
  if ($('#modal').hidden) anteprimaVia();             // l'anteprima del pannello di prima
  const stessa = sel && sel.id === id && sel.face === face;
  if (!stessa) { selGen++; MINI.faccia = false; }
  MINI.stessa = !!stessa;
  const eraMini = stessa && sel.soloMini, pannello = !!(stessa && sel.pannello);
  sel = { id, face, ids, soloMini: eraMini, pannello };
  paint(); renderTree(); paintNodes();
  // il nome della faccia: dopo una modifica quello di quando l'hai cliccata (il numero, nel pezzo rifatto, può essere un'altra faccia)
  const nome = face != null ? nomeNoto ?? objs.get(id)?.data.faces?.find(x => x.index === face)?.name ?? null : null;
  sel.nome = nome;
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
  nascondiMini(); togliManiglie(); MINI.faccia = false; MINI.s = null; puntoVia();
  if (!TRAV && !DIVSCEGLI) passoTubi(null);
  selTok++; selGen++;
  togliAnteprimaForo();
  if ($('#modal').hidden) anteprimaVia();
  sel = null; selForo = null; paint(); renderTree(); paintNodes();
  $('#props').innerHTML = '';
  aggiornaLayout();
}

async function disegnaSopra(aiuto) {
  // la faccia di sopra del pezzo: lì si disegnano fori, tagli, persiane
  const facce = objs.get('body')?.data?.faces || [];
  // la faccia cliccata, se c'è (sulla tramoggia non c'è un «sopra»: si lavora sulla parete scelta, 28/10)
  const scelta = sel?.id === 'body' && sel.face != null ? facce.find(x => x.index === sel.face && x.name) : null;
  const f = scelta || facce.find(x => x.name === `${S.sheet?.feature}/sopra`) || facce.find(x => /\/fine$/.test(x.name || ''));
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
    conAnteprima('add_end_miter', () => [leggiTesta()]);
  });
}
function pannelloTesta(s) {
  $('#props').innerHTML = pannelloLam({ titolo: esc(s.title), cose: 'taglio di testa sulle punte della lamiera',
    azioni: [azioneLam('delete', 'Togli questo taglio', 'id="tt-del"', 'danger', 'Toglie il taglio di testa: le punte tornano dritte')],
    corpo: campiTesta(s.def, 'ff'), dettagli: s.rows, fine: '<button class="btn primary big" id="tt-ok">Applica</button>' });
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
    case 'dividi':                                  // DIVIDI dalla barra: col tubo già scelto, o il prossimo cliccato
      // il tubo che hai appena cliccato tu (non quello scelto dall'ultimo comando): subito il pannello
      if (sel?.id && ultimoClic?.id === sel.id && objs.get(sel.id)?.data?.kind === 'member') { inCoda(() => iniziaDividi({ id: sel.id })); return; }
      DIVSCEGLI = true; passoTubi('Clicca un tubo del lato da dividere: il fianco, il davanti, il telaio sopra'); return;
    case 'piedi': case 'tappi': {                 // PIEDI e TAPPI (03/11): su tutte le gambe / teste in un colpo
      const id0 = sel?.id || '';
      const st = (id0.startsWith('struct=') ? id0.slice(7) : /[/:]/.test(id0) ? id0.split(/[/:]/)[0] : '') || S?.cutlist?.rows?.[0]?.members?.[0]?.split('/')[0];
      if (!st) { t('Prima serve una struttura.', 'err'); return; }
      inCoda(() => pannelloPiedi(st, id)); return;
    }
    case 'tipo_foro': t('Clicca un foro già fatto sul pezzo: a destra scegli svasato o filettato. Per un foro nuovo c’è «Foro».'); return;
    case 'foro': inCoda(() => foroDialog('tondo')); return;
    case 'angoli_tondi': inCoda(() => angoliSviluppo()); return;
    case 'incastri': inCoda(() => incastriDialog()); return;
    case 'asola': inCoda(() => foroDialog('asola')); return;
    case 'taglia': inCoda(() => disegnaSopra('Disegna la parte da togliere partendo da un bordo, poi «Togli materiale».')); return;
    case 'forme': inCoda(() => disegnaSopra('Una linea per ogni persiana, un cerchio per ogni bugna; poi «Pieghe e forme ▾» → Persiane o Imbutiture.')); return;
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
    case 'giunti': {
      const angolo = nodes.filter(n => n.members.length >= 2).sort((a, b) => b.xyz[2] - a.xyz[2])[0];
      if (angolo) inCoda(() => select(angolo.id));
      t('Clicca un angolo (pallino): nel pannello scegli col disegnino come si saldano i tubi.'); return;
    }
    case 'tubonuovo': t(nodes.length ? 'Clicca un angolo (pallino): intorno compaiono le frecce Su, Giù, Avanti, Dietro, Destra, Sinistra.' : 'Prima serve una struttura.'); return;
    case 'traverso': iniziaTraverso(); return;
    case 'fori': t('Clicca nel 3D la faccia del tubo dove vanno i fori, poi «Disegna sulla faccia» nel pannello.'); return;
    case 'sagoma': inCoda(sagomaNuova); return;
    case 'raccordo3d': dressTool('fillet'); return;
    case 'smusso3d': dressTool('chamfer'); return;
    case 'saldatura3d': dressTool('weld'); return;
    default: return;
  }
}
$('#props').addEventListener('click', ev => {
  const b = ev.target.closest('[data-azione]');
  if (b) { azione(b.dataset.azione); return; }
  const c = ev.target.closest('[data-cmd]');
  if (c) runCmd(c.dataset.cmd);
});

// ------------------------------------------------------------- prepara per il laser / l'officina
// 03/11 (collaudo): il verde «a posto» sopra il giallo «Da guardare» sembrava dire due cose opposte. Prima quello che va
// guardato; il verde solo se non c'è niente da guardare (se no il controllo fatto resta una riga piccola sotto)
function prepControllo(c, laserNo) {
  if (!c) return '';
  const avvisi = c.avvisi || [];
  // notte 03/11: un riquadro solo, col colore di stato: rosso se il laser non si può fare, ambra se c'è da guardare, verde se a posto
  if (!c.ok || avvisi.length) {
    const titolo = !c.ok ? c.testo : 'Da guardare prima di tagliare';
    return `<div class="prep-ok no${avvisi.length ? ' prep-avvisi' : ''}${!c.ok && laserNo ? ' err' : ''}"><div class="prep-stato">
      <b>${!c.ok ? 'Attenzione: ' : ''}${esc(titolo)}</b>
      ${avvisi.length ? `<span class="prep-da">${!c.ok ? 'Da guardare:' : ''}</span><ul>${avvisi.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${c.ok ? '<small>Per il resto: contorno chiuso, fori e pieghe controllati.</small>' : ''}</div></div>`;
  }
  return '<div class="prep-ok"><div class="prep-stato"><b>Il pezzo è a posto per il laser.</b><small>Contorno chiuso, fori e pieghe controllati.</small></div></div>';
}
// il tipo del file, da mettere accanto al nome (DXF, PDF, STEP…)
const tipoFile = f => { const m = /\.([a-z0-9]+)$/i.exec(String(f || '')); return m ? m[1].toUpperCase() : ''; };
// un percorso lungo va a capo dopo una \ (non a metà di un nome)
const percorsoHtml = f => esc(f).replace(/\\/g, '\\<wbr>');
const rigaFile = f => `<li><span class="pf-tipo">${esc(tipoFile(f))}</span><span class="pf-nome">${esc(f)}</span></li>`;
// 04/11 (percorsi A, B, C, telaio): «Guarda le tavole» da Prepara e poi «Chiudi» riporta qui, con le stesse spunte e
// la stessa cartella (prima si tornava al pezzo e la spunta del PDF era persa: 3 clic in più ogni volta)
let tornaPrepara = null;
async function preparaDialog(ricorda = null) {
  if (!Array.isArray(ricorda?.scelte)) ricorda = null;
  const info = await call('prepara_info');
  if (!info.ok) { toast(info.message, 'err'); return; }
  let cartella = ricorda?.cartella || info.cartella;
  if (ricorda) info.voci.forEach(v => { if (v.si) v.scelta = ricorda.scelte.includes(v.id); });
  const c = info.controllo;
  // notte 03/11: prima quello che si può fare, in fondo (spente) le voci non disponibili per questo pezzo
  const voci = [...info.voci.filter(v => v.si), ...info.voci.filter(v => !v.si)].map(v => `<label class="prep-voce${v.si ? '' : ' no'}" title="${v.si ? '' : esc('Non disponibile: ' + (v.motivo || ''))}">
      <input type="checkbox" data-voce="${v.id}" ${v.scelta ? 'checked' : ''} ${v.si ? '' : 'disabled'}>
      <span><b>${esc(v.titolo)}</b><span>${esc(v.desc)}</span>${v.si ? (tipoFile(v.file) ? '' : `<small class="pv-no">${esc(v.file)}</small>`) : `<small class="pv-no">${esc('Non disponibile: ' + (v.motivo || ''))}</small>`}${
        v.id === 'officina' && v.si ? '<button type="button" class="link prep-guarda" id="prep-tavole">Guarda le tavole</button>' : ''}</span>
      ${v.si && tipoFile(v.file) ? `<small class="pv-file" title="${esc(v.file)}"><i>${esc(tipoFile(v.file))}</i>${esc(v.file)}</small>` : '<small class="pv-file"></small>'}</label>`).join('');
  const laserNo = !info.voci.some(v => v.id === 'laser' && v.si);
  // 04/11 (percorsi A, B, C): un pezzo mai salvato non ha ancora un nome suo e i file venivano «Lamiera_sviluppo.dxf»,
  // «Pezzo_pieghe.csv»: qui si scrive il nome, e file e cartella lo prendono subito
  const chiediNome = !S?.path && S?.mode !== 'assembly';
  modal(`<h3>Cosa ti serve?</h3>
    ${chiediNome ? `<label class="prep-nome"><span>Come si chiama il pezzo</span><input class="field" id="prep-nome" value="${esc(S.name || '')}" spellcheck="false"></label>` : ''}
    ${prepControllo(c, laserNo)}
    <div class="prep-voci" role="group" aria-label="Cosa salvare">${voci}</div>
    <div class="prep-dove"><img src="icons/open.svg" alt=""><span>Si salvano in</span><b id="prep-dir" title="${esc(cartella)}">${percorsoHtml(cartella)}</b>
      <button class="btn piccolo" id="prep-cambia">Cambia cartella</button></div>
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
    $('#prep-cambia').onclick = () => inCoda(async () => { const r = await call('scegli_cartella'); if (r.ok) { cartella = r.cartella; $('#prep-dir').innerHTML = percorsoHtml(cartella); $('#prep-dir').title = cartella; } });
    // 03/11: le tavole si guardano da qui (prima solo da «Esporta ▾ → Tavole»): si apre l'editor delle tavole
    const scelteOra = () => [...document.querySelectorAll('#modal-box [data-voce]:checked')].map(i => i.dataset.voce);
    const nomeNuovo = () => { const v = $('#prep-nome')?.value.trim(); return v && v !== S.name ? v : null; };
    const rinomina = async v => { const r = await call('rinomina_pezzo', v); if (!(await apply(r))) return false; renderTree(); return true; };
    if ($('#prep-nome')) {
      const cambia = () => { const v = nomeNuovo(); if (!v) return;
        const scelte = scelteOra(), diversa = cartella !== info.cartella ? cartella : null;
        close(); inCoda(async () => { if (await rinomina(v)) await preparaDialog({ scelte, cartella: diversa }); }); };
      $('#prep-nome').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); ev.stopPropagation(); cambia(); } };
      // mentre scrivi i nomi dei file si aggiornano (il nome vero si dà con Invio o con «Salva i file»)
      const vecchio = S.name || '';
      const file = [...document.querySelectorAll('#modal-box .pv-file')].map(el => [el, el.lastChild?.textContent || '']);
      $('#prep-nome').oninput = () => {
        const v = $('#prep-nome').value.trim() || vecchio;
        for (const [el, f] of file) if (el.lastChild && vecchio && f.startsWith(vecchio)) el.lastChild.textContent = v + f.slice(vecchio.length);
      };
    }
    const tav = $('#prep-tavole');
    if (tav) tav.onclick = ev => {
      ev.preventDefault(); ev.stopPropagation();
      const v = nomeNuovo();                          // il nome scritto vale anche per le tavole (il cartiglio)
      tornaPrepara = { scelte: scelteOra(), cartella: cartella !== info.cartella ? cartella : null };
      close();
      if (v) inCoda(async () => { await rinomina(v); runCmd('drawings'); }); else runCmd('drawings');
    };
    $('#m-ok').onclick = () => {
      const scelte = scelteOra(), v = nomeNuovo(), diversa = cartella !== info.cartella;
      close();
      inCoda(async () => {
        if (v) {                                    // il nome scritto e non ancora confermato: prima quello
          if (!(await rinomina(v))) return;
          if (!diversa) { const ni = await call('prepara_info'); if (ni.ok) cartella = ni.cartella; }
        }
        const r = await call('prepara', cartella, scelte);
        if (!r.ok) { toast(r.message || 'Non riuscito.', 'err'); return; }
        preparaFatto(r);
      });
    };
  });
}

// 03/11: dopo «Salva i file» una conferma che resta (prima un messaggio di pochi secondi): quali file, dove, e i
// pulsanti per aprire la cartella o guardare le tavole. Si chiude solo con «Chiudi».
function preparaFatto(r) {
  modal(`<h3>File pronti</h3>
    <div class="prep-ok"><div class="prep-stato"><b>Salvat${r.files.length === 1 ? 'o 1 file' : `i ${r.files.length} file`}.</b><small>Li trovi nella cartella qui sotto.</small></div></div>
    <ul class="prep-fatti">${r.files.map(rigaFile).join('')}</ul>
    <div class="prep-dove"><img src="icons/open.svg" alt=""><span>Nella cartella</span><b class="prep-percorso" id="prep-dir">${percorsoHtml(r.cartella)}</b></div>
    <div class="acts"><button class="btn" id="prep-tav">Guarda le tavole</button><button class="btn" id="prep-apri">Apri la cartella</button>
      <button class="btn primary" id="m-ok">Chiudi</button></div>`, close => {
    $('#modal-box').classList.add('prepara');
    $('#m-ok').onclick = close;
    $('#prep-apri').onclick = () => inCoda(async () => {
      const x = await call('apri_cartella', r.cartella);
      if (x && x.ok === false) toast('Non riesco ad aprire la cartella: ' + (x.message || '') + '. Il percorso è scritto qui sopra.', 'err');
    });
    $('#prep-tav').onclick = () => { close(); runCmd('drawings'); };
  });
}
// 03/11: dopo ogni esportazione (tavole PDF/DXF, DXF di taglio, STEP, Excel, tabella pieghe) la stessa conferma di
// «Prepara»: il nome del file, la cartella, «Apri la cartella». Prima un messaggio di pochi secondi, e poi «dove l'ha messo?»
function fileFatto(r, titolo = 'File salvato') {
  const p = String(r.path || ''), k = Math.max(p.lastIndexOf('\\'), p.lastIndexOf('/'));
  const nome = k >= 0 ? p.slice(k + 1) : p, cartella = k >= 0 ? p.slice(0, k) : '';
  const avvisi = r.avvisi?.length;
  modal(`<h3>${esc(titolo)}</h3>
    <div class="prep-ok${avvisi ? ' no' : ''}"><div class="prep-stato"><b>${avvisi ? 'Salvato, ma c’è da guardare' : 'Salvato.'}</b>
      ${r.message ? `<small class="fatto-msg">${esc(r.message)}</small>` : ''}</div></div>
    <ul class="prep-fatti">${rigaFile(nome)}</ul>
    <div class="prep-dove"><img src="icons/open.svg" alt=""><span>Nella cartella</span><b class="prep-percorso" id="fatto-dir">${percorsoHtml(cartella)}</b></div>
    <div class="acts"><button class="btn" id="fatto-apri">Apri la cartella</button><button class="btn primary" id="m-ok">Chiudi</button></div>`, close => {
    $('#m-ok').onclick = close;
    $('#m-ok').focus();
    $('#modal-box').classList.add('prepara', 'fatto');
    $('#fatto-apri').onclick = () => inCoda(async () => {
      const x = await call('apri_cartella', cartella);
      if (x && x.ok === false) toast('Non riesco ad aprire la cartella: ' + (x.message || '') + '. Il percorso è scritto qui sopra.', 'err');
    });
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter' || ev.key === 'Escape') close(); };
  });
}
async function esportaFile(kind) {
  const r = await call('export', kind);
  if (r?.cancelled) return;
  if (!r?.ok || !r.path) { await apply(r); return; }
  const titoli = { step: 'STEP salvato', dxf: 'DXF di taglio salvato', bom: 'Distinta in Excel salvata', bendtable: 'Tabella pieghe salvata' };
  fileFatto(r, titoli[kind]);
}

let profili = null;
// 29/10: «la minibar fa cagare». Al clic nel 3D solo una barretta di icone attaccata alla cosa scelta (la segue quando
// giri la vista); le misure stanno SUL pezzo, come quote arancioni: clic e scrivi, oppure tira. Secondo clic sulla stessa
// flangia: la sua faccia. «⋯» apre il pannello completo a destra, solo se lo chiedi.
const MINI = { dove: null, ancora: null, faccia: false, stessa: false, s: null, tutti: true, nuova: false };
const QUOTE = [];                                    // { el, p: punto nel 3D, dx, dy, fuori: verso cui staccarla dal pezzo }
const SCELTE = { el: null, q: null, prova: null };   // il menu sotto una quota (45° 90° 135°, M6 M8…)
function nascondiMini() {
  document.getElementById('mini-barra')?.remove();
  document.getElementById('sc-linea')?.remove();
  togliQuote();
}
function togliQuote() { chiudiScelte(); for (const q of QUOTE) q.el.remove(); QUOTE.length = 0; }
function chiudiScelte() { SCELTE.el?.remove(); SCELTE.el = null; SCELTE.q = null; SCELTE.prova = null; }
const aSchermo = p => {
  const r = canvas.getBoundingClientRect(), v = p.clone().project(camera);
  return v.z > 1 ? null : [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height];
};
// 04/11: dove sta a schermo quello che hai scelto (la faccia, le facce della piega, o il pezzo intero), per mettere la
// barretta accanto e non sopra. I punti 3D si prendono una volta per scelta; a ogni disegno si proiettano
const SCELTA = { chi: '', punti: null };
function puntiScelta() {
  if (!sel) return null;
  const facce = sel.face != null ? [sel.face] : sel.hl || [];
  const chi = `${sel.id}|${facce.join(',')}|${S?.scene_version ?? ''}`;
  if (SCELTA.chi === chi) return SCELTA.punti;
  SCELTA.chi = chi; SCELTA.punti = null;
  const e = edgeSel();                               // un bordo: la barretta va accanto alla sua linea
  if (e) { SCELTA.punti = [v3(e.a), v3(e.b)]; return SCELTA.punti; }
  const o = objs.get(sel.id) || (facce.length ? objs.get('body') : null);
  if (!o?.mesh) return null;
  const M = o.pos || o.mesh.matrixWorld, pts = [];
  if (facce.length && o.data?.faces) {
    const P = o.data.positions, I = o.data.indices;
    const lista = facce.map(i => o.data.faces.find(f => f.index === i)).filter(Boolean);
    const tot = lista.reduce((n, f) => n + f.count, 0), passo = Math.max(1, Math.floor(tot / 900));
    for (const f of lista) for (let k = f.start; k < f.start + f.count; k += passo) {
      const j = I[k] * 3;
      pts.push(new THREE.Vector3(P[j], P[j + 1], P[j + 2]).applyMatrix4(M));
    }
  } else {
    const b = new THREE.Box3().setFromObject(o.mesh);
    if (b.isEmpty()) return null;
    for (const X of [b.min.x, b.max.x]) for (const Y of [b.min.y, b.max.y]) for (const Z of [b.min.z, b.max.z]) pts.push(new THREE.Vector3(X, Y, Z));
  }
  SCELTA.punti = pts.length ? pts : null;
  return SCELTA.punti;
}
function rettScelta(r) {
  const pts = puntiScelta();
  if (!pts) return null;
  let l = Infinity, t = Infinity, rr = -Infinity, b = -Infinity;
  for (const p of pts) {
    const q = aSchermo(p);
    if (!q) continue;
    l = Math.min(l, q[0]); rr = Math.max(rr, q[0]); t = Math.min(t, q[1]); b = Math.max(b, q[1]);
  }
  if (!Number.isFinite(l)) return null;
  return { left: Math.max(l, r.left), right: Math.min(rr, r.right), top: Math.max(t, r.top), bottom: Math.min(b, r.bottom) };
}
// a ogni disegno della vista: la barretta e le quote tornano sui loro punti del pezzo
function placeBarra() {
  const m = document.getElementById('mini-barra'), r = canvas.getBoundingClientRect();
  for (const x of QUOTE) {
    if (x.dopo) {                                    // in fila dopo un'altra quota (29/10: angolo e verso accanto alla lunghezza)
      const d = x.dopo;
      x.el.style.display = d.el.style.display;
      if (d.el.style.display === 'none') continue;
      const cx = parseFloat(d.el.style.left) + d.el.offsetWidth / 2 + 5 + x.el.offsetWidth / 2;
      x.el.style.left = cx + 'px'; x.el.style.top = d.el.style.top;
      continue;
    }
    const q = aSchermo(x.p);
    x.el.style.display = q ? '' : 'none';
    if (!q) continue;
    let ox = x.dx || 0, oy = x.dy || 0;
    if (x.fuori) {
      const q2 = aSchermo(x.p.clone().add(x.fuori));
      if (q2) { const vx = q2[0] - q[0], vy = q2[1] - q[1], n = Math.hypot(vx, vy) || 1; ox += vx / n * 42; oy += vy / n * 42; }
    }
    x.el.style.left = (q[0] + ox) + 'px'; x.el.style.top = (q[1] + oy) + 'px';
  }
  if (m && MINI.ancora) {
    const q = aSchermo(MINI.ancora);
    m.style.visibility = q ? '' : 'hidden';
    if (q && m.classList.contains('lato')) {
      const w = m.offsetWidth, h = m.offsetHeight, destra = q[0] + 80 + w < r.right - 8;
      const x = destra ? q[0] + 80 : Math.max(r.left + 8, q[0] - 80 - w), y = Math.max(r.top + 8, Math.min(q[1] - 70, r.bottom - h - 8));
      m.style.left = x + 'px'; m.style.top = y + 'px';
      let l = document.getElementById('sc-linea');
      if (!l) { l = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); l.id = 'sc-linea'; document.body.appendChild(l); }
      const ax = destra ? x : x + w, ay = Math.max(y + 20, Math.min(q[1], y + 60));
      l.innerHTML = `<path d="M${q[0]} ${q[1]}L${ax + (destra ? -24 : 24)} ${ay}H${ax}"/>`;
    } else if (q && m._evita && mettiAccanto(m, m._evita(), { left: r.left, right: r.right, top: r.top, bottom: Math.min(r.bottom, sopraRiga(r) + 8) })) {
      // (assieme) sotto, sopra o di lato al pezzo: non sopra
    } else if (q) {
      const w = m.offsetWidth, h = m.offsetHeight;
      let x = Math.max(r.left + 8, Math.min(q[0] - w / 2, r.right - w - 8));
      let y = Math.max(r.top + 34, Math.min(q[1] + (+m.dataset.giu || 30), sopraRiga(r) - h));
      // 04/11 (regola 3): la barretta non copre quello che hai cliccato. Sotto la faccia (o la piega) scelta, se no
      // sopra, se no di lato; solo se la scelta riempie la vista resta dov'era
      const sc = rettScelta(r), basso = sopraRiga(r), nome = 28;     // sopra la barra Inquadra/Quote/Tema (e la riga «prossimo passo»)
      if (sc) {
        const cx = Math.max(r.left + 8, Math.min((sc.left + sc.right) / 2 - w / 2, r.right - w - 8));
        const cy = Math.max(r.top + nome + 8, Math.min((sc.top + sc.bottom) / 2 - h / 2, basso - h));
        if (sc.bottom + 12 + nome + h <= basso) { x = cx; y = sc.bottom + 12 + nome; }
        else if (sc.top - 12 - h - nome >= r.top + 4) { x = cx; y = sc.top - 12 - h; }
        else if (sc.right + 16 + w <= r.right - 8) { x = sc.right + 16; y = cy; }
        else if (sc.left - 16 - w >= r.left + 8) { x = sc.left - 16 - w; y = cy; }
      }
      // 29/10: la barretta (col suo nome sopra, ~28 px) non copre le quote: sotto di loro, o sopra se sotto non c'è posto
      const sopraNome = 28, tocca = yy => QUOTE.filter(z => z.el.style.display !== 'none').map(z => z.el.getBoundingClientRect())
        .filter(b => b.right > x - 4 && b.left < x + w + 4 && b.bottom > yy - sopraNome - 4 && b.top < yy + h + 4);
      let urti = tocca(y);
      if (urti.length) {
        const giu = Math.max(...urti.map(b => b.bottom)) + sopraNome + 8;
        if (giu + h <= r.bottom - 8 && !tocca(giu).length) y = giu;
        else {
          const su = Math.min(...urti.map(b => b.top)) - h - 8;
          if (su - sopraNome >= r.top) y = su;
        }
      }
      m.style.left = x + 'px'; m.style.top = y + 'px';
    }
    if (!q) document.getElementById('sc-linea')?.remove();
  }
  if (SCELTE.el && SCELTE.q) {
    const b = SCELTE.q.getBoundingClientRect();
    SCELTE.el.style.left = (b.left + b.width / 2) + 'px'; SCELTE.el.style.top = (b.bottom + 6) + 'px';
  }
}
// 04/11 notte (attriti): fin dove può scendere la barretta: sopra la barretta Inquadra/Quote/Tema (62 px dal fondo) e
// sopra la riga «prossimo passo» se c'è (assieme appena creato, tubi): prima ci finiva sopra
function sopraRiga(r) {
  let y = r.bottom - 62;
  // (occhio) anche Inquadra/Quote/Tema, che sale sopra la riga «prossimo passo» quando c'è
  for (const id of ['asm-passo', 'trav-hint', 'link-hint', 'navbar']) {
    const e = document.getElementById(id);
    if (e && !e.hidden && e.offsetParent) y = Math.min(y, e.getBoundingClientRect().top - 10);
  }
  return y;
}
// 04/11: la barretta accanto al riquadro del pezzo, mai sopra: sotto (col nome sopra di lei), se no sopra, se no a
// destra o a sinistra. Se il pezzo riempie la vista: in basso nella vista, sopra la barrina Inquadra/Quote
function mettiAccanto(m, p, r) {
  if (!p) return false;
  const w = m.offsetWidth, h = m.offsetHeight, nome = 30, g = 10;
  const a = { left: Math.max(p.left, r.left), right: Math.min(p.right, r.right), top: Math.max(p.top, r.top), bottom: Math.min(p.bottom, r.bottom) };
  const cx = Math.max(r.left + 8, Math.min((a.left + a.right) / 2 - w / 2, r.right - w - 8));
  const cy = Math.max(r.top + nome + 8, Math.min((a.top + a.bottom) / 2 - h / 2, r.bottom - h - 8));
  const prove = [
    [cx, a.bottom + g + nome, () => a.bottom + g + nome + h <= r.bottom - 8],
    [cx, a.top - g - h, () => a.top - g - h - nome >= r.top + 8],
    [a.right + g, cy, () => a.right + g + w <= r.right - 8],
    [a.left - g - w, cy, () => a.left - g - w >= r.left + 8],
  ];
  let [x, y] = [cx, r.bottom - h - 64];
  const buona = prove.find(t => t[2]());
  if (buona) [x, y] = buona;
  m.style.left = x + 'px'; m.style.top = y + 'px';
  return true;
}
// la barretta. voci: [icona, suggerimento, fai, classe, anteprima(on)]; '|' = separatore. opz.chi: chi è (stessa
// cosa = niente animazione), opz.piu: cosa fa «⋯» (di solito il pannello completo), opz.piu === false: niente «⋯»
// 04/11 notte (attriti): UNA barretta per tutto (lamiera, tubi, assieme): il nome sopra, al massimo 5 azioni con
// icona e nome scritto accanto, «⋯» in fondo che apre il pannello a destra. Col pannello aperto la barretta non c'è
// (il pannello ha le stesse azioni, coi campi), come già nei tubi; la barretta torna scegliendo un'altra cosa
function barretta(nome, voci, opz = {}) {
  const vecchia = document.getElementById('mini-barra'), chi = opz.chi || nome;
  const uguale = vecchia?.dataset.chi === chi;
  vecchia?.remove();
  tip.style.display = 'none';
  if (sel?.pannello && opz.piu === undefined) { document.getElementById('sc-linea')?.remove(); return; }
  const m = document.createElement('div');
  m.id = 'mini-barra'; m.dataset.chi = chi;
  if (uguale) m.classList.add('fermo');
  // 04/11 (regola 3): al massimo 5 azioni col nome, il resto sta nel pannello («⋯»)
  { let n = 0; voci = voci.filter(v => v[0] === '|' || ++n <= 5); while (voci.at(-1)?.[0] === '|') voci.pop(); }
  m.innerHTML = `<span class="nome">${esc(nome)}</span>` + voci.map(([ic, t, , cls], i) => ic === '|' ? '<span class="sep"></span>'
    : `<button data-i="${i}" data-t="${esc(t)}" aria-label="${esc(t)}" class="${cls || (/^Togli/.test(t) ? 'via' : '')} con-scritta"${/ \(/.test(t) ? ` title="${esc(t)}"` : ''}><img src="icons/${ic}.svg" alt=""><span>${esc(t.replace(/ \(.*$/, ''))}</span></button>`).join('')
    + (opz.piu !== false ? `<span class="sep"></span><button class="piu" data-t="Tutte le opzioni" aria-label="Tutte le opzioni" title="Tutte le opzioni (il pannello a destra)">⋯</button>` : '');
  if (opz.evita) m._evita = opz.evita;
  document.body.appendChild(m);
  m.querySelectorAll('[data-i]').forEach(b => {
    const v = voci[+b.dataset.i];
    b.onclick = () => v[2]();
    if (v[4]) { b.onmouseenter = () => v[4](true); b.onmouseleave = () => v[4](false); }
  });
  m.querySelector('.piu')?.addEventListener('click', () => (opz.piu ? opz.piu() : tutteLeOpzioni()));
  placeBarra();
}
function tutteLeOpzioni() {
  if (!sel) return;
  sel.pannello = true; sel.soloMini = false; aggiornaLayout();
  // 04/11: il pannello dice già tutto: via la barretta (le quote sul pezzo restano)
  document.getElementById('mini-barra')?.remove(); document.getElementById('sc-linea')?.remove();
}   // il pannello completo, a destra
// mentre il pezzo si ricalcola: un segno accanto al nome (non sembra bloccata)
function schedaCalcola(on) { document.getElementById('mini-barra')?.classList.toggle('calcolo', on); }
// una quota sul pezzo. o: unita, num (il valore), etichetta, blu, dx/dy/fuori, titolo; e cosa fa:
// scrivi(v) (clic: si scrive lì), scelte [[v, testo]] + sceglie(v) + libero (si può scrivere anche un altro valore),
// clic(), tira { muovi(dx, dy, maiusc) → valore, fine() }, prova(v | null) (l'anteprima mentre scegli o scrivi), sopra(on)
function quota(p, testo, o = {}) {
  const el = document.createElement('div');
  el.className = 'quota' + (o.blu ? ' blu' : '') + (o.tira ? ' tira' : '') + (o.pulsa ? ' pulsa' : '');
  if (o.titolo) el.title = o.titolo;
  const scrivi = t => {
    el.innerHTML = `${o.etichetta ? `<span class="et">${esc(o.etichetta)}</span>` : ''}<span class="v">${esc(t)}</span>${o.unita ? `<span class="u">${o.unita}</span>` : ''}${o.tira ? '<span class="h" aria-hidden="true">↔</span>' : ''}`;
  };
  scrivi(testo);
  document.body.appendChild(el);
  const ent = { el, p, dx: o.dx || 0, dy: o.dy || 0, fuori: o.fuori || null, dopo: o.dopo || null };
  QUOTE.push(ent);
  let giu = null, mosso = false;
  el.addEventListener('pointerdown', e => {
    if (e.target.tagName === 'INPUT' || e.button !== 0) return;
    e.stopPropagation();
    giu = { x: e.clientX, y: e.clientY }; mosso = false;
    el.setPointerCapture(e.pointerId);
  });
  el.addEventListener('pointermove', e => {
    if (!giu || !o.tira) return;
    const dx = e.clientX - giu.x, dy = e.clientY - giu.y;
    if (!mosso && Math.hypot(dx, dy) < 4) return;
    mosso = true;
    el.querySelector('.v').textContent = virgola(o.tira.muovi(dx, dy, e.shiftKey, ent));
  });
  el.addEventListener('pointerup', () => {
    if (!giu) return;
    giu = null;
    if (mosso) { o.tira.fine(); return; }
    if (o.clic) o.clic();
    else if (o.scelte) apriScelte(el, o);
    else if (o.scrivi) scriviQuota(el, o);
  });
  if (o.sopra) { el.onmouseenter = () => o.sopra(true); el.onmouseleave = () => o.sopra(false); }
  ridisegna();
  return ent;
}
const rifaiMini = () => { if (MINI.s && sel) miniBarra(MINI.s); };
function scriviQuota(el, o) {
  chiudiScelte();
  el.classList.add('scrive');
  el.innerHTML = `${o.etichetta ? `<span class="et">${esc(o.etichetta)}</span>` : ''}<input value="${esc(virgola(o.num ?? ''))}" aria-label="${esc(o.etichetta || 'Valore')}">${o.unita ? `<span class="u">${o.unita}</span>` : ''}`;
  const i = el.querySelector('input');
  i.focus(); i.select();
  let chiuso = false;
  const fine = ok => {
    if (chiuso) return;
    chiuso = true;
    o.prova?.(null);
    const t = i.value.trim().replace(',', '.'), v = parseFloat(t);
    if (ok && t && Number.isFinite(v) && v > 0 && String(v) !== String(o.num)) o.scrivi(t);
    else rifaiMini();
  };
  i.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') fine(true); if (e.key === 'Escape') fine(false); };
  i.oninput = () => { const v = parseFloat(i.value.replace(',', '.')); if (Number.isFinite(v) && v > 0) o.prova?.(v); };
  i.onblur = () => fine(true);
}
function apriScelte(el, o) {
  chiudiScelte();
  const sc = document.createElement('div');
  sc.className = 'q-scelte';
  sc.innerHTML = o.scelte.map(([v, t]) => `<button data-v="${esc(String(v))}" class="${String(v) === String(o.num) ? 'on' : ''}">${esc(t)}</button>`).join('')
    + (o.libero ? `<input class="lib" placeholder="${esc(o.libero)}" aria-label="Un altro valore">` : '');
  document.body.appendChild(sc);
  Object.assign(SCELTE, { el: sc, q: el, prova: o.prova || null });
  placeBarra();
  sc.querySelectorAll('button').forEach(b => {
    b.onmouseenter = () => o.prova?.(b.dataset.v);
    b.onmouseleave = () => o.prova?.(null);
    b.onclick = () => { chiudiScelte(); o.prova?.(null); if (String(b.dataset.v) !== String(o.num)) o.sceglie(b.dataset.v); };
  });
  const i = sc.querySelector('.lib');
  if (!i) return;
  setTimeout(() => i.focus(), 0);
  i.oninput = () => { const v = parseFloat(i.value.replace(',', '.')); o.prova?.(Number.isFinite(v) && v > 0 ? String(v) : null); };
  i.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter' && i.value.trim()) { const v = i.value.trim().replace(',', '.'); chiudiScelte(); o.prova?.(null); o.sceglie(v); }
    if (e.key === 'Escape') { chiudiScelte(); o.prova?.(null); }
  };
}
// fuori dal menu di una quota: si chiude
document.addEventListener('pointerdown', e => {
  if (SCELTE.el && !e.target.closest('.q-scelte, .quota')) { SCELTE.prova?.(null); chiudiScelte(); }
}, true);
// la punta della flangia (il bordo libero, con la direzione in cui la flangia si allunga)
const puntaDi = s => bendEdges.find(x => x.kind === 'tip' && x.ref === s.flange && x.feature === s.feature && x.dir);
// dove si attacca la barretta quando la selezione non viene da un clic nel 3D (dopo una piega, dall'albero…)
function ancoraDi(s) {
  if (s.kind === 'flange') {
    const e = puntaDi(s);
    if (e) return v3(e.a).lerp(v3(e.b), 0.5).addScaledVector(v3(e.dir).normalize(), -(+s.def?.length || 0) / 2);
  }
  const o = objs.get(sel?.id);
  return o ? new THREE.Box3().setFromObject(o.mesh).getCenter(new THREE.Vector3()) : null;
}
// le azioni sul pezzo dell'assieme, le più usate prima: la barretta mostra le prime 5, il pannello tutte.
// ic, t (il nome; tra parentesi il di più per il suggerimento), fai, cls ('mov' = la misura che lo tiene)
function azioniPezzo(s) {
  const id = s.id, faccia = sel?.id === id && sel?.face != null ? sel.face : null;
  const piana = faccia != null && s.face?.kind === 'piana', foro = faccia != null && /cilindr/.test(s.face?.kind || '');
  return [
    // 03/11: il pezzo tenuto da una distanza o da un angolo (il cassetto): la misura sulla barretta, un clic e la
    // scrivi o tiri il cursore nel pannello
    ...(s.movimenti || []).slice(0, 1).map((mv, k) => ({ ic: 'dimension', cls: 'mov',
      t: `${mv.nome.replace(/ \(.*$/, '')} ${virgola(Math.round(mv.valore * 10) / 10)} ${mv.campo === 'angle' ? '°' : 'mm'}`,
      fai: () => { tutteLeOpzioni(); setTimeout(() => { const c = $('#mv-v' + k); if (c) { c.focus(); c.select(); } }, 60); } })),
    { ic: 'open', t: 'Apri il pezzo', fai: () => apriPezzoAssieme(id), id: 'open' },
    { ic: 'appoggia', t: piana ? 'Appoggia (da questa faccia)' : 'Appoggia', fai: () => appoggiaDa(id, piana ? faccia : null) },
    ...(foro ? [{ ic: 'fastener', t: 'Viti nei fori', fai: () => runCmd('asm_viteria') }] : []),
    { ic: 'move', t: 'Sposta', fai: () => spostaDa() },
    ...(piana ? [{ ic: 'sketch', t: 'Pezzo nuovo qui (su questa faccia)', fai: () => nuovoPezzoDialog(s) }] : []),
    { ic: 'vano', t: 'Metti nel vano di un telaio', fai: () => vanoDa(id) },
    ...(s.scassi ? [{ ic: 'cut', t: `Scassi: ${s.scassi.frase.replace(/ \(.*$/, '')} (in rosso)`, fai: () => tutteLeOpzioni() }] : []),
    { ic: 'pattern_rect', t: 'In fila', fai: () => ripetiApri(id) },
    ...(foro ? [] : [{ ic: 'fastener', t: 'Viteria', fai: () => runCmd('asm_viteria') }]),
    { ic: 'eye', t: 'Nascondi', fai: () => { VIS.nascosti.add(id); clearSelection(); applicaVisibilita(); renderTree(); } },
    { ic: 'select', t: 'Solo questo', fai: () => { VIS.solo = new Set([id]); applicaVisibilita(); renderTree(); } },
  ];
}
// dove sta il pezzo sullo schermo (il riquadro dei suoi 8 spigoli), per non metterci sopra la barretta
function rettangoloPezzo(id) {
  const o = objs.get(id);
  if (!o) return null;
  const b = new THREE.Box3().setFromObject(o.mesh);
  if (b.isEmpty()) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) {
    const q = aSchermo(new THREE.Vector3(x, y, z));
    if (!q) return null;
    x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]);
  }
  return { left: x0, top: y0, right: x1, bottom: y1 };
}
function miniBarra(s) {
  if (SK || DRESS || MIS) { if (!(sel?.soloMini)) nascondiMini(); return; }
  const d = MINI.dove;
  MINI.dove = null;
  // 04/11 (ritocchi): «viene da un clic nel 3D» non scade dopo 2,5 s: se il motore è lento a rispondere, il clic su
  // quel pezzo apre lo stesso la barretta (prima apriva il pannello). Vale il pezzo cliccato; il tempo solo per i clic
  // che non sanno su cosa sono caduti (e mezzo minuto al massimo)
  const passati = d ? performance.now() - d.t : Infinity;
  const daClic = !!d && (d.id && sel?.id ? d.id === sel.id && passati < 30000 : passati < 2500);
  if (daClic) MINI.ancora = d.p ? d.p.clone() : null;
  else if (!MINI.stessa) MINI.ancora = null;
  const assieme = S.mode === 'assembly' && s.kind === 'instance';
  if (s.kind === 'member' && S.mode !== 'assembly') { miniTubo(s, daClic); return; }
  if (!assieme && (S.mode === 'assembly' || !['body', 'flange', 'fold', 'sidebend', 'edgeflange', 'endmiter'].includes(s.kind) || s.flange_form)) { nascondiMini(); return; }
  MINI.s = s;
  if (!MINI.ancora) MINI.ancora = ancoraDi(s);
  if (!MINI.ancora) { nascondiMini(); return; }
  togliQuote();
  sel.soloMini = !sel.pannello; aggiornaLayout();      // il pannello a destra solo se l'hai chiesto con «⋯»
  if (assieme) {
    // 04/11 (regola 3): al massimo 5 azioni col nome, le altre in «Altro» (il pannello a destra le ha tutte, con il
    // nome). La barretta si mette sotto il pezzo (o sopra, o di lato): prima copriva proprio il pezzo appena cliccato
    const id = sel?.id;
    barretta(s.title, azioniPezzo(s).slice(0, 5).map(a => [a.ic, a.t, a.fai, a.cls]), { chi: 'i:' + id, evita: () => rettangoloPezzo(id) });
    return;
  }
  if (s.foro) { miniForo(s); return; }
  if (s.contorno) { miniTaglio(s); return; }
  const suFaccia = s.face?.planar && s.face?.name;
  const foro = ['hole', 'Foro', () => inCoda(() => foroDialog('tondo', s.face?.name))];
  const asola = ['slot', 'Asola', () => inCoda(() => foroDialog('asola', s.face?.name))];
  const taglio = ['cut', 'Taglio', () => azione('taglia')];
  const faccia = s.face?.label ? s.face.label.replace(/ di "[^"]*"$/, '') : '';
  if (s.kind === 'flange' && s.def && !MINI.faccia) { miniFlangia(s, suFaccia ? [foro, asola, taglio] : []); return; }
  const lavora = suFaccia ? [foro, asola, ['project', 'Disegna qui', () => inCoda(() => disegnaSopra())], taglio] : [];
  const nome = MINI.faccia ? `Faccia di ${s.title.toLowerCase()}` : s.kind === 'body' ? (s.face ? faccia || 'Faccia' : s.title) : s.title;
  // 03/11: sulla faccia i pulsanti con il nome scritto (Foro, Asola, Disegna qui…): con le sole icone non si trovavano.
  // 04/11: sempre col nome (anche il pezzo intero e le pieghe); il pezzo intero ha anche lo sviluppo
  const intero = s.kind === 'body' && !s.face && S?.sheet?.data ? [['flat', 'Sviluppo', () => runCmd('unfold')]] : [];
  barretta(nome, [...lavora, ...intero, ['dimension', 'Misura', () => runCmd('misura')]], { chi: `${sel.id}:${sel.face}:${MINI.faccia}`, scritte: true });
}
// TUBI (notte 03/11, regola 3): clic su un tubo nel 3D = la barretta accanto al tubo, coi comandi che si usano di
// più, scritti; «⋯» apre il pannello intero (come la lamiera). Dall'albero o dopo un comando: subito il pannello.
// Il tubo in piedi ha la barretta di lato (sotto coprirebbe la gamba), quello sdraiato sotto il punto cliccato
function apriPannelloTubi() { if (sel) { sel.pannello = true; sel.soloMini = false; } nascondiMini(); aggiornaLayout(); }
function miniTubo(s, daClic) {
  const resta = MINI.stessa && sel?.soloMini && document.getElementById('mini-barra');
  if (!daClic && !resta) { nascondiMini(); if (sel) { sel.pannello = true; sel.soloMini = false; } aggiornaLayout(); return; }
  MINI.s = s;
  if (!MINI.ancora) MINI.ancora = ancoraDi(s);
  if (!MINI.ancora) { nascondiMini(); return; }
  togliQuote();
  sel.soloMini = !sel.pannello; aggiornaLayout();
  const tb = s.tubo || {}, mis = (s.rows.find(r => r[0] === 'Da tagliare')?.[1] || '').replace(/, dritto$/, '');
  const poi = (fn, campo) => () => { apriPannelloTubi(); fn?.(); if (campo) { const c = $(campo); if (c) { c.focus(); c.select?.(); } } };
  const id = s.id;
  // 04/11 notte (attriti): sul telaio sopra o su un tubo lungo «Dividi» viene prima (la croce in 3 clic)
  const dividere = !!tb.facce?.length && !tb.verticale && tuboDaDividere(id);
  const dividi = tb.facce?.length ? [['pattern_rect', 'Dividi', poi(() => inCoda(() => iniziaDividi({ id })))]] : [];
  barretta(`${s.title}${mis ? ', ' + mis : ''}`, [
    ...(dividere ? dividi : []),
    ['box', 'Cambia tubo', poi(null, '#p-prof')],
    ['traverso', 'Traverso da qui', poi(() => iniziaTraverso(id))],
    ...(dividere ? [] : dividi),
    ['tubo', 'Tubo nuovo da qui', poi(() => $('#p-punto')?.click())],
    ...(s.lavorabile ? [['hole', 'Fori qui', poi(() => $('#p-lav')?.click())]] : []),
  ].slice(0, 5), { chi: 'tubo:' + id, scritte: true, piu: apriPannelloTubi });   // «⋯»: il pannello intero, la barretta va via (direbbe le stesse cose)
  const m = document.getElementById('mini-barra');
  if (m) { if (tb.verticale) m.classList.add('lato'); else m.dataset.giu = '72'; placeBarra(); }
  if (dividere && !TRAV && !DIVSCEGLI && !PUNTO) consiglioDividi(id);
}
// la flangia: lunghezza, angolo e verso sono quote sul pezzo; la lunghezza si scrive o si tira
function miniFlangia(s, lavora) {
  const f = s.def, e = puntaDi(s), L = +f.length;
  const cambia = campi => {
    schedaCalcola(true);
    inCoda(async () => { const ok = await apply(await call('edit_flange', s.feature, s.flange, campi)); fantasmaFlangia(0); if (ok) await refreshSel(); schedaCalcola(false); });
  };
  barretta(titoloFlangia(s), [
    ...(e ? [['flange', 'Piega sulla punta', () => { MINI.dove = { p: v3(e.a).lerp(v3(e.b), 0.5), t: performance.now() }; selectEdge(e); }]] : []),
    ...lavora, '|',
    ['delete', 'Togli la piega', () => { clearSelection(); inCoda(async () => apply(await call('delete_flange', s.feature, s.flange))); }]].map(v => (v === '|' ? ['|'] : v)),
  { chi: `fl:${s.feature}/${s.flange}`, scritte: true });
  const nuova = MINI.nuova;
  MINI.nuova = false;
  if (!e) return;
  const a = v3(e.a), b = v3(e.b), d = v3(e.dir).normalize(), m = a.clone().lerp(b, 0.5);
  let tiro = 0;
  const pxmm = () => {                               // quanti pixel fa un millimetro lungo la flangia, adesso
    const p0 = aSchermo(m), p1 = aSchermo(m.clone().addScaledVector(d, 100));
    return p0 && p1 ? [(p1[0] - p0[0]) / 100, (p1[1] - p0[1]) / 100] : [1, 0];
  };
  const qL = quota(m.clone(), NUM(L), {
    // 04/11: sulla quota si legge se è fuori tutto o dal bordo (B_staffa 15: «60 è fuori o dentro?»)
    unita: 'mm', num: L, etichetta: (POS_UI[f.position || 'inside'] || '').toLowerCase(), tira: {
      muovi: (dx, dy, maiusc, ent) => {
        const [ux, uy] = pxmm(), l2 = ux * ux + uy * uy || 1;
        let dl = (dx * ux + dy * uy) / l2;
        dl = Math.max(maiusc ? Math.round(dl / 5) * 5 : Math.round(dl), 1 - L);
        tiro = dl;
        ent.p = m.clone().addScaledVector(d, dl);
        fantasmaFlangia(dl);
        return L + dl;
      },
      fine: () => { if (tiro) cambia({ length: String(L + tiro) }); else fantasmaFlangia(0); tiro = 0; },
    },
    fuori: d.clone().multiplyScalar(10), pulsa: nuova, titolo: 'Clic: scrivi la lunghezza · trascina: allunga o accorcia (Maiusc: passi di 5)',
    scrivi: v => cambia({ length: v }), prova: v => fantasmaFlangia(v == null ? 0 : v - L),
  });
  // 29/10: angolo e verso in fila subito dopo la lunghezza («deve stare vicino, senò lo perdi»)
  const provaAng = v => (v == null ? anteprimaVia() : anteprima('edit_flange', () => [s.feature, s.flange, { angle: String(v) }], null));
  const qA = quota(m.clone(), `${NUM(f.angle)}°`, {
    num: f.angle, dopo: qL, titolo: 'Angolo della piega',
    scelte: [[90, '90°'], [45, '45°'], [135, '135°']], libero: 'altro…', sceglie: v => cambia({ angle: v }), prova: provaAng,
  });
  const giu = f.direction === 'down', altro = giu ? 'up' : 'down';
  quota(m.clone(), '⇅', {
    blu: true, dopo: qA, titolo: `Verso: adesso ${giu ? 'in giù' : 'in su'} · clic per girarla`,
    clic: () => { anteprimaVia(); cambia({ direction: altro }); },
    sopra: on => (on ? anteprima('edit_flange', () => [s.feature, s.flange, { direction: altro }], null) : anteprimaVia()),
  });
}
// 29/10 (opzione B): il foro ha la sua scheda accanto, legata da una linea. In alto i quattro tipi col disegnino in
// sezione; in mezzo la sezione del foro con le misure scritte sul disegno (clic e scrivi); sotto «vale per tutti / solo
// questo». Gli altri fori uguali si accendono sul pezzo, così si vede a quali vale la modifica.
const TIPI_FORO = [['semplice', 'Passante'], ['svasato', 'Svasato'], ['filettato', 'Filettato'], ['inserto', 'Inserto']];
// la sezione del foro (w × h px). t: lo spessore da disegnare; d, D, A: foro, svasatura, angolo
function sezioneForo(tipo, d, D, A, t, w, h, spazio = 0) {
  const sc = Math.min((w - 10) / 36, (h - 14 - spazio) / t), cx = w / 2, top = h / 2 - t * sc / 2, bot = top + t * sc;
  const largo = 18 * sc, r = Math.min(d / 2 * sc, largo - 6), id = 'tr' + Math.random().toString(36).slice(2, 7);
  let sx, dx, R = r;
  if (tipo === 'svasato') {
    R = Math.min(D / 2 * sc, largo - 3);
    const hz = Math.min(t * sc, (R - r) / Math.tan(A / 2 * Math.PI / 180));
    sx = `M${cx - largo} ${top}H${cx - R}L${cx - r} ${top + hz}V${bot}H${cx - largo}Z`;
    dx = `M${cx + largo} ${top}H${cx + R}L${cx + r} ${top + hz}V${bot}H${cx + largo}Z`;
  } else {
    const g = tipo === 'inserto' ? 3 : 0;
    sx = `M${cx - largo} ${top}H${cx - r - g}V${bot}H${cx - largo}Z`; dx = `M${cx + largo} ${top}H${cx + r + g}V${bot}H${cx + largo}Z`;
  }
  let g = `<defs><pattern id="${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#5E6B78" stroke-width="1.5"/></pattern></defs>
    <path d="${sx}" fill="url(#${id})" stroke="#C7CFD8" stroke-width="1.5"/><path d="${dx}" fill="url(#${id})" stroke="#C7CFD8" stroke-width="1.5"/>
    <line x1="${cx}" y1="${top - 12}" x2="${cx}" y2="${bot + 12}" stroke="#75808B" stroke-dasharray="8 3 2 3"/>`;
  if (tipo === 'filettato') for (let y = top + 3; y < bot - 1; y += 4) g += `<path d="M${cx - r} ${y}l-3 2l3 2M${cx + r} ${y}l3 2l-3 2" stroke="#FFB000" fill="none" stroke-width="1.2"/>`;
  if (tipo === 'inserto') g += `<rect x="${cx - r - 3}" y="${top - 4}" width="${2 * r + 6}" height="${bot - top + 4}" fill="none" stroke="#5AA9FF" stroke-width="2"/><rect x="${cx - r - 7}" y="${top - 6}" width="${2 * r + 14}" height="4" fill="#5AA9FF"/>`;
  return { g, cx, top, bot, r, R };
}
const pittogrammaForo = tipo => `<svg width="46" height="28" viewBox="0 0 80 46" aria-hidden="true">${sezioneForo(tipo, 12, 26, 90, 9, 80, 46).g}</svg>`;
function miniForo(s) {
  const fo = s.foro, h = fo.hole || {}, n = fo.uguali.length, tipo = h.tipo || 'semplice', t = +fo.spessore || 0;
  if (!MINI.stessa) MINI.tutti = true;
  if (sel?.pannello) { nascondiMini(); return; }     // 04/11: col pannello aperto («⋯») la scheda accanto direbbe le stesse cose
  const c3 = fo.centri?.[fo.cerchio];
  if (c3) MINI.ancora = v3(c3);                      // la scheda punta al centro del foro, non a dove hai cliccato
  const cerchi = () => (MINI.tutti ? fo.uguali : [fo.cerchio]);
  const fai = (spec, diam = fo.d) => {
    schedaCalcola(true);
    inCoda(async () => {
      let r;
      if (fo.importato) r = await call('hole_adopt', fo.faccia, cerchi().map(k => fo.centri[k]), diam, spec);
      else {
        if (Math.abs(diam - fo.d) > 1e-6 && !(await apply(await call('sketch_hole_diameter', fo.sketch, cerchi(), String(diam))))) { schedaCalcola(false); return; }
        r = await call('sketch_hole_type', fo.sketch, cerchi(), spec);
      }
      if (await apply(r)) {
        const f = c3 ? await call('faccia_del_foro', c3) : null;
        if (f?.ok) await select('body', f.face, null, true); else await refreshSel();
      }
      schedaCalcola(false);
    });
  };
  const spec = () => (tipo === 'svasato' ? { tipo, D: h.D, angolo: h.angolo } : tipo === 'filettato' ? { tipo, M: h.M } : tipo === 'inserto' ? { ...h } : null);
  // la svasatura più larga che sta nello spessore (la stessa regola del messaggio d'errore), a mezzo millimetro
  const okM = fo.min_d ? fo.filetti_ok || [] : FILETTI_M;   // un foro dello STEP può solo allargarsi
  const piuLarga = ang => (t ? Math.floor((fo.d + 2 * t * Math.tan(ang / 2 * Math.PI / 180)) * 2 - 1e-6) / 2 : Math.round(fo.d * 2 * 10) / 10);
  const scegli = k => {
    if (k === tipo) return;
    if (k === 'semplice') fai(null);
    else if (k === 'svasato') fai({ tipo: 'svasato', D: String(piuLarga(90)), angolo: '90' });
    else if (k === 'filettato') { if (okM.length) fai({ tipo: 'filettato', M: okM.includes(h.M) ? h.M : fo.min_d ? okM[0] : 'M6' }); }
    else tutteLeOpzioni();                           // l'inserto vuole il codice del catalogo: il pannello completo
  };
  nascondiMini();
  tip.style.display = 'none';
  const W = 312, H = 168, sz = sezioneForo(tipo, fo.d, +h.D || fo.d, +h.angolo || 90, t || 3, W, H, 64);
  const chip = (k, testo, x, y, titolo) => `<button class="quota in${k === 'd' || k === 'M' ? '' : ' blu'}" data-k="${k}" style="left:${x}px;top:${y}px" title="${esc(titolo)}"><span class="v">${esc(testo)}</span></button>`;
  const chips = [];
  if (tipo === 'filettato') chips.push(chip('M', h.M || 'M6', sz.cx, sz.bot + 26, 'Filetto'));
  else chips.push(chip('d', `Ø${NUM(fo.d)}`, sz.cx, sz.bot + 26, 'Diametro del foro'));
  if (tipo === 'svasato') chips.push(chip('D', `Ø${NUM(h.D)}`, sz.cx, sz.top - 24, 'Diametro della svasatura'), chip('A', `${NUM(h.angolo)}°`, sz.cx + sz.R + 34, sz.top + 4, 'Angolo della svasatura'));
  if (tipo === 'inserto') chips.push(chip('ins', h.codice || 'inserto', sz.cx, sz.top - 24, 'Codice e misure: in «⋯»'));
  const linee = `<line x1="${sz.cx - sz.r}" y1="${sz.bot + 12}" x2="${sz.cx + sz.r}" y2="${sz.bot + 12}" stroke="#FFB000"/>`
    + (tipo === 'svasato' ? `<line x1="${sz.cx - sz.R}" y1="${sz.top - 10}" x2="${sz.cx + sz.R}" y2="${sz.top - 10}" stroke="#5AA9FF"/>` : '');
  const m = document.createElement('div');
  m.id = 'mini-barra'; m.className = 'lato scheda-foro'; m.dataset.chi = `foro:${fo.sketch || fo.faccia}:${fo.cerchio}`;
  m.innerHTML = `<div class="sf-testa"><b>${esc(s.title)}</b>${n > 1 ? `<small>${n} uguali</small>` : ''}
      <button class="sf-b" data-a="piu" title="Tutte le opzioni">⋯</button>${fo.sketch ? '<button class="sf-b via" data-a="togli" title="Togli il foro"><img src="icons/delete.svg" alt=""></button>' : ''}
      <button class="sf-b" data-a="x" title="Chiudi (Esc)">×</button></div>
    <div class="sf-tipi">${TIPI_FORO.map(([k, l]) => { const no = k === 'filettato' && !okM.length;
      return `<button data-t="${k}" class="${k === tipo ? 'on' : ''}"${no ? ` disabled title="Il foro è già Ø${NUM(fo.min_d)}: troppo grande per i filetti in tabella"` : ''}>${pittogrammaForo(k)}${l}</button>`; }).join('')}</div>
    <div class="sf-sez" style="height:${H}px"><svg width="${W}" height="${H}">${sz.g}${linee}</svg>${chips.join('')}</div>
    ${fo.min_d ? `<div class="sf-nota">Foro già nel pezzo STEP: può solo allargarsi (da Ø${NUM(fo.min_d)} in su).</div>` : ''}
    ${n > 1 ? `<div class="sf-piede"><span>Vale per</span><div class="sf-seg"><button data-tt="1" class="${MINI.tutti ? 'on' : ''}">tutti e ${n}</button><button data-tt="0" class="${MINI.tutti ? '' : 'on'}">solo questo</button></div></div>` : ''}
    ${fo.cambiabile ? `<div class="sf-piede"><span>Dove sono${n > 1 ? ', quanti' : ''}, diametro</span><button class="btn" data-a="cambia" title="Riapre la finestra del Foro: al centro, agli angoli, in fila, distanze dai bordi">Sposta o cambia…</button></div>` : ''}`;
  document.body.appendChild(m);
  m.querySelector('[data-a="cambia"]')?.addEventListener('click', () => cambiaFori(fo.feature || fo.sketch));
  m.querySelector('[data-a="x"]').onclick = () => clearSelection();
  m.querySelector('[data-a="piu"]').onclick = () => tutteLeOpzioni();
  m.querySelector('[data-a="togli"]')?.addEventListener('click', () => togliDalTaglio(fo.sketch, [fo.cerchio], 'il foro'));
  m.querySelectorAll('[data-t]').forEach(b => { b.onclick = () => { anteprimaVia(); scegli(b.dataset.t); }; });
  // 29/10: passando col mouse su un tipo il foro si vede già così (svasato, filettato) sul pezzo
  const specDi = k => (k === 'semplice' ? null : k === 'svasato' ? { tipo: 'svasato', D: String(piuLarga(90)), angolo: '90' }
    : k === 'filettato' && okM.length ? { tipo: 'filettato', M: okM.includes(h.M) ? h.M : fo.min_d ? okM[0] : 'M6' } : undefined);
  m.querySelectorAll('[data-t]').forEach(b => {
    const k = b.dataset.t, sp = specDi(k);
    if (k === tipo || sp === undefined) return;
    b.onmouseenter = () => anteprima(fo.importato ? 'hole_adopt' : 'sketch_hole_type',
      () => (fo.importato ? [fo.faccia, cerchi().map(i => fo.centri[i]), fo.d, sp] : [fo.sketch, cerchi(), sp]), null);
    b.onmouseleave = () => anteprimaVia();
  });
  m.querySelectorAll('[data-tt]').forEach(b => { b.onclick = () => { MINI.tutti = b.dataset.tt === '1'; miniForo(s); }; });
  const lega = (k, o) => { const b = m.querySelector(`[data-k="${k}"]`); if (b) b.onclick = e => { e.stopPropagation(); (o.scelte ? apriScelte : scriviQuota)(b, o); }; };
  lega('d', { unita: 'mm', num: fo.d, scrivi: v => fai(spec(), parseFloat(v)) });
  lega('D', { num: h.D, scrivi: v => fai({ ...spec(), D: v }) });
  lega('A', { num: h.angolo, scelte: [[90, '90°'], [120, '120°']], libero: 'altro…', sceglie: v => fai({ ...spec(), angolo: v }) });
  lega('M', { num: h.M, scelte: okM.map(x => [x, x]), sceglie: v => fai({ tipo: 'filettato', M: v }) });
  m.querySelector('[data-k="ins"]')?.addEventListener('click', () => tutteLeOpzioni());
  // gli anelli sui fori: arancio quello scelto, azzurri gli altri a cui vale la modifica
  for (const k of fo.uguali) {
    const p = fo.centri?.[k];
    if (!p || (!MINI.tutti && k !== fo.cerchio)) continue;
    const el = document.createElement('div');
    el.className = 'q-anello' + (k === fo.cerchio ? ' scelto' : '');
    document.body.appendChild(el);
    QUOTE.push({ el, p: v3(p), dx: 0, dy: 0 });
  }
  placeBarra(); ridisegna();
}
// il taglio: le sue misure come quote accanto, una sotto l'altra
function miniTaglio(s) {
  const co = s.contorno, P = MINI.ancora.clone();
  barretta(s.title, [...(co.rapido ? [['move', 'Sposta o cambia', () => cambiaFori(co.feature)]] : []),
    ['sketch', 'Modifica il disegno', () => { clearSelection(); enterSketch(co.sketch); }],
    ...(co.eids?.length ? [['delete', 'Togli il taglio', () => togliDalTaglio(co.sketch, co.eids, 'il taglio')]] : [])], { chi: `taglio:${co.sketch}`, scritte: true });
  (co.campi || []).forEach((c, i) => quota(P.clone(), NUM(c.value), {
    etichetta: c.label, unita: c.kind === 'angle' || /°/.test(c.label) ? '°' : 'mm', num: c.value, dx: 96, dy: -46 + i * 30,
    scrivi: v => { schedaCalcola(true); inCoda(async () => { const r = await call('cut_contour_set', co.sketch, [{ ...c, value: v }]); if (await apply(r, r.message)) await refreshSel(); schedaCalcola(false); }); },
  }));
}
const NUM = v => virgola(Math.round(+v * 100) / 100);
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (e.target.closest?.('.quota, .q-scelte')) return;          // nel campo di una quota Esc annulla solo quello
  if (!$('#palette').hidden || !$('#home').hidden) return;      // palette o pagina iniziale aperte: Esc chiude quelle
  if (document.getElementById('mini-barra')) { e.stopPropagation(); clearSelection(); }
}, true);
// 28/10: l'errore che dice dove e come uscirne. Il punto si accende in rosso (se c'è), le soluzioni si applicano con un
// clic: la stessa chiamata di prima, coi valori corretti
function mostraErrore(r) {
  document.getElementById('err-card')?.remove();
  const ch = ultimaChiamata;
  const box = document.createElement('div');
  box.id = 'err-card';
  // il titolo è la frase del problema (senza «Non applicato:» davanti), il resto sotto; via il dato tra quadre per le soluzioni
  const msg = String(r.message || 'Non riuscito.').replace(/^Non applicato:\s*/, '').replace(/\s*\[foro Ø[^\]]*\]/, '');
  const cut = msg.search(/[:.]\s/);
  const tit = cut > 0 ? msg.slice(0, cut) : msg, resto = cut > 0 ? [msg.slice(cut + 1).trim()] : [];
  box.innerHTML = `<button class="ec-x" title="Chiudi">×</button><h5>${esc(tit)}</h5>${resto.length ? `<p>${esc(resto.join(' '))}</p>` : ''}
    <div class="ec-sol">${(r.soluzioni || []).map((s, i) => `<button class="btn${i ? '' : ' primary'}" data-i="${i}">${esc(s.testo)}${s.sotto ? `<small>${esc(s.sotto)}</small>` : ''}</button>`).join('')}
    ${r.evidenzia ? '<button class="btn" data-mostra>Mostrami il punto</button>' : ''}</div>`;
  document.body.appendChild(box);
  const accendi = () => {
    const o = objs.get('body');
    if (!o || !r.evidenzia) return;
    for (const f of o.data.faces || []) if ((f.name || '').startsWith(r.evidenzia)) faceOverlay(o, f.index, new THREE.Color(0xE5484D));
    ridisegna();
  };
  accendi();
  const via = () => { box.remove(); paint(); };
  box.querySelector('.ec-x').onclick = via;
  box.querySelector('[data-mostra]')?.addEventListener('click', () => { accendi(); });
  box.querySelectorAll('[data-i]').forEach(b => { b.onclick = () => {
    const s = r.soluzioni[+b.dataset.i];
    via();
    if (!ch) return;
    // la stessa chiamata, con i campi della soluzione al posto di quelli di prima (nei dizionari degli argomenti)
    const args = JSON.parse(JSON.stringify(ch[1])).map(a => a && typeof a === 'object' && !Array.isArray(a)
      && Object.keys(s.cambia).some(k => k in a) ? { ...a, ...s.cambia } : a);
    inCoda(async () => apply(await call(ch[0], ...args)));
  }; });
  clearTimeout(mostraErrore.t);
  mostraErrore.t = setTimeout(() => { if (document.getElementById('err-card') === box && !r.soluzioni?.length) via(); }, 9000);
}
// l'anteprima azzurra della flangia più lunga o più corta di dl, mentre tiri o scrivi la sua quota (senza ricalcolare)
const MAN = { g: null, e: null };
const MAN_FANT = new THREE.MeshBasicMaterial({ color: 0x5AA9FF, transparent: true, opacity: 0.28, depthTest: false, side: THREE.DoubleSide });
function fantasmaFlangia(dl) {
  const E = MAN.e;
  if (!E) return;
  const A2 = E.a.clone().addScaledVector(E.d, dl), B2 = E.b.clone().addScaledVector(E.d, dl);
  E.fant.geometry.dispose();
  E.fant.geometry = new THREE.BufferGeometry().setFromPoints([E.a, E.b, B2, E.a, B2, A2]);
  E.fant.visible = Math.abs(dl) > 1e-6;
  ridisegna();
}
function togliManiglie() {
  if (MAN.g) { MAN.g.traverse(o => o.geometry?.dispose()); scene.remove(MAN.g); MAN.g = null; }
  MAN.e = null; ridisegna();
}
function maniglieFlangia(s) {
  togliManiglie();
  const e = puntaDi(s);
  if (!e) return;
  const fant = new THREE.Mesh(new THREE.BufferGeometry(), MAN_FANT);
  fant.visible = false; fant.renderOrder = 30;
  const g = new THREE.Group();
  g.add(fant);
  scene.add(g);
  MAN.g = g; MAN.e = { a: v3(e.a), b: v3(e.b), d: v3(e.dir).normalize(), fant };
}
async function renderProps(s) {
  if (s.kind !== 'flange') togliManiglie();
  if (!TRAV && !DIVSCEGLI && !PUNTO) passoTubi(null);          // la barra dei tubi di prima (capo libero, Dividi…)
  latoAcceso(null);
  miniBarra(s);
  togliAnteprimaForo();
  selForo = null;
  const tab = rows => `<table class="grid">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
  const quanti = sel?.ids?.length > 1 && s.kind !== 'structure' ? ` <span class="spento" style="font-weight:400">e altre ${sel.ids.length - 1} uguali</span>` : '';
  let h = `<h3>${esc(s.title)}${quanti}</h3>${tab(s.rows)}`;
  if (!profili) profili = await call('profile_suggestions');
  if (s.kind === 'structure') { pannelloStruttura(s); return; }     // tubi e strutture: i pannelli stanno più giù
  if (s.kind === 'member') { pannelloTubo(s, quanti); return; }
  if (s.kind === 'structure' || (s.kind === 'body' && s.template)) {
    const t = s.template, idf = s.kind === 'structure' ? s.id : s.tpl_id;
    const forma = s.kind === 'body';
    if (forma) h += faceSketchButton(s);          // anche sulle facce delle tramogge si disegna (fori, tagli: 22/10)
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
  if (s.kind === 'accessorio') {         // clic su un piede o un tappo: il pannello per cambiarli tutti
    await pannelloPiedi(s.structure, s.cosa, `<h3>${esc(s.title)}</h3><section class="sezione t-misure">${tRighe(s.rows)}</section>`);
    return;
  } else if (s.kind === 'instance') {
    tieniScritto(() => { $('#props').innerHTML = instancePanel(s); wireInstance(s); });
    return;
  } else if (s.kind === 'assembly') {
    // 04/11 (regola 2): l'assieme intero, come il pannello del pezzo: cos'è, cosa puoi fare, ruota tutto, dettagli
    const riga = k => s.rows.find(r => r[0] === k)?.[1] || '0';
    const cmd = [['asm_insert', 'box', 'Inserisci pezzo'], ['asm_interf', 'section', 'Interferenze'], ['asm_esploso', 'explode', 'Vista esplosa'], ['drawings', 'export', 'Tavole PDF']];
    $('#props').innerHTML = `<div class="asm-pan"><div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">L’assieme intero: ${esc(riga('Pezzi'))} pezzi, ${esc(riga('Accoppiamenti'))} accoppiamenti</div></div></div>
      <section class="sezione"><h4>Cosa puoi fare</h4><div class="asm-azioni">${cmd.map(([c, ic, t]) => `<button class="btn" data-asm-cmd="${c}"><img src="icons/${ic}.svg" alt=""><span>${t}</span></button>`).join('')}</div></section>
      <section class="sezione"><h4>Ruota tutto di 90°</h4>
      <div class="seg asm-ruota"><button data-rotall="x">attorno a X</button><button data-rotall="y">attorno a Y</button><button data-rotall="z">attorno a Z</button></div>
      <p class="hint">Gira tutti i pezzi insieme: gli accoppiamenti restano come sono. Per guardarlo da un altro lato invece trascina col tasto sinistro.</p></section>
      <details class="fsec"><summary>Dettagli</summary><table class="grid">${s.rows.map(r => `<tr><td>${esc(r[0])}</td><td class="num">${esc(r[1])}</td></tr>`).join('')}</table></details></div>`;
    document.querySelectorAll('[data-asm-cmd]').forEach(b => { b.onclick = () => runCmd(b.dataset.asmCmd); });
    document.querySelectorAll('[data-rotall]').forEach(b => {
      b.onclick = () => inCoda(async () => { if (await apply(await call('asm_rotate_all', b.dataset.rotall, 90))) await refreshSel(); });
    });
    return;
  } else if (s.kind === 'mate') {
    tieniScritto(() => { $('#props').innerHTML = matePanel(s); wireMate(s); });
    return;
  } else if (s.kind === 'fold') {
    $('#props').innerHTML = foldPanel(s);
    wireFold(s);
    return;
  } else if (s.kind === 'endmiter') {
    pannelloTesta(s);
    return;
  } else if (s.kind === 'sidebend' || s.kind === 'edgeflange') {
    pannelloPiegaBordo(null, s);                    // con le azioni della sua faccia (ci si disegna sopra)
    return;
  } else if (s.kind === 'flange') {
    $('#props').innerHTML = flangePanel(s);
    wireFlange(s);
    maniglieFlangia(s);
    return;
  } else if (s.kind === 'body' && s.flange_form) {
    // 04/11 (regola 2): il lato della base cliccato: la flangia nuova, col pulsante blu in fondo
    $('#props').innerHTML = pannelloLam({ titolo: 'Flangia su questo lato', cose: esc(`${s.flange_form.label} di ${s.title}`),
      azioni: [azioneLam('pattern_rect', 'Piega anche altri bordi', 'data-cmd="flange_help"'),
        // sul fianco si disegna la sezione della lamiera a contorno
        s.face?.planar && s.face.name ? azioneLam('project', 'Disegna su questa faccia', `data-face-sketch="${esc(s.face.name)}"`, '', 'Per la lamiera a contorno: la sezione parte dallo spigolo') : ''],
      corpo: newFlangePanel(s.flange_form), dettagli: righeIt(s.rows.filter(r => r[0] !== 'Faccia')),
      fine: `<button class="btn primary big" id="f-add">Aggiungi flangia su ${esc(s.flange_form.label)}</button>` });
    wireNewFlange(s.flange_form);
    return;
  } else if (s.kind === 'node') {
    $('#props').innerHTML = nodePanel(s);
    wireNode(s);
    return;
  }
  selForo = s.kind === 'body' && s.foro?.sketch ? { sketch: s.foro.sketch, eids: [s.foro.cerchio], cosa: 'il foro' }
    : s.kind === 'body' && s.contorno?.eids?.length ? { sketch: s.contorno.sketch, eids: s.contorno.eids, cosa: 'il taglio' } : null;
  if (s.kind === 'body' && s.contorno) {
    $('#props').innerHTML = pannelloTaglio(s, quanti);
    wireContorno(s.contorno);
    return;
  } else if (s.kind === 'body' && s.foro) {
    $('#props').innerHTML = pannelloForo(s, quanti);
    wireForo(s.foro);
    return;
  } else if (s.kind === 'body') {
    // 04/11: la faccia cliccata (o il pezzo intero) col pannello in ordine: cos'è, cosa puoi fare, Dettagli chiusi
    let corpo = '', fine = '';
    if (s.step) {                          // pezzo da STEP: lo spessore di una lastra piana si cambia (28/10)
      corpo = s.step.pieghe ? `<p class="hint">Pezzo da STEP con ${s.step.pieghe} ${s.step.pieghe === 1 ? 'piega' : 'pieghe'}: lo spessore (${virgola(s.step.t)} mm) segue il file 3D.</p>`
        : `<div class="ff"><label>Spessore<span class="inp"><input class="field" id="st-sp" value="${esc(virgola(s.step.t))}"><i>mm</i></span></label><span></span></div>
           <p class="hint">La faccia di sotto (con i fori) resta dov’è: lo spessore cresce verso l’interno del pezzo.</p>`;
      if (!s.step.pieghe) fine = '<button class="btn primary big" id="st-ok">Cambia lo spessore</button>';
    }
    const lab = s.face?.label ? s.face.label.replace(/ di "[^"]*"$/, '') : '';
    const lamiera = !!S?.sheet?.data;
    h = s.face ? pannelloLam({ titolo: esc(maiuscola(lab) || 'Faccia') + quanti, cose: esc(`${s.face.planar ? 'faccia piana' : 'faccia curva'} di ${s.title}`),
      azioni: s.face.planar ? azioniFaccia(s) : [azioneLam('dimension', 'Misura', 'data-cmd="misura"')], corpo, fine,
      dettagli: righeIt(s.rows.filter(r => r[0] !== 'Faccia')) })
      : pannelloLam({ titolo: esc(s.title), cose: 'il pezzo intero', corpo, fine,
        azioni: [lamiera ? azioneLam('flat', 'Sviluppo', 'data-cmd="unfold"', '', 'Spiega o ripiega la lamiera (U)') : '', azioneLam('dimension', 'Misura', 'data-cmd="misura"'),
          lamiera ? azioneLam('library', 'Raggio e K della piega', 'data-azione="piegatrice"') : ''],
        dettagli: righeIt(s.rows) });
  }
  $('#props').innerHTML = h;
  if ($('#st-ok')) {
    const vai = () => inCoda(async () => apply(await call('step_spessore', $('#st-sp').value.trim())));
    $('#st-ok').onclick = vai;
    $('#st-sp').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
  }
}

// Il punto sul tubo col mouse (03/11): passando sul tubo compare la misura (da terra o dall'inizio, come nel campo),
// il clic la scrive nel campo e la si corregge scrivendo; un segnetto mostra dov'è
let PUNTO = null, puntoMesh = null;
function puntoMisura(p) {
  const m = PUNTO.mis;
  const q = PUNTO.vert ? p.z - m.z0 : (p.x - m.da[0]) * m.dir[0] + (p.y - m.da[1]) * m.dir[1] + (p.z - m.da[2]) * m.dir[2];
  return Math.max(1, Math.min(Math.round(q), Math.floor(PUNTO.vert ? m.da[2] - m.z0 + m.lunghezza : m.lunghezza) - 1));
}
function puntoSegno(q) {
  if (!PUNTO?.mis) return;
  const m = PUNTO.mis;
  const pos = PUNTO.vert ? [m.da[0], m.da[1], m.z0 + q] : m.da.map((c, i) => c + m.dir[i] * q);
  if (!puntoMesh) {
    puntoMesh = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: 0xFF6B1A, depthTest: false }));   // arancio dei tubi
    puntoMesh.renderOrder = 10;
    scene.add(puntoMesh);
  }
  const r = Math.max(4, (m.lunghezza || 500) / 80);
  puntoMesh.scale.set(r, r, r);
  puntoMesh.position.set(...pos);
  puntoMesh.visible = true;
  ridisegna();
}
function puntoVia() {
  if (PUNTO) { tip.style.display = 'none'; passoTubi(null); }
  PUNTO = null;
  if (puntoMesh) { scene.remove(puntoMesh); puntoMesh.geometry.dispose(); puntoMesh = null; ridisegna(); }
}
function puntoPreso(p) {
  const q = puntoMisura(p);
  puntoSegno(q);
  const f = $('#p-punto-q');
  f.value = virgola(q);
  f.focus(); f.select();
}

// Lavorazioni sul tubo (22/10): clic sulla faccia del tubo → sketch su quella faccia, come sulla lamiera
function facciaCliccata(n) {
  if (!n) return 'di sopra';
  if (n === 'davanti') return 'davanti';
  const [x, y, z] = n, m = Math.max(Math.abs(x), Math.abs(y), Math.abs(z));
  return m === Math.abs(z) ? (z > 0 ? 'di sopra' : 'di sotto') : m === Math.abs(y) ? (y < 0 ? 'davanti' : 'dietro') : (x > 0 ? 'a destra' : 'a sinistra');
}
function pannelloLavorazioni(s) {
  if (!s.lavorabile) return s.non_lavorabile ? `<p class="hint">${esc(s.non_lavorabile)}</p>` : '';
  const n = ultimoClic?.id === s.id ? ultimoClic.normal : (s.tubo?.verticale ? [0, -1, 0] : null);   // in piedi: davanti
  const fatte = (s.lavorazioni || []).map(l => `<tr><td>${esc(l.label)}${l.through ? ' (passante)' : ''}${l.members.length > 1 ? ` · ${l.members.length} tubi` : ''}</td>
    <td class="destra"><button class="btn" data-lav-sk="${esc(l.sketch)}">Modifica</button></td></tr>`).join('');
  return `<div class="sub">Lavorazioni sul tubo</div>
    ${fatte ? `<table class="grid">${fatte}</table>` : ''}
    <div class="row-btns"><button class="btn primary" id="p-lav">Disegna sulla faccia ${facciaCliccata(n)}</button></div>
    <p class="hint">Fori, asole, intagli: clicca nel 3D la faccia del tubo dove vanno, poi questo pulsante. Le misure partono dalla testa del tubo.</p>`;
}
function wireLavorazioni(s) {
  const b = $('#p-lav');
  if (b) b.onclick = () => inCoda(async () => {
    const n = ultimoClic?.id === s.id && ultimoClic.normal ? ultimoClic.normal : (s.tubo?.verticale ? [0, -1, 0] : [0, 0, 1]);
    const r = await call('sketch_on_tube', s.id, n);
    if (await apply(r)) await enterSketch(r.sketch);
  });
  document.querySelectorAll('[data-lav-sk]').forEach(x => { x.onclick = () => enterSketch(x.dataset.lavSk); });
}
function lavorazioneTuboDialog() {
  const sid = SK.sid;
  inCoda(async () => {
    const u = await call('tubo_uguali', sid);
    const uguali = u.ok ? u.uguali.length : 1;
    modal(`<h3>Lavorazione sul tubo</h3>
      <p class="hint">Il disegno buca la parete del tubo. Una sagoma che esce dal bordo o dalla testa diventa un intaglio.</p>
      <div class="form"><label class="tutta-riga">Nome<input class="field" id="lt-n" placeholder="es. Fori per le viti"></label></div>
      <label class="check"><input type="radio" name="lt-p" value="" checked> Solo questa parete</label>
      <label class="check"><input type="radio" name="lt-p" value="1"> Passante: anche la parete di fronte</label>
      ${uguali > 1 ? `<label class="check"><input type="checkbox" id="lt-u" checked> ${uguali - 1 === 1 ? 'Anche sull’altro tubo uguale' : `Anche sugli altri ${uguali - 1} tubi uguali`} (stessa misura, stessi tagli)</label>` : ''}
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fai la lavorazione</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const passante = !!document.querySelector('input[name="lt-p"]:checked')?.value, tutti = !!$('#lt-u')?.checked, nome = $('#lt-n').value.trim();
        close();
        inCoda(async () => { const r = await call('lavora_tubo', sid, passante, tutti, nome); if (await apply(r, r.message)) exitSketch(); });
      };
      conAnteprima('lavora_tubo', () => [sid, !!document.querySelector('input[name="lt-p"]:checked')?.value, !!$('#lt-u')?.checked, $('#lt-n').value.trim()]);
    });
  });
}

// Forma da sezioni (tramoggia): i pezzi con l'ingombro e, spigolo per spigolo, piega o saldatura
function formaPanel(f) {
  const pezzi = f.pezzi.map(p => `<tr><td><b>${esc(p.nome)}</b></td><td>${p.pieghe} pieghe</td><td>${num(p.ingombro[0], 0)} × ${num(p.ingombro[1], 0)}</td>
    <td>${p.nel_foglio ? '✓' : '<span class="testo-err">fuori foglio</span>'}</td></tr>`).join('');
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
// 04/11 (regola 2 dell'impaginazione): il pannello di destra sempre nello stesso ordine. In cima il titolo e cos'è;
// «Cosa puoi fare» con le azioni (pulsanti col nome); i campi del comando; «Dettagli» (peso, ingombro…) chiuso;
// in fondo, fermo, il pulsante principale blu (se c'è). Le azioni: [html del pulsante] già fatti, con i loro id.
function pannelloLam({ titolo, cose = '', azioni = [], corpo = '', dettagli = [], dettagliHtml = '', fine = '', testa = '' }) {
  const az = azioni.filter(Boolean);
  const righe = dettagli.filter(r => r && r[1] != null && r[1] !== '');
  return `<div class="fhead"${testa}><div><h3>${titolo}</h3>${cose ? `<div class="fsub">${cose}</div>` : ''}</div></div>`
    + (az.length ? `<section class="sezione cosa-fai"><h4>Cosa puoi fare</h4><div class="azioni">${az.join('')}</div></section>` : '')
    + (corpo ? `<div class="pl-corpo">${corpo}</div>` : '')
    + (righe.length || dettagliHtml ? `<details class="fsec dettagli"><summary>Dettagli</summary>${righe.length ? `<table class="grid">${righe.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>` : ''}${dettagliHtml}</details>` : '')
    + (fine ? `<div class="pl-fine">${fine}</div>` : '');
}
// un'azione del pannello: icona + nome (data: gli attributi che la fanno funzionare, es. data-azione="foro" o id="h-sk")
const azioneLam = (icona, nome, data, cls = '', titolo = '') =>
  `<button type="button" class="btn azione${cls ? ' ' + cls : ''}" ${data}${titolo ? ` title="${esc(titolo)}"` : ''}><img src="icons/${icona}.svg" alt="">${esc(nome)}</button>`;
// le azioni di una faccia piana della lamiera (le stesse della barretta, più quelle che non ci stanno)
function azioniFaccia(s) {
  if (!s.face?.planar || !s.face.name) return [];
  return [azioneLam('hole', 'Foro', 'data-azione="foro"'), azioneLam('slot', 'Asola', 'data-azione="asola"'),
    azioneLam('project', 'Disegna su questa faccia', `data-face-sketch="${esc(s.face.name)}"`),
    azioneLam('cut', 'Taglio', 'data-azione="taglia"'), azioneLam('dimension', 'Misura', 'data-cmd="misura"')];
}
// i numeri dei Dettagli con la virgola (l'area arrivava «98784.0 mm²»)
const righeIt = rows => (rows || []).map(([k, v]) => [k, typeof v === 'string' ? v.replace(/(\d)\.(\d)/g, '$1,$2') : v]);
const maiuscola = t => (t ? t[0].toUpperCase() + t.slice(1) : t);
// ------------------------------------------------------------- un foro cliccato sul pezzo: semplice, svasato, filettato
// Come in ogni CAD: clic sulla parete del foro, a destra il tipo. Vale per il cerchio che l'ha fatto (e, se vuoi, per
// tutti i fori uguali dello stesso disegno).
const FILETTI_M = ['M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M16'];
// il taglio cliccato sul pezzo (rettangolo, raccordi, contorno): le sue misure, da cambiare lì (22/10)
function pannelloContorno(co) {
  const righe = co.campi.map((c, i) => `<label>${esc(c.label)}<span class="inp"><input class="field" data-ci="${i}" value="${esc(virgola(Math.round(c.value * 100) / 100))}"><i>${c.kind === 'angle' || /°/.test(c.label) ? '°' : 'mm'}</i></span></label>`).join('');
  if (co.rapido) return '<p class="hint">Fatte col comando Foro: si cambiano dalla stessa finestra (misure, al centro / agli angoli / in fila, distanze dai bordi).</p>';
  return `<div class="ff">${righe}</div>
    <p class="hint">Cambia le misure e premi Applica: il taglio si rifà. La posizione è dall’origine del disegno (l’angolo del pezzo su cui hai disegnato).</p>`;
}
// 04/11 (regola 2): il taglio cliccato. Cosa puoi fare (sposta, disegno, togli), le misure, Dettagli, «Applica» in fondo
function pannelloTaglio(s, quanti = '') {
  const co = s.contorno;
  return pannelloLam({ titolo: esc(s.title) + quanti, cose: 'taglio nella lamiera',
    azioni: [co.rapido ? azioneLam('move', 'Sposta o cambia…', 'id="co-cambia"', '', 'Riapre la finestra: misure, al centro / agli angoli / in fila, distanze dai bordi') : '',
      azioneLam('sketch', 'Modifica il disegno', 'id="co-sk"'),
      co.eids?.length ? azioneLam('delete', 'Togli questo taglio', 'id="co-togli"', 'danger', 'Toglie questo taglio dal suo disegno (Canc); gli altri restano') : ''],
    corpo: pannelloContorno(co), dettagli: righeIt(s.rows.filter(r => r[0] !== 'Faccia')),
    fine: co.rapido ? '' : '<button class="btn primary big" id="co-ok">Applica</button>' });
}
function wireContorno(co) {
  const vai = () => {
    const cambiati = [];
    document.querySelectorAll('[data-ci]').forEach(inp => {
      const c = co.campi[+inp.dataset.ci], v = parseFloat(inp.value.trim().replace(',', '.'));
      if (Number.isFinite(v) && Math.abs(v - c.value) > 1e-6) cambiati.push({ ...c, value: inp.value.trim() });
      else if (!Number.isFinite(v)) cambiati.push({ ...c, value: inp.value.trim() });     // il servizio dice cosa non va
    });
    if (!cambiati.length) { toast('Nessuna misura cambiata.'); return; }
    inCoda(async () => { const r = await call('cut_contour_set', co.sketch, cambiati); await apply(r, r.message); });
  };
  if (co.rapido) $('#co-cambia').onclick = () => cambiaFori(co.feature);
  else $('#co-ok').onclick = vai;
  document.querySelectorAll('[data-ci]').forEach(inp => { inp.onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  $('#co-sk').onclick = () => { clearSelection(); enterSketch(co.sketch); };
  if ($('#co-togli')) $('#co-togli').onclick = () => togliDalTaglio(co.sketch, co.eids, 'il taglio');
}
// 28/10: il foro (o il taglio) cliccato sul pezzo si toglie da lì: dal disegno del suo taglio; se era l'unico
// contorno, il taglio intero (con la conferma di sempre)
function togliDalTaglio(sid, eids, cosa) {
  if (!sid || !eids?.length) return;
  clearSelection();
  provaSulPezzo({ metodo: 'togli_dal_taglio', argomenti: () => [sid, eids], togli: true, conferma: `Togli ${cosa}`,
    accetta: r => r.code === 'ultimo',                  // era l'unico contorno: va via tutto il taglio (lo dice la barra)
    frase: r => (r?.code === 'ultimo' ? `Toglie ${cosa} e il suo taglio (era l’unico contorno)` : r?.frase || `Toglie ${cosa}: la lamiera torna piena`),
    // 03/11: una conferma sola. Quello che sparisce insieme al taglio lo dice già questa barra (prima, dopo la barra,
    // si apriva anche la finestra «Elimina»)
    sotto: r => (r?.code === 'ultimo' && r.dipendenti?.length ? `Spariscono anche: ${r.dipendenti.join(', ')} · si annulla con Ctrl+Z`
      : 'Lo sviluppo torna senza quel contorno · si annulla con Ctrl+Z'),
    fai: () => inCoda(async () => {
      const r = await call('togli_dal_taglio', sid, eids);
      if (!r.ok && r.code === 'ultimo') {
        const r2 = await call('tree_action', 'feature', r.feature, 'elimina');
        await apply(r2, r2.ok ? `Tolto ${cosa} e il suo taglio. Annulla (Ctrl+Z) lo rimette.` : undefined);
        return;
      }
      await apply(r, r.message);
    }) });
}
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
    <div class="ff" id="h-dia-w"${tipo === 'filettato' || tipo === 'inserto' ? ' hidden' : ''}><label>Diametro del foro<span class="inp"><input class="field" id="h-d" value="${esc(virgola(Math.round(fo.d * 100) / 100))}"><i>mm</i></span></label><span></span></div>
    <div class="fo-scelta" id="h-tipo">${[['semplice', 'Semplice'], ['svasato', 'Svasato'], ['filettato', 'Filettato'], ['inserto', 'Inserto']]
      .map(([k, l]) => `<button type="button" data-k="${k}" class="${tipo === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    <div id="h-sva"${tipo === 'svasato' ? '' : ' hidden'}>${sv}</div><div id="h-fil"${tipo === 'filettato' ? '' : ' hidden'}>${fi}</div>
    <div id="h-ins"${tipo === 'inserto' ? '' : ' hidden'}>${ins}</div>
    ${n > 1 ? `<label class="check"><input type="checkbox" id="h-tutti" checked> anche gli altri ${n - 1} fori Ø${esc(virgola(Math.round(fo.d * 100) / 100))} ${fo.importato ? 'su questa faccia' : 'di questo disegno'}</label>` : ''}</div>`;
}
// 04/11 (regola 2): il foro cliccato. Cos'è, cosa puoi fare (sposta, disegno, vite, togli), il tipo e le misure,
// Dettagli chiusi, «Applica» in fondo
function pannelloForo(s, quanti = '') {
  const fo = s.foro, n = fo.uguali.length;
  return pannelloLam({ titolo: esc(s.title) + quanti, cose: esc(n > 1 ? `${n} fori uguali ${fo.importato ? 'su questa faccia' : 'nello stesso disegno'}` : 'foro nella lamiera'),
    azioni: [fo.cambiabile ? azioneLam('move', `Sposta o cambia ${n > 1 ? 'questi fori' : 'il foro'}…`, 'id="h-cambia"', '', 'Riapre la finestra del Foro: diametro, al centro / agli angoli / in fila, distanze dai bordi') : '',
      azioneLam('sketch', 'Modifica il disegno', 'id="h-sk"', '', 'Apre il disegno del foro: lo sposti, cambi le quote, ne aggiungi altri'),
      azioneLam('fastener', 'Metti una vite in questo foro…', 'id="h-vite"', '', 'Salva il pezzo, apre un assieme e ci mette la vite in questo foro'),
      azioneLam('delete', 'Togli questo foro', 'id="h-togli"', 'danger', 'Toglie questo foro dal disegno del suo taglio (Canc); gli altri restano')],
    corpo: foroPanel(fo), dettagli: righeIt(s.rows), fine: '<button class="btn primary big" id="h-ok">Applica</button>' });
}
// anteprima della svasatura sul pezzo mentre scrivi: il cono com'è, rosso se va più giù dello spessore (21/10)
const anteprimaForo = new THREE.Group();
scene.add(anteprimaForo);
const SVA_OK = new THREE.MeshBasicMaterial({ color: 0xFFB21A, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthTest: false });
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
    testo.style.color = 'var(--c-err-testo)'; return;
  }
  const h = (D - fo.d) / 2 / Math.tan(ang * Math.PI / 360), t = fo.spessore;
  const troppo = t != null && h > t + 1e-6;
  testo.textContent = `Profonda ${virgola(Math.round(h * 100) / 100)} mm` + (t != null ? (troppo ? ` · più dello spessore (${virgola(t)}): riduci il Ø o apri l’angolo` : ` su ${virgola(t)} di spessore`) : '');
  testo.style.color = troppo ? 'var(--c-err-testo)' : '';
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
    <div class="form">${nomeServe ? `<label class="tutta-riga">Nome del pezzo (si salva in Documenti/SteelCAD)<input class="field" id="vp-n" value="${esc(S?.name || 'Pezzo')}"></label>` : ''}
      <label class="tutta-riga">Cosa<select class="field" id="vp-t">${viti.map(([k, c]) => `<option value="${k}"${k === (sva ? 'vite_tspei' : 'vite_tcei') ? ' selected' : ''}>${esc(c.nome)}</option>`).join('')}</select></label>
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
    $('#h-dia-w').hidden = tipo === 'filettato' || tipo === 'inserto';
    vedi();
  }; });
  ['#h-D', '#h-ang'].forEach(q => { $(q).oninput = vedi; });
  if ($('#h-tutti')) $('#h-tutti').onchange = vedi;
  vedi();
  // un foro del pezzo da STEP (28/10): non ha un disegno da aprire; «Applica» gli mette sotto il suo cerchio
  if (fo.importato) {
    $('#h-sk').hidden = true; $('#h-togli').hidden = true;
  } else {
    $('#h-sk').onclick = () => { clearSelection(); enterSketch(fo.sketch); };
    if ($('#h-cambia')) $('#h-cambia').onclick = () => cambiaFori(fo.feature || fo.sketch);
    $('#h-togli').onclick = () => togliDalTaglio(fo.sketch, [fo.cerchio], 'il foro');
  }
  const vai = () => {
    const spec = tipo === 'svasato' ? { tipo, D: $('#h-D').value.trim(), angolo: $('#h-ang').value.trim() }
      : tipo === 'filettato' ? { tipo, M: $('#h-M').value }
      : tipo === 'inserto' ? { tipo, codice: $('#h-cod').value.trim(), D: $('#h-Di').value.trim() } : null;
    const cerchi = $('#h-tutti')?.checked ? fo.uguali : [fo.cerchio];
    const nuovo = parseFloat($('#h-d').value.trim().replace(',', '.'));
    const cambia = !$('#h-dia-w').hidden && Number.isFinite(nuovo) && Math.abs(nuovo - fo.d) > 1e-6;
    if (fo.importato) {
      if (!spec && !cambia) { toast('È già un foro semplice.'); return; }
      inCoda(async () => { await apply(await call('hole_adopt', fo.faccia, cerchi.map(k => fo.centri[k]), cambia ? nuovo : fo.d, spec)); });
      return;
    }
    inCoda(async () => {
      // prima il diametro (la svasatura si controlla col foro nuovo), poi il tipo
      if (cambia && !await apply(await call('sketch_hole_diameter', fo.sketch, cerchi, $('#h-d').value.trim()))) return;
      await apply(await call('sketch_hole_type', fo.sketch, cerchi, spec));
    });
  };
  $('#h-ok').onclick = vai;
  $('#h-d').onkeydown = ev => { if (ev.key === 'Enter') vai(); };
}

// ------------------------------------------------------------- comando «Foro» e «Asola» diretti sul pezzo (03/11)
// Clic su una faccia → «Foro» (o «Foro» nella barra in alto): una finestra piccola di lato con il diametro (o
// larghezza × altezza dell'asola) e dove vanno: uno al centro, 4 agli angoli a tot dai bordi, in fila, o dove clicchi.
// Le distanze sono dal fuori tutto del pezzo (anche sulla faccia piegata: dal bordo esterno). Anteprima sul pezzo
// mentre scrivi; «Fatto» fa il taglio vero (sketch su faccia + taglio), così sviluppo, DXF e tavole restano giusti.
let FORO = null;
let ultimoForo = { tipo: 'tondo', d: '10', larg: '30', alt: '10', disposizione: 'centro', bordo: '20', bordo_y: '', diversa: false,
  n: '4', passo: '40', verso: 'x', lato: 'mezzo', dal: '30', punti: [] };
function facciaPerForo() {
  const facce = objs.get('body')?.data?.faces || [];
  const scelta = sel?.id === 'body' && sel.face != null ? facce.find(x => x.index === sel.face && x.name && x.planar !== false) : null;
  return scelta?.name || null;
}
// modifica (03/11): {feature, spec, info} da fori_da_modificare: la stessa finestra, con com'erano i fori fatti
async function foroDialog(tipo = 'tondo', face = null, modifica = null) {
  if (SK) { toast('Stai disegnando: nel disegno il foro è il Cerchio. Per il comando Foro sul pezzo, prima «Esci».', 'err'); return; }
  if (!objs.get('body')) { toast('I fori si fanno su una lamiera o su una piastra: prima crea il pezzo.', 'err'); return; }
  const info = modifica ? modifica.info : await call('fori_info', face || facciaPerForo());
  if (!info.ok) { toast(info.message || 'Qui non si possono fare fori: clicca una faccia piana del pezzo.', 'err'); return; }
  nascondiMini();
  const testo = x => (x == null ? '' : typeof x === 'number' ? virgola(x) : String(x));
  const v = modifica ? { ...ultimoForo, ...Object.fromEntries(Object.entries(modifica.spec).map(([k, x]) => [k, k === 'punti' ? x.map(p => p.map(testo)) : testo(x)])) }
    : { ...ultimoForo, tipo, punti: [], disposizione: ultimoForo.perTipo?.[tipo] || 'centro' };
  if (modifica) { v.punti = v.punti || []; v.diversa = modifica.spec.bordo_y != null && modifica.spec.bordo_y !== ''; if (!v.lato) v.lato = 'mezzo'; }
  FORO = { face: info.face, info, v, modifica: modifica?.feature || null };
  const nomeFaccia = s => (s || '').replace(/ di "[^"]*"$/, '');
  const num = x => String(x ?? '').trim();
  const seg = (k, o) => `<div class="seg" data-fo-seg="${k}">${o.map(([id, l]) => `<button type="button" data-v="${id}" class="${String(v[k]) === id ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  const riga = (l, id, val, unita = 'mm', extra = '') => `<label class="ft-riga"><span>${l}</span><span class="ft-mm"><input class="field" id="fo-${id}" value="${esc(virgola(val))}" autocomplete="off"><i>${unita}</i>${extra}</span></label>`;
  const dove = () => {
    const d = v.disposizione;
    if (d === 'angoli') return riga(v.diversa ? 'Dai bordi destro e sinistro' : 'Dai bordi', 'bordo', v.bordo)
      + (v.diversa ? riga('Dai bordi davanti e dietro', 'bordo_y', v.bordo_y || v.bordo) : '')
      + `<label class="ft-check"><input type="checkbox" id="fo-diversa"${v.diversa ? ' checked' : ''}> Misura diversa davanti e dietro</label>`;
    if (d === 'fila') return riga('Quanti', 'n', v.n, '') + riga('Uno ogni (passo)', 'passo', v.passo)
      + `<div class="ft-riga"><span>La fila va</span>${seg('verso', [['x', '↔ in orizzontale'], ['y', '↕ in verticale']])}</div>`
      + `<div class="ft-riga"><span>Messa</span>${seg('lato', v.verso === 'x' ? [['mezzo', 'in mezzo'], ['davanti', 'dal bordo davanti'], ['dietro', 'dal bordo dietro']]
        : [['mezzo', 'in mezzo'], ['sinistra', 'dal bordo sinistro'], ['destra', 'dal bordo destro']])}</div>`
      + (v.lato !== 'mezzo' ? riga('A', 'dal', v.dal) : '');
    if (d === 'punti') return `<p class="hint">Clicca sul pezzo dove va ${v.tipo === 'asola' ? 'l’asola' : 'il foro'} (anche più volte). Le misure si correggono qui sotto.</p>`
      + (v.punti.length ? v.punti.map((p, i) => `<div class="ft-riga fo-punto"><span>${v.punti.length > 1 ? `n. ${i + 1}: ` : ''}dal bordo sinistro / davanti</span><span class="ft-mm">
        <input class="field" data-px="${i}" value="${esc(virgola(p[0]))}"><i>/</i><input class="field" data-py="${i}" value="${esc(virgola(p[1]))}"><i>mm</i>
        <button type="button" class="link danger" data-pvia="${i}" title="Togli questo">×</button></span></div>`).join('') : '');
    return '';
  };
  const misure = () => (v.tipo === 'asola'
    ? riga('Larghezza', 'larg', v.larg) + riga('Altezza', 'alt', v.alt)
    : riga('Diametro', 'd', v.d));
  const corpo = () => `<div class="ft-form">
      <div class="ft-riga"><span>Cosa</span>${seg('tipo', [['tondo', 'Foro tondo'], ['asola', 'Asola']])}</div>
      ${misure()}
      <div class="ft-riga"><span>Dove</span>${seg('disposizione', [['centro', 'Uno al centro'], ['angoli', '4 agli angoli'], ['fila', 'In fila'], ['punti', 'Dove clicco']])}</div>
      ${dove()}</div>`;
  const spec = () => {
    const s = { tipo: v.tipo, disposizione: v.disposizione };
    if (v.tipo === 'asola') { s.larg = num(v.larg); s.alt = num(v.alt); } else s.d = num(v.d);
    if (v.disposizione === 'angoli') { s.bordo = num(v.bordo); if (v.diversa) s.bordo_y = num(v.bordo_y || v.bordo); }
    if (v.disposizione === 'fila') { s.n = num(v.n); s.passo = num(v.passo); s.verso = v.verso; s.lato = v.lato; if (v.lato !== 'mezzo') s.dal = num(v.dal); }
    if (v.disposizione === 'punti') s.punti = v.punti.map(p => [num(p[0]), num(p[1])]);
    return s;
  };
  modal(`<div id="fo-tutto"><h3 id="fo-tit"></h3>
    <p class="hint" id="fo-sotto"></p>
    <div id="fo-corpo">${corpo()}</div>
    <p class="fo-frase" id="fo-frase"></p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fatto</button></div></div>`, close => {
    const cornice = $('#modal-box'), box = $('#fo-tutto');      // gli ascoltatori sul contenuto: la cornice resta per le altre finestre
    const titolo = () => {
      $('#fo-tit').textContent = `${FORO.modifica ? 'Cambia ' + (v.tipo === 'asola' ? 'le asole' : 'i fori') : v.tipo === 'asola' ? 'Asola' : 'Foro'} su: ${nomeFaccia(FORO.info.label)}`;
      $('#fo-sotto').textContent = `Misure dal fuori tutto del pezzo (${virgola(Math.round(FORO.info.outer[0] * 10) / 10)} × ${virgola(Math.round(FORO.info.outer[1] * 10) / 10)}), anche dal lato della piega.`
        + (FORO.modifica ? ' Quelli di adesso vengono tolti e messi così.' : ' Clic su un’altra faccia per cambiarla.');
    };
    // 04/11: il pulsante dice cosa fa («Fai i 4 fori», «Fai l’asola»), non «Fatto»
    const nomeOk = () => {
      const q = v.disposizione === 'angoli' ? 4 : v.disposizione === 'fila' ? Math.max(0, parseInt(v.n, 10) || 0) : v.disposizione === 'punti' ? v.punti.length : 1;
      const cosa = v.tipo === 'asola' ? (q > 1 ? `le ${q} asole` : 'l’asola') : (q > 1 ? `i ${q} fori` : 'il foro');
      $('#m-ok').textContent = `${FORO.modifica ? 'Cambia' : 'Fai'} ${cosa}`;
    };
    const vai = () => anteprima(FORO.modifica ? 'fori_modifica' : 'fori_guidati', () => [FORO.modifica || FORO.face, spec()], box.querySelector('.ant-stato'), {
      frase: true, dopo: r => { $('#fo-frase').textContent = r.ok ? (r.frase || '') : ''; },
    });
    const ridisegna = (fuoco) => {
      $('#fo-corpo').innerHTML = corpo();
      titolo(); nomeOk();
      const i = fuoco && box.querySelector(fuoco);
      if (i) { i.focus(); i.select?.(); } else if (!box.contains(document.activeElement)) { cornice.tabIndex = -1; cornice.focus(); }   // Invio = Fatto anche dopo un clic
      vai();
    };
    FORO.ridisegna = ridisegna;
    FORO.vai = vai;
    titolo(); nomeOk();
    box.addEventListener('input', ev => {
      const t = ev.target;
      if (t.dataset.px != null) v.punti[+t.dataset.px][0] = t.value;
      else if (t.dataset.py != null) v.punti[+t.dataset.py][1] = t.value;
      else if (t.id?.startsWith('fo-') && t.type !== 'checkbox') v[t.id.slice(3)] = t.value;
      nomeOk(); vai();
    });
    box.addEventListener('change', ev => {
      if (ev.target.id === 'fo-diversa') { v.diversa = ev.target.checked; ridisegna(v.diversa ? '#fo-bordo_y' : '#fo-bordo'); }
    });
    box.addEventListener('click', ev => {
      const b = ev.target.closest('[data-fo-seg] button');
      if (b) {
        const k = b.closest('[data-fo-seg]').dataset.foSeg;
        v[k] = b.dataset.v;
        if (k === 'verso') v.lato = 'mezzo';
        const fuoco = { tipo: v.tipo === 'asola' ? '#fo-larg' : '#fo-d', disposizione: { angoli: '#fo-bordo', fila: '#fo-n' }[v.disposizione], lato: '#fo-dal' }[k];
        ridisegna(fuoco);
        return;
      }
      const x = ev.target.closest('[data-pvia]');
      if (x) { v.punti.splice(+x.dataset.pvia, 1); ridisegna(); }
    });
    const chiudi = () => { FORO = null; close(); };
    $('#m-no').onclick = chiudi;
    $('#m-ok').onclick = () => {
      const s = spec(), face = FORO.face, cambia = FORO.modifica;
      if (v.disposizione === 'punti' && !v.punti.length) { toast('Clicca sul pezzo dove va il foro.', 'err'); return; }
      // 04/11 (percorso B): la disposizione si ricorda per tipo: dopo «4 agli angoli» per i fori l'asola non propone 4 asole
      ultimoForo = { ...v, punti: [], perTipo: { ...ultimoForo.perTipo, [v.tipo]: v.disposizione } };
      chiudi();
      inCoda(async () => { const r = cambia ? await call('fori_modifica', cambia, s) : await call('fori_guidati', face, s); await apply(r, r.message); });
    };
    cornice.onkeydown = ev => { if (ev.key === 'Enter' && !$('#m-ok').disabled) { ev.preventDefault(); $('#m-ok').click(); } if (ev.key === 'Escape') chiudi(); };
    $('#modal').classList.add('laterale');
    let st = document.createElement('div'); st.className = 'ant-stato'; box.querySelector('.acts').before(st);
    anteprimaSpazio();
    const primo = box.querySelector(v.tipo === 'asola' ? '#fo-larg' : '#fo-d');
    primo?.focus(); primo?.select();
    vai();
  });
}
// clic su un foro fatto → «Sposta o cambia…»: la finestra del Foro con com'erano (03/11)
function cambiaFori(fid) {
  inCoda(async () => {
    const r = await call('fori_da_modificare', fid);
    if (!r.ok) { toast(r.message, 'err'); return; }
    clearSelection();
    await foroDialog(r.spec.tipo, r.face, r);
  });
}
// ------------------------------------------------------------- «Piega» su più bordi in un colpo (03/11)
// La vaschetta: «Piega» nella barra, clic sui 4 bordi (o «Tutti i bordi»), altezza 30, Fatto. Negli angoli tra due
// bordi piegati: aperti (scantonati, con lo scarico) o chiusi (il lato lungo copre il corto, col gioco). Anteprima
// sul pezzo mentre scegli; un Annulla toglie tutte le pieghe.
let PIEGA = null;
let ultimePieghe = { length: '30', angle: '90', direction: 'up', angoli: 'aperti', gioco: '0,5' };
function nomeBordo(e) {
  const base = (e.label || '').replace(/ \(.*$/, ''), mm = (e.label || '').match(/\(([^)]*)\)/)?.[1] || '';
  if (e.kind === 'tip') return `${base}${mm ? ' (' + mm + ')' : ''}`;
  return `bordo ${LATI[base] || base}${mm ? ' (' + mm + ')' : ''}`;
}
function pieghePiuBordi(primo = null) {
  if (SK) { toast('Stai disegnando: prima «Esci».', 'err'); return; }
  if (!S?.sheet?.data) { toast('Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', 'err'); return; }
  if (flatView) toggleFlat(false);
  if (!bendEdges.some(e => e.kind === 'edge' || e.kind === 'tip')) { toast('Su questo pezzo non ci sono bordi da piegare così: clicca il bordo che vuoi piegare.', 'err'); return; }
  clearSelection(); nascondiMini();
  const v = { ...ultimePieghe };
  PIEGA = { bordi: primo && (primo.kind === 'edge' || primo.kind === 'tip') ? [primo] : [], v };
  const seg = (k, o) => `<div class="seg" data-pg-seg="${k}">${o.map(([id, l]) => `<button type="button" data-v="${id}" class="${String(v[k]) === id ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  const riga = (l, id, val, unita = 'mm') => `<label class="ft-riga"><span>${l}</span><span class="ft-mm"><input class="field" id="pg-${id}" value="${esc(virgola(val))}" autocomplete="off"><i>${unita}</i></span></label>`;
  const lati = () => PIEGA.bordi.filter(e => e.kind === 'edge').length;
  const corpo = () => `<div class="ft-form">
      <div class="ft-riga"><span>Bordi</span><span class="pg-bordi">${PIEGA.bordi.length ? PIEGA.bordi.map((e, i) => `<span class="pg-bordo">${esc(nomeBordo(e))}<button type="button" class="link danger" data-pvia="${i}" title="Non piegare questo bordo">×</button></span>`).join('')
        : '<i class="hint">nessuno: clicca i bordi sul pezzo</i>'}</span></div>
      <div class="ft-riga"><span></span><span><button type="button" class="btn" id="pg-tutti">Tutti i bordi del contorno</button></span></div>
      ${riga('Altezza (fuori tutto)', 'length', v.length)}
      ${riga('Angolo', 'angle', v.angle, '°')}
      <div class="ft-riga"><span>Verso</span>${seg('direction', [['up', 'In su'], ['down', 'In giù']])}</div>
      ${lati() > 1 ? `<div class="ft-riga"><span>Negli angoli</span>${seg('angoli', [['aperti', 'Aperti (scantonati)'], ['chiusi', 'Chiusi']])}</div>`
        + (v.angoli === 'chiusi' ? riga('Gioco nell’angolo', 'gioco', v.gioco) + '<p class="hint">Il lato lungo resta intero e copre quello corto; il gioco è lo spazio per la saldatura.</p>' : '') : ''}</div>`;
  const args = () => [PIEGA.bordi[0]?.feature || S.sheet.feature, PIEGA.bordi.map(e => ({ kind: e.kind, ref: e.ref })),
    { length: v.length, angle: v.angle, direction: v.direction }, lati() > 1 ? v.angoli : 'aperti', v.gioco];
  modal(`<div id="pg-tutto"><h3>Piega i bordi</h3>
    <p class="hint">Clicca sul pezzo i bordi da piegare: si accendono in giallo. Un altro clic lo toglie. Tutte le pieghe vengono uguali.</p>
    <div id="pg-corpo">${corpo()}</div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Piega i bordi</button></div></div>`, close => {
    const cornice = $('#modal-box'), box = $('#pg-tutto');
    const vai = () => {
      paint();
      const st = box.querySelector('.ant-stato');
      if (!PIEGA.bordi.length) {
        anteprimaVia();
        if (st) { st.className = 'ant-stato'; st.textContent = 'Clicca i bordi da piegare.'; }
        confermaAccesa(st, false);
        return;
      }
      anteprima('piega_bordi', args, st);
    };
    const ridisegna = fuoco => {
      $('#pg-corpo').innerHTML = corpo();
      const i = fuoco && box.querySelector(fuoco);
      if (i) { i.focus(); i.select?.(); } else if (!box.contains(document.activeElement)) { cornice.tabIndex = -1; cornice.focus(); }
      vai();
    };
    PIEGA.ridisegna = ridisegna;
    box.addEventListener('input', ev => { const t = ev.target; if (t.id?.startsWith('pg-')) { v[t.id.slice(3)] = t.value; vai(); } });
    box.addEventListener('click', ev => {
      const b = ev.target.closest('[data-pg-seg] button');
      if (b) { v[b.closest('[data-pg-seg]').dataset.pgSeg] = b.dataset.v; ridisegna(b.dataset.v === 'chiusi' ? '#pg-gioco' : null); return; }
      const x = ev.target.closest('[data-pvia]');
      if (x) { PIEGA.bordi.splice(+x.dataset.pvia, 1); ridisegna(); return; }
      if (ev.target.closest('#pg-tutti')) {
        const tutti = bendEdges.filter(e => e.kind === 'edge');
        if (!tutti.length) { toast('I bordi del contorno sono già tutti piegati: clicca le punte delle pieghe.'); return; }
        PIEGA.bordi = [...PIEGA.bordi.filter(e => e.kind !== 'edge'), ...tutti];
        ridisegna('#pg-length');
      }
    });
    const chiudi = () => { PIEGA = null; close(); paint(); };
    $('#m-no').onclick = chiudi;
    $('#m-ok').onclick = () => {
      if (!PIEGA.bordi.length) { toast('Clicca almeno un bordo da piegare.', 'err'); return; }
      const a = args();
      ultimePieghe = { ...v };
      chiudi();
      inCoda(async () => { const r = await call('piega_bordi', ...a); await apply(r, r.message); });
    };
    cornice.onkeydown = ev => { if (ev.key === 'Enter' && !$('#m-ok').disabled) { ev.preventDefault(); $('#m-ok').click(); } if (ev.key === 'Escape') chiudi(); };
    $('#modal').classList.add('laterale');
    const st = document.createElement('div'); st.className = 'ant-stato'; box.querySelector('.acts').before(st);
    anteprimaSpazio();
    const primoCampo = box.querySelector('#pg-length'); primoCampo?.focus(); primoCampo?.select();
    vai();
  });
}
// con la finestra «Piega i bordi» aperta: il bordo sotto il mouse si accende, il clic lo mette o lo toglie
function piegaMove(ev) {
  const vis = model.visible; model.visible = true;
  const he = pickEdge(ev);
  model.visible = vis;
  const buono = he && (he.kind === 'edge' || he.kind === 'tip') ? he : null;
  if (buono !== hoverEdge) { hoverEdge = buono; paint(); }
  if (!buono) { tip.style.display = 'none'; return; }
  const dentro = PIEGA.bordi.some(e => e.id === buono.id);
  tip.textContent = `${nomeBordo(buono)} · clic: ${dentro ? 'non piegarlo' : 'piega anche questo'}`;
  const r = view.getBoundingClientRect();
  tip.style.left = (ev.clientX - r.left + 14) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px';
  tip.style.display = 'block';
}
function piegaClic(ev) {
  const vis = model.visible; model.visible = true;
  const he = pickEdge(ev);
  model.visible = vis;
  if (!he) return;
  if (he.kind !== 'edge' && he.kind !== 'tip') { toast('Questo bordo si piega da solo: chiudi la finestra e cliccalo.'); return; }
  const i = PIEGA.bordi.findIndex(e => e.id === he.id);
  if (i >= 0) PIEGA.bordi.splice(i, 1); else PIEGA.bordi.push(he);
  PIEGA.ridisegna();
}
// ------------------------------------------------------------- «Angoli tondi» sullo sviluppo (03/11)
// Raggio o smusso sugli spigoli vivi del contorno dello sviluppo (le punte che pungono): tutti, o solo quelli
// cliccati (i cerchi sugli angoli). Si guarda sullo sviluppo: in azzurro come verrà, in arancio le punte che vanno
// via. Diventa un taglio sullo sviluppo, che torna nel pezzo piegato e va nel DXF.
let ANGOLI = null;
let ultimiAngoli = { tipo: 'raggio', valore: '5' };
async function angoliSviluppo() {
  if (SK) { toast('Stai disegnando: prima «Esci».', 'err'); return; }
  if (!S?.sheet?.data) { toast('Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', 'err'); return; }
  const info = await call('angoli_sviluppo_info', S.sheet.feature);
  if (!info.ok) { toast(info.message, 'err'); return; }
  if (!info.angoli.length) { toast('Lo sviluppo non ha spigoli vivi: gli angoli sono già tondi o verso dentro.'); return; }
  clearSelection(); nascondiMini();
  if (!flatView) await toggleFlat(true);
  const v = { ...ultimiAngoli, quali: 'tutti' };
  ANGOLI = { info, v, scelti: new Set() };
  const seg = (k, o) => `<div class="seg" data-ag-seg="${k}">${o.map(([id, l]) => `<button type="button" data-v="${id}" class="${String(v[k]) === id ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  const n = info.angoli.length;
  const corpo = () => `<div class="ft-form">
      <div class="ft-riga"><span>Come</span>${seg('tipo', [['raggio', 'Arrotondati (raggio)'], ['smusso', 'Smussati a 45°']])}</div>
      <label class="ft-riga"><span>${v.tipo === 'raggio' ? 'Raggio' : 'Smusso'}</span><span class="ft-mm"><input class="field" id="ag-valore" value="${esc(virgola(v.valore))}" autocomplete="off"><i>mm</i></span></label>
      <div class="ft-riga"><span>Quali</span>${seg('quali', [['tutti', `Tutti gli spigoli vivi (${n})`], ['scelti', 'Solo quelli che clicco']])}</div>
      ${v.quali === 'scelti' ? `<p class="hint">${ANGOLI.scelti.size ? `Scelti ${ANGOLI.scelti.size} di ${n}.` : 'Nessuno scelto.'} Clicca i cerchi sugli angoli dello sviluppo.</p>` : ''}</div>`;
  const args = () => [S.sheet.feature, v.tipo, v.valore, v.quali === 'tutti' ? null : [...ANGOLI.scelti].map(i => info.angoli[i].xy)];
  const segni = () => {
    togliQuote();
    info.angoli.forEach((a, i) => {
      const el = document.createElement('div');
      const acceso = v.quali === 'tutti' || ANGOLI.scelti.has(i);
      el.className = 'q-anello ag-angolo' + (acceso ? ' scelto' : '');
      el.title = acceso && v.quali === 'scelti' ? 'Clic: lascia questo angolo vivo' : 'Clic: arrotonda questo angolo';
      el.onclick = () => {
        if (v.quali === 'tutti') { v.quali = 'scelti'; ANGOLI.scelti = new Set(info.angoli.map((_, k) => k)); }
        if (ANGOLI.scelti.has(i)) ANGOLI.scelti.delete(i); else ANGOLI.scelti.add(i);
        ANGOLI.ridisegna();
      };
      document.body.appendChild(el);
      QUOTE.push({ el, p: v3(a.xyz), dx: 0, dy: 0 });
    });
    placeBarra();
  };
  modal(`<div id="ag-tutto"><h3>Angoli dello sviluppo</h3>
    <p class="hint">Gli spigoli vivi del contorno (quelli che pungono) arrotondati o smussati in un colpo. Si vede sullo sviluppo: in arancio quello che va via.</p>
    <div id="ag-corpo">${corpo()}</div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fai gli angoli</button></div></div>`, close => {
    const cornice = $('#modal-box'), box = $('#ag-tutto');
    const vai = () => {
      const st = box.querySelector('.ant-stato');
      if (v.quali === 'scelti' && !ANGOLI.scelti.size) {
        anteprimaVia();
        if (st) { st.className = 'ant-stato'; st.textContent = 'Clicca gli angoli da arrotondare.'; }
        confermaAccesa(st, false);
        return;
      }
      anteprima('angoli_sviluppo', args, st);
    };
    const ridisegna = fuoco => {
      $('#ag-corpo').innerHTML = corpo();
      segni();
      const i = fuoco && box.querySelector(fuoco);
      if (i) { i.focus(); i.select?.(); } else if (!box.contains(document.activeElement)) { cornice.tabIndex = -1; cornice.focus(); }
      vai();
    };
    ANGOLI.ridisegna = ridisegna;
    box.addEventListener('input', ev => { if (ev.target.id === 'ag-valore') { v.valore = ev.target.value; vai(); } });
    box.addEventListener('click', ev => {
      const b = ev.target.closest('[data-ag-seg] button');
      if (!b) return;
      const k = b.closest('[data-ag-seg]').dataset.agSeg;
      v[k] = b.dataset.v;
      if (k === 'quali' && v.quali === 'scelti' && !ANGOLI.scelti.size) ANGOLI.scelti = new Set();
      ridisegna(k === 'tipo' ? '#ag-valore' : null);
    });
    const chiudi = () => { ANGOLI = null; togliQuote(); close(); };
    $('#m-no').onclick = chiudi;
    $('#m-ok').onclick = () => {
      const a = args();
      ultimiAngoli = { tipo: v.tipo, valore: v.valore };
      chiudi();
      inCoda(async () => { const r = await call('angoli_sviluppo', ...a); if (await apply(r, r.message) && flatView) buildFlat(); });
    };
    cornice.onkeydown = ev => { if (ev.key === 'Enter' && !$('#m-ok').disabled) { ev.preventDefault(); $('#m-ok').click(); } if (ev.key === 'Escape') chiudi(); };
    $('#modal').classList.add('laterale');
    const st = document.createElement('div'); st.className = 'ant-stato'; box.querySelector('.acts').before(st);
    anteprimaSpazio();
    segni();
    const primo = box.querySelector('#ag-valore'); primo?.focus(); primo?.select();
    vai();
  });
}
// ------------------------------------------------------------- «Incastri» dalla barra (03/11)
// Linguette sulla punta di una piega che entrano in asole sulla parete dove appoggia (scatole chiuse, U, cassoni):
// prima si trovavano solo aprendo la piega giusta nel pannello. Qui: quale piega, quante, larghe quanto, gioco;
// anteprima sul pezzo; Fatto. Negli assiemi restano nel pannello della lamiera che appoggia.
let ultimiIncastri = { n: '3', w: '15', c: '0,2', s: '0' };
async function incastriDialog() {
  if (SK) { toast('Stai disegnando: prima «Esci».', 'err'); return; }
  if (S?.mode === 'assembly') { toast('Nell’assieme: clicca la lamiera che appoggia con la punta sull’altra; nel pannello a destra c’è «Incastri con …».'); return; }
  if (!S?.sheet?.data) { toast('Prima serve una lamiera piegata.', 'err'); return; }
  const r = await call('incastri_possibili');
  if (!r.ok) { toast(r.message, 'err'); return; }
  if (!r.pieghe.length) {
    toast('Gli incastri si fanno dove la punta di una piega appoggia su un’altra parete del pezzo (una scatola chiusa, una U ripiegata). Qui nessuna piega appoggia: piega anche la punta fino a toccare.', 'err', null, 9000);
    return;
  }
  if (flatView) await toggleFlat(false);
  clearSelection(); nascondiMini();
  const v = { ...ultimiIncastri, quale: 0 };
  const P = r.pieghe;
  const corto = s => String(s || '').replace(/ di "[^"]*"$/, '');
  const riga = (l, id, unita = 'mm') => `<label class="ft-riga"><span>${l}</span><span class="ft-mm"><input class="field" id="in-${id}" value="${esc(virgola(v[id]))}" autocomplete="off"><i>${unita}</i></span></label>`;
  const corpo = () => {
    const p = P[v.quale];
    return `<div class="ft-form">
      ${P.length > 1 ? `<div class="ft-riga"><span>Quale piega</span><div class="seg" data-in-quale>${P.map((x, i) => `<button type="button" data-v="${i}" class="${i === v.quale ? 'on' : ''}">${esc(x.nome)}</button>`).join('')}</div></div>`
        : `<div class="ft-riga"><span>Piega</span><b>${esc(p.nome)}</b></div>`}
      <p class="hint">La punta appoggia su ${esc(corto(p.contro))} (lunga ${esc(virgola(p.lunga))} mm): le linguette sulla punta entrano nelle asole di quella faccia.${p.fatti ? ' Su questa piega gli incastri ci sono già.' : ''}</p>
      ${riga('Quante linguette', 'n', '')}
      ${riga('Larghezza', 'w')}
      ${riga('Gioco nell’asola', 'c')}
      ${riga('Sporgenza oltre', 's')}</div>`;
  };
  const args = () => { const p = P[v.quale]; return [p.feature, p.flange, v.n, v.w, v.c, v.s]; };
  modal(`<div id="in-tutto"><h3>Incastri linguetta e asola</h3>
    <p class="hint">Per tenere insieme la scatola prima di saldare: le asole sono più larghe della linguetta del gioco, per lato.</p>
    <div id="in-corpo">${corpo()}</div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Fai gli incastri</button></div></div>`, close => {
    const cornice = $('#modal-box'), box = $('#in-tutto');
    const vai = () => anteprima('auto_tabs', args, box.querySelector('.ant-stato'), { vista: 'iso' });
    box.addEventListener('input', ev => { const t = ev.target; if (t.id?.startsWith('in-')) { v[t.id.slice(3)] = t.value; vai(); } });
    box.addEventListener('click', ev => {
      const b = ev.target.closest('[data-in-quale] button');
      if (!b) return;
      v.quale = +b.dataset.v;
      $('#in-corpo').innerHTML = corpo();
      vai();
    });
    const chiudi = () => { close(); };
    $('#m-no').onclick = chiudi;
    $('#m-ok').onclick = () => {
      const a = args();
      ultimiIncastri = { n: v.n, w: v.w, c: v.c, s: v.s };
      chiudi();
      inCoda(async () => { const x = await call('auto_tabs', ...a); await apply(x, x.message); });
    };
    cornice.onkeydown = ev => { if (ev.key === 'Enter' && !$('#m-ok').disabled) { ev.preventDefault(); $('#m-ok').click(); } if (ev.key === 'Escape') chiudi(); };
    $('#modal').classList.add('laterale');
    const st = document.createElement('div'); st.className = 'ant-stato'; box.querySelector('.acts').before(st);
    anteprimaSpazio();
    const primo = box.querySelector('#in-n'); primo?.focus(); primo?.select();
    vai();
  });
}
// con la finestra del foro aperta: niente bordi da piegare sotto il mouse, solo cosa fa il clic
function foroMove(ev) {
  if (hoverEdge) { hoverEdge = null; paint(); }
  const vis = model.visible;
  model.visible = true;
  const h = pick(ev);
  model.visible = vis;
  const f = h?.id === 'body' && h.face != null ? objs.get('body').data.faces.find(x => x.index === h.face) : null;
  if (!f?.name) { tip.style.display = 'none'; return; }
  tip.textContent = f.name === FORO.face ? (FORO.v.disposizione === 'punti' ? `Clic: ${FORO.v.tipo === 'asola' ? 'l’asola' : 'il foro'} va qui` : 'La faccia dei fori')
    : `Clic: ${FORO.v.tipo === 'asola' ? 'l’asola' : 'il foro'} su ${(f.label || 'questa faccia').replace(/ di "[^"]*"$/, '')}`;
  const r = view.getBoundingClientRect();
  tip.style.left = (ev.clientX - r.left + 14) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px';
  tip.style.display = 'block';
}
// con la finestra del foro aperta, il clic sul pezzo: «Dove clicco» mette un foro lì; se no cambia la faccia
async function foroClic(ev) {
  const vis = model.visible;
  model.visible = true;                     // durante l'anteprima il pezzo vero è nascosto, ma si clicca lui
  const h = pick(ev);
  model.visible = vis;
  if (!h || h.id !== 'body' || h.face == null) return;
  const f = objs.get('body').data.faces.find(x => x.index === h.face);
  if (!f?.name) return;
  if (FORO.v.disposizione === 'punti' && f.name === FORO.face) {
    const r = await call('fori_dove', f.name, h.point.toArray());
    if (!r.ok) { toast(r.message, 'err'); return; }
    FORO.v.punti.push([String(r.x), String(r.y)]);
    FORO.ridisegna();
    return;
  }
  if (f.name === FORO.face) return;
  if (FORO.modifica) { toast('Stai cambiando i fori di questa faccia: per farne su un’altra, «Fatto» e poi «Foro».'); return; }
  const info = await call('fori_info', f.name);
  if (!info.ok) { toast('Su questa faccia non si fanno fori: scegline una piana.', 'err'); return; }
  FORO.face = info.face; FORO.info = info; FORO.v.punti = [];
  FORO.ridisegna();
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
  if (sel?.id === 'body' && selForo) { const x = selForo; selForo = null; togliDalTaglio(x.sketch, x.eids, x.cosa); return; }
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
// 04/11 (percorso B): il bordo si chiama come nell'albero («davanti»), non come nello sketch («lato sotto»)
function latoOfficina(l) { return String(l || '').replace(/^lato (sotto|sopra|destro|sinistro)(?![a-z])/, m => LATI[m] || m); }
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
  return `<p class="hint">${esc(ff.label)}: lunghezza dallo spigolo esterno alla punta.</p>
    ${flangeFields(ultimaFlangia, VERSI_UI, POS_UI)}`;
}
function wireNewFlange(ff) {
  const vai = () => {
    ultimaFlangia = readFlange();
    const prima = selGen;
    inCoda(async () => { const r = await call('add_flange', ff.feature, ff.edge, ultimaFlangia); if (await apply(r) && selGen === prima) await select(r.select); });
  };
  $('#f-add').onclick = vai;
  ['#f-len', '#f-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  anteprimaPannello('add_flange', () => [ff.feature, ff.edge, readFlange()]);
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
      b.onmouseenter = () => anteprima('set_tip_corners', () => [a.feature, b.dataset.k], null);   // 29/10: si vede prima di scegliere
      b.onmouseleave = () => anteprimaVia();
    });
  });
}
async function refreshSel() { if (sel) await select(sel.id, sel.face, sel.ids, true, sel.nome); }

// il nome della piega, uguale sulla barretta, nel pannello e (come lato) nell'albero: «Piega davanti», «Orlo»…
function titoloFlangia(s) {
  const lato = (s.rows || []).find(r => r[0] === 'Lato')?.[1] || '';
  if (s.parent) return Math.abs(+s.def?.angle) >= 170 ? 'Orlo' : 'Piega sulla punta';
  return lato ? `Piega ${LATI[lato] || lato}` : s.title;
}
// 04/11 (ritocchi): nel pannello le pieghe si chiamano come nell'albero («la piega davanti»), mai con la sigla FL3
function nomePiegaAlbero(feature, flid) {
  let trovato = '';
  const giu = n => { if (trovato || !n) return; if (n.kind === 'flange' && n.ref === `${feature}/${flid}`) trovato = n.label || ''; (n.children || []).forEach(giu); };
  [].concat(S?.tree || []).forEach(giu);
  const nome = trovato.replace(/\s+\d+(?:[.,]\d+)?°?(?:\s+(?:su|giù))?$/, '').trim()
    .replace(/^Piega su (piega .+)$/i, 'bordo sulla $1');     // piega sulla punta di un'altra: «bordo sulla piega a destra»
  return nome ? nome.charAt(0).toLowerCase() + nome.slice(1) : 'l’altra piega';
}
// e nei nomi dei bordi che vengono dal motore: «punta di FL1» → «punta della piega davanti»
const pieghePerNome = (label, feature) => String(label || '').replace(/punta di (FL\d+)/g, (m, id) => 'punta della ' + nomePiegaAlbero(feature, id))
  .replace(/FL\d+/g, id => nomePiegaAlbero(feature, id));
function flangePanel(s) {
  const riga = k => (s.rows.find(r => r[0] === k) || [])[1];
  const np = flid => nomePiegaAlbero(s.feature, flid);
  const questa = 'questa piega';
  const angoli = [];
  if (s.tip_corners) angoli.push(`<label class="lbl">Con ${esc(s.tip_corners.others.map(np).join(', '))} <span class="hint">(vale per tutti i bordi)</span>
    <select class="field" id="f-tipc">${opts(s.tip_corners.modes, s.tip_corners.mode)}</select></label>`);
  for (const c of s.corners) angoli.push(`<div class="corner" data-other="${esc(c.other)}">
      <label class="lbl">Con ${esc(np(c.other))}<select class="field" data-corner>
        <option value="open"${c.mode === 'open' ? ' selected' : ''}>aperto</option>
        <option value="over"${c.mode === 'over' ? ' selected' : ''}>chiuso, ${questa} copre ${esc(np(c.other))}</option>
        <option value="under"${c.mode === 'under' ? ' selected' : ''}>chiuso, ${esc(np(c.other))} copre ${questa}</option></select></label>
      <label class="lbl"${c.mode === 'open' ? ' hidden' : ''}>Fessura (mm, 0 = a contatto)<input class="field" data-cgap value="${esc(String(c.gap).replace('.', ','))}"></label></div>`);
  const sezAngoli = angoli.length ? `<details class="fsec"${s.tip_corners || s.corners.some(c => c.mode !== 'open') ? ' open' : ''}><summary>Angoli</summary>
    ${angoli.join('')}
    <label class="lbl">Fessura d’angolo (mm)<input class="field" id="f-gap" value="${esc(String(s.def.gap ?? 0).replace('.', ','))}"></label></details>` : '';
  const sezLinguetta = s.can_extend ? `<div class="fnote">Sulla punta della ${esc(np(s.parent))} c’è una linguetta: questa piega può continuare sopra di lei.
    <button class="btn" id="f-ext">Prolunga sopra la linguetta</button></div>` : '';
  const sezPunta = s.tip_child ? '' : `<details class="fsec"${s.tip_form ? ' open' : ''} id="f-punta"><summary>Piega sulla punta</summary>
    <p class="hint">Una flangia sul bordo libero di questa piega: bordo di scatola, omega, Z…</p>
    ${flangeFields(ultimaPunta, VERSI_PUNTA, POS_UI, 't')}
    <div class="row-btns"><button class="btn" id="t-add">Aggiungi sulla punta</button>
      <button class="btn" id="t-orlo" title="Risvolto a 180° (orlo): la parete resta lunga fino al bordo esterno della piega">Orlo 180°</button>
      <button class="btn" id="t-gradino" title="Gradino (joggle): la parete si sposta di poco e continua parallela, per sovrapporre due lamiere a filo">Gradino…</button></div></details>`;
  const sezIncastri = s.tip_contact ? `<details class="fsec" open id="f-incastri"><summary>Incastri sulla punta</summary>
    <p class="hint">La punta di questa piega appoggia su ${esc(/^FL\d+$/.test(s.tip_contact) ? np(s.tip_contact) : s.tip_contact)}: linguette sulla punta e asole sull’altra faccia.</p>
    <div class="ff"><label>Quante<span class="inp"><input class="field" id="i-n" value="3"></span></label>
      <label>Larghezza<span class="inp"><input class="field" id="i-w" value="15"><i>mm</i></span></label>
      <label>Gioco<span class="inp"><input class="field" id="i-c" value="0,2"><i>mm</i></span></label>
      <label>Sporgenza<span class="inp"><input class="field" id="i-s" value="0"><i>mm</i></span></label></div>
    <div class="row-btns"><button class="btn" id="i-add">Crea gli incastri</button></div></details>` : '';
  const dati = s.rows.filter(r => !['Lato', 'Piegata sulla punta di'].includes(r[0]));
  const titolo = titoloFlangia(s);
  const sotto = s.parent ? `sulla ${np(s.parent)}` : (riga('Larghezza') ? `bordo da ${riga('Larghezza')}` : '');
  // 04/11 (regola 2): cos'è, cosa puoi fare, quanto è alta / angolo / verso / misura, le sezioni che si aprono,
  // Dettagli chiusi, «Fatto» in fondo
  const faccia = azioniFaccia(s).slice(0, 3);
  return pannelloLam({ titolo: esc(titolo), cose: esc(sotto), testa: ` data-flangia="${esc(s.flange)}"`,
    azioni: [s.tip_child ? '' : azioneLam('flange', 'Piega sulla punta', 'data-apri="f-punta"', '', 'Una piega sul bordo libero: bordo di scatola, omega, Z, orlo'),
      ...faccia, azioneLam('delete', 'Togli questa piega', 'id="f-del"', 'danger', 'Canc')],
    corpo: `${flangeFields(s.def, s.parent ? VERSI_PUNTA : (s.directions?.up ? VERSI_UI : s.directions), POS_UI)}${sezLinguetta}${sezAngoli}${sezIncastri}${sezPunta}`,
    dettagliHtml: rigaPiega(righeIt(dati)), fine: '<button class="btn primary big" id="f-fatto">Fatto</button>' });
}
// un'azione che apre una sezione del pannello (es. «Piega sulla punta»): la apre e ci va
document.addEventListener('click', ev => {
  const b = ev.target.closest('#props [data-apri]');
  if (!b) return;
  const d = document.getElementById(b.dataset.apri);
  if (!d) return;
  d.open = true;
  d.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  d.querySelector('input')?.focus();
});
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
  asse: { nome: 'Foro su foro', clic: ['il foro del pezzo che sta fermo', 'il foro dell’altro pezzo (poi ti propongo la vite)'], val: 0 },
  distanza: { nome: 'Distanza', clic: ['una faccia del pezzo che sta fermo', 'la faccia dell’altro pezzo'], val: null },
  angolo: { nome: 'Angolo', clic: ['una faccia del pezzo che sta fermo', 'una faccia dell’altro pezzo'], val: null },
  tangente: { nome: 'Tangente', clic: ['la faccia (o il tubo) del pezzo che sta fermo', 'il tubo (o la faccia) dell’altro pezzo'], val: 0 },
  parallelo: { nome: 'Parallele', clic: ['una faccia (o un tubo) del pezzo che sta fermo', 'una faccia (o un tubo) dell’altro pezzo'], val: 0 },
  perpendicolare: { nome: 'Perpendicolari', clic: ['una faccia (o un tubo) del pezzo che sta fermo', 'una faccia (o un tubo) dell’altro pezzo'], val: 0 },
  centra: { nome: 'In mezzo', clic: ['un lato del pezzo che sta fermo', 'il lato di fronte, sullo stesso pezzo', 'un lato del pezzo da mettere in mezzo', 'il suo lato di fronte'], val: 0 },
  blocca: { nome: 'Blocca', clic: ['il pezzo che sta fermo', 'il pezzo da bloccare'], val: 0 },
  spigolo: { nome: 'Spigolo su spigolo', clic: ['uno spigolo dritto del pezzo che sta fermo', 'lo spigolo dell’altro pezzo'], val: 0, spigoli: [true, true] },
  spigolo_faccia: { nome: 'Spigolo su faccia', clic: ['la faccia del pezzo che sta fermo', 'lo spigolo dritto dell’altro pezzo'], val: 0, spigoli: [false, true] },
  cono: { nome: 'Cono su cono', clic: ['la svasatura del foro', 'la testa conica della vite'], val: 0 },
  vano: { nome: 'Metti nel vano', clic: ['il pannello da mettere', 'il telaio, vicino al vano dove va'], val: 0 },
  appoggia: { nome: 'Appoggia', clic: ['una faccia del pezzo da mettere (va bene quella che vedi)', 'la faccia del pezzo fermo, dove appoggiarlo'], val: 0 },
  testa: { nome: 'Testa a testa', clic: ['la faccia a 45° del pezzo che sta fermo', 'la faccia a 45° dell’altro pezzo (la stessa parete)'], val: null },
};
function asmHelp() {
  const u = MATE_UI[ASM.tool], k = ASM.clic.length;
  const su = t => t.replace(/^la /, 'sulla ').replace(/^il /, 'sul ').replace(/^lo /, 'sullo ').replace(/^l’/, 'sull’').replace(/^(?!sul)/, 'su ');
  // 04/11 (regola 4): una riga sola; sotto, piccolo, quale pezzo hai già scelto (dopo un giro della vista non si vedeva più)
  const scelti = [...new Set(ASM.clic.map(c => objs.get(c.inst)?.data.name).filter(Boolean))];
  setHelp(`${u.nome} (${k + 1} di ${u.clic.length}): ${k ? 'ora ' : ''}clic ${su(u.clic[k])}${scelti.length ? ` · Scelto «${scelti.join('» e «')}»` : ''} · Esc annulla`);
}
function asmTool(t) {
  if (t && !ASM.tool && sel) clearSelection();     // la barretta del pezzo scelto copriva proprio le facce da cliccare
  ASM.tool = t; ASM.clic = [];
  document.querySelectorAll('[data-asm-tool]').forEach(b => b.classList.toggle('on', b.dataset.asmTool === t));
  if (t) asmHelp(); else setHelp('');
  if (!SK) $('#sk-foot').hidden = !t;                // il suggerimento in basso, anche fuori dal disegno
  if (typeof passoAssieme === 'function' && S) passoAssieme();   // la riga «metti i pezzi al loro posto» lascia il posto
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
    <div class="form"><label>Fattore K (il tuo, della piegatrice)<input class="field" id="st-k" value="${esc(String(k).replace('.', ','))}"></label></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Scegli il file STEP…</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const kk = $('#st-k').value.trim(); close();
      inCoda(async () => {
        const r = await call('import_step_dialog', kk);
        if (r.cancelled) return;
        if (r.code === 'assieme') { stepPezzi(r); return; }
        primaVolta = true; clearSelection();
        if (await apply(r, r.message)) hideHome();
      });
    };
  }, { stretta: true });
}
// 28/10: lo STEP del cliente è un assieme: l'elenco dei pezzi, apri quello che serve o i DXF di tutte le lamiere
window.__stepPezzi = r => stepPezzi(r);              // per le prove automatiche
function stepPezzi(r) {
  const mm = v => String(v).replace('.', ',');
  const righe = r.pezzi.map(x => `<tr><td>${x.i + 1}</td><td>${x.misure.map(mm).join(' × ')}</td>
      <td>${x.lamiera ? `sp. ${mm(x.spessore)} · ${x.pieghe} ${x.pieghe === 1 ? 'piega' : 'pieghe'}` : `<span class="hint">${esc(x.perche || 'non è una lamiera')}</span>`}</td>
      <td><button class="btn" data-sp="${x.i}">Apri</button></td></tr>`).join('');
  const lam = r.pezzi.filter(x => x.lamiera).length;
  modal(`<h3>Lo STEP ha ${r.pezzi.length} pezzi</h3>
    <p class="hint">«Apri come assieme»: ogni pezzo diventa un file (le lamiere con lo sviluppo) in una cartella accanto allo STEP, e l’assieme si apre con i pezzi al loro posto. Oppure apri un pezzo solo, o fai subito il DXF di sviluppo di tutte le lamiere (${lam}), con il K ${mm(r.k)}.</p>
    <div class="tab-scroll"><table class="grid"><tr><th>N.</th><th>Misure (mm)</th><th>Lamiera</th><th></th></tr>${righe}</table></div>
    <div class="acts"><button class="btn" id="m-no">Chiudi</button>${lam ? `<button class="btn" id="sp-tutti">DXF di tutte le lamiere…</button>` : ''}<button class="btn primary" id="sp-asm">Apri come assieme</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#sp-asm').onclick = () => { close(); inCoda(async () => {
      const x = await call('step_assieme', r.path, r.k);
      primaVolta = true; clearSelection();
      if (await apply(x, x.message)) hideHome();
    }); };
    document.querySelectorAll('[data-sp]').forEach(b => { b.onclick = () => { close(); inCoda(async () => {
      const x = await call('import_step', r.path, r.k, +b.dataset.sp);
      primaVolta = true; clearSelection();
      if (await apply(x, x.message)) hideHome();
    }); }; });
    if ($('#sp-tutti')) $('#sp-tutti').onclick = () => { close(); inCoda(async () => {
      const x = await call('step_dxf_tutti', r.path, r.k);
      if (x.cancelled) return;
      toast(x.message, x.ok ? '' : 'err');
    }); };
  });
}
async function viteriaDialog() {
  if (S?.mode !== 'assembly') { toast('La viteria si mette negli assiemi.', 'err'); return; }
  const r = await call('libreria_catalogo');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const cat = r.catalogo, foro = sel?.id && sel.face != null && objs.get(sel.id)?.data.kind === 'instance' ? { inst: sel.id, face: sel.face } : null;
  const opz = (lst, v) => lst.map(x => `<option${String(x) === String(v) ? ' selected' : ''}>${esc(String(x))}</option>`).join('');
  let ultimo = viteriaDialog.ultimo || { tipo: 'vite_tcei', misura: 'M6', L: 20 };
  if (foro) {                                          // (03/11) la misura giusta per il foro cliccato e il pacco
    const vv = camera.position.clone().sub(controls.target).normalize();
    const pr = await call('asm_vite_proposta', foro, [vv.x, vv.y, vv.z]);
    if (pr?.ok) ultimo = { ...ultimo, tipo: ultimo.tipo === 'vite_tspei' ? 'vite_tspei' : pr.proposta.tipo, misura: pr.proposta.misura, L: pr.proposta.L };
  }
  // 04/11 (regola 2): la viteria nel pannello a destra, come Vite nei fori (prima una finestra in mezzo, sopra il pezzo)
  viteriaChiudi();
  const el = document.createElement('div');
  el.id = 'viteria-pan'; el.className = 'pannello-cmd';
  el.innerHTML = `<div class="pc-testa"><h3>Viteria</h3><p>Viti, dadi, rondelle e rivetti dalle norme ISO: il pezzo si fa la prima volta e poi si riusa. In distinta va tra gli acquisti</p></div>
    <div class="pc-corpo">
    <section class="sezione"><h4>Cosa</h4><select class="field" id="vt-t" aria-label="Cosa">${Object.entries(cat).map(([k, c]) => `<option value="${k}"${k === ultimo.tipo ? ' selected' : ''}>${esc(c.nome)}</option>`).join('')}</select>
      <div class="ff"><label>Misura<select class="field" id="vt-m"></select></label><label id="vt-lw">Lunghezza<select class="field" id="vt-l"></select></label></div></section>
    <section class="sezione"><h4>Dove</h4>
    ${foro ? `<label class="interruttore"><input type="checkbox" id="vt-f" checked><i></i>Nel foro che hai cliccato</label>
      <label class="interruttore" id="vt-tutti-w" hidden><input type="checkbox" id="vt-tutti" checked><i></i><span id="vt-tutti-t">Anche negli altri fori uguali del pezzo</span></label>
      <label class="interruttore"><input type="checkbox" id="vt-app" checked><i></i>Appoggiata sotto la testa (dal lato che guardi)</label>`
      : `<div class="ff"><label>Quante<span class="inp"><input class="field num" id="vt-n" value="${esc(String(ultimo.n || 1))}"></span></label><span></span></div>
      <p class="hint">Per metterle nei fori: clicca prima un foro del pezzo, poi «Viteria»: le metto in quel foro e, se vuoi, in tutti i fori uguali.</p>`}</section></div>
    <div class="pc-fondo"><button class="btn" id="vt-no">Annulla <kbd>Esc</kbd></button><button class="btn primary big" id="vt-ok">Inserisci</button></div>`;
  document.body.appendChild(el);
  VIT.el = el;
  const close = viteriaChiudi;
  {
    if (foro) call('asm_fori_uguali', foro.inst, foro.face).then(x => {      // quanti fori uguali ha il pezzo
      if (!x?.ok || x.n < 2 || !$('#vt-tutti-w')) return;
      $('#vt-tutti-w').hidden = false;
      $('#vt-tutti-t').textContent = `In tutti i ${x.n} fori uguali del pezzo (una vite per foro)`;
      $('#vt-ok').textContent = `Inserisci (${x.n})`;
      $('#vt-tutti').onchange = () => { $('#vt-ok').textContent = $('#vt-tutti').checked ? `Inserisci (${x.n})` : 'Inserisci'; };
    });
    const rifai = () => {
      const c = cat[$('#vt-t').value];
      $('#vt-m').innerHTML = opz(c.misure, c.misure.includes(ultimo.misura) ? ultimo.misura : c.misure[Math.floor(c.misure.length / 2)]);
      $('#vt-l').innerHTML = opz(c.lunghezze, c.lunghezze.includes(+ultimo.L) ? ultimo.L : c.lunghezze[Math.floor(c.lunghezze.length / 3)]);
      $('#vt-lw').hidden = !c.lunghezze.length;
    };
    $('#vt-t').onchange = rifai; rifai();
    $('#vt-no').onclick = close;
    VIT.ok = $('#vt-ok').onclick = () => {
      const tipo = $('#vt-t').value, misura = $('#vt-m').value, L = cat[tipo].lunghezze.length ? +$('#vt-l').value : null;
      const n = $('#vt-n') ? $('#vt-n').value.trim() : 1;
      viteriaDialog.ultimo = { tipo, misura, L: L || ultimo.L, n };
      const dove = $('#vt-f')?.checked ? foro : null;
      const verso = camera.position.clone().sub(controls.target).normalize();
      const opz = { tutti: !!dove && !$('#vt-tutti-w')?.hidden && $('#vt-tutti')?.checked, quante: dove ? 1 : n,
        appoggia: !!$('#vt-app')?.checked, verso: [verso.x, verso.y, verso.z] };
      close();
      inCoda(async () => { const r2 = await call('asm_insert_viteria', tipo, misura, L, dove, opz); if (await apply(r2, r2.message) && r2.select) await select(r2.select); });
    };
  }
}
const VIT = { el: null, ok: null };
function viteriaChiudi() { VIT.el?.remove(); VIT.el = null; VIT.ok = null; }
window.addEventListener('keydown', e => {
  if (!VIT.el || e.target.closest?.('input:not([type=checkbox]), textarea')) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); viteriaChiudi(); }
  else if (e.key === 'Enter' && !e.target.closest?.('select')) { e.preventDefault(); e.stopImmediatePropagation(); VIT.ok?.(); }
}, true);
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
  if (ASM.tool === 'appoggia') { appoggiaClick(ev); return; }
  if (ASM.tool === 'vano') { vanoClick(ev); return; }
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
    if (ASM.tool === 'asse') c.pt = [h.point.x, h.point.y, h.point.z];   // anche cliccando vicino al foro (è piccolo)
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
  if (tipo === 'asse') { viteFori(a, b); return; }    // foro su foro: la vite già proposta, Invio e c'è
  inCoda(async () => {
    const r = await call('asm_add_mate', tipo, a, b, u.val, false, a2, b2, true);
    if (await apply(r, 'Accoppiato.') && r.select) {
      await select(r.select);
      // a pannello pronto (04/11: si aspetta che ci sia; con 60 ms fissi, la prima volta il pannello arrivava dopo)
      if (u.val === null) { const t0 = performance.now(); const fuoco = () => { const c = $('#m-off') || $('#m-ang');
        if (c && c.offsetParent) { c.focus(); c.select(); } else if (performance.now() - t0 < 3000) setTimeout(fuoco, 40); }; setTimeout(fuoco, 40); }
    }
  });
}
// ===================================================================== In fila: lo stesso pezzo più volte (03/11)
// «la stessa staffa × 4»: quante in tutto, a che passo (o distribuite tra la prima e l'ultima) e da che parte; le
// copie si vedono subito, trasparenti; Invio le mette (bloccate all'originale: la fila lo segue).
const RIP = { el: null, id: null, ghost: new THREE.Group(), t: null };
scene.add(RIP.ghost);
const RIP_MAT = new THREE.MeshBasicMaterial({ color: 0x5B9BFF, transparent: true, opacity: 0.35, depthWrite: false });
function ripetiChiudi() { RIP.el?.remove(); RIP.el = null; RIP.ghost.clear(); ridisegna(); }
function ripetiOpz() {
  const v = id => RIP.el.querySelector(id).value.trim();
  const sul = RIP.el.querySelector('#rp-modo .on')?.dataset.m === 'lung';
  return { quante: v('#rp-n'), passo: sul ? null : v('#rp-p'), lung: sul ? v('#rp-p') : null, verso: RIP.el.querySelector('#rp-verso .on')?.dataset.v || 'destra' };
}
const RIP_VERSI = { destra: [1, 0, 0], sinistra: [-1, 0, 0], dietro: [0, 1, 0], davanti: [0, -1, 0], su: [0, 0, 1], giu: [0, 0, -1] };
function ripetiAnteprima() {
  RIP.ghost.clear();
  const o = objs.get(RIP.id); if (!o || !RIP.el) return;
  const op = ripetiOpz(), n = parseInt(op.quante, 10), num = x => parseFloat(String(x || '').replace(',', '.'));
  const passo = op.lung != null ? num(op.lung) / Math.max(1, n - 1) : num(op.passo);
  const info = RIP.el.querySelector('#rp-info');
  if (!(n >= 2 && n <= 100) || !(passo > 0)) { info.textContent = 'Scrivi quante (da 2) e il passo in mm.'; ridisegna(); return; }
  const d = RIP_VERSI[op.verso];
  for (let k = 1; k < n; k++) {
    const m = new THREE.Mesh(o.mesh.geometry, RIP_MAT);
    m.matrixAutoUpdate = false;
    m.matrix.copy(o.mesh.matrixWorld).premultiply(new THREE.Matrix4().makeTranslation(d[0] * passo * k, d[1] * passo * k, d[2] * passo * k));
    RIP.ghost.add(m);
  }
  info.textContent = `${n} in tutto (questo + ${n - 1}), passo ${mmTesto(passo)} mm: la fila va ${mmTesto(passo * (n - 1))} mm verso ${op.verso === 'giu' ? 'giù' : op.verso}.`;
  ridisegna();
}
function ripetiApri(id) {
  ripetiChiudi();
  const o = objs.get(id); if (!o) return;
  const el = document.createElement('div');
  el.id = 'ripeti'; el.className = 'pannello-cmd';
  const versi = Object.keys(RIP_VERSI).map(v => `<button data-v="${v}" class="${v === 'destra' ? 'on' : ''}">${v === 'giu' ? 'giù' : v}</button>`).join('');
  el.innerHTML = `<div class="pc-testa"><h3>In fila</h3><p>«${esc(o.data.name)}» più volte, a passo fisso: le copie si vedono subito, trasparenti</p></div>
    <div class="pc-corpo">
    <section class="sezione"><h4>Quante</h4>
      <div class="ap-riga"><span class="ap-lab">Quante in tutto (con questo)</span><span class="inp"><input class="field num" id="rp-n" value="4"></span></div></section>
    <section class="sezione"><h4>Verso</h4><span class="seg griglia3" id="rp-verso">${versi}</span></section>
    <section class="sezione"><h4>Distanza</h4><span class="seg" id="rp-modo"><button data-m="passo" class="on">Passo</button><button data-m="lung">Dalla prima all’ultima</button></span>
      <div class="ap-riga"><span class="inp"><input class="field num" id="rp-p" value="100"><i>mm</i></span></div>
      <p class="ap-dist" id="rp-info"></p></section></div>
    <div class="pc-fondo"><button class="btn" id="rp-no">Annulla <kbd>Esc</kbd></button><button class="btn primary big" id="rp-ok">Fatto <kbd>Invio</kbd></button></div>`;
  document.body.appendChild(el);
  RIP.el = el; RIP.id = id;
  el.querySelectorAll('#rp-verso button, #rp-modo button').forEach(b => { b.onclick = () => {
    b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); ripetiAnteprima(); }; });
  el.querySelectorAll('input').forEach(i => { i.oninput = () => { clearTimeout(RIP.t); RIP.t = setTimeout(ripetiAnteprima, 60); }; });
  $('#rp-no').onclick = ripetiChiudi;
  $('#rp-ok').onclick = ripetiFatto;
  ripetiAnteprima();
  setTimeout(() => { const i = $('#rp-n'); i?.focus(); i?.select(); }, 0);
}
function ripetiFatto() {
  if (!RIP.el) return;
  const op = ripetiOpz(), id = RIP.id;
  ripetiChiudi();
  inCoda(async () => { const r = await call('asm_ripeti', id, op.quante, op.passo, op.verso, op.lung); await apply(r, r.message); });
}
window.addEventListener('keydown', e => {
  if (!RIP.el) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); ripetiChiudi(); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopImmediatePropagation(); ripetiFatto(); }
}, true);
window.__ripeti = { apri: ripetiApri, get copie() { return RIP.ghost.children.length; } };
// ===================================================================== Interferenze in rosso (03/11)
// Il pezzo in comune tra due pezzi che entrano uno nell'altro, rosso sopra tutto, con un cartellino coi due nomi e
// quanto entra. Resta finché non cambia l'assieme (o si rifà il controllo); clic sul cartellino = sceglie i due pezzi.
const interfGroup = new THREE.Group();
scene.add(interfGroup);
var interfEls = [];                                 // var: placeDims la legge
const interfBox = document.createElement('div');
interfBox.id = 'interf-box';
document.getElementById('dims').after(interfBox);
const INTERF_MAT = new THREE.MeshBasicMaterial({ color: 0xE5484D, transparent: true, opacity: 0.75, depthTest: false, side: THREE.DoubleSide });
function interfPulisci() {
  interfGroup.traverse(x => x.geometry?.dispose()); interfGroup.clear();
  interfBox.innerHTML = ''; interfEls = [];
  document.getElementById('interf-pan')?.remove();
}
// 04/11: l'elenco delle interferenze a destra, come il pannello del pezzo: ogni riga sceglie i due pezzi
function interfPannello(lista) {
  document.getElementById('interf-pan')?.remove();
  const el = document.createElement('div');
  el.id = 'interf-pan'; el.className = 'pannello-cmd';
  const vol = x => { const cm3 = x.volume / 1000; return cm3 >= 1 ? mmTesto(cm3) + ' cm³' : Math.round(x.volume) + ' mm³'; };
  el.innerHTML = `<div class="pc-testa"><h3>Interferenze</h3><p>${lista.length === 1 ? 'Un punto' : lista.length + ' punti'} dove un pezzo entra nell’altro: in rosso nel 3D. Clic su una riga per scegliere i due pezzi</p></div>
    <div class="pc-corpo"><section class="sezione"><h4>Dove</h4>${lista.map((x, i) => `<button class="asm-mate" data-interf="${i}"><img src="icons/interferenze.svg" alt="">
      <span>«${esc(x.nomi[0])}» e «${esc(x.nomi[1])}»<small class="testo-2"> entra ${vol(x)}</small></span></button>`).join('')}</section>
    <section class="sezione"><h4>Cosa puoi fare</h4><button class="btn" id="interf-rifai"><img src="icons/interferenze.svg" alt="">Controlla di nuovo</button>
      <p class="hint">Sposta o cambia un pezzo: il rosso sparisce da solo, poi controlla di nuovo.</p></section></div>
    <div class="pc-fondo"><button class="btn primary big" id="interf-ok">Fatto</button></div>`;
  document.body.appendChild(el);
  el.querySelectorAll('[data-interf]').forEach(b => { b.onclick = () => { const x = lista[+b.dataset.interf]; sel = { id: x.a, ids: [x.a, x.b] }; paint(); renderTree(); }; });
  $('#interf-rifai').onclick = () => runCmd('asm_interf');
  $('#interf-ok').onclick = () => { interfPulisci(); ridisegna(); };
}
function interfMostra(lista) {
  interfPulisci();
  for (const x of lista) {
    if (x.mesh?.positions?.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(x.mesh.positions, 3));
      g.setIndex(x.mesh.indices);
      const m = new THREE.Mesh(g, INTERF_MAT); m.renderOrder = 40; interfGroup.add(m);
    }
    if (!x.centro) continue;
    const el = document.createElement('div');
    el.className = 'dim interf';
    const cm3 = x.volume / 1000;
    el.textContent = `${x.nomi[0]} ↔ ${x.nomi[1]}: ${cm3 >= 1 ? mmTesto(cm3) + ' cm³' : Math.round(x.volume) + ' mm³'}`;
    el.title = 'Questi due pezzi entrano uno nell’altro: clic per sceglierli';
    el.onclick = ev => { ev.stopPropagation(); sel = { id: x.a, ids: [x.a, x.b] }; paint(); renderTree(); };
    interfBox.appendChild(el);
    interfEls.push({ el, at: new THREE.Vector3(...x.centro) });
  }
  placeDims(); ridisegna();
  if (lista.length) interfPannello(lista);
}
window.__interf = { mostra: interfMostra, pulisci: interfPulisci, get n() { return interfGroup.children.length; } };
// ===================================================================== Vite nei fori (03/11, secondo giro)
// Foro su foro: clic nel foro di un pezzo, poi in quello dell'altro → un pannello piccolo con la vite giusta per il
// foro (Ø13 → M12) e lunga quanto il pacco più il dado: Invio la mette (e allinea i pezzi), «Solo allinea» come prima.
const VF = { el: null, a: null, b: null, p: null };
function viteForiChiudi() { VF.el?.remove(); VF.el = null; }
async function viteFori(a, b) {
  viteForiChiudi();
  const verso = camera.position.clone().sub(controls.target).normalize(), v = [verso.x, verso.y, verso.z];
  const r = await call('asm_bullone', a, b, { verso: v }, true);
  if (!r.ok) {                                        // non è un foro (o troppo piccolo): foro su foro come prima
    inCoda(async () => { const x = await call('asm_add_mate', 'asse', a, b, 0, false, null, null, true);
      if (await apply(x, 'Accoppiato.') && x.select) await select(x.select); });
    return;
  }
  const p = r.proposta, nomi = [a, b].map(f => objs.get(f.inst)?.data.name || f.inst);
  const el = document.createElement('div');
  el.id = 'vitefori'; el.className = 'pannello-cmd';
  const sel = (id, lst, v) => `<select class="field" id="${id}">${lst.map(x => `<option${String(x) === String(v) ? ' selected' : ''}>${esc(String(x))}</option>`).join('')}</select>`;
  el.innerHTML = `<div class="pc-testa"><h3>Vite nei fori</h3><p>«${esc(nomi[0])}» e «${esc(nomi[1])}»: la vite giusta per il foro, lunga quanto il pacco</p></div>
    <div class="pc-corpo">
    <section class="sezione"><h4>Cosa puoi fare</h4><button class="btn" id="vf-solo" title="Solo foro su foro, senza vite"><img src="icons/hole.svg" alt="">Solo allinea i fori, senza vite</button></section>
    <section class="sezione"><h4>${esc(p.tipo === 'vite_te' ? 'Vite TE' : 'Vite TCEI')}</h4>
      <div class="ap-riga vf-misura">${sel('vf-m', r.misure, p.misura)}<span>×</span>${sel('vf-l', r.lunghezze, p.L)}<span class="testo-2">mm</span></div>
      ${p.dado ? '<label class="interruttore"><input type="checkbox" id="vf-d" checked><i></i>Con dado</label>' : ''}
      <p class="ap-dist">Foro Ø${mmTesto(p.foro)}, quindi ${esc(p.misura)}; pacco ${mmTesto(p.pacco)} mm.${r.allineati ? '' : ' I pezzi si mettono uno contro l’altro, coi fori allineati.'}</p>
      ${p.corta ? '<p class="msg warn ap-err">Anche la più lunga del catalogo è corta per questo pacco.</p>' : ''}</section></div>
    <div class="pc-fondo"><button class="btn" id="vf-no">Annulla <kbd>Esc</kbd></button><button class="btn primary big" id="vf-ok">Metti la vite <kbd>Invio</kbd></button></div>`;
  document.body.appendChild(el);
  VF.el = el; VF.a = a; VF.b = b; VF.p = p; VF.v = v;
  $('#vf-no').onclick = viteForiChiudi;
  $('#vf-solo').onclick = () => { viteForiChiudi(); inCoda(async () => {
    const x = await call('asm_add_mate', 'asse', a, b, 0, false, null, null, true);
    if (await apply(x, 'Fori allineati.') && x.select) await select(x.select); }); };
  $('#vf-ok').onclick = viteForiFatto;
}
function viteForiFatto() {
  if (!VF.el) return;
  const opz = { misura: $('#vf-m').value, L: +$('#vf-l').value, dado: $('#vf-d') ? $('#vf-d').checked : false, verso: VF.v };
  const a = VF.a, b = VF.b;
  viteForiChiudi();
  inCoda(async () => { const r = await call('asm_bullone', a, b, opz, false); if (await apply(r, r.message) && r.select) await select(r.select); });
}
window.addEventListener('keydown', e => {
  if (!VF.el || e.target.closest?.('input:not([type=checkbox]), textarea')) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); viteForiChiudi(); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopImmediatePropagation(); viteForiFatto(); }
}, true);
// ===================================================================== Appoggia (03/11)
// Stefano: «appoggia e centra in un comando». Clic su una faccia del pezzo da mettere, poi su quella del pezzo fermo:
// si appoggia senza capovolgersi né entrare e parte al centro. Un pannello piccolo per «al centro / su un bordo / a
// misura», «Gira di 90°» e «Capovolgi»: ogni scelta si vede subito sul pezzo; «Fatto» crea gli accoppiamenti veri.
const APP = { el: null, mobile: null, fermo: null, opz: null, dove: 'centro', info: null, prima: null, n: 0, t: null };
const mmTesto = v => String(Math.round(v * 10) / 10).replace('.', ',');
function appoggiaClick(ev) {
  const h = pick(ev);
  if (!h || h.face == null) { toast('Clicca una faccia di un pezzo.', 'err'); return; }
  if (!ASM.clic.length) { ASM.clic.push({ inst: h.id, face: h.face }); sel = { id: h.id, face: h.face }; paint(); asmHelp(); return; }
  if (h.id === ASM.clic[0].inst) { toast('Ora clic su una faccia di un altro pezzo: quello su cui appoggiarlo.', 'err'); return; }
  const mobile = ASM.clic[0], fermo = { inst: h.id, face: h.face };
  asmTool(null);
  sel = null; nascondiMini(); paint();
  appoggiaApri(mobile, fermo);
}
function appoggiaApri(mobile, fermo) {
  appoggiaChiudi(true);
  APP.mobile = mobile; APP.fermo = fermo; APP.dove = 'centro'; APP.info = null;
  // auto: alla prima prova, se così entra nell'altro, Radius prova da solo a girarlo o capovolgerlo
  APP.opz = { u: { modo: 'centro', mm: 0 }, v: { modo: 'centro', mm: 0 }, gira: 0, capovolgi: false, auto: true };
  APP.cambio = null;
  APP.prima = {};
  for (const o of objs.values()) if (o.data.kind === 'instance') APP.prima[o.data.id] = [...o.data.matrix];
  const el = document.createElement('div');
  el.id = 'appoggia'; el.className = 'pannello-cmd';
  el.innerHTML = '<div class="pc-testa"><h3>Appoggia</h3><p>Calcolo dove sta…</p></div>';
  document.body.appendChild(el);
  APP.el = el;
  appoggiaProva();
}
function appoggiaChiudi(ripristina) {
  clearTimeout(APP.t);
  APP.n++;
  if (ripristina && APP.prima) spostaPezzi(APP.prima);
  APP.el?.remove();
  APP.el = null; APP.prima = null;
}
async function appoggiaProva() {
  const n = ++APP.n;
  APP.el?.classList.add('calcolo');
  const r = await call('asm_appoggia', APP.mobile, APP.fermo, APP.opz, true);
  if (n !== APP.n || !APP.el) return;
  APP.el.classList.remove('calcolo');
  if (!r.ok) {
    if (!APP.info) { appoggiaChiudi(true); toast(r.message, 'err'); return; }
    APP.el.querySelector('.ap-err').textContent = r.message; APP.el.querySelector('.ap-err').hidden = false;
    return;
  }
  spostaPezzi({ ...APP.prima, ...r.pose });
  const prima = !APP.info;
  delete APP.opz.auto;
  if (r.scelto) { APP.opz.gira = r.scelto.gira || 0; APP.opz.capovolgi = !!r.scelto.capovolgi; APP.cambio = r.cambio; }
  else if (!prima) APP.cambio = null;
  APP.info = r;
  if (prima) appoggiaDisegna(); else appoggiaDistanze();
}
function appoggiaDistanze() {
  const r = APP.info, el = APP.el;
  if (!r || !el) return;
  el.querySelector('.ap-err').hidden = true;
  // 04/11: una riga per coppia di lati, senza «·» (dai bordi, in mm)
  el.querySelector('.ap-dist').innerHTML = 'Dai bordi, in mm:' + ['u', 'v'].map(k => { const d = r.dirs[k];
    const q = v => v < -0.05 ? `sporge <b>${mmTesto(-v)}</b>` : `<b>${mmTesto(v)}</b>`;      // più grande della faccia
    return `<span class="riga-dist">${esc(d.basso)} ${q(d.da_basso)}, ${esc(d.alto)} ${q(d.da_alto)}</span>`; }).join('');
  const liberi = ['u', 'v'].filter(k => !r.dirs[k].tiene).map(k => `${r.dirs[k].basso}/${r.dirs[k].alto}`);
  const note = [];
  if (APP.cambio) note.push(`${APP.cambio === 'Capovolgi' ? 'Capovolto' : APP.cambio === 'Gira di 90°' ? 'Girato di 90°' : 'Capovolto e girato'}: così ci sta senza entrare in «${r.nome_fermo}».`);
  if (r.alzato > 0) note.push(`Sulla faccia non ci sta: lo poso su quello che tocca prima, ${mmTesto(r.alzato)} mm più su.`);
  if (liberi.length) note.push(`${liberi.join(', ')}: non c’è un lato piano per tenerlo; resta lì ma non segue i pezzi se cambiano.`);
  el.querySelector('.ap-nota').textContent = note.join(' ');
  const prop = el.querySelector('.ap-prop');
  prop.innerHTML = (r.proposte || []).length ? 'Ci sta giù se: ' + r.proposte.map((p, i) => `<button class="btn" data-prop="${i}">${esc(p.testo)}</button>`).join(' ') : '';
  prop.querySelectorAll('[data-prop]').forEach(b => { b.onclick = () => {
    const p = r.proposte[+b.dataset.prop].opz;
    APP.opz.gira = p.gira || 0; APP.opz.capovolgi = !!p.capovolgi;
    $('#ap-capo')?.classList.toggle('on', APP.opz.capovolgi);
    appoggiaProva();
  }; });
  const err = el.querySelector('.ap-err');
  if (r.dentro > 1) {
    const cm3 = r.dentro / 1000;
    err.textContent = `Così entra in «${r.nome_fermo}» (${cm3 >= 1 ? mmTesto(cm3) + ' cm³' : Math.round(r.dentro) + ' mm³'}): scegli un’altra faccia, «Capovolgi» o spostalo dal bordo.`;
    err.hidden = false;
  }
}
function appoggiaDisegna() {
  const r = APP.info, el = APP.el, o = APP.opz;
  const riga = k => {
    const d = r.dirs[k], m = o[k].modo;
    const b = (modo, t) => `<button data-k="${k}" data-modo="${modo}" class="${m === modo ? 'on' : ''}">${esc(t)}</button>`;
    return `<div class="ap-riga ap-lati"><span class="ap-lab">${esc(d.basso[0].toUpperCase() + d.basso.slice(1))} o ${esc(d.alto)}</span>
      <span class="seg">${b('basso', d.basso)}${b('centro', 'al centro')}${b('alto', d.alto)}</span>
      ${APP.dove === 'misura' && m !== 'centro' ? `<span class="inp"><input class="field" data-mm="${k}" value="${mmTesto(+String(o[k].mm).replace(',', '.') || 0)}" aria-label="Distanza da ${esc(m === 'basso' ? d.basso : d.alto)}"><i>mm</i></span>` : ''}</div>`;
  };
  const dove = (k, t) => `<button data-dove="${k}" class="${APP.dove === k ? 'on' : ''}">${t}</button>`;
  el.innerHTML = `<div class="pc-testa"><h3>Appoggia «${esc(r.nome_mobile)}»</h3><p>su «${esc(r.nome_fermo)}»: senza entrarci e senza capovolgersi. Ogni scelta si vede subito sul pezzo</p></div>
    <div class="pc-corpo">
    <section class="sezione"><h4>Cosa puoi fare</h4><div class="asm-azioni">
      <button class="btn" id="ap-gira" title="Gira il pezzo di un quarto di giro sulla faccia"><img src="icons/orbit.svg" alt=""><span>Gira di 90°</span></button>
      <button class="btn" id="ap-capo" title="Appoggia il pezzo dall’altra parte (sottosopra), sempre fuori dall’altro"><img src="icons/mirror.svg" alt=""><span>Capovolgi</span></button></div>
      <p class="ap-prop"></p></section>
    <section class="sezione"><h4>Dove sulla faccia</h4>
      <div class="seg ap-dove">${dove('centro', 'Al centro')}${dove('bordo', 'Su un bordo')}${dove('misura', 'A misura')}</div>
      ${APP.dove === 'centro' ? '' : riga('u') + riga('v')}
      <p class="ap-dist"></p><p class="ap-nota hint"></p><p class="msg err ap-err" hidden></p></section></div>
    <div class="pc-fondo"><button class="btn" id="ap-no">Annulla <kbd>Esc</kbd></button><button class="btn primary big" id="ap-ok">Fatto <kbd>Invio</kbd></button></div>`;
  el.querySelectorAll('[data-dove]').forEach(b => { b.onclick = () => {
    APP.dove = b.dataset.dove;
    for (const k of ['u', 'v']) {
      if (APP.dove === 'centro') o[k] = { modo: 'centro', mm: 0 };
      else if (APP.dove === 'bordo') o[k].mm = 0;
      else if (o[k].modo !== 'centro') o[k].mm = Math.round(r.dirs[k]['da_' + o[k].modo] * 10) / 10;
    }
    if (APP.dove !== 'centro' && o.u.modo === 'centro' && o.v.modo === 'centro') {
      o.v = { modo: 'basso', mm: APP.dove === 'misura' ? Math.round(r.dirs.v.da_basso * 10) / 10 : 0 };
      if (APP.dove === 'misura') o.u = { modo: 'basso', mm: Math.round(r.dirs.u.da_basso * 10) / 10 };
    }
    appoggiaDisegna(); appoggiaProva();
  }; });
  el.querySelectorAll('[data-modo]').forEach(b => { b.onclick = () => {
    const k = b.dataset.k, modo = b.dataset.modo;
    o[k] = { modo, mm: APP.dove === 'misura' && modo !== 'centro' ? Math.round(r.dirs[k]['da_' + modo] * 10) / 10 : 0 };
    appoggiaDisegna(); appoggiaProva();
    setTimeout(() => { const i = APP.el?.querySelector(`[data-mm="${k}"]`); if (i) { i.focus(); i.select(); } }, 0);
  }; });
  el.querySelectorAll('[data-mm]').forEach(i => { i.oninput = () => {
    o[i.dataset.mm].mm = i.value.trim();
    clearTimeout(APP.t); APP.t = setTimeout(appoggiaProva, 120);
  }; });
  $('#ap-gira').onclick = () => { o.gira = (o.gira + 1) % 4; appoggiaProva(); };
  $('#ap-capo').onclick = () => { o.capovolgi = !o.capovolgi; $('#ap-capo').classList.toggle('on', o.capovolgi); appoggiaProva(); };
  $('#ap-capo').classList.toggle('on', o.capovolgi);
  $('#ap-no').onclick = () => appoggiaChiudi(true);
  $('#ap-ok').onclick = appoggiaFatto;
  appoggiaDistanze();
}
function appoggiaFatto() {
  if (!APP.el) return;
  clearTimeout(APP.t);
  const mobile = APP.mobile, fermo = APP.fermo, opz = JSON.parse(JSON.stringify(APP.opz)), prima = APP.prima;
  appoggiaChiudi(false);
  inCoda(async () => {
    const r = await call('asm_appoggia', mobile, fermo, opz, false);
    if (!r.ok && prima) spostaPezzi(prima);
    if (await apply(r, r.message) && r.select) await select(r.select);
  });
}
window.addEventListener('keydown', e => {
  if (!APP.el) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); appoggiaChiudi(true); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopImmediatePropagation(); appoggiaFatto(); }
}, true);
window.__appoggia = { apri: appoggiaApri, stato: () => APP };      // per le prove automatiche
// ===================================================================== Metti nel vano (04/11)
// Stefano: «accoppiare il pannello dentro il telaio è difficile, deve essere facile». Clic sul pannello, poi sul
// telaio: Radius trova i vani (in azzurro), sceglie quello dove ci sta (il più vicino al clic), lo mette in piedi,
// girato e centrato con lo stesso gioco tutto intorno. Nel pannello: quale vano, a filo davanti / in mezzo / dietro,
// Gira e Capovolgi; ogni scelta si vede subito. «Fatto» crea gli accoppiamenti veri (resta centrato se il telaio cambia).
const VAN = { el: null, mobile: null, fermo: null, opz: null, info: null, prima: null, n: 0, ghost: new THREE.Group() };
scene.add(VAN.ghost);
const VAN_LINEA = new THREE.LineBasicMaterial({ color: 0x1F5EFF, depthTest: false, transparent: true, opacity: 0.9 });
const VAN_SPENTO = new THREE.LineBasicMaterial({ color: 0x8A94A0, depthTest: false, transparent: true, opacity: 0.7 });
const VAN_FONDO = new THREE.MeshBasicMaterial({ color: 0x5B9BFF, transparent: true, opacity: 0.22, depthWrite: false, side: THREE.DoubleSide });
function vanoClick(ev) {
  const h = pick(ev);
  if (!h) { toast('Clicca un pezzo.', 'err'); return; }
  if (!ASM.clic.length) { ASM.clic.push({ inst: h.id, face: h.face }); sel = { id: h.id, face: h.face }; paint(); asmHelp(); return; }
  if (h.id === ASM.clic[0].inst) { toast('Ora clic sul telaio, vicino al vano dove va il pannello.', 'err'); return; }
  const mobile = ASM.clic[0], fermo = { inst: h.id, face: h.face, point: [h.point.x, h.point.y, h.point.z] };
  asmTool(null);
  sel = null; nascondiMini(); paint();
  vanoApri(mobile, fermo);
}
function vanoDa(id) { asmTool('vano'); ASM.clic = [{ inst: id, face: null }]; sel = { id }; paint(); asmHelp(); }
function vanoApri(mobile, fermo) {
  vanoChiudi(true);
  VAN.mobile = mobile; VAN.fermo = fermo; VAN.info = null;
  VAN.opz = { vano: null, gira: 0, capovolgi: false, prof: 'davanti' };
  VAN.prima = {};
  for (const o of objs.values()) if (o.data.kind === 'instance') VAN.prima[o.data.id] = [...o.data.matrix];
  const el = document.createElement('div');
  el.id = 'vano'; el.className = 'pannello-cmd';
  el.innerHTML = '<div class="pc-testa"><h3>Metti nel vano</h3><p>Cerco i vani del telaio…</p></div>';
  document.body.appendChild(el);
  VAN.el = el;
  passoAssieme();                                   // la riga «metti i pezzi al loro posto» lascia il posto
  vanoProva();
}
function vanoChiudi(ripristina) {
  VAN.n++;
  if (ripristina && VAN.prima) spostaPezzi(VAN.prima);
  VAN.el?.remove();
  VAN.el = null; VAN.prima = null;
  if (S) passoAssieme();
  VAN.ghost.traverse(o => o.geometry?.dispose()); VAN.ghost.clear();
  paint();
}
function vanoRettangoli(r) {
  VAN.ghost.traverse(o => o.geometry?.dispose()); VAN.ghost.clear();
  for (const v of r.vani) {
    const p = v.rett.map(q => new THREE.Vector3(...q));
    const g = new THREE.BufferGeometry().setFromPoints([...p, p[0]]);
    const l = new THREE.Line(g, v.i === r.vano ? VAN_LINEA : VAN_SPENTO); l.renderOrder = 5; VAN.ghost.add(l);
    if (v.i === r.vano) {
      const f = new THREE.BufferGeometry().setFromPoints([p[0], p[1], p[2], p[0], p[2], p[3]]);
      VAN.ghost.add(new THREE.Mesh(f, VAN_FONDO));
    }
  }
}
async function vanoProva() {
  const n = ++VAN.n;
  VAN.el?.classList.add('calcolo');
  const r = await call('asm_vano', VAN.mobile, VAN.fermo, VAN.opz, true);
  if (n !== VAN.n || !VAN.el) return;
  VAN.el.classList.remove('calcolo');
  if (!r.ok) {
    if (!VAN.info) { vanoChiudi(true); toast(r.message, 'err', null, 9000); return; }
    const e = VAN.el.querySelector('.vn-err'); e.textContent = r.message; e.hidden = false;
    return;
  }
  VAN.opz.vano = r.vano;
  spostaPezzi({ ...VAN.prima, ...r.pose });
  VAN.info = r;
  vanoRettangoli(r);
  vanoDisegna();
  paint();
}
function vanoDisegna() {
  const r = VAN.info, el = VAN.el, o = VAN.opz;
  const mis = v => `${mmTesto(v.W)} × ${mmTesto(v.H)}`;
  const vani = r.vani.length > 1 ? `<section class="sezione"><h4>Quale vano</h4><div class="seg">${r.vani.map(v =>
    `<button data-vano="${v.i}" class="${v.i === r.vano ? 'on' : ''}"${v.ci_sta ? '' : ' disabled title="Il pannello qui non ci sta"'}>${esc(v.nome[0].toUpperCase() + v.nome.slice(1))}, ${mis(v)}</button>`).join('')}</div></section>` : '';
  const prof = (k, t) => `<button data-prof="${k}" class="${r.prof === k ? 'on' : ''}">${esc(t)}</button>`;
  const g = r.giochi;
  el.innerHTML = `<div class="pc-testa"><h3>Metti «${esc(r.nome_mobile)}» nel vano</h3><p>di «${esc(r.nome_fermo)}»: in piedi, girato nel verso in cui entra, centrato. Ogni scelta si vede subito sul pezzo</p></div>
    <div class="pc-corpo">${vani}
    <section class="sezione"><h4>In profondità</h4><div class="seg">${prof('davanti', `A filo ${r.davanti}`)}${prof('mezzo', 'In mezzo')}${prof('dietro', `A filo ${r.dietro}`)}</div></section>
    <section class="sezione"><h4>Cosa puoi fare</h4><div class="asm-azioni${r.versi > 1 ? '' : ' una'}">
      ${r.versi > 1 ? '<button class="btn" id="vn-gira" title="Gira il pannello nel vano: nell’altro verso in cui ci sta"><img src="icons/orbit.svg" alt=""><span>Gira</span></button>' : ''}
      <button class="btn${o.capovolgi ? ' on' : ''}" id="vn-capo" title="Il pannello rovesciato: le pieghe dall’altra parte"><img src="icons/mirror.svg" alt=""><span>Capovolgi</span></button></div></section>
    <p class="vn-gioco">Gioco, in mm:<span>${esc(g[0].lato)} <b>${mmTesto(g[0].mm)}</b>, ${esc(g[1].lato)} <b>${mmTesto(g[1].mm)}</b></span><span>${esc(g[2].lato)} <b>${mmTesto(g[2].mm)}</b>, ${esc(g[3].lato)} <b>${mmTesto(g[3].mm)}</b></span></p>
    ${r.dentro > 1 ? `<p class="msg err">Così tocca dentro «${esc(r.nome_fermo)}»: prova «Capovolgi» o l’altra profondità.</p>` : ''}
    ${r.tiene ? '' : '<p class="hint">Un lato del vano non è piano: lì il pannello resta dove l’ho messo, non segue il telaio se cambia.</p>'}
    <p class="msg err vn-err" hidden></p></div>
    <div class="pc-fondo"><button class="btn" id="vn-no">Annulla <kbd>Esc</kbd></button><button class="btn primary big" id="vn-ok">Fatto <kbd>Invio</kbd></button></div>`;
  el.querySelectorAll('[data-vano]').forEach(b => { b.onclick = () => { o.vano = +b.dataset.vano; o.gira = 0; vanoProva(); }; });
  el.querySelectorAll('[data-prof]').forEach(b => { b.onclick = () => { o.prof = b.dataset.prof; vanoProva(); }; });
  if ($('#vn-gira')) $('#vn-gira').onclick = () => { o.gira = (o.gira + 1) % 4; vanoProva(); };
  $('#vn-capo').onclick = () => { o.capovolgi = !o.capovolgi; vanoProva(); };
  $('#vn-no').onclick = () => vanoChiudi(true);
  $('#vn-ok').onclick = vanoFatto;
}
function vanoFatto() {
  if (!VAN.el || !VAN.info) return;
  const mobile = VAN.mobile, fermo = VAN.fermo, opz = JSON.parse(JSON.stringify(VAN.opz)), prima = VAN.prima;
  vanoChiudi(false);
  inCoda(async () => {
    const r = await call('asm_vano', mobile, fermo, opz, false);
    if (!r.ok && prima) spostaPezzi(prima);
    if (await apply(r, r.message) && r.select) await select(r.select);
  });
}
window.addEventListener('keydown', e => {
  if (!VAN.el) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); vanoChiudi(true); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopImmediatePropagation(); vanoFatto(); }
}, true);
window.__vano = { apri: vanoApri, stato: () => VAN };      // per le prove automatiche
// 04/11 (regola 2): il pannello del pezzo sempre nello stesso ordine: chi è → cosa puoi fare (tutte le azioni, col
// nome) → chi lo tiene (gli accoppiamenti, con la misura e il cursore) → dove sta, sposta, ruota → il pezzo (nome,
// fermo, finitura, da acquistare) → «Dettagli» chiuso (file, peso, ingombro) → in fondo, fermo, «Apri il pezzo» in blu
function frasiMate() {                              // M1 → «Staffa su Piastra» (le stesse parole dell'albero)
  const g = (S?.tree?.children || []).find(c => c.kind === 'group' && c.label === 'Accoppiamenti');
  return Object.fromEntries((g?.children || []).map(c => [c.ref, c]));
}
// nella riga «Lo tengono» il nome del pezzo stesso non serve: «Staffa su Base» → «su Base»
const senzaNome = (frase, nome) => frase.startsWith(nome + ' ') ? frase.slice(nome.length + 1) : frase;
function cosEPezzo(s) {
  const n = (s.mates || []).length;
  if (s.fixed) return 'Pezzo dell’assieme, fermo: gli altri si appoggiano a lui';
  if (s.acquisto) return 'Da acquistare: va in distinta, niente DXF';
  return n ? `Pezzo dell’assieme, tenuto da ${n === 1 ? 'un accoppiamento' : n + ' accoppiamenti'}` : 'Pezzo dell’assieme, libero: si sposta come vuoi';
}
// l'icona di ogni tipo di accoppiamento (righe «Lo tengono» e albero)
function iconaMate(t) { return ICONA_MATE[t] || null; }
const ICONA_MATE = { faccia: 'faccia_su_faccia', asse: 'foro_su_foro', distanza: 'dimension', angolo: 'plane_angle', tangente: 'c_tangent', parallelo: 'c_parallel',
  perpendicolare: 'c_perpendicular', centra: 'c_symmetry', blocca: 'c_fix', spigolo: 'c_collinear', spigolo_faccia: 'c_coincident', cono: 'fastener', testa: 'testa', appoggia: 'appoggia' };
const TOGLI_ASM = (id, nome, titolo) => `<button class="btn danger tutta-riga" id="${id}" title="${esc(titolo)}"><img src="icons/delete.svg" alt=""><span>${esc(nome)}</span></button>`;
function instancePanel(s) {
  const tab = `<table class="grid">${s.rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;
  const faccia = s.face ? `<p class="hint">Faccia cliccata: ${esc(s.face.label)} (${esc(s.face.kind)})</p>` : '';
  const incastri = s.tabs_with ? `<details class="fsec" open><summary>Incastri con ${esc(s.tabs_with)}</summary>
    <p class="hint">Questa punta appoggia su ${esc(s.tabs_with)}: linguette qui e asole nell’altro pezzo (si salvano i due file).</p>
    <div class="ff"><label>Quante<span class="inp"><input class="field" id="t-n" value="3"></span></label>
      <label>Larghezza<span class="inp"><input class="field" id="t-w" value="15"><i>mm</i></span></label>
      <label>Gioco<span class="inp"><input class="field" id="t-c" value="0,2"><i>mm</i></span></label>
      <label>Sporgenza<span class="inp"><input class="field" id="t-s" value="0"><i>mm</i></span></label></div>
    <div class="row-btns"><button class="btn" id="t-go">Crea gli incastri</button></div></details>` : '';
  const scassi = s.scassi ? `<details class="fsec" open><summary>Scassi per i pezzi che entrano</summary>
    <p class="hint" id="sc-frase">${esc(s.scassi.frase)} In rosso dove taglia.</p>
    <div class="ff"><label>Gioco per lato<span class="inp"><input class="field" id="sc-c" value="0,5"><i>mm</i></span></label><span></span></div>
    <div class="row-btns"><button class="btn" id="sc-go">Fai gli scassi</button></div></details>` : '';
  // cosa puoi fare: tutte le azioni della barretta (anche quelle che lì stanno in «Altro»), meno «Apri», che è in fondo
  const azioni = azioniPezzo(s).filter(x => x.id !== 'open' && x.cls !== 'mov');
  // 04/11 (ritocchi): «Togli» sta in tutti i pannelli nello stesso posto: l'ultima voce di «Cosa puoi fare», rossa e quieta
  const cosa = `<section class="sezione"><h4>Cosa puoi fare</h4><div class="asm-azioni">${azioni.map((x, i) =>
    `<button class="btn" data-azione-pezzo="${i}" title="${esc(x.t)}"><img src="icons/${x.ic}.svg" alt=""><span>${esc(x.t.replace(/ \(.*$/, '').replace(/:.*$/, ''))}</span></button>`).join('')}
    ${TOGLI_ASM('a-del', 'Togli dall’assieme', 'Toglie questo pezzo dall’assieme (Canc); il suo file resta')}</div></section>`;
  // chi lo tiene: ogni accoppiamento in parole (clic = lo apri); quelli con una misura hanno il campo e il cursore
  const frasi = frasiMate(), mov = Object.fromEntries((s.movimenti || []).map((m, k) => [m.id, [m, k]]));
  const tiene = `<section class="sezione"><h4>Lo tengono</h4>${(s.mates || []).length ? s.mates.map(mid => {
    const [m, k] = mov[mid] || [], f = frasi[mid];
    const riga = `<button class="asm-mate" data-vai-mate="${esc(mid)}" title="Apri l’accoppiamento"><img src="icons/${ICONA_MATE[f?.tipo] || 'joint'}.svg" alt=""><span>${esc(senzaNome(f?.label || mid, s.title))}</span></button>`;
    if (!m) return riga;
    const v = m.valore, lo = m.campo === 'angle' ? 0 : Math.floor(Math.min(v - 200, -2)), hi = m.campo === 'angle' ? 180 : Math.ceil(v + 200);
    return riga + `<div class="asm-misura"><span>${esc(m.nome)}</span><span class="campo-unita"><input class="field num" id="mv-v${k}" value="${esc(String(Math.round(v * 10) / 10).replace('.', ','))}" aria-label="${esc(m.nome)}"><i>${m.campo === 'angle' ? '°' : 'mm'}</i></span>
      <input type="range" class="cursore" id="mv-s${k}" min="${lo}" max="${hi}" step="1" value="${v}" title="Trascina: il pezzo si muove"></div>`;
  }).join('') : '<p class="hint">Nessun accoppiamento: si sposta liberamente. Per metterlo su un altro pezzo: «Appoggia».</p>'}</section>`;
  const fin = s.acquisto ? '' : `<div class="ff"><label>Finitura<select class="field" id="a-fin">${[['grezzo', 'Grezzo'], ['zincato', 'Zincato'], ['inox', 'Inox spazzolato'], ['verniciato', 'Verniciato RAL']].map(([k, l]) => `<option value="${k}"${(s.finitura?.tipo || 'grezzo') === k ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
      <label${s.finitura?.tipo === 'verniciato' ? '' : ' hidden'} id="a-ral-w">RAL<input class="field" id="a-ral" list="ral-lista" value="${esc(s.finitura?.ral || '')}" placeholder="es. 7035"></label></div>
      <datalist id="ral-lista">${['1003', '1013', '1023', '2004', '3000', '3002', '3020', '5010', '5012', '5015', '6005', '6018', '7016', '7021', '7035', '7037', '7040', '9005', '9006', '9010', '9016'].map(x => `<option value="${x}">`).join('')}</datalist>`;
  return `<div class="asm-pan"><div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">${esc(cosEPezzo(s))}</div></div></div>
    ${cosa}${incastri}${scassi}${tiene}
    <section class="sezione"><h4>Dove sta</h4>${dovePanel(s)}
      <div class="asm-sposta"${s.tenuto ? ' hidden' : ''}><div class="sub">Sposta di (mm)</div>
      <div class="xyz"><label>X<input class="field" id="a-dx" value="0"></label><label>Y<input class="field" id="a-dy" value="0"></label><label>Z<input class="field" id="a-dz" value="0"></label></div>
      <div class="row-btns"><button class="btn" id="a-move">Sposta</button></div></div>
      <div class="sub">Ruota di 90°</div>
      <div class="seg asm-ruota"><button data-rot="x">attorno a X</button><button data-rot="y">attorno a Y</button><button data-rot="z">attorno a Z</button></div></section>
    <section class="sezione"><h4>Il pezzo</h4>
      <div class="ff"><label class="tutta-riga">Nome<input class="field" id="a-nome" value="${esc(nomeSenzaCopia(s.title))}" title="Vale per tutte le copie, la distinta e le tavole (anche doppio clic sulla voce a sinistra)"></label></div>
      <label class="interruttore"><input type="checkbox" id="a-fixed"${s.fixed ? ' checked' : ''}><i></i>Fermo: gli altri pezzi si appoggiano a lui</label>
      ${fin}
      <label class="interruttore"><input type="checkbox" id="a-acq"${s.acquisto ? ' checked' : ''}><i></i>Da acquistare (guide, viti…): in distinta, niente DXF</label>
      ${s.acquisto ? `<div class="ff"><label class="tutta-riga">Descrizione<input class="field" id="a-acq-d" value="${esc(s.acquisto.descrizione || '')}"></label>
        <label>Codice<input class="field" id="a-acq-c" value="${esc(s.acquisto.codice || '')}"></label>
        <label>Fornitore<input class="field" id="a-acq-f" value="${esc(s.acquisto.fornitore || '')}"></label></div>` : ''}</section>
    <details class="fsec"><summary>Dettagli</summary>${tab}${faccia}</details>
    <div class="asm-fondo"><button class="btn primary big" id="a-open">Apri il pezzo</button></div></div>`;
}
// 03/11: «Sposta» diceva solo «di quanto», non dove sta il pezzo. Qui dove sta (l'angolo in basso a sinistra davanti) e,
// se appoggia su un altro pezzo, quanto manca ai suoi bordi: si scrive dove lo vuoi e Invio, il conto lo fa Radius
function dovePanel(s) {
  const d = s.dove;
  if (!d) return '';
  const fermo = !!s.tenuto, v = x => mmTesto(x);
  const campo = (id, t, x) => `<label>${t}<input class="field" id="${id}" value="${v(x)}"${fermo ? ' readonly' : ''}></label>`;
  return `
    <div class="xyz">${campo('a-px', 'X', d.min[0])}${campo('a-py', 'Y', d.min[1])}${campo('a-pz', 'Z', d.min[2])}</div>
    <p class="hint stretto">L’angolo in basso a sinistra, davanti, in mm${fermo ? '' : ': scrivi dove lo vuoi e Invio'}.</p>
    ${d.sotto ? `<div class="sub">Dai bordi di «${esc(d.sotto.name)}» (mm)</div>
      <div class="xyz xyz4">${campo('a-bs', 'sinistra', d.sotto.sinistra)}${campo('a-bd', 'destra', d.sotto.destra)}${campo('a-bv', 'davanti', d.sotto.davanti)}${campo('a-bt', 'dietro', d.sotto.dietro)}</div>` : ''}
    ${fermo ? `<p class="hint stretto">Lo tengono gli accoppiamenti: per spostarlo ${(s.movimenti || []).length ? 'cambia le misure qui sopra o ' : ''}rifai «Appoggia».</p>` : ''}`;
}
function wireDove(s, fai) {
  const d = s.dove;
  if (!d || s.tenuto) return;
  const num = el => parseFloat(el.value.trim().replace(',', '.'));
  // ogni campo: di quanto si sposta, in X, Y, Z, se scrivi il valore v al posto di quello che c'è
  const campi = { 'a-px': [d.min[0], 1, 0], 'a-py': [d.min[1], 1, 1], 'a-pz': [d.min[2], 1, 2] };
  if (d.sotto) Object.assign(campi, { 'a-bs': [d.sotto.sinistra, 1, 0], 'a-bd': [d.sotto.destra, -1, 0], 'a-bv': [d.sotto.davanti, 1, 1], 'a-bt': [d.sotto.dietro, -1, 1] });
  for (const [id, [prima, segno, asse]] of Object.entries(campi)) {
    const el = $('#' + id);
    if (!el) continue;
    const vai = () => {
      const x = num(el);
      if (!Number.isFinite(x) || Math.abs(x - prima) < 1e-9) return;
      const dd = [0, 0, 0]; dd[asse] = (x - prima) * segno;
      fai('asm_move', s.id, ...dd.map(String));
    };
    el.onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); vai(); } };
    el.onchange = vai;
  }
}
function wireInstance(s) {
  const fai = (m, ...a) => inCoda(async () => { if (await apply(await call(m, ...a))) await refreshSel(); });
  wireDove(s, fai);
  const nm = $('#a-nome');
  nm.onkeydown = ev => { if (ev.key === 'Enter') nm.blur(); };
  nm.onchange = () => { if (nm.value.trim() && nm.value.trim() !== nomeSenzaCopia(s.title)) rinominaPezzo(s.id, nm.value); };
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
  $('#a-open').onclick = () => apriPezzoAssieme(s.id);
  const azioni = azioniPezzo(s).filter(x => x.id !== 'open' && x.cls !== 'mov');
  document.querySelectorAll('[data-azione-pezzo]').forEach(b => { b.onclick = () => azioni[+b.dataset.azionePezzo]?.fai(); });
  document.querySelectorAll('[data-vai-mate]').forEach(b => { b.onclick = () => inCoda(() => select('mate=' + b.dataset.vaiMate)); });
  if ($('#t-go')) $('#t-go').onclick = () => inCoda(async () => apply(await call('asm_tabs', s.id, s.face.index,
    $('#t-n').value.trim(), $('#t-w').value.trim(), $('#t-c').value.trim(), $('#t-s').value.trim())));
  wireScassi(s);
}
// dalla barretta del pezzo (03/11): i comandi che servono di più, fuori da «⋯»
function appoggiaDa(id, faccia) {
  if (faccia == null) { asmTool('appoggia'); return; }
  asmTool('appoggia');
  ASM.clic = [{ inst: id, face: faccia }];
  sel = { id, face: faccia }; paint(); asmHelp();
}
function spostaDa() {
  tutteLeOpzioni();
  setTimeout(() => { const i = $('#a-px'); if (i) { i.scrollIntoView({ block: 'center' }); if (!i.readOnly) { i.focus(); i.select(); } } }, 80);
}
function nuovoPezzoDialog(s) {
  if (!s.face) return;
  modal(`<h3>Nuovo pezzo su questa faccia</h3>
      <p class="hint">Lo disegni sul piano della faccia, vedendo gli altri pezzi; tornando all’assieme si monta da solo.</p>
      <div class="form"><label class="tutta-riga">Nome<input class="field" id="np-nome" value="Lamiera di collegamento"></label></div>
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
}
function wireScassi(s) {
  // scassi: le sagome in rosso sul pezzo mentre cambi il gioco, poi il taglio nel file del pezzo
  SCASSI = s.scassi ? { id: s.id, face: s.face.index, anelli: s.scassi.anelli } : null;
  if (SCASSI) paint();
  if ($('#sc-c')) {
    let t = null;
    $('#sc-c').oninput = () => { clearTimeout(t); t = setTimeout(async () => {
      const r = await call('asm_scassi', s.id, s.face.index, $('#sc-c').value.trim(), true);
      if (!$('#sc-frase')) return;
      $('#sc-frase').textContent = r.ok ? r.message + ' In rosso dove taglia.' : r.message;
      if (r.ok) { SCASSI = { id: s.id, face: s.face.index, anelli: r.anelli }; paint(); }
    }, 250); };
    $('#sc-go').onclick = () => { const c = $('#sc-c').value.trim(); SCASSI = null;
      inCoda(async () => { if (await apply(await call('asm_scassi', s.id, s.face.index, c, false))) await refreshSel(); }); };
  }
}
const SCASSI_MAT = new THREE.LineBasicMaterial({ color: 0xDC2626, depthTest: false, transparent: true });
function paintScassi() {
  if (!SCASSI || !sel || sel.id !== SCASSI.id || sel.face !== SCASSI.face) return;
  const pts = [];
  for (const a of SCASSI.anelli) a.forEach((p, k) => { const q = a[(k + 1) % a.length]; pts.push(new THREE.Vector3(...p), new THREE.Vector3(...q)); });
  const l = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), SCASSI_MAT.clone());
  l.renderOrder = 20;
  overlay.add(l);
}
// il campo del valore e il pulsante «gira» di ogni accoppiamento (niente = non serve)
const MATE_CAMPO = { faccia: 'Distanza', distanza: 'Distanza', tangente: 'Gioco', centra: 'Fuori centro', testa: 'Gioco di saldatura' };
// 03/11: «Allinea invece di affacciare» erano parole da CAD: a filo (le facce dalla stessa parte) o contro (una sull'altra)
const MATE_GIRA = { faccia: ['Metti a filo (facce dalla stessa parte)', 'Metti contro (faccia su faccia)'], distanza: ['Metti a filo (facce dalla stessa parte)', 'Metti contro (faccia su faccia)'],
  asse: ['Gira dall’altra parte'], parallelo: ['Gira dall’altra parte'], angolo: ['Angolo dall’altra parte'], tangente: ['Dall’altra parte'] };
// 04/11 (regola 2): l'accoppiamento scelto: cos'è in parole → cosa puoi fare (gira, sospendi) → la misura col cursore →
// i due pezzi (clic = scegli il pezzo) → «Dettagli» (tipo, scarto) → in fondo «Fatto» in blu
const MATE_COSA = { faccia: 'Una faccia contro l’altra', asse: 'I due fori sulla stessa linea', distanza: 'Due facce a una distanza',
  angolo: 'Due facce a un angolo', tangente: 'Il tubo appoggiato sulla faccia', parallelo: 'Due facce (o tubi) paralleli',
  perpendicolare: 'Due facce (o tubi) a squadra', centra: 'Il pezzo al centro, tra due lati', blocca: 'I due pezzi fermi uno rispetto all’altro',
  spigolo: 'Due spigoli sulla stessa linea', spigolo_faccia: 'Lo spigolo appoggiato sulla faccia', cono: 'La testa della vite nella svasatura',
  testa: 'Due tagli a 45° uno contro l’altro' };
// 04/11 (ritocchi): se il pannello si ridisegna mentre stai scrivendo in un suo campo (il motore che risponde tardi
// a un clic di prima), quello che hai scritto resta lì, col cursore: non torna al valore vecchio
function tieniScritto(disegna) {
  const a = document.activeElement;
  const scritto = a && a.id && $('#props').contains(a) && a.tagName === 'INPUT' && a.value !== a.defaultValue ? [a.id, a.value] : null;
  disegna();
  if (!scritto) return;
  const n = document.getElementById(scritto[0]);
  if (n && $('#props').contains(n)) { n.value = scritto[1]; n.focus(); }
}
function matePanel(s) {
  const d = s.def, v = x => esc(String(Math.round(x * 1000) / 1000).replace('.', ','));
  const gira = d.da === 'appoggia' || d.da === 'vano' ? null : MATE_GIRA[d.type];          // da «Appoggia»: il verso è già quello giusto
  const riga = k => s.rows.find(r => r[0] === k)?.[1] || '';
  const tipo = riga('Tipo').replace(/^./, c => c.toUpperCase()), scarto = riga('Scarto');
  const cos = `${tipo}${d.da === 'appoggia' ? ', messo da «Appoggia»' : d.da === 'vano' ? ', messo da «Metti nel vano»' : ''}${d.off ? ': sospeso, adesso non tiene' : ''}`;
  const campo = MATE_CAMPO[d.type] ? `<div class="ff"><label>${(d.da === 'appoggia' || d.da === 'vano') && d.type === 'distanza' ? 'Dal bordo' : MATE_CAMPO[d.type]}<span class="inp"><input class="field num" id="m-off" value="${v(d.offset)}"><i>mm</i></span></label><span></span></div>
      ${d.type === 'distanza' ? `<input type="range" class="cursore" id="m-slide" min="${Math.floor(Math.min(0, d.offset - 200))}" max="${Math.ceil(d.offset + 200)}" step="1" value="${d.offset}" title="Trascina: il pezzo si muove">` : ''}` : '';
  const angolo = d.type === 'angolo' ? `<div class="ff"><label>Angolo<span class="inp"><input class="field num" id="m-ang" value="${v(d.angle)}"><i>°</i></span></label><span></span></div>
      <input type="range" class="cursore" id="m-slide" min="0" max="180" step="1" value="${d.angle}" title="Trascina: il pezzo gira">
      <p class="hint">0° = una faccia contro l’altra, 90° = a squadra.</p>` : '';
  const pezzo = (k, id) => `<button class="asm-mate" data-vai-pezzo="${esc(id || '')}" title="Scegli il pezzo"><img src="icons/${k === 'Fermo' ? 'c_fix' : 'move'}.svg" alt=""><span><span class="testo-2">${k === 'Fermo' ? 'Sta fermo' : 'Si muove'}:</span> ${esc(riga(k))}</span></button>`;
  return `<div class="asm-pan"><div class="fhead"><div><h3>${esc(s.title)}</h3><div class="fsub">${esc(cos)}</div></div></div>
    <section class="sezione"><h4>Cosa puoi fare</h4><div class="asm-azioni una">${gira ? `<button class="btn" id="m-flip" title="${esc(gira[d.flip && gira[1] ? 1 : 0])}"><img src="icons/mirror.svg" alt=""><span>${esc(gira[d.flip && gira[1] ? 1 : 0].replace(/ \(.*$/, ''))}</span></button>` : ''}
      <button class="btn" id="m-sosp" title="${d.off ? 'Torna a tenere i due pezzi' : 'Per un momento non tiene: il pezzo resta dov’è e lo puoi spostare'}"><img src="icons/${d.off ? 'joint' : 'eye'}.svg" alt=""><span>${d.off ? 'Riattiva' : 'Sospendi'}</span></button>
      ${TOGLI_ASM('m-del', 'Togli l’accoppiamento', 'I due pezzi restano dove sono, liberi')}</div>
      <p class="hint">${MATE_COSA[d.type] ? esc(MATE_COSA[d.type]) + '.' : ''}</p></section>
    ${campo || angolo ? `<section class="sezione"><h4>Misura</h4>${campo}${angolo}</section>` : ''}
    <section class="sezione"><h4>I due pezzi</h4>${pezzo('Fermo', d.a)}${pezzo('Si muove', d.b)}</section>
    <details class="fsec"><summary>Dettagli</summary><table class="grid"><tr><td>Tipo</td><td>${esc(tipo)}</td></tr><tr><td>Scarto</td><td class="num">${esc(scarto)}</td></tr></table>
      <p class="hint">Lo scarto è quanto il risolutore non riesce a rispettare: vicino a zero va bene.</p></details>
    <div class="asm-fondo"><button class="btn primary big" id="m-fatto">Fatto</button></div></div>`;
}
function wireMate(s) {
  const fai = f => inCoda(async () => { if (await apply(await call('asm_edit_mate', s.id, f))) await refreshSel(); });
  if ($('#m-off')) { $('#m-off').onkeydown = ev => { if (ev.key === 'Enter') fai({ offset: $('#m-off').value.trim() }); }; $('#m-off').onchange = () => fai({ offset: $('#m-off').value.trim() }); }
  if ($('#m-ang')) { $('#m-ang').onkeydown = ev => { if (ev.key === 'Enter') fai({ angle: $('#m-ang').value.trim() }); }; $('#m-ang').onchange = () => fai({ angle: $('#m-ang').value.trim() }); }
  if ($('#m-flip')) $('#m-flip').onclick = () => fai({ flip: !s.def.flip });
  if ($('#m-slide')) cursoreMovimento($('#m-slide'), $('#m-off') || $('#m-ang'), s.id, s.def.type === 'angolo' ? 'angle' : 'offset');
  $('#m-sosp').onclick = () => fai({ off: !s.def.off });
  $('#m-del').onclick = () => { clearSelection(); inCoda(async () => apply(await call('asm_delete_mate', s.id))); };
  document.querySelectorAll('[data-vai-pezzo]').forEach(b => { if (b.dataset.vaiPezzo) b.onclick = () => inCoda(() => select(b.dataset.vaiPezzo)); });
  $('#m-fatto').onclick = () => { document.activeElement?.blur?.(); setTimeout(clearSelection, 30); };
  // 04/11: nel 3D, in giallo, il pezzo che questo accoppiamento muove (prima non si vedeva niente: di chi parla?)
  if (sel && sel.id === 'mate=' + s.id && s.def.b && objs.has(s.def.b)) { sel.ids = [sel.id, s.def.b]; paint(); }
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
const MIS_MAT = new THREE.LineBasicMaterial({ color: 0xFFB21A, depthTest: false });
const MIS_RUB = new THREE.LineDashedMaterial({ color: 0xFFB21A, dashSize: 4, gapSize: 3, depthTest: false });
var misEls = [];                                   // var: placeDims la legge già prima di qui
const misBox = document.createElement('div');
misBox.id = 'mis-box';
document.getElementById('dims').after(misBox);
const misSnap = document.createElement('div');
misSnap.id = 'mis-snap';
misBox.after(misSnap);
const chiaveMis = () => (S?.path || S?.name || 'nuovo') + (S?.mode === 'assembly' ? '#asm' : '');
const quoteDi = () => {
  const k = chiaveMis();
  if (!MISURE.has(k)) MISURE.set(k, S?.mode !== 'assembly' && Array.isArray(S?.quote) ? S.quote.map(q => ({ ...q })) : []);
  return MISURE.get(k);
};
// nel pezzo le quote si salvano nel progetto: vanno anche nelle tavole (nella vista dove si vedono vere)
const salvaQuote = () => { if (S?.mode !== 'assembly') call('set_quote', quoteDi()); };

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
// angolo (24/10): tre clic, un punto su un lato, il vertice, un punto sull'altro lato
const gradiTra = (a, v, b) => THREE.MathUtils.radToDeg(a.clone().sub(v).angleTo(b.clone().sub(v)));
function misStart(angolo = false) {
  if (SK) { toast('Nel disegno c’è già la Quota del disegno (tasto D).'); return; }
  if (MIS) misStop();
  MIS = { a: null, cand: misCandidati(), hover: null, angolo, pts: [] };
  document.querySelectorAll(`[data-cmd="${angolo ? 'misura_angolo' : 'misura'}"]`).forEach(b => b.classList.add('on'));
  setHelp(angolo ? 'Angolo: clic su un punto del primo lato, poi sul vertice, poi su un punto dell’altro lato · tasto destro su una misura per toglierla · Esc finisce'
    : 'Quota: clic sul primo punto (vertice, metà, centro) e sul secondo · clic sul bordo di un foro = diametro · tasto destro su una quota per toglierla · Esc finisce');
  $('#sk-foot').hidden = false;
}
function misStop() {
  MIS = null;
  document.querySelectorAll('[data-cmd="misura"], [data-cmd="misura_angolo"]').forEach(b => b.classList.remove('on'));
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
    tip.textContent = MIS.angolo ? (MIS.pts.length === 2 ? `${num(gradiTra(MIS.pts[0], MIS.pts[1], h.p), 1)}° · ${NOMI_AGGANCIO[h.tipo]}`
        : `${['primo lato', 'vertice'][MIS.pts.length]} · ${NOMI_AGGANCIO[h.tipo]}`)
      : MIS.a ? `${num(MIS.a.p.distanceTo(h.p), 2)} mm · ${NOMI_AGGANCIO[h.tipo]}` : NOMI_AGGANCIO[h.tipo];
    tip.style.left = (ev.clientX - r.left + 14) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px'; tip.style.display = 'block';
  } else { misSnap.style.display = 'none'; tip.style.display = 'none'; }
  disegnaMisure();
}
function misClick(ev) {
  const h = MIS.hover || misTrova(ev);
  if (!h) return;
  if (MIS.angolo) {
    if (MIS.pts.length && h.p.distanceTo(MIS.pts[MIS.pts.length - 1]) < 1e-6) return;
    MIS.pts.push(h.p.clone());
    if (MIS.pts.length === 3) {
      const [a, v, b] = MIS.pts;
      quoteDi().push({ a: a.toArray(), v: v.toArray(), b: b.toArray(), testo: num(gradiTra(a, v, b), 1) + '°' });
      salvaQuote();
      MIS.pts = [];
    }
    disegnaMisure(); return;
  }
  if (h.tipo === 'cerchio' && !MIS.a) {
    const lontano = h.giro.reduce((m, q) => (q.distanceTo(h.giro[0]) > m.distanceTo(h.giro[0]) ? q : m), h.giro[0]);
    quoteDi().push({ a: h.giro[0].toArray(), b: lontano.toArray(), testo: 'Ø' + num(2 * h.r, 2) });
    salvaQuote(); disegnaMisure(); return;
  }
  if (!MIS.a) { MIS.a = h; disegnaMisure(); return; }
  const a = MIS.a.p, b = h.p, d = a.distanceTo(b);
  if (d < 1e-6) return;
  const dx = Math.abs(b.x - a.x), dy = Math.abs(b.y - a.y), dz = Math.abs(b.z - a.z);
  quoteDi().push({ a: a.toArray(), b: b.toArray(), testo: num(d, 2), dett: `ΔX ${num(dx, 2)} · ΔY ${num(dy, 2)} · ΔZ ${num(dz, 2)}` });
  salvaQuote();
  MIS.a = null;
  disegnaMisure();
}
function disegnaMisure() {
  misGroup.traverse(x => x.geometry?.dispose()); misGroup.clear();
  misBox.innerHTML = ''; misEls = [];
  const lista = SK ? [] : quoteDi();
  lista.forEach((q, k) => {
    const a = new THREE.Vector3(...q.a), b = new THREE.Vector3(...q.b), v = q.v ? new THREE.Vector3(...q.v) : null;
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(v ? [a, v, b] : [a, b]), MIS_MAT); l.renderOrder = 30; misGroup.add(l);
    for (const p of v ? [a, v, b] : [a, b]) {
      const g = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.6, modelRadius * 0.004), 10, 8), new THREE.MeshBasicMaterial({ color: 0xFFB21A, depthTest: false }));
      g.position.copy(p); g.renderOrder = 30; misGroup.add(g);
    }
    const el = document.createElement('div');
    el.className = 'dim mis'; el.textContent = q.testo; el.title = (q.dett ? q.dett + '\n' : '') + 'Tasto destro: togli questa quota';
    el.oncontextmenu = ev => { ev.preventDefault(); quoteDi().splice(k, 1); salvaQuote(); disegnaMisure(); };
    misBox.appendChild(el);
    // l'angolo: la scritta sulla bisettrice, vicino al vertice
    const at = v ? v.clone().addScaledVector(a.clone().sub(v).normalize().add(b.clone().sub(v).normalize()).normalize(),
      Math.min(a.distanceTo(v), b.distanceTo(v)) * 0.35) : a.clone().add(b).multiplyScalar(0.5);
    misEls.push({ el, at });
  });
  if (MIS?.angolo && MIS.pts.length && MIS.hover) {
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([...MIS.pts, MIS.hover.p]), MIS_RUB);
    l.computeLineDistances(); l.renderOrder = 30; misGroup.add(l);
  }
  if (MIS?.a && MIS.hover) {
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([MIS.a.p, MIS.hover.p]), MIS_RUB);
    l.computeLineDistances(); l.renderOrder = 30; misGroup.add(l);
  }
  placeDims(); ridisegna();
}
function misTogliTutte() { quoteDi().length = 0; salvaQuote(); disegnaMisure(); }
document.addEventListener('keydown', ev => {
  if (!MIS || ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
  if (ev.key === 'Escape') { ev.stopPropagation(); ev.preventDefault(); if (MIS.a || MIS.pts?.length) { MIS.a = null; MIS.pts = []; disegnaMisure(); } else misStop(); }
}, true);

// ===================================================================== tavole
// ------------------------------------------------------------- tavole: l'editor (23/10)
// La tavola nasce automatica; qui la ritocchi col mouse: sposti le viste, clicchi una quota per spostarla, cambiarne il
// testo o nasconderla, aggiungi quote (due punti) e note, scegli l'altezza dei testi e cosa va nel cartiglio. I ritocchi
// si salvano nel progetto (con Annulla) e restano anche se il pezzo cambia.
// il simbolo di saldatura: tipo, misura, lunghezza, lato, tutto intorno, in opera (ISO 2553)
function saldaturaDialog(q, fatto) {
  const tipi = [['angolo', 'D’angolo (a gola)'], ['V', 'Di testa a V'], ['I', 'Di testa a I (lembi dritti)']];
  modal(`<h3>Saldatura</h3><div class="te-form">
    <label class="te-riga">Tipo<select class="field" id="sd-tipo">${tipi.map(([v, t]) => `<option value="${v}"${q.tipo === v ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="te-riga">Misura<span class="te-mm"><input class="field" id="sd-a" value="${esc(q.a || '')}" placeholder="a gola, es. 4"><i>mm</i></span></label>
    <label class="te-riga">Lunghezza<input class="field" id="sd-l" value="${esc(q.l || '')}" placeholder="vuoto = tutto il giunto"></label>
    <label class="te-riga">Lato<select class="field" id="sd-lato"><option value="freccia"${q.lato !== 'altro' ? ' selected' : ''}>dalla parte della freccia</option><option value="altro"${q.lato === 'altro' ? ' selected' : ''}>dalla parte opposta</option></select></label>
    <label class="check"><input type="checkbox" id="sd-giro"${q.giro ? ' checked' : ''}> Tutto intorno</label>
    <label class="check"><input type="checkbox" id="sd-opera"${q.opera ? ' checked' : ''}> In opera (in cantiere)</label></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Metti la saldatura</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const r = { tipo: $('#sd-tipo').value, a: $('#sd-a').value.trim(), l: $('#sd-l').value.trim(), lato: $('#sd-lato').value,
        giro: $('#sd-giro').checked, opera: $('#sd-opera').checked };
      close(); fatto(r);
    };
    setTimeout(() => $('#sd-a').focus(), 30);
  });
}
// la distinta della tavola d'assieme, da ritoccare a mano (28/10): una tabella come quella stampata. Le righe
// automatiche si cambiano cella per cella (vuoto = come la fa Radius) o si tolgono; in fondo le righe in più.
function distintaDialog(o, d, fatto) {
  const celle = { ...(d.celle || {}) }, via = new Set((d.via || []).map(Number)), nuove = (d.nuove || []).map(r => [...r]);
  const nc = o.intest.length;
  const larghe = [52, 0, 60, 104, 84, 90, 76];
  const riga = (cls, i, valori, orig) => `<tr class="${cls}" data-r="${i}">${valori.map((v, j) =>
    `<td><input class="field" data-c="${j}" value="${esc(v)}"${orig ? ` placeholder="${esc(orig[j] ?? '')}"` : ''}></td>`).join('')}
    <td><button class="btn dd-via" data-via title="${cls === 'nuova' ? 'Togli questa riga' : 'Togli questa riga dalla distinta'}">×</button></td></tr>`;
  const disegna = () => {
    const corpo = o.righe.map((r, i) => via.has(i) ? '' : riga('auto', i, r.map((v, j) => celle[`${i}:${j}`] ?? v), r)).join('')
      + nuove.map((r, i) => riga('nuova', i, Array.from({ length: nc }, (_, j) => r[j] ?? ''), null)).join('');
    $('#dd-corpo').innerHTML = corpo;
    $('#dd-tolte').hidden = !via.size;
    $('#dd-tolte').textContent = `Rimetti le righe tolte (${via.size})`;
    $('#dd-corpo').querySelectorAll('input').forEach(inp => { inp.oninput = () => {
      const tr = inp.closest('tr'), i = +tr.dataset.r, j = +inp.dataset.c;
      if (tr.classList.contains('nuova')) nuove[i][j] = inp.value;
      else if (inp.value === String(o.righe[i][j] ?? '')) delete celle[`${i}:${j}`];
      else celle[`${i}:${j}`] = inp.value;
    }; });
    $('#dd-corpo').querySelectorAll('[data-via]').forEach(b => { b.onclick = () => {
      const tr = b.closest('tr'), i = +tr.dataset.r;
      if (tr.classList.contains('nuova')) nuove.splice(i, 1); else via.add(i);
      disegna();
    }; });
  };
  modal(`<h3>Distinta</h3>
    <p class="hint dd-aiuto">Scrivi sopra le celle per cambiarle; × toglie una riga. Le righe automatiche seguono l’assieme: se cambi un pezzo, il resto si aggiorna.</p>
    <div class="dd-scorri"><table class="dd-tab"><colgroup>${larghe.slice(0, nc).map(w => `<col${w ? ` style="width:${w}px"` : ''}>`).join('')}<col style="width:40px"></colgroup>
      <thead><tr>${o.intest.map(t => `<th>${esc(t)}</th>`).join('')}<th></th></tr></thead><tbody id="dd-corpo"></tbody></table></div>
    <div class="te-bott"><button class="btn" id="dd-piu">+ Riga in più</button><button class="btn" id="dd-tolte" hidden></button></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Metti nella tavola</button></div>`, close => {
    disegna();
    $('#dd-piu').onclick = () => {
      const pos = String(o.righe.length - via.size + nuove.length + 1);
      nuove.push([pos, ...Array(nc - 1).fill('')]); disegna();
      const ult = $('#dd-corpo').querySelector('tr.nuova:last-child input[data-c="1"]'); if (ult) ult.focus();
    };
    $('#dd-tolte').onclick = () => { via.clear(); disegna(); };
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      const pulite = nuove.filter(r => r.some((v, j) => j > 0 && String(v).trim()));
      const nuova = {};
      if (Object.keys(celle).length) nuova.celle = celle;
      if (via.size) nuova.via = [...via].sort((a, b) => a - b);
      if (pulite.length) nuova.nuove = pulite;
      close(); fatto(Object.keys(nuova).length ? nuova : null);
    };
  });
  $('#modal-box').classList.add('wide');
}

async function drawingsDialog() {
  const torna = tornaPrepara; tornaPrepara = null;              // aperte da «Prepara»: alla chiusura si torna lì
  const r = await call('drawing_fields');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const c = r.fields;
  const ED = { fogli: [], k: 0, sel: null, strumento: 'sel', punto1: null, modificabili: true, vb: null, ang: [], sald: null };
  const box = document.createElement('div');
  box.id = 'tav-ed';
  const campo = (k, l) => `<label class="te-riga">${l}<input class="field" data-c="${k}" value="${esc(c[k] || '')}"></label>`;
  const scelta = (k, l, opz) => `<label class="te-riga">${l}<select class="field" data-c="${k}">${opz.map(([v, t]) =>
    `<option value="${esc(v)}"${String(c[k] ?? opz[0][0]) === v ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  box.innerHTML = `<header class="te-testa"><b class="te-titolo" title="${esc(S?.name || '')}"><i class="te-modo">Tavole</i><span>${esc(S?.name || '')}</span></b>
      <span class="te-sepv"></span>
      <button class="btn te-quieto" id="te-adatta" title="Il foglio intero (rotella: zoom; tasto centrale: sposta)"><img src="icons/fit.svg" alt="">Adatta</button>
      <button class="btn te-quieto" id="te-undo" title="Annulla l’ultimo ritocco (Ctrl+Z)"><img src="icons/undo.svg" alt="">Annulla ritocco</button>
      <span class="te-spazio"></span>
      <button class="btn" id="te-dxf" title="Le tavole in DXF, per chi le apre col CAD">Esporta DXF</button><button class="btn primary" id="te-pdf" title="Le tavole in PDF, da stampare o mandare">Esporta PDF</button>
      <span class="te-sepv"></span>
      <button class="btn te-quieto" id="te-chiudi" title="Torna al pezzo (Esc)">Chiudi</button></header>
    <div class="te-tabs" id="te-tabs" role="tablist"></div>
    <div class="te-corpo">
      <nav class="te-strumenti" aria-label="Strumenti">
        <button data-str="sel" class="on" title="Clicca una vista, una quota o una nota; trascina per spostarla"><img src="icons/select.svg" alt=""><span>Seleziona</span></button>
        <span class="te-gruppo">Aggiungi</span>
        <button data-str="quota" title="Una quota nuova: clicca due punti della stessa vista (si agganciano agli spigoli). Maiusc = inclinata"><img src="icons/dimension.svg" alt=""><span>Quota</span></button>
        <button data-str="nota" title="Una nota: clicca dove va e scrivi"><img src="icons/text.svg" alt=""><span>Nota</span></button>
        <button data-str="diametro" title="Diametro o raggio: clicca un cerchio o un arco di una vista, dove vuoi la scritta"><img src="icons/hole.svg" alt=""><span>Ø / R</span></button>
        <button data-str="angolo" title="Angolo: clicca un punto su un lato, il vertice, un punto sull’altro lato"><img src="icons/plane_angle.svg" alt=""><span>Angolo</span></button>
        <button data-str="saldatura" title="Saldatura: clicca il giunto (la punta della freccia), poi dove va il simbolo"><img src="icons/saldatura.svg" alt=""><span>Saldatura</span></button>
        <button data-str="dettaglio" title="Dettaglio ingrandito: clicca il centro della zona su una vista, poi quanto è grande il cerchio"><img src="icons/zoom.svg" alt=""><span>Dettaglio</span></button>
      </nav>
      <div class="te-centro"><main class="te-foglio" id="te-foglio"><p class="hint te-attesa">Preparo la tavola…</p></main>
        <div class="te-passo" id="te-passo" hidden></div></div>
      <aside class="te-lato">
        <section id="te-persi" hidden></section>
        <section id="te-sel" hidden></section>
        <details class="te-sez" open><summary>Foglio</summary>
          ${scelta('formato', 'Formato', [['A4', 'A4'], ['A3', 'A3'], ['A2', 'A2']])}
          ${scelta('scala_fissa', 'Scala', ['auto', '2:1', '1:1', '1:2', '1:2,5', '1:5', '1:10', '1:15', '1:20', '1:25', '1:50'].map(x => [x, x === 'auto' ? 'automatica' : x]))}
          ${scelta('quote_fori', 'Quote dei fori', [['sì', 'sì'], ['no', 'no']])}
          ${scelta('fianco', 'Vista di fianco', [['sinistra', 'da sinistra'], ['destra', 'da destra']])}
          ${scelta('isometrica', 'Isometrica', [['sì', 'sì'], ['no', 'no']])}
          ${scelta('sezione', 'Sezione', [['', 'nessuna'], ['X', 'A-A lungo la larghezza'], ['Y', 'A-A lungo la profondità']])}
          ${r.assembly ? '<label class="check"><input type="checkbox" id="tav-tutte" checked> anche le tavole di tutti i pezzi</label>' : ''}
        </details>
        <details class="te-sez"><summary>Altezza dei testi</summary>
          <label class="te-riga">Quote<span class="te-mm"><input class="field" data-t="quote"><i>mm</i></span></label>
          <label class="te-riga">Frecce delle quote<span class="te-mm"><input class="field" data-t="frecce"><i>mm</i></span></label>
          <label class="te-riga">Note<span class="te-mm"><input class="field" data-t="note"><i>mm</i></span></label>
          <label class="te-riga">Titoli delle viste<span class="te-mm"><input class="field" data-t="titoli"><i>mm</i></span></label>
          <p class="hint">Vuoto = come la fa il programma. Le frecce seguono il testo, se non scrivi niente.</p>
        </details>
        <details class="te-sez"><summary>Cartiglio</summary>
          ${campo('azienda', 'Azienda')}${campo('numero', 'N. disegno')}${campo('revisione', 'Revisione')}
          ${campo('disegnatore', 'Disegnato')}${campo('approvato', 'Approvato')}
          ${campo('cliente', 'Cliente')}${campo('commessa', 'Commessa')}${campo('tolleranze', 'Tolleranze generali')}${campo('finitura', 'Trattamento / finitura')}
          ${campo('note', 'Note')}
          <div class="te-rev"><span class="hint">Revisioni (la più nuova va in alto nel cartiglio)</span>
            <div class="te-rev-g"><b>Rev.</b><b>Data</b><b>Descrizione</b><b>Da</b>
            ${[0, 1, 2].map(i => ['rev', 'data', 'descrizione', 'da'].map(k => `<input class="field" data-rev="${i}:${k}" value="${esc(((c.revisioni || [])[i] || {})[k] || '')}">`).join('')).join('')}</div></div>
          <p class="hint">${r.logo ? 'Il logo dell’azienda è nel cartiglio.' : 'Il logo dell’azienda si mette in Impostazioni → Tavole e cartiglio.'}</p>
        </details>
        <details class="te-sez" open><summary>I tuoi ritocchi <span class="te-conta" id="te-rit-n" hidden></span></summary><div id="te-rit"></div>
          <button class="btn" id="te-auto" title="Toglie tutti i ritocchi di questo foglio: torna come la fa il programma">Rimetti automatico</button></details>
      </aside>
    </div>`;
  document.body.appendChild(box);
  const chiudi = () => { box.remove(); document.removeEventListener('keydown', tasti, true);
    if (ED.toccato) inCoda(async () => { const st = await call('state'); if (st && st.version) { S = st; renderPanels(); } });
    if (torna) inCoda(() => preparaDialog(torna)); };
  const leggi = () => {
    const o = {};
    box.querySelectorAll('[data-c]').forEach(i => { o[i.dataset.c] = i.value.trim(); });
    o.revisioni = [0, 1, 2].map(i => Object.fromEntries(['rev', 'data', 'descrizione', 'da'].map(k => [k, box.querySelector(`[data-rev="${i}:${k}"]`).value.trim()])))
      .filter(r => Object.values(r).some(Boolean));
    return o;
  };
  const tutte = () => !!box.querySelector('#tav-tutte')?.checked;
  const foglio = () => ED.fogli[ED.k];
  window.__tavole = { ED, foglio };                 // per le prove automatiche
  const rit = () => JSON.parse(JSON.stringify(foglio()?.ritocchi || {}));
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : null; };
  const mm = v => String(Math.round(v * 10) / 10).replace('.', ',');

  // ---- disegno del foglio e selezione
  const svgDi = () => box.querySelector('#te-foglio svg');
  const H = () => foglio().size[1];
  const aFoglio = ev => {                          // dal mouse al foglio: mm, y in su
    const svg = svgDi(), p = svg.createSVGPoint();
    p.x = ev.clientX; p.y = ev.clientY;
    const q = p.matrixTransform(svg.getScreenCTM().inverse());
    return [q.x, H() - q.y];
  };
  const oggettoDi = tag => {                       // il più preciso tra gli oggetti che contengono quel pezzo di disegno
    if (!tag) return null;
    let best = null;
    for (const o of foglio().oggetti) if ((tag === o.id || tag.startsWith(o.id + '/')) && (!best || o.id.length > best.id.length)) best = o;
    return best;
  };
  const evidenzia = () => {
    const svg = svgDi();
    if (!svg) return;
    svg.querySelectorAll('.te-evid').forEach(e => e.remove());
    const o = ED.sel && foglio().oggetti.find(x => x.id === ED.sel);
    if (!o) return;
    const [x0, y0, x1, y1] = o.bbox, m = 1.2;
    const r_ = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r_.setAttribute('class', 'te-evid'); r_.setAttribute('x', x0 - m); r_.setAttribute('y', H() - y1 - m);
    r_.setAttribute('width', x1 - x0 + 2 * m); r_.setAttribute('height', y1 - y0 + 2 * m);
    svg.appendChild(r_);
  };
  const disegna = () => {
    const f = foglio();
    if (!f) return;
    box.querySelector('#te-foglio').innerHTML = f.svg.replace(/width="[\d.]+mm" height="[\d.]+mm"/, 'width="100%" height="100%"');
    if (ED.vb && ED.vbFoglio === ED.k) svgDi().setAttribute('viewBox', ED.vb.join(' ')); else ED.vb = null;
    box.querySelectorAll('#te-tabs button').forEach((b, i) => { b.classList.toggle('on', i === ED.k); if (i === ED.k) b.scrollIntoView({ block: 'nearest', inline: 'nearest' }); });
    const t = f.ritocchi?.testi || {}, k = f.fattore || 1, base = { quote: 2.8, frecce: 2.5, note: 3.5, titoli: 2.5 };
    box.querySelectorAll('[data-t]').forEach(i => {
      i.placeholder = mm(base[i.dataset.t] * k * (i.dataset.t === 'frecce' && t.quote ? t.quote / (2.8 * k) : 1));
      if (document.activeElement !== i) i.value = t[i.dataset.t] != null ? String(t[i.dataset.t]).replace('.', ',') : '';
    });
    evidenzia(); pannelloSel(); elencoRitocchi();
  };
  const carica = p => {
    if (!p.ok) { box.querySelector('#te-foglio').innerHTML = `<div class="msg err">${esc(p.message)}</div>`; return; }
    ED.fogli = p.sheets; ED.modificabili = p.modificabili !== false;
    if (ED.k >= ED.fogli.length) ED.k = 0;
    // «Cassone — sviluppo»: il nome del pezzo e, piccolo, che foglio è (sviluppo, esploso…)
    box.querySelector('#te-tabs').innerHTML = ED.fogli.map((f, i) => {
      const [nome, ...tipo] = String(f.title || '').split(' — ');
      return `<button data-i="${i}" role="tab" title="${esc(f.title)}"><i>${i + 1}</i><span>${esc(nome)}</span>${tipo.length ? `<small>${esc(tipo.join(' — '))}</small>` : ''}</button>`;
    }).join('');
    box.querySelectorAll('#te-tabs button').forEach(b => { b.onclick = () => { ED.k = +b.dataset.i; ED.sel = null; disegna(); }; });
    if (ED.sel && !foglio().oggetti.some(o => o.id === ED.sel)) ED.sel = null;
    disegna();
  };
  const aggiorna = () => inCoda(async () => carica(await call('drawing_preview', leggi(), tutte())));
  const salva = nuovi => {                          // i ritocchi del foglio aperto, tutti insieme
    if (!ED.modificabili) { toast('Le tavole degli assiemi non si ritoccano ancora: aprile dal pezzo.', 'err'); return; }
    const ch = foglio().chiave;
    inCoda(async () => {
      // 29/10: torna solo il foglio toccato (prima tutte le tavole e lo stato intero del pezzo: lentissimo coi fori)
      const p = await call('tavola_ritocchi', ch, nuovi, leggi(), tutte());
      if (!p.ok) { toast(p.message, 'err'); return; }
      ED.toccato = true;
      const i = ED.fogli.findIndex(f => f.chiave === ch);
      if (p.foglio && i >= 0) ED.fogli[i] = p.foglio;
      if (ED.sel && !foglio().oggetti.some(o => o.id === ED.sel)) ED.sel = null;
      disegna();
    });
  };

  // ---- il pannello dell'oggetto selezionato
  function pannelloSel() {
    const sez = box.querySelector('#te-sel');
    const o = ED.sel && foglio()?.oggetti.find(x => x.id === ED.sel);
    sez.hidden = !o;
    if (!o) return;
    const R_ = rit();
    if (o.kind === 'quota') {
      const q = (R_.quote || {})[o.id] || {};
      const agg = o.aggiunta != null;
      sez.innerHTML = `<h4>${esc(o.label)}</h4>
        <label class="te-riga">Testo<input class="field" id="ts-testo" value="${esc(q.testo || '')}" placeholder="${esc(o.testo)}"></label>
        <label class="te-riga">Altezza<span class="te-mm"><input class="field" id="ts-h" value="${q.h ? String(q.h).replace('.', ',') : ''}" placeholder="${mm(o.h)}"><i>mm</i></span></label>
        <label class="te-riga">Frecce<span class="te-mm"><input class="field" id="ts-fr" value="${q.freccia ? String(q.freccia).replace('.', ',') : ''}" placeholder="${mm(o.freccia)}"><i>mm</i></span></label>
        <p class="hint">Trascinala per allontanarla o avvicinarla al pezzo.</p>
        <div class="te-bott">${agg ? '<button class="btn danger" id="ts-via">Togli questa quota</button>' : '<button class="btn" id="ts-via">Nascondi</button>'}
          ${!agg && (R_.quote || {})[o.id] ? '<button class="btn" id="ts-rimetti">Rimetti com’era</button>' : ''}</div>`;
      const cambia = () => { const n = rit(); n.quote = n.quote || {}; const m = n.quote[o.id] || {};
        const t = $('#ts-testo').value.trim(), h = num($('#ts-h').value), fr = num($('#ts-fr').value);
        if (t) m.testo = t; else delete m.testo;
        if (h) m.h = h; else delete m.h;
        if (fr) m.freccia = fr; else delete m.freccia;
        n.quote[o.id] = m; salva(n); };
      $('#ts-testo').onchange = cambia; $('#ts-h').onchange = cambia; $('#ts-fr').onchange = cambia;
      $('#ts-via').onclick = () => { const n = rit();
        if (agg) n.aggiunte.splice(o.aggiunta, 1); else { n.quote = n.quote || {}; n.quote[o.id] = { ...(n.quote[o.id] || {}), via: true }; }
        ED.sel = null; salva(n); };
      if ($('#ts-rimetti')) $('#ts-rimetti').onclick = () => { const n = rit(); delete n.quote[o.id]; salva(n); };
    } else if (o.kind === 'vista' && o.id.startsWith('dettaglio:')) {
      const lettera = o.id.slice(10), i = (R_.dettagli || []).findIndex(d => d.lettera === lettera), d = (R_.dettagli || [])[i] || {};
      sez.innerHTML = `<h4>${esc(o.label)}</h4><p class="hint">Trascinalo dove vuoi. Le quote si aggiungono anche qui, come sulle altre viste.</p>
        <label class="te-riga">Ingrandimento<select class="field" id="ts-k">${[1.5, 2, 2.5, 3, 4, 5, 10].map(k => `<option value="${k}"${+d.k === k ? ' selected' : ''}>× ${String(k).replace('.', ',')}</option>`).join('')}</select></label>
        <div class="te-bott"><button class="btn danger" id="ts-via">Togli il dettaglio</button></div>`;
      $('#ts-k').onchange = () => {                  // cresce verso destra: il bordo sinistro resta dov'è
        const n = rit(), dd = n.dettagli[i], vv = foglio().oggetti.find(x => x.id === dd.vista), k2 = +$('#ts-k').value;
        if (vv) { const Rk = dd.r * vv.T[0] * k2, W = foglio().size[0];
          dd.p[0] = Math.min(W - Rk - 12 * (foglio().fattore || 1), dd.p[0] + dd.r * vv.T[0] * (k2 - (dd.k || 2))); }   // dentro il foglio
        dd.k = k2; salva(n); };
      $('#ts-via').onclick = () => { const n = rit(); n.dettagli.splice(i, 1); if (n.viste) delete n.viste[o.id]; ED.sel = null; salva(n); };
    } else if (o.kind === 'vista') {
      const sp = (R_.viste || {})[o.id];
      const figlia = ['vista:alto', 'vista:sinistra', 'vista:destra'].includes(o.id) && foglio().oggetti.some(x => x.id === 'vista:fronte');
      const libera = (R_.libere || []).includes(o.id);
      const aiuto = o.id === 'vista:fronte' ? 'Trascinala dove vuoi: le sue quote e le viste allineate (dall’alto, da sinistra) vengono con lei.'
        : figlia && !libera ? (o.id === 'vista:alto' ? 'Resta sotto la vista di fronte: si sposta solo in su e in giù.' : 'Resta accanto alla vista di fronte: si sposta solo di lato.')
        : 'Trascinala dove vuoi: le sue quote vengono con lei.';
      // 03/11: «e le viste?»: la scala delle viste (tutte e tre insieme, il cartiglio la scrive), l'isometrica in %
      const iso = o.id === 'vista:iso', scelta = R_.scala || '';
      const SCALE_V = ['1:1', '1:2', '1:2,5', '1:5', '1:10', '1:15', '1:20', '1:25', '1:50'];
      const grand = iso ? `<div class="te-riga te-pila">Grandezza<div class="fp-len"><button type="button" class="pm" id="ts-imeno" aria-label="Più piccola">−</button>
          <span class="inp"><input class="field" id="ts-ik" value="${Math.round((R_.iso || 1) * 100)}"><i>%</i></span>
          <button type="button" class="pm" id="ts-ipiu" aria-label="Più grande">+</button></div></div>`
        : `<label class="te-riga">Scala<select class="field" id="ts-scala"><option value="">come il foglio${!scelta && foglio().scala ? ' (' + esc(foglio().scala) + ')' : ''}</option>
          ${SCALE_V.map(x => `<option value="${x}"${scelta === x ? ' selected' : ''}>${x}</option>`).join('')}</select></label>
          <p class="hint">Vale per tutte le viste del foglio (restano allineate); il cartiglio scrive la scala.</p>`;
      sez.innerHTML = `<h4>${esc(o.label)}</h4><p class="hint">${aiuto}</p>
        ${grand}
        ${figlia ? `<label class="check"><input type="checkbox" id="ts-allinea"${libera ? '' : ' checked'}> allineata alla vista di fronte</label>` : ''}
        <div class="te-bott">${sp ? '<button class="btn" id="ts-rimetti">Rimetti al suo posto</button>' : ''}
          ${o.id !== 'vista:fronte' ? '<button class="btn danger" id="ts-togli">Togli questa vista</button>' : ''}</div>`;
      if ($('#ts-scala')) $('#ts-scala').onchange = () => { const n = rit(), v = $('#ts-scala').value; if (v) n.scala = v; else delete n.scala; salva(n); };
      if (iso) {
        const pc = Math.round((R_.iso || 1) * 100);
        const metti = v => { const n = rit(); v = Math.max(40, Math.min(250, Math.round(v))); if (v === 100) delete n.iso; else n.iso = v / 100; salva(n); };
        $('#ts-imeno').onclick = () => metti(pc - 10);
        $('#ts-ipiu').onclick = () => metti(pc + 10);
        $('#ts-ik').onchange = () => { const v = parseFloat($('#ts-ik').value.replace(',', '.')); if (v > 0) metti(v); };
      }
      if ($('#ts-togli')) $('#ts-togli').onclick = () => { const n = rit(); n.tolte = [...new Set([...(n.tolte || []), o.id])]; ED.sel = null; salva(n); };
      if ($('#ts-rimetti')) $('#ts-rimetti').onclick = () => { const n = rit(); delete n.viste[o.id]; salva(n); };
      if ($('#ts-allinea')) $('#ts-allinea').onchange = () => { const n = rit(); const l = new Set(n.libere || []);
        if ($('#ts-allinea').checked) l.delete(o.id); else l.add(o.id);
        n.libere = [...l]; if (!n.libere.length) delete n.libere; salva(n); };
    } else if (o.kind === 'nota') {
      const nt = (R_.note || [])[o.indice] || {};
      sez.innerHTML = `<h4>Nota</h4><label class="te-riga te-alto">Testo<textarea class="field" id="ts-nota" rows="3">${esc(nt.testo || '')}</textarea></label>
        <label class="te-riga">Altezza<span class="te-mm"><input class="field" id="ts-h" value="${nt.h ? String(nt.h).replace('.', ',') : ''}" placeholder="${mm(o.h)}"><i>mm</i></span></label>
        <div class="te-bott"><button class="btn danger" id="ts-via">Togli la nota</button></div>`;
      const cambia = () => { const n = rit(); const m = n.note[o.indice]; m.testo = $('#ts-nota').value; const h = num($('#ts-h').value); if (h) m.h = h; else delete m.h; salva(n); };
      $('#ts-nota').onchange = cambia; $('#ts-h').onchange = cambia;
      $('#ts-via').onclick = () => { const n = rit(); n.note.splice(o.indice, 1); ED.sel = null; salva(n); };
    } else if (['diametro', 'angolo', 'saldatura'].includes(o.kind)) {
      const lista = { diametro: 'diametri', angolo: 'angoli', saldatura: 'saldature' }[o.kind], m = (R_[lista] || [])[o.indice] || {};
      sez.innerHTML = `<h4>${esc(o.label)}</h4>
        ${o.kind === 'diametro' ? `<div class="seg" id="ts-tipo">${[['Ø', 'Diametro'], ['R', 'Raggio']].map(([v, t]) => `<button type="button" data-v="${v}" class="${(m.tipo || 'Ø') === v ? 'on' : ''}">${t}</button>`).join('')}</div>` : ''}
        ${o.kind !== 'saldatura' ? `<label class="te-riga">Testo<input class="field" id="ts-testo" value="${esc(m.testo || '')}" placeholder="automatico"></label>` : ''}
        <p class="hint">${o.kind === 'saldatura' ? 'Trascinalo per spostare il simbolo (la freccia resta sul giunto).' : 'Trascinala per spostarla.'}</p>
        <div class="te-bott">${o.kind === 'saldatura' ? '<button class="btn" id="ts-modifica">Cambia…</button>' : ''}<button class="btn danger" id="ts-via">Togli</button></div>`;
      const cambia = f => { const n = rit(); f(n[lista][o.indice]); salva(n); };
      if ($('#ts-tipo')) $('#ts-tipo').querySelectorAll('button').forEach(b => { b.onclick = () => cambia(x => { x.tipo = b.dataset.v; }); });
      if ($('#ts-testo')) $('#ts-testo').onchange = () => cambia(x => { const t = $('#ts-testo').value.trim(); if (t) x.testo = t; else delete x.testo; });
      if ($('#ts-modifica')) $('#ts-modifica').onclick = () => saldaturaDialog(m, q => cambia(x => Object.assign(x, q)));
      $('#ts-via').onclick = () => { const n = rit(); n[lista].splice(o.indice, 1); ED.sel = null; salva(n); };
    } else if (o.kind === 'distinta') {
      // 28/10: «la distinta non posso modificarla»: celle, righe tolte, righe in più (restano anche se l'assieme cambia)
      const d = R_.distinta || {}, nc = Object.keys(d.celle || {}).length, nv = (d.via || []).length, nn = (d.nuove || []).length;
      const cosa = [nc && `${nc} ${nc === 1 ? 'cella cambiata' : 'celle cambiate'}`, nv && `${nv} ${nv === 1 ? 'riga tolta' : 'righe tolte'}`,
        nn && `${nn} ${nn === 1 ? 'riga in più' : 'righe in più'}`].filter(Boolean).join(', ');
      sez.innerHTML = `<h4>Distinta</h4><p class="hint">${cosa ? 'Ritoccata: ' + esc(cosa) + '.' : 'Quella automatica, dai pezzi dell’assieme.'}
        Trascinala per spostarla.</p>
        ${grandezzaHtml(o.id)}
        <div class="te-bott"><button class="btn" id="ts-dist">Modifica la distinta…</button>
          ${cosa ? '<button class="btn" id="ts-dist-auto">Torna automatica</button>' : ''}</div>`;
      grandezzaTabella(o.id);
      $('#ts-dist').onclick = () => distintaDialog(o, d, nuova => { const n = rit(); if (nuova) n.distinta = nuova; else delete n.distinta; salva(n); });
      if ($('#ts-dist-auto')) $('#ts-dist-auto').onclick = () => { const n = rit(); delete n.distinta; salva(n); };
    } else if (o.kind === 'tabella') {
      // 03/11: «la distinta di taglio non posso ingrandirla come le viste»: grandezza e posto (titolo e totali con lei)
      sez.innerHTML = `<h4>${esc(o.label)}</h4><p class="hint">Trascinala per spostarla: i totali per profilo vengono con lei.</p>
        ${grandezzaHtml(o.id)}`;
      grandezzaTabella(o.id);
    } else if (o.kind === 'cartiglio') {
      // 29/10: il cartiglio si ingrandisce e si rimpicciolisce (resta nell'angolo in basso a destra)
      const k = +(R_.cartiglio || 1), pc = Math.round(k * 100);
      sez.innerHTML = `<h4>Cartiglio</h4><p class="hint">I campi stanno qui sotto, in «Cartiglio».</p>
        <div class="te-riga te-pila">Grandezza<div class="fp-len"><button type="button" class="pm" id="ts-cmeno" aria-label="Più piccolo">−</button>
          <span class="inp"><input class="field" id="ts-ck" value="${pc}"><i>%</i></span>
          <button type="button" class="pm" id="ts-cpiu" aria-label="Più grande">+</button></div></div>
        ${k !== 1 ? '<div class="te-bott"><button class="btn" id="ts-c100">Grandezza normale</button></div>' : ''}`;
      const metti = v => { const n = rit(); v = Math.max(40, Math.min(250, Math.round(v))); if (v === 100) delete n.cartiglio; else n.cartiglio = v / 100; salva(n); };
      $('#ts-cmeno').onclick = () => metti(pc - 10);
      $('#ts-cpiu').onclick = () => metti(pc + 10);
      $('#ts-ck').onchange = () => { const v = parseFloat($('#ts-ck').value.replace(',', '.')); if (v > 0) metti(v); };
      if ($('#ts-c100')) $('#ts-c100').onclick = () => metti(100);
      const d = box.querySelectorAll('.te-sez')[2]; if (d) d.open = true;
    }
  }
  // 03/11: grandezza (in %) e spostamento delle tabelle: ritocchi.tabelle[id] = {k, d: [dx, dy]}
  function grandezzaHtml(id) {
    const t = ((foglio().ritocchi || {}).tabelle || {})[id] || {}, pc = Math.round((t.k || 1) * 100);
    return `<div class="te-riga te-pila">Grandezza<div class="fp-len"><button type="button" class="pm" id="ts-tmeno" aria-label="Più piccola">−</button>
        <span class="inp"><input class="field" id="ts-tk" value="${pc}"><i>%</i></span>
        <button type="button" class="pm" id="ts-tpiu" aria-label="Più grande">+</button></div></div>
      ${pc !== 100 || t.d ? '<div class="te-bott"><button class="btn" id="ts-t100">Grandezza e posto normali</button></div>' : ''}`;
  }
  function grandezzaTabella(id) {
    const pc = Math.round((((foglio().ritocchi || {}).tabelle || {})[id]?.k || 1) * 100);
    const metti = v => { const n = rit(); n.tabelle = n.tabelle || {}; const t = n.tabelle[id] || {};
      v = Math.max(40, Math.min(250, Math.round(v)));
      if (v === 100) delete t.k; else t.k = v / 100;
      if (Object.keys(t).length) n.tabelle[id] = t; else delete n.tabelle[id];
      if (!Object.keys(n.tabelle).length) delete n.tabelle;
      salva(n); };
    $('#ts-tmeno').onclick = () => metti(pc - 10);
    $('#ts-tpiu').onclick = () => metti(pc + 10);
    $('#ts-tk').onchange = () => { const v = parseFloat($('#ts-tk').value.replace(',', '.')); if (v > 0) metti(v); };
    if ($('#ts-t100')) $('#ts-t100').onclick = () => { const n = rit(); if (n.tabelle) { delete n.tabelle[id]; if (!Object.keys(n.tabelle).length) delete n.tabelle; } salva(n); };
  }
  // ---- l'elenco dei ritocchi, ognuno con ×
  const ETICHETTE_TAV = { 'vista:fronte': 'Vista di fronte', 'vista:alto': 'Vista dall’alto', 'vista:sinistra': 'Vista da sinistra',
    'vista:destra': 'Vista da destra', 'vista:iso': 'Isometrica' };
  function elencoRitocchi() {
    const R_ = foglio()?.ritocchi || {}, nomi = Object.fromEntries((foglio()?.oggetti || []).map(o => [o.id, o.label]));
    const righe = [];
    for (const v of Object.keys(R_.viste || {})) righe.push([`${nomi[v] || v} spostata`, n => { delete n.viste[v]; }]);
    for (const [q, m] of Object.entries(R_.quote || {})) {
      const cosa = m.via ? 'nascosta' : [m.testo ? `testo «${m.testo}»` : '', m.d ? 'spostata' : '', m.h ? `altezza ${mm(m.h)}` : '',
        m.freccia ? `frecce ${mm(m.freccia)}` : ''].filter(Boolean).join(', ');
      righe.push([`${nomi[q] || 'Quota'}: ${cosa || 'cambiata'}`, n => { delete n.quote[q]; }]);
    }
    (R_.aggiunte || []).forEach((a, i) => righe.push([`Quota aggiunta (${a.vista.replace('vista:', '')})`, n => { n.aggiunte.splice(i, 1); }]));
    (R_.note || []).forEach((a, i) => righe.push([`Nota «${String(a.testo).slice(0, 24)}»`, n => { n.note.splice(i, 1); }]));
    (R_.diametri || []).forEach((a, i) => righe.push([`${a.tipo === 'R' ? 'Raggio' : 'Diametro'} (${a.vista.replace('vista:', '')})`, n => { n.diametri.splice(i, 1); }]));
    (R_.angoli || []).forEach((a, i) => righe.push([`Angolo (${a.vista.replace('vista:', '')})`, n => { n.angoli.splice(i, 1); }]));
    (R_.saldature || []).forEach((a, i) => righe.push([`Saldatura ${a.tipo === 'angolo' ? 'd’angolo' : a.tipo}${a.a ? ' ' + a.a : ''}`, n => { n.saldature.splice(i, 1); }]));
    (R_.dettagli || []).forEach((a, i) => righe.push([`Dettaglio ${a.lettera} (× ${String(a.k).replace('.', ',')})`, n => { n.dettagli.splice(i, 1); if (n.viste) delete n.viste['dettaglio:' + a.lettera]; }]));
    (R_.tolte || []).forEach((v, i) => righe.push([`${ETICHETTE_TAV[v] || v} tolta`, n => { n.tolte.splice(i, 1); }]));
    (R_.libere || []).forEach((v, i) => righe.push([`${ETICHETTE_TAV[v] || v} non allineata`, n => { n.libere.splice(i, 1); }]));
    if (R_.cartiglio) righe.push([`Cartiglio al ${Math.round(R_.cartiglio * 100)}%`, n => { delete n.cartiglio; }]);
    if (R_.scala) righe.push([`Viste in scala ${R_.scala}`, n => { delete n.scala; }]);
    if (R_.iso) righe.push([`Isometrica al ${Math.round(R_.iso * 100)}%`, n => { delete n.iso; }]);
    if (R_.distinta) righe.push(['Distinta ritoccata', n => { delete n.distinta; }]);
    for (const [id, t] of Object.entries(R_.tabelle || {})) {
      const cosa = [t.k && t.k !== 1 ? `al ${Math.round(t.k * 100)}%` : '', t.d ? 'spostata' : ''].filter(Boolean).join(', ');
      righe.push([`${nomi[id] || 'Tabella'} ${cosa}`, n => { delete n.tabelle[id]; if (!Object.keys(n.tabelle).length) delete n.tabelle; }]);
    }
    const NOMI_T = { quote: 'Testi delle quote', frecce: 'Frecce delle quote', note: 'Testi delle note', titoli: 'Titoli delle viste' };
    for (const [k, v] of Object.entries(R_.testi || {})) righe.push([`${NOMI_T[k] || k}: ${mm(v)} mm`, n => { delete n.testi[k]; }]);
    const el = box.querySelector('#te-rit');
    el.innerHTML = righe.length ? righe.map(([t], i) => `<div class="te-r"><span>${esc(t)}</span><button class="btn" data-ri="${i}" aria-label="Togli questo ritocco">×</button></div>`).join('')
      : '<p class="hint">Nessun ritocco: la tavola è come la fa il programma.</p>';
    const nr = box.querySelector('#te-rit-n'); nr.hidden = !righe.length; nr.textContent = righe.length;
    box.querySelector('#te-auto').hidden = !righe.length;
    el.querySelectorAll('[data-ri]').forEach(b => { b.onclick = () => { const n = rit(); righe[+b.dataset.ri][1](n); salva(n); }; });
    avvisoPersi();
  }
  // 28/10: i ritocchi che il pezzo cambiato ha lasciato senza oggetto (una quota di un foro tolto…): si dicono, non spariscono zitti
  function avvisoPersi() {
    const el = box.querySelector('#te-persi'), persi = foglio()?.persi || [];
    el.hidden = !persi.length;
    if (!persi.length) { el.innerHTML = ''; return; }
    el.innerHTML = `<h4>${persi.length === 1 ? 'Un ritocco non trova più' : persi.length + ' ritocchi non trovano più'} il suo posto</h4>
      <p class="hint">Il pezzo è cambiato. Toglili, o rifalli dove servono.</p>
      ${persi.map((x, i) => `<div class="te-r"><span>${esc(x.testo)}</span><button class="btn" data-pi="${i}" aria-label="Togli questo ritocco">×</button></div>`).join('')}
      ${persi.length > 1 ? '<div class="te-bott"><button class="btn" id="te-persi-tutti">Togli tutti</button></div>' : ''}`;
    const togli = (n, lista) => {
      // gli indici delle liste dal più alto: togliendo, quelli prima non cambiano
      [...lista].sort((a, b) => (typeof b.chiave === 'number' ? b.chiave : 0) - (typeof a.chiave === 'number' ? a.chiave : 0)).forEach(x => {
        if (typeof x.chiave === 'number') { if (n[x.tipo]) n[x.tipo].splice(x.chiave, 1); }
        else if (n[x.tipo]) delete n[x.tipo][x.chiave];
      });
    };
    el.querySelectorAll('[data-pi]').forEach(b => { b.onclick = () => { const n = rit(); togli(n, [persi[+b.dataset.pi]]); salva(n); }; });
    if ($('#te-persi-tutti')) $('#te-persi-tutti').onclick = () => { const n = rit();
      togli(n, persi.filter((x, i, a) => a.findIndex(y => y.tipo === x.tipo && y.chiave === x.chiave) === i)); salva(n); };
  }

  // ---- mouse: seleziona e trascina, quota nuova (due punti), nota
  let tiro = null;
  const foglioEl = box.querySelector('#te-foglio');
  const aggancia = (p, vista = null) => {          // il punto di una vista più vicino al mouse (entro 4 mm)
    let best = null;
    for (const o of foglio().oggetti) {
      if (o.kind !== 'vista' || o.id === 'vista:iso' || (vista && o.id !== vista)) continue;
      for (const q of o.punti) { const d = Math.hypot(q[0] - p[0], q[1] - p[1]); if (d < 4 && (!best || d < best.d)) best = { d, p: q, vista: o }; }
    }
    return best;
  };
  const segno = (p, cls = 'te-aggancio') => {
    const svg = svgDi(); svg.querySelectorAll('.' + cls).forEach(e => e.remove());
    if (!p) return;
    const c_ = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c_.setAttribute('class', cls); c_.setAttribute('cx', p[0]); c_.setAttribute('cy', H() - p[1]); c_.setAttribute('r', 1.4);
    svg.appendChild(c_);
  };
  // zoom e spostamento (24/10): la rotella ingrandisce dove sta il mouse, il tasto centrale sposta il foglio
  const vbAttuale = () => { const v = svgDi().viewBox.baseVal; return [v.x, v.y, v.width, v.height]; };
  const vbMetti = vb => { ED.vb = vb; ED.vbFoglio = ED.k; svgDi().setAttribute('viewBox', vb.join(' ')); };
  let pan = null;
  foglioEl.addEventListener('wheel', ev => {
    if (!svgDi()) return;
    ev.preventDefault();
    const svg = svgDi(), pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse()), [x, y, w, h] = vbAttuale(), W = foglio().size[0];
    const k = ev.deltaY > 0 ? 1.18 : 1 / 1.18, nw = Math.min(W * 1.6, Math.max(W / 25, w * k)), kk = nw / w;
    vbMetti([q.x - (q.x - x) * kk, q.y - (q.y - y) * kk, w * kk, h * kk]);
  }, { passive: false });
  foglioEl.addEventListener('auxclick', ev => { if (ev.button === 1) ev.preventDefault(); });
  foglioEl.addEventListener('mousedown', ev => {
    if (!svgDi()) return;
    if (ev.button === 1) { ev.preventDefault(); pan = { x: ev.clientX, y: ev.clientY, vb: vbAttuale(), s: svgDi().getScreenCTM().a }; return; }
    if (ev.button !== 0) return;
    const p = aFoglio(ev);
    const kf = foglio().fattore || 1;
    const inVista = (v, q) => { const [s_, tx, ty] = v.T; return [(q[0] - tx) / s_, (q[1] - ty) / s_]; };
    if (ED.strumento === 'diametro') {
      let best = null;
      for (const v of foglio().oggetti) {
        if (v.kind !== 'vista' || v.id === 'vista:iso') continue;
        for (const c of v.cerchi || []) {
          const d = Math.abs(Math.hypot(p[0] - c.c[0], p[1] - c.c[1]) - c.r);
          if (d < 3 && (!best || d < best.d)) best = { d, c, v };
        }
      }
      if (!best) { toast('Clicca sul bordo di un cerchio o di un arco di una vista.'); return; }
      const s_ = best.v.T[0], ang = Math.atan2(p[1] - best.c.c[1], p[0] - best.c.c[0]) * 180 / Math.PI;
      const n = rit(); n.diametri = n.diametri || [];
      n.diametri.push({ vista: best.v.id, c: inVista(best.v, best.c.c), r: best.c.r / s_, tipo: best.c.chiuso ? 'Ø' : 'R', ang, d: 10 * kf });
      salva(n); return;
    }
    if (ED.strumento === 'dettaglio') {                // 28/10: centro, poi raggio; il dettaglio va a destra, lo sposti
      if (!ED.det) {
        const v = foglio().oggetti.find(o => o.kind === 'vista' && o.id.startsWith('vista:') && o.id !== 'vista:iso'
          && p[0] >= o.bbox[0] && p[0] <= o.bbox[2] && p[1] >= o.bbox[1] && p[1] <= o.bbox[3]);
        if (!v) { toast('Clicca il centro della zona da ingrandire, dentro una vista.'); return; }
        ED.det = { v, c: p }; segno(p, 'te-p1'); return;
      }
      const { v, c } = ED.det; ED.det = null; segno(null, 'te-p1');
      const R = Math.hypot(p[0] - c[0], p[1] - c[1]);
      if (R < 1) { toast('Il cerchio del dettaglio è troppo piccolo: clicca più lontano dal centro.'); return; }
      const n = rit(); n.dettagli = n.dettagli || [];
      const usate = new Set(n.dettagli.map(d => d.lettera)); let lettera = 'A';
      while (usate.has(lettera)) lettera = String.fromCharCode(lettera.charCodeAt(0) + 1);
      const W = foglio().size[0], k = 2, px = Math.min(W - R * k - 15 * kf, c[0] + R + R * k + 20 * kf);
      n.dettagli.push({ vista: v.id, c: inVista(v, c), r: R / v.T[0], k, p: [px, c[1]], lettera });
      ED.sel = 'dettaglio:' + lettera; salva(n); return;
    }
    if (ED.strumento === 'angolo') {
      const a = aggancia(p, ED.ang[0]?.vista.id);
      if (!a) { toast('Clicca vicino a uno spigolo della vista: il punto si accende in blu.'); return; }
      ED.ang.push(a); segno(a.p, 'te-p1');
      if (ED.ang.length < 3) return;
      const [A, V, B] = ED.ang, v = V.vista;
      ED.ang = []; segno(null, 'te-p1');
      const n = rit(); n.angoli = n.angoli || [];
      n.angoli.push({ vista: v.id, a: inVista(v, A.p), v: inVista(v, V.p), b: inVista(v, B.p), r: 15 * kf });
      salva(n); return;
    }
    if (ED.strumento === 'saldatura') {
      if (!ED.sald) {
        const a = aggancia(p) || (() => {                 // anche un punto qualsiasi dentro una vista
          const v = foglio().oggetti.find(o => o.kind === 'vista' && p[0] >= o.bbox[0] && p[0] <= o.bbox[2] && p[1] >= o.bbox[1] && p[1] <= o.bbox[3]);
          return v ? { p, vista: v } : null; })();
        if (!a) { toast('Clicca il giunto dentro una vista: lì va la punta della freccia.'); return; }
        ED.sald = a; segno(a.p, 'te-p1'); return;
      }
      const a = ED.sald; ED.sald = null; segno(null, 'te-p1');
      saldaturaDialog({ tipo: 'angolo', a: '', l: '', lato: 'freccia', giro: false, opera: false }, q => {
        const n = rit(); n.saldature = n.saldature || [];
        n.saldature.push({ vista: a.vista.id, p: inVista(a.vista, a.p), dx: p[0] - a.p[0], dy: p[1] - a.p[1], ...q });
        salva(n);
      });
      return;
    }
    if (ED.strumento === 'quota') {
      const a = aggancia(p, ED.punto1?.vista.id);
      if (!a) { toast('Clicca vicino a uno spigolo della vista: il punto si accende in blu.'); return; }
      if (!ED.punto1) { ED.punto1 = a; segno(a.p, 'te-p1'); return; }
      const v = a.vista, [s, tx, ty] = v.T, inV = q => [(q[0] - tx) / s, (q[1] - ty) / s];
      const A = ED.punto1.p, B = a.p, dx = Math.abs(B[0] - A[0]), dy = Math.abs(B[1] - A[1]);
      ED.punto1 = null; segno(null, 'te-p1');
      if (Math.hypot(dx, dy) < 0.5) return;
      const dir = ev.shiftKey ? 'a' : dx >= dy ? 'h' : 'v';
      // la quota va dalla parte di fuori della vista, non dentro il disegno
      const B2 = dir === 'h' ? [B[0], A[1]] : dir === 'v' ? [A[0], B[1]] : B, L = Math.hypot(B2[0] - A[0], B2[1] - A[1]) || 1;
      const nx = -(B2[1] - A[1]) / L, ny = (B2[0] - A[0]) / L, [x0, y0, x1, y1] = v.bbox;
      const fuori = ((A[0] + B2[0]) / 2 - (x0 + x1) / 2) * nx + ((A[1] + B2[1]) / 2 - (y0 + y1) / 2) * ny >= 0 ? 1 : -1;
      // e non sopra un'altra quota: si allontana finché trova posto libero
      const mx = (A[0] + B2[0]) / 2, my = (A[1] + B2[1]) / 2, quote = foglio().oggetti.filter(o => o.kind === 'quota');
      const kf = foglio().fattore || 1;
      let d = 8 * kf;
      while (d < 60 * kf && quote.some(o => { const [a0, b0, a1, b1] = o.bbox, x = mx + nx * d * fuori, y = my + ny * d * fuori;
        return x > a0 - 2 * kf && x < a1 + 2 * kf && y > b0 - 2 * kf && y < b1 + 2 * kf; })) d += 6 * kf;
      const n = rit(); n.aggiunte = n.aggiunte || [];
      n.aggiunte.push({ vista: v.id, a: inV(A), b: inV(B), dir, d: d * fuori });
      salva(n); return;
    }
    if (ED.strumento === 'nota') {
      modal(`<h3>Nota sulla tavola</h3><label class="te-nota">Testo<textarea class="field" id="nt-t" rows="3" placeholder="Es.: sbavare tutti gli spigoli"></textarea></label>
        <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Metti la nota</button></div>`, close => {
        $('#m-no').onclick = close;
        $('#m-ok').onclick = () => { const t = $('#nt-t').value.trim(); close(); if (!t) return;
          const n = rit(); n.note = n.note || []; n.note.push({ x: p[0], y: p[1], testo: t }); salva(n); };
        setTimeout(() => $('#nt-t').focus(), 30);
      });
      return;
    }
    let o = oggettoDi(ev.target.closest('[data-el]')?.getAttribute('data-el'));
    if (!o) {                                       // 29/10: nel vuoto dentro una vista si prende la vista (non serve centrare una linea)
      const area = x => (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]);
      const dentro = x => p[0] >= x.bbox[0] - 0.5 && p[0] <= x.bbox[2] + 0.5 && p[1] >= x.bbox[1] - 0.5 && p[1] <= x.bbox[3] + 0.5;
      // prima le cose piccole (una quota, una nota, un simbolo), poi la vista che contiene il clic
      o = foglio().oggetti.filter(x => !['vista', 'cartiglio'].includes(x.kind) && dentro(x)).sort((a, b) => area(a) - area(b))[0]
        || foglio().oggetti.filter(x => x.kind === 'vista' && dentro(x)).sort((a, b) => area(a) - area(b))[0]
        || foglio().oggetti.find(x => x.kind === 'cartiglio' && dentro(x)) || null;
    }
    ED.sel = o?.id || null;
    evidenzia(); pannelloSel();
    if (o && ['vista', 'quota', 'nota', 'diametro', 'angolo', 'saldatura', 'tabella', 'distinta'].includes(o.kind)) {
      // 29/10: gli elementi da muovere si trovano adesso, non a ogni movimento del mouse
      const ids = o.kind === 'vista' ? Object.keys(mosseViste(o.id, 0, 0)) : [o.id];
      const els = [];
      svgDi().querySelectorAll('[data-el]').forEach(e => {
        const t = e.getAttribute('data-el');
        const v = o.kind === 'vista' ? ids.find(id => t === id || t.startsWith(id + '/')) : (t === o.id ? o.id : null);
        if (!v) return;
        if (e.dataset.t0 === undefined) e.dataset.t0 = e.getAttribute('transform') || '';
        els.push([e, v]);
      });
      tiro = { o, da: p, ora: p, els, raf: 0 };
    }
  });
  foglioEl.addEventListener('mousemove', ev => {
    if (!svgDi()) return;
    if (pan) {
      const [x, y, w, h] = pan.vb;
      vbMetti([x - (ev.clientX - pan.x) / pan.s, y - (ev.clientY - pan.y) / pan.s, w, h]);
      return;
    }
    const p = aFoglio(ev);
    if (ED.strumento === 'quota') { const a = aggancia(p, ED.punto1?.vista.id); segno(a?.p || null); return; }
    if (ED.strumento === 'angolo') { const a = aggancia(p, ED.ang[0]?.vista.id); segno(a?.p || null); return; }
    if (ED.strumento === 'saldatura' && !ED.sald) { const a = aggancia(p); segno(a?.p || null); return; }
    if (!tiro) return;
    tiro.ora = p;
    if (tiro.raf) return;                           // al massimo una volta per fotogramma
    tiro.raf = requestAnimationFrame(() => {
      if (!tiro) return;
      tiro.raf = 0;
      const dx = tiro.ora[0] - tiro.da[0], dy = tiro.ora[1] - tiro.da[1];
      // durante il trascinamento si sposta solo il disegno a video; il ritocco si salva quando lasci
      let mosse;
      if (tiro.o.kind === 'vista') mosse = mosseViste(tiro.o.id, dx, dy);
      else if (tiro.o.kind === 'quota') {           // la quota si muove solo di traverso
        const [ax, ay] = tiro.o.a, [bx, by] = tiro.o.b, L = Math.hypot(bx - ax, by - ay) || 1, nx = -(by - ay) / L, ny = (bx - ax) / L;
        const k = dx * nx + dy * ny;
        mosse = { [tiro.o.id]: [k * nx, k * ny] };
      } else mosse = { [tiro.o.id]: [dx, dy] };
      for (const [e, v] of tiro.els) {
        const m = mosse[v];
        e.setAttribute('transform', m ? `translate(${m[0]} ${-m[1]}) ` + e.dataset.t0 : e.dataset.t0);
      }
    });
  });
  // 28/10: viste allineate come in ogni CAD: l'alto si sposta solo in su e in giù sotto la fronte, il fianco solo di
  // lato, e seguono la fronte. Le «libere» (scelta nel pannello della vista) si spostano dove vuoi
  function mosseViste(id, dx, dy) {
    const R_ = foglio().ritocchi || {}, libere = new Set(R_.libere || []);
    const c = id => !libere.has(id) && foglio().oggetti.some(o => o.id === id);
    if (id === 'vista:fronte') {
      const m = { [id]: [dx, dy] };
      if (c('vista:alto')) m['vista:alto'] = [dx, dy];
      if (c('vista:sinistra')) m['vista:sinistra'] = [dx, dy];
      if (c('vista:destra')) m['vista:destra'] = [dx, dy];
      return m;
    }
    if (id === 'vista:alto' && c('vista:alto') && c('vista:fronte')) return { [id]: [0, dy] };
    if (['vista:sinistra', 'vista:destra'].includes(id) && c(id) && c('vista:fronte')) return { [id]: [dx, 0] };
    return { [id]: [dx, dy] };
  }
  const lascia = () => {
    pan = null;
    if (!tiro) return;
    const { o, da, ora } = tiro; if (tiro.raf) cancelAnimationFrame(tiro.raf); tiro = null;
    const dx = ora[0] - da[0], dy = ora[1] - da[1];
    if (Math.hypot(dx, dy) < 0.4) return;            // era un clic, non un trascinamento
    const n = rit();
    if (o.kind === 'vista') { n.viste = n.viste || {}; const v = n.viste[o.id] || [0, 0], m = mosseViste(o.id, dx, dy)[o.id]; n.viste[o.id] = [v[0] + m[0], v[1] + m[1]]; }
    else if (o.kind === 'nota') { const m = n.note[o.indice]; m.x += dx; m.y += dy; }
    else if (o.kind === 'tabella' || o.kind === 'distinta') {
      n.tabelle = n.tabelle || {}; const t = n.tabelle[o.id] || {}, d = t.d || [0, 0];
      t.d = [d[0] + dx, d[1] + dy]; n.tabelle[o.id] = t;
    }
    else if (o.kind === 'saldatura') { const m = n.saldature[o.indice]; m.dx += dx; m.dy += dy; }   // si sposta il simbolo, la punta resta
    else if (o.kind === 'diametro') {                // la scritta va dove lasci il mouse
      const m = n.diametri[o.indice], [cx, cy] = o.C;
      m.ang = Math.atan2(ora[1] - cy, ora[0] - cx) * 180 / Math.PI;
      m.d = Math.max(2, Math.hypot(ora[0] - cx, ora[1] - cy) - o.R);
    }
    else if (o.kind === 'angolo') { const m = n.angoli[o.indice], vv = foglio().oggetti.find(x => x.id === m.vista);
      const [s_, tx, ty] = vv.T, V = [m.v[0] * s_ + tx, m.v[1] * s_ + ty];
      m.r = Math.max(3, Math.hypot(ora[0] - V[0], ora[1] - V[1])); }
    else if (o.kind === 'quota') {
      const [ax, ay] = o.a, [bx, by] = o.b, L = Math.hypot(bx - ax, by - ay) || 1;
      const k = dx * (-(by - ay) / L) + dy * ((bx - ax) / L);
      if (o.aggiunta != null) n.aggiunte[o.aggiunta].d = (n.aggiunte[o.aggiunta].d || 8) + k;
      else { n.quote = n.quote || {}; const m = n.quote[o.id] || {}; m.d = (m.d || 0) + k; n.quote[o.id] = m; }
    }
    salva(n);
  };
  foglioEl.addEventListener('mouseup', lascia);
  foglioEl.addEventListener('mouseleave', lascia);

  // ---- strumenti, testi, campi, esporta
  // notte 03/11: con uno strumento acceso, una riga in basso sul foglio dice cosa cliccare adesso (prima solo nel title)
  const PASSI = {
    quota: ['Quota', 'dimension', [['Clicca il primo punto', 'vicino a uno spigolo di una vista: il punto si accende'], ['Clicca il secondo punto', 'sulla stessa vista; con Maiusc la quota viene inclinata']]],
    nota: ['Nota', 'text', [['Clicca dove va la nota', 'poi scrivi il testo']]],
    diametro: ['Ø / R', 'hole', [['Clicca il bordo di un cerchio o di un arco', 'la scritta va dove clicchi']]],
    angolo: ['Angolo', 'plane_angle', [['Clicca un punto sul primo lato', 'vicino a uno spigolo'], ['Clicca il vertice', 'dove si incontrano i due lati'], ['Clicca un punto sull’altro lato', 'e l’angolo è fatto']]],
    saldatura: ['Saldatura', 'saldatura', [['Clicca il giunto', 'lì va la punta della freccia'], ['Clicca dove va il simbolo', 'poi scegli che saldatura è']]],
    dettaglio: ['Dettaglio', 'zoom', [['Clicca il centro della zona da ingrandire', 'dentro una vista'], ['Clicca quanto è grande il cerchio', 'il dettaglio va a destra, poi lo sposti']]],
  };
  const passo = () => {
    const el = box.querySelector('#te-passo'), d = PASSI[ED.strumento];
    el.hidden = !d;
    if (!d) { el.innerHTML = ''; return; }
    const [nome, icona, passi] = d;
    const k = Math.min(passi.length - 1, ED.strumento === 'quota' ? (ED.punto1 ? 1 : 0) : ED.strumento === 'angolo' ? ED.ang.length
      : ED.strumento === 'saldatura' ? (ED.sald ? 1 : 0) : ED.strumento === 'dettaglio' ? (ED.det ? 1 : 0) : 0);
    const [t, sm] = passi[k];
    el.innerHTML = `<div class="sk-help"><span class="g-cmd"><img src="icons/${icona}.svg" alt="">${esc(nome)}</span>
      ${passi.length > 1 ? `<span class="g-passi">${passi.map((_, i) => `<i class="${i <= k ? 'on' : ''}"></i>`).join('')}</span>` : ''}
      <span class="g-testo">${esc(t)}<small>${esc(sm)}</small></span><span class="g-sep"></span>
      <span class="g-tasto"><kbd>Esc</kbd>${k > 0 ? 'ricomincia' : 'fine'}</span></div>`;
  };
  const strumento = nome => {
    ED.strumento = nome; ED.punto1 = null; ED.ang = []; ED.sald = null; ED.det = null; if (svgDi()) { segno(null); segno(null, 'te-p1'); }
    box.querySelectorAll('[data-str]').forEach(x => x.classList.toggle('on', x.dataset.str === nome));
    foglioEl.dataset.strumento = ED.strumento;
    passo();
  };
  box.querySelectorAll('[data-str]').forEach(b => { b.onclick = () => strumento(b.dataset.str); });
  foglioEl.addEventListener('mousedown', () => passo());          // dopo il clic dello strumento: il passo dopo
  box.querySelectorAll('[data-t]').forEach(i => { i.onchange = () => {
    const n = rit(); n.testi = n.testi || {}; const v = num(i.value);
    if (v) n.testi[i.dataset.t] = v; else delete n.testi[i.dataset.t];
    salva(n);
  }; });
  let attesa = null;
  box.querySelectorAll('[data-c], [data-rev]').forEach(i => i.addEventListener('change', () => { clearTimeout(attesa); attesa = setTimeout(aggiorna, 250); }));
  if (box.querySelector('#tav-tutte')) box.querySelector('#tav-tutte').onchange = aggiorna;
  box.querySelector('#te-auto').onclick = () => { ED.sel = null; salva({}); };
  box.querySelector('#te-undo').onclick = () => inCoda(async () => { await call('undo'); ED.toccato = true; carica(await call('drawing_preview', leggi(), tutte())); });
  const esporta = fmt => inCoda(async () => { const x = await call('export_drawings_dialog', fmt, leggi(), tutte()); if (x.cancelled) return;
    if (x.ok && x.path) fileFatto(x, fmt === 'pdf' ? 'Tavole in PDF salvate' : 'Tavole in DXF salvate'); else toast(x.message, x.ok ? '' : 'err'); });
  box.querySelector('#te-pdf').onclick = () => esporta('pdf');
  box.querySelector('#te-dxf').onclick = () => esporta('dxf');
  box.querySelector('#te-chiudi').onclick = chiudi;
  box.querySelector('#te-adatta').onclick = () => { ED.vb = null; if (svgDi()) svgDi().setAttribute('viewBox', `0 0 ${foglio().size[0]} ${foglio().size[1]}`); };
  function tasti(ev) {
    if (!document.body.contains(box) || !$('#modal').hidden) return;
    if (ev.key === 'Escape') {
      if (ED.punto1 || ED.ang.length || ED.sald || ED.det) { ED.punto1 = null; ED.ang = []; ED.sald = null; ED.det = null; segno(null, 'te-p1'); passo(); }
      else if (ED.strumento !== 'sel') strumento('sel');          // notte 03/11: Esc spegne lo strumento, non chiude le tavole
      else if (ED.sel) { ED.sel = null; evidenzia(); pannelloSel(); } else chiudi();
      ev.stopPropagation(); ev.preventDefault(); }
    if ((ev.key === 'Delete' || ev.key === 'Backspace') && ED.sel && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      $('#ts-via')?.click(); ev.preventDefault(); ev.stopPropagation();
    }
    if (ev.ctrlKey && ev.key.toLowerCase() === 'z' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) { box.querySelector('#te-undo').click(); ev.preventDefault(); ev.stopPropagation(); }
  }
  document.addEventListener('keydown', tasti, true);
  aggiorna();
}

// 03/11: il percorso intero occupava tre righe per pezzo: basta la cartella (e quella sopra); intero passandoci sopra
function cartellaCorta(f) {
  const p = String(f || '').split(/[\\/]/).filter(Boolean);
  return p.length > 2 ? '…\\' + p.slice(-2).join('\\') : String(f || '');
}
async function newAssemblyDialog() {
  const info = await call('home_info');
  let pezzi = (info.ok ? info.recent : []).filter(x => !x.assembly).map(x => ({ ...x, scelto: 0, n: 1 }));
  let ordine = 0;                                  // la base è il primo pezzo scelto: l'ordine dei clic
  const scegliPezzo = (x, si) => { x.scelto = si ? (x.scelto || ++ordine) : 0; };
  const scelti = () => pezzi.filter(x => x.scelto).sort((a, b) => a.scelto - b.scelto);
  const righe = () => pezzi.map((x, i) => `<tr class="${x.scelto ? 'scelto' : ''}">
      <td class="na-c"><input type="checkbox" data-i="${i}" ${x.scelto ? 'checked' : ''} aria-label="Metti nell’assieme"></td>
      <td class="na-p"><span class="na-pic">${x.thumb ? `<img src="${x.thumb}" alt="">` : '<img class="icona" src="icons/box.svg" alt="">'}</span></td>
      <td><b>${esc(x.name)}</b> <span class="na-base" data-base="${i}"></span><br><span class="hint" title="${esc(x.folder || '')}">${esc(cartellaCorta(x.folder))}</span></td>
      <td class="na-q"><label class="na-n">nr <input class="field" data-n="${i}" value="${x.n}" inputmode="numeric"></label></td>
      <td class="hint na-w">${esc(x.when || '')}</td></tr>`).join('')
    || '<tr><td colspan="5" class="hint">Nessun pezzo recente: usa «Sfoglia…» oppure crea l’assieme vuoto.</td></tr>';
  modal(`<h3>Nuovo assieme</h3>
    <div class="form"><label class="tutta-riga">Nome<input class="field" id="n-name" value="Assieme"></label></div>
    <div class="na-testa"><div class="sub">Pezzi da mettere dentro</div><button class="btn" id="na-sfoglia">Sfoglia…</button></div>
    <div class="na-lista"><table class="grid" id="na-tab">${righe()}</table></div>
    <p class="hint">Il primo pezzo che scegli è la base e resta fermo; le copie si mettono a fianco e poi le accoppi. Nella distinta compaiono con la quantità.</p>
    <div class="acts"><span class="hint na-tot spingi" id="na-tot"></span><button class="btn" id="n-no">Annulla</button><button class="btn primary" id="n-ok">Crea l’assieme</button></div>`, close => {
    const tot = () => {
      const sc = scelti();
      $('#na-tab').querySelectorAll('[data-base]').forEach(s => { s.textContent = pezzi[+s.dataset.base] === sc[0] ? 'base, resta fermo' : ''; });
      const n = sc.reduce((a, x) => a + (parseInt(x.n, 10) || 0), 0);
      $('#na-tot').textContent = sc.length ? `${sc.length} ${sc.length === 1 ? 'pezzo' : 'pezzi diversi'}, ${n} in tutto` : 'Assieme vuoto: i pezzi li metti dopo';
    };
    const wire = () => {
      $('#na-tab').querySelectorAll('[data-i]').forEach(c => { c.onchange = () => { scegliPezzo(pezzi[+c.dataset.i], c.checked); c.closest('tr').classList.toggle('scelto', c.checked); tot(); }; });
      // 04/11 (percorso D): un clic sul nome o sulla foto del pezzo lo spunta, non solo sulla casella da 13 px
      $('#na-tab').querySelectorAll('tr').forEach(tr => { tr.onclick = ev => {
        const c = tr.querySelector('[data-i]');
        if (!c || ev.target.closest('input, label, button')) return;
        c.checked = !c.checked; c.dispatchEvent(new Event('change'));
      }; });
      $('#na-tab').querySelectorAll('[data-n]').forEach(c => { c.oninput = () => {
        const x = pezzi[+c.dataset.n]; x.n = c.value.trim(); if (!x.scelto && x.n) { scegliPezzo(x, true); c.closest('tr').classList.add('scelto'); c.closest('tr').querySelector('[data-i]').checked = true; } tot(); }; });
      tot();
    };
    wire();
    $('#na-sfoglia').onclick = () => inCoda(async () => {
      const r = await call('scegli_pezzo');
      if (!r.ok) { if (!r.cancelled) toast(r.message, 'err'); return; }
      const g = pezzi.find(x => x.path === r.path);
      if (g) scegliPezzo(g, true); else pezzi.unshift({ path: r.path, name: r.name, folder: r.folder, when: '', thumb: r.thumb, scelto: ++ordine, n: 1 });
      $('#na-tab').innerHTML = righe(); wire();
    });
    $('#n-no').onclick = close;
    $('#n-ok').onclick = () => {
      const sc = scelti();
      const male = sc.find(x => !/^\d+$/.test(String(x.n)) || +x.n < 1 || +x.n > 100);
      if (male) { toast(`Quantità di «${male.name}»: scrivi un numero da 1 a 100.`, 'err'); return; }
      const n = $('#n-name').value.trim() || 'Assieme';
      close(); primaVolta = true; clearSelection();
      inCoda(async () => { if (await apply(await call('new_assembly_con_pezzi', n, sc.map(x => ({ path: x.path, n: +x.n }))))) hideHome(); });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter' && ev.target.id === 'n-name') $('#n-ok').click(); if (ev.key === 'Escape') close(); };
    setTimeout(() => { $('#n-name').focus(); $('#n-name').select(); }, 30);
  });
  $('#modal-box').classList.add('na-box');
}

// ------------------------------------------------------------- impostazioni: quelle che c'erano già, in un posto solo
async function impostazioniDialog(sezione = 'piegatrice') {
  const r = await call('impostazioni');
  if (!r.ok) { toast(r.message, 'err'); return; }
  const n = v => (v == null || v === '' ? '' : String(v).replace('.', ','));
  const metodo = x => (x.method === 'bd90' ? 'BD90 ' + n(x.bd90) : x.method === 'din6935' ? 'DIN 6935' : n(x.k));
  const regole = r.rules.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.material || '')}</td><td class="destra">${n(x.thickness)}</td>
      <td class="destra">${n(x.radius)}</td><td class="destra">${metodo(x)}</td>
      <td class="destra"><button class="btn piccolo danger" data-rule-del="${esc(x.name)}" title="Elimina la regola">Elimina</button></td></tr>`).join('')
    || '<tr><td colspan="6" class="hint">Ancora nessuna regola. Con una lamiera aperta: «Regole piega», poi «Salva regola».</td></tr>';
  const scuro = r.tema === 'scuro';
  const corpi = {
    piegatrice: `<h4>Piegatrice</h4>
      <p class="hint">Raggio e K per ogni lamiera nuova, quando non scrivi niente.</p>
      <div class="imp-riga"><span>Raggio interno</span><span class="campo-unita imp-corto"><input class="field" id="i-r" value="${n(r.bend_default?.radius)}" placeholder="es. 2"><i>mm</i></span><span></span></div>
      <div class="imp-riga"><span>Fattore K</span><span class="campo-unita imp-corto"><input class="field" id="i-k" value="${n(r.bend_default?.k)}" placeholder="es. 0,33"></span><span></span></div>
      <h4 class="imp-sotto">Regole salvate</h4>
      <table class="grid imp-regole"><tr><th>Nome</th><th>Materiale</th><th class="destra">Spessore</th><th class="destra">Raggio</th><th class="destra">K</th><th></th></tr>${regole}</table>`,
    materiali: `<h4>Materiali</h4>
      <p class="hint">Il materiale dei pezzi nuovi. Ogni pezzo lo cambi poi a sinistra, sotto «Misure».</p>
      <div class="imp-riga"><span>Materiale predefinito</span><select class="field medio" id="i-mat">${r.materiali.map(m =>
        `<option value="${esc(m.code)}"${m.code === r.materiale ? ' selected' : ''}>${esc(m.nome)}</option>`).join('')}</select><span></span></div>`,
    tavole: `<h4>Tavole e cartiglio</h4>
      <p class="hint">Vanno nel cartiglio di ogni tavola.</p>
      <div class="imp-riga"><span>Azienda</span><input class="field medio" id="i-az" value="${esc(r.cartiglio.azienda || '')}"><span></span></div>
      <div class="imp-riga"><span>Disegnatore</span><input class="field medio" id="i-dis" value="${esc(r.cartiglio.disegnatore || '')}"><span></span></div>
      <div class="imp-riga"><span>Logo</span><span class="imp-percorso" id="i-logo">${r.logo ? esc(r.logo.split(/[\\/]/).pop()) : 'nessuno'}</span>
        <span class="imp-bott"><button class="btn" id="i-logo-sc" title="Un’immagine PNG o JPG: va nel cartiglio, accanto al nome dell’azienda">Scegli immagine…</button>
        <button class="btn" id="i-logo-via"${r.logo ? '' : ' hidden'}>Togli</button></span></div>`,
    cartelle: `<h4>Cartelle</h4>
      <div class="imp-riga"><span>Lavori</span><span class="imp-percorso" title="${esc(r.cartelle.lavori)}">${esc(r.cartelle.lavori)}</span><button class="btn" data-apri="${esc(r.cartelle.lavori)}">Apri cartella</button></div>
      <div class="imp-riga"><span>Viti e bulloni</span><span class="imp-percorso" title="${esc(r.cartelle.libreria)}">${esc(r.cartelle.libreria)}</span><button class="btn" data-apri="${esc(r.cartelle.libreria)}">Apri cartella</button></div>`,
    aspetto: `<h4>Aspetto</h4>
      <div class="imp-riga"><span>Tema</span><div class="seg imp-tema" id="i-tema">${[['chiaro', 'Chiaro'], ['scuro', 'Scuro']].map(([k, t]) =>
        `<button type="button" data-v="${k}" class="${scuro === (k === 'scuro') ? 'on' : ''}">${t}</button>`).join('')}</div><span></span></div>
      <p class="hint">Il chiaro è quello di partenza. Lo cambi anche col pulsante «Tema» in basso nella vista.</p>`,
  };
  const voci = [['piegatrice', 'Piegatrice'], ['materiali', 'Materiali'], ['tavole', 'Tavole e cartiglio'], ['cartelle', 'Cartelle'], ['aspetto', 'Aspetto']];
  modal(`<div class="imp-box"><nav class="imp-nav"><h3>Impostazioni</h3>${voci.map(([k, t]) => `<button data-sez="${k}" class="${k === sezione ? 'on' : ''}">${t}</button>`).join('')}</nav>
    <div class="imp-corpo">${voci.map(([k]) => `<section data-corpo="${k}"${k === sezione ? '' : ' hidden'}>${corpi[k]}</section>`).join('')}
      <div class="imp-spazio"></div>
      <div class="imp-acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="i-ok">Salva le impostazioni</button></div></div></div>`, close => {
    $('#m-no').onclick = close;
    // le sezioni sono tutte nella finestra: cambiando sezione quello che hai scritto resta, e Applica salva tutto
    $('#modal-box').querySelectorAll('[data-sez]').forEach(b => { b.onclick = () => {
      $('#modal-box').querySelectorAll('[data-sez]').forEach(x => x.classList.toggle('on', x === b));
      $('#modal-box').querySelectorAll('[data-corpo]').forEach(x => { x.hidden = x.dataset.corpo !== b.dataset.sez; });
    }; });
    $('#i-tema').querySelectorAll('button').forEach(b => { b.onclick = () => $('#i-tema').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); });
    $('#modal-box').querySelectorAll('[data-rule-del]').forEach(b => { b.onclick = () => inCoda(async () => { await call('delete_sheet_rule', b.dataset.ruleDel); close(); impostazioniDialog('piegatrice'); }); });
    $('#modal-box').querySelectorAll('[data-apri]').forEach(b => { b.onclick = () => call('apri_cartella', b.dataset.apri); });
    // il logo si mette subito (è un file): Annulla non lo toglie, lo toglie «Togli»
    const logo = x => { if (x.cancelled) return; toast(x.message, x.ok ? '' : 'err'); if (!x.ok) return;
      $('#i-logo').textContent = x.logo ? x.logo.split(/[\\/]/).pop() : 'nessuno'; $('#i-logo-via').hidden = !x.logo; };
    $('#i-logo-sc').onclick = () => inCoda(async () => logo(await call('scegli_logo')));
    $('#i-logo-via').onclick = () => inCoda(async () => logo(await call('set_logo', null)));
    $('#i-ok').onclick = () => inCoda(async () => {
      const tema = $('#i-tema .on')?.dataset.v || 'chiaro';
      const x = await call('set_impostazioni', { radius: $('#i-r').value.trim(), k: $('#i-k').value.trim(), materiale: $('#i-mat').value,
        azienda: $('#i-az').value, disegnatore: $('#i-dis').value, tema });
      if (!x.ok) { toast(x.message, 'err'); return; }
      applyTheme(tema === 'scuro');
      if (S && x.bend_default) S.bend_default = x.bend_default;
      close();
      toast(x.message);
    });
  });
  $('#modal-box').classList.add('imp-dlg');
}

function foldPanel(s) {
  const d = s.def;
  // 04/11 (regola 2): la piega su una linea (anche le pieghe di un profilo piegato)
  return pannelloLam({ titolo: `Piega ${esc(s.fold)}`, cose: 'piega su una linea dello sviluppo',
    azioni: [azioneLam('fold', 'Piega l’altra parte', 'id="f-flip"', '', 'La linea resta lì: si alza l’altra parte della lamiera'),
      ...azioniFaccia(s).slice(0, 3),
      azioneLam('delete', 'Togli la piega', 'id="f-del"', 'danger', 'Elimina la piega (la lamiera torna piana lì)')],
    corpo: `<div class="ff"><label>Angolo<span class="inp"><input class="field" id="f-ang" value="${esc(String(d.angle).replace('.', ','))}"><i>°</i></span></label><span></span></div>
    <div class="seg-row"><span>Verso</span><div class="seg" id="f-dir">${[['up', 'In su'], ['down', 'In giù']].map(([k, t]) => `<button type="button" data-v="${k}" class="${d.direction === k ? 'on' : ''}">${t}</button>`).join('')}</div></div>
    <p class="hint">La lunghezza la calcolo io: quella che serve perché lo sviluppo resti quello disegnato.</p>
    <details class="fsec"${d.bump?.colpi ? ' open' : ''}><summary>A colpi (raggio grande)</summary>
    <div class="ff"><label>Colpi<input class="field" id="f-colpi" value="${esc(String(d.bump?.colpi ?? ''))}" placeholder="vuoto = piega normale"></label>
      <label>Raggio grande<span class="inp"><input class="field" id="f-rg" value="${esc(String(d.bump?.raggio ?? '').replace('.', ','))}"><i>mm</i></span></label></div>
    ${s.colpi?.length ? `<p class="hint">Battuta dei colpi (dalla linea, nello sviluppo): ${s.colpi.map(c => num(c, 1)).join('; ')} mm</p>` : ''}</details>`,
    dettagliHtml: rigaPiega(righeIt(s.rows.filter(r => r[0] !== 'Piega su linea'))),
    fine: '<button class="btn primary big" id="f-fatto">Fatto</button>' });
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
  $('#f-fatto').onclick = () => clearSelection();
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
      modal(`<h3>Gradino sulla punta della ${esc(nomePiegaAlbero(s.feature, s.flange))}</h3>
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
        conAnteprima('gradino', () => [s.feature, s.flange, ...['#g-h', '#g-a', '#g-l'].map(q => $(q).value.trim()), $('#g-v').value]);
      });
    };
    ['#t-len', '#t-ang'].forEach(q => { $(q).onkeydown = ev => { if (ev.key === 'Enter') punta(); }; });
    if (s.tip_form) $('#t-len').focus();          // hai cliccato la punta: si parte da lì
    // la piega sulla punta: anteprima appena tocchi i suoi campi (il pannello della flangia serve anche per altro)
    const tAnt = () => anteprima('add_flange', () => [s.feature, null, readFlange('t'), s.flange], $('#t-ant'));
    if (!$('#t-ant')) $('#t-add').closest('.row-btns')?.insertAdjacentHTML('beforebegin', '<div class="ant-stato" id="t-ant"></div>');
    ['#t-len', '#t-ang'].forEach(q => { $(q).addEventListener('input', tAnt); });
    ['#t-dir', '#t-pos'].forEach(q => { if ($(q)) $(q).addEventListener('change', tAnt); });
    if (s.tip_form) tAnt();
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
  // 04/11 (percorsi C, D): il «!» solo se il pezzo ha pieghe; una piastra piana non ha bisogno di raggio e K
  $('#sheet-badge').textContent = manca.size && (sh.data?.bends?.length || sh.shape) ? '!' : '';
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

let ultimaAsta = { length: '500', profile: null, group: '', nome: '' };
function ricordaTubo() {
  if (!$('#n-len')) return;
  ultimaAsta = { ...ultimaAsta, length: $('#n-len').value.trim(), profile: $('#n-prof').value.trim(), nome: $('#n-nome')?.value.trim() || '' };
}
// ===================================================================== TUBI E STRUTTURE: i pannelli (notte 03→04/11)
// Sempre lo stesso ordine (regola 2): titolo e cos'è → «Cosa puoi fare adesso» → i campi → Dettagli (chiuso) → in
// fondo il pulsante. Il pulsante di un campo diventa blu solo quando hai cambiato qualcosa: il prossimo passo si vede
const tRighe = rows => rows.map(([k, v]) => `<div class="riga"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
const tAzione = (attr, icona, nome, spiega = '', cls = '') => `<button class="cosa-b t-az${cls ? ' ' + cls : ''}" ${attr}><img src="icons/${icona}.svg" alt=""><b>${esc(nome)}</b>${spiega ? `<span>${esc(spiega)}</span>` : ''}</button>`;
const tMinuscola = t => (t ? t.charAt(0).toLowerCase() + t.slice(1) : '');
function bluSeCambia(campi, btn) {
  campi = [...campi].filter(Boolean);
  if (!btn || !campi.length) return;
  const prima = campi.map(i => i.value);
  const guarda = () => btn.classList.toggle('primary', campi.some((i, k) => i.value !== prima[k]));
  campi.forEach(i => { i.addEventListener('input', guarda); i.addEventListener('change', guarda); });
}
// la struttura intera (clic nell'albero, o appena creata dal modello): cosa puoi fare e le misure del modello
function pannelloStruttura(s) {
  const c = s.cosa, t = s.template;
  const fuori = c?.fuori_tutto?.length ? `fuori tutto ${c.fuori_tutto.join(' × ')} mm` : '';
  const cose = [t ? `${t.title} da modello` : 'Struttura disegnata', fuori].filter(Boolean).join(', ');
  let h = `<div class="t-pan"><h3>${esc(s.title)}</h3><p class="t-cose">${esc(cose)}</p>`;
  if (c) h += `<section class="sezione"><h4>Cosa puoi fare</h4><div class="cosa t-azioni">
    ${tAzione('data-azione="dividi"', 'pattern_rect', 'Dividi un lato', 'Montanti e traversi in mezzo, quadri uguali')}
    ${tAzione('data-azione="traverso"', 'traverso', 'Aggiungi un traverso', 'Clicca due tubi, poi scrivi l’altezza')}
    ${tAzione('data-azione="giunti"', 'giunto', 'Come sono saldati gli angoli', 'Clicca un angolo, scegli col disegnino')}
    ${tAzione('data-azione="tubonuovo"', 'tubo', 'Tubo nuovo da un angolo', 'Le frecce Su, Giù, Avanti… (mensole)')}
    ${tAzione('data-azione="piedi"', 'piedi', 'Piedi sotto le gambe', 'Piastra coi fori o piedino regolabile')}
    ${tAzione('data-azione="tappi"', 'tappi', 'Tappi sulle teste dei tubi', 'In plastica o lamierino saldato')}
    ${tAzione('data-azione="fori"', 'hole', 'Fori sui tubi', 'Clicca la faccia del tubo e disegna')}
    ${tAzione('data-cmd="prepara"', 'export', 'Prepara per l’officina', 'Lista di taglio dei tubi, tavola quotata')}</div></section>`;
  if (t) {
    // le misure (in mm, o quanti ripiani) e i tubi in due sezioni: prima quanto è grande, poi con cosa è fatto
    const numero = v => /^-?\d+([.,]\d+)?$/.test(String(v ?? '').trim());
    const campo = ([k, l, v, scelte]) => scelte
      ? `<label class="lbl">${esc(l)}<select class="field" data-tf="${esc(k)}">${Object.entries(scelte).map(([a, b]) => `<option value="${a}"${a === v ? ' selected' : ''}>${esc(b)}</option>`).join('')}</select></label>`
      : numero(v) ? `<label class="lbl">${esc(l)}<span class="campo-unita"><input class="field" data-tf="${esc(k)}" value="${esc(String(v ?? '').replace('.', ','))}">${/ripian|livell/i.test(k) ? '' : '<i>mm</i>'}</span></label>`
      : `<label class="lbl">${esc(l)}<input class="field" data-tf="${esc(k)}" list="dl-prof" value="${esc(String(v ?? ''))}" spellcheck="false"></label>`;
    const misure = t.fields.filter(f => f[3] || numero(f[2])), tubi = t.fields.filter(f => !f[3] && !numero(f[2]));
    h += `<section class="sezione"><h4>Misure</h4><div class="form st-tpl">${misure.map(campo).join('')}</div></section>
      ${tubi.length ? `<section class="sezione"><h4>Tubi</h4><div class="form st-tpl">${tubi.map(campo).join('')}</div></section>` : ''}
      <datalist id="dl-prof">${(profili || []).map(p => `<option value="${esc(p)}">`).join('')}</datalist>
      <p class="hint t-nota">Cambia e premi «Applica le misure»: la struttura si rifà. I tubi ritoccati a mano restano.</p>`;
  } else h += `<p class="hint">Struttura disegnata: le misure si cambiano dal disegno (clic sul disegno nell’albero), il tubo cliccando i tubi.</p>`;
  const det = c ? [['Tubi da tagliare', `${c.tubi}, ${c.misure} ${c.misure === 1 ? 'misura' : 'misure'}`], ['Peso', `circa ${num(c.kg)} kg`]] : [];
  for (const r of s.rows || []) if (!(c && r[0] === 'Peso')) det.push(r);
  h += `<details class="fsec"><summary>Dettagli</summary>${tRighe(det)}</details>`;
  if (t) h += `<div class="t-piede"><button class="btn" id="tpl-apply">Applica le misure</button></div>`;
  $('#props').innerHTML = h + '</div>';
  if (!t) return;
  const vai = () => {
    const v = {};
    document.querySelectorAll('[data-tf]').forEach(i => { v[i.dataset.tf] = i.value.trim(); });
    inCoda(async () => { if (await apply(await call('structure_template_apply', s.id, v), 'Struttura rifatta con le misure nuove.')) await select('struct=' + s.id); });
  };
  $('#tpl-apply').onclick = vai;
  document.querySelectorAll('input[data-tf]').forEach(i => { i.onkeydown = ev => { if (ev.key === 'Enter') vai(); }; });
  bluSeCambia(document.querySelectorAll('[data-tf]'), $('#tpl-apply'));
}
// il tubo cliccato: le misure da officina in cima, poi cosa ci puoi fare, il tubo, come sta il profilo
function pannelloTubo(s, quanti) {
  const tb = s.tubo || {}, altri = (tb.gruppo_n || 1) - 1;
  const riga = k => s.rows.find(r => r[0] === k)?.[1];
  const tubo = riga('Tubo') || s.profile || '';
  const cose = s.group ? `${s.group}, ${tMinuscola(tubo)}` : tubo;
  const anc = Object.entries(s.anchors || {}).map(([k, v]) => `<option value="${k}"${k === s.anchor ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const n = ultimoClic?.id === s.id ? ultimoClic.normal : (tb.verticale ? [0, -1, 0] : null);   // in piedi: davanti
  const fatte = (s.lavorazioni || []).map(l => `<div class="riga"><span>${esc(l.label)}${l.through ? ' (passante)' : ''}${l.members.length > 1 ? `, su ${l.members.length} tubi` : ''}</span>
    <button class="btn piccolo" data-lav-sk="${esc(l.sketch)}">Modifica</button></div>`).join('');
  $('#props').innerHTML = `<div class="t-pan"><h3>${esc(s.title)}${quanti}</h3><p class="t-cose">${esc(cose)}</p>
    <section class="sezione t-misure">${tRighe(s.rows.filter(r => r[0] === 'Da tagliare' || r[0] === 'Batte contro'))}</section>
    <section class="sezione"><h4>Cosa puoi fare</h4><div class="cosa t-azioni">
      ${tb.facce?.length ? tAzione('id="p-dividi"', 'pattern_rect', 'Dividi il lato', `Montanti e traversi in mezzo: ${tb.facce.join(' o ').toLowerCase()}`) : ''}
      ${tAzione('id="p-trav"', 'traverso', 'Traverso da qui', 'Parte da questo tubo, poi clicchi dove arriva')}
      ${tAzione('id="p-punto"', 'tubo', 'Tubo nuovo da un punto di questo tubo', `${tb.verticale ? 'A che altezza da terra' : 'A che distanza dall’inizio'}, poi la freccia`)}
      <div class="t-punto" id="p-punto-riga" hidden><label class="lbl" for="p-punto-q">${tb.verticale ? 'Altezza da terra' : 'Distanza dall’inizio del tubo'}</label>
        <div class="t-in-riga"><span class="campo-unita"><input class="field" id="p-punto-q" value="" placeholder="es. 265"><i>mm</i></span>
        <button class="btn primary" id="p-punto-ok">Metti il punto</button></div><p class="hint">O passa col mouse sul tubo e clicca dove vuoi.</p></div>
      ${s.lavorabile ? tAzione('id="p-lav"', 'hole', `Disegna sulla faccia ${facciaCliccata(n)}`, 'Fori, asole, intagli: prima clicca la faccia giusta') : ''}
      ${tAzione('id="p-del" title="Canc"', 'delete', `Togli ${sel?.ids?.length > 1 ? sel.ids.length + ' tubi' : 'questo tubo'}`, '', 'danger')}
    </div>${!s.lavorabile && s.non_lavorabile ? `<p class="hint">${esc(s.non_lavorabile)}</p>` : ''}
    ${fatte ? `<div class="t-righe"><div class="sub">Lavorazioni sul tubo</div>${fatte}</div>` : ''}</section>
    <section class="sezione"><h4>Tubo</h4>
      <div class="t-in-riga"><input class="field" id="p-prof" list="dl-prof" value="${esc(s.profile)}" spellcheck="false" aria-label="Tubo"><button class="btn" id="p-apply">Cambia tubo</button></div>
      <datalist id="dl-prof">${(profili || []).map(p => `<option value="${esc(p)}">`).join('')}</datalist>
      ${altri > 0 ? `<label class="check"><input type="checkbox" id="p-all" checked> Anche gli altri ${altri === 1 ? 'tubo' : altri + ' tubi'} di «${esc(s.group)}»</label>` : ''}</section>
    <div id="p-pos"></div>
    <details class="fsec"><summary>Dettagli</summary>${tRighe(s.rows.filter(r => r[0] === 'Tubo' || r[0] === 'Peso'))}
      ${s.esterno ? '' : `<label class="lbl" for="p-anc">Linea d’asse sul profilo</label>
      <div class="t-in-riga"><select class="field" id="p-anc">${anc}</select><button class="btn" id="p-flip">Inverti</button></div>`}</details></div>`;
  const tutti = () => $('#p-all')?.checked ?? false;
  const edit = fields => inCoda(async () => apply(await call('edit_member', s.id, fields, tutti())));
  $('#p-apply').onclick = () => edit({ profile: $('#p-prof').value.trim() });
  $('#p-prof').onkeydown = ev => { if (ev.key === 'Enter') edit({ profile: $('#p-prof').value.trim() }); };
  bluSeCambia([$('#p-prof')], $('#p-apply'));
  // 03/11: come sta il profilo (rettangolare, angolare, piatto, UPN): le posizioni col disegnino della sezione vista
  // di testa, «su» in alto e «fuori» a destra; passandoci sopra l'anteprima nel 3D, clic = lo gira così
  chiamaMuto('member_posizioni', s.id).then(r => {
    const box = $('#p-pos');
    if (!box || !r.ok || !r.posizioni?.length) return;
    const tutti_ = r.posizioni.flatMap(p => p.disegno.flat());
    const m = Math.max(...tutti_.map(([x, y]) => Math.max(Math.abs(x), Math.abs(y)))) * 1.25 || 1;
    const svg = p => `<svg width="64" height="64" viewBox="${-m} ${-m} ${2 * m} ${2 * m}" aria-hidden="true">
      <line class="t-asse" x1="${-m}" y1="0" x2="${m}" y2="0" stroke-width="${m / 60}" stroke-dasharray="${m / 12}"/>
      <line class="t-asse" x1="0" y1="${-m}" x2="0" y2="${m}" stroke-width="${m / 60}" stroke-dasharray="${m / 12}"/>
      <path class="t-sezione" fill-rule="evenodd" stroke-width="${m / 40}" d="${p.disegno.map(c => 'M' + c.map(([x, y]) => `${x} ${-y}`).join(' L') + ' Z').join(' ')}"/></svg>`;
    box.innerHTML = `<section class="sezione"><h4>Come sta il profilo</h4><p class="hint">Visto di testa: ${esc(r.su)} in alto, ${esc(r.destra)} a destra.</p>
      <div class="angoli">${r.posizioni.map((p, i) => `<button class="angolo${p.ora ? ' on' : ''}" data-posiz="${i}">${svg(p)}<span>${esc(p.testo)}</span></button>`).join('')}</div></section>`;
    box.querySelectorAll('[data-posiz]').forEach(b => {
      const p = r.posizioni[+b.dataset.posiz], campi = { rotate: p.rotate, flip: p.flip };
      b.onclick = () => { anteprimaVia(); edit(campi); };
      b.onmouseenter = () => { if (!p.ora) anteprima('edit_member', () => [s.id, campi, tutti()], null); };
      b.onmouseleave = () => anteprimaVia();
    });
  });
  if ($('#p-flip')) $('#p-flip').onclick = () => edit({ toggle_flip: true });
  if ($('#p-anc')) $('#p-anc').onchange = () => edit({ anchor: $('#p-anc').value });
  $('#p-del').onclick = deleteSelected;
  $('#p-trav').onclick = () => iniziaTraverso(s.id);
  if ($('#p-dividi')) $('#p-dividi').onclick = () => iniziaDividi(s);
  // 03/11: un punto qualsiasi sul tubo (il montante a 265 da terra), poi le frecce come da un angolo
  $('#p-punto').onclick = () => {
    $('#p-punto-riga').hidden = false; $('#p-punto-q').focus();
    PUNTO = { id: s.id, mis: tb.misura, vert: !!tb.verticale };
    passoTubi(`Passa sul tubo e clicca dove parte il tubo nuovo, o scrivi ${tb.verticale ? 'l’altezza da terra' : 'la distanza'} a destra`);
  };
  $('#p-punto-q').oninput = () => { const q = parseFloat($('#p-punto-q').value.replace(',', '.')); if (PUNTO && isFinite(q)) puntoSegno(q); };
  const metti = () => {
    const q = $('#p-punto-q').value.trim();
    if (!q) { toast('Scrivi la misura.', 'err'); return; }
    const [st, mid] = s.id.split('/');
    puntoVia();
    inCoda(async () => { const r = await call('punto_su_tubo', st, mid, q); if (await apply(r) && r.node) await select(r.node); });
  };
  $('#p-punto-ok').onclick = metti;
  $('#p-punto-q').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); metti(); } };
  const lav = $('#p-lav');
  if (lav) lav.onclick = () => inCoda(async () => {
    const nn = ultimoClic?.id === s.id && ultimoClic.normal ? ultimoClic.normal : (tb.verticale ? [0, -1, 0] : [0, 0, 1]);
    const r = await call('sketch_on_tube', s.id, nn);
    if (await apply(r)) await enterSketch(r.sketch);
  });
  document.querySelectorAll('#props [data-lav-sk]').forEach(x => { x.onclick = () => enterSketch(x.dataset.lavSk); });
}
// la barra «prossimo passo» dei tubi (regola 4): una riga in basso al centro della vista, Esc scritto come tasto.
// È #trav-hint (le prove lo cercano lì): traverso, Dividi senza tubo, punto sul tubo
function passoTubi(testo, tasti = [['Esc', 'annulla']]) {
  const b = $('#trav-hint');
  if (!b) return;
  if (!testo) { b.hidden = true; b.textContent = ''; return; }
  b.innerHTML = `<span class="t-passo">${esc(testo)}</span>${tasti.map(([k, t]) => `<span class="g-tasto"><kbd>${esc(k)}</kbd> ${esc(t)}</span>`).join('')}`;
  b.hidden = false;
}
// 04/11 notte (attriti, E 7): la croce sopra il telaio si faceva con due «Traverso» (9 clic), «Dividi» la fa in 3.
// Un tubo del telaio sopra (o un tubo lungo) sdraiato: la barra in basso lo dice, col pulsante che parte da quel tubo
function tuboDaDividere(id) {
  const o = objs.get(id);
  if (!o?.mesh || o.data?.kind !== 'member') return false;
  const b = new THREE.Box3().setFromObject(o.mesh), tutto = new THREE.Box3();
  for (const x of objs.values()) if (x.mesh && x.data?.kind === 'member') tutto.expandByObject(x.mesh);
  const d = b.getSize(new THREE.Vector3()), lungo = Math.max(d.x, d.y);
  const sdraiato = d.z < 0.3 * lungo, sopra = b.max.z >= tutto.max.z - 1 && tutto.max.z - tutto.min.z > 3 * d.z;
  return sdraiato && (sopra || lungo >= 1000);
}
function consiglioDividi(id, conPasso = false) {
  if (!conPasso) passoTubi('Una croce o una griglia di traversi uguali?', []);
  const b = $('#trav-hint');
  b.insertAdjacentHTML('beforeend', (conPasso ? '<span class="g-sep"></span><span class="t-poi">Una croce?</span>' : '')
    + `<button type="button" class="btn piccolo" id="trav-dividi"><img src="icons/pattern_rect.svg" alt="">Dividi</button><span class="t-poi">${conPasso ? 'fa tutto in 3 clic' : 'li fa tutti in un colpo'}</span>`);
  $('#trav-dividi').onclick = () => {
    TRAV = null; passoTubi(null); nascondiMini();
    inCoda(async () => { await select(id); apriPannelloTubi(); await iniziaDividi({ id }); });
  };
}
// i disegnini dell'angolo: due tubi visti di fronte, come si saldano. I colori dal foglio di stile (chiaro e scuro):
// .gt-p il tubo che passa intero (chiaro), .gt-t quello tagliato (scuro), .gt-l il taglio
function disegnoGiunto(tipo) {
  const forme = {
    miter: `<polygon class="gt-t" points="10,10 26,26 26,76 10,76"/><polygon class="gt-p" points="10,10 76,10 76,26 26,26"/><line class="gt-l" x1="10" y1="10" x2="26" y2="26"/>`,
    verticale: `<rect class="gt-t" x="10" y="10" width="16" height="66"/><rect class="gt-p" x="27" y="10" width="49" height="16"/>`,
    orizzontale: `<rect class="gt-p" x="10" y="10" width="66" height="16"/><rect class="gt-t" x="10" y="27" width="16" height="49"/>`,
    // incroci (03/11): il tubo che passa è intero e chiaro, l'altro è in due pezzi scuri che gli battono contro
    // (staccati di un filo, così si vede subito chi è tagliato)
    croce_v: `<rect class="gt-p" x="35" y="4" width="16" height="78"/><rect class="gt-t" x="4" y="35" width="27" height="16"/><rect class="gt-t" x="55" y="35" width="27" height="16"/>`
      + `<line class="gt-l" x1="31" y1="33" x2="31" y2="53"/><line class="gt-l" x1="55" y1="33" x2="55" y2="53"/>`,
    croce_o: `<rect class="gt-p" x="4" y="35" width="78" height="16"/><rect class="gt-t" x="35" y="4" width="16" height="27"/><rect class="gt-t" x="35" y="55" width="16" height="27"/>`
      + `<line class="gt-l" x1="33" y1="31" x2="53" y2="31"/><line class="gt-l" x1="33" y1="55" x2="53" y2="55"/>`,
  };
  return `<svg class="giunto" width="56" height="56" viewBox="0 0 86 86" aria-hidden="true">${forme[tipo] || ''}</svg>`;
}
// la freccia di un verso (Su, Giù…) disegnata nel pulsante del pannello: come la vedi nel disegno iso
const VERSO_SVG = { su: 'M8 13V3M4 7l4-4 4 4', giu: 'M8 3v10M4 9l4 4 4-4', avanti: 'M11 5L4 12M4 7v5h5', dietro: 'M5 11l7-7M7 4h5v5',
  destra: 'M3 6l10 4M9 12.5l4-2.5-2-4', sinistra: 'M13 10L3 6M7 3.5L3 6l2 4' };
const versoSvg = d => `<svg class="t-verso" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="${VERSO_SVG[d] || ''}"/></svg>`;
// l'angolo (o l'incrocio, o un capo libero) cliccato: come si saldano i tubi qui, e il tubo nuovo da qui con le frecce
function nodePanel(s) {
  const a = s.angolo;
  let h = `<div class="t-pan"><h3>${esc(s.title)}</h3>`;
  h += `<p class="t-cose">${a ? (a.incrocio ? 'Due tubi che si incrociano' : (a.quanti || a.righe.length) === 1 ? 'Il capo di un tubo: da qui puoi continuare' : `Qui si incontrano ${a.quanti || a.righe.length} tubi`) : s.rows?.length ? esc(s.rows[0][1].replace(/^./, x => x.toUpperCase())) : 'Un capo libero: da qui parte un tubo nuovo'}</p>`;
  if (a && a.scelte.length) {
    h += `<section class="sezione"><h4>Come si saldano qui?</h4><div class="angoli">${a.scelte.map(x =>
      `<button class="angolo${x.key === a.ora ? ' on' : ''}" data-angolo="${x.key}">${disegnoGiunto(x.disegno)}<span>${esc(x.label)}</span></button>`).join('')}</div>
      ${a.simili > 1 ? `<label class="check"><input type="checkbox" id="n-tutti" checked> Uguale su tutti i ${a.simili} ${a.incrocio ? 'incroci' : 'angoli'} come questo</label>` : ''}
      <div class="t-righe">${tRighe(a.righe)}</div></section>`;
  } else if (a?.righe?.length) h += `<section class="sezione t-righe">${tRighe(a.righe)}</section>`;
  if (!ultimaAsta.profile) ultimaAsta.profile = s.default_profile;
  h += `<section class="sezione"><h4>Tubo nuovo da qui</h4>
    <p class="hint">Scrivi lunghezza e tubo, poi clicca una freccia nel disegno o qui sotto. Si riparte dal capo del tubo nuovo.</p>
    <div class="t-campi"><label class="lbl">Lunghezza<span class="campo-unita"><input class="field" id="n-len" value="${esc(ultimaAsta.length)}"><i>mm</i></span></label>
    <label class="lbl">Tubo<input class="field" id="n-prof" list="dl-prof2" value="${esc(ultimaAsta.profile)}" spellcheck="false"></label></div>
    <datalist id="dl-prof2">${(profili || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist>
    <label class="lbl">Nome (se vuoi)<input class="field" id="n-nome" value="" placeholder="es. Mensola"></label>
    <div class="dirs">${FRECCE.map(([d, t]) => `<button class="btn" data-freccia="${d}">${versoSvg(d)}${t}</button>`).join('')}</div>
    <div class="row-btns"><button class="btn" id="n-link">Unisci a un altro angolo…</button></div></section>`;
  const p = s.position;
  if (p.mode !== 'fixed') {
    const cosa = { abs: 'Misure da zero (mm, anche nomi di misure)', from: 'Spostamento dall’angolo da cui parte', sketch: 'Spostamento dal punto del disegno' }[p.mode];
    h += `<details class="fsec"><summary>Sposta l’angolo</summary><p class="hint">${esc(cosa)}: verso destra, verso dietro, verso su.</p><div class="xyz">${['Destra', 'Dietro', 'Su'].map((t, i) =>
      `<label>${t}<input class="field" data-xyz="${i}" value="${esc(String(p.values[i] ?? 0).replace('.', ','))}"></label>`).join('')}</div>
      <div class="row-btns"><button class="btn" id="n-move">Sposta</button></div></details>`;
  }
  return h + '</div>';
}
function wireNode(s) {
  // un capo libero (da zero, o la punta di una mensola): la barra in basso dice come si continua
  if ((s.angolo?.quanti ?? (s.angolo?.righe?.length || 0)) <= 1) passoTubi('Scrivi la lunghezza a destra, poi clicca una freccia: il tubo parte da qui', [['Esc', 'finisci']]);
  document.querySelectorAll('[data-angolo]').forEach(b => {
    b.onclick = () => inCoda(async () => {
      if (await apply(await call('set_angolo', s.structure, s.key, b.dataset.angolo, !!$('#n-tutti')?.checked))) await refreshSel();
    });
  });
  document.querySelectorAll('[data-freccia]').forEach(b => { b.onclick = () => tuboDaFreccia(nodes.find(x => x.id === s.id) || { structure: s.structure, key: s.key }, b.dataset.freccia); });
  if ($('#n-move')) {
    const sposta = () => inCoda(async () => apply(await call('move_node', s.structure, s.key,
      [...document.querySelectorAll('[data-xyz]')].map(x => x.value))));
    $('#n-move').onclick = sposta;
    document.querySelectorAll('[data-xyz]').forEach(x => { x.onkeydown = ev => { if (ev.key === 'Enter') sposta(); }; });
  }
  $('#n-link').onclick = () => {
    ricordaTubo();
    linkFrom = { st: s.structure, key: s.key, profile: ultimaAsta.profile, group: '' };
    passoTubi(null); paintNodes();              // la barra in basso dice cosa fare (Esc annulla)
  };
}
// --------------------------------------------------------------- distinta, cut list, info
// pezzi dell'assieme che non sono dove li aveva lasciati (23/10): quelli ritrovati da soli si dicono una volta,
// quelli che mancano restano in una striscia sopra il disegno finché non li indichi con «Cerca…»
let ritrovatiDetti = '';
function renderMancanti() {
  let bar = document.getElementById('mancanti');
  const lst = S?.mode === 'assembly' ? (S.mancanti || []) : [];
  const rit = S?.mode === 'assembly' ? (S.ritrovati || []) : [];
  const chiave = JSON.stringify(rit);
  if (rit.length && chiave !== ritrovatiDetti) {
    ritrovatiDetti = chiave;
    toast(`Ritrovat${rit.length === 1 ? 'o' : 'i'} da solo: ${rit.map(x => `${x.name} (in ${x.folder})`).join(', ')}. Salva l’assieme per ricordarlo.`);
  }
  if (!lst.length) { if (bar) bar.hidden = true; return; }
  if (!bar) { bar = document.createElement('div'); bar.id = 'mancanti'; document.getElementById('view').appendChild(bar); }
  bar.hidden = false;
  bar.innerHTML = `<b>${lst.length === 1 ? 'Un pezzo non si trova' : lst.length + ' pezzi non si trovano'}</b>
    <span>Spostati o cancellati: li ho cercati accanto all’assieme e in Documenti\\SteelCAD.</span>
    ${lst.map(x => `<span class="manca-riga"><span title="${esc(x.file)}">${esc(x.name)}${x.n > 1 ? ` (${x.n} volte)` : ''}</span><button class="btn" data-cerca-pezzo="${esc(x.file)}">Cerca…</button></span>`).join('')}`;
  bar.querySelectorAll('[data-cerca-pezzo]').forEach(b => { b.onclick = () => inCoda(async () => {
    const r = await call('asm_ritrova', b.dataset.cercaPezzo);
    if (r.cancelled) return;
    await apply(r, r.message);
  }); });
}
// le saldature segnate sul pezzo: un cordone arancio sugli spigoli (24/10)
// var: buildScene (più su) li usa, e il file può girare prima di arrivare qui
var SALD_MAT = new THREE.LineBasicMaterial({ color: 0xE8890C, depthTest: false, transparent: true });
var saldGroup = new THREE.Group();
function disegnaSaldature() {
  SPESSORE.set(SALD_MAT, 5);
  if (saldGroup.parent !== model) model.add(saldGroup);
  saldGroup.traverse(x => x.geometry?.dispose()); saldGroup.clear();
  const tratti = [];
  for (const w of S?.saldature || []) for (const l of w.linee) {
    const pts = [];
    for (let i = 0; i + 2 < l.length; i += 3) pts.push(new THREE.Vector3(l[i], l[i + 1], l[i + 2]));
    tratti.push([pts, SALD_MAT]);
  }
  lineeInBlocco(saldGroup, tratti, 20);
  ridisegna();
}
// 03/11: il pezzo di tubo disegnato coi suoi tagli (dritto, 45° a trapezio o a parallelogramma), accanto alla scritta:
// chi taglia vede subito come vengono le punte
function formaPezzo(r) {
  const ang = (r.cuts || []).map(c => /°/.test(c) ? parseFloat(c.replace(',', '.')) : 0);
  if (!ang.some(a => a)) return '';
  // notte 03/11: un po' più grande e coi colori del foglio di stile (si vede anche sullo scuro)
  const W = 56, h = 12, o = a => Math.min(18, h * Math.tan(a * Math.PI / 180));
  const [a0, a1] = ang.length === 2 ? ang : [ang[0] || 0, 0];
  const pts = r.forma === 'parallelo' ? [[o(a0), 0], [W, 0], [W - o(a1), h], [0, h]]
    : [[o(a0), 0], [W - o(a1), 0], [W, h], [0, h]];
  return `<svg class="forma-pezzo" width="${W + 2}" height="${h + 2}" viewBox="-1 -1 ${W + 2} ${h + 2}" aria-hidden="true"><polygon points="${pts.map(p => p.join(',')).join(' ')}"/></svg>`;
}
function renderBottom() {
  renderMancanti();
  disegnaSaldature();
  const b = S.bom;
  $('#tab-bom').innerHTML = b.length ? `<table class="grid"><thead><tr><th>Codice</th><th>Descrizione</th><th class="n">Q.tà</th>
    <th>Materiale</th><th>Profilo / spessore</th><th class="n">Peso cad. kg</th><th class="n">Peso tot. kg</th></tr></thead><tbody>
    ${b.map(r => `<tr><td>${esc(r.code)}</td><td>${esc(r.description)}</td><td class="n">${r.qty}</td><td>${esc(r.material)}</td>
      <td>${esc(r.profile || (r.thickness_mm != null ? 'sp. ' + num(r.thickness_mm) + ' mm' : ''))}</td>
      <td class="n">${kg(r.kg_each)}</td><td class="n">${kg(r.kg_total)}</td></tr>`).join('')}
    <tr class="tot"><td colspan="6">Totale</td><td class="n">${kg(S.bom_kg)}</td></tr></tbody></table>`
    : '<p class="empty">Il progetto è vuoto.</p>';
  const sw = S.saldature || [];
  if (sw.length) {                                 // le saldature: per tipo e misura, coi metri
    const nome = w => w.tipo === 'angolo' ? `d’angolo${w.a ? ' a' + w.a : ''}` : `di testa a ${w.tipo}${w.a ? ' s' + w.a : ''}`;
    const tot = {};
    for (const w of sw) tot[nome(w)] = (tot[nome(w)] || 0) + w.m;
    $('#tab-bom').insertAdjacentHTML('beforeend', `<h4 style="margin:12px 0 4px">Saldature</h4><table class="grid"><thead><tr><th>Tipo</th><th class="n">Spigoli</th><th class="n">Metri</th><th></th></tr></thead><tbody>
      ${sw.map(w => `<tr${w.persa ? ' class="warn"' : ''}><td>${esc(nome(w))}${w.persa ? ' · <b>uno spigolo non c’è più</b>' : ''}</td><td class="n">${w.spigoli}</td>
        <td class="n">${num(w.m, 2)}</td><td class="n"><button class="btn" data-sald-via="${w.i}" title="Togli questa saldatura">×</button></td></tr>`).join('')}
      ${Object.entries(tot).map(([k, m]) => `<tr class="tot"><td colspan="2">Totale ${esc(k)}</td><td class="n">${num(m, 2)} m</td><td></td></tr>`).join('')}</tbody></table>`);
    $('#tab-bom').querySelectorAll('[data-sald-via]').forEach(b => { b.onclick = () => inCoda(async () => apply(await call('del_saldatura', +b.dataset.saldVia))); });
  }

  const c = S.cutlist;
  // 03/11: come la distinta di taglio della tavola: posizione, nome da officina (mai le sigle dei tubi), poi le misure
  $('#tab-cut').innerHTML = c.rows.length ? `<div class="cols t-taglio"><table class="grid"><thead><tr><th class="n">Pos.</th><th>Nome</th><th>Tubo</th><th class="n">Lunghezza (mm)</th>
    <th>Tagli</th><th class="n">Pezzi</th><th class="n">kg cad.</th><th class="n">kg tot.</th></tr></thead><tbody>
    ${c.rows.map((r, i) => `<tr data-ids="${esc(r.members.join(','))}"><td class="n t-pos">${i + 1}</td><td>${esc(r.nome || (r.dove || r.groups).join(', '))}</td>
      <td class="t-nowrap">${esc(r.profile)} <span class="spento">${esc(r.material)}</span></td><td class="n t-lung">${num(r.length_mm)}</td>
      <td><span class="t-tagli">${formaPezzo(r)}<span>${esc(r.tagli_testo || r.tagli || r.cuts.join(' / '))}</span></span></td><td class="n"><b>${r.qty}</b></td>
      <td class="n">${kg(r.kg_each)}</td><td class="n">${kg(r.kg_total)}</td></tr>`).join('')}
    <tr class="tot"><td colspan="5">Totale</td><td class="n">${c.pieces}</td><td></td><td class="n">${kg(c.kg)}</td></tr></tbody></table>
    <table class="grid"><thead><tr><th>Per tubo</th><th class="n">Pezzi</th><th class="n">Metri</th><th class="n">kg</th></tr></thead><tbody>
    ${c.totals.map(t => `<tr><td class="t-nowrap">${esc(t.profile)} <span class="spento">${esc(t.material)}</span></td><td class="n">${t.pieces}</td>
      <td class="n">${num(t.total_length_mm / 1000, 2)}</td><td class="n">${kg(t.kg)}</td></tr>`).join('')}</tbody></table></div>`
    + (c.accessori?.length ? `<h4 class="t-sotto">Piedi e tappi</h4><table class="grid t-acc"><thead><tr><th>Descrizione</th><th class="n">Pezzi</th><th>Dove va</th><th class="n">kg cad.</th><th class="n">kg tot.</th></tr></thead><tbody>
      ${c.accessori.map(a => `<tr data-ids="${esc(a.ids.join(','))}"><td>${esc(a.description)}${a.acquisto ? ' <span class="t-compra">da acquistare</span>' : ''}</td><td class="n"><b>${a.qty}</b></td>
        <td title="${esc(a.dove.join(', '))}">${esc(a.dove.slice(0, 2).join(', ') + (a.dove.length > 2 ? ` e altre ${a.dove.length - 2}` : ''))}</td><td class="n">${a.kg_each ? kg(a.kg_each) : ''}</td><td class="n">${a.kg_total ? kg(a.kg_total) : ''}</td></tr>`).join('')}</tbody></table>` : '')
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
  // 04/11: niente «·» (brief); «mancano dati di piega» solo se il pezzo ha pieghe (una piastra piana non ne ha bisogno)
  const sum = [b.length ? `Distinta: ${b.length === 1 ? '1 riga' : b.length + ' righe'}, ${kg(S.bom_kg)} kg` : 'Distinta vuota'];
  if (S.sheet?.missing?.length && (S.sheet.data?.bends?.length || S.sheet.shape)) sum.push('Lamiera: mancano dati di piega');
  if (n) sum.push(`${n} ${n === 1 ? 'avviso' : 'avvisi'}`);
  $('#bottom-sum').textContent = sum.join('; ');
}
// pannello in basso (il cassetto): chiuso è una barretta col riassunto; si apre col clic su una scheda (Distinta,
// Info…) e si chiude con la freccia o con un altro clic sulla scheda aperta. 04/11: parte SEMPRE chiuso, la vista prende lo spazio (non si ricorda aperto)
let bassoAperto = false;
function setBottom(aperto) {
  bassoAperto = aperto;
  document.body.classList.toggle('bottom-closed', !aperto);
  $('#bottom-arrow').textContent = aperto ? '▾' : '▴';
  $('#bottom-toggle').title = aperto ? 'Chiudi il pannello in basso (più spazio al 3D)' : 'Apri il pannello in basso';
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
  // 04/11 sera: clic sulla scheda già aperta = chiude il cassetto (come la freccia)
  if (bassoAperto && b.classList.contains('on')) { setBottom(false); return; }
  showTab(b.dataset.tab, true);
});

// ===================================================================== comandi
// le notifiche (23/10, polish): un'icona per tipo (errore, fatto, informazione), e se serve un pulsante (Annulla)
const ICONE_TOAST = { err: '!', ok: '✓', '': 'i' };
function toast(msg, kind = '', azione = null, durata = 0) {
  const t = document.createElement('div');
  // un lavoro riuscito è verde (brief: verde = fatto), anche «Fatti 4 fori.», «Traverso aggiunto.», «4 tubi aggiunti…» (04/11)
  if (!kind && (/^(fatt[oaie](?![a-z])|salvat|tavole salvate|quota tolta|aggiunt|creat|esportat|tagliat)/i.test(String(msg))
    || /^[^.:]{0,40}[ ]aggiunt[oaie](?![a-z])/i.test(String(msg)))) kind = 'ok';
  t.className = 'toast ' + kind;
  const ic = document.createElement('span'); ic.className = 'ti'; ic.textContent = ICONE_TOAST[kind] ?? 'i';
  const tx = document.createElement('span'); tx.className = 'tt'; tx.textContent = msg;
  t.append(ic, tx);
  if (azione) {
    const b = document.createElement('button'); b.className = 'ta'; b.textContent = azione.label;
    b.onclick = () => { t.remove(); azione.fn(); };
    t.append(b);
  }
  $('#toasts').appendChild(t);
  while ($('#toasts').children.length > 3) $('#toasts').firstChild.remove();
  const via = () => { t.classList.add('via'); setTimeout(() => t.remove(), 220); };
  setTimeout(via, durata || (kind === 'err' ? 7000 : azione ? 6000 : 3500));
}

// aggiornamenti (23/10): Radius installato guarda se su GitHub c'è una versione nuova; «Aggiorna» la scarica e la
// installa (Radius si chiude e si riapre da solo)
async function controllaAggiornamenti() {
  if (DEV) return;
  let r;
  try { r = await call('update_check'); } catch { return; }
  if (!r?.ok || !r.nuova) return;
  toast(`È uscita Radius ${r.nuova}${r.mb ? ` (${r.mb} MB)` : ''}.`, '', {
    label: 'Aggiorna',
    fn: async () => {
      const sporco = S?.dirty;
      if (sporco && !confirm('Ci sono modifiche non salvate: Radius le mette nel salvataggio automatico e si chiude per aggiornarsi. Continuare?')) return;
      toast('Scarico l’aggiornamento…', '', null, 60000);
      const x = await call('update_install', r.url);
      toast(x?.message || 'Aggiornamento non riuscito.', x?.ok ? 'ok' : 'err');
    },
  }, 30000);
}

// ------------------------------------------------------------- anteprima dei comandi (22/10)
// «ci deve essere SEMPRE una preview del comando»: mentre la finestra è aperta il risultato si vede in trasparenza
// nel 3D, calcolato dal motore su una copia del progetto (è proprio quello che verrà). Se non si può: rosso e perché.
const ANT_MAT = new THREE.MeshStandardMaterial({ color: 0x5FA8F5, metalness: 0.1, roughness: 0.6, transparent: true, opacity: 0.75,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
const ANT_EDGE = new THREE.LineBasicMaterial({ color: 0x8CC0FF });
// 29/10: quando non si può fare, quello che hai chiesto si vede lo stesso, in rosso (sopra al pezzo, che resta)
const ANT_ROSSO = new THREE.MeshStandardMaterial({ color: 0xE5484D, metalness: 0.05, roughness: 0.6, transparent: true, opacity: 0.8,
  depthTest: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
const ANT_ROSSO_EDGE = new THREE.LineBasicMaterial({ color: 0xFF9B9E, depthTest: false });
function gruppoAnteprima(oggetti, mat, edge) {
  const gr = new THREE.Group();
  for (const d of oggetti) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(d.positions, 3)); g.setIndex(d.indices); g.computeVertexNormals();
    const seg = [];
    for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
    const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
    const m = new THREE.Mesh(g, mat), l = new THREE.LineSegments(lg, edge);
    m.raycast = () => {}; l.raycast = () => {}; m.renderOrder = l.renderOrder = 6;
    gr.add(m, l);
  }
  return gr;
}
const ANT_TOGLI = new THREE.MeshStandardMaterial({ color: 0xE8833A, transparent: true, opacity: 0.55, depthTest: false });
const ANT_TOGLI_EDGE = new THREE.LineBasicMaterial({ color: 0xFFB27A, depthTest: false });
// il pulsante che conferma, spento finché l'anteprima è rossa
function confermaAccesa(stato, si) {
  const b = stato?.closest('#modal-box, #props')?.querySelector('#m-ok, #f-add');
  if (!b) return;
  b.disabled = !si;
  b.title = si ? '' : 'Prima sistema quello in rosso';
}
let antGruppo = null, antTimer = null, antN = 0, antCamera = null, antUltimi = '', antNascosto = false, antInVolo = false, antDopo = null;
function anteprimaVia() {
  clearTimeout(antTimer); antN++; antUltimi = '';
  applicaSposta(spostaBase);                        // lo spostamento dell'ultimo Inquadra (la parte libera della vista)
  if (antCamera) {                                  // la vista torna com'era prima della finestra
    camera.position.copy(antCamera.pos); controls.target.copy(antCamera.target); controls.update(); antCamera = null; ridisegna();
  }
  // il pezzo si rimostra solo se l'aveva nascosto l'anteprima: guardando lo sviluppo deve restare nascosto (23/10:
  // dopo Spiega, una finestra aperta e chiusa rimetteva il pezzo piegato sopra lo sviluppo)
  if (antNascosto) { model.visible = true; overlay.visible = true; antNascosto = false; }
  if (!antGruppo) return;
  scene.remove(antGruppo);
  antGruppo.traverse(o => o.geometry?.dispose());
  antGruppo = null;
  paint();
}
async function chiamaMuto(name, ...args) {          // come call, senza la finestrella «Sto lavorando…»
  if (!DEV) return await window.pywebview.api[name](...args);
  const r = await fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args) });
  return await r.json();
}
// il disegno si sposta a sinistra della finestra laterale, così la finestra non copre l'anteprima
function anteprimaSpazio() {
  const box = $('#modal.laterale .modal-box'), cv = document.getElementById('c3d');
  if (!box || !cv) return;
  const w = cv.clientWidth, h = cv.clientHeight, dx = Math.round((box.offsetWidth + 24) / 2);
  camera.setViewOffset(w, h, dx, 0, w, h);
  ridisegna();
}
// metodo: il comando del motore; argomenti: funzione che legge la finestra; stato: dove scrivere com'è andata;
// opz.vista: 'iso' = al primo risultato gira la vista in isometrica (per vedere anche la profondità)
function anteprima(metodo, argomenti, stato, opz = {}) {
  // stessi valori di prima (es. il campo che perde il fuoco cliccando Annulla): niente da rifare. Se si rifacesse, la
  // scritta sotto cambierebbe lunghezza e il pulsante scapperebbe sotto il mouse (22/10)
  const chiave = metodo + JSON.stringify(argomenti());
  if (chiave === antUltimi) return;
  antUltimi = chiave;
  clearTimeout(antTimer);
  const n = ++antN;
  anteprimaSpazio();
  if (stato) {                                    // la scritta di prima resta (più chiara) finché arriva la nuova
    stato.classList.add('calcolo');
    if (!stato.textContent) stato.textContent = 'Preparo l’anteprima…';
  }
  // 29/10: parte dopo 0,12 s; se il motore ne sta già facendo una, questa aspetta e poi si fa solo l'ultima (prima
  // scrivendo «12» si calcolava anche quella per «1»: 2 secondi buttati)
  antTimer = setTimeout(async function giro() {
    if (n !== antN) return;                       // annullata o superata da una più nuova
    if (antInVolo) { antDopo = giro; return; }
    antInVolo = true;
    let r;
    try { r = await chiamaMuto('anteprima', metodo, argomenti()); } catch (e) { r = { ok: false, message: String(e) }; }
    finally { antInVolo = false; }
    const dopo = antDopo; antDopo = null;
    if (dopo) { dopo(); }
    if (n !== antN) return;                       // nel frattempo hai cambiato un valore: vale l'ultima
    if (antGruppo) { scene.remove(antGruppo); antGruppo.traverse(o => o.geometry?.dispose()); antGruppo = null; }
    if (r.message) r.message = r.message.replace(/^Non applicato:\s*/, '');
    opz.dopo?.(r);
    if (!r.ok) {
      if (antNascosto) { model.visible = true; overlay.visible = true; antNascosto = false; }
      if (stato) { stato.className = 'ant-stato no'; stato.textContent = r.message || 'Così non si può fare.'; }
      // 29/10: la soluzione con un clic, dentro l'anteprima rossa: scrive il valore giusto nel campo e l'anteprima si rifà
      const box = stato?.closest('#modal-box, #props');
      const CAMPI_SOL = { length: '[id$="-len"]', angle: '[id$="-ang"]', D: '#h-D', angolo: '#h-ang' };
      const sol = (r.soluzioni || []).filter(x => Object.keys(x.cambia || {}).every(k => CAMPI_SOL[k] && box?.querySelector(CAMPI_SOL[k])));
      if (sol.length) {
        stato.insertAdjacentHTML('beforeend', `<span class="ant-sol">${sol.map((x, i) => `<button type="button" class="btn" data-sol="${i}" title="${esc(x.sotto || '')}">${esc(x.testo)}</button>`).join('')}</span>`);
        stato.querySelectorAll('[data-sol]').forEach(b => {
          b.onclick = () => {
            for (const [k, v] of Object.entries(sol[+b.dataset.sol].cambia)) {
              const i = box.querySelector(CAMPI_SOL[k]);
              i.value = virgola(v); i.dispatchEvent(new Event('input', { bubbles: true }));
            }
          };
        });
      }
      if (r.fantasma?.length) { antGruppo = gruppoAnteprima(r.fantasma, ANT_ROSSO, ANT_ROSSO_EDGE); scene.add(antGruppo); }
      if (r.vero) confermaAccesa(stato, false);
      paint();
      return;
    }
    confermaAccesa(stato, true);
    if (model.visible) { model.visible = false; overlay.visible = false; antNascosto = true; }   // al posto del pezzo di adesso, quello che verrà
    antGruppo = new THREE.Group();
    for (const d of r.objects) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(d.positions, 3)); g.setIndex(d.indices); g.computeVertexNormals();
      const seg = [];
      for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
      const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
      const m = new THREE.Mesh(g, ANT_MAT), l = new THREE.LineSegments(lg, ANT_EDGE);
      m.raycast = () => {}; l.raycast = () => {}; m.renderOrder = l.renderOrder = 5;
      antGruppo.add(m, l);
    }
    if (r.togli?.length) antGruppo.add(gruppoAnteprima(r.togli, ANT_TOGLI, ANT_TOGLI_EDGE));   // quello che si toglie, in arancio
    scene.add(antGruppo);
    if (stato) {
      stato.className = 'ant-stato ok';
      // DIVIDI: quanti tubi e che quadri vengono (03/11), è la cosa che l'officina controlla
      // 04/11 (percorso A): anche il profilo in lamiera dice cosa viene («calandrato R55 interno…») prima di confermare:
      // con la parte sbagliata il collare veniva R52 e lo si scopriva solo dal messaggio, dopo
      const dice = (metodo === 'dividi' || /^Profilo in lamiera/.test(r.message || '')) && r.message;
      stato.textContent = opz.frase ? '' : dice ? `In azzurro: ${r.message}` : 'Anteprima: in azzurro il pezzo come verrà.';
    }
    // se il risultato esce dalla vista, si allarga l'inquadratura per vederlo tutto
    const box = new THREE.Box3().setFromObject(antGruppo);
    if (!box.isEmpty() && opz.vista === 'iso' && !antCamera) {
      antCamera = { pos: camera.position.clone(), target: controls.target.clone() };
      fitBox(box.union(new THREE.Box3().setFromObject(model)), vistaIso(), false, true, true);
    } else if (!box.isEmpty()) {
      const fr = new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse));
      if (!fr.containsPoint(box.min) || !fr.containsPoint(box.max)) fitBox(box.union(new THREE.Box3().setFromObject(model)), null, true);
    }
    paint();
  }, 120);
}
// l'anteprima nel pannello a destra (le pieghe sui bordi: 23/10, «anche per le pieghe la preview del su/giù,
// così non sbaglio il senso»): sotto i campi la riga dello stato; ogni campo cambiato, o Verso/Misura, la rifà.
// Si toglie da sola quando il pannello cambia (altra selezione, piega aggiunta)
function anteprimaPannello(metodo, argomenti, dentro = '#props') {
  const box = $(dentro);
  if (!box) return;
  let st = box.querySelector('.ant-stato');
  if (!st) {
    st = document.createElement('div'); st.className = 'ant-stato';
    (box.querySelector('#f-add')?.closest('.row-btns') || box.querySelector('.t-piede') || box.querySelector('.row-btns') || box.lastElementChild)?.before(st);
  }
  const vai = () => anteprima(metodo, argomenti, st);
  box.querySelectorAll('input, select').forEach(i => { i.addEventListener('input', vai); i.addEventListener('change', vai); });
  box.querySelectorAll('.seg').forEach(g => g.addEventListener('change', vai));
  vai();
}
// una finestra con l'anteprima: si mette di lato, sotto i campi la riga dello stato, e ogni campo cambiato rifà
// l'anteprima. Nel disegno (sketch) la vista gira in isometrica, se no lo spessore e la profondità non si vedono
function conAnteprima(metodo, argomenti, opz = {}) {
  $('#modal').classList.add('laterale');
  const box = $('#modal-box');
  let st = box.querySelector('.ant-stato');
  if (!st) { st = document.createElement('div'); st.className = 'ant-stato'; (box.querySelector('.acts') || box).before(st); }
  const o = { vista: SK ? 'iso' : undefined, ...opz };
  if (SK) controls.enableRotate = true;               // 30/10: l'anteprima si gira col mouse anche dal disegno
  const vai = () => anteprima(metodo, argomenti, st, o);
  box.querySelectorAll('input, select').forEach(i => { i.addEventListener('input', vai); i.addEventListener('change', vai); });
  box.querySelectorAll('.seg button').forEach(b => b.addEventListener('click', () => setTimeout(vai)));
  vai();
}
// la finestra si chiude (Annulla, Esc, OK): l'anteprima sparisce
new MutationObserver(() => { if ($('#modal').hidden) { anteprimaVia(); $('#modal').classList.remove('laterale'); if (SK) controls.enableRotate = false; } })
  .observe(document.getElementById('modal'), { attributes: true, attributeFilter: ['hidden'] });

// opz.stretta: una domanda breve (conferma, un nome, un campo solo) in una finestra stretta
// 04/11 notte (occhio): «Spessore (mm)» con la casella sotto diventa «Spessore» e la casella con «mm» dentro, come in
// tutte le altre finestre e nei pannelli (.campo-unita). Solo l'aspetto: la casella resta la stessa (id, eventi)
function unitaDentro(box) {
  for (const lab of box.querySelectorAll('label')) {
    const t = [...lab.childNodes].find(n => n.nodeType === 3 && /\s\(mm\)\s*$/.test(n.textContent));
    const inp = [...lab.children].find(c => c.matches('input.field'));
    if (!t || !inp) continue;
    t.textContent = t.textContent.replace(/\s\(mm\)\s*$/, '');
    const cu = document.createElement('span');
    cu.className = 'campo-unita';
    inp.replaceWith(cu);
    cu.append(inp, Object.assign(document.createElement('i'), { textContent: 'mm' }));
  }
}
function modal(html, wire, opz = {}) {
  $('#modal-box').classList.remove('wide', 'nuovo', 'prepara', 'fatto', 'stretta');
  if (opz.stretta) $('#modal-box').classList.add('stretta');
  $('#modal').classList.remove('laterale');
  $('#modal-box').innerHTML = html;
  unitaDentro($('#modal-box'));
  $('#modal').hidden = false;
  const close = () => { $('#modal').hidden = true; };
  wire(close);
  const primo = $('#modal-box').querySelector('input, button.primary');
  primo?.focus();
  // il primo campo col testo già scelto: chi scrive 30 sopra «1000» ha 30, non «100030» (04/11, percorsi A e D)
  if (primo?.tagName === 'INPUT' && /^(text|number|search|)$/.test(primo.type)) primo.select();
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
  const svg = (c, h = 380) => `<svg viewBox="0 0 520 ${h}" role="img" aria-label="Disegno con le misure">${c}</svg>`;
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
      ${qv(40, 120, 310)}${b(40, 215, 'C')}`, 410),            // 410: le lettere A e B in basso non si tagliano
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
    // 04/11: anche le partenze senza misure hanno il loro disegno: si capisce cosa succede dopo il clic
    zero: svg(`<path class="gr" d="M40 60H480M40 120H480M40 180H480M40 240H480M40 300H480M80 30V340M160 30V340M240 30V340M320 30V340M400 30V340"/>
      <g class="ln"><path class="pz" d="M100 290V130h110l50 50h150v110z"/></g>
      <g class="pt"><circle cx="100" cy="290" r="6"/><circle cx="100" cy="130" r="6"/><circle cx="210" cy="130" r="6"/><circle cx="260" cy="180" r="6"/><circle cx="410" cy="180" r="6"/><circle cx="410" cy="290" r="6"/></g>
      ${qo(100, 410, 330)}<text class="nota" x="190" y="322">la misura la scrivi tu</text>`),
    disegno: svg(`<path class="gr" d="M40 60H480M40 120H480M40 180H480M40 240H480M40 300H480M80 30V340M160 30V340M240 30V340M320 30V340M400 30V340"/>
      <g class="ln tubo"><path d="M120 310V90h280v220M120 200h280"/></g>
      <g class="pt"><circle cx="120" cy="310" r="7"/><circle cx="120" cy="90" r="7"/><circle cx="400" cy="90" r="7"/><circle cx="400" cy="310" r="7"/><circle cx="120" cy="200" r="7"/><circle cx="400" cy="200" r="7"/></g>
      <text class="nota" x="150" y="160">ogni linea è un tubo</text>`),
    vuoto: svg(`<g class="ln"><path d="M150 300l220 0M150 300l-70 40M150 300V110"/></g>
      <g class="pt"><circle cx="150" cy="300" r="9"/></g>
      <path class="q" d="M380 300h40M410 290l12 10-12 10M150 100V60M140 72l10-14 10 14M74 344l-30 18M50 350l-8 14 16 0"/>
      <text class="nota" x="180" y="270">parti da un angolo e tiri i tubi</text>`),
    tramoggia_cassone: svg(`<g class="ln"><path class="pz" d="M110 60h300v120H110z"/><path d="M110 180l120 120h60l120-120M230 300v40h60v-40"/></g>
      ${qo(110, 410, 32)}${b(260, 32, 'A')}${qv(450, 60, 180)}<text class="nota" x="462" y="126">Hc</text>
      ${qo(230, 290, 360)}<text class="nota" x="300" y="366">a</text>${qv(70, 180, 300)}<text class="nota" x="40" y="246">Ht</text>`),
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
    lamiera: { titolo: 'Lamiera', bottone: 'Crea la lamiera', nota: 'Un rettangolo dello spessore che vuoi: se serve lo pieghi dopo, cliccando i bordi.', nome: 'Lamiera',
      campi: [{ k: 'larghezza', l: 'Larghezza', v: 500, lettera: 'A' }, { k: 'profondita', l: 'Profondità', v: 300, lettera: 'B' },
        { k: 'spessore', l: 'Spessore', v: 2, lettera: 'C' }, ...piega] },
    piastra: { titolo: 'Piastra piana', bottone: 'Crea la piastra', nota: 'Piastra con un foro; gli altri fori li aggiungi dopo.', nome: 'Piastra',
      campi: [{ k: 'larghezza', l: 'Larghezza', v: 300, lettera: 'A' }, { k: 'altezza', l: 'Altezza', v: 200, lettera: 'B' },
        { k: 'foro', l: 'Diametro del foro', v: 30, lettera: 'C' }, { k: 'spessore', l: 'Spessore', v: 5, lettera: 'D' }] },
    zero: { titolo: 'Da zero', bottone: 'Inizia a disegnare', nota: 'Disegni la sagoma con linee e archi. Chiusa diventa lamiera o piastra; aperta (un collare, un omega) diventa lamiera piegata con «Estrudi in lamiera».', nome: 'Pezzo', campi: [] },
    telaio: { titolo: 'Telaio in tubo', bottone: 'Crea il telaio', nota: 'Misure fuori tutto: il telaio finito è grande così, i tubi stanno dentro.', nome: 'Banco',
      campi: [{ k: 'L', l: 'Lunghezza', v: 1600, lettera: 'A' }, { k: 'P', l: 'Profondità', v: 700, lettera: 'B' },
        { k: 'H', l: 'Altezza (piano di lavoro)', v: 850, lettera: 'C' },
        { k: 'ripiano', l: 'Ripiano sotto, da terra (0 = senza)', v: 150 },
        { k: 'profilo', l: 'Tubo del telaio', v: '40x40x3', prof: true },
        { k: 'gambe', l: 'Tubo delle gambe', v: '40x40x3', prof: true }, { k: 'tubo_ripiano', l: 'Tubo del ripiano', v: '30x30x2', prof: true }] },
    scaffale: { titolo: 'Scaffale o telaio', bottone: 'Crea lo scaffale', nota: 'Scaffali e telai per armadi. Misure fuori tutto; i piani hanno la stessa luce tra un tubo e l’altro. Tubi uguali? Scrivi lo stesso nei due campi.', nome: 'Scaffale',
      campi: [{ k: 'L', l: 'Larghezza', v: 1000, lettera: 'A' }, { k: 'P', l: 'Profondità', v: 400, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 1800, lettera: 'C' }, { k: 'ripiani', l: 'Quanti piani (a terra e in cima compresi)', v: 4, lettera: 'D' },
        { k: 'montanti', l: 'Tubo dei montanti', v: '30x30x2', prof: true }, { k: 'traversi', l: 'Tubo dei traversi', v: '40x20x2', prof: true }] },
    armadio: { titolo: 'Telaio per armadio', bottone: 'Crea il telaio', nota: 'Misure in asse dei tubi: sotto vedi il fuori tutto.', nome: 'Telaio armadio',
      campi: [{ k: 'L', l: 'Larghezza', v: 800, lettera: 'A' }, { k: 'P', l: 'Profondità', v: 600, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 2000, lettera: 'C' }, { k: 'ripiani', l: 'Quanti livelli (sotto e sopra compresi)', v: 3, lettera: 'D' },
        { k: 'profilo', l: 'Tubo', v: '40x40x2', prof: true }] },
    cancello: { titolo: 'Cancello', bottone: 'Crea il cancello', nota: 'Misure fuori tutto. La luce tra le sbarre è a filo interno, anche contro il telaio.', nome: 'Cancello',
      campi: [{ k: 'L', l: 'Larghezza', v: 1500, lettera: 'A' }, { k: 'H', l: 'Altezza', v: 1200, lettera: 'B' },
        { k: 'passo', l: 'Luce tra le sbarre, circa', v: 120, lettera: 'C' },
        { k: 'telaio', l: 'Tubo del telaio', v: '60x60x3', prof: true }, { k: 'sbarre', l: 'Tubo delle sbarre', v: '20x20x2', prof: true }] },
    disegno: { titolo: 'Disegna la sagoma', bottone: 'Inizia a disegnare', nota: 'Disegni la sagoma (un fianco, un portale): ogni linea diventa un tubo, poi la ripeti dietro. Misure fuori tutto.', nome: 'Struttura',
      campi: [{ k: 'piano', l: 'Da dove la guardi mentre la disegni', v: 'XZ',
        scelte: { XZ: 'Di fronte: cancelli, spalle, portali', XY: 'Dall’alto: basamenti, telai a terra', YZ: 'Di fianco' } }] },
    cono: { titolo: 'Cono o tronco di cono', bottone: 'Crea il cono', nota: 'Misure finite del pezzo.', nome: 'Tronco di cono',
      campi: [{ k: 'D1', l: 'Diametro grande', v: 400, lettera: 'A' }, { k: 'D2', l: 'Diametro piccolo (0 = a punta)', v: 200, lettera: 'B' },
        { k: 'H', l: 'Altezza', v: 300, lettera: 'C' }, { k: 'spessore', l: 'Spessore', v: 2 },
        { k: 'modo', l: 'Come lo fai', v: 'press', scelte: { press: 'a pieghe, con la piegatrice', rolled: 'calandrato' } },
        { k: 'riferimento', l: 'Le misure sono', v: 'esterno', scelte: RIF },
        { k: 'passo', l: 'Distanza tra le pieghe sul bordo (vuoto = dal raggio)', v: '', altro: true, unit: 'mm' }, ...piega] },
    tramoggia: { titolo: 'Raccordo quadro-tondo', bottone: 'Crea il raccordo', nota: 'Misure finite del pezzo.', nome: 'Raccordo quadro-tondo',
      campi: [{ k: 'A', l: 'Lato lungo della base', v: 600, lettera: 'A' }, { k: 'B', l: 'Lato corto della base', v: 400, lettera: 'B' },
        { k: 'D', l: 'Diametro del tondo', v: 250, lettera: 'C' }, { k: 'H', l: 'Altezza', v: 300, lettera: 'D' },
        { k: 'spessore', l: 'Spessore', v: 2 },
        { k: 'ex', l: 'Tondo spostato di lato (X)', v: 0, altro: true, unit: 'mm' }, { k: 'ey', l: 'Tondo spostato avanti/dietro (Y)', v: 0, altro: true, unit: 'mm' },
        { k: 'rif_base', l: 'Misure della base', v: 'esterno', scelte: RIF, altro: true }, { k: 'rif_tondo', l: 'Misure del tondo', v: 'esterno', scelte: RIF, altro: true },
        { k: 'passo', l: 'Distanza tra le pieghe sul tondo (vuoto = dal raggio)', v: '', altro: true, unit: 'mm' }, ...piega] },
    tramoggia_cassone: { titolo: 'Tramoggia con cassone', bottone: 'Crea la tramoggia', nota: 'Cassone e tramoggia a falde, divisa in pezzi da piegare (più pieghe possibile nel foglio).', nome: 'Tramoggia',
      campi: [{ k: 'A', l: 'Bocca: lato A', v: 1000, lettera: 'A' }, { k: 'B', l: 'Bocca: lato B', v: 1000, lettera: 'B' },
        { k: 'Hc', l: 'Altezza del cassone (0 = solo tramoggia)', v: 700 }, { k: 'a', l: 'Scarico: lato a', v: 250 }, { k: 'b', l: 'Scarico: lato b', v: 250 },
        { k: 'Ht', l: 'Altezza della tramoggia', v: 700 }, { k: 'spessore', l: 'Spessore', v: 3 },
        { k: 'bordo', l: 'Bordo in alto (0 = niente)', v: 40, altro: true, unit: 'mm' },
        { k: 'verso_bordo', l: 'Bordo in alto piegato', v: 'fuori', scelte: { fuori: 'verso fuori', dentro: 'verso dentro' }, altro: true },
        { k: 'flangia', l: 'Flangia allo scarico (0 = niente)', v: 0, altro: true, unit: 'mm' },
        { k: 'verso_flangia', l: 'Flangia allo scarico piegata', v: 'fuori', scelte: { fuori: 'verso fuori', dentro: 'verso dentro' }, altro: true },
        { k: 'angoli_bordo', l: 'Angoli dei bordi', v: 'aperti', scelte: { aperti: 'dritti (scasso all’angolo, più pieghe)', 45: 'a 45° (da saldare)' }, altro: true }, { k: 'smusso', l: 'Angoli smussati (0 = vivi)', v: 0, altro: true, unit: 'mm' },
        { k: 'ex', l: 'Scarico spostato di lato (X)', v: 0, altro: true, unit: 'mm' }, { k: 'ey', l: 'Scarico spostato avanti/dietro (Y)', v: 0, altro: true, unit: 'mm' },
        { k: 'riferimento', l: 'Le misure sono', v: 'esterno', scelte: RIF },
        { k: 'divisione', l: 'Divisione in pezzi', v: 'auto', scelte: { auto: 'automatica (meno saldature)', verticali: 'pieghe sugli spigoli verticali', tramoggia: 'pieghe sugli spigoli della tramoggia', lati: 'un pezzo per lato' }, altro: true },
        { k: 'foglio', l: 'Foglio', v: '1500x3000', altro: true }, ...piega] },
    vuoto: { titolo: 'Telaio da zero', bottone: 'Parti dal primo angolo', nota: 'Parti da un angolo sul pavimento e tiri i tubi con le frecce (Su, Giù, Avanti, Dietro, Destra, Sinistra). Misure fuori tutto.', nome: 'Telaio', campi: [] },
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
    const scelta = daHome ? '' : `<div class="n-kinds">${GRUPPI.map(([g, ks]) => `<div class="n-gruppo"><span>${g}</span><div class="n-scelte">${ks.map(k =>
      `<button data-k="${k}" class="btn${k === kind ? ' on' : ''}">${esc(MODELLI[k].titolo)}</button>`).join('')}</div></div>`).join('')}</div>`;
    const pic = DISEGNI[kind];
    const riassuntoPiega = altri.some(c => c.k === 'raggio') && conPiegatrice ? `Piegatrice: raggio ${esc(virgola(BD.radius) || '?')}, K ${esc(virgola(BD.k) || '?')}` : 'Altre misure';
    return `<h3>${daHome ? esc(m.titolo) : 'Nuovo pezzo'}</h3>${scelta}
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
      <div class="acts"><button class="btn" id="n-no">Annulla</button><button class="btn primary big" id="n-ok">${esc(m.bottone || 'Crea ' + m.titolo.toLowerCase())}</button></div>`;
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
  // 04/11: tre parti come nelle Impostazioni (per ogni lamiera nuova, le regole salvate, salva questa); un blu solo in fondo
  const righe = r.rules.map(x => `<tr><td><b>${esc(x.name)}</b><div class="hint">${esc([x.material, `sp. ${n(x.thickness)}`, `R ${n(x.radius)}`,
    x.method === 'bd90' ? 'BD90 ' + n(x.bd90) : x.method === 'din6935' ? 'DIN 6935' : 'K ' + n(x.k)].filter(Boolean).join(', '))}</div></td>
    <td class="rg-az">${fid ? `<button class="btn" data-rule-apply="${esc(x.name)}">Usa su questa lamiera</button>` : ''}
    <button class="btn danger" data-rule-del="${esc(x.name)}" title="Elimina la regola ${esc(x.name)}">Elimina</button></td></tr>`).join('')
    || '<tr><td class="hint">Ancora nessuna regola. Scrivi i dati di piega nella scheda Lamiera e salvali qui sotto con un nome.</td></tr>';
  modal(`<h3>Regole di piega</h3>
    <p class="hint">I dati della tua piegatrice (spessore, raggio interno, K o deduzione) salvati con un nome: li riusi in ogni progetto con un clic.</p>
    <section class="rg-sez"><h4>Per ogni lamiera nuova</h4>
      <div class="rg-riga"><label>Raggio interno<span class="campo-unita"><input class="field" id="d-r" value="${n(r.default?.radius).replace('–', '')}" placeholder="es. 2"><i>mm</i></span></label>
        <label>Fattore K<input class="field" id="d-k" value="${n(r.default?.k).replace('–', '')}" placeholder="es. 0,33"></label>
        <button class="btn" id="d-save">Salva come predefinito</button></div></section>
    <section class="rg-sez"><h4>Regole salvate</h4><table class="grid rg-tab">${righe}</table></section>
    ${fid ? `<section class="rg-sez"><h4>Salva i dati di questa lamiera</h4>
      <label class="rg-nome">Nome della regola<input class="field" id="r-name" placeholder="es. S235 sp. 2, matrice V16"></label></section>`
    : '<p class="hint">Apri o crea una lamiera per usare o salvare una regola.</p>'}
    <div class="acts"><button class="btn" id="m-no">Chiudi</button>${fid ? '<button class="btn primary" id="r-save">Salva la regola</button>' : ''}</div>`, close => {
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

// un file aperto col doppio clic mentre Radius è già aperto: arriva qui (main.py). Se il lavoro aperto ha modifiche
// non salvate si chiede prima (restano comunque nel salvataggio automatico)
window.__apriDaFuori = percorso => {
  const nome = String(percorso).split(/[\\/]/).pop();
  if (!S?.dirty) { inCoda(() => openProject(percorso)); return; }
  modal(`<h3>Aprire ${esc(nome)}?</h3><p>Il lavoro aperto adesso ha modifiche non salvate. Se apri l’altro, le modifiche restano nel salvataggio automatico.</p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn" id="m-salva">Salva e apri</button><button class="btn primary" id="m-ok">Apri senza salvare</button></div>`, close => {
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => { close(); inCoda(() => openProject(percorso)); };
    $('#m-salva').onclick = () => { close(); inCoda(async () => { if (await apply(await call('save', false), 'Salvato.')) await openProject(percorso); }); };
  }, { stretta: true });
};
async function openProject(percorso) {
  const r = percorso ? await call('open_recent', percorso) : await call('open_dialog');
  if (r.recovery) {
    modal(`<h3>C’è un salvataggio automatico più recente</h3><p>Il file <b>${esc(r.path)}</b> ha un salvataggio automatico fatto dopo l’ultimo
      salvataggio. Probabilmente il programma si è chiuso prima di salvare.</p>
      <div class="acts"><button class="btn" id="r-no">Apri il file salvato</button><button class="btn primary" id="r-ok">Recupera le modifiche</button></div>`,
    close => {
      const vai = rec => { close(); primaVolta = true; clearSelection(); inCoda(async () => { if (await apply(await call('open_path', r.path, rec), rec ? 'Modifiche recuperate.' : null)) { hideHome(); fotoAnteprima(S.path); } }); };
      $('#r-no').onclick = () => vai(false); $('#r-ok').onclick = () => vai(true);
    }, { stretta: true });
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
        <label class="tutta-riga">Nome<input class="field" id="imp-name" value="${esc(r.name)}"></label>
        <label>Materiale<select class="field" id="imp-mat">${r.materiali.map(m => `<option value="${esc(m.code)}"${m.code === mat ? ' selected' : ''}>${esc(m.code)}</option>`).join('')}</select></label>
        <label>Spessore<input class="field" id="imp-sp" value="${virg(r.spessore)}" placeholder="mm"></label>
        ${regole.length ? `<label class="tutta-riga">Regola di piega<select class="field" id="imp-rule"><option value="">— scrivi i dati qui sotto —</option>
          ${regole.map((x, i) => `<option value="${i}">${esc(x.name)}</option>`).join('')}</select></label>` : ''}
        <label>Raggio interno<input class="field" id="imp-r" placeholder="mm" value="${virg(S?.bend_default?.radius)}"></label>
        <label>Metodo<select class="field" id="imp-met"><option value="k">Fattore K</option><option value="din6935">DIN 6935</option><option value="bd90">Deduzione 90°</option></select></label>
        <label id="imp-k-l">Fattore K<input class="field" id="imp-k" placeholder="es. 0,4" value="${virg(S?.bend_default?.k)}"></label>
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
let homeFiltro = 'tutti';
async function showHome(info) {
  info = info || await call('home_info');
  if (!info.ok) return;
  if (SK) exitSketch();
  // 04/11 (A. «Prima riprendi»): in alto, grande, l'ultimo lavoro con «Continua»; a destra gli altri, col filtro e la ricerca
  const tutti = info.recent;
  const ultimo = tutti.find(x => !x.manca) || null;
  const altri = tutti.filter(x => x !== ultimo);
  const conta = { tutti: altri.length, pezzi: altri.filter(x => !x.assembly).length, assiemi: altri.filter(x => x.assembly).length };
  const foto = x => (x.thumb ? `<img src="${x.thumb}" alt="">`
    : `<img class="icona" src="icons/${x.assembly ? 'assieme' : 'box'}.svg" alt="">${anteprimeProvate.has(x.path) ? '' : '<i class="in-arrivo">Preparo l’anteprima…</i>'}`);
  const cartella = x => (x.folder || '').split(/[\\/]/).filter(Boolean).pop() || '';
  // il pulsante blu è uno solo: «Riprendilo» se c'è un lavoro non salvato, se no «Torna al lavoro» se ce n'è uno aperto, se no «Continua»
  const blu = info.unsaved ? 'recupera' : !info.show ? 'torna' : 'continua';
  const aperto = !info.show && ultimo && S?.path && ultimo.path === S.path;      // l'ultimo è quello che hai già aperto
  $('#home-ultimo').innerHTML = ultimo ? `<div class="home-ultimo${ultimo.assembly ? ' asm' : ''}" data-path="${esc(ultimo.path)}" title="${esc(ultimo.path)}">
      <span class="pic">${foto(ultimo)}</span>
      <div class="testo">
        <small>${aperto ? 'Il lavoro aperto' : 'Il tuo ultimo lavoro'}</small>
        <b>${esc(ultimo.name)}</b>
        <span class="dati">${ultimo.assembly ? 'Assieme, ' : ''}salvato ${esc(ultimo.when)}</span>
        <span class="dati">nella cartella ${esc(cartella(ultimo))}</span>
        <span class="home-spazio"></span>
        <button class="btn big${blu === 'continua' ? ' primary' : ''}" id="home-continua">Continua</button>
      </div></div>`
    : `<div class="home-ultimo vuoto"><div class="testo"><b>Qui ritrovi il tuo ultimo lavoro</b>
      <span class="dati">Quando apri o salvi un pezzo, qui c'è la sua foto e «Continua» per riprenderlo. Per cominciare scegli da «Nuovo», qui sotto.</span></div></div>`;
  const disegnaRecenti = () => {
    const q = norm($('#home-cerca').value.trim());
    // cercando, si cerca in tutti (anche l'ultimo); se no la colonna ha gli altri
    const base = q ? tutti : altri;
    const lst = base.filter(x => (homeFiltro === 'tutti' || (homeFiltro === 'assiemi') === !!x.assembly) && (!q || norm(x.name).includes(q)));
    $('#home-recent').innerHTML = lst.map(x => x.manca ? `<div class="home-rec manca" title="${esc(x.path)}">
        <span class="pic">${x.thumb ? `<img src="${x.thumb}" alt="">` : `<img class="icona" src="icons/${x.assembly ? 'assieme' : 'box'}.svg" alt="">`}</span>
        <div class="testo"><b>${esc(x.name)}</b><small>Spostato o cancellato: non è più in ${esc(x.folder)}</small>
          <span class="rec-azioni"><button class="btn piccolo" data-ritrova="${esc(x.path)}">Cerca…</button><button class="btn piccolo" data-forget="${esc(x.path)}">Togli</button></span></div></div>`
      : `<div class="home-rec${x.assembly ? ' asm' : ''}" data-path="${esc(x.path)}" title="${esc(x.path)}" tabindex="0">
        <span class="pic">${foto(x)}</span>
        <div class="testo"><b>${esc(x.name)}</b><small>${x.assembly ? '<span class="tipo">Assieme</span>' : ''}${esc(x.when)}${cartella(x) ? `, ${esc(cartella(x))}` : ''}</small></div>
        <button class="x" data-forget="${esc(x.path)}" title="Togli dai recenti (il file resta)" aria-label="Togli dai recenti">×</button></div>`).join('')
      || `<p class="home-vuoto">${q ? `Nessun lavoro si chiama così. <button class="link" id="home-cerca-via">Mostra tutti</button>`
        : altri.length ? 'Nessun lavoro di questo tipo.' : tutti.length ? 'Gli altri lavori che apri o salvi compaiono qui.' : 'Qui compaiono i lavori che apri o salvi.'}</p>`;
    $('#home').querySelectorAll('.home-rec:not(.manca)').forEach(d => {
      d.onclick = ev => { if (!ev.target.closest('.x')) inCoda(() => openProject(d.dataset.path)); };
      d.onkeydown = ev => { if (ev.key === 'Enter' && ev.target === d) d.click(); };
    });
    if ($('#home-cerca-via')) $('#home-cerca-via').onclick = () => { $('#home-cerca').value = ''; homeFiltro = 'tutti'; showHome(info); };
    $('#home').querySelectorAll('[data-ritrova]').forEach(b => { b.onclick = () => inCoda(async () => {
      const r = await call('recent_ritrova', b.dataset.ritrova);
      if (r.ok) showHome(r); else if (!r.cancelled) toast(r.message, 'err');
    }); });
    $('#home').querySelectorAll('[data-forget]').forEach(b => { b.onclick = () => inCoda(async () => showHome(await call('forget_recent', b.dataset.forget))); });
  };
  $('#home-filtro').innerHTML = [['tutti', 'Tutti'], ['pezzi', 'Pezzi'], ['assiemi', 'Assiemi']]
    .map(([k, t]) => `<button data-filtro="${k}" class="${homeFiltro === k ? 'on' : ''}">${t}<i>${conta[k]}</i></button>`).join('');
  $('#home-filtro').querySelectorAll('button').forEach(b => { b.onclick = () => { homeFiltro = b.dataset.filtro; showHome(info); }; });
  $('#home-cerca').oninput = disegnaRecenti;
  disegnaRecenti();
  $('#home .home-riprendi').classList.toggle('solo', !tutti.length);      // ancora nessun lavoro: niente colonna vuota
  if ($('#home-continua')) $('#home-continua').onclick = () => (aperto ? hideHome() : inCoda(() => openProject(ultimo.path)));
  const fotoUltimo = $('#home-ultimo .home-ultimo .pic');
  if (fotoUltimo) fotoUltimo.onclick = () => $('#home-continua').click();
  $('#home-unsaved').innerHTML = info.unsaved ? `<div class="home-unsaved"><div><b>Hai un lavoro non salvato</b>
      <span>lasciato ${esc(info.unsaved.when)}: riprendilo e salvalo con un nome.</span></div>
      <button class="btn primary" id="home-recover">Riprendilo</button></div>` : '';
  $('#home-close').hidden = !!info.show;              // all'avvio non c'è un lavoro a cui tornare
  $('#home-close').classList.toggle('primary', blu === 'torna');
  $('#home').hidden = false;
  document.body.classList.add('at-home');
  // le anteprime che mancano arrivano una alla volta, al loro posto (anche nella foto grande dell'ultimo)
  setTimeout(() => anteprimeMancanti(tutti, x => {
    document.querySelectorAll('#home .home-rec[data-path], #home .home-ultimo[data-path]').forEach(e => {
      if (e.dataset.path !== x.path) return;
      const pic = e.querySelector('.pic');
      if (pic) pic.innerHTML = `<img src="${x.thumb}" alt="">`;
    });
  }), 1200);                                          // dopo un attimo: un clic svelto su «Lamiera» passa prima
  // Cono e Tubi: sopra i recenti si apre la scelta del tipo, con le foto; la lamiera si apre subito
  const scegli = cat => {
    $('#home').querySelectorAll('[data-cat]').forEach(b => b.classList.toggle('on', b.dataset.cat === cat));
    $('#home').querySelectorAll('.home-tipi').forEach(s => { s.hidden = s.dataset.of !== cat; });
    const aperta = cat && $(`#home .home-tipi[data-of="${cat}"]`);
    if (aperta) aperta.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };
  $('#home').querySelectorAll('[data-cat]').forEach(b => { b.onclick = () => scegli(b.classList.contains('on') ? null : b.dataset.cat); });
  $('#home').querySelectorAll('[data-chiudi-tipi]').forEach(b => { b.onclick = () => scegli(null); });
  scegli(null);
  renderModelli();
  $('#home').querySelectorAll('[data-new]').forEach(b => {
    b.onclick = () => (b.dataset.new === 'assieme' ? newAssemblyDialog() : b.dataset.new === 'step' ? stepDialog()
      : b.dataset.new === 'lamiera' ? nuovaLamiera() : b.dataset.new === 'zero' ? nuovoDaZero() : newDialog(b.dataset.new, true));
  });
  $('#home').querySelectorAll('[data-altro="importa"]').forEach(b => { b.onclick = () => inCoda(importDialog); });
  $('#home-open').onclick = () => inCoda(() => openProject());
  $('#home-close').onclick = hideHome;
  if ($('#home-recover')) $('#home-recover').onclick = () => inCoda(async () => {
    primaVolta = true; clearSelection();
    if (await apply(await call('recover_unsaved'), 'Lavoro recuperato: salvalo con un nome.')) hideHome();
  });
}
// la lamiera nuova si apre subito, senza finestra: 500 × 300 sp. 2 coi dati della piegatrice; le misure si cambiano a sinistra
// 28/10: i modelli pronti. Si sceglie, si scrivono 4 misure guardando l'anteprima, «Crea»: il pezzo vero con le pieghe
const MODELLI = [
  { k: 'staffa', n: 'Staffa a L', d: 'base + parete', c: { larghezza: 300, profondita: 200, altezza: 120, spessore: 3 }, et: { altezza: 'Altezza parete' } },
  { k: 'profilo_u', n: 'Profilo a U', d: 'due ali piegate', c: { larghezza: 1000, profondita: 120, altezza: 50, spessore: 2 }, et: { larghezza: 'Lunghezza', profondita: 'Larghezza fondo', altezza: 'Altezza ali' } },
  { k: 'scatola', n: 'Scatola', d: '4 pareti piegate', c: { larghezza: 400, profondita: 300, altezza: 150, spessore: 1.5 } },
  { k: 'coperchio', n: 'Coperchio', d: 'bordo piegato in giù', c: { larghezza: 600, profondita: 400, altezza: 25, spessore: 1.5 }, et: { altezza: 'Bordo' } },
  { k: 'tramoggia_cassone', n: 'Tramoggia con cassone', d: 'in pezzi da piegare', img: 'tramoggia.png' },
  { k: 'tramoggia', n: 'Raccordo quadro-tondo', d: 'anche fuori centro', img: 'raccordo.png' },
  { k: 'cono', n: 'Cono', d: 'calandrato o a pieghe', img: 'cono.png' },
  { k: 'telaio', n: 'Telaio in tubo', d: 'gambe e traversi', img: 'telaio.png' },
];
const ETICHETTE_MOD = { larghezza: 'Larghezza', profondita: 'Profondità', altezza: 'Altezza', spessore: 'Spessore' };
function disegnoModello(k, c) {                       // l'anteprima in isometrica, che segue le misure
  const C30 = Math.cos(Math.PI / 6), punti = [];
  const P = (x, y, z) => { const p = [(x - y) * C30, (x + y) * 0.5 - z]; punti.push(p); return p; };
  const poly = (pts, fill) => `<polygon points="${pts.map(p => P(...p).map(v => v.toFixed(1)).join(',')).join(' ')}" fill="${fill}" stroke="#20262D" stroke-width="${0.004 * Math.max(c.larghezza, c.profondita)}" stroke-linejoin="round"/>`;
  const L = +c.larghezza || 1, Pp = +c.profondita || 1, Hh = +c.altezza || 1, t = Math.max(+c.spessore || 1, 0.006 * Math.max(L, Pp));
  const box = (x0, y0, z0, x1, y1, z1, alto = '#C7CFD8') => poly([[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], alto)
    + poly([[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], '#8A96A3') + poly([[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], '#6E7A87');
  let s = '';
  if (k === 'staffa') s = box(0, 0, 0, L, Pp, t) + box(0, 0, t, L, t, Hh, '#DDE3E9');
  else if (k === 'profilo_u') s = box(0, 0, t, L, t, Hh, '#DDE3E9') + box(0, 0, 0, L, Pp, t) + box(0, Pp - t, t, L, Pp, Hh, '#DDE3E9');
  else if (k === 'scatola') s = box(0, 0, 0, L, Pp, t) + box(0, 0, t, L, t, Hh, '#DDE3E9') + box(0, t, t, t, Pp, Hh, '#B8C2CC') + box(L - t, t, t, L, Pp, Hh) + box(t, Pp - t, t, L - t, Pp, Hh);
  else if (k === 'coperchio') s = box(0, Pp - t, 0, L, Pp, Hh) + box(L - t, 0, 0, L, Pp - t, Hh) + box(0, 0, Hh - t, L, Pp, Hh);
  const xs = punti.map(p => p[0]), ys = punti.map(p => p[1]);
  const x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(...xs) - x0, h = Math.max(...ys) - y0, m = Math.max(w, h) * 0.08;
  return `<svg viewBox="${x0 - m} ${y0 - m} ${w + 2 * m} ${h + 2 * m}" preserveAspectRatio="xMidYMid meet">${s}</svg>`;
}
function renderModelli() {
  const g = document.getElementById('home-modelli');
  if (!g || g.childElementCount) return;
  g.innerHTML = MODELLI.map(m => `<button class="home-mod" data-mod="${m.k}"><span class="pic">${m.img ? `<img src="img/modelli/${m.img}" alt="">` : disegnoModello(m.k, m.c)}</span>
    <b>${esc(m.n)}</b><small>${esc(m.d)}</small></button>`).join('');
  g.onclick = e => { const b = e.target.closest('[data-mod]'); if (!b) return; const m = MODELLI.find(x => x.k === b.dataset.mod);
    if (m.img) newDialog(m.k, true); else modelloDialog(m); };
}
function modelloDialog(m) {
  const c = { ...m.c };
  modal(`<h3>${esc(m.n)}</h3>
    <div class="mod-corpo"><div class="mod-ant" id="mod-ant">${disegnoModello(m.k, c)}</div>
      <div class="mod-campi">${Object.keys(c).map(k => `<label class="campo-mod">${esc((m.et || {})[k] || ETICHETTE_MOD[k])}<span class="inp"><input class="field" data-k="${k}" value="${String(c[k]).replace('.', ',')}"><i>mm</i></span></label>`).join('')}
      <div class="mod-piega"><b>Piegatrice</b>
        <label class="campo-mod">Raggio interno<span class="inp"><input class="field" id="mod-r" value="${esc(virgola(S?.bend_default?.radius ?? ''))}" placeholder="es. 2"><i>mm</i></span></label>
        <label class="campo-mod">K-factor<span class="inp"><input class="field" id="mod-k" value="${esc(virgola(S?.bend_default?.k ?? ''))}" placeholder="es. 0,33"><i></i></span></label>
        ${S?.bend_default?.radius != null ? '<p class="hint">Dalle tue regole di piega.</p>' : '<p class="hint attenzione">Scrivili tu: sono dati della tua piegatrice, Radius non li inventa. Li ricorda in «Regole piega».</p>'}</div>
      <p class="hint">Le misure sono esterne (fuori tutto). Dopo si cambiano a sinistra, e le pieghe cliccandole.</p></div></div>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary big" id="m-ok">Crea il pezzo</button></div>`, close => {
    const leggi = () => { document.querySelectorAll('.mod-campi input').forEach(x => { const v = parseFloat(x.value.replace(',', '.')); if (v > 0) c[x.dataset.k] = v; }); };
    document.querySelectorAll('.mod-campi input').forEach(x => { x.oninput = () => { leggi(); $('#mod-ant').innerHTML = disegnoModello(m.k, c); }; });
    $('#m-no').onclick = close;
    $('#m-ok').onclick = () => {
      leggi();
      const raggio = $('#mod-r').value.trim(), k = $('#mod-k').value.trim();
      if (!raggio || !k) { toast('Scrivi raggio interno e K della tua piegatrice: senza, le pieghe non si possono fare.', 'err'); (raggio ? $('#mod-k') : $('#mod-r')).focus(); return; }
      close();
      primaVolta = true; clearSelection(); if (SK) exitSketch();
      inCoda(async () => { if (await apply(await call('crea_da_modello', m.k, { ...c, nome: m.n, raggio, k }))) hideHome(); });
    };
  });
  $('#modal-box').classList.add('wide');
}
function nuovaLamiera() {
  primaVolta = true; sel = null; clearSelection();
  if (SK) exitSketch();
  inCoda(async () => {
    if (!(await apply(await call('new_project', 'lamiera', { name: 'Lamiera', larghezza: 500, profondita: 300, spessore: 2 })))) return;
    hideHome();
    toast('Lamiera 500 × 300 sp. 2: cambia le misure a sinistra, poi clicca un bordo per piegarlo.');
  });
}
// 02/11 («crea una sezione da dove posso partire da 0»): dalla pagina iniziale dritti nello sketch vuoto
function nuovoDaZero() {
  primaVolta = true; sel = null; clearSelection();
  if (SK) exitSketch();
  inCoda(async () => {
    if (!(await apply(await call('new_project', 'zero', { name: 'Pezzo' })))) return;
    hideHome();
    await enterSketch('S1');
    toast('Disegna la sagoma. Chiusa: in alto a destra «Crea lamiera» o «Crea piastra». Aperta (un collare, un omega): «Estrudi in lamiera».');
  });
}
// il menu File → Apri recenti: gli ultimi lavori, letti quando il menu si apre
async function menuRecenti() {
  const r = await call('home_info');
  const box = $('#m-recenti');
  if (!r.ok || !box) return;
  box.innerHTML = r.recent.slice(0, 10).map(x => `<button data-recente="${esc(x.path)}">${esc(x.name)}<small>${x.assembly ? 'Assieme, ' : ''}${esc(x.when)}</small></button>`).join('')
    || '<div class="vuoto">Nessun lavoro recente</div>';
  box.querySelectorAll('[data-recente]').forEach(b => { b.onclick = () => { b.closest('.menu-item')?.classList.remove('open'); inCoda(() => openProject(b.dataset.recente)); }; });
}
function hideHome() {
  $('#home').hidden = true;
  document.body.classList.remove('at-home');
}

// l'anteprima del lavoro per la pagina iniziale (23/10, polish): una foto da catalogo, sempre uguale qualunque cosa
// ci sia a video — isometrica inquadrata sul pezzo, luce da studio e ombra, sfondo trasparente, senza quote,
// selezioni né disegno — poi la vista torna com'era
function scattaFoto() {
  const box = new THREE.Box3();
  model.traverse(o => { if (o.isMesh && o.visible && o.geometry) box.expandByObject(o); });
  if (box.isEmpty()) return null;
  const c = box.getCenter(new THREE.Vector3()), r = box.getBoundingSphere(new THREE.Sphere()).radius || 100;
  const cam = camera.clone();
  cam.clearViewOffset();
  const dir = new THREE.Vector3(1, -1.25, 0.95).normalize();
  cam.position.copy(c).addScaledVector(dir, r / Math.sin(THREE.MathUtils.degToRad(cam.fov) / 2) * 1.05);
  cam.up.set(0, 0, 1); cam.lookAt(c); cam.near = r * 0.05; cam.far = r * 40; cam.updateProjectionMatrix();
  const nascosti = [dimLines, overlay, flatGroup, workGroup].filter(g => g && g.visible);
  nascosti.forEach(g => { g.visible = false; });
  const modelPrima = model.visible, suoloPrima = suolo.visible;
  model.visible = true;
  aggiornaSuolo();
  suolo.visible = true;
  renderer.render(scene, cam);
  const W = canvas.width, H = canvas.height;
  let x0 = W, y0 = H, x1 = 0, y1 = 0;
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
    const v = new THREE.Vector3(x, y, z).project(cam);
    const px = (v.x + 1) / 2 * W, py = (1 - v.y) / 2 * H;
    x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
  }
  const m = 0.06 * Math.max(x1 - x0, y1 - y0);
  x0 = Math.max(0, x0 - m); y0 = Math.max(0, y0 - m); x1 = Math.min(W, x1 + m); y1 = Math.min(H, y1 + m);
  let url = null;
  if (x1 - x0 >= 4 && y1 - y0 >= 4) {
    const out = document.createElement('canvas');
    out.width = 480; out.height = 360;
    const k = Math.min(out.width / (x1 - x0), out.height / (y1 - y0));
    const w = (x1 - x0) * k, h = (y1 - y0) * k;
    const g2 = out.getContext('2d');
    g2.imageSmoothingQuality = 'high';
    g2.drawImage(canvas, x0, y0, x1 - x0, y1 - y0, (out.width - w) / 2, (out.height - h) / 2, w, h);
    url = out.toDataURL('image/png');
  }
  nascosti.forEach(g => { g.visible = true; });
  model.visible = modelPrima;
  suolo.visible = suoloPrima;
  return url;
}
async function fotoAnteprima(percorso) {
  try {
    if (!percorso || !objs.size || SK) return;
    const selPrima = sel;
    sel = null; hover = null; paint();
    const url = scattaFoto();
    sel = selPrima; paint();
    aggiornaSuolo();
    ridisegna();
    if (url) await call('save_thumbnail', percorso, url);
  } catch (e) { /* l'anteprima è una comodità: se non riesce, pazienza */ }
}
// 04/11: i lavori recenti senza anteprima (salvati da un'altra versione, o mai aperti da qui) se la fanno fare adesso,
// uno alla volta mentre la pagina iniziale è aperta: il motore dà i triangoli, qui lo stesso scatto da catalogo.
// Il lavoro aperto non si tocca: si nasconde per un attimo dietro la pagina iniziale e torna com'era.
const anteprimeProvate = new Set();
let anteprimeInCorso = false;
async function anteprimeMancanti(lista, fatta) {
  if (anteprimeInCorso) return;
  anteprimeInCorso = true;
  try {
    for (const x of lista) {
      if (x.thumb || x.manca || anteprimeProvate.has(x.path)) continue;
      if ($('#home').hidden || SK) break;
      anteprimeProvate.add(x.path);
      let r;
      try { r = await chiamaMuto('anteprima_maglia', x.path); } catch { continue; }
      if (!r?.ok || $('#home').hidden || SK) continue;
      const gruppo = new THREE.Group(), geo = [], mat = [];
      for (const d of r.objects) {
        const g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.Float32BufferAttribute(d.positions, 3)); g.setIndex(d.indices); g.computeVertexNormals();
        const ma = new THREE.MeshStandardMaterial({ color: new THREE.Color(d.look?.color || 0xCBD1D8), metalness: d.look?.metal ?? 0.15,
          roughness: d.look?.rough ?? 0.55, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
        ma.envMapIntensity = 0.45 + 0.8 * ma.metalness;
        const lastra = vetro(ma, d.look);
        const seg = [];
        for (const e of d.edges) for (let i = 0; i + 5 < e.length; i += 3) seg.push(e[i], e[i + 1], e[i + 2], e[i + 3], e[i + 4], e[i + 5]);
        const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
        const mesh = new THREE.Mesh(g, ma), linee = new THREE.LineSegments(lg, lastra ? EDGE_VETRO : EDGE);
        mesh.castShadow = !lastra;
        if (d.matrix) for (const o of [mesh, linee]) { o.matrixAutoUpdate = false; o.matrix.set(...d.matrix); }
        gruppo.add(mesh, linee); geo.push(g, lg); mat.push(ma);
      }
      // il lavoro aperto si spegne, al suo posto il recente; scatto; tutto torna com'era (niente attese in mezzo)
      const spenti = [];
      model.traverse(o => { if (o !== model && o.visible) { spenti.push(o); o.visible = false; } });
      model.add(gruppo);
      gruppo.updateMatrixWorld(true);
      let url = null;
      try { url = scattaFoto(); } finally {
        model.remove(gruppo);
        spenti.forEach(o => { o.visible = true; });
        geo.forEach(g => g.dispose()); mat.forEach(m => m.dispose());
        aggiornaSuolo(); ridisegna();
      }
      if (!url) continue;
      x.thumb = url;
      fatta?.(x);
      try { await chiamaMuto('save_thumbnail', x.path, url); } catch { /* resta per questa volta */ }
    }
  } finally {
    anteprimeInCorso = false;
    document.querySelectorAll('#home-recent .in-arrivo').forEach(e => e.remove());    // quelle che non sono venute
  }
}

const CMDS = [
  { id: 'new', label: 'Nuovo pezzo (lamiera, cono, tubi)…', keys: 'Ctrl+N', run: () => inCoda(() => showHome()) },
  { id: 'new_assembly', label: 'Nuovo assieme…', keys: 'Ctrl+Maiusc+N', run: () => newAssemblyDialog() },
  { id: 'impostazioni', label: 'Impostazioni…', run: () => impostazioniDialog() },
  { id: 'home', label: 'Pagina iniziale', run: () => inCoda(() => showHome()) },
  { id: 'new_asm', label: 'Nuovo assieme…', run: newAssemblyDialog },
  { id: 'drawings', label: 'Tavole con cartiglio (PDF e disegni)…', run: () => inCoda(drawingsDialog) },
  { id: 'prepara', label: 'Prepara per il laser / l’officina (DXF, pieghe, disegni, STEP)…', run: () => inCoda(() => preparaDialog()) },
  { id: 'asm_insert', label: 'Assieme: inserisci pezzo…', run: () => inCoda(async () => { const r = await call('asm_insert_dialog'); if (await apply(r) && r.select) await select(r.select); }) },
  { id: 'asm_esploso', label: 'Assieme: vista esplosa (apri / chiudi)', run: () => {
    if (S?.mode !== 'assembly') { toast('La vista esplosa è degli assiemi.', 'err'); return; }
    const da = ESPLOSO, a = ESPLOSO > 0 ? 0 : 0.8, t0 = performance.now();
    const passo = t => { const k = Math.min(1, (t - t0) / 450); esplodi(da + (a - da) * (1 - (1 - k) ** 3)); if (k < 1) requestAnimationFrame(passo); };
    requestAnimationFrame(passo);
    document.querySelector('#ribbon [data-cmd="asm_esploso"]')?.classList.toggle('on', a > 0);
    esplosoPannello(a > 0);
  } },
  { id: 'asm_interf', label: 'Assieme: controlla interferenze', run: () => inCoda(async () => {
    const r = await call('asm_interferences');
    if (!r.ok) { toast(r.message, 'err'); return; }
    interfPulisci();
    if (!r.interferences.length) { toast(r.message); return; }
    clearSelection();                               // il rosso si vede meglio senza i pezzi scelti (e la barretta) sopra
    interfMostra(r.interferences);
    toast(`${r.interferences.length === 1 ? 'Un’interferenza' : r.interferences.length + ' interferenze'}: in rosso il pezzo che entra nell’altro, l’elenco a destra.`, 'err');
  }) },
  { id: 'asm_back', label: 'Torna all’assieme', run: tornaAllAssieme },
  { id: 'open', label: 'Apri progetto…', keys: 'Ctrl+O', run: () => inCoda(openProject) },
  { id: 'import_dxf', label: 'Importa sviluppo DXF / DWG…', run: () => inCoda(importDialog) },
  { id: 'import_step', label: 'Apri STEP di una lamiera (fa lo sviluppo)…', run: () => stepDialog() },
  { id: 'save', label: 'Salva', keys: 'Ctrl+S', run: () => salvaPezzo(false) },
  { id: 'specchiato', label: 'Crea la versione specchiata (destra / sinistra)', run: () => {
    if (!S?.sheet?.data || S?.mode === 'assembly') { toast('Lo specchio si fa su un pezzo di lamiera aperto.', 'err'); return; }
    modal(`<h3>Versione specchiata</h3><p class="hint">Il pezzo rovesciato come in uno specchio (la staffa destra dalla sinistra), con il suo sviluppo per il laser.
      Si salva accanto a questo, col nome «… specchiato», e si apre. Le pieghe vengono dal 3D: per cambiarle si cambia l’originale e si rifà lo specchio.</p>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Crea lo specchiato</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => { close(); inCoda(async () => { const r = await call('crea_specchiato'); if (await apply(r, r.message)) await loadScene(); }); };
    }, { stretta: true });
  } },
  { id: 'saveas', label: 'Salva con nome…', keys: 'Ctrl+Maiusc+S', run: () => salvaPezzo(true) },
  { id: 'export_step', label: 'Esporta STEP…', run: () => inCoda(() => esportaFile('step')) },
  { id: 'asm_viteria', label: 'Viteria: viti, dadi, rondelle, rivetti (norme ISO)…', run: () => inCoda(viteriaDialog) },
  { id: 'export_bom', label: 'Distinta materiali in Excel (con gli acquisti)…', run: () => inCoda(() => esportaFile('bom')) },
  { id: 'export_dxf', label: 'Esporta DXF di taglio…', run: () => inCoda(() => esportaFile('dxf')) },
  { id: 'undo', label: 'Annulla', keys: 'Ctrl+Z', run: () => S?.undo[0] && inCoda(async () => apply(await call('undo'))) },
  { id: 'redo', label: 'Ripeti', keys: 'Ctrl+Y', run: () => S?.redo[0] && inCoda(async () => apply(await call('redo'))) },
  { id: 'view_iso', label: 'Vista isometrica', keys: '0', run: () => goTo(vistaIso()) },
  { id: 'view_top', label: 'Vista dall’alto', keys: '7', run: () => goTo(VISTE.view_top) },
  { id: 'view_front', label: 'Vista di fronte', keys: '1', run: () => goTo(VISTE.view_front) },
  { id: 'view_right', label: 'Vista da destra', keys: '3', run: () => goTo(VISTE.view_right) },
  { id: 'fit', label: 'Adatta alla finestra', keys: 'F', run: () => (SK ? fitSketch() : goTo(null, true)) },
  { id: 'toggle_dims', label: 'Mostra/nascondi quote', keys: 'Q', run: () => { showDims = !showDims; buildDims(); } },
  { id: 'toggle_theme', label: 'Tema scuro / chiaro', run: () => {
    const scuro = !document.body.classList.contains('dark');
    applyTheme(scuro); call('set_impostazioni', { tema: scuro ? 'scuro' : 'chiaro' });
  } },
  { id: 'unfold', label: 'Spiega / ripiega la lamiera', keys: 'U', run: () => toggleFlat() },
  { id: 'misura', label: 'Quota: misura tra due punti, diametro di un foro', keys: 'M', run: () => (MIS && !MIS.angolo ? misStop() : misStart()) },
  { id: 'misura_angolo', label: 'Angolo: misura l’angolo tra due lati (tre clic)', run: () => (MIS?.angolo ? misStop() : misStart(true)) },
  { id: 'misura_via', label: 'Togli tutte le quote misurate', run: () => misTogliTutte() },
  { id: 'view_back', label: 'Vista da dietro', run: () => goTo(VISTE.view_back) },
  { id: 'view_left', label: 'Vista da sinistra', run: () => goTo(VISTE.view_left) },
  { id: 'view_bottom', label: 'Vista da sotto', run: () => goTo(VISTE.view_bottom) },
  { id: 'new_sheet', label: 'Nuova lamiera', run: () => nuovaLamiera() },
  { id: 'new_zero', label: 'Nuovo da zero (disegna)…', run: () => newDialog('zero') },
  { id: 'new_frame', label: 'Nuovo telaio / tavolo…', run: () => newDialog('telaio') },
  { id: 'new_free', label: 'Nuova struttura libera…', run: () => newDialog('vuoto') },
  { id: 'flange_help', label: 'Piega i bordi', run: () => pieghePiuBordi() },
  { id: 'contour_help', label: 'Lamiera a contorno', run: () => toast(S?.sheet?.data
    ? 'Lamiera a contorno: clicca la faccia di estremità (testata) da cui partire, «Disegna su questa faccia», disegna la sezione con la Linea partendo dallo spigolo del bordo (arancio), poi «Pieghe e forme ▾» → «Lamiera a contorno».'
    : 'Prima serve una lamiera: Nuova lamiera, oppure Disegna e poi Crea lamiera.', S?.sheet?.data ? '' : 'err') },
  { id: 'face_help', label: 'Disegna su una faccia', run: () => toast('Clicca una faccia piana del pezzo, poi «Disegna qui» nella barretta che compare.') },
  // 04/11 (percorso C): «testo», «scritta», «marca» nella ricerca portano qui (la scritta si fa disegnando sulla faccia)
  { id: 'scritta', label: 'Scritta sul pezzo, tagliata o marcata (testo)…', run: () => toast('Clicca la faccia dove va la scritta, poi «Disegna qui» e il comando «Testo». Tagliata: «Togli materiale»; marcata: «Marca col laser».') },
  { id: 'member_help', label: 'Nuova asta', run: () => toast(nodes.length ? 'Clicca un nodo (pallino) del telaio: nel pannello scegli direzione e lunghezza della nuova asta.' : 'Prima serve una struttura: Telaio / tavolo o Struttura libera.', nodes.length ? '' : 'err') },
  { id: 'export_bendtable', label: 'Esporta la tabella pieghe…', run: () => inCoda(() => esportaFile('bendtable')) },
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
  if (mi && ev.target.closest('.menu-item > button')) {
    mi.classList.toggle('open');
    if (mi.classList.contains('open') && mi.querySelector('#m-recenti')) menuRecenti();
    return;
  }
  if (ev.target.closest('.sub-btn')) return;              // i sottomenu si aprono passandoci sopra
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
  // 04/11: cercando si trovano anche tutti i comandi della barra, quelli dentro i menu dei gruppi compresi
  if (nq) {
    const visti = new Set(palItems.map(it => norm(it.label)));
    const ora = document.querySelector('#ribbon .rbody:not([hidden])');     // prima i comandi della barra che si vede
    const tutti = [...document.querySelectorAll('#ribbon .rb, #ribbon .rmenu .drop button')];
    for (const b of [...tutti.filter(x => ora?.contains(x)), ...tutti.filter(x => !ora?.contains(x))]) {
      if (b.dataset.cmd && CMDS.some(c => c.id === b.dataset.cmd)) continue;
      const rbody = b.closest('.rbody'), tab = rbody && document.querySelector(`.rtabs [data-rtab="${rbody.dataset.rbody}"]`);
      const nascosto = b.closest('[hidden]');
      if (!tab || tab.hidden || b.disabled || (nascosto && nascosto !== rbody)) continue;
      const nome = (b.querySelector('span')?.textContent || b.textContent).trim().replace(/\s*▾$/, '');
      if (!nome || !norm(nome).includes(nq) || visti.has(norm(nome))) continue;
      visti.add(norm(nome));
      palItems.push({ label: nome, d: tab.textContent.trim(), run: () => { if (rbody.hidden) tab.click(); b.click(); } });
    }
  }
  palOn = 0;
  drawPalette();
}
function drawPalette() {
  $('#pal-list').innerHTML = palItems.map((it, i) => `<li data-i="${i}" class="${i === palOn ? 'on' : ''}">${esc(it.label)}<span class="d">${esc(it.d)}</span></li>`).join('')
    || '<li class="spento">Nessun comando con questo nome.</li>';
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
    const mappa = { z: ev.shiftKey ? 'redo' : 'undo', y: 'redo', s: ev.shiftKey ? 'saveas' : 'save', o: 'open', n: ev.shiftKey ? 'new_assembly' : 'new', k: 'palette' };
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
    // tubi (notte 03/11): Esc chiude il comando in corso, come dice la barra in basso
    if (TRAV) { anteprimaVia(); finisciTraverso(); return; }
    if (DIV && $('#dv-no')) { $('#dv-no').click(); return; }
    if (DIVSCEGLI) { DIVSCEGLI = false; passoTubi(null); return; }
    if (PUNTO) { puntoVia(); if ($('#p-punto-riga')) $('#p-punto-riga').hidden = true; return; }
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
const skOver = new THREE.Group();      // sopra lo sketch: solo gli elementi selezionati o sotto il mouse
scene.add(skGroup, skGrid, skRubber, skOver);
let skBase = null;                     // per quale vista dello sketch è fatto il disegno di base (si rifà solo se cambia)
// 04/11: il disegno nel suo colore di modalità (verde acqua), la selezione gialla come nel 3D
const SK_LINE = new THREE.LineBasicMaterial({ color: 0x00A88F });
const SK_SEL = new THREE.LineBasicMaterial({ color: 0xFFB21A });
const SK_SCIOLTA = new THREE.LineBasicMaterial({ color: 0xE5484D });   // non chiude nessun contorno: non conta
const SK_HOV = new THREE.LineBasicMaterial({ color: 0x6E9BFF });
const SK_RUB = new THREE.LineDashedMaterial({ color: 0x00A88F, dashSize: 6, gapSize: 4 });
const SK_ANTEPRIMA = new THREE.LineDashedMaterial({ color: 0xFFB21A, dashSize: 5, gapSize: 3 });   // dove andrà la copia
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
const SK_TRACK = new THREE.LineDashedMaterial({ color: 0x4CC3AE, dashSize: 3, gapSize: 3 });       // puntamento
const SK_PTS = new THREE.PointsMaterial({ color: 0x1C2228, size: 6, sizeAttenuation: false });
// tema chiaro / scuro: i colori del disegno che devono staccare dallo sfondo
const COLORI_TEMA = {
  chiaro: [[SK_LINE, 0x00A88F], [SK_RUB, 0x00A88F], [SK_GRID1, 0xDDE2E8], [SK_GRID2, 0xC2CAD3], [SK_PTS, 0x15202B], [DIM_MAT, 0x3A4A5C], [ING_MAT, 0x3A4A5C], [FLAT_EDGE, 0x2B3138]],
  scuro: [[SK_LINE, 0x2CCCB0], [SK_RUB, 0x2CCCB0], [SK_GRID1, 0x262C33], [SK_GRID2, 0x353D46], [SK_PTS, 0xE1E6EB], [DIM_MAT, 0x6FA8E8], [ING_MAT, 0x6FA8E8], [FLAT_EDGE, 0xC9D2DB]],
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
const SK_CONSTR_SEL = new THREE.LineDashedMaterial({ color: 0xFFB21A, dashSize: 8, gapSize: 5 });
let lineeSpesse = true;
const SPESSORE = new Map();          // materiale sottile -> pixel
const GROSSI = new Map();            // materiale sottile -> materiale spesso (stesso colore, aggiornato ogni volta)
SPESSORE.set(SK_CONSTR, 1.8); SPESSORE.set(SK_CONSTR_SEL, 2.2); SPESSORE.set(SK_REF, 2.2); SPESSORE.set(SK_XRAY, 1.6);
SPESSORE.set(SK_TESTO, 2); SPESSORE.set(SK_SEL, 3.2); SPESSORE.set(SK_HOV, 3.2);
// 04/11: la barra «prossimo passo» è una riga sola: il comando, cosa fare adesso (corto), i tasti scritti
const AIUTI = {
  line: 'Linea: clic sui punti, o scrivi la lunghezza (100 o 100<30) · Invio conferma · Esc finisce',
  rect: 'Rettangolo: clic su un angolo e sull’angolo opposto, o scrivi 100x50 · Invio conferma · Esc annulla',
  circle: 'Cerchio: clic sul centro e sul bordo, o scrivi il diametro · Invio conferma · Esc annulla',
  slot: 'Asola: clic sui due centri, poi la larghezza · Invio conferma · Esc annulla',
  arc3: 'Arco: clic sulla partenza, su un punto dove passa, poi sull’arrivo · col raggio scritto: «Arco col raggio», accanto · Esc annulla',
  arcr: 'Arco col raggio: parte dalla fine della linea, scrivi il raggio · Invio conferma · Esc finisce',
  polygon: 'Poligono: scrivi quanti lati, poi clic sul centro e su un vertice · Esc annulla',
  fillet: 'Raccordo: clic sullo spigolo (o sulle due linee), poi scrivi il raggio · Invio conferma · Esc finisce',
  chamfer: 'Smusso: clic sullo spigolo (o sulle due linee), poi scrivi la misura · Invio conferma · Esc finisce',
  select: 'Seleziona: clic su linee e cerchi, poi un comando · Maiusc aggiunge · doppio clic il contorno · Canc toglie',
  dim: 'Quota: clic su una linea, un cerchio, o due punti · Esc finisce',
  trim: 'Accorcia: clic sul pezzo di linea da togliere (diventa rosso) · Esc finisce',
  extend: 'Allunga: clic vicino alla fine della linea da allungare · Esc finisce',
  text: 'Testo: clic dove va la scritta (sul centro del foro per centrarla) · doppio clic con Seleziona la cambia · Esc finisce',
};
const AIUTI_VISTA = ' · destro sposta · rotella zoom';

const v3 = a => new THREE.Vector3(...a);
// gli assi dello sketch come vettori, fatti una volta per disegno (03/11: rifatti per ogni punto, migliaia di volte a
// ogni movimento del mouse mentre si cercano gli agganci); stessi numeri di prima
let _skAssi = null;
function skAssi() {
  const v = SK.v;
  if (!_skAssi || _skAssi.v !== v) _skAssi = { v, o: v3(v.origin), x: v3(v.x_dir), y: v3(v.y_dir) };
  return _skAssi;
}
function skToWorld(xy) {
  const a = skAssi();
  return a.o.clone().addScaledVector(a.x, xy[0]).addScaledVector(a.y, xy[1]);
}
function skToLocal(p) {
  const v = SK.v, d = p.clone().sub(v3(v.origin));
  return [d.dot(v3(v.x_dir)), d.dot(v3(v.y_dir))];
}
function skScreen(xy, w = view.clientWidth, h = view.clientHeight) {    // w, h: la misura della vista, se già letta
  const p = skToWorld(xy).project(camera);
  return [(p.x + 1) / 2 * w, (1 - p.y) / 2 * h];
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
  SK = { sid, v: r.sketch, tool: 'line', pts: [], cursor: null, sel: new Set(), buf: '', constr: false, pick: null, dimPick: [], ghost: !!r.sketch.on_tube, grid: aggancioGriglia };   // sul tubo: la struttura si vede in trasparenza
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
  // 03/11: la riga delle schede (Disegno / Lamiera) compare SUBITO, non al primo cerchio: prima la vista si
  // abbassava di 22 px dopo il primo foro e chi cliccava dove aveva visto metteva i fori a 280/180 invece di 275/175
  ribbonTabs();
  resize();                                   // la vista è appena cresciuta (pannello in basso chiuso)
  $('#sk-foot').hidden = false;
  drawSketch();
  const pts = SK.v.points.filter(p => p.id !== 'O' || !(faccia || sviluppo)).map(p => p.xyz);
  const box = new THREE.Box3();
  if (pts.length > 1) pts.forEach(p => box.expandByPoint(v3(p)));
  else if (!faccia && !sviluppo) { box.expandByPoint(skToWorld([-50, -50])); box.expandByPoint(skToWorld([550, 350])); }
  if (SK.v.on_tube) {
    // sul tubo: la faccia è lunga e stretta (2 m × 40): si parte inquadrando la testa, dove partono le misure
    const xy = SK.v.points.filter(p => p.id !== 'O').map(p => p.xy);
    const y0 = Math.min(...xy.map(q => q[1])), y1 = Math.max(...xy.map(q => q[1])), lung = Math.max(...xy.map(q => q[0]));
    const x1 = Math.min(lung + 10, Math.max(250, 8 * (y1 - y0)));
    box.makeEmpty();
    box.expandByPoint(skToWorld([-15, y0 - 10])); box.expandByPoint(skToWorld([x1, y1 + 10]));
  } else if (faccia) box.union(faccia);
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
  provaVia();
  togliRossi();
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
  ribbonTabs();
  resize();
  $('#sk-foot').hidden = true;
  $('#sk-cmd').hidden = true;
  $('#sk-tip').style.display = 'none';
  $('#sk-snap').style.display = 'none';
  for (const g of [skGroup, skGrid, skRubber, skOver]) { g.traverse(x => x.geometry?.dispose()); g.clear(); }
  skBase = null;
  chiudiOrigine();
  goTo(vistaIso());
  renderTree();
  buildDims();
}
function fitSketch(subito = false, extra = []) {
  const pts = SK.v.points.filter(p => p.id !== 'O').map(p => v3(p.xyz));
  const box = new THREE.Box3();
  pts.forEach(p => box.expandByPoint(p));
  // 03/11: anche la pancia degli archi (il collare: la cima dell'arco R55 restava fuori) e l'anteprima in corso
  for (const a of SK.v.arcs || []) for (let i = 0; i <= 8; i++) { const t = a.a0 + (a.a1 - a.a0) * i / 8; box.expandByPoint(skToWorld([a.xc[0] + a.r * Math.cos(t), a.xc[1] + a.r * Math.sin(t)])); }
  extra.forEach(p => box.expandByPoint(p));
  SK.v.circles.forEach(c => { box.expandByPoint(v3(c.center).addScalar(c.r)); box.expandByPoint(v3(c.center).addScalar(-c.r)); });
  // sullo sviluppo o su una faccia si inquadra sempre anche quella: si disegna sopra di lei
  if (SK.v.on_flat && flatGroup.children.length) box.union(flatBox());
  else if (SK.v.on_face && workGroup.children.length) box.union(new THREE.Box3().setFromObject(workGroup));
  else if (!box.isEmpty()) box.expandByPoint(v3(SK.v.origin));
  if (box.isEmpty()) return;
  // 04/11: un disegno appena iniziato (la prima linea da 28) non riempie la vista: almeno 200 mm attorno, così c'è
  // posto per il resto (A_collare 5-7: 40 scatti di rotella per rimpicciolire)
  const tratti = SK.v.lines.filter(l => !l.ref && !l.construction).length + (SK.v.arcs || []).length + SK.v.circles.length;
  if (!SK.v.on_flat && !SK.v.on_face && tratti <= 1) {            // solo il primo tratto: con più cose si inquadra quello che c'è
    const c = skToLocal(box.getCenter(new THREE.Vector3())), sz = box.getSize(new THREE.Vector3());
    if (Math.max(sz.x, sz.y, sz.z) < 200) { box.expandByPoint(skToWorld([c[0] - 100, c[1] - 100])); box.expandByPoint(skToWorld([c[0] + 100, c[1] + 100])); }
  }
  const zd = v3(SK.v.z_dir);
  if (Math.abs(zd.z) > 0.99) zd.add(new THREE.Vector3(0, -0.0001 * Math.sign(zd.z), 0));
  fitBox(box, zd, false, subito);
}
// Vedi attraverso: le parti dietro e davanti alla faccia, proiettate (ci si aggancia); il pezzo si vede in trasparenza
function toggleXray() {
  if (!SK || !SK.v.on_face || SK.v.on_tube) return;
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
  setHelp(AIUTI[t] + AIUTI_VISTA);
  $('#sk-tip').style.display = 'none';              // 04/11: niente scritta vecchia del mouse (B_staffa 21-31)
  if (t === 'text' && SK.lastText && !SK.provaTesto) provaTesto(SK.lastText);    // la scritta di prima segue il mouse
  SK.arcR = null;
  if (t === 'arcr') arcrInizia();
  drawRubber();
}
// 28/10: la barra «cosa fare adesso», uguale per ogni comando. I comandi scrivono come prima («Nome: cosa fare · Esc
// annulla»); qui diventa: il comando con la sua icona, i passi (2 di 3), cosa fare, e i tasti disegnati
const ICONA_CMD = { Raccordo: 'fillet', Smusso: 'chamfer', Saldatura: 'saldatura', Quota: 'dimension', Angolo: 'plane_angle', Offset: 'offset',
  Specchia: 'mirror', Copia: 'copy', Sposta: 'move', Poligono: 'polygon', Linea: 'line', Rettangolo: 'rect', Cerchio: 'circle', Arco: 'arc3',
  Asola: 'slot', Testo: 'text', 'Arco col raggio': 'arc_tangent', Accorcia: 'trim', Allunga: 'extend', Serie: 'pattern_rect', 'Faccia su faccia': 'faccia_su_faccia', 'Foro su foro': 'foro_su_foro',
  'Testa a testa': 'cut', 'Cono su cono': 'fastener', Distanza: 'dimension', Tangente: 'c_tangent', Parallele: 'c_parallel',
  Perpendicolari: 'c_perpendicular', 'In mezzo': 'c_symmetry', Blocca: 'c_fix', 'Spigolo su spigolo': 'c_collinear', 'Spigolo su faccia': 'c_coincident',
  Seleziona: 'select', Costruzione: 'construction', Appoggia: 'appoggia', 'Metti nel vano': 'vano', 'Vite nei fori': 'fastener' };
let misuraSkFoot = () => {};
// 04/11: la casella di comando (#sk-cmd) sta sopra la barra d'aiuto anche quando la barra va su due righe (avviso del
// profilo aperto): l'altezza della barra in una variabile CSS
{
  const f = document.getElementById('sk-foot');      // il modulo parte a pagina già letta: #sk-foot c'è
  // 04/11 notte (occhio): conta anche quanto la barra sta alta dal fondo della vista (non solo la sua altezza): la casella
  // della distanza (Offset) non la copre mai
  const misura = () => {
    document.documentElement.style.setProperty('--sk-foot-h', (f.offsetHeight || 38) + 'px');
    const sopra = f.offsetParent ? f.offsetParent.clientHeight - f.offsetTop : 0;
    if (sopra > 0) document.documentElement.style.setProperty('--sk-foot-sopra', sopra + 'px');
  };
  if (f && window.ResizeObserver) { new ResizeObserver(misura).observe(f); new ResizeObserver(misura).observe(document.getElementById('view')); }
  if (f) misuraSkFoot = misura;
}
function setHelp(t) {
  const el = $('#sk-help');
  t = String(t || '');
  if (!t) { el.innerHTML = ''; el.removeAttribute('title'); return; }
  el.title = t.replace(/\s+·\s+/g, ' · ');         // una riga sola: il testo intero passando col mouse
  const pezzi = t.split(/\s+·\s+/);
  let principale = pezzi.shift(), cmd = '', passo = null;
  const m = principale.match(/^([^:]{2,34}?)(?:\s*\((\d+) di (\d+)\))?:\s+(.+)$/);
  if (m) { cmd = m[1].trim(); principale = m[4]; if (m[2]) passo = [+m[2], +m[3]]; }
  const tasti = [], altro = [];
  for (const p of pezzi) {
    const k = p.match(/^(Esc|Invio|Canc|Maiusc|F\d+)\b\s*(?:per\s+)?(.*)$/i) || p.match(/^(tasto destro|destro|rotella|doppio clic)\s*(.*)$/i);
    if (k) tasti.push([k[1].replace(/^destro$/i, 'tasto destro'), k[2]]); else altro.push(p);
  }
  const kbd = x => /^(tasto destro|rotella|doppio clic)$/i.test(x) ? `<b class="g-mouse">${esc(x)}</b>` : `<kbd>${esc(x)}</kbd>`;
  const ic = ICONA_CMD[cmd.replace(/\s+\d.*$/, '')] || ICONA_CMD[cmd.split(' ')[0]];
  el.innerHTML = (cmd ? `<span class="g-cmd">${ic ? `<img src="icons/${ic}.svg" alt="">` : ''}${esc(cmd)}</span>` : '')
    + (passo ? `<span class="g-passi" title="Passo ${passo[0]} di ${passo[1]}">${Array.from({ length: passo[1] }, (_, i) => `<i class="${i < passo[0] ? 'on' : ''}"></i>`).join('')}</span>` : '')
    + `<span class="g-testo">${esc(principale[0].toUpperCase() + principale.slice(1))}${altro.length ? `<small>${esc(altro.join(' · '))}</small>` : ''}</span>`
    + (tasti.length ? `<span class="g-sep"></span>${tasti.map(([k, v]) => `<span class="g-tasto">${kbd(k)}${esc(v)}</span>`).join('')}` : '');
}

// le linee del disegno spesse (le linee normali di WebGL sono sempre di 1 pixel: sullo sfondo scuro si vedevano poco,
// 21/10). Ogni linea diventa una Line2 con lo stesso colore e tratteggio; lo spessore in pixel per tipo di linea.
function grosso(m, w, h) {
  let g = GROSSI.get(m);
  if (!g) {
    g = new LineMaterial({ linewidth: SPESSORE.get(m) ?? 2.6, dashed: !!m.isLineDashedMaterial, dashSize: m.dashSize ?? 3,
      gapSize: m.gapSize ?? 1, depthTest: m.depthTest, transparent: m.transparent, opacity: m.opacity ?? 1 });
    GROSSI.set(m, g);
  }
  g.color.copy(m.color);
  g.resolution.set(w, h);
  return g;
}
// 24/10: lo sketch in pochi oggetti, uno per colore. Uno per linea erano 1.600 oggetti da disegnare a ogni
// fotogramma (e da rifare a ogni passaggio del mouse): girare la vista e disegnare diventavano lenti
function lineeInBlocco(gruppo, tratti, ordine = 0) {           // tratti: [[punti 3D], materiale]
  const per = new Map();
  for (const [pts, mat] of tratti) {
    let b = per.get(mat);
    if (!b) per.set(mat, b = { xyz: [], dist: [] });
    let d = 0;                                          // il tratteggio riparte a ogni linea, come prima
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], c = pts[i], L = a.distanceTo(c);
      b.xyz.push(a.x, a.y, a.z, c.x, c.y, c.z);
      b.dist.push(d, d + L);
      d += L;
    }
  }
  const w = canvas.clientWidth, h = canvas.clientHeight;
  for (const [mat, { xyz, dist }] of per) {
    if (!xyz.length) continue;
    let o;
    if (lineeSpesse) {
      const g = grosso(mat, w, h), geo = new LineSegmentsGeometry();
      geo.setPositions(xyz);
      if (g.dashed) {
        const buf = new THREE.InstancedInterleavedBuffer(new Float32Array(dist), 2, 1);
        geo.setAttribute('instanceDistanceStart', new THREE.InterleavedBufferAttribute(buf, 1, 0));
        geo.setAttribute('instanceDistanceEnd', new THREE.InterleavedBufferAttribute(buf, 1, 1));
      }
      o = new LineSegments2(geo, g);
    } else {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(xyz, 3));
      if (mat.isLineDashedMaterial) geo.setAttribute('lineDistance', new THREE.Float32BufferAttribute(dist, 1));
      o = new THREE.LineSegments(geo, mat);
    }
    o.renderOrder = ordine;
    gruppo.add(o);
  }
}
function ingrossa(gruppo) {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  for (const ln of [...gruppo.children]) {
    if (!ln.isLine || ln.isLine2) continue;
    const g = grosso(ln.material, w, h);
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
// i punti di un elemento dello sketch, come polilinee 3D
function skPolilinee(tipo, e, v) {
  if (tipo === 'line') return [[v3(e.pa), v3(e.pb)]];
  if (tipo === 'text') return e.strokes.map(s => s.map(q => v3(q)));
  const ctr = v3(e.center), x = v3(v.x_dir), y = v3(v.y_dir), pts = [];
  if (tipo === 'circle') for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; pts.push(ctr.clone().addScaledVector(x, e.r * Math.cos(a)).addScaledVector(y, e.r * Math.sin(a))); }
  else for (let i = 0; i <= 64; i++) { const t = e.a0 + (e.a1 - e.a0) * i / 64; pts.push(ctr.clone().addScaledVector(x, e.r * Math.cos(t)).addScaledVector(y, e.r * Math.sin(t))); }
  return [pts];
}
function drawSketch() {
  const v = SK.v, w = canvas.clientWidth, h = canvas.clientHeight;
  if (!skBase || skBase.v !== v || skBase.spesse !== lineeSpesse || skBase.w !== w || skBase.h !== h) disegnaBaseSketch(v, w, h);
  // sopra: selezionati e sotto il mouse (pochi, si rifà a ogni passaggio del mouse senza toccare il resto)
  skOver.traverse(x => x.geometry?.dispose()); skOver.clear();
  const sopra = [];
  for (const id of new Set([...SK.sel, ...(SK.hover ? [SK.hover] : [])])) {
    const el = skBase.idx.get(id);
    if (!el) continue;
    const [tipo, e] = el, sel = SK.sel.has(id);
    const mat = tipo === 'line' ? (sel ? (e.construction && !e.ref ? SK_CONSTR_SEL : SK_SEL) : SK_HOV) : sel ? SK_SEL : SK_HOV;
    for (const pts of skPolilinee(tipo, e, v)) sopra.push([pts, mat]);
  }
  lineeInBlocco(skOver, sopra, 3);
  skOver.position.copy(skGroup.position);
  statoSketch(v);
}
function disegnaBaseSketch(v, w, h) {
  for (const g of [skGroup, skGrid]) { g.traverse(x => x.geometry?.dispose()); g.clear(); }
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
  const sciolte = new Set(v.sciolte || []), idx = new Map(), tratti = [];
  for (const l of v.lines) {
    idx.set(l.id, ['line', l]);
    const mat = l.xray ? SK_XRAY : l.piega ? (l.piega === 'centro' ? SK_PIEGA : SK_PIEGA_BORDO) : l.ref ? SK_REF
      : l.construction ? SK_CONSTR : sciolte.has(l.id) ? SK_SCIOLTA : SK_LINE;
    tratti.push([[v3(l.pa), v3(l.pb)], mat]);
  }
  for (const t of v.texts || []) {                  // testi da marcare: i tratti delle lettere
    idx.set(t.id, ['text', t]);
    for (const pts of skPolilinee('text', t, v)) tratti.push([pts, SK_TESTO]);
  }
  for (const c of v.circles) {
    idx.set(c.id, ['circle', c]);
    tratti.push([skPolilinee('circle', c, v)[0], c.xray ? SK_XRAY : c.ref ? SK_REF : c.construction ? SK_CONSTR : SK_LINE]);
    const fuori = c.hole?.tipo === 'filettato' ? ({ M3: 3, M4: 4, M5: 5, M6: 6, M8: 8, M10: 10, M12: 12, M16: 16 }[c.hole.M] || 0) / 2
      : c.hole?.tipo === 'svasato' ? Number(c.hole.D) / 2 : 0;
    if (fuori > c.r) tratti.push([skPolilinee('circle', { ...c, r: fuori }, v)[0], SK_CONSTR]);   // filettatura o svasatura: tratteggiato attorno
  }
  for (const a of v.arcs || []) {
    idx.set(a.id, ['arc', a]);
    tratti.push([skPolilinee('arc', a, v)[0], a.xray ? SK_XRAY : a.ref ? SK_REF : a.construction ? SK_CONSTR : sciolte.has(a.id) ? SK_SCIOLTA : SK_LINE]);
  }
  lineeInBlocco(skGroup, tratti);
  const pg = new THREE.BufferGeometry().setFromPoints(v.points.map(p => v3(p.xyz)));
  skGroup.add(new THREE.Points(pg, SK_PTS));
  skGroup.position.copy(v3(v.z_dir).multiplyScalar(0.05));
  skBase = { v, spesse: lineeSpesse, w, h, idx };
}
// Elimina nello sketch (24/10): i bordi arancio sono il pezzo; se vengono da un taglio fatto prima, invece del «non si
// cancellano» si dice da quale taglio vengono e si può toglierli da lì, aprire quel disegno o togliere tutto il taglio
function eliminaNelloSketch(ids) {
  const arancio = id => !!skBase?.idx.get(id)?.[1]?.ref;
  const propri = ids.filter(id => !arancio(id)), bordi = ids.filter(arancio);
  if (propri.length) inCoda(async () => { await apply(await call('sketch_delete', SK.sid, propri)); });
  else if (bordi.length) inCoda(() => origineBordi(bordi));
}
function chiudiOrigine() { $('#sk-origine')?.remove(); }
async function origineBordi(ids) {
  chiudiOrigine();
  const sid = SK?.sid;
  const r = await call('origine_bordi', sid, ids);
  if (!r.ok) { toast(r.message, 'err'); return; }
  const box = document.createElement('div');
  box.id = 'sk-origine';
  const quanti = r.fori ? (r.tutti ? `tutti i suoi ${r.totale} ${r.totale === 1 ? 'contorno' : 'contorni'}` : `${r.fori} ${r.fori === 1 ? 'foro' : 'fori'} dei suoi ${r.totale}`) : '';
  box.innerHTML = `<div class="or-testo">Questi bordi arancio sono ${r.fori === 1 ? 'un foro' : 'fori'} già fatti da <b>${esc(r.nome)}</b> (${esc(r.feature)})${quanti ? ': ' + quanti : ''}.
      ${r.altri ? `<span class="hint">${r.altri} ${r.altri === 1 ? 'bordo scelto viene' : 'bordi scelti vengono'} da un altro taglio: rifalli dopo.</span>` : ''}
      ${!r.eids.length ? '<span class="hint">Il taglio è disegnato sullo sviluppo: i fori si tolgono dal suo disegno.</span>' : ''}</div>
    <div class="or-bott">
      ${r.eids.length && !r.tutti ? `<button class="btn primary" id="or-togli">Togli ${r.fori === 1 ? 'questo foro' : `questi ${r.fori} fori`}</button>` : ''}
      <button class="btn" id="or-apri">Apri il disegno di ${esc(r.feature)}</button>
      <button class="btn danger" id="or-tutto">Togli tutto il taglio</button>
      <button class="btn" id="or-chiudi" aria-label="Chiudi">×</button></div>`;
  document.body.appendChild(box);
  $('#or-chiudi').onclick = chiudiOrigine;
  if ($('#or-togli')) $('#or-togli').onclick = () => { chiudiOrigine();
    provaSulPezzo({ metodo: 'togli_fori_da_taglio', argomenti: () => [sid, ids], togli: true, conferma: 'Chiudi i fori', frase: r => r?.frase || 'Chiude i fori scelti',
      sotto: () => 'La lamiera torna piena dove c’erano · si annulla con Ctrl+Z',
      fai: () => inCoda(async () => { const x = await call('togli_fori_da_taglio', sid, ids); await apply(x, x.message); }) }); };
  $('#or-apri').onclick = () => { chiudiOrigine(); exitSketch(); inCoda(() => enterSketch(r.sketch)); };
  $('#or-tutto').onclick = () => { chiudiOrigine(); confermaElimina('feature', r.feature, `${r.nome} (${r.feature}): tutti i suoi fori e tagli`); };
}
function statoSketch(v) {
  // in alto nel pannello: dove sei e cosa fare adesso, in parole semplici
  const libero = !v.used_by.length, suPezzo = !!(v.on_face || v.on_flat), pronto = v.ok && v.profiles > 0;
  let cls = 'todo', testo;
  if (!libero) { cls = 'ok'; testo = `Usato da ${v.used_by.join(', ')}: cambia linee o quote e il pezzo si aggiorna da solo.`; }
  else if (!v.drawn) testo = suPezzo
    ? 'Vuoto. Scegli Rettangolo o Cerchio e disegna sulla faccia. Le misure partono dall’angolo in basso a sinistra (0;0); i bordi del pezzo sono in arancio: ci si aggancia e ci si fa l’offset.'
    : 'Vuoto. Scegli Linea o Rettangolo e disegna il contorno.';
  else if (pronto) { cls = 'ok'; testo = `✓ ${v.profiles === 1 ? '1 contorno chiuso' : v.profiles + ' contorni chiusi'}: ${suPezzo ? 'premi «Togli materiale» per fare il foro' : 'crea la lamiera o la piastra'}. Per cambiare una misura, clicca la quota.`;
    if (v.sciolte?.length) { cls = 'todo'; testo += ' ⚠ ' + v.status; } }
  else if (v.on_sheet && !v.on_flat) { cls = 'todo'; testo = 'Linea aperta da bordo a bordo (arancio): «Togli materiale» la chiude lungo il bordo e toglie il pezzo più piccolo; «Aggiungi materiale» se è disegnata fuori, attaccata al bordo. Se parte dallo spigolo di un bordo libero: «Pieghe e forme ▾» → «Lamiera a contorno» la fa diventare lamiera piegata.'; }
  else { cls = 'bad'; testo = /^Il disegno (è tutto quotato|si può ancora muovere)/.test(v.status || '') ? 'Nessun contorno chiuso: chiudi il disegno tornando sul primo punto.' : v.status; }
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
  $('#rb-xray').hidden = !(SK && SK.v.on_face) || !!v.on_tube;
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
  $('#sk-tab').hidden = !((v.tab_ok && v.on_face) || v.on_flat);
  $('#sk-tab').disabled = !v.drawn;
  $('#sk-mark').hidden = !!v.on_tube; $('#sk-boss').hidden = $('#sk-boss').hidden || !!v.on_tube;   // sul tubo: si buca e basta
  // una sagoma di tubi: un solo pulsante grande, «Fai i tubi»; i comandi della lamiera non servono (22/10)
  $('#sk-tubi').hidden = !v.sagoma;
  $('#sk-tubi').disabled = !v.lines.some(l => !l.construction);
  for (const m of ['sheet', 'plate', 'revolve', 'structure', 'profilo']) {
    const b = document.querySelector(`#sk-make [data-make="${m}"]`);
    if (b) b.hidden = !!v.sagoma;
  }
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
  // la misura della vista letta una volta: chiederla al browser per ogni punto era metà del tempo a ogni movimento
  const W = view.clientWidth, H = view.clientHeight, skScreenQui = q => skScreen(q, W, H);
  const prendi = (q, tipo, extra = {}) => {
    const sq = skScreenQui(q), d = Math.hypot(sq[0] - mx, sq[1] - my);
    if (d < AP) cand.push({ xy: q, tipo, d, ...extra });
  };
  const centri = new Set([...SK.v.circles, ...(SK.v.arcs || [])].map(c => c.center_id));
  for (const p of SK.v.points) prendi(p.xy, p.id === 'O' ? 'origine' : centri.has(p.id) ? 'centro' : 'punto', { id: p.id });
  SK.pts.forEach((p, i) => { if (!p.id) prendi(p.xy, 'punto', { id: null, first: i === 0 }); });
  const L = SK.v.lines, tondi = roundsOf();
  for (const l of L) prendi([(l.xa[0] + l.xb[0]) / 2, (l.xa[1] + l.xb[1]) / 2], 'metà', { ref: { mid: l.id } });
  // gli incroci non dipendono dal mouse: calcolati una volta per disegno (03/11: con 600 linee erano 180 mila conti a
  // ogni movimento del mouse), poi a ogni movimento si guarda solo quali sono vicini. Stesso ordine di prima
  for (const [x, a, b] of incrociSketch(SK.v)) { const q = [x[0], x[1]]; prendi(q, 'incrocio', { ref: { cross: [a, b], xy: q } }); }
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
    const sp = skScreenQui(p.xy);
    if (Math.abs(sp[0] - sm[0]) < 7 && (!tx || Math.abs(sp[0] - sm[0]) < tx.d)) tx = { p, d: Math.abs(sp[0] - sm[0]) };
    if (Math.abs(sp[1] - sm[1]) < 7 && (!ty || Math.abs(sp[1] - sm[1]) < ty.d)) ty = { p, d: Math.abs(sp[1] - sm[1]) };
  }
  // orizzontale/verticale rispetto al punto prima: a meno di 7 pixel dalla sua orizzontale/verticale
  const hvLast = last && (SK.tool === 'line' || (SK.tool === 'slot' && SK.pts.length === 1));
  const st = skStep();
  let q = SK.grid ? [Math.round(xy[0] / st) * st, Math.round(xy[1] / st) * st] : [xy[0], xy[1]];
  let how = SK.grid ? 'griglia' : '', tipo = null, ref = null, guide = [];
  if (hvLast) {
    const sl = skScreenQui(last.xy);
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
// tutti gli incroci del disegno [punto, id, id]: linea-linea, linea-cerchio, cerchio-cerchio; ricordati per la vista
let _incroci = null;
function incrociSketch(v) {
  if (_incroci && _incroci.v === v) return _incroci.lista;
  const L = v.lines, tondi = roundsOf(), lista = [];
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
    const q = segX(L[i].xa, L[i].xb, L[j].xa, L[j].xb);
    if (q) lista.push([q, L[i].id, L[j].id]);
  }
  for (const c of tondi) for (const l of L) for (const q of segCircle(l.xa, l.xb, c)) lista.push([q, l.id, c.id]);
  for (let i = 0; i < tondi.length; i++) for (let j = i + 1; j < tondi.length; j++)
    for (const q of circleCircle(tondi[i], tondi[j])) lista.push([q, tondi[i].id, tondi[j].id]);
  _incroci = { v, lista };
  return lista;
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
  // le quote si cliccano anche con un comando in mano, finché non hai cominciato a disegnare (02/11: con «Arco»
  // acceso il clic su R56 faceva partire un altro arco); a disegno cominciato i clic ci passano attraverso
  document.body.classList.toggle('in-corso', !!(SK && SK.pts && SK.pts.length));
  // la scritta in prova: al punto cliccato (finestra aperta) o sotto il mouse col comando Testo (le ultime misure)
  const pt = SK?.provaTesto;
  if (pt?.tratti?.length && (pt.at || (SK.tool === 'text' && SK.cursor && $('#modal').hidden))) {
    const o = pt.at || SK.cursor.xy;
    for (const tr of pt.tratti) skRubber.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(tr.map(q => skToWorld([q[0] + o[0], q[1] + o[1]]))), SK_TESTO));
  }
  const tip = $('#sk-tip');
  if (SK?.scritteProva) {                           // le scritte sotto i fori, in prova al loro posto
    for (const sp of SK.scritteProva) for (const tr of sp.tratti) skRubber.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(tr.map(q => skToWorld([q[0] + sp.at[0], q[1] + sp.at[1]]))), SK_TESTO));
    tip.style.display = 'none'; ridisegna(); return;
  }
  if (SK?.serieProva) {                             // la serie in prova: le copie (non l'originale) in azzurro
    const P = SK.serieProva;
    const metti = (pts, mat) => { const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(skToWorld)), mat); l.computeLineDistances(); skRubber.add(l); };
    for (let j = 0; j < P.r; j++) for (let i = 0; i < P.c; i++) if (i || j) anteprimaCopia(P.ids, i * P.px, j * P.py, metti);
    tip.style.display = 'none'; ridisegna(); return;
  }
  if (SK?.pick?.what === 'corner') { drawSnap({ tipo: 'punto', xy: SK.pick.xy }); updateCmd(); ridisegna(); return; }
  if (SK && (SK.tool === 'trim' || SK.tool === 'extend') && !SK.pick) {
    tip.style.display = 'none';
    const pv = SK.cutPrev;
    if (pv?.tool === 'trim') skRubber.add(fatLine(pv.remove, 5, SK_CUT_FILL)); else if (pv?.tool === 'extend') {
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pv.add.map(skToWorld)), SK_RUB);
      l.computeLineDistances(); skRubber.add(l);
    }
    if (SK.cutMsg && SK.cutAt) setHelp(SK.cutMsg); else setHelp(AIUTI[SK.tool] + AIUTI_VISTA);
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
  if (SK?.tool === 'arcr' && !SK.cursor) {         // arco col raggio: l'anteprima c'è anche senza il mouse sul disegno
    arcrDisegna(pts => { const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(skToWorld)), SK_RUB); l.computeLineDistances(); skRubber.add(l); });
    tip.style.display = 'none'; ridisegna(); return;
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
  } else if (SK.tool === 'arcr') {
    testo = arcrDisegna(add);
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
  // 04/11: dopo Esc il punto scritto non è più sotto il mouse: niente «28 ; 0 · scritto» lasciato lì (percorso A)
  if (SK.cursor.how === 'scritto' && !SK.pts.length) { tip.style.display = 'none'; ridisegna(); return; }
  const s = skScreen(c);
  const aggancio = SK.cursor.how && SK.cursor.how !== 'griglia' ? ` · ${SK.cursor.how}` : '';
  const scritto = SK.buf ? `<b>${esc(SK.buf)}</b>_ ` : '';
  tip.innerHTML = `${scritto}${esc(testo || `${num(c[0], 2)} ; ${num(c[1], 2)}`)}${esc(aggancio)}`;
  tip.style.display = 'block';
  // 04/11: la scritta vicino al mouse resta dentro la vista (prima usciva dal bordo destro, A_collare 16 e B_staffa 21)
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  const tx = s[0] + 14 + tw > view.clientWidth - 8 ? s[0] - 14 - tw : s[0] + 14;
  const ty = s[1] + 14 + th > view.clientHeight - 8 ? s[1] - 14 - th : s[1] + 14;
  tip.style.left = Math.max(4, tx) + 'px'; tip.style.top = Math.max(4, ty) + 'px';
  ridisegna();
}

view.addEventListener('pointerleave', () => { $('#sk-tip').style.display = 'none'; });
function skHit(ev) {          // linea o cerchio vicino al mouse (per selezionare)
  const r = canvas.getBoundingClientRect(), m = [ev.clientX - r.left, ev.clientY - r.top];
  let best = null;
  const segDist = (p, a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L));
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  };
  const W = view.clientWidth, H = view.clientHeight;          // letta una volta, non per ogni punto (03/11)
  const proj = p => { const q = v3(p).project(camera); return [(q.x + 1) / 2 * W, (1 - q.y) / 2 * H]; };
  for (const l of SK.v.lines) { const d = segDist(m, proj(l.pa), proj(l.pb)); if (d < 7 && (!best || d < best.d)) best = { id: l.id, d }; }
  for (const c of SK.v.circles) {
    const ctr = proj(c.center), e = proj(skToWorld([...skToLocal(v3(c.center))].map((v, i) => i === 0 ? v + c.r : v)));
    const dc = Math.hypot(m[0] - ctr[0], m[1] - ctr[1]), rs = Math.hypot(e[0] - ctr[0], e[1] - ctr[1]);
    let d = Math.abs(dc - rs);
    // 04/11: un foro piccolo sullo schermo si prende anche cliccandoci dentro (sul suo centro), non solo sul filo:
    // prima il clic al centro non sceglieva niente e «Serie» e «Tipo di foro» restavano spenti
    if (d >= 7 && dc < rs && rs <= 40) d = 6.9;
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
    if (SK.pick.stage === 'side') {
      // 03/11: il mouse fermo resta sullo stesso punto del disegno anche se la vista finisce di muoversi sotto
      // (dopo «Disegna sulla faccia»): il lato è quello dell'anteprima che hai visto, non quello di dopo
      const P = SK.pick, fermo = P.schermo && P.schermo[0] === ev.clientX && P.schermo[1] === ev.clientY;
      if (!fermo) { P.schermo = [ev.clientX, ev.clientY]; P.mouse = skPick(ev); offPreview(); }
    }
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
// ------------------------------------------------------------- arco col raggio scritto (03/11)
// Dopo una linea: l'arco parte dalla sua fine. Si scrive il raggio (55) e si sceglie quanto gira (90°, mezzo giro,
// altro) e come parte (tangente, o a squadra come il collare); il mouse dice da che parte. Niente punti cliccati sulla
// griglia: raggio e angolo sono esatti. Poi si torna alla Linea, dalla fine dell'arco.
let ultimoArcoR = { giro: 180, partenza: 'squadra' };
function arcrPunti(A, r) {          // centro, fine e punti dell'arco per l'anteprima (stessi conti del motore)
  const [ax, ay] = A.xa, [bx, by] = A.xb, L = Math.hypot(bx - ax, by - ay) || 1;
  const ux = (bx - ax) / L, uy = (by - ay) / L, nx = -uy, ny = ux, lato = A.lato >= 0 ? 1 : -1;
  let cx, cy, antiorario;
  if (ultimoArcoR.partenza === 'squadra') { cx = bx + r * ux; cy = by + r * uy; antiorario = lato < 0; }
  else { cx = bx + lato * r * nx; cy = by + lato * r * ny; antiorario = lato > 0; }
  const t = ultimoArcoR.giro * Math.PI / 180 * (antiorario ? 1 : -1), vx = bx - cx, vy = by - cy;
  const pts = [];
  for (let i = 0; i <= 48; i++) { const a = t * i / 48; pts.push([cx + vx * Math.cos(a) - vy * Math.sin(a), cy + vx * Math.sin(a) + vy * Math.cos(a)]); }
  return { c: [cx, cy], fine: pts[pts.length - 1], pts };
}
// la linea da cui parte: quella appena disegnata (la sua fine), o quella cliccata vicino a una delle sue estremità
function arcrDa(pid) {
  const linee = SK.v.lines.filter(l => !l.ref && !l.construction);
  const l = pid ? linee.find(x => x.a === pid || x.b === pid)
    : linee.sort((p, q) => (+q.id.replace(/\D/g, '') || 0) - (+p.id.replace(/\D/g, '') || 0))[0];
  if (!l) return null;
  const finale = pid ? pid : l.b;
  return finale === l.b ? { linea: l.id, punto: l.b, xa: l.xa, xb: l.xb, lato: 1 } : { linea: l.id, punto: l.a, xa: l.xb, xb: l.xa, lato: 1 };
}
function arcrInizia() {
  SK.arcR = arcrDa(null);
  SK.pts = SK.arcR ? [{ id: SK.arcR.punto, xy: SK.arcR.xb }] : [];
  arcrAiuto();
}
function arcrAiuto() {
  setHelp(SK.arcR ? 'Arco col raggio: scrivi il raggio + Invio · sopra scegli quanto gira e come parte · il mouse dice da che parte · clic sulla fine di un’altra linea per partire da lì · Esc finisce'
    : 'Arco col raggio: clic sulla fine della linea da cui parte l’arco · Esc finisce');
}
function arcrRaggio() {
  const v = parseFloat(String(SK.buf || '').replace(',', '.'));
  if (v > 0) return v;
  if (ultimoArcoR.r > 0) return ultimoArcoR.r;
  return null;
}
function arcrDisegna(add) {
  const A = SK.arcR;
  if (!A) return '';
  const c = SK.cursor?.xy;
  if (c) {                                             // da che parte: a sinistra o a destra della linea
    const ux = A.xb[0] - A.xa[0], uy = A.xb[1] - A.xa[1];
    const cr = ux * (c[1] - A.xb[1]) - uy * (c[0] - A.xb[0]);
    if (Math.abs(cr) > 1e-6) A.lato = cr > 0 ? 1 : -1;
  }
  const r = arcrRaggio();
  if (!r) return 'scrivi il raggio';
  const p = arcrPunti(A, r);
  add(p.pts);
  // l'anteprima esce dalla vista: si allarga (una volta per raggio, se no la vista balla mentre muovi il mouse)
  const fuori = p.pts.some(q => { const v = skToWorld(q).project(camera); return Math.abs(v.x) > 0.95 || Math.abs(v.y) > 0.95; });
  if (fuori && A.adattato !== r) { A.adattato = r; setTimeout(() => SK && fitSketch(false, p.pts.map(skToWorld)), 0); }
  return `R ${num(r, 2)} · ${ultimoArcoR.giro === 180 ? 'mezzo giro' : num(ultimoArcoR.giro, 1) + '°'} · ${ultimoArcoR.partenza === 'squadra' ? 'a squadra' : 'tangente'}`;
}
function arcrClic(c) {                                 // clic sulla fine di un'altra linea: si parte da lì
  if (!c.id) { if (!SK.arcR) toast('Clicca la fine di una linea: l’arco parte da lì.', 'err'); return; }
  const A = arcrDa(c.id);
  if (!A) { toast('Questo punto non è la fine di una linea.', 'err'); return; }
  SK.arcR = A; SK.pts = [{ id: A.punto, xy: A.xb }];
  arcrAiuto();
}
function arcrScritto(r) {
  const A = SK.arcR;
  if (!A) { toast('Prima clicca la fine della linea da cui parte l’arco.', 'err'); return; }
  ultimoArcoR.r = r;
  const fine = arcrPunti(A, r).fine, sid = SK.sid, k = SK.constr;
  const g = ultimoArcoR.giro, part = ultimoArcoR.partenza, lato = A.lato;
  inCoda(async () => {
    const res = await call('sketch_add_arc_raggio', sid, A.linea, A.punto, r, g, part, lato, k);
    if (!(await apply(res)) || !SK || SK.sid !== sid) return;
    // si continua con la Linea dalla fine dell'arco: scrivi 28 + Invio per la gamba
    setTool('line');
    SK.pts = [{ id: res.end, xy: fine }];
    if (SK.v.points.some(q => { const p = v3(q.xyz).project(camera); return Math.abs(p.x) > 0.95 || Math.abs(p.y) > 0.95; })) fitSketch(true);
    drawRubber();
  });
}
// i pulsanti «quanto gira» e «come parte», accanto alla casella in alto
function arcrScelte() {
  const g = ultimoArcoR.giro, p = ultimoArcoR.partenza;
  const b = (k, v, t, on) => `<button type="button" data-arcr-${k}="${v}" class="${on ? 'on' : ''}">${t}</button>`;
  return `<span class="arcr"><span>gira</span>${b('g', 90, '90°', g === 90)}${b('g', 180, 'mezzo giro', g === 180)}<input id="sk-arcr-g" value="${esc(virgola(g))}" title="Quanti gradi gira l’arco"><i>°</i>
    <span>parte</span>${b('p', 'tangente', 'tangente', p === 'tangente')}${b('p', 'squadra', 'a squadra', p === 'squadra')}</span>`;
}
document.addEventListener('mousedown', ev => { if (ev.target.closest('[data-arcr-g],[data-arcr-p]')) ev.preventDefault(); });   // la casella del raggio resta attiva
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-arcr-g],[data-arcr-p]');
  if (!b || !SK) return;
  if (b.dataset.arcrG) ultimoArcoR.giro = +b.dataset.arcrG; else ultimoArcoR.partenza = b.dataset.arcrP;
  $('#sk-cmd-extra').innerHTML = arcrScelte();
  drawRubber();
});
document.addEventListener('input', ev => {
  if (ev.target.id !== 'sk-arcr-g') return;
  const v = parseFloat(ev.target.value.replace(',', '.'));
  if (v > 0 && v < 360) { ultimoArcoR.giro = v; drawRubber(); }
});
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
  } else if (SK.tool === 'arcr') {
    arcrClic(c);
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
    finestraTesto({ valori: SK.lastText, at: p.xy, nuova: true, ok: (v, close) => {
      SK.lastText = v;
      close();
      inCoda(async () => { await apply(await call('sketch_add_text', sid, ptArg(p), v.text, v.h, v.angle, v.come || null, v.centro)); });
    } });
  } else if (SK.tool === 'circle') {
    if (!SK.pts.length) { SK.pts.push(p); }
    else { const a = SK.pts[0]; SK.pts = []; const k = SK.constr; const r = Math.hypot(c.xy[0] - a.xy[0], c.xy[1] - a.xy[1]); if (r > 0) inCoda(async () => { await apply(await call('sketch_add_circle', SK.sid, ptArg(a), r, k)); }); }
  }
  SK.buf = '';
  drawRubber();
}
// la finestra del testo (30/10): nuova, al punto cliccato, o per cambiare una scritta già messa (doppio clic). Mentre
// scrivi, la scritta si vede al suo posto; «al centro» = il punto cliccato è il centro della scritta (sul centro del foro)
const TESTO_BASE = { text: '', h: 5, angle: 0, come: '', centro: true };
// una scritta sotto ogni foro scelto, in una volta (03/11, porta ugelli: 6 numeri sotto 6 fori). I fori da sinistra
// a destra; ogni scritta si vede al suo posto mentre scrivi. La finestra sta di lato e non copre i fori
function scritteSottoFori(sid, cerchi) {
  const fori = cerchi.map(id => SK.v.circles.find(c => c.id === id)).filter(Boolean)
    .sort((a, b) => (Math.round(a.xc[0] * 1000) - Math.round(b.xc[0] * 1000)) || (a.xc[1] - b.xc[1]));
  const u = { ...TESTO_BASE, come: 'saira', ...(SK.lastText || {}) };
  const virg = x => esc(String(x).replace('.', ','));
  modal(`<h3>${fori.length === 1 ? 'Scritta sotto il foro' : `Scritte sotto ${fori.length} fori`}</h3>
    <p class="hint">Da sinistra a destra. Ogni scritta va centrata sotto il suo foro; vuota = niente.</p>
    <div class="form" id="ss-form">${fori.map((f, i) => `<label>Foro ${i + 1} (Ø${virg(Math.round(f.r * 200) / 100)})<input class="field" data-ss="${i}" value=""></label>`).join('')}
      <label class="tutta-riga">Come<select class="field" id="ss-c">
        <option value="saira"${u.come === 'saira' ? ' selected' : ''}>Tagliato passante, lettere grosse (Saira Stencil)</option>
        <option value="allerta"${u.come === 'allerta' ? ' selected' : ''}>Tagliato passante, lettere sottili (Allerta Stencil)</option>
        <option value=""${!u.come ? ' selected' : ''}>Marcato col laser (non buca, layer MARK)</option></select></label>
      <label>Altezza delle lettere<span class="inp"><input class="field" id="ss-h" value="${virg(u.h)}"><i>mm</i></span></label>
      <label>Spazio sotto il foro<span class="inp"><input class="field" id="ss-g" value="2"><i>mm</i></span></label></div>
    <p class="fo-frase" id="ss-frase"></p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Metti le scritte</button></div>`, close => {
    $('#modal').classList.add('laterale');
    const leggi = () => ({ testi: fori.map((_, i) => $(`[data-ss="${i}"]`).value), h: $('#ss-h').value.trim().replace(',', '.'),
      come: $('#ss-c').value, gioco: $('#ss-g').value.trim().replace(',', '.') });
    let giro = 0;
    const prova = async () => {
      const v = leggi(), mio = ++giro, h = parseFloat(v.h), g = parseFloat(v.gioco) || 0;
      const fatti = [];
      for (let i = 0; i < fori.length; i++) {
        const t = v.testi[i].trim();
        if (!t || !(h > 0)) continue;
        const r = await call('testo_anteprima', t, h, 0, v.come || null, true);
        if (mio !== giro || !SK) return;
        if (r?.ok) fatti.push({ at: [fori[i].xc[0], fori[i].xc[1] - fori[i].r - g - h / 2], tratti: r.tratti });
      }
      SK.scritteProva = fatti;
      $('#ss-frase').textContent = fatti.length ? `${fatti.length} ${fatti.length === 1 ? 'scritta' : 'scritte'}: si vedono già sotto i fori` : 'Scrivi le scritte (es. 1.0, 1.2, 1.5…)';
      drawRubber();
    };
    let t = null;
    $('#ss-form').addEventListener('input', () => { clearTimeout(t); t = setTimeout(prova, 150); });
    $('#ss-form').addEventListener('change', () => { clearTimeout(t); t = setTimeout(prova, 50); });
    const chiudi = () => { if (SK) { SK.scritteProva = null; drawRubber(); } close(); };
    $('#m-no').onclick = chiudi;
    $('#m-ok').onclick = () => {
      const v = leggi();
      SK.lastText = { ...(SK.lastText || {}), come: v.come, h: v.h };
      chiudi();
      inCoda(async () => { const r = await call('sketch_scritte_sotto', sid, fori.map(f => f.id), v.testi, v.h, v.come || null, v.gioco); await apply(r, r.message); });
    };
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); $('#m-ok').click(); } if (ev.key === 'Escape') chiudi(); };
    setTimeout(() => scostaDallaFinestra(fori.map(f => skToWorld(f.xc))), 0);
    $('[data-ss="0"]')?.focus();
    prova();
  });
}
async function provaTesto(v, at = null) {
  if (!SK) return;
  const chiave = JSON.stringify([v.text, v.h, v.angle, v.come, v.centro]);
  if (SK.provaTesto?.chiave !== chiave) {
    const r = v.text?.trim() ? await call('testo_anteprima', v.text, v.h, v.angle || 0, v.come || null, !!v.centro) : null;
    if (!SK) return;
    SK.provaTesto = { chiave, tratti: r?.ok ? r.tratti : [] };
  }
  SK.provaTesto.at = at;
  drawRubber();
}
function finestraTesto({ valori, at, nuova, ok }) {
  const u = { ...TESTO_BASE, ...(valori || {}) };
  const virg = x => esc(String(x).replace('.', ','));
  modal(`<h3>${nuova ? 'Testo' : 'Cambia il testo'}</h3>
    <div class="form"><label class="tutta-riga">Testo<input class="field" id="tx-t" data-c="testo" value="${esc(u.text)}" placeholder="es. PP-001, Ø10, LATO A"></label>
      <label class="tutta-riga">Come<select class="field" id="tx-c">
        <option value=""${!u.come ? ' selected' : ''}>Marcato col laser (non buca, layer MARK)</option>
        <option value="saira"${u.come === 'saira' ? ' selected' : ''}>Tagliato passante, lettere grosse (Saira Stencil)</option>
        <option value="allerta"${u.come === 'allerta' ? ' selected' : ''}>Tagliato passante, lettere sottili (Allerta Stencil)</option></select></label>
      <label>Altezza delle lettere<span class="inp"><input class="field" id="tx-h" value="${virg(u.h)}"><i>mm</i></span></label>
      <label>Angolo<span class="inp"><input class="field" id="tx-a" value="${virg(u.angle)}"><i>°</i></span></label>
      ${nuova ? `<label class="tutta-riga">Il punto che hai cliccato è<select class="field" id="tx-p">
        <option value="1"${u.centro ? ' selected' : ''}>il centro della scritta (clicca il centro del foro)</option>
        <option value=""${!u.centro ? ' selected' : ''}>l’angolo in basso a sinistra</option></select></label>` : ''}</div>
    <p class="hint" id="tx-hint"></p>
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">${nuova ? 'Metti il testo' : 'Cambia'}</button></div>`, close => {
    $('#modal').classList.add('laterale');           // di lato: la scritta in prova sul foro si vede
    if (at && SK) setTimeout(() => scostaDallaFinestra([skToWorld(at)]), 0);   // 03/11: e il punto non finisce sotto la finestra
    const chiudi = () => { if (SK) { SK.provaTesto = null; drawRubber(); } close(); };
    $('#m-no').onclick = chiudi;
    const leggi = () => ({ text: $('#tx-t').value, h: $('#tx-h').value.trim().replace(',', '.'), angle: ($('#tx-a').value.trim() || '0').replace(',', '.'),
      come: $('#tx-c').value, centro: nuova ? !!$('#tx-p').value : u.centro });
    const spiega = () => { $('#tx-hint').textContent = ($('#tx-c').value
      ? 'Lettere stencil a contorno chiuso, coi ponticelli (le isole di O, A, B… non cadono): poi «Togli materiale».'
      : 'Il laser lo segna in una passata (lettere a tratto singolo): poi «Marca col laser».') +
      ' L’altezza è quella delle maiuscole; la scritta la vedi già al suo posto.'; };
    let t = null;
    const aggiorna = () => { spiega(); clearTimeout(t); t = setTimeout(() => provaTesto(leggi(), at), 150); };
    for (const id of ['#tx-t', '#tx-h', '#tx-a']) $(id).addEventListener('input', aggiorna);
    for (const id of ['#tx-c', '#tx-p']) $(id)?.addEventListener('change', aggiorna);
    aggiorna();
    // una volta sola: Invio nella casella e l'Invio della finestra (= «Metti il testo») mettevano la scritta due
    // volte, una sopra l'altra (02/11, porta ugelli: poi «Togli materiale» si rifiutava)
    let fatto = false;
    const vai = () => {
      if (fatto) return;
      const v = leggi();
      if (!v.text.trim()) { toast('Scrivi il testo.', 'err'); return; }
      fatto = true;
      ok(v, chiudi);
      if (SK) { SK.provaTesto = null; if (SK.tool === 'text') provaTesto(v); }
    };
    $('#m-ok').onclick = vai;
    $('#tx-t').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); ev.stopPropagation(); vai(); } };
    $('#tx-t').focus(); $('#tx-t').select();          // 04/11 (percorso C): scrivendo «1.2» sopra «1.0» viene 1.2, non «1.21.0»
  });
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
  if (SK.tool === 'arcr' && !SK.pick) { arcrScritto(v); return; }
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
    eliminaNelloSketch(ids);
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
  // 04/11 (occhio): cosa cliccare lo dice già la barra «prossimo passo» sotto; qui solo cosa scrivere
  if (P?.what === 'offset') return 'Distanza dell’offset';
  if ((P?.what === 'copy' || P?.what === 'move') && P.base) return 'Distanza (nella direzione del mouse)';
  if (P) return null;
  if (SK.tool === 'polygon' && !SK.pts.length) return 'Numero di lati';
  if (SK.tool === 'arcr') return SK.arcR ? 'Raggio dell’arco' : null;
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
  const extra = $('#sk-cmd-extra'), vuole = testo && SK?.tool === 'arcr' && !SK.pick ? 'arcr' : '';
  if (extra && extra.dataset.cosa !== vuole) { extra.dataset.cosa = vuole; extra.innerHTML = vuole ? arcrScelte() : ''; }
  if (!testo) { if (document.activeElement === inp) inp.blur(); return; }
  misuraSkFoot();
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
    P.stage = 'side'; P.mouse = skPick(ev); P.schermo = [ev.clientX, ev.clientY];
    drawSketch(); offHelp(); offPreview();
    return;
  }
  // il clic dove stava già il mouse: lo stesso punto dell'anteprima a video (la vista intanto poteva muoversi:
  // una finestra a 10 dai bordi diventava un contorno a 10 fuori dai bordi, e Togli materiale tagliava la parete)
  const fermo = P.schermo && P.mouse && P.schermo[0] === ev.clientX && P.schermo[1] === ev.clientY;
  const punto = fermo ? P.mouse : skPick(ev);
  if (!punto) return;
  const sid = SK.sid, ids = P.ids, d = P.dist;
  P.schermo = null;
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
  if (act === 'delete') { SK.sel.clear(); eliminaNelloSketch(ids); return; }
  if (act === 'constr') {
    const tutte = ids.every(id => (SK.v.lines.find(l => l.id === id) || SK.v.circles.find(c => c.id === id))?.construction);
    inCoda(async () => { await apply(await call('sketch_construction', sid, ids, !tutte)); });
    return;
  }
  if (act === 'scritte') {
    const cerchi = ids.filter(id => SK.v.circles.some(c => c.id === id));
    if (!cerchi.length) { toast('Seleziona i fori (cerchi) sotto cui scrivere: clic, Maiusc+clic per aggiungerne.', 'err'); return; }
    scritteSottoFori(sid, cerchi);
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
        <p class="hint tutta-riga">Il diametro del cerchio diventa quello del preforo (es. M6 → Ø5). La filettatura compare nell’albero.</p></div>
      <div class="form" id="h-ins"><label>Codice inserto<input class="field" id="h-cod" value="${esc(h.codice || '')}" placeholder="es. dal catalogo del fornitore"></label>
        <label>Ø foro (mm, da catalogo)<input class="field" id="h-Di" value="${esc(h.tipo === 'inserto' ? String(h.D).replace('.', ',') : '')}"></label>
        <p class="hint tutta-riga">Il cerchio prende il diametro del foro; gli inserti compaiono nell’albero col loro codice.</p></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Usa questo tipo</button></div>`, close => {
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
    // 03/11: la finestra di lato (non copre il disegno) e le copie in anteprima mentre scrivi, prima di confermare
    const v0 = SK.lastSerie || { c: '3', px: '50', r: '1', py: '50' };
    modal(`<h3>Serie</h3><p class="hint">Colonne verso destra e righe verso l’alto, originale compreso. Tratteggiate, le copie come verranno. I passi diventano misure (px, py): li cambi dopo e la serie segue.</p>
      <div class="form"><label>Colonne<input class="field" id="p-c" value="${esc(v0.c)}"></label><label>Passo X (mm)<input class="field" id="p-px" value="${esc(v0.px)}"></label>
      <label>Righe<input class="field" id="p-r" value="${esc(v0.r)}"></label><label>Passo Y (mm)<input class="field" id="p-py" value="${esc(v0.py)}"></label></div>
      <p class="fo-frase" id="p-frase"></p>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Crea serie</button></div>`, close => {
      $('#modal').classList.add('laterale');
      const leggi = () => ({ c: $('#p-c').value.trim(), px: $('#p-px').value.trim(), r: $('#p-r').value.trim(), py: $('#p-py').value.trim() });
      const nn = x => parseFloat(String(x).replace(',', '.'));
      const prova = () => {
        const v = leggi(), c = Math.round(nn(v.c)), r = Math.round(nn(v.r)), px = nn(v.px), py = nn(v.py);
        const va = c >= 1 && r >= 1 && c * r >= 2 && (c === 1 || px) && (r === 1 || py) && c * r <= 400;
        SK.serieProva = va ? { ids, c, r, px: px || 0, py: py || 0 } : null;
        $('#p-frase').textContent = va ? `${c * r} in tutto (${c} × ${r}), originale compreso` : 'Scrivi colonne, righe e passi con i numeri.';
        $('#m-ok').disabled = !va;
        drawRubber();
        if (va) scostaDallaFinestra(serieMondo(SK.serieProva));
      };
      const chiudi = () => { if (SK) { SK.serieProva = null; drawRubber(); } close(); };
      $('#modal-box .form').addEventListener('input', prova);     // sul contenuto: la cornice della finestra resta per le altre
      $('#m-no').onclick = chiudi;
      $('#m-ok').onclick = () => { const v = leggi(); SK.lastSerie = v; chiudi();
        inCoda(async () => { await apply(await call('sketch_pattern', sid, ids, v.c, v.px, v.r, v.py)); }); };
      $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter' && !$('#m-ok').disabled) $('#m-ok').click(); if (ev.key === 'Escape') chiudi(); };
      prova();
      $('#p-c').select();
    });
    return;
  }
}
// i punti (nel 3D) delle copie della serie in prova: per tenerle fuori da sotto la finestra
function serieMondo(P) {
  const out = [];
  for (const c of SK.v.circles) if (P.ids.includes(c.id)) for (let j = 0; j < P.r; j++) for (let i = 0; i < P.c; i++) {
    out.push(skToWorld([c.xc[0] + i * P.px + c.r, c.xc[1] + j * P.py]), skToWorld([c.xc[0] + i * P.px - c.r, c.xc[1] + j * P.py]));
  }
  for (const l of SK.v.lines) if (P.ids.includes(l.id)) for (let j = 0; j < P.r; j++) for (let i = 0; i < P.c; i++) {
    out.push(skToWorld([l.xa[0] + i * P.px, l.xa[1] + j * P.py]), skToWorld([l.xb[0] + i * P.px, l.xb[1] + j * P.py]));
  }
  return out;
}
// la finestra di lato non deve coprire il punto su cui lavori (03/11: la finestra del testo copriva il foro, la
// serie le copie): se ci finisce sotto, il disegno scorre a sinistra quanto basta. Torna com'era alla chiusura
function scostaDallaFinestra(punti) {
  const box = document.querySelector('#modal.laterale .modal-box');
  if (!box || !punti.length) return;
  const b = box.getBoundingClientRect();
  const gia = camera.view?.enabled ? camera.view.offsetX : 0;
  let destra = -Infinity;
  for (const p of punti) {
    const q = aSchermo(p.clone ? p.clone() : v3(p));
    if (q && q[1] > b.top - 30 && q[1] < b.bottom + 30) destra = Math.max(destra, q[0]);
  }
  const dx = destra - (b.left - 40);
  if (!(dx > 0)) return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  camera.setViewOffset(w, h, gia + dx, 0, w, h);
  ridisegna();
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
  }, { stretta: true });
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
      <label class="check"><input type="checkbox" id="st-c" checked> Collega i nodi con traversi</label>
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
    conAnteprima('create_from_sketch', () => [sid, 'structure', { profile: $('#st-p').value.trim(), group: $('#st-g').value.trim(),
      copies: $('#st-n').value.trim(), distance: $('#st-d').value.trim(), side: $('#st-s').value, connect: $('#st-c').checked,
      connect_profile: $('#st-cp').value.trim(), connect_group: $('#st-cg').value.trim() }]);
    $('#modal-box').onkeydown = ev => { if (ev.key === 'Enter') $('#m-ok').click(); if (ev.key === 'Escape') close(); };
  });
}

// 29/10, «anteprime rapide per ogni lavorazione, che chiunque capisca cosa sta facendo»: i comandi che prima partivano
// subito (taglio, linguetta, flangia sul contorno, scritta) e la piega su linea si provano sul pezzo. Il risultato in
// azzurro (quello che si toglie in arancio), in rosso se non si può; sotto una frase che dice cosa succede.
// Invio conferma, Esc annulla; la piega ha le sue scelte sul pezzo (angolo, verso, l'altra parte)
let PROVA = null;
function provaSulPezzo(o) {
  provaVia();
  const b = document.createElement('div');
  b.id = 'prova-barra';
  b.innerHTML = `<span class="pallino"></span><span class="frase"><b></b><small></small></span><span class="sep"></span>
    <span class="tasti"><button class="btn ${o.togli ? 'danger pieno' : 'primary'}" id="pr-ok">${esc(o.conferma || (o.togli ? 'Togli' : 'Conferma'))} <kbd>Invio</kbd></button><button class="btn" id="pr-no">Annulla <kbd>Esc</kbd></button>${o.altro ? '<button class="btn" id="pr-altro" title="Tutte le opzioni">⋯</button>' : ''}</span>`;
  // 04/11: la barra sta dentro la vista, al posto della barra Inquadra/Quote/Tema (prima le stava sopra); i colori dicono
  // lo stato: grigio mentre calcola, verde si può fare, rosso no. «Togli» è rosso pieno
  if (o.togli) b.classList.add('togli');
  view.appendChild(b);
  document.body.classList.add('in-prova');
  PROVA = { ...o, el: b, r: null };
  const stato = document.createElement('span');            // dove l'anteprima scrive come è andata (la frase lo dice)
  const rifai = () => {
    if (!PROVA) return;
    b.querySelector('.frase b').textContent = o.frase();
    b.classList.add('calcolo');
    anteprima(o.metodo, o.argomenti, stato, { vista: SK ? 'iso' : undefined, frase: true, dopo: r => {
      if (!PROVA) return;
      const va = r.ok || !!o.accetta?.(r);
      PROVA.r = { ...r, ok: va };
      b.classList.remove('calcolo');
      b.classList.toggle('no', !va); b.classList.toggle('si', va);
      b.querySelector('.frase b').textContent = va ? o.frase(r) : 'Così non si può fare';
      b.querySelector('.frase small').textContent = va ? (o.sotto ? o.sotto(r) : '') : (r.message || '');
      $('#pr-ok').disabled = !va;
      // Invio (o Conferma) premuto mentre l'anteprima si calcolava: appena è pronta si fa
      if (PROVA.aspetta) { PROVA.aspetta = false; if (va) provaConferma(); }
    } });
  };
  PROVA.rifai = rifai;
  $('#pr-ok').onclick = () => provaConferma();
  $('#pr-no').onclick = () => provaVia();
  if (o.altro) $('#pr-altro').onclick = () => { provaVia(); o.altro(); };
  o.quote?.(rifai);
  rifai();
}
function provaVia() {
  if (!PROVA) return;
  PROVA.el.remove();
  document.body.classList.remove('in-prova');
  togliQuote();
  PROVA = null;
  anteprimaVia();
}
function provaConferma() {
  if (!PROVA) return;
  if (!PROVA.r) {
    // 03/11: l'anteprima non è ancora pronta: prima Invio non faceva niente. Lo si dice, e appena è pronta si fa
    PROVA.aspetta = true;
    PROVA.el.querySelector('.frase small').textContent = 'Sto calcolando… lo faccio appena è pronto';
    return;
  }
  if (!PROVA.r.ok) return;
  const fai = PROVA.fai;
  provaVia();
  fai();
}
window.addEventListener('keydown', e => {
  if (!PROVA || e.target.closest?.('input, textarea')) return;
  if (e.key === 'Enter') { e.preventDefault(); e.stopImmediatePropagation(); provaConferma(); }
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); provaVia(); }
}, true);
// 29/10, «il conferma del togli materiale è fastidioso»: taglio, linguetta, flangia sul contorno e scritta si fanno
// subito (Ctrl+Z se non andava). La barra di prova, rossa col motivo, compare solo quando non si può fare
// prima: cosa è già successo (le copie doppie tolte), detto nello stesso messaggio del comando rifatto
function subitoOProva(o, chiama, okMsg, prima = '') {
  inCoda(async () => {
    togliRossi();
    const r = await chiama();
    if (r?.ok) { if (await apply(r, prima || okMsg || r.message)) exitSketch(); }
    else if (r && !r.cancelled) {
      provaSulPezzo(o);
      // 03/11: «due contorni si sovrappongono» dice anche quali (in rosso) e, se sono doppioni, «Tienine una»
      if (SK && /si sovrappongono/.test(r.message || '')) {
        const sid = SK.sid, a = o.argomenti?.() || [];
        // «Tienine una» rifà subito il comando: lo si dice prima (nella scheda) e dopo (nel messaggio)
        const [cosa, fatto] = o.metodo === 'sheet_tab' ? ['la linguetta', 'fatta la linguetta'] : o.metodo === 'contour_flange' ? ['la piega', 'fatta la piega']
          : a[1] === 'mark' ? ['la scritta', 'fatta la scritta'] : ['il taglio', 'fatto il taglio'];
        await mostraSovrapposti(sid, tolte => subitoOProva(o, chiama, okMsg, `${tolte} e ${fatto}.`), cosa);
      }
    }
  });
}
// ------------------------------------------------------------- «Due contorni si sovrappongono»: dove, e come uscirne (03/11)
// I due contorni in rosso sul disegno; se sono cose disegnate due volte (la scritta messa due volte) «Tienine una»
// toglie le copie e si riprova il taglio. Prima l'errore non diceva quali, e le copie a video non si vedevano.
const skRossi = new THREE.Group();
scene.add(skRossi);
const SK_ROSSO = new THREE.MeshBasicMaterial({ color: 0xE5484D, side: THREE.DoubleSide, depthTest: false });
function togliRossi() {
  skRossi.traverse(o => o.geometry?.dispose()); skRossi.clear();
  document.getElementById('sovr-card')?.remove();
  ridisegna();
}
async function mostraSovrapposti(sid, rifai, cosa = 'il taglio') {
  const r = await call('sketch_sovrapposti', sid);
  if (!r.ok || !SK || SK.sid !== sid || (!r.contorni?.length && !r.doppioni)) return;
  togliRossi();
  for (const c of r.contorni) skRossi.add(fatLine(c, 4, SK_ROSSO));
  ridisegna();
  const box = document.createElement('div');
  box.id = 'sovr-card';
  box.innerHTML = `<button class="ec-x" title="Chiudi">×</button><h5>${r.doppioni ? 'Disegnato due volte' : 'Due contorni si sovrappongono'}</h5>
    <p>${esc(rifai ? r.frase.replace('«Tienine una» toglie le copie in più.', `«Tienine una» toglie le copie in più e rifà subito ${cosa} (Annulla rimette tutto com’era).`) : r.frase)}</p>
    <div class="ec-sol">${r.doppioni ? `<button class="btn primary" data-tieni title="Toglie le copie in più e rifà subito ${esc(cosa)}">Tienine una</button>` : ''}
    <button class="btn" data-mostra>Mostrami dove</button></div>`;
  document.body.appendChild(box);
  box.querySelector('.ec-x').onclick = togliRossi;
  box.querySelector('[data-mostra]').onclick = () => {
    const pts = r.contorni.flat().map(skToWorld);
    if (pts.length) fitSketch(false, pts);
  };
  box.querySelector('[data-tieni]')?.addEventListener('click', () => {
    togliRossi(); provaVia();
    inCoda(async () => {
      const t = await call('sketch_togli_doppioni', sid);
      const tolte = (t.message || '').replace(/:.*$/, '');            // «Tolta 1 copia doppia»
      if (await apply(t, rifai ? `${tolte}: rifaccio ${cosa}…` : t.message) && rifai) rifai(tolte);
    });
  });
}

// la piega su una linea dello sketch, provata sul pezzo: 90° in su, la parte piccola; le scelte sono quote sulla linea
function provaPiega() {
  const l = SK.v.lines.find(x => !x.ref && !x.construction && !x.xray);
  const pa = SK.v.points.find(p => p.id === l.a), pb = SK.v.points.find(p => p.id === l.b);
  const mezzo = v3(pa.xyz).lerp(v3(pb.xyz), 0.5);
  const P = { ang: '90', dir: 'up', flip: false };
  const sid = SK.sid;
  provaSulPezzo({
    metodo: 'sheet_fold', argomenti: () => [sid, P.ang, P.dir, P.flip, null],
    frase: r => (r?.message?.includes('linguetta') ? `Piega la linguetta ${P.dir === 'up' ? 'in su' : 'in giù'} di ${virgola(P.ang)}°`
      : `Piega ${P.dir === 'up' ? 'in su' : 'in giù'} di ${virgola(P.ang)}° ${P.flip ? 'la parte più grande' : 'la parte più piccola'}`),
    sotto: () => 'Lo sviluppo resta quello disegnato · la linea è lo spigolo esterno della piega',
    fai: () => inCoda(async () => { const r = await call('sheet_fold', sid, P.ang, P.dir, P.flip, null); if (await apply(r)) exitSketch(); }),
    altro: () => makeDialog('fold_finestra'),
    quote: rifai => {
      const metti = () => {
        togliQuote();
        const qa = quota(mezzo.clone(), `${virgola(P.ang)}°`, { num: P.ang, dy: -40, titolo: 'Angolo della piega',
          scelte: [[45, '45°'], [90, '90°'], [120, '120°'], [135, '135°']], libero: 'altro…',
          sceglie: v => { P.ang = String(v); metti(); rifai(); } });
        const qv = quota(mezzo.clone(), '⇅', { blu: true, dopo: qa, titolo: `Verso: ${P.dir === 'up' ? 'in su' : 'in giù'} · clic per girarla`,
          clic: () => { P.dir = P.dir === 'up' ? 'down' : 'up'; metti(); rifai(); } });
        quota(mezzo.clone(), '↔', { blu: true, dopo: qv, titolo: P.flip ? 'Si piega la parte più grande · clic: la più piccola' : 'Si piega la parte più piccola · clic: l’altra',
          clic: () => { P.flip = !P.flip; metti(); rifai(); } });
      };
      metti();
    },
  });
}
function makeDialog(kind) {
  if (kind === 'structure') { structureDialog(); return; }
  if (kind === 'tubi') { faiTubiDialog(); return; }
  if (kind === 'cut' && SK.v.on_tube) { lavorazioneTuboDialog(); return; }
  if (kind === 'tab') {
    const sid = SK.sid;
    subitoOProva({ metodo: 'sheet_tab', argomenti: () => [sid], frase: r => r?.frase || 'Aggiunge materiale nel piano della faccia',
      sotto: () => 'Stesso spessore della lamiera · nello sviluppo si aggiunge anche lì',
      fai: () => inCoda(async () => { if (await apply(await call('sheet_tab', sid))) exitSketch(); }) }, () => call('sheet_tab', sid));
    return;
  }
  if (kind === 'contour') {
    const sid = SK.sid;
    subitoOProva({ metodo: 'contour_flange', argomenti: () => [sid], frase: r => r?.frase || 'Piega lungo il contorno disegnato',
      sotto: () => 'La lamiera segue la linea disegnata, con le pieghe dove la linea gira',
      fai: () => inCoda(async () => { if (await apply(await call('contour_flange', sid))) exitSketch(); }) }, () => call('contour_flange', sid));
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
      conAnteprima('create_from_sketch', () => [sid, 'revolve', { angle: $('#rv-a').value.trim() || '360', togli: $('#rv-t')?.checked ? 1 : '' }]);
    });
    return;
  }
  if (kind === 'mark') {
    const sid = SK.sid;
    subitoOProva({ metodo: 'create_from_sketch', argomenti: () => [sid, 'mark', {}], frase: r => r?.frase || 'Scrive col laser sul pezzo',
      sotto: () => 'Il laser segna senza tagliare · nel DXF su un livello a parte',
      fai: () => inCoda(async () => { const r = await call('create_from_sketch', sid, 'mark', {}); if (await apply(r, r.message)) exitSketch(); }) }, () => call('create_from_sketch', sid, 'mark', {}));
    return;
  }
  if (kind === 'cut') {
    const sid = SK.sid;
    subitoOProva({ metodo: 'create_from_sketch', argomenti: () => [sid, 'cut', {}], togli: true, conferma: 'Togli materiale', frase: r => r?.frase || 'Toglie dal pezzo quello che hai disegnato',
      sotto: () => 'In arancio quello che va via · nello sviluppo è il contorno che taglia il laser',
      fai: () => inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'cut', {}), 'Tagliato.')) exitSketch(); }) },
      () => call('create_from_sketch', sid, 'cut', {}), 'Tagliato.');
    return;
  }
  if (kind === 'fold' || kind === 'fold_finestra') {
    // più linee = pieghe in serie (calandratura a colpi, "bumping"): si scrive l'angolo totale, si divide per i colpi
    const n = SK.v.lines.filter(l => !l.ref && !l.construction && !l.xray).length;
    const serie = n > 1;
    if (kind === 'fold' && n === 1) { provaPiega(); return; }     // 29/10: senza finestra, le scelte sul pezzo
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
      conAnteprima('sheet_fold', () => [SK.sid, serie ? String(colpo() ?? '') : $('#m-ang').value.trim(), $('#m-dir .on').dataset.v,
        !serie && $('#m-flip').checked,
        !serie && $('#m-colpi').value.trim() ? { colpi: $('#m-colpi').value.trim(), raggio: $('#m-rg').value.trim() } : null]);
    });
    return;
  }
  if (kind === 'profilo') {
    // profilo estruso in lamiera: gli archi diventano colpi (bumping)
    const sid = SK.sid, BD = S?.bend_default || {};
    const archi = SK.v.arcs.filter(a => !a.construction && !a.ref).length;
    // 02/11: sullo sketch di un profilo già fatto la finestra riparte dai suoi valori (e lo cambia)
    call('profilo_valori', sid).then(rv => { const prima = rv?.valori || null;
    modal(`<h3>${prima ? 'Cambia il profilo in lamiera' : 'Estrudi in lamiera'}</h3>
      <p class="hint">Il profilo disegnato (aperto) diventa lamiera piegata: ogni spigolo è una piega${archi ? `, ogni arco (qui ${archi}) si fa a colpi (bumping) o calandrato` : ''}, col raggio del punzone.</p>
      ${archi ? `<div class="sub">Gli archi si fanno…</div>
      <div class="choice" id="pf-archi"><button type="button" data-c="0" class="${prima?.calandra ? '' : 'on'}"><b>a colpi</b><small>con la piegatrice (bumping)</small></button>
        <button type="button" data-c="1" class="${prima?.calandra ? 'on' : ''}"><b>calandrati</b><small>lisci, col raggio disegnato</small></button></div>` : ''}
      <div class="sub">La linea che hai disegnato è…</div>
      <div class="choice" id="pf-lato"><button type="button" data-gira="0"><b>l’interno</b> della lamiera<small>lo spessore va verso fuori</small></button>
        <button type="button" data-gira="1"><b>l’esterno</b> della lamiera<small>lo spessore va verso dentro</small></button></div>
      <div class="ff"><label>Lunghezza dell’estrusione (larghezza della fascia)<span class="inp"><input class="field" id="pf-L" value="1000"><i>mm</i></span></label>
        <label>Spessore<span class="inp"><input class="field" id="pf-sp" value="${esc(virgola(S?.parameters?.find?.(p => p.name === 'sp')?.value) || '3')}"><i>mm</i></span></label></div>
      ${archi ? `<div class="ff" id="pf-colpi-riga"${prima?.calandra ? ' style="display:none"' : ''}><label>Colpi per ogni arco<span class="inp"><input class="field" id="pf-colpi" placeholder="1 ogni 20 mm" value="${esc(virgola(prima?.colpi) || '')}"></span></label><span></span></div>` : ''}
      <div class="ff"><label>Raggio del punzone<span class="inp"><input class="field" id="pf-r" value="${esc(virgola(BD.radius) || '')}"><i>mm</i></span></label>
        <label>Fattore K<span class="inp"><input class="field" id="pf-k" value="${esc(virgola(BD.k) || '')}"></span></label></div>
      <p class="hint">Il 3D si gira trascinando col mouse e si ingrandisce con la rotella, anche con questa finestra aperta.</p>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok" disabled title="Prima scegli: interno o esterno">${prima ? 'Cambia' : 'Estrudi in lamiera'}</button></div>`, close => {
      // 30/10, Stefano: «non mi chiede se il profilo è l'interno o l'esterno»: si sceglie per forza, e l'anteprima lo fa vedere
      let gira = null, avviata = false;
      const calandra = () => !!$('#pf-archi .on[data-c="1"]');
      const valori = () => ({ lunghezza: $('#pf-L').value.trim(), spessore: $('#pf-sp').value.trim(), colpi: calandra() ? '' : ($('#pf-colpi')?.value.trim() || ''),
        raggio: $('#pf-r').value.trim(), k: $('#pf-k').value.trim(), gira: !!gira, calandra: calandra() });
      $('#m-no').onclick = close;
      document.querySelectorAll('#pf-archi button').forEach(b => {
        b.onclick = () => {
          document.querySelectorAll('#pf-archi button').forEach(x => x.classList.toggle('on', x === b));
          $('#pf-colpi-riga').style.display = calandra() ? 'none' : '';
          if (avviata) $('#pf-L').dispatchEvent(new Event('input'));
        };
      });
      if (prima) {
        if (prima.lunghezza != null) $('#pf-L').value = virgola(prima.lunghezza);
        if (prima.spessore != null) $('#pf-sp').value = virgola(prima.spessore);
        if (prima.raggio != null) $('#pf-r').value = virgola(prima.raggio);
        if (prima.k != null) $('#pf-k').value = virgola(prima.k);
      }
      document.querySelectorAll('#pf-lato button').forEach(b => {
        b.onclick = () => {
          gira = b.dataset.gira === '1';
          document.querySelectorAll('#pf-lato button').forEach(x => x.classList.toggle('on', x === b));
          $('#m-ok').disabled = false; $('#m-ok').title = '';
          if (!avviata) { avviata = true; conAnteprima('create_from_sketch', () => [sid, 'profilo', valori()]); }
          else $('#pf-L').dispatchEvent(new Event('input'));
        };
      });
      $('#m-ok').onclick = () => {
        if (gira === null) return;
        const v = valori();
        close();
        inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'profilo', v))) exitSketch(); });
      };
      $('#modal').classList.add('laterale');                // il 3D resta libero già prima della scelta
      if (SK) controls.enableRotate = true;
      if (prima) $(`#pf-lato button[data-gira="${prima.gira ? 1 : 0}"]`).click();   // già scelto: anteprima subito
    });
    });
    return;
  }
  if (kind === 'louver' || kind === 'dimple') {
    const per = kind === 'louver';
    modal(`<h3>${per ? 'Persiane' : 'Imbutiture'}</h3>
      <p class="hint">${per ? 'Ogni linea disegnata è il bordo aperto di una persiana; la cappa sale verso sinistra (guardando dal primo al secondo punto).' : 'Ogni cerchio disegnato è un’imbutitura di quel diametro, verso fuori dalla faccia.'}</p>
      <div class="form">${per ? '<label>Larghezza (mm)<input class="field" id="m-w" value="8"></label><label>Altezza (mm)<input class="field" id="m-h" value="4"></label>'
        : '<label>Profondità (mm)<input class="field" id="m-h" value="3"></label>'}</div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">${per ? 'Fai le persiane' : 'Fai le imbutiture'}</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => {
        const v = per ? { width: $('#m-w').value.trim(), height: $('#m-h').value.trim() } : { depth: $('#m-h').value.trim() };
        const sid = SK.sid; close();
        inCoda(async () => { if (await apply(await call('create_from_sketch', sid, kind, v))) exitSketch(); });
      };
      conAnteprima('create_from_sketch', () => [SK.sid, kind, per ? { width: $('#m-w').value.trim(), height: $('#m-h').value.trim() } : { depth: $('#m-h').value.trim() }]);
    });
    return;
  }
  if (kind === 'boss') {
    modal(`<h3>Estrudi dalla faccia</h3><div class="form"><label>Di quanto (mm)<input class="field" id="m-d" value="10"></label></div>
      <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">Estrudi</button></div>`, close => {
      $('#m-no').onclick = close;
      $('#m-ok').onclick = () => { const sid = SK.sid, d = $('#m-d').value.trim(); close();
        inCoda(async () => { if (await apply(await call('create_from_sketch', sid, 'boss', { distance: d }))) exitSketch(); }); };
      conAnteprima('create_from_sketch', () => [SK.sid, 'boss', { distance: $('#m-d').value.trim() }]);
    });
    return;
  }
  const lam = kind === 'sheet';
  modal(`<h3>${lam ? 'Crea lamiera dal contorno' : 'Crea piastra dal contorno'}</h3>
    <div class="form"><label>Spessore (mm)<input class="field" id="m-sp" value="${lam ? 2 : 5}"></label>
    ${lam ? `<label>Raggio interno di piega<input class="field" id="m-r" placeholder="dato della piegatrice"></label>
    <label>Fattore K<input class="field" id="m-k" placeholder="dato della piegatrice"></label>` : ''}</div>
    ${lam ? '<p class="hint">Raggio e K servono solo quando aggiungi le flange; se li lasci vuoti te li chiederà la scheda Lamiera.</p>' : ''}
    <div class="acts"><button class="btn" id="m-no">Annulla</button><button class="btn primary" id="m-ok">${lam ? 'Crea la lamiera' : 'Crea la piastra'}</button></div>`, close => {
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
    conAnteprima('create_from_sketch', () => {
      const v = { thickness: $('#m-sp').value.trim() };
      if (lam) { v.radius = $('#m-r').value.trim(); v.k = $('#m-k').value.trim(); }
      return [SK.sid, kind, v];
    });
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
  const tx = h && (SK.v.texts || []).find(t => t.id === h);
  if (tx) {                                       // 30/10: doppio clic su una scritta = cambiala (il suo punto resta fermo)
    const sid = SK.sid, pa = SK.v.points.find(q => q.id === tx.anchor_id);
    const at = pa ? [...skToLocal(v3(pa.xyz))].slice(0, 2) : null;
    finestraTesto({ valori: { text: tx.text, h: tx.h, angle: tx.angle, come: tx.stencil || '', centro: tx.centrato }, at, nuova: false,
      ok: (v, close) => { close(); inCoda(async () => { await apply(await call('sketch_edit_text', sid, tx.id, v.text, v.h, v.angle, v.come || null)); }); } });
    return;
  }
  if (!h || !SK.v.lines.some(l => l.id === h)) return;
  if (SK.pick?.stage === 'sel') { for (const x of chainOf(h)) SK.sel.add(x); } else SK.sel = chainOf(h);
  drawSketch();
});

// ===================================================================== barra a schede (stile SolidCraft)
let schedaPrima = 'lamiera';
// Esporta: un pulsante solo con il menu; si vedono le voci che hanno senso per il pezzo aperto
// notte 03/11: gli stessi nomi di «Prepara» e delle conferme (DXF di taglio salvato, Tabella pieghe salvata…)
const VOCI_ESPORTA = [['drawings', 'Tavole con cartiglio (PDF, DXF)…'], ['export_dxf', 'DXF di taglio, per il laser…'],
  ['export_bendtable', 'Tabella pieghe, per la piegatrice…'], ['export_step', 'STEP, per un altro programma 3D…'],
  ['export_bom', 'Distinta in Excel…']];
document.querySelectorAll('.rgroup[data-esporta]').forEach(g => g.insertAdjacentHTML('beforebegin',
  `<div class="rgroup"><div class="rbtns"><button class="rb" data-cmd="misura" title="Quota: due clic = distanza; clic sul bordo di un foro = diametro (M)"><img src="icons/dimension.svg" alt=""><span>Quota</span></button><button class="rb" data-cmd="misura_angolo" title="Angolo: clic su un lato, sul vertice e sull’altro lato"><img src="icons/plane_angle.svg" alt=""><span>Angolo</span></button><button class="rb" data-azione="saldatura3d" title="Saldatura: clicca gli spigoli da saldare (si accendono), poi Invio: tipo e misura; i metri vanno in distinta"><img src="icons/saldatura.svg" alt=""><span>Saldatura</span></button></div><div class="rname">Misura</div></div>`));
document.querySelectorAll('.rgroup[data-esporta]').forEach(g => {
  g.innerHTML = `<div class="rbtns"><div class="menu-item rmenu"><button class="rb rb-export" title="Esporta: tavole, DXF di taglio, tabella pieghe, STEP">
    <img src="icons/export.svg" alt=""><span>Esporta ▾</span></button><div class="drop">${VOCI_ESPORTA.map(([c, l]) =>
    `<button data-cmd="${c}">${l}</button>`).join('')}</div></div></div><div class="rname">Esporta</div>`;
});
// 04/11 (cornice): la barra dei comandi su UNA riga. In ogni gruppo restano grandi, con icona e nome, i comandi
// che si usano di più (dai percorsi di lavoro veri); gli altri vanno nel menu del gruppo, coi nomi.
// Nessun comando sparisce: stessi pulsanti (stessi id, data-…, gestori), solo spostati; e si trovano anche in
// «Cerca un comando». Un gruppo senza comandi grandi diventa un pulsante col suo nome e la tendina.
// 04/11 sera: ogni menu dice cosa c'è dentro («Bordi e tagli ▾», «Forme ▾»…), non più quattro «Altro ▾» di fila;
// un menu che avrebbe una voce sola non si fa: quel comando resta grande.
const BARRA_GRANDI = {
  lamiera: ['flange_help', 'foro', 'asola', 'tipo_foro', 'taglia', 'face_help', 'unfold', 'misura'],
  strutture: ['tubonuovo', 'traverso', 'dividi', 'piedi', 'misure', 'tubo', 'giunti', 'misura', 'saldatura3d'],
  piastra: ['foro', 'taglia', 'face_help', 'misure', 'misura'],
  assieme: ['asm_insert', 'asm_viteria', 'appoggia', 'vano', 'asse', 'distanza', 'angolo', 'asm_interf', 'asm_esploso', 'misura'],
  sketch: ['line', 'rect', 'circle', 'arcr', 'arc3', 'text', 'trim', 'fillet', 'pattern', 'dim', 'sk-grid',
    'tubi', 'sheet', 'profilo', 'fold', 'cut', 'tab', 'mark', 'sk-done'],
};
// il nome del menu di ogni gruppo (scheda:gruppo, e :id dell'insieme per «sulla faccia»): parole da officina
const NOMI_MENU = {
  'lamiera:Crea': 'Bordi e tagli', 'lamiera:Disegna': 'Disegna', 'lamiera:Sviluppo': 'Sviluppo', 'lamiera:Misura': 'Angolo, saldatura',
  'strutture:Aggiungi': 'Tappi, sagoma', 'strutture:Misura': 'Misura',
  'piastra:Crea': 'Asole, svasi', 'piastra:Disegna': 'Disegna', 'piastra:Modifica': 'Spigoli', 'piastra:Misura': 'Angolo, saldatura',
  'assieme:Accoppiamenti': 'Accoppiamenti', 'assieme:Misura': 'Angolo, saldatura',
  'sketch:Disegna': 'Forme', 'sketch:Modifica': 'Modifica', 'sketch:Quota': 'Seleziona', 'sketch:Vista': 'Vista',
  'sketch:Fine': 'Crea', 'sketch:Fine:sk-face': 'Pieghe e forme',
};
const chiaveComando = b => b.dataset.cmd || b.dataset.azione || b.dataset.tool || b.dataset.asmTool || b.dataset.act || b.dataset.make || b.id;
function nuovoAltro(nome) {
  const m = document.createElement('div');
  m.className = 'menu-item rmenu ralt';
  m.dataset.nome = nome;
  m.innerHTML = `<button class="ralt-btn" type="button"><i class="ralt-ico" aria-hidden="true"></i><span>${esc(nome)}</span></button>`
    + `<div class="drop"><div class="drop-tit">${esc(nome)}</div></div>`;
  return m;
}
function impaginaBarra() {
  for (const rb of document.querySelectorAll('#ribbon .rbody')) {
    const grandi = new Set(BARRA_GRANDI[rb.dataset.rbody] || []);
    for (const g of rb.querySelectorAll('.rgroup:not([data-esporta])')) {
      const gruppo = g.querySelector('.rname')?.textContent.trim() || 'Altro';
      // ogni insieme che si accende e si spegne da solo (Fine: «crea» o «sulla faccia») ha la sua tendina
      const contenitori = [...g.querySelectorAll('.rset'), g.querySelector('.rbtns')].filter(Boolean);
      for (const c of contenitori) {
        const nome = NOMI_MENU[`${rb.dataset.rbody}:${gruppo}:${c.id}`] || NOMI_MENU[`${rb.dataset.rbody}:${gruppo}`] || gruppo;
        const mio = e => (e.closest('.rset') || c) === c;
        const miei = [...c.querySelectorAll('.rb')].filter(b => !b.closest('.rmenu') && mio(b));
        if (!miei.length) continue;
        let menu = [...c.querySelectorAll('.rmenu')].find(mio);   // c'è già un menu (sulla faccia): uso quello
        let piccoli = miei.filter(b => !grandi.has(chiaveComando(b)));
        if (piccoli.length === 1 && !menu && miei.length > 1) piccoli = [];   // un menu con una voce sola non serve
        if (piccoli.length && !menu) {
          menu = nuovoAltro(nome);
        } else if (menu) {
          const bt = menu.querySelector(':scope > button');
          bt.className = 'ralt-btn'; bt.innerHTML = `<i class="ralt-ico" aria-hidden="true"></i><span>${esc(nome)}</span>`;
          menu.classList.add('ralt'); menu.dataset.nome = nome;
          menu.querySelector('.drop').insertAdjacentHTML('afterbegin', `<div class="drop-tit">${esc(nome)}</div>`);
        }
        for (const b of miei) {
          b.classList.remove('rb-s');
          if (!piccoli.includes(b)) c.appendChild(b);
        }
        if (menu) {
          const drop = menu.querySelector('.drop');
          let dopo = drop.querySelector('.drop-tit');
          for (const b of piccoli) { b.classList.add('rb-m'); dopo.after(b); dopo = b; }
          c.appendChild(menu);
          const voci = [...drop.querySelectorAll('button')].map(b => b.textContent.trim().replace(/…$/, ''));
          menu.querySelector('.ralt-btn').title = nome + ': ' + voci.join(', ');
        }
        for (const col of c.querySelectorAll('.rcol')) if (!col.children.length) col.remove();
      }
    }
  }
  // passando su un altro menu mentre uno è aperto si apre quello (come File, Vista)
  document.querySelectorAll('#ribbon .ralt').forEach(m => m.addEventListener('mouseenter', () => {
    if (document.querySelector('.menu-item.open') && !m.classList.contains('open')) {
      document.querySelectorAll('.menu-item').forEach(x => x.classList.remove('open')); m.classList.add('open');
    }
  }));
}
impaginaBarra();
// il menu del gruppo si vede solo se dentro c'è qualcosa; è acceso se il comando in uso sta lì dentro
function statoAltro() {
  for (const m of document.querySelectorAll('#ribbon .ralt')) {
    const voci = [...m.querySelectorAll('.drop button')];
    const vuoto = voci.length > 0 && voci.every(b => b.hidden);
    if (m.hidden !== vuoto) m.hidden = vuoto;
    const acceso = voci.some(b => b.classList.contains('on') && !b.hidden);
    const bt = m.querySelector('.ralt-btn');
    if (bt.classList.contains('on') !== acceso) bt.classList.toggle('on', acceso);
  }
}
new MutationObserver(statoAltro).observe($('#ribbon'), { subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
statoAltro();
// 04/11 notte (attriti): nessuna barra esce dallo schermo. Se la barra dei comandi non ci sta (1366 px, disegno su
// una faccia…), i comandi grandi che si usano meno passano nel menu del loro gruppo, uno alla volta, finché ci sta;
// allargando la finestra tornano al loro posto. «Esci», i pulsanti blu e i comandi base del disegno non si spostano mai.
// Sono gli stessi pulsanti (stessi id e data-…): li trovano le prove, «Cerca un comando» e i tasti.
const BARRA_CEDE = {
  sketch: ['pattern', 'sk-grid', 'tab', 'arc3', 'mark', 'fillet', 'trim', 'text', 'dim', 'circle', 'rect'],
  lamiera: ['misura', 'unfold', 'tipo_foro', 'asola', 'taglia', 'face_help', 'foro'],
  strutture: ['saldatura3d', 'misura', 'giunti', 'tubo', 'misure', 'piedi', 'dividi'],
  piastra: ['misura', 'misure', 'face_help', 'taglia'],
  assieme: ['misura', 'asm_esploso', 'asm_interf', 'angolo', 'distanza', 'asse', 'asm_viteria'],
};
const BARRA_FERMI = new Set(['sk-done', 'line']);
let barraAdatto = false;
function adattaBarra() {
  barraAdatto = true;
  try {
    // prima tutto torna al suo posto…
    for (const b of document.querySelectorAll('#ribbon .rb[data-ceduto]')) {
      const posto = b._posto;
      delete b.dataset.ceduto; b.classList.remove('rb-m');
      if (posto?.parentNode) posto.replaceWith(b);
    }
    document.querySelectorAll('#ribbon .ralt[data-ceduti]').forEach(m => {
      if (!m.querySelector('.drop button')) m.remove(); else delete m.dataset.ceduti;
    });
    const rb = document.querySelector('#ribbon .rbody:not([hidden])');
    if (!rb || !rb.clientWidth) return;
    // non ci sta: la barra scorre, o il suo ultimo pulsante finisce oltre il bordo della finestra
    const troppo = () => rb.scrollWidth > rb.clientWidth + 1
      || Math.max(0, ...[...rb.querySelectorAll('.rb, .ralt-btn')].filter(b => b.offsetParent && !b.closest('.drop'))
        .map(b => b.getBoundingClientRect().right)) > document.documentElement.clientWidth - 2;
    if (!troppo()) return;
    // …poi si sposta nel menu un comando alla volta, dal meno usato
    const visibile = b => b.offsetParent !== null && !b.closest('.drop');
    const tutti = [...rb.querySelectorAll('.rb')].filter(b => visibile(b) && !b.classList.contains('primary')
      && !BARRA_FERMI.has(chiaveComando(b)) && !b.closest('.rmenu'));
    const ordine = BARRA_CEDE[rb.dataset.rbody] || [];
    const pos = new Map(tutti.map((b, i) => [b, i]));
    const peso = b => { const i = ordine.indexOf(chiaveComando(b)); return i < 0 ? 999 : i; };
    tutti.sort((a, b) => peso(a) - peso(b) || pos.get(b) - pos.get(a));   // fuori elenco: da destra
    for (const b of tutti) {
      if (!troppo()) break;
      const c = b.closest('.rset') || b.closest('.rbtns');
      const gruppo = b.closest('.rgroup')?.querySelector('.rname')?.textContent.trim() || 'Altro';
      let menu = [...c.querySelectorAll('.ralt')].find(m => (m.closest('.rset') || m.closest('.rbtns')) === c);
      if (!menu) {
        const nome = NOMI_MENU[`${rb.dataset.rbody}:${gruppo}:${c.id}`] || NOMI_MENU[`${rb.dataset.rbody}:${gruppo}`] || gruppo;
        menu = nuovoAltro(nome); menu.dataset.ceduti = '1';
        const fine = c.querySelector(':scope > #sk-done');
        c.insertBefore(menu, fine || null);
        menu.addEventListener('mouseenter', () => {
          if (document.querySelector('.menu-item.open') && !menu.classList.contains('open')) {
            document.querySelectorAll('.menu-item').forEach(x => x.classList.remove('open')); menu.classList.add('open');
          }
        });
      }
      b._posto = b._posto || document.createComment('posto');
      b.replaceWith(b._posto);
      b.dataset.ceduto = '1'; b.classList.add('rb-m');
      const tit = menu.querySelector('.drop-tit');
      tit.after(b);                                    // in cima al menu: sono i comandi «quasi grandi»
    }
    for (const m of rb.querySelectorAll('.ralt')) {
      const voci = [...m.querySelectorAll('.drop button')].map(x => x.textContent.trim().replace(/…$/, ''));
      m.querySelector('.ralt-btn').title = m.dataset.nome + ': ' + voci.join(', ');
    }
  } finally {
    statoAltro();
    osservaBarra.takeRecords();
    barraAdatto = false;
  }
}
let barraRaf = 0;
function adattaBarraPoi() { if (!barraRaf) barraRaf = requestAnimationFrame(() => { barraRaf = 0; adattaBarra(); }); }
const osservaBarra = new MutationObserver(() => { if (!barraAdatto) adattaBarraPoi(); });
osservaBarra.observe($('#ribbon'), { subtree: true, attributes: true, attributeFilter: ['hidden'] });
window.addEventListener('resize', adattaBarraPoi);
if (document.fonts?.ready) document.fonts.ready.then(adattaBarraPoi);
adattaBarraPoi();
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
  const conFacce = ['profilo', 'step', 'sezioni'].includes(S?.sheet?.data?.shape_info?.kind);
  // 28/10: una tramoggia (o un profilo, uno STEP) fatta è un pezzo come gli altri: si disegna sulle facce e sullo
  // sviluppo, si fora, si taglia, si aggiunge una linguetta, si piega un bordo libero. Le pieghe della forma invece
  // sono i suoi spigoli (orli, angoli, profilo piegato, persiane restano della lamiera disegnata)
  const suForma = new Set(['face_help', 'flat_sketch', 'flange_help', 'taglia', 'linguetta', 'tipo_foro', 'contorno']);
  document.querySelectorAll('#ribbon .rb[data-cmd]').forEach(b => {
    if (b.dataset.title === undefined) b.dataset.title = b.title || '';
    const no = motivoNo(b.dataset.cmd);
    b.disabled = !!no;
    b.title = no ? `${b.dataset.title} · Non disponibile: ${no}` : b.dataset.title;
    if (b.hasAttribute('data-no-shape')) b.hidden = forma && !(conFacce && suForma.has(b.dataset.cmd));
  });
  document.querySelectorAll('#ribbon .rb[data-serve="lam"]').forEach(b => {
    if (b.dataset.title === undefined) b.dataset.title = b.title || '';
    b.disabled = !S?.sheet?.data; b.title = b.disabled ? `${b.dataset.title} · Non disponibile: prima serve una lamiera` : b.dataset.title;
    if (b.hasAttribute('data-no-shape')) b.hidden = forma && !(conFacce && suForma.has(b.dataset.azione));
  });
  document.querySelectorAll('.rmenu:not(.ralt) .drop [data-cmd]').forEach(b => { b.hidden = !!motivoNo(b.dataset.cmd); });   // Esporta ▾ (non gli «Altro»)
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
  aggiornaModo();
}
// 04/11: il colore di modalità (banda sotto la barra in alto, scheda attiva, pallino del documento, striscia del
// «prossimo passo»): body[data-modo] = lamiera | disegno | tubi | assieme | tavole. I colori stanno in style.css
function aggiornaModo() {
  const scheda = document.querySelector('.rtabs button.on')?.dataset.rtab;
  const m = document.getElementById('tav-ed') ? 'tavole' : SK ? 'disegno' : S?.mode === 'assembly' ? 'assieme'
    : ({ strutture: 'tubi', sketch: 'disegno', assieme: 'assieme' })[scheda] || 'lamiera';
  if (document.body.dataset.modo !== m) document.body.dataset.modo = m;
}
// l'editor delle tavole si apre e si chiude aggiungendo e togliendo #tav-ed: basta guardare i figli di body
new MutationObserver(() => aggiornaModo()).observe(document.body, { childList: true });
// le schede di modalità (Lamiera, Strutture, Piastra, Assieme, Disegno) stanno nella barra in alto, come segmenti
document.querySelector('.rtabs').addEventListener('click', ev => {
  const tab = ev.target.closest('.rtabs button');
  if (tab) { showRibbon(tab.dataset.rtab); if (tab.dataset.rtab !== 'sketch') schedaPrima = tab.dataset.rtab; }
});
$('#ribbon').addEventListener('click', ev => {
  if (ev.target.closest('.ralt .drop button')) ev.target.closest('.ralt').classList.remove('open');
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
  const r = ribbonTabsDentro();
  // 28/10: una scheda sola (Lamiera, Assieme…) non serve a niente da cliccare: via la riga, più spazio alla vista
  const viste = [...document.querySelectorAll('.rtabs button')].filter(b => !b.hidden).length;
  const una = viste <= 1 && !SK;
  if (document.body.classList.contains('una-scheda') !== una) {
    document.body.classList.toggle('una-scheda', una);
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
  }
  return r;
}
function ribbonTabsDentro() {
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
const ICONA_TIPO = { instance: 'box', mate: 'joint', assembly: 'assieme', sketch: 'sketch', sheet: 'lamiera', flange: 'flange', sheet_cut: 'cut', sheet_miter: 'testa', extrude: 'extrude', revolve: 'rivoluzione', hole: 'hole', fillet: 'fillet',
  chamfer: 'chamfer', structure: 'struttura', members: 'tubo', part: 'box', group: 'list', project: 'box' };
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
  const h = 38;                                    // metà del lato del cubo (76 px, 28/10: più grande e leggibile)
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
  let tema = 'chiaro';                             // 04/11: chiaro di partenza (lo scuro resta col pulsante Tema)
  try { tema = localStorage.getItem('steelcad.tema') || 'chiaro'; } catch { /* va bene il predefinito */ }
  try { const imp = await call('impostazioni'); if (imp?.ok && imp.tema) tema = imp.tema; } catch { /* resta quello di prima */ }
  applyTheme(tema === 'scuro');
  introStato('Collego il motore geometrico…', 0.45);
  S = await call('state');
  if (S?.version) { const v = document.querySelector('#intro .intro-versione'); if (v) v.textContent = 'versione ' + S.version; }
  introStato('Preparo l’interfaccia…', 0.7);
  renderPanels();
  tastiNeiSuggerimenti();
  await loadScene();
  setInterval(() => call('autosave'), 60000);
  setTimeout(controllaAggiornamenti, 5000);
  const casa = await call('home_info');
  if (casa.ok && casa.show) await showHome(casa);
  introStato('Pronto', 0.95);
  requestAnimationFrame(loop);
  introFine();
  window.__steelcad = { ready: true, runCmd: id => runCmd(id), nuovo: k => newDialog(k), get state() { return S; }, get sceneVersion() { return sceneVersion; }, get nodes() { return nodes; }, get sketch() { return SK; },
    objs, select, camera, controls, skScreen: xy => skScreen(xy), get mis() { return MIS; }, lineeSpesse: on => { lineeSpesse = on; if (SK) drawSketch(); }, toScreen: p => { const q = v3(p).project(camera); return [(q.x + 1) / 2 * canvas.clientWidth, (1 - q.y) / 2 * canvas.clientHeight]; }, enterSketch, exitSketch, apply, toast, hideHome, foto: p => fotoAnteprima(p), THREE, get bendEdges() { return bendEdges; },
    get look() { return { model: model.visible, flat: flatGroup.visible, work: workGroup.visible && workGroup.children.length > 0 }; } };
  window.__prova = { call, MAN, MINI, renderProps, apriPezzoAssieme, tornaAllAssieme };            // per le prove automatiche dell'interfaccia
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
        } else if (ev.type === 'select') {                 // come un clic sul pezzo (e la sua faccia); pannello = «⋯»
          await select(ev.id, ev.face ?? null);
          if (ev.pannello) tutteLeOpzioni();
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
