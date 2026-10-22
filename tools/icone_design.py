"""Icone SteelCAD — il sistema (23/10, «falle come un designer»).

Regole:
- griglia 28 (la misura della barra), 2 px di margine, vertici agganciati al quarto di pixel;
- una sola vista per tutte, da prodotto: x → (1, .42), y → (−.62, .78), z → (0, −1.1) (si vede bene la sezione davanti);
- la lamiera è sempre lamiera: spessore visibile, pieghe col raggio vero, sfumatura sulle pieghe dalla luce;
- acciaio grigio per il pezzo; in ambra (il colore della selezione nel 3D) quello che il comando fa;
- contorno 1 px scuro solo sugli spigoli veri (non tra le fette delle pieghe).

    python tools/icone_design.py   → app/ui/icons_nuove/design/*.svg e app/ui/icons_nuove/design.html
"""
import math
from pathlib import Path

R = Path(__file__).resolve().parents[1] / 'app' / 'ui' / 'icons_nuove'
OUT = R / 'design'

INK = '#2B333D'
ACCIAIO = ('#8794A3', '#F3F5F8')       # dal più scuro (in ombra) al più chiaro (in luce)
AMBRA = ('#D8920F', '#FFDC8A')
V = (0.62, 1.0, 0.946)                  # verso chi guarda
LUCE = (-0.35, 0.55, 1.0)
nrm = lambda v: (lambda l: tuple(c / l for c in v))(math.sqrt(sum(c * c for c in v)))  # noqa: E731
dot = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
LUCE = nrm(LUCE)


def mix(c0, c1, t):
    t = max(0.0, min(1.0, t))
    a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * t):02X}' for x, y in zip(a, b))


def tinta(n, pal):
    return mix(pal[0], pal[1], 0.12 + 0.88 * max(0.0, dot(nrm(n), LUCE)) ** 0.9)


class Faccia:
    def __init__(self, pts, fill, spigoli=(), prof=None):
        self.pts, self.fill, self.spigoli = pts, fill, list(spigoli)   # spigoli: coppie di indici da ripassare
        self.prof = prof if prof is not None else dot([sum(p[i] for p in pts) / len(pts) for i in range(3)], V)


