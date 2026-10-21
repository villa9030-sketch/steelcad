"""Vetrina: cassettiera porta punte e maschi da muro, in lamiera, disegnata con i comandi di SteelCAD.

    python tools/vetrina_cassettiera.py [cartella]     (di default Documenti/SteelCAD/Cassettiera porta punte)

La cassa (fondo + quattro bordi, sp. 1,5) con le asole per fissarla al muro; quattro cassetti a vaschetta su guide
a sfere commerciali (Prmape 200, H 40, sp. 20: da acquistare, in distinta col codice), frontalino con la gola per
le dita; in ogni cassetto una rastrelliera a incastro (due traversini e i separatori, cave a metà altezza, niente viti) che fa
uno scomparto per misura, con le punte coricate dentro (Ø1–Ø13 a passo 0,5, maschi M3–M12). Tutto montato con gli accoppiamenti (faccia su faccia, distanza, in mezzo, foro su foro); i cassetti
aperti a scalare. Poi interferenze, distinta, DXF, pieghe, tavole e STEP.
"""
import math
import os
import sys
import time
from pathlib import Path

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))
import build123d as bd  # noqa: E402
import numpy as np  # noqa: E402

from app.service import Service  # noqa: E402
from cad_engine.topology.naming import _faces_of  # noqa: E402
from cad_engine import assembly as A  # noqa: E402

D = Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'Cassettiera porta punte'
MAT = 'S235'
R_P, K_P = 1, 0.21                        # piegatrice di Stefano
# cassa
W, H, P, SPC = 420, 260, 220, 1.5
PASSO = 64                                # un cassetto ogni 64 mm
# guide a sfere: fissa C 35 × 6, mobile C 28 × 4 (dentro la fissa), lunghe 180, sp. 1,5
# guide a sfere da acquistare: telescopiche, estrazione totale, sp. 12,7, alte 35, lunghe 200 (disegnate come ingombro)
G_H, G_SP, G_L = 40, 20, 200             # Prmape 200 mm, misurata da Stefano: alta 40, spessa 20
GUIDA = {'descrizione': 'Guida per cassetti a sfere, estrazione totale 3 sezioni, L 200 H 40 sp. 20, portata 45 kg '
                        '(conf. 4 pz = 2 coppie: servono 2 confezioni)',
         'codice': 'Amazon B0GVCYMQ4K', 'fornitore': 'Prmape'}
INGOMBRO_GUIDE = G_SP + 0.3               # dal fianco della cassa al fianco del cassetto
# cassetto
CW = W - 2 * SPC - 2 * INGOMBRO_GUIDE     # 402
CP, CH, SPK = 202, 46, 1.0
FW, FH = W - 2 * SPC - 1, 60              # frontalino
# rastrelliera a incastro nel cassetto: due traversini (davanti, dietro) e i separatori tra gli scomparti
LI, PI = CW - 2 * SPK, CP - 2 * SPK       # dentro il cassetto: 400 × 180
SPR, HR = 1.0, 25                         # lamierini sp. 1, alti 25
CAVA = SPR + 0.2                          # cava d'incastro: spessore + gioco
FONDO_CAVA = HR / 2 + 0.1                 # le cave arrivano a metà (+0,1: non si toccano)
DAL_BORDO = 7                             # i traversini a 7 mm dal davanti e dal dietro del cassetto
COPIE = {0: 2, 1: 3, 2: 3, 3: 3}          # utensili per scomparto (due maschi, tre punte)
APERTO = {0: 165, 1: 120, 2: 75, 3: 30}   # quanto è tirato fuori ogni cassetto (0 in basso): a scalare, come in vetrina
# contenuto (dal basso): maschi, punte grandi, medie, piccole — Ø del foro e lunghezza dell'utensile
DIN338 = {1: 34, 1.5: 40, 2: 49, 2.5: 57, 3: 61, 3.5: 70, 4: 75, 4.5: 80, 5: 86, 5.5: 93, 6: 93, 6.5: 101, 7: 109,
          7.5: 109, 8: 117, 8.5: 117, 9: 125, 9.5: 125, 10: 133, 10.5: 133, 11: 142, 11.5: 142, 12: 151, 12.5: 151,
          13: 151}
