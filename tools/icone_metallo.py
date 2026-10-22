"""Icone SteelCAD, stile «metallo» (23/10, dal riferimento del cliente): acciaio satinato con la luce vera, niente
contorni neri, blu elettrico pieno su quello che fa il comando, nello schizzo linee blu e maniglie quadrate bianche.
La geometria (lamiera con le pieghe vere, lastre) è quella di icone_design; qui cambia come si dipinge.

    python tools/icone_metallo.py            → app/ui/icons_nuove/metallo/*.svg e metallo.html
    python tools/icone_metallo.py --giallo   → la variante gialla (corpo giallo, contorno scuro, blu solo sulle facce
                                               che fa il comando) in icons_nuove/giallo/ e giallo.html
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icone_design as D  # noqa: E402

R = D.R
GIALLO = '--giallo' in sys.argv
NOME = 'giallo' if GIALLO else 'metallo'
OUT = R / NOME
ACC = ('#C27A00', '#FFE066') if GIALLO else ('#4E5864', '#F4F6F8')     # il corpo: in ombra → in luce
BLU = ('#0B35B8', '#4F8BFF') if GIALLO else ('#0A2A9E', '#5A86FF')
SPIGOLO = ('#1A2232', .9, .75) if GIALLO else (None, .55, .6)            # colore (None: dalla faccia), opacità, spessore
LUCE_G = (.22, .1) if GIALLO else (.32, .16)
D.ACCIAIO, D.AMBRA = ACC, BLU           # la lamiera prende questi colori
BLU_PIENO = '#1F4FE8'


class Tela:
    """Le facce dipinte con una sfumatura ciascuna (luce dall'alto a sinistra) e lo spigolo come una lama di luce."""

    def __init__(self):
        self.defs, self.n = [], 0

    def grad(self, c):
        self.n += 1
        i = f'g{self.n}'
        self.defs.append(f'<linearGradient id="{i}" x1="0" y1="0" x2="1" y2="1">'
                         f'<stop offset="0" stop-color="{D.mix(c, "#FFFFFF", LUCE_G[0])}"/><stop offset=".55" stop-color="{c}"/>'
                         f'<stop offset="1" stop-color="{D.mix(c, "#000000", LUCE_G[1])}"/></linearGradient>')
        return f'url(#{i})'


def svg(strati, margine=1.5, fit=()):
    """strati: liste di facce (dal più lontano) o funzioni (T, k, tela) → svg, nell'ordine dato."""
    tutte = [p for s in strati if isinstance(s, list) for f in s for p in f.pts] + list(fit)
    xs, ys = zip(*map(D.proietta, tutte))
    lato = 28 - 2 * margine
    k = min(lato / (max(xs) - min(xs)), lato / (max(ys) - min(ys)))
    ox, oy = 14 - k * (max(xs) + min(xs)) / 2, 14 - k * (max(ys) + min(ys)) / 2
    T = lambda p: (round((ox + k * D.proietta(p)[0]) * 4) / 4, round((oy + k * D.proietta(p)[1]) * 4) / 4)  # noqa: E731
    tela, out = Tela(), []
    for s in strati:
        if not isinstance(s, list):
            out.append(s(T, k, tela))
            continue
        for f in sorted(s, key=lambda f: f.prof):
            pp = [T(p) for p in f.pts]
            d = 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pp) + 'Z'
            op = f' opacity="{f.opacita}"' if getattr(f, 'opacita', None) else ''
            out.append(f'<path d="{d}" fill="{tela.grad(f.fill)}" stroke="{f.fill}" stroke-width=".3" stroke-linejoin="round"{op}/>')
            if f.spigoli:
                e = ''.join(f'M{pp[i][0]:g} {pp[i][1]:g} L{pp[j][0]:g} {pp[j][1]:g}' for i, j in f.spigoli)
                out.append(f'<path d="{e}" fill="none" stroke="{SPIGOLO[0] or D.mix(f.fill, "#1A2230", .55)}" stroke-opacity="{SPIGOLO[1]}" '
                           f'stroke-width="{SPIGOLO[2]}" stroke-linecap="round"{op}/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28"><defs>' + ''.join(tela.defs) + '</defs>'
            + ''.join(out) + '</svg>')


