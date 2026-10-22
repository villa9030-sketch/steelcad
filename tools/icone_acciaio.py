"""Le 70 icone SteelCAD in stile «acciaio» (23/10: scelto dal cliente tra metallo e giallo).

Regole (le stesse delle 12 di prova in icone_metallo):
- pezzi e lamiera in 3D: acciaio satinato, in blu quello che fa il comando;
- schizzo: tratto blu, maniglie quadrate bianche;
- vincoli: la geometria in grigio, il vincolo in blu;
- vista, file e azioni: forme piatte in acciaio con un accento blu.

    python tools/icone_acciaio.py   → app/ui/icons_nuove/acciaio/*.svg e app/ui/icons_nuove/acciaio.html
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icone_metallo as M  # noqa: E402

D = M.D
R = M.R
OUT = R / 'acciaio'
B = M.BLU_PIENO                 # il blu pieno
G = '#8591A0'                   # la geometria grigia (vincoli, linee di riferimento)
BORDO = '#5D6773'               # il bordo delle forme d'acciaio piatte
ACC, BLU, _q = M.ACC, M.BLU, M._q
GRAD = ('<linearGradient id="ac" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F8FAFB"/>'
        '<stop offset=".55" stop-color="#CDD4DB"/><stop offset="1" stop-color="#8E99A6"/></linearGradient>'
        '<linearGradient id="bl" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6D95FF"/>'
        f'<stop offset=".55" stop-color="{B}"/><stop offset="1" stop-color="#0A2A9E"/></linearGradient>')


def piatto(corpo):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" fill="none" stroke-linecap="round" '
            f'stroke-linejoin="round"><defs>{GRAD}</defs>{corpo}</svg>')


def H(x, y, l=4.4):
    """La maniglia dello schizzo, un po' più piccola che nelle prime prove: non deve coprire la figura."""
    return f'<rect x="{x - l / 2:g}" y="{y - l / 2:g}" width="{l:g}" height="{l:g}" rx=".9" fill="#FFFFFF" stroke="{B}" stroke-width="1.5"/>'


def fr(pts, w=2.0):
    """Freccia blu piatta lungo dei punti dello schermo."""
    return M.freccia(pts, w)(lambda p: p, 1, None)


def arco(cx, cy, r, a0, a1, n=16, ry=None):
    ry = ry or r
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy - ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def d(pts, chiudi=False):
    return 'M' + ' L'.join(f'{x:.2f} {y:.2f}' for x, y in pts) + ('Z' if chiudi else '')


def linea(pts, colore=B, w=2.2, extra=''):
    return f'<path d="{d(pts)}" stroke="{colore}" stroke-width="{w}"{extra}/>'


def sopra(pts3, colore=B, w=1.6, riempi=None):
    """Una figura disegnata su una faccia del pezzo (punti 3D)."""
    def f(T, k, tela):
        pp = [T(p) for p in pts3]
        r = f' fill="{riempi}" fill-opacity=".3"' if riempi else ' fill="none"'
        return f'<path d="{d(pp, True)}" stroke="{colore}" stroke-width="{w}" stroke-linejoin="round"{r}/>'
    return f


def fantasma(facce, op=.4):
    for f in facce:
        f.opacita = op
    return facce


def a_schermo(svg_testo):
    return lambda T, k, tela: svg_testo


I = {}
# ------------------------------------------------------------------------------------------------- le 12 già viste
for chiave, _, file in M.NOMI:
    I[file] = M.I[chiave]

# ------------------------------------------------------------------------------------------------- Disegno
I['rect_center'] = piatto(f'<rect x="5" y="7.5" width="18" height="13" stroke="{B}" stroke-width="2.2"/>'
                          f'<path d="M14 14 L23 7.5" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>' + H(14, 14) + H(23, 7.5))
I['circle'] = piatto(f'<circle cx="13" cy="15" r="9" stroke="{B}" stroke-width="2.2"/>'
                     f'<path d="M13 15 L19.4 8.6" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>' + H(13, 15) + H(19.4, 8.6))