MASCHI = [('M3', 3.5, 56), ('M4', 4.5, 63), ('M5', 6, 70), ('M6', 6, 80), ('M8', 8, 90), ('M10', 10, 100), ('M12', 9, 110)]
CASSETTI = {
    0: [(n, d, L) for n, d, L in MASCHI],
    1: [(f'Ø{d:g}', d, DIN338[d]) for d in (10, 10.5, 11, 11.5, 12, 12.5, 13)],
    2: [(f'Ø{d:g}', d, DIN338[d]) for d in (5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5)],
    3: [(f'Ø{d:g}', d, DIN338[d]) for d in (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)],
}
T0 = time.time()


def ok(r, cosa):
    if not r.get('ok'):
        raise SystemExit(f'{cosa}: {r.get("message")}')
    return r


def log(t):
    print(f'{time.time() - T0:6.1f}s  {t}', flush=True)


# ------------------------------------------------------------------------------------------ pezzi
def bbox(s):
    b = bd.Compound(s.result.body.shape).bounding_box()
    return np.array([b.min.X, b.min.Y, b.min.Z]), np.array([b.max.X, b.max.Y, b.max.Z])


def piega(s, edge, length, giusto, parent=None):
    """Una flangia: prova «su», e se l'ingombro non è quello voluto (giusto(min, max)) la gira «giù»."""
    r = ok(s.add_flange('SM1', edge, {'length': length, 'direction': 'up'}, parent), f'piega {edge or parent}')
    fl = r['select'].split('/')[-1]
    if not giusto(*bbox(s)):
        ok(s.edit_flange('SM1', fl, {'direction': 'down'}), 'gira la piega')
        if not giusto(*bbox(s)):
            raise SystemExit(f'la piega {fl} non va dove serve: {bbox(s)}')
    return fl


def fori_nel_mondo(s, faccia, cerchi=(), asole=()):
    """Fori e asole sulla faccia, dati nelle coordinate del pezzo (x, y, z): lo sketch li riporta sul suo piano."""
    from cad_engine.sketch.face_plane import plane_of
    sid = ok(s.sketch_on_face(faccia), f'sketch su {faccia}')['sketch']
    sk = s.doc.sketch(sid)
    piano = plane_of(s.result.body, faccia, sk)
    loc = lambda q: [round(v, 4) for v in tuple(piano.to_local_coords(bd.Vector(*q)))[:2]]  # noqa: E731
    for c, d in cerchi:
        ok(s.sketch_add_circle(sid, loc(c), round(d / 2, 4)), f'foro Ø{d}')
    for c1, c2, d in asole:
        ok(s.sketch_add_slot(sid, loc(c1), loc(c2), d / 2), 'asola')
    ok(s.create_from_sketch(sid, 'cut', {}), 'togli materiale')


def nuovo(nome, larg, prof, sp):
    s = Service()
    ok(s.new_project('lamiera', {'name': nome, 'larghezza': larg, 'profondita': prof, 'spessore': sp,
                                 'raggio': R_P, 'k': K_P, 'material': MAT}), nome)
    return s


def salva(s, nome):
    f = D / f'{nome}.steelcad'
    ok(s.save(str(f)), f'salva {nome}')
    return f


def cassa():
    """Fondo (il dietro, contro il muro) W × H con i quattro bordi in avanti; asole per le viti a muro."""
    s = nuovo('Cassa', W, H, SPC)
    for e in ('L1', 'L2', 'L3', 'L4'):
        piega(s, e, P, lambda a, b: b[2] > P - 1)
    asole = [((x, y - 10, 0), (x, y + 10, 0), 6.5) for x in (45, W - 45) for y in (60, H - 50)]
    fori_nel_mondo(s, 'SM1/sopra', asole=asole)
    return salva(s, 'Cassa')