# ------------------------------------------------------------------------------------------------- solidi
def lamiera(tratti, t, W, giro=lambda p: p, inizio=(0.0, 0.0), dir0=0.0):
    """Una lamiera piegata: la linea media nel piano xz (tratti ('L', lunghezza, ambra) e ('A', gradi, raggio, ambra)),
    estrusa lungo y da 0 a W. Ritorna le facce."""
    x, z, a = inizio[0], inizio[1], math.radians(dir0)
    cent = [(x, z, a, False)]
    for tr in tratti:
        amb = tr[-1]
        if tr[0] == 'L':
            x += tr[1] * math.cos(a); z += tr[1] * math.sin(a)
            cent.append((x, z, a, amb))
        else:
            ang, r = math.radians(tr[1]), tr[2]
            s = 1 if ang > 0 else -1
            cx, cz = x - s * r * math.sin(a), z + s * r * math.cos(a)
            n = max(3, int(abs(tr[1]) / 10))
            for k in range(1, n + 1):
                b = a + ang * k / n
                cent.append((cx + s * r * math.sin(b), cz - s * r * math.cos(b), b, amb))
            a += ang; x, z = cent[-1][0], cent[-1][1]
    off = lambda c, d: (c[0] - d * math.sin(c[2]), c[1] + d * math.cos(c[2]))  # noqa: E731
    sopra = [off(c, t / 2) for c in cent]
    sotto = [off(c, -t / 2) for c in cent]
    P3 = lambda q, y: giro((q[0], y, q[1]))  # noqa: E731
    N3 = lambda nx, ny, nz: tuple(b - a for a, b in zip(giro((0, 0, 0)), giro((nx, ny, nz))))  # noqa: E731
    facce = []
    n = len(cent)

    def striscia(q0, q1, nn, pal, sp_inizio, sp_fine):
        N = N3(nn[0], 0, nn[1])
        if dot(N, V) <= 1e-6:
            return None
        pts = [P3(q0, 0), P3(q1, 0), P3(q1, W), P3(q0, W)]
        sp = [(0, 1)] + ([(3, 0)] if sp_inizio else []) + ([(1, 2)] if sp_fine else [])
        return Faccia(pts, tinta(N, pal), sp)
    # le due superfici (sopra e sotto) e le due teste (le facce dello spessore ai capi)
    for lato, segno in ((sopra, 1), (sotto, -1)):
        vis = []
        for i in range(n - 1):
            q0, q1 = lato[i], lato[i + 1]
            dx, dz = q1[0] - q0[0], q1[1] - q0[1]
            l = math.hypot(dx, dz) or 1
            vis.append(((-dz / l * segno, dx / l * segno), q0, q1, cent[i + 1][3]))
        for i, (nn, q0, q1, amb) in enumerate(vis):
            visibile = lambda j: 0 <= j < len(vis) and dot(N3(vis[j][0][0], 0, vis[j][0][1]), V) > 1e-6  # noqa: E731
            piega = lambda j, k: 0 <= k < len(vis) and dot(vis[j][0], vis[k][0]) < 0.9  # noqa: E731
            f = striscia(q0, q1, nn, AMBRA if amb else ACCIAIO, not visibile(i - 1) or piega(i, i - 1),
                         not visibile(i + 1) or piega(i, i + 1))
            if f:
                facce.append(f)
    for i, segno in ((0, -1), (n - 1, 1)):
        c = cent[i]
        nn = (segno * math.cos(c[2]), segno * math.sin(c[2]))
        f = striscia(sotto[i], sopra[i], nn, AMBRA if (cent[1][3] if i == 0 else c[3]) else ACCIAIO, True, True)
        if f:
            facce.append(f)
    # la testa davanti (y = W): fettine, il contorno solo fuori e dove cambia colore
    for i in range(n - 1):
        amb = cent[i + 1][3]
        pts = [P3(sopra[i], W), P3(sopra[i + 1], W), P3(sotto[i + 1], W), P3(sotto[i], W)]
        sp = [(0, 1), (2, 3)]
        if i == 0:
            sp.append((3, 0))
        if i == n - 2:
            sp.append((1, 2))
        if i > 0 and cent[i][3] != amb:
            sp.append((3, 0))
        facce.append(Faccia(pts, tinta(N3(0, 1, 0), AMBRA if amb else ACCIAIO), sp, prof=1e6 + i))
    return facce


def lastra(poly, z0, z1, pal=ACCIAIO, pareti=None):
    """Una lastra (poligono antiorario estruso in z): il sopra e le pareti che si vedono; pareti = {indice lato: tavolozza}."""
    facce = [Faccia([(x, y, z1) for x, y in poly], tinta((0, 0, 1), pal), [(i, (i + 1) % len(poly)) for i in range(len(poly))], prof=1e5)]
    for i, (a, b) in enumerate(zip(poly, poly[1:] + poly[:1])):
        N = (b[1] - a[1], a[0] - b[0], 0)
        if dot(N, V) <= 1e-6:
            continue
        p = (pareti or {}).get(i, pal)
        facce.append(Faccia([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], tinta(N, p),
                            [(0, 1), (1, 2), (3, 0)]))
    return facce


# ------------------------------------------------------------------------------------------------- disegno
def proietta(p):
    return (p[0] - 0.62 * p[1], 0.42 * p[0] + 0.78 * p[1] - 1.1 * p[2])


