"""Tavolo 2200 x 600 x 850, 3 ripiani, retro e fianchi chiusi, piedini fissi: tutto inox 304 satinato sp. 3.
Mondo: X lungo il tavolo (0..2200), Y profondita (0 davanti .. 600 dietro), Z in su (0 = pavimento).
uso: costruisci.py <cartella di uscita>"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # la cartella di Radius
import build123d as bd  # noqa: E402

from app.service import Service  # noqa: E402
from cad_engine.sketch.face_plane import plane_of  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
T = 3.0
L, D, H = 2200.0, 600.0, 850.0
PIEDE = 95.0                      # altezza dei piedini (sotto il ripiano basso)
LS, DS = L - 2 * T, D - T         # ripiano: 2194 x 597 (fianchi e retro fuori)
X0 = T                            # il ripiano parte da X = 3
Z_TOP, Z_MEZZO = H, 475.0         # superficie del top e del ripiano di mezzo
GAMBA_Z0, GAMBA_Z1 = PIEDE + T + 1, H - T - 1     # 1 mm d aria sul piano: niente raggio di piega contro lo spigolo
NOMI = {'top': 'TAVOLO 2200 TOP', 'mezzo': 'TAVOLO 2200 RIPIANO MEZZO', 'basso': 'TAVOLO 2200 RIPIANO BASSO',
        'gamba': 'TAVOLO 2200 GAMBA', 'fianco': 'TAVOLO 2200 FIANCO', 'retro': 'TAVOLO 2200 RETRO',
        'piede': 'TAVOLO 2200 PIEDINO'}


def ok(r, cosa):
    if not r.get('ok'):
        raise SystemExit(f'{cosa}: {r.get("message")}')
    return r


def nuovo(nome, lx, ly):
    s = Service()
    ok(s.new_project('lamiera', {'name': nome, 'larghezza': lx, 'profondita': ly, 'spessore': T, 'raggio': 1,
                                 'k': 0.21, 'material': 'AISI304'}), nome)
    s.doc.meta['finitura'] = {'tipo': 'inox'}
    return s


def taglio_su(s, faccia, cerchi=(), rettangoli=(), opz=None):
    """Cerchi Ø9 [(x,y,z) nel pezzo] e rettangoli [((x,y,z),(x,y,z))] su una faccia, poi il taglio."""
    if not cerchi and not rettangoli:
        return
    sid = ok(s.sketch_on_face(faccia), f'sketch su {faccia}')['sketch']
    pl = plane_of(s.result.body, faccia, s.doc.sketch(sid))
    loc = lambda p: pl.to_local_coords(bd.Vector(*p))  # noqa: E731
    for p in cerchi:
        q = loc(p)
        ok(s.sketch_add_circle(sid, [round(q.X, 4), round(q.Y, 4)], 4.5), 'foro')
    for a, b in rettangoli:
        qa, qb = loc(a), loc(b)
        ok(s.sketch_add_rectangle(sid, [round(qa.X, 4), round(qa.Y, 4)], [round(qb.X, 4), round(qb.Y, 4)]), 'rettangolo')
    ok(s.create_from_sketch(sid, 'cut', opz or {}), f'taglio su {faccia}')


def salva(s, chiave):
    assert not s.state()['errors'], (chiave, s.state()['errors'])
    f = OUT / f'{NOMI[chiave]}.steelcad'
    ok(s.save(str(f)), 'salva')
    return f


# ------------------------------------------------------------------ dove stanno i pezzi (R, T: pezzo -> mondo)
def rz(k):
    c, s_ = [(1, 0), (0, 1), (-1, 0), (0, -1)][k % 4]
    return np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]], dtype=float)


def metti(R, bbox_pezzo, minimo):
    """T perché il pezzo girato con R abbia l'angolo minimo dell'ingombro in «minimo»."""
    (a, b) = bbox_pezzo
    ang = np.array([[x, y, z] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]) @ R.T
    return np.array(minimo, dtype=float) - ang.min(axis=0)


R_DRITTO = np.eye(3)
R_ROVESCIO = np.diag([1.0, -1.0, -1.0])                 # vaschetta girata: piano sopra, bordi in giu
POSE = {'basso': (R_DRITTO, np.array([X0, 0, PIEDE])),
        'mezzo': (R_ROVESCIO, np.array([X0, DS, Z_MEZZO])),
        'top': (R_ROVESCIO, np.array([X0, DS, Z_TOP]))}


def a_pezzo(chiave, p):
    R, Tv = POSE[chiave]
    return R.T @ (np.array(p, dtype=float) - Tv)


# quote dei fori nel mondo
def z_righe(chiave):
    """Le due file di fori alle gambe e la fila dei pannelli, in Z nel mondo."""
    if chiave == 'basso':
        return PIEDE + 17.5, PIEDE + 32.5, PIEDE + 25
    z = {'top': Z_TOP, 'mezzo': Z_MEZZO}[chiave]
    return z - 32.5, z - 17.5, z - 25


XG = (X0 + 23, X0 + LS - 23)                              # fori alle gambe lungo X (26, 2174)
YG = (23.0, DS - 23)                                      # e lungo Y (23, 574)
XP = [XG[0] + k * (XG[1] - XG[0]) / 6 for k in range(1, 6)]   # fori del retro tra le gambe
YP = [DS / 2]                                             # fori dei fianchi tra le gambe
for k in ('top', 'mezzo', 'basso'):
    for z in z_righe(k)[:2]:
        assert abs((z - 7.5) / 15 - round((z - 7.5) / 15)) < 1e-9, (k, z)   # sulla griglia delle gambe


def fori_mondo(chiave):
    """{'davanti','dietro','sx','dx'}: punti (sulla faccia esterna del bordo) nel mondo."""
    z1, z2, zp = z_righe(chiave)
    return {'davanti': [(x, 0.0, z) for x in XG for z in (z1, z2)],
            'dietro': [(x, DS, z) for x in XG for z in (z1, z2)] + [(x, DS, zp) for x in XP],
            'sx': [(X0, y, z) for y in YG for z in (z1, z2)] + [(X0, y, zp) for y in YP],
            'dx': [(X0 + LS, y, z) for y in YG for z in (z1, z2)] + [(X0 + LS, y, zp) for y in YP]}


# ------------------------------------------------------------------ la linguetta del ripiano di mezzo
# Copiata dal ripiano del carrello (S7/TG6 «Linguetta»): in ogni angolo, distanze (u, v) dai due bordi del piano
# (il piano parte a 4 dall'esterno, dopo la piega). Contorno chiuso: linee e raccordi r2 (centro, da, a).
LING = [('L', (5, 3), (33, 3)), ('A', (33, 5), (33, 3), (35, 5)), ('L', (35, 5), (35, 17)), ('L', (35, 17), (41, 17)),
        ('L', (41, 17), (41, 41)), ('L', (41, 41), (17, 41)), ('L', (17, 41), (17, 35)), ('L', (17, 35), (5, 35)),
        ('A', (5, 33), (5, 35), (3, 33)), ('L', (3, 33), (3, 5)), ('A', (5, 5), (3, 5), (5, 3))]


def linguette(s):
    faccia = 'SM1/sotto'
    sid = ok(s.sketch_on_face(faccia), 'sketch linguette')['sketch']
    pl = plane_of(s.result.body, faccia, s.doc.sketch(sid))
    x0, x1, y0, y1 = 4.0, LS - 4.0, 4.0, DS - 4.0         # il piano (dopo le pieghe), nel pezzo

    def fn():
        sk = s.doc.sketch(sid)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            punti = {}

            def pt(uv):
                x = x0 + uv[0] if sx > 0 else x1 - uv[0]
                y = y0 + uv[1] if sy > 0 else y1 - uv[1]
                q = pl.to_local_coords(bd.Vector(x, y, 0))
                k = (round(q.X, 4), round(q.Y, 4))
                if k not in punti:
                    punti[k] = sk.point(*k)
                return punti[k], k
            for el in LING:
                if el[0] == 'L':
                    sk.line(pt(el[1])[0], pt(el[2])[0])
                else:
                    (c, kc), (a_, ka), (b_, kb) = pt(el[1]), pt(el[2]), pt(el[3])
                    antiorario = (ka[0] - kc[0]) * (kb[1] - kc[1]) - (ka[1] - kc[1]) * (kb[0] - kc[0]) > 0
                    sk.arc(c, a_, b_) if antiorario else sk.arc(c, b_, a_)
        s.doc.add_feature('sheet_cut', 'Linguetta', sketch=sid, mode='add')
    ok(s._change('Linguette nelle gambe', fn), 'linguette')


# ------------------------------------------------------------------ i ripiani
def tacche_ritorni(s, lx, ly, quanto=46):
    """Toglie i ritorni (e la loro piega) per «quanto» mm da ogni angolo, disegnando sullo sviluppo: i 4 ritorni
    sono una faccia sola nel pezzo piegato e il taglio sulla faccia non si abbina."""
    from cad_engine import sheetmetal as SMm
    d = s.result.body.sheet
    sid = ok(s.sketch_on_flat('SM1'), 'sketch sullo sviluppo')['sketch']
    for g in d.flanges:
        if g.parent is None:
            continue
        ax = max(range(3), key=lambda i: abs(tuple(g.xf)[i]))
        lung = lx if ax == 0 else ly
        o, xf = tuple(g.origin)[ax], tuple(g.xf)[ax]
        for a, b in ((-1, quanto), (lung - quanto, lung + 1)):
            ua, ub = sorted(((a - o) / xf, (b - o) / xf))
            ua, ub = max(ua, g.u0 - 1), min(ub, g.u1 + 1)
            if ub <= ua:
                continue
            rf = SMm._rett_flat(g, ua, ub, g.off - 0.01, g.off + g.bend.ba + g.lf + 1)
            pts = [d.plane.to_local_coords(v) for v in rf.vertices()]
            xs, ys = [q.X for q in pts], [q.Y for q in pts]
            ok(s.sketch_add_rectangle(sid, [round(min(xs), 4), round(min(ys), 4)], [round(max(xs), 4), round(max(ys), 4)]), 'tacca')
    ok(s.create_from_sketch(sid, 'cut', {}), 'tacche dei ritorni')


def ripiano(chiave):
    s = nuovo(NOMI[chiave], LS, DS)
    for lato in ('L1', 'L2', 'L3', 'L4'):
        ok(s.add_flange('SM1', lato, {'length': 50}), lato)
    fl = {f['edge']: f['id'] for f in s.doc.feature('SM1')['flanges']}
    for lato in ('L1', 'L2', 'L3', 'L4'):
        ok(s.add_flange('SM1', None, {'length': 20}, parent=fl[lato]), 'ritorno')
    # angoli chiusi: i bordi lunghi sopra (il davanti resta pulito fino agli spigoli)
    for lungo in ('L1', 'L3'):
        for corto in ('L2', 'L4'):
            ok(s.set_corner('SM1', fl[lungo], fl[corto], 'over'), 'angolo')
    rit = {f['parent']: f['id'] for f in s.doc.feature('SM1')['flanges'] if f.get('parent')}
    # i fori sui bordi (dal mondo al pezzo): ogni bordo e' la faccia esterna della flangia su quel lato
    lato_di = {}
    for lato, fid in fl.items():
        b = bd.Compound(children=[bd.Face(f) for f in s.result.body.names[f'SM1/{fid}/esterno']]).bounding_box()
        lato_di[fid] = b
    fm = fori_mondo(chiave)
    for nome, punti in fm.items():
        pp = [a_pezzo(chiave, p) for p in punti]
        # la flangia la cui faccia esterna sta su quel piano
        fid = next(f for f, b in lato_di.items()
                   if all(b.min.X - 0.01 <= q[0] <= b.max.X + 0.01 and b.min.Y - 0.01 <= q[1] <= b.max.Y + 0.01 for q in pp)
                   and (abs(b.max.X - b.min.X) < 0.01 or abs(b.max.Y - b.min.Y) < 0.01))
        taglio_su(s, f'SM1/{fid}/esterno', cerchi=[tuple(q) for q in pp])
    if chiave == 'mezzo':
        # le gambe passano attraverso: un quadrato 45 x 45 in ogni angolo, attraverso tutto il pezzo
        e = 4.0                                           # 41 x 41 dal bordo del piano, come il carrello (la piega va via intera)
        q = [((e, e, 0), (45, 45, 0)), ((LS - 45, e, 0), (LS - e, 45, 0)), ((e, DS - 45, 0), (45, DS - e, 0)),
             ((LS - 45, DS - 45, 0), (LS - e, DS - e, 0))]
        taglio_su(s, 'SM1/sotto', rettangoli=q, opz={'passante': True})
        linguette(s)                                      # e la linguetta dentro la gamba, come il carrello
    else:
        tacche_ritorni(s, LS, DS)                         # le gambe arrivano al piano: via i ritorni negli angoli
    if chiave == 'basso':
        # i fori dei piedini nel piano
        pts = []
        for xc, yc, sx, sy in ((X0, 0, 1, 1), (X0 + LS, 0, -1, 1), (X0, DS, 1, -1), (X0 + LS, DS, -1, -1)):
            pts += [(xc + sx * 25, yc + sy * 60, PIEDE), (xc + sx * 60, yc + sy * 25, PIEDE)]
        taglio_su(s, 'SM1/sotto', cerchi=[tuple(a_pezzo('basso', p)) for p in pts])
    return salva(s, chiave)


# ------------------------------------------------------------------ la gamba
LG = GAMBA_Z1 - GAMBA_Z0                                  # 749
ZF = [z for z in np.arange(7.5, H, 15.0) if GAMBA_Z0 + 9 < z < GAMBA_Z1 - 9]


def gamba():
    s = nuovo(NOMI['gamba'], LG, 40)
    ok(s.add_flange('SM1', 'L3', {'length': 40}), 'parete')
    fl = {f['edge']: f['id'] for f in s.doc.feature('SM1')['flanges']}
    ok(s.add_flange('SM1', None, {'length': 17}, parent=fl['L3']), 'risvolto')
    ok(s.add_flange('SM1', 'L1', {'length': 17}), 'risvolto base')
    b = bd.Compound(children=[bd.Face(f) for f in s.result.body.names[f'SM1/{fl["L3"]}/esterno']]).bounding_box()
    xs = [z - GAMBA_Z0 for z in ZF]
    taglio_su(s, 'SM1/sotto', cerchi=[(x, 20, 0) for x in xs])
    taglio_su(s, f'SM1/{fl["L3"]}/esterno', cerchi=[(x, b.max.Y, 20) for x in xs])
    return salva(s, 'gamba'), fl['L3']


# ------------------------------------------------------------------ il piedino
def piede():
    s = nuovo(NOMI['piede'], 80, 80)
    ok(s.add_flange('SM1', 'L1', {'length': PIEDE}), 'parete')
    ok(s.add_flange('SM1', 'L4', {'length': PIEDE}), 'parete')
    fl = {f['edge']: f['id'] for f in s.doc.feature('SM1')['flanges']}
    for lato in ('L1', 'L4'):
        ok(s.add_flange('SM1', None, {'length': 30}, parent=fl[lato]), 'appoggio')
    ok(s.set_corner('SM1', fl['L1'], fl['L4'], 'over'), 'angolo')
    taglio_su(s, 'SM1/sotto', cerchi=[(25, 60, 0), (60, 25, 0)])
    return salva(s, 'piede')


# ------------------------------------------------------------------ i pannelli
ZP0, ZP1 = PIEDE, H
R_FIANCO = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float)     # pezzo X->Y, Y->Z, Z->X
R_RETRO = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)     # pezzo X->X, Y->Z, Z->-Y


def pannello(chiave, lx, R, minimo, punti_mondo):
    s = nuovo(NOMI[chiave], lx, ZP1 - ZP0)
    Tv = metti(R, ((0, 0, 0), (lx, ZP1 - ZP0, T)), minimo)
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    for p in punti_mondo:
        q = R.T @ (np.array(p, dtype=float) - Tv)
        ok(s.sketch_add_circle(sid, [round(q[0], 4), round(q[1], 4)], 4.5), 'foro pannello')
    return salva(s, chiave), Tv


if __name__ == '__main__':
    file = {k: ripiano(k) for k in ('top', 'mezzo', 'basso')}
    file['gamba'], parete = gamba()
    file['piede'] = piede()
    sx = [p for k in ('top', 'mezzo', 'basso') for p in fori_mondo(k)['sx']]
    retro = [p for k in ('top', 'mezzo', 'basso') for p in fori_mondo(k)['dietro']]
    file['fianco'], T_fianco = pannello('fianco', DS, R_FIANCO, (0, 0, ZP0), [(0, y, z) for _, y, z in sx])
    file['retro'], T_retro = pannello('retro', L, R_RETRO, (0, DS, ZP0), [(x, DS, z) for x, _, z in retro])
    print({k: str(v) for k, v in file.items()})