def guida():
    """La guida a sfere (si compra): il suo ingombro, un C 200 × 35 × 12,7 con i fori delle viti."""
    s = nuovo('Guida a sfere L200', G_L, G_H, 1.2)
    for e in ('L1', 'L3'):
        piega(s, e, G_SP, lambda a, b: b[2] > G_SP - 0.1)
    fori_nel_mondo(s, 'SM1/sopra', cerchi=[((x, G_H / 2, 0), 4.5) for x in (20, G_L / 2, G_L - 20)])
    return salva(s, 'Guida a sfere L200')


def vaschetta():
    s = nuovo('Cassetto', CW, CP, SPK)
    for e in ('L1', 'L2', 'L3', 'L4'):
        piega(s, e, CH, lambda a, b: b[2] > CH - 1)
    return salva(s, 'Cassetto')


def marca(s, faccia, testi):
    """Testi marcati col laser sulla faccia: [(testo, centro nelle coordinate del pezzo (x, y, z), altezza)]."""
    from cad_engine.sketch import testo as testo_mod
    from cad_engine.sketch.face_plane import plane_of
    sid = ok(s.sketch_on_face(faccia), f'sketch su {faccia}')['sketch']
    piano = plane_of(s.result.body, faccia, s.doc.sketch(sid))
    for t, c, h in testi:
        x, y = tuple(piano.to_local_coords(bd.Vector(*c)))[:2]
        ok(s.sketch_add_text(sid, [round(x - testo_mod.larghezza(t, h) / 2, 3), round(y - h / 2, 3)], t, h), f'testo {t}')
    ok(s.create_from_sketch(sid, 'mark', {}), f'marca {faccia}')


ETICHETTE = {0: 'MASCHI M3 - M12', 1: 'PUNTE Ø10 - Ø13', 2: 'PUNTE Ø5,5 - Ø9,5', 3: 'PUNTE Ø1 - Ø5'}


def frontalino(k):
    """Frontalino del cassetto k: in basso un bordo indietro, in alto la gola per le dita; il contenuto marcato."""
    nome = f'Frontalino {k + 1}'
    s = nuovo(nome, FW, FH, SPC)
    piega(s, 'L1', 10, lambda a, b: a[2] < -5)
    g = piega(s, 'L3', 16, lambda a, b: a[2] < -10)
    # la gola: dal bordo in alto scende di 7, sopra le sponde del cassetto
    piega(s, None, 7, lambda a, b: b[1] < FH + 0.1, parent=g)
    marca(s, 'SM1/sopra', [(ETICHETTE[k], (FW / 2, FH * 0.42, SPC), 9)])
    return salva(s, nome)


def sagoma(nome, punti, sp):
    """Un lamierino piano dal contorno disegnato (chiuso)."""
    s = Service()
    ok(s.new_project('zero', {'name': nome, 'material': MAT}), nome)
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    ok(s.sketch_add_polyline(sid, [[round(x, 4), round(y, 4)] for x, y in punti], True), f'contorno {nome}')
    ok(s.create_from_sketch(sid, 'sheet', {'thickness': sp}), f'lamiera {nome}')
    return salva(s, nome)


def scomparti(n):
    """I centri dei separatori, dal fianco sinistro dentro il cassetto: n scomparti uguali."""
    return [i * LI / n for i in range(1, n)]


def separatore():
    """Va da davanti a dietro; due cave dal basso dove passano i traversini."""
    L = PI - 2                                         # 1 mm di gioco davanti e dietro
    cave = [DAL_BORDO + SPR / 2 - 1, PI - DAL_BORDO - SPR / 2 - 1]
    pts = [(0, 0)]
    for c in cave:
        pts += [(c - CAVA / 2, 0), (c - CAVA / 2, FONDO_CAVA), (c + CAVA / 2, FONDO_CAVA), (c + CAVA / 2, 0)]
    pts += [(L, 0), (L, HR), (0, HR)]
    return sagoma('Separatore', pts, SPR)