def svg(corpi, sopra=(), margine=2.0, k=None, sposta=(0, 0)):
    """corpi: liste di facce, dal più lontano. sopra: funzioni (T, k) → svg aggiunto dopo."""
    tutte = [p for c in corpi for f in c for p in f.pts]
    xs, ys = zip(*map(proietta, tutte))
    lato = 28 - 2 * margine
    k = k or min(lato / (max(xs) - min(xs)), lato / (max(ys) - min(ys)))
    ox = round((14 - k * (max(xs) + min(xs)) / 2) * 2) / 2 + sposta[0]
    oy = round((14 - k * (max(ys) + min(ys)) / 2) * 2) / 2 + sposta[1]
    snap = lambda v: round(v * 4) / 4  # noqa: E731
    T = lambda p: (snap(ox + k * proietta(p)[0]), snap(oy + k * proietta(p)[1]))  # noqa: E731
    out = []
    for corpo in corpi:
        for f in sorted(corpo, key=lambda f: f.prof):
            pp = [T(p) for p in f.pts]
            d = 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pp) + 'Z'
            out.append(f'<path d="{d}" fill="{f.fill}" stroke="{f.fill}" stroke-width=".35" stroke-linejoin="round"/>')
            if f.spigoli:
                e = ''.join(f'M{pp[i][0]:g} {pp[i][1]:g} L{pp[j][0]:g} {pp[j][1]:g}' for i, j in f.spigoli)
                out.append(f'<path d="{e}" fill="none" stroke="{INK}" stroke-width="1" stroke-linecap="round"/>')
    for fn in sopra:
        out.append(fn(T, k))
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28">' + ''.join(out) + '</svg>'


def schizzo(corpo):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" fill="none" stroke-linecap="round" '
            f'stroke-linejoin="round">{corpo}</svg>')


def nodo(x, y):
    """Un punto dello schizzo: quadratino ambra, come le maniglie nel disegno."""
    return f'<rect x="{x - 2.25:g}" y="{y - 2.25:g}" width="4.5" height="4.5" rx=".6" fill="{AMBRA[1]}" stroke="{INK}" stroke-width="1"/>'


# ------------------------------------------------------------------------------------------------- le icone
t = 1.0
I = {}
# Piega: la lastra piegata su una linea, la parte che si alza (piega compresa) in ambra
I['piega'] = svg([lamiera([('L', 7, False), ('A', 90, 2.4, True), ('L', 7, False)], t, 7, inizio=(0, 0))])
# Flangia: la lastra e, su un suo bordo, la flangia nuova in ambra (verso dietro, così si vede dentro)
I['flangia'] = svg([lamiera([('L', 7, True), ('A', 90, 1.4, True), ('L', 10, False)], t, 7, inizio=(0, 8.4), dir0=-90)])
# Orlo: la lastra col bordo ripiegato su se stesso
I['orlo'] = svg([lamiera([('L', 11, False), ('A', 180, 1.1, True), ('L', 5.5, True)], t, 7, inizio=(0, 0))])


# Spiega: la lastra distesa, con le fasce di piega in ambra
def _spiega():
    faces = lastra([(0, 0), (14, 0), (14, 10), (0, 10)], 0, 1.0)
    fasce = []
    for x0 in (4.2, 9.0):
        fasce.append(Faccia([(x0, 0, 1.0), (x0 + 0.9, 0, 1.0), (x0 + 0.9, 10, 1.0), (x0, 10, 1.0)], AMBRA[1], [(0, 3), (1, 2)], prof=2e5))
        fasce.append(Faccia([(x0, 10, 0), (x0 + 0.9, 10, 0), (x0 + 0.9, 10, 1.0), (x0, 10, 1.0)], tinta((0, 1, 0), AMBRA), [], prof=3e5))
    return svg([faces + fasce])


I['spiega'] = _spiega()
# Taglio: la lastra con una tasca tolta dal bordo davanti; le pareti del taglio in ambra
I['taglio'] = svg([lastra([(0, 0), (13, 0), (13, 11), (9, 11), (9, 5), (4, 5), (4, 11), (0, 11)], 0, 1.4, pareti={4: AMBRA, 5: AMBRA})])


