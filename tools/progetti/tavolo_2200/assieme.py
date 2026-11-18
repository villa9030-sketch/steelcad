"""Assieme del tavolo: i pezzi al loro posto (fissi), poi una vite TBEI M8 inox con dado in ogni pacco di fori.
uso: assieme.py <cartella dei pezzi> [viti]"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import costruisci as C  # noqa: E402  (solo le misure: non ricostruisce niente)

from app.service import Service  # noqa: E402
from cad_engine import assembly as A  # noqa: E402
from cad_engine.topology.naming import _faces_of  # noqa: E402

CART = Path(sys.argv[1])
VITI = len(sys.argv) > 2 and sys.argv[2] == 'viti'
f = {k: CART / f'{n}.steelcad' for k, n in C.NOMI.items()}

R0_GAMBA = np.array([[0, 0, 1], [0, -1, 0], [1, 0, 0]], dtype=float)
R0_PIEDE = np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]], dtype=float)
G = 40.0
gambe = [(0, (C.X0 + 3, 3, C.GAMBA_Z0)), (1, (C.X0 + C.LS - 3 - G, 3, C.GAMBA_Z0)),
         (2, (C.X0 + C.LS - 3 - G, C.DS - 3 - G, C.GAMBA_Z0)), (3, (C.X0 + 3, C.DS - 3 - G, C.GAMBA_Z0))]
piedi = [(0, (C.X0, 0, 0)), (1, (C.X0 + C.LS - 80, 0, 0)), (2, (C.X0 + C.LS - 80, C.DS - 80, 0)), (3, (C.X0, C.DS - 80, 0))]

s = Service()
assert s.new_assembly('TAVOLO 2200')['ok']
pose = []                                                  # (file, nome, R, T)
for k in ('top', 'mezzo', 'basso'):
    pose.append((f[k], C.NOMI[k], *C.POSE[k]))
pg = A.load_part(f['gamba'])
bbg = pg.shape
import build123d as bd  # noqa: E402
b = bd.Shape.cast(pg.shape).bounding_box()
bb_gamba = ((b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z))
for k, mn in gambe:
    R = C.rz(k) @ R0_GAMBA
    pose.append((f['gamba'], C.NOMI['gamba'], R, C.metti(R, bb_gamba, mn)))
b = bd.Shape.cast(A.load_part(f['piede']).shape).bounding_box()
bb_piede = ((b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z))
for k, mn in piedi:
    R = C.rz(k) @ R0_PIEDE
    pose.append((f['piede'], C.NOMI['piede'], R, C.metti(R, bb_piede, mn)))
for mn in ((0, 0, C.ZP0), (C.L - C.T, 0, C.ZP0)):
    pose.append((f['fianco'], C.NOMI['fianco'], C.R_FIANCO, C.metti(C.R_FIANCO, ((0, 0, 0), (C.DS, C.ZP1 - C.ZP0, C.T)), mn)))
pose.append((f['retro'], C.NOMI['retro'], C.R_RETRO, C.metti(C.R_RETRO, ((0, 0, 0), (C.L, C.ZP1 - C.ZP0, C.T)), (0, C.DS, C.ZP0))))

for file, nome, R, Tv in pose:
    r = s.asm_insert(str(file))
    assert r['ok'], r
    i = s.asm.instances[-1]
    i['R'], i['T'], i['fixed'] = np.asarray(R, float).tolist(), np.asarray(Tv, float).tolist(), True
out = CART / 'TAVOLO 2200.steelcad-asm'
assert s.save(str(out))['ok']
s = Service()
assert s.open(str(out))['ok']
print('pezzi', len(s.asm.instances), 'avvisi', s.asm.warnings, s.asm_errors)
for i in s.asm.instances:
    bb = A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()
    print(' ', i['id'], i['name'].ljust(28), [round(v, 1) for v in (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)])
interf = A.interferences(s.asm, s.asm_parts)
for x in interf:
    print('INTERFERENZA', s.asm.instance(x['a'])['name'], '|', s.asm.instance(x['b'])['name'], round(x['volume'], 1))

# ---------------------------------------------------------------- i fori e i pacchi
fori = []
for i in s.asm.instances:
    part = s.asm_parts[i['file']]
    R, Tv = np.array(i['R']), np.array(i['T'])
    visti = []
    for k, fc in enumerate(_faces_of(part.shape)):
        inf = A.face_info(part, fc)
        if inf['kind'] != 'cilindrica' or abs(2 * inf['r'] - 9) > 1e-3:
            continue
        n = R @ np.array(inf['n']); p = R @ np.array(inf['p']) + Tv
        q = p - n * np.dot(p, n)
        if any(np.linalg.norm(q - v[0]) < 1e-3 and abs(np.dot(p - v[1], n)) < 6 for v in visti):
            continue
        visti.append((q, p)); fori.append({'inst': i['id'], 'face': k, 'p': p, 'n': n / np.linalg.norm(n), 'nome': i['name']})
pacchi, usati = [], set()
for a in fori:
    if id(a) in usati:
        continue
    g = [b for b in fori if np.linalg.norm(np.cross(a['n'], b['n'])) < 1e-4
         and np.linalg.norm(A._perp(b['p'] - a['p'], a['n'])) < 0.05 and abs(np.dot(b['p'] - a['p'], a['n'])) < 12]
    if len({x['inst'] for x in g}) >= 2:
        pacchi.append(g)
        usati.update(id(x) for x in g)
soli = [a for a in fori if id(a) not in usati and 'GAMBA' not in a['nome']]
print('pacchi', len(pacchi), {len({x['inst'] for x in g}) for g in pacchi}, '| fori senza compagno (non gambe):', len(soli))
for a in soli[:10]:
    print('   SOLO', a['nome'], np.round(a['p'], 1))
if not VITI:
    raise SystemExit
centro = np.array([C.L / 2, C.DS / 2, 0.0])
t0 = time.time()
for g in pacchi:
    n = g[0]['n']
    if abs(n[2]) > 0.9:
        verso = np.array([0, 0, 1.0])                       # piedini: testa dentro il ripiano, dado sotto
    else:
        verso = n if np.dot((g[0]['p'] - centro) * [1, 1, 0], n) > 0 else -n      # testa fuori
    g = sorted(g, key=lambda x: -np.dot(x['p'], verso))      # dal piu' esterno
    fa = {'inst': g[0]['inst'], 'face': g[0]['face']}
    fb = next({'inst': x['inst'], 'face': x['face']} for x in reversed(g) if x['inst'] != g[0]['inst'])   # il piu' interno
    r = s.asm_bullone(fa, fb, {'tipo': 'vite_tbei', 'misura': 'M8', 'dado': True, 'inox': True, 'verso': verso.tolist()})
    assert r['ok'], (r.get('message'), g[0]['nome'], np.round(g[0]['p'], 1))
print('viti messe in', round(time.time() - t0), 's; avvisi', len(s.asm.warnings), s.asm.warnings[:3])
viti = [i for i in s.asm.instances if i['name'].startswith('TBEI')]
dadi = [i for i in s.asm.instances if i['name'].startswith('Dado')]
centro3 = np.array([C.L / 2, C.DS / 2, 0.0])
buone = 0
for v in viti:
    Tv = np.array(v['T']); ax = np.array(v['R'])[:, 1]
    d = min(dadi, key=lambda x: np.linalg.norm(np.array(x['T']) - Tv))
    fuori = (ax[2] > 0.9) or np.dot((Tv - centro3) * [1, 1, 0], ax) > 0
    buone += bool(fuori and np.dot(np.array(d['T']) - Tv, ax) < 0)
print('teste fuori (o in su per i piedini) e dado dall altra parte:', buone, 'di', len(viti))
from collections import Counter  # noqa: E402
print(Counter(i['name'].split(' (')[0] for i in s.asm.instances))
for x in A.interferences(s.asm, s.asm_parts):
    print('INTERFERENZA', s.asm.instance(x['a'])['name'], '|', s.asm.instance(x['b'])['name'], round(x['volume'], 1))
assert s.save(str(out))['ok']
print('salvato', out)