def traversino(n, k=None):
    """Largo quanto il cassetto; una cava dall'alto per ogni separatore. Quello davanti del cassetto k ha la misura
    di ogni scomparto marcata col laser."""
    L = LI - 1
    pts = [(2, 0), (L - 2, 0), (L, 2), (L, HR)]        # angoli in basso smussati: lì c'è il raggio della piega del cassetto
    for x in reversed([x - 0.5 for x in scomparti(n)]):
        pts += [(x + CAVA / 2, HR), (x + CAVA / 2, HR - FONDO_CAVA), (x - CAVA / 2, HR - FONDO_CAVA), (x - CAVA / 2, HR)]
    pts += [(0, HR), (0, 2)]
    if k is None:
        return sagoma(f'Traversino {n} scomparti', pts, SPR)
    f = sagoma(f'Traversino {n} scomparti - cassetto {k + 1}', pts, SPR)
    s = Service()
    ok(s.open(str(f)), 'apri traversino')
    w = LI / n
    misure = [nome.replace('Ø', '').replace('.', ',') for nome, _d, _L in CASSETTI[k]]
    marca(s, 'SM1/sopra', [(m, ((j + 0.5) * w - 0.5, 6, SPR), 5) for j, m in enumerate(misure)])
    ok(s.save(str(f)), 'salva traversino')
    return f


def utensile(nome, d, L):
    s = Service()
    ok(s.new_project('zero', {'name': nome, 'material': MAT}), nome)
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    ok(s.sketch_add_circle(sid, [0, 0], d / 2), 'tondo')
    ok(s.create_from_sketch(sid, 'plate', {'thickness': L}), 'estrudi')
    return salva(s, nome.replace('/', '-'))


# ------------------------------------------------------------------------------------------ assieme
class Facce:
    """Le facce di un'istanza nel mondo, senza ricalcolare la scena: (indice, tipo, p, n, r, area)."""
    def __init__(self, s):
        self.s, self.loc = s, {}

    def di(self, iid):
        i = self.s.asm.instance(iid)
        part = self.s.asm_parts[i['file']]
        if i['file'] not in self.loc:
            out = []
            for k, f in enumerate(_faces_of(part.shape)):
                inf = A.face_info(part, f)
                out.append((k, inf['kind'], np.array(inf['p']), np.array(inf['n']), inf.get('r'), bd.Face(f).area))
            self.loc[i['file']] = out
        R, T = np.array(i['R']), np.array(i['T'])
        return [(k, kind, R @ p + T, R @ n, r, a) for k, kind, p, n, r, a in self.loc[i['file']]]

    def piana(self, iid, n, piu=True, filtro=None):
        """La faccia piana con quella normale, la più avanti lungo n (piu) o la più indietro."""
        n = np.array(n, dtype=float)
        c = [(np.dot(p, n) * (1 if piu else -1), -a, k) for k, kind, p, nn, r, a in self.di(iid)
             if kind == 'piana' and np.dot(nn, n) > 0.999 and (filtro is None or filtro(p, a))]
        if not c:
            raise SystemExit(f'nessuna faccia di {iid} con normale {n}')
        best = max(c)
        # a pari posizione la più grande
        pari = [x for x in c if abs(x[0] - best[0]) < 1e-6]
        return {'inst': iid, 'face': max(pari)[2]}

    def cilindro(self, iid, asse, r, vicino):
        c = [(0 if vicino is None else np.linalg.norm(np.cross(p - np.array(vicino), asse)), k)
             for k, kind, p, nn, rr, a in self.di(iid)
             if kind == 'cilindrica' and abs(abs(np.dot(nn, asse)) - 1) < 1e-6 and abs(rr - r) < 1e-3]
        if not c:
            raise SystemExit(f'nessun foro r={r} in {iid}')
        return {'inst': iid, 'face': min(c)[1]}