# Foro: la lastra col foro passante; la parete del foro in ambra, dentro il vuoto
def _foro(T, k):
    giro = lambda z: [T((6 + 3.4 * math.cos(a / 24 * math.pi), 6 + 3.4 * math.sin(a / 24 * math.pi), z)) for a in range(48)]  # noqa: E731
    d = lambda pp: 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pp) + 'Z'  # noqa: E731
    su, giu = d(giro(1.4)), d(giro(0))
    return (f'<defs><clipPath id="h"><path d="{su}"/></clipPath></defs><path d="{su}" fill="{mix(*AMBRA, .5)}"/>'
            f'<path clip-path="url(#h)" d="{giu}" fill="#46505C"/><path d="{su}" stroke="{INK}" stroke-width="1" fill="none"/>')


I['foro'] = svg([lastra([(0, 0), (12, 0), (12, 12), (0, 12)], 0, 1.4)], [_foro])
# Pezzo: un blocco pieno, neutro
I['pezzo'] = svg([lastra([(0, 0), (9, 0), (9, 9), (0, 9)], 0, 7.5)])


# Esploso: due lastre staccate lungo le linee di montaggio
def _linee(T, k):
    s = ''
    for p in ((0, 10, 1.6), (10, 10, 1.6), (10, 0, 1.6)):
        a, b = T(p), T((p[0], p[1], 6.4))
        s += f'M{a[0]:g} {a[1]:g} L{b[0]:g} {b[1]:g}'
    return f'<path d="{s}" stroke="{INK}" stroke-width="1" stroke-dasharray="1.5 1.5" fill="none"/>'


I['esploso'] = svg([lastra([(0, 0), (10, 0), (10, 10), (0, 10)], 0, 1.6),
                    lastra([(0, 0), (10, 0), (10, 10), (0, 10)], 6.4, 8.0, AMBRA)], [_linee])
# — schizzo: linee nette, i punti come maniglie
I['linea'] = schizzo(f'<path d="M6 22 L22 6" stroke="{INK}" stroke-width="1.75"/>' + nodo(6, 22) + nodo(22, 6))
I['rettangolo'] = schizzo(f'<rect x="5.5" y="8.5" width="17" height="11" stroke="{INK}" stroke-width="1.75"/>' + nodo(5.5, 8.5) + nodo(22.5, 19.5))
I['quota'] = schizzo(f'<path d="M5.5 22.5 H22.5" stroke="{INK}" stroke-width="2"/>'
                     f'<path d="M5.5 20 V6 M22.5 20 V6" stroke="{INK}" stroke-width="1"/>'
                     f'<path d="M6 11.5 H22" stroke="{INK}" stroke-width="1"/>'
                     f'<path d="M5.5 11.5 L10 9.5 V13.5 Z M22.5 11.5 L18 9.5 V13.5 Z" fill="{INK}" stroke="{INK}" stroke-width=".8"/>'
                     f'<rect x="10.5" y="15" width="7" height="3" rx="1" fill="{AMBRA[1]}" stroke="{INK}" stroke-width="1"/>')
I['specchia'] = schizzo(f'<path d="M14 3.5 V24.5" stroke="{INK}" stroke-width="1" stroke-dasharray="4 1.5 1 1.5"/>'
                        f'<path d="M11 7.5 V20.5 H4 Z" fill="{ACCIAIO[1]}" stroke="{INK}" stroke-width="1.5"/>'
                        f'<path d="M17 7.5 V20.5 H24 Z" fill="{AMBRA[1]}" stroke="{INK}" stroke-width="1.5"/>')