def blu(facce, opacita=None):
    for f in facce:
        f.fill = D.tinta(_normale(f), BLU)
        f.opacita = opacita
    return facce


def _normale(f):
    a, b, c = f.pts[0], f.pts[1], f.pts[2]
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return n if D.dot(n, D.V) > 0 else tuple(-x for x in n)


def tratteggio(a3, b3, colore='#FFFFFF', w=1.0, d='1.6 1.2'):
    return lambda T, k, tela: (lambda a, b: f'<path d="M{a[0]:g} {a[1]:g} L{b[0]:g} {b[1]:g}" stroke="{colore}" '
                                            f'stroke-width="{w}" stroke-dasharray="{d}" fill="none"/>')(T(a3), T(b3))


def freccia(punti3, w=1.6):
    """Una freccia blu lungo dei punti 3D, con la punta in fondo."""
    def f(T, k, tela):
        pp = [T(p) for p in punti3]
        (x0, y0), (x1, y1) = pp[-2], pp[-1]
        l = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / l, (y1 - y0) / l
        tip, bx, by = (x1, y1), x1 - ux * 2.8, y1 - uy * 2.8      # la punta sul punto, il gambo si ferma alla base
        a = (bx - uy * 1.9, by + ux * 1.9)
        b = (bx + uy * 1.9, by - ux * 1.9)
        d = 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pp[:-1] + [(bx + ux * .4, by + uy * .4)])
        return (f'<path d="{d}" stroke="{BLU_PIENO}" stroke-width="{w}" fill="none" stroke-linecap="round"/>'
                f'<path d="M{a[0]:.2f} {a[1]:.2f} L{tip[0]:.2f} {tip[1]:.2f} L{b[0]:.2f} {b[1]:.2f}Z" fill="{BLU_PIENO}"/>')
    return f


def dentro(facce):
    if GIALLO:
        for f in facce:
            n = D.nrm(_normale(f))
            if f.fill.startswith('#') and (n[1] > .95 or n[2] > .95) and f.fill != D.tinta(n, ACC):
                f.fill = D.tinta(n, ACC)
    return facce


I = {}
# Piega: la parete alzata in blu (dentro si vede), la freccia del verso
_arco = [(2 + 6.8 * math.cos(math.radians(a)), 9.5, 2 + 6.8 * math.sin(math.radians(a))) for a in range(-12, 67, 6)]
I['piega'] = svg([dentro(D.lamiera([('L', 9, True), ('A', 90, 1.8, True), ('L', 9, False)], 1.1, 8, inizio=(0, 10.8), dir0=-90)),
                  freccia(_arco)], fit=_arco)
# Flangia: una lastra larga e, sul bordo dietro, la flangia bassa in blu
I['flangia'] = svg([D.lamiera([('L', 3.2, True), ('A', 90, 0.9, True), ('L', 11, False)], 1.0, 13, inizio=(0, 5), dir0=-90,
                              giro=lambda p: (p[1], p[0], p[2]))])
# Orlo: il bordo arrotolato in blu
I['orlo'] = svg([D.lamiera([('L', 12, False), ('A', 180, 1.0, True), ('L', 3, True)], 1.0, 12, inizio=(0, 0))])
# Spiega: lo sviluppo a croce, il fondo in acciaio, le ali in blu, le linee di piega tratteggiate bianche
_q = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # noqa: E731
_sp = 0.9
I['spiega'] = svg([blu(D.lastra(_q(4.6, 0, 9.4, 4.6), 0, _sp, ACC)), blu(D.lastra(_q(0, 4.6, 4.6, 9.4), 0, _sp, ACC)),
                   D.lastra(_q(4.6, 4.6, 9.4, 9.4), 0, _sp, ACC),
                   blu(D.lastra(_q(9.4, 4.6, 14, 9.4), 0, _sp, ACC)), blu(D.lastra(_q(4.6, 9.4, 9.4, 14), 0, _sp, ACC)),
                   tratteggio((4.6, 4.6, _sp), (9.4, 4.6, _sp)), tratteggio((9.4, 4.6, _sp), (9.4, 9.4, _sp)),
                   tratteggio((9.4, 9.4, _sp), (4.6, 9.4, _sp)), tratteggio((4.6, 9.4, _sp), (4.6, 4.6, _sp))])