def assieme(f):
    s = Service()
    ok(s.new_assembly('Cassettiera porta punte'), 'assieme')
    ok(s.save(str(D / 'Cassettiera porta punte.steelcad-asm')), 'salva assieme')
    F = Facce(s)
    X, Y, Z = np.eye(3)
    n_mate = [0]

    def mate(tipo, a, b, off=0, flip=False, a2=None, b2=None):
        ok(s.asm_add_mate(tipo, a, b, off, flip, a2, b2), f'{tipo} {a["inst"]}-{b["inst"]}')
        n_mate[0] += 1

    def metti(file, rot=()):
        ok(s.asm_insert(str(file)), f'inserisci {Path(file).name}')
        iid = s.asm.instances[-1]['id']
        for asse, g in rot:
            ok(s.asm_rotate(iid, asse, g), 'ruota')
        return iid

    cassa = metti(f['cassa'], [('x', 90)])
    ok(s.asm_set(cassa, {'fixed': True}), 'cassa ferma')
    fondo = F.piana(cassa, Z, piu=False)                     # il fondo della cassa, dentro
    sx, dx = F.piana(cassa, X, piu=False), F.piana(cassa, -X, piu=False)    # i fianchi, dentro
    davanti = F.piana(cassa, -Y)                             # il bordo davanti (le punte delle pieghe)
    log('cassa')
    for k in range(4):
        z = 4 + k * PASSO
        fuori = APERTO[k]
        # cassetto: altezza, in mezzo ai fianchi, quanto è tirato fuori
        c = metti(f['cassetto'])
        mate('distanza', fondo, F.piana(c, -Z), z)
        mate('centra', sx, F.piana(c, -X), 0, False, dx, F.piana(c, X))
        mate('distanza', davanti, F.piana(c, -Y), -SPC + fuori, True)
        # frontalino contro il davanti del cassetto
        fr = metti(f[f'frontalino {k}'], [('x', 90)])
        mate('faccia', F.piana(c, -Y), F.piana(fr, Y, piu=False, filtro=lambda p, a: a > 5000))
        mate('centra', F.piana(c, -X), F.piana(fr, -X), 0, False, F.piana(c, X), F.piana(fr, X))
        mate('distanza', F.piana(c, -Z), F.piana(fr, -Z), 3, True)
        # guide a sfere (commerciali) avvitate sui fianchi della cassa, il cassetto in mezzo
        for lato, fianco_cassa, verso in (('sx', sx, X), ('dx', dx, -X)):
            gf = metti(f['guida'], [('x', 90), ('z', 90)] + ([('z', 180)] if lato == 'dx' else []))
            mate('faccia', fianco_cassa, F.piana(gf, -verso, piu=True, filtro=lambda p, a: a > 3000))
            mate('distanza', fondo, F.piana(gf, -Z), z + 3)
            mate('distanza', davanti, F.piana(gf, -Y), -5, True)
        # rastrelliera: i due traversini sul fondo, a 7 mm dal davanti e dal dietro, in mezzo ai fianchi
        roba = CASSETTI[k]
        n = len(roba)
        pavimento = F.piana(c, Z, piu=False)
        sx_c, dx_c = F.piana(c, X, piu=False), F.piana(c, -X, piu=False)    # i fianchi del cassetto, dentro
        dav_c, die_c = F.piana(c, Y, piu=False), F.piana(c, -Y, piu=False)  # davanti e dietro, dentro
        tr = {}
        for dove, faccia_c, verso in (('davanti', dav_c, -Y), ('dietro', die_c, Y)):
            t = metti(f[f'traversino davanti {k}'] if dove == 'davanti' else f[f'traversino {n}'], [('x', 90)])
            mate('faccia', pavimento, F.piana(t, -Z))
            mate('distanza', faccia_c, F.piana(t, verso), DAL_BORDO)
            mate('centra', sx_c, F.piana(t, -X), 0, False, dx_c, F.piana(t, X))
            tr[dove] = t
        # i separatori infilati nelle cave
        for x in scomparti(n):
            sp_ = metti(f['separatore'], [('x', 90), ('z', 90)])
            mate('faccia', pavimento, F.piana(sp_, -Z))
            mate('distanza', sx_c, F.piana(sp_, -X), x - SPR / 2)
            mate('distanza', dav_c, F.piana(sp_, -Y), 1)
        # gli utensili coricati nel loro scomparto: tangenti al fondo e a distanza dal fianco, 3 mm dietro al traversino
        dietro_trav = F.piana(tr['davanti'], Y)
        w = LI / n
        for j, (nome, d, L) in enumerate(roba):
            copie = COPIE[k]
            passo = min((w - 6) / copie, d + 3)
            for cc in range(copie):
                xc = (j + 0.5) * w + (cc - (copie - 1) / 2) * passo
                u = metti(f[f'utensile {nome}'], [('x', 90)])
                tondo = F.cilindro(u, Y, d / 2, None)
                mate('tangente', pavimento, tondo)
                mate('tangente', sx_c, tondo, xc - d / 2)
                mate('distanza', dietro_trav, F.piana(u, -Y), 3)
        log(f'cassetto {k + 1}: {n_mate[0]} accoppiamenti')
    ok(s.save(str(D / 'Cassettiera porta punte.steelcad-asm')), 'salva assieme')
    return s