NOMI = [('piega', 'Piega', 'fold'), ('flangia', 'Flangia', 'flange'), ('orlo', 'Orlo', 'hem'), ('spiega', 'Spiega', 'flat'),
        ('taglio', 'Taglio', 'cut'), ('foro', 'Foro', 'hole'), ('pezzo', 'Pezzo', 'box'), ('esploso', 'Esploso', 'explode'),
        ('linea', 'Linea', 'line'), ('rettangolo', 'Rettangolo', 'rect'), ('quota', 'Quota', 'dimension'), ('specchia', 'Specchia', 'mirror')]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'scuro').mkdir(exist_ok=True)
    for k, v in I.items():
        (OUT / f'{k}.svg').write_text(v, encoding='utf-8')
        (OUT / 'scuro' / f'{k}.svg').write_text(v.replace(INK, '#DCE2E8').replace(ACCIAIO[1], '#5B6673'), encoding='utf-8')
    celle = ''.join(f'<div class="c"><img class="g" src="design/{k}.svg"><img class="p" src="design/{k}.svg"><img class="t" src="design/{k}.svg">'
                    f'<span>{it}</span></div>' for k, it, _ in NOMI)
    barra = ''.join(f'<button><img src="design/{k}.svg"><span>{it}</span></button>' for k, it, _ in NOMI)
    vecchia = ''.join(f'<button><img src="../icons/{o}.svg"><span>{it}</span></button>' for _, it, o in NOMI)
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Icone SteelCAD</title><style>
body {{ font: 13px/1.45 "Segoe UI", system-ui, sans-serif; margin: 28px 40px; background: #EEF0F3; color: #1C2228; }}
h1 {{ font-size: 20px; margin: 0; }} h2 {{ font-size: 14px; margin: 22px 0 8px; color: #4A5560; font-weight: 600; }}
.regole {{ color: #4A5560; margin: 6px 0 0; padding-left: 18px; }}
.riga {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 8px; }}
.c {{ display: grid; justify-items: center; gap: 8px; padding: 12px 2px 10px; border-radius: 8px; background: #fff; border: 1px solid #DDE1E6; }}
.c .g {{ width: 84px; height: 84px; }} .c .p {{ width: 28px; height: 28px; }} .c .t {{ width: 16px; height: 16px; }}
.c span {{ font-size: 11.5px; color: #3A4552; }}
.ribbon {{ display: flex; gap: 2px; padding: 6px 8px; background: #F7F8FA; border: 1px solid #D5DAE0; border-radius: 6px; overflow-x: auto; }}
.ribbon button {{ all: unset; display: grid; justify-items: center; gap: 3px; width: 64px; padding: 6px 0 4px; border-radius: 4px; font-size: 11px; color: #2B333D; }}
.ribbon button:hover {{ background: #E6EBF0; }} .ribbon img {{ width: 28px; height: 28px; }}
.ribbon.scuro {{ background: #1E232A; border-color: #2C333C; }} .ribbon.scuro button {{ color: #D5DBE1; }}
.ribbon.scuro button:hover {{ background: #2A313A; }}
</style></head><body>
<h1>Icone SteelCAD: proposta</h1>
<ul class="regole"><li>Griglia 28 px (la misura della barra), una sola vista per tutte, come un pezzo fotografato: si vede la sezione della lamiera davanti.</li>
<li>La lamiera è lamiera: spessore visibile, pieghe con il raggio, la luce sempre dall'alto a sinistra.</li>
<li>Acciaio grigio per il pezzo; in <b style="color:#B9770E">ambra</b> — il colore della selezione nel 3D — quello che il comando fa.</li></ul>
<h2>Grande · nella barra (28) · nell'albero (16)</h2><div class="riga">{celle}</div>
<h2>Nella barra, come sarà</h2><div class="ribbon">{barra}</div>
<h2>Nella barra, tema scuro</h2><div class="ribbon scuro">{barra.replace('design/', 'design/scuro/')}</div>
<h2>Quelle di adesso, per confronto</h2><div class="ribbon">{vecchia}</div>
</body></html>'''
    (R / 'design.html').write_text(html, encoding='utf-8')
    print('ok', len(I))


if __name__ == '__main__':
    main()