_a3 = arco(14, 20, 10, 165, 15)
I['arc3'] = piatto(linea(_a3) + H(*_a3[0]) + H(*_a3[8]) + H(*_a3[-1]))
_at = arco(13.5, 12.5, 7.5, -90, 90)
I['arc_tangent'] = piatto(linea([(3, 20), (13.5, 20)], G, 2.2) + linea(_at) + H(13.5, 20) + H(*_at[-1]))
I['slot'] = piatto(f'<path d="M9 9 H19 A5 5 0 0 1 19 19 H9 A5 5 0 0 1 9 9 Z" stroke="{B}" stroke-width="2.2"/>'
                   f'<path d="M9 14 H19" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>' + H(9, 14) + H(19, 14))
_esa = [(14 + 9.5 * math.cos(math.radians(30 + 60 * i)), 14 - 9.5 * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
I['polygon'] = piatto(f'<path d="{d(_esa, True)}" stroke="{B}" stroke-width="2.2"/>'
                      f'<path d="M14 14 L{_esa[0][0]:.2f} {_esa[0][1]:.2f}" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>'
                      + H(14, 14) + H(*_esa[0]))
I['point'] = piatto(f'<path d="M14 4 V10 M14 18 V24 M4 14 H10 M18 14 H24" stroke="{G}" stroke-width="1.6"/>'
                    f'<rect x="10" y="10" width="8" height="8" rx="1.4" fill="#FFFFFF" stroke="{B}" stroke-width="2.2"/>')
I['text'] = piatto(f'<path d="M6 6.5 H22 V10.5 H16.2 V23 H11.8 V10.5 H6 Z" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>'
                   f'<path d="M4 25 H24" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>')
I['construction'] = piatto(f'<path d="M5 23 L23 5" stroke="{B}" stroke-width="2" stroke-dasharray="3.2 2.4"/>'
                           f'<rect x="2.6" y="20.6" width="4.8" height="4.8" rx="1" fill="#FFFFFF" stroke="{B}" stroke-width="1.4" stroke-dasharray="1.4 1"/>'
                           f'<rect x="20.6" y="2.6" width="4.8" height="4.8" rx="1" fill="#FFFFFF" stroke="{B}" stroke-width="1.4" stroke-dasharray="1.4 1"/>')
I['sketch'] = M.svg([D.lastra(_q(0, 0, 14, 12), 0, 1.2, ACC), sopra([(3, 3, 1.2), (11, 3, 1.2), (11, 9, 1.2), (3, 9, 1.2)])])
I['project'] = M.svg([D.lastra(_q(0, 0, 10, 10), 0, 6, ACC), sopra([(1.8, 1.8, 6), (8.2, 1.8, 6), (8.2, 8.2, 6), (1.8, 8.2, 6)], riempi=B)])
I['measure'] = piatto('<g transform="rotate(-35 14 14)"><rect x="2" y="10" width="24" height="8" rx="1.2" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                      + ''.join(f'<path d="M{x} 10 V{13.8 if i % 2 else 15.4}" stroke="{B}" stroke-width="1.3"/>' for i, x in enumerate(range(5, 25, 3)))
                      + '</g>')
I['select'] = piatto(f'<rect x="3.5" y="3.5" width="13" height="13" rx="1" stroke="{B}" stroke-width="1.4" stroke-dasharray="2 1.6"/>'
                     '<path d="M10 9 L22 14.5 L16.6 16.3 L20.6 22.4 L18.2 24 L14.2 17.9 L10.4 21.8 Z" fill="url(#ac)" stroke="#2B333D" stroke-width="1.1"/>')

# ------------------------------------------------------------------------------------------------- Modifica
I['offset'] = piatto(f'<path d="M12 24 V15 A3 3 0 0 1 15 12 H24" stroke="{G}" stroke-width="2.2"/>'
                     f'<path d="M5 24 V12 A7 7 0 0 1 12 5 H24" stroke="{B}" stroke-width="2.2"/>'
                     f'<path d="M15.5 9.5 V7.5 M15.5 9.5" stroke="{G}" stroke-width="1"/>' + fr([(18.5, 11), (18.5, 6.2)], 1.2))
I['trim'] = piatto(f'<path d="M4 15 H24" stroke="{G}" stroke-width="2"/>'
                   f'<path d="M14 15 V24" stroke="{B}" stroke-width="2.2"/>'
                   f'<path d="M14 13 V4" stroke="{B}" stroke-width="1.6" stroke-dasharray="2 1.8" opacity=".55"/>'
                   f'<path d="M17 5 L22 10 M22 5 L17 10" stroke="#2B333D" stroke-width="1.6"/>')
I['extend'] = piatto(f'<path d="M23 4 V24" stroke="{G}" stroke-width="2"/>'
                     f'<path d="M4 14 H12" stroke="{B}" stroke-width="2.2"/>'
                     f'<path d="M12 14 H17.5" stroke="{B}" stroke-width="1.8" stroke-dasharray="2 1.6"/>' + fr([(12, 14), (22.5, 14)], 0.01) + H(4, 14))
I['fillet'] = piatto(f'<path d="M5 24 V13 M15 5 H24" stroke="{G}" stroke-width="2"/>'
                     f'<path d="M5 13 V5 H15" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>'
                     f'<path d="M5 15 A10 10 0 0 1 15 5" stroke="{B}" stroke-width="2.4"/>')
I['chamfer'] = piatto(f'<path d="M5 24 V13 M15 5 H24" stroke="{G}" stroke-width="2"/>'
                      f'<path d="M5 13 V5 H15" stroke="{G}" stroke-width="1.2" stroke-dasharray="2 1.6"/>'
                      f'<path d="M5 14 L14 5" stroke="{B}" stroke-width="2.4"/>' + H(5, 14) + H(14, 5))
I['copy'] = M.svg([D.lastra(_q(0, 0, 8, 8), 0, 2, ACC), M.blu(D.lastra(_q(5.5, 5.5, 13.5, 13.5), 0, 2, ACC))])
I['move'] = M.svg([fantasma(D.lastra(_q(0, 0, 7, 7), 0, 2, ACC)), M.freccia([(3.5, 3.5, 2), (10.2, 10.2, 2)], 1.6),
                   M.blu(D.lastra(_q(8, 8, 15, 15), 0, 2, ACC))])
_serie = sorted(((x, y) for x in (0, 5, 10) for y in (0, 5)), key=lambda p: 0.62 * p[0] + p[1])
I['pattern_rect'] = M.svg([D.lastra(_q(x, y, x + 3.4, y + 3.4), 0, 1.6, ACC) if (x, y) == (0, 0) else
                           M.blu(D.lastra(_q(x, y, x + 3.4, y + 3.4), 0, 1.6, ACC)) for x, y in _serie])
I['delete'] = piatto('<path d="M7.5 9 H20.5 L19.2 24 H8.8 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                     '<rect x="5" y="6" width="18" height="3" rx="1" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                     '<path d="M11.5 4 H16.5 V6 H11.5 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                     f'<path d="M11.5 12 V21 M14 12 V21 M16.5 12 V21" stroke="{B}" stroke-width="1.4"/>')

# ------------------------------------------------------------------------------------------------- Vincoli
I['c_coincident'] = piatto(f'<path d="M4 22 L14 14 M14 14 L24 18" stroke="{G}" stroke-width="2"/>'
                           f'<circle cx="14" cy="14" r="4" fill="url(#bl)" stroke="#FFFFFF" stroke-width="1.2"/>')
I['c_collinear'] = piatto(f'<path d="M3 23 L25 5" stroke="{B}" stroke-width="1.3" stroke-dasharray="2 1.8"/>'
                          f'<path d="M4.5 21.8 L10 17.3 M18 10.7 L23.5 6.2" stroke="{G}" stroke-width="2.6"/>' + H(10, 17.3, 3.8) + H(18, 10.7, 3.8))
I['c_parallel'] = piatto(f'<path d="M4 18 L16 6 M12 22 L24 10" stroke="{G}" stroke-width="2"/>'
                         f'<path d="M15.5 17.5 L19.5 13.5 M18.5 20.5 L22.5 16.5" stroke="{B}" stroke-width="2.2"/>')
I['c_perpendicular'] = piatto(f'<path d="M6 4 V22 H24" stroke="{G}" stroke-width="2"/>'
                              f'<path d="M6 15 H13 V22" stroke="{B}" stroke-width="2.2" fill="{B}" fill-opacity=".14"/>')
I['c_tangent'] = piatto(f'<circle cx="14" cy="15.5" r="7" stroke="{G}" stroke-width="2"/>'
                        f'<path d="M3 8.5 H25" stroke="{B}" stroke-width="2.2"/>' + H(14, 8.5))
I['c_symmetry'] = piatto(f'<path d="M14 3 V25" stroke="{G}" stroke-width="1.4" stroke-dasharray="3 1.4 .8 1.4"/>'
                         f'<path d="M7 14 H21" stroke="{B}" stroke-width="1.3" stroke-dasharray="2 1.6"/>' + H(6, 14) + H(22, 14))
I['c_fix'] = piatto(f'<path d="M3 24 H25" stroke="{G}" stroke-width="2"/>'
                    '<path d="M9.5 12 V9 A4.5 4.5 0 0 1 18.5 9 V12" stroke="#7D8895" stroke-width="2.4"/>'
                    '<rect x="7" y="12" width="14" height="9.5" rx="1.8" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>'
                    '<circle cx="14" cy="16.2" r="1.5" fill="#FFFFFF"/><path d="M14 17 V19" stroke="#FFFFFF" stroke-width="1.4"/>')
_pa = arco(5, 22, 11, 0, 50)
I['plane_angle'] = piatto(f'<path d="M5 22 H25 M5 22 L19 5.5" stroke="{G}" stroke-width="2"/>' + fr(_pa, 1.8) + H(5, 22))

# ------------------------------------------------------------------------------------------------- Lamiera
I['refold'] = M.svg([D.lamiera([('L', 7, True), ('A', 90, 1.2, True), ('L', 11, False), ('A', 90, 1.2, True), ('L', 7, True)],
                               1.0, 8, inizio=(0, 8.2), dir0=-90)])
I['convert_sheet'] = M.svg([fantasma(D.lastra(_q(0, 0, 10, 9), 0, 7, ACC), .35),
                            D.lamiera([('L', 10, True), ('A', -90, 0.8, True), ('L', 7, True)], 0.9, 9, inizio=(-0.2, 7.5))])
I['perforate'] = M.svg([D.lastra(_q(0, 0, 14, 12), 0, 1, ACC)] + [M.blu(D.lastra(_q(2.5, y, 11.5, y + 1.3), 1, 1.9, ACC)) for y in (2.2, 5.2, 8.2)])
I['bendtable'] = piatto('<rect x="4" y="5" width="20" height="18" rx="2" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                        '<path d="M4 7 A2 2 0 0 1 6 5 H22 A2 2 0 0 1 24 7 V10 H4 Z" fill="url(#bl)"/>'
                        '<path d="M4 14.5 H24 M4 19 H24 M11 10 V23" stroke="#5D6773" stroke-width="1"/>')
_L = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
I['extrude'] = M.svg([D.lastra(_L, -1, 0, ACC), M.blu(D.lastra(_L, 0, 8, ACC), opacita=.92),
                      M.freccia([(12.5, 2, 0), (12.5, 2, 9.5)], 1.6)], fit=[(12.5, 2, 9.5)])
I['section'] = M.svg([D.lastra(_q(0, 0, 12, 6), 0, 9, ACC, pareti={2: BLU}), fantasma(D.lastra(_q(0, 6, 12, 12), 0, 9, ACC), .22)])
I['hole'] = M.I['foro']

# ------------------------------------------------------------------------------------------------- 3D, vista e assiemi
_j = D.lastra(_q(0, 0, 10, 10), 0, 3, ACC)
_j[0].fill = D.tinta((0, 0, 1), BLU)
_ax = lambda p, z0, z1: M.tratteggio((*p, z0), (*p, z1), '#3A4452', 1, '1.8 1.3')  # noqa: E731
I['joint'] = M.svg([_j, _ax((10, 10), 3, 8), _ax((0, 10), 3, 8), _ax((10, 0), 3, 8), D.lastra(_q(0, 0, 10, 10), 8, 11, ACC)])
I['fastener'] = piatto('<path d="M7 4 H21 L23 7 L21 10 H7 L5 7 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                       '<rect x="10.5" y="10" width="7" height="15" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                       + ''.join(f'<path d="M10.5 {y} L17.5 {y - 1.6}" stroke="#5D6773" stroke-width=".9"/>' for y in (13, 15.5, 22.5, 25))
                       + '<path d="M6.5 16.5 H21.5 L23 19 L21.5 21.5 H6.5 L5 19 Z" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>')
_staffe = (f'<path d="M3 9 V3 H9 M19 3 H25 V9 M25 19 V25 H19 M9 25 H3 V19" stroke="{B}" stroke-width="2.4"/>')
I['fit'] = M.svg([D.lastra(_q(0, 0, 8, 8), 0, 8, ACC), a_schermo(_staffe)], margine=6)
I['lookat'] = M.svg([D.lastra(_q(0, 0, 9, 9), 0, 9, ACC, pareti={2: BLU}), M.freccia([(4.5, 17, 4.5), (4.5, 10.5, 4.5)], 1.8)],
                    fit=[(4.5, 17, 4.5)])
_orb = arco(14, 15, 12, 200, -20, 24, ry=5)
I['orbit'] = M.svg([D.lastra(_q(0, 0, 8, 8), 0, 8, ACC), a_schermo(fr(_orb, 2))], margine=5)
_p4 = ''.join(fr(pp, 2) for pp in ([(14, 14), (14, 3.5)], [(14, 14), (14, 24.5)], [(14, 14), (3.5, 14)], [(14, 14), (24.5, 14)]))
I['pan'] = piatto(_p4 + '<circle cx="14" cy="14" r="3" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>')
_lente = ('<path d="M17.5 17.5 L24 24" stroke="#5D6773" stroke-width="5"/><path d="M17.5 17.5 L24 24" stroke="url(#ac)" stroke-width="3.4"/>'
          '<circle cx="11.5" cy="11.5" r="8" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
          '<circle cx="11.5" cy="11.5" r="5.6" fill="url(#bl)"/><path d="M8.4 9.2 A4 4 0 0 1 11 7.6" stroke="#FFFFFF" stroke-width="1.2" opacity=".8"/>')
I['zoom'] = piatto(_lente + '<path d="M11.5 9 V14 M9 11.5 H14" stroke="#FFFFFF" stroke-width="1.6"/>')
I['search'] = piatto(_lente)
I['eye'] = M.svg([M.blu(D.lastra(_q(3, 3, 7, 7), 2.5, 6.5, ACC)), fantasma(D.lastra(_q(0, 0, 10, 10), 0, 9, ACC), .33)])
I['home'] = piatto('<path d="M6.5 13 V24 H21.5 V13" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                   '<path d="M3 14 L14 4 L25 14 L22.5 16 L14 8.5 L5.5 16 Z" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>'
                   '<rect x="11.5" y="17" width="5" height="7" fill="#5D6773"/>')
I['params'] = piatto(''.join(f'<rect x="4" y="{y - 1.5}" width="20" height="3" rx="1.5" fill="url(#ac)" stroke="#5D6773" stroke-width=".9"/>'
                             f'<rect x="{x - 2.5}" y="{y - 3.5}" width="5" height="7" rx="1.2" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>'
                             for x, y in ((10, 7), (18, 14), (8, 21))))
_den = []
for i in range(8):
    c = i * 45
    for a, r in ((c - 13, 8.6), (c - 8, 11.2), (c + 8, 11.2), (c + 13, 8.6)):
        _den.append((14 + r * math.cos(math.radians(a)), 14 + r * math.sin(math.radians(a))))
I['settings'] = piatto(f'<path d="{d(_den, True)}" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                       '<circle cx="14" cy="14" r="4.2" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/><circle cx="14" cy="14" r="1.6" fill="#FFFFFF"/>')
I['library'] = piatto('<rect x="4" y="6" width="5" height="18" rx=".8" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                      '<rect x="10" y="4" width="5" height="20" rx=".8" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>'
                      '<rect x="15.5" y="7" width="5" height="17.5" rx=".8" transform="rotate(-14 18 24)" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                      '<path d="M3 25 H25" stroke="#5D6773" stroke-width="1.6"/>')
I['list'] = piatto('<rect x="4" y="4" width="20" height="20" rx="2.5" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                   + ''.join(f'<rect x="7" y="{y - 1.5}" width="3" height="3" rx=".6" fill="{B}"/><path d="M12.5 {y} H21" stroke="#5D6773" stroke-width="1.6"/>'
                             for y in (9, 14, 19)))

# ------------------------------------------------------------------------------------------------- File e azioni
_foglio = '<path d="M6 3 H17 L22 8 V25 H6 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/><path d="M17 3 V8 H22" fill="#E9EDF1" stroke="#5D6773" stroke-width="1"/>'
I['new'] = piatto(_foglio + '<circle cx="20" cy="20" r="6" fill="url(#bl)" stroke="#FFFFFF" stroke-width="1.2"/>'
                  '<path d="M20 17 V23 M17 20 H23" stroke="#FFFFFF" stroke-width="1.8"/>')
I['open'] = piatto('<path d="M3 8 A1.5 1.5 0 0 1 4.5 6.5 H11 L13 9 H23.5 A1.5 1.5 0 0 1 25 10.5 V22 A1.5 1.5 0 0 1 23.5 23.5 H4.5 A1.5 1.5 0 0 1 3 22 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                   '<path d="M6 13 H26 L23.5 23.5 H3.5 Z" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>')
I['save'] = piatto('<path d="M4 6 A2 2 0 0 1 6 4 H20 L24 8 V22 A2 2 0 0 1 22 24 H6 A2 2 0 0 1 4 22 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                   '<rect x="8.5" y="4" width="10" height="6.5" fill="url(#bl)" stroke="#0A2A9E" stroke-width=".8"/>'
                   '<rect x="7.5" y="14.5" width="13" height="9.5" rx="1" fill="#FFFFFF" stroke="#5D6773" stroke-width="1"/>'
                   '<path d="M10 18 H18 M10 21 H16" stroke="#9AA5B1" stroke-width="1"/>')
I['export'] = piatto('<path d="M4 3 H14 L18.5 7.5 V25 H4 Z" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                     '<path d="M14 3 V7.5 H18.5" fill="#E9EDF1" stroke="#5D6773" stroke-width="1"/>' + fr([(10, 16), (25.5, 16)], 2.4))
I['dxf'] = piatto(_foglio + '<rect x="2.5" y="14" width="19" height="8" rx="1.5" fill="url(#bl)"/>'
                  '<text x="12" y="20.4" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-weight="700" font-size="6.4" fill="#FFFFFF">DXF</text>')
I['undo'] = piatto(fr(arco(14, 16, 8.5, -50, 175, 24), 2.6))
I['redo'] = piatto(fr(arco(14, 16, 8.5, 230, 5, 24), 2.6))
I['finish'] = piatto('<circle cx="14" cy="14" r="11" fill="url(#ac)" stroke="#5D6773" stroke-width="1"/>'
                     '<circle cx="14" cy="14" r="8" fill="url(#bl)"/><path d="M9.5 14.5 L12.8 17.6 L18.8 10.8" stroke="#FFFFFF" stroke-width="2.4"/>')

GRUPPI = {'Disegno': ['line', 'rect', 'rect_center', 'circle', 'arc3', 'arc_tangent', 'slot', 'polygon', 'point', 'text',
                      'construction', 'sketch', 'project', 'dimension', 'measure', 'select'],
          'Modifica': ['offset', 'trim', 'extend', 'fillet', 'chamfer', 'mirror', 'copy', 'move', 'pattern_rect', 'delete', 'cut'],
          'Vincoli': ['c_coincident', 'c_collinear', 'c_parallel', 'c_perpendicular', 'c_tangent', 'c_symmetry', 'c_fix', 'plane_angle'],
          'Lamiera': ['fold', 'flange', 'hem', 'flat', 'refold', 'convert_sheet', 'perforate', 'hole', 'bendtable', 'extrude', 'section'],
          '3D, vista e assiemi': ['box', 'joint', 'explode', 'fastener', 'fit', 'lookat', 'orbit', 'pan', 'zoom', 'search', 'eye',
                                  'home', 'params', 'settings', 'library', 'list'],
          'File e azioni': ['new', 'open', 'save', 'export', 'dxf', 'undo', 'redo', 'finish']}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vecchie = sorted(p.stem for p in (R.parent / 'icons').glob('*.svg'))
    manca = [n for n in vecchie if n not in I]
    if manca:
        raise SystemExit(f'Mancano: {manca}')
    for n in vecchie:
        (OUT / f'{n}.svg').write_text(I[n], encoding='utf-8')
    src = (Path(__file__).resolve().parent / 'icone_nuove.py').read_text(encoding='utf-8')
    i = src.index('nomi_it = {'); j = src.index('}', i)
    nomi_it = eval(src[i + len('nomi_it = '):j + 1])       # i nomi italiani, dalla pagina di prima
    blocchi = []
    for g, nomi in GRUPPI.items():
        celle = ''.join(f'<div class="c"><img class="g" src="acciaio/{n}.svg"><div class="pp"><img src="../icons/{n}.svg" class="old">'
                        f'<span>→</span><img src="acciaio/{n}.svg"></div><b>{nomi_it.get(n, n)}</b></div>' for n in nomi)
        barra = ''.join(f'<img src="acciaio/{n}.svg" title="{nomi_it.get(n, n)}">' for n in nomi)
        blocchi.append(f'<h2>{g}</h2><div class="riga">{celle}</div><div class="ribbon">{barra}</div><div class="ribbon scuro">{barra}</div>')
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Icone acciaio</title><style>
body {{ font: 13px/1.45 "Segoe UI", system-ui, sans-serif; margin: 28px 40px; background: #EEF0F3; color: #1C2228; }}
h1 {{ font-size: 20px; margin: 0; }} h2 {{ font-size: 15px; margin: 26px 0 10px; }}
.riga {{ display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px; }}
.c {{ display: grid; justify-items: center; gap: 8px; padding: 14px 4px 10px; border-radius: 10px; background: #fff; border: 1px solid #DDE1E6; }}
.c .g {{ width: 84px; height: 84px; }} .c b {{ font-weight: 500; font-size: 12px; color: #3A4552; }}
.pp {{ display: flex; align-items: center; gap: 8px; color: #A0A9B2; }} .pp img {{ width: 28px; height: 28px; }} .pp .old {{ opacity: .7; }}
.ribbon {{ display: flex; gap: 22px; margin-top: 8px; padding: 10px 14px; background: #F7F8FA; border: 1px solid #D5DAE0; border-radius: 6px; flex-wrap: wrap; }}
.ribbon img {{ width: 28px; height: 28px; }} .ribbon.scuro {{ background: #1E232A; border-color: #2C333C; }}
</style></head><body><h1>Icone SteelCAD in acciaio: tutte le 70</h1>
<p style="color:#5B6670;margin:4px 0 0">In ogni scheda: grande, poi quella di adesso → la nuova a grandezza vera (28 px). Sotto ogni gruppo, come stanno in barra (chiaro e scuro).</p>
{''.join(blocchi)}</body></html>'''
    (R / 'acciaio.html').write_text(html, encoding='utf-8')
    print('ok', len(vecchie))


if __name__ == '__main__':
    main()