if __name__ == '__main__':
    _arg = [a for a in sys.argv[1:] if not a.startswith('--')]
    if _arg:
        D = Path(_arg[0])
    D.mkdir(parents=True, exist_ok=True)
    f = {'cassa': cassa()}
    log('cassa fatta')
    f['guida'] = guida()
    f['cassetto'] = vaschetta()
    for k in range(4):
        f[f'frontalino {k}'] = frontalino(k)
    log('guide, cassetto, frontalino')
    f['separatore'] = separatore()
    for n in sorted({len(v) for v in CASSETTI.values()}):
        f[f'traversino {n}'] = traversino(n)
    for k in range(4):
        f[f'traversino davanti {k}'] = traversino(len(CASSETTI[k]), k)
    for k in range(4):
        for nome, d, L in CASSETTI[k]:
            f[f'utensile {nome}'] = utensile(('Maschio ' if nome.startswith('M') else 'Punta ') + nome, d, L)
    log('rastrelliere e utensili')
    s = assieme(f)
    # i pezzi da comprare: guide, punte, maschi (in distinta col codice, niente DXF)
    fatti = set()
    for i in list(s.asm.instances):
        nome = Path(i['file']).stem
        if i['file'] in fatti or not (nome.startswith(('Guida', 'Punta', 'Maschio'))):
            continue
        fatti.add(i['file'])
        if nome.startswith('Guida'):
            campi = GUIDA
        elif nome.startswith('Punta'):
            campi = {'descrizione': f'Punta elicoidale HSS DIN 338 {nome[6:]}', 'codice': '', 'fornitore': ''}
        else:
            m = nome[8:]
            campi = {'descrizione': f'Maschio a macchina HSS {m} {"DIN 376" if m == "M12" else "DIN 371"}', 'codice': '', 'fornitore': ''}
        ok(s.asm_set_acquisto(i['id'], campi), f'acquisto {nome}')
    ok(s.save(str(D / 'Cassettiera porta punte.steelcad-asm')), 'salva assieme')
    log(f'avvisi: {s.asm.warnings}')
    inter = s.asm_interferences().get('interferences') or []
    log(f'interferenze: {[x.get("label") for x in inter]}')
    # per l'officina: i pezzi in lamiera (le punte e i maschi si comprano)
    officina = D / 'Per officina'
    for k, nome in enumerate(['Cassa', 'Cassetto'] + [f'Frontalino {i + 1}' for i in range(4)] + ['Separatore']
                             + [f'Traversino {n} scomparti' for n in sorted({len(v) for v in CASSETTI.values()})]
                             + [f'Traversino {len(CASSETTI[i])} scomparti - cassetto {i + 1}' for i in range(4)]):
        x = Service()
        ok(x.open(str(D / f'{nome}.steelcad')), f'apri {nome}')
        ok(x.prepara(str(officina), ['laser', 'piegatrice', 'officina', 'step'], {'numero': f'CP-{k + 1:03d}'}), f'prepara {nome}')
    ok(s.export_step(str(officina / 'Cassettiera porta punte.step')), 'STEP assieme')
    log(ok(s.asm_export_bom(str(officina / 'Cassettiera porta punte_distinta.xlsx')), 'distinta')['message'])
    c = s.drawing_fields().get('fields', {})
    ok(s.export_drawings(str(officina / 'Cassettiera porta punte_disegni.pdf'), {**c, 'numero': 'CP-000'}, False), 'tavola assieme')
    log(f"file per l'officina in {officina}")