# Taglio: la lastra spessa con la tasca tolta (pareti blu) e il pezzo tolto che esce
I['taglio'] = svg([D.lastra([(0, 0), (14, 0), (14, 4), (9, 4), (9, 9), (14, 9), (14, 13), (0, 13)], 0, 3, ACC, pareti={2: BLU, 3: BLU}),
                   blu(D.lastra(_q(15.5, 5.5, 19.5, 9.5), -1.5, 1.5, ACC), opacita=.75)])


# Foro: un blocco in piedi col foro passante, dentro blu
def _foro(T, k, tela):
    cer = lambda y: [T((6 + 3.3 * math.cos(a / 24 * math.pi), y, 6 + 3.3 * math.sin(a / 24 * math.pi))) for a in range(48)]  # noqa: E731
    d = lambda pp: 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pp) + 'Z'  # noqa: E731
    da, dietro = d(cer(3.5)), d(cer(0))
    return (f'<clipPath id="h"><path d="{da}"/></clipPath><path d="{da}" fill="{tela.grad("#2A5CF0")}"/>'
            f'<path clip-path="url(#h)" d="{dietro}" fill="#0B237F"/>'
            f'<path d="{da}" fill="none" stroke="#FFFFFF" stroke-opacity=".7" stroke-width=".6"/>')


I['foro'] = svg([D.lastra(_q(0, 0, 12, 3.5), 0, 12, ACC), _foro])
if GIALLO:                                   # come nel riferimento: la lastra piana col foro, dentro blu
    def _foro_piano(T, k, tela):
        cer = lambda z: [T((6.5 + 3.4 * math.cos(a / 24 * math.pi), 6.5 + 3.4 * math.sin(a / 24 * math.pi), z)) for a in range(48)]  # noqa: E731
        d = lambda pp: 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pp) + 'Z'  # noqa: E731
        su, giu = d(cer(2.2)), d(cer(-1.2))
        return (f'<clipPath id="h"><path d="{su}"/></clipPath><path d="{su}" fill="{tela.grad("#1E5BE6")}"/>'
                f'<path clip-path="url(#h)" d="{giu}" fill="#4F8BFF"/><path d="{su}" fill="none" stroke="#1A2232" stroke-width=".75"/>')
    I['foro'] = svg([D.lastra(_q(0, 0, 13, 13), 0, 2.2, ACC), _foro_piano])
# Pezzo: un blocco d'acciaio col sopra blu
_pz = D.lastra(_q(0, 0, 11, 11), 0, 7, ACC)
_pz[0].fill = D.tinta((0, 0, 1), BLU)
I['pezzo'] = svg([_pz])
# Esploso: tre lastre staccate lungo l'asse di montaggio, quella di mezzo in blu
_c = (4.5, 4.5)
_ax = lambda z0, z1: tratteggio((*_c, z0), (*_c, z1), '#3A4452', 1, '1.8 1.3')  # noqa: E731
I['esploso'] = svg([D.lastra(_q(0, 0, 9, 9), 0, 1.2, ACC), _ax(1.2, 7.4),
                    blu(D.lastra(_q(0, 0, 9, 9), 7.4, 8.6, ACC)), _ax(8.6, 14.8),
                    D.lastra(_q(0, 0, 9, 9), 14.8, 16, ACC), _ax(16, 19)], fit=[(*_c, 19)])


def maniglia(x, y):
    return f'<rect x="{x - 2.75:g}" y="{y - 2.75:g}" width="5.5" height="5.5" rx="1" fill="#FFFFFF" stroke="{BLU_PIENO}" stroke-width="1.6"/>'


I['linea'] = D.schizzo(f'<path d="M6 22 L22 6" stroke="{BLU_PIENO}" stroke-width="2.2"/>' + maniglia(6, 22) + maniglia(22, 6))
I['rettangolo'] = D.schizzo(f'<rect x="5" y="7.5" width="18" height="13" stroke="{BLU_PIENO}" stroke-width="2.2"/>'
                            + ''.join(maniglia(x, y) for x in (5, 23) for y in (7.5, 20.5)))


# Quota: un canale a U in acciaio, le linee di richiamo scure e la quota blu con le frecce
def _quota(T, k, tela):
    a, b = T((0, 3, 6.6)), T((0, 3, 13))
    c, e = T((15.6, 3, 6.6)), T((15.6, 3, 13))
    m0, m1 = T((0, 3, 11.2)), T((15.6, 3, 11.2))
    lin = f'<path d="M{a[0]:g} {a[1]:g} L{b[0]:g} {b[1]:g} M{c[0]:g} {c[1]:g} L{e[0]:g} {e[1]:g}" stroke="#2B333D" stroke-width="1"/>'
    return lin + freccia([m0, m1], 1.5)(lambda p: p, k, tela) + freccia([m1, m0], 1.5)(lambda p: p, k, tela)


I['quota'] = svg([D.lamiera([('L', 4.6, False), ('A', 90, 0.8, False), ('L', 14, False), ('A', 90, 0.8, False), ('L', 4.6, False)],
                            1.3, 3, inizio=(0, 6.2), dir0=-90), _quota])
# Specchia: una staffa in acciaio, l'asse, la sua copia specchiata in blu
_st = [('L', 6, False), ('A', 90, 0.9, False), ('L', 7, False)]
_st_b = [('L', 6, True), ('A', 90, 0.9, True), ('L', 7, True)]
I['specchia'] = svg([D.lamiera(_st, 1.6, 6, inizio=(-11, 0)), tratteggio((0, 3, -3), (0, 3, 11), '#3A4452', 1.1, '3 1.4 .8 1.4'),
                     dentro(D.lamiera(_st_b, 1.6, 6, inizio=(-11, 0), giro=lambda p: (-p[0], p[1], p[2])))])

NOMI = D.NOMI


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for k, v in I.items():
        (OUT / f'{k}.svg').write_text(v, encoding='utf-8')
    celle = ''.join(f'<div class="c"><img class="g" src="{NOME}/{k}.svg"><img class="p" src="{NOME}/{k}.svg">'
                    f'<span>{it}</span></div>' for k, it, _ in NOMI)
    barra = ''.join(f'<button><img src="{NOME}/{k}.svg"><span>{it}</span></button>' for k, it, _ in NOMI)
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Icone metallo</title><style>
body {{ font: 13px/1.45 "Segoe UI", system-ui, sans-serif; margin: 28px 40px; background: #EEF0F3; color: #1C2228; }}
h1 {{ font-size: 20px; margin: 0; }} h2 {{ font-size: 14px; margin: 22px 0 8px; color: #4A5560; font-weight: 600; }}
.riga {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }}
.c {{ display: grid; justify-items: center; gap: 10px; padding: 16px 4px 10px; border-radius: 10px; background: #fff; border: 1px solid #DDE1E6; }}
.riga.nero .c {{ background: #0B0D10; border-color: #0B0D10; }} .riga.nero .c span {{ color: #C9D0D7; }}
.c .g {{ width: 120px; height: 120px; }} .c .p {{ width: 28px; height: 28px; }} .c span {{ font-size: 12px; color: #3A4552; }}
.ribbon {{ display: flex; gap: 2px; padding: 6px 8px; background: #F7F8FA; border: 1px solid #D5DAE0; border-radius: 6px; }}
.ribbon button {{ all: unset; display: grid; justify-items: center; gap: 3px; width: 66px; padding: 6px 0 4px; border-radius: 4px; font-size: 11px; color: #2B333D; }}
.ribbon img {{ width: 28px; height: 28px; }} .ribbon.scuro {{ background: #1E232A; border-color: #2C333C; }} .ribbon.scuro button {{ color: #D5DBE1; }}
</style></head><body><h1>Icone SteelCAD: stile {"giallo" if GIALLO else "metallo"} (dal tuo riferimento)</h1>
<h2>Su fondo nero, come il riferimento</h2><div class="riga nero">{celle}</div>
<h2>Su fondo chiaro</h2><div class="riga">{celle}</div>
<h2>Nella barra, tema chiaro</h2><div class="ribbon">{barra}</div>
<h2>Nella barra, tema scuro</h2><div class="ribbon scuro">{barra}</div>
</body></html>'''
    (R / f'{NOME}.html').write_text(html, encoding='utf-8')
    print('ok', len(I))


if __name__ == '__main__':
    main()
