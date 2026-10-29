"""Tre stili di icone a confronto, su 12 comandi campione (23/10: «non mi piacciono, puoi fare di meglio»).

A) isometrico ombreggiato (come i CAD: facce in tre toni, il risultato del comando in blu)
B) pieno a due toni (forme piene morbide, grigio ardesia + blu, senza contorni)
C) tratto deciso (contorno spesso, riempimenti chiari, accento blu)

    python tools/icone_proposte.py   → app/ui/icons_nuove/proposte.html (+ le svg in icons_nuove/proposte/)
"""
import math
from pathlib import Path

R = Path(__file__).resolve().parents[1] / 'app' / 'ui' / 'icons_nuove'
OUT = R / 'proposte'

# ------------------------------------------------------------------------------------------- A: isometrico
# vista dall'alto, davanti a destra: si vedono il sopra e le facce verso +x e +y; il disegno si adatta al riquadro
GRIGI = {'top': '#F1F4F7', 'sx': '#C6D0DA', 'dx': '#97A6B6'}
BLU = {'top': '#A9D0F8', 'sx': '#5E9FE6', 'dx': '#2F72C2'}
LINEA = '#26303B'
C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))


def P(p):
    x, y, z = p
    return ((x - y) * C30, (x + y) * S30 - z)


def prisma(poly, z0, z1, col, pareti=None):
    """Un poligono (antiorario) estruso da z0 a z1: le facce visibili, ognuna (profondità, tipo, punti, colore)."""
    out = [(sum(x + y for x, y in poly) / len(poly) + z1 * 2, 'poly', [(x, y, z1) for x, y in poly], col['top'])]
    for i, (a, b) in enumerate(zip(poly, poly[1:] + poly[:1])):
        nx, ny = b[1] - a[1], a[0] - b[0]
        if nx + ny <= 1e-9:
            continue
        c = (pareti or {}).get(i, col)
        tono = 'dx' if nx > ny else 'sx'
        d = (a[0] + b[0] + a[1] + b[1]) / 2 + (z0 + z1)
        out.append((d, 'poly', [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], c[tono]))
    return out


def blocco(x0, y0, z0, x1, y1, z1, col):
    return prisma([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, col)


def svgA(el, dopo=()):
    """Ordina dal più lontano, adatta al riquadro 24 (margine 2) e scrive l'svg."""
    pts = [P(p) for e in el for p in e[2]] + [P(p) for e in dopo for p in e[1:3] if e[0] == 'line']
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    k = min(20 / (max(xs) - min(xs)), 20 / (max(ys) - min(ys)))
    ox, oy = 12 - k * (max(xs) + min(xs)) / 2, 12 - k * (max(ys) + min(ys)) / 2
    T = lambda p: (ox + k * P(p)[0], oy + k * P(p)[1])   # noqa: E731
    out = []
    for e in sorted(el, key=lambda e: e[0]):
        pp = ' '.join(f'{x:.2f},{y:.2f}' for x, y in map(T, e[2]))
        out.append(f'<polygon points="{pp}" fill="{e[3]}" stroke="{LINEA}" stroke-width="1" stroke-linejoin="round"/>')
    for e in dopo:
        if e[0] == 'line':
            (x1, y1), (x2, y2) = T(e[1]), T(e[2])
            out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" {e[3]}/>')
        elif e[0] == 'foro':                       # centro, raggio, spessore: il foro passante visto dall'alto
            (cx, cy), r, t = T(e[1]), e[2] * k * math.sqrt(2), e[3] * k
            rx, ry = r * C30, r * S30
            out.append(f'<clipPath id="f"><ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}"/></clipPath>'
                       f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{BLU["sx"]}"/>'
                       f'<ellipse clip-path="url(#f)" cx="{cx:.2f}" cy="{cy + t:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="#1E2630"/>'
                       f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="none" stroke="{LINEA}" stroke-width="1"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' + ''.join(out) + '</svg>'


TRAT = f'stroke="#2F7DE1" stroke-width="1.3" stroke-dasharray="1.8 1.3" stroke-linecap="round"'
A = {}
A['piega'] = svgA(blocco(0, 0, 0, 12, 9, 1.2, GRIGI) + blocco(12, 0, 0, 13.2, 9, 10, BLU))
A['flangia'] = svgA(blocco(0, 0, 0, 12, 10, 1.2, GRIGI) + blocco(0, -1.2, 0, 12, 0, 8, BLU))
A['orlo'] = svgA(blocco(0, 0, 0, 12, 9, 1.2, GRIGI) + blocco(12, 0, 0, 13.2, 9, 4.2, BLU) + blocco(7, 0, 3.0, 12, 9, 4.2, BLU))
A['spiega'] = svgA(blocco(0, 0, 0, 14, 11, 0.9, GRIGI),
                   [('line', (4.7, 0, 0.9), (4.7, 11, 0.9), TRAT), ('line', (9.3, 0, 0.9), (9.3, 11, 0.9), TRAT)])
A['taglio'] = svgA(prisma([(0, 0), (12, 0), (12, 5.5), (6.5, 5.5), (6.5, 11), (0, 11)], 0, 1.4, GRIGI, {2: BLU, 3: BLU}),
                   [('line', (12, 5.5, 1.4), (12, 11, 1.4), TRAT), ('line', (6.5, 11, 1.4), (12, 11, 1.4), TRAT)])
A['foro'] = svgA(blocco(0, 0, 0, 12, 12, 1.6, GRIGI), [('foro', (6, 6, 1.6), 3.4, 1.6)])
A['pezzo'] = svgA(blocco(0, 0, 0, 10, 10, 7, GRIGI) + [(99, 'poly', [(0, 0, 7), (10, 0, 7), (10, 10, 7), (0, 10, 7)], BLU['top'])])
A['esploso'] = svgA(blocco(0, 0, 0, 10, 10, 2, GRIGI) + blocco(0, 0, 9, 10, 10, 11, BLU),
                    [('line', (10, 10, 2.4), (10, 10, 8.6), TRAT)])


def schizzo(corpo):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{corpo}</svg>'


PUNTO = lambda x, y: f'<rect x="{x - 1.7}" y="{y - 1.7}" width="3.4" height="3.4" rx=".6" fill="#2F7DE1" stroke="#fff" stroke-width=".8"/>'  # noqa: E731
A['linea'] = schizzo(f'<line x1="5" y1="19" x2="19" y2="5" stroke="{LINEA}" stroke-width="1.8" stroke-linecap="round"/>' + PUNTO(5, 19) + PUNTO(19, 5))
A['rettangolo'] = schizzo(f'<rect x="4" y="6" width="16" height="12" fill="#DCEBFB" stroke="{LINEA}" stroke-width="1.6"/>' + PUNTO(4, 6) + PUNTO(20, 18))
A['quota'] = schizzo(f'<rect x="5" y="14" width="14" height="6" fill="#C9D2DC" stroke="{LINEA}" stroke-width="1.2"/>'
                     '<path d="M5 13 V5 M19 13 V5" stroke="#26303B" stroke-width="1" fill="none"/>'
                     '<path d="M5 8 H19" stroke="#2F7DE1" stroke-width="1.6"/><path d="M8 6 L5 8 L8 10 Z M16 6 L19 8 L16 10 Z" fill="#2F7DE1"/>')
A['specchia'] = schizzo('<path d="M12 2.5 V21.5" stroke="#26303B" stroke-width="1.2" stroke-dasharray="2 1.6"/>'
                        f'<path d="M9.5 6 L3 17 H9.5 Z" fill="#C9D2DC" stroke="{LINEA}" stroke-width="1.2" stroke-linejoin="round"/>'
                        f'<path d="M14.5 6 L21 17 H14.5 Z" fill="#5E9FE6" stroke="{LINEA}" stroke-width="1.2" stroke-linejoin="round"/>')

# ------------------------------------------------------------------------------------------- B: pieno a due toni
INK, BL, CH = '#3A4757', '#2F7DE1', '#9FB0C2'


def B_(corpo):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{corpo}</svg>'


B = {
    'piega': B_(f'<path d="M3 15.5 H12.5 L13 15.6 L19.6 5.3 L22 6.8 L15.2 17.5 A2.5 2.5 0 0 1 13 18.5 H3 Z" fill="{INK}"/>'
                f'<path d="M13 15.6 L19.6 5.3 L22 6.8 L15.2 17.5 Z" fill="{BL}"/>'),
    'flangia': B_(f'<path d="M2 14 L12 19 L22 14 L12 9 Z" fill="{CH}"/><path d="M12 9 L22 14 V6.5 L12 1.5 Z" fill="{BL}"/>'),
    'orlo': B_(f'<path d="M2 14 H16.5 A3.5 3.5 0 0 0 16.5 7 H9 V9.5 H16.5 A1 1 0 0 1 16.5 11.5 H2 Z" fill="{INK}"/>'
               f'<path d="M16.5 14 A3.5 3.5 0 0 0 16.5 7 H9 V9.5 H16.5 A1 1 0 0 1 16.5 11.5 Z" fill="{BL}"/>'),
    'spiega': B_(f'<rect x="3" y="4" width="18" height="16" rx="2.5" fill="{CH}"/><rect x="3" y="9.2" width="18" height="1.8" fill="{BL}"/>'
                 f'<rect x="3" y="14" width="18" height="1.8" fill="{BL}"/>'),
    'taglio': B_(f'<path d="M3 4 H12 V12 H21 V20 H3 Z" fill="{INK}"/><path d="M12 4 H21 V12 H12 Z" fill="{BL}" opacity=".35"/>'
                 f'<path d="M12 4 V12 H21" stroke="{BL}" stroke-width="2" fill="none" stroke-dasharray="2 1.5"/>'),
    'foro': B_(f'<rect x="3" y="3" width="18" height="18" rx="3" fill="{INK}"/><circle cx="12" cy="12" r="5" fill="{BL}"/>'
               f'<circle cx="12" cy="12" r="2.6" fill="#fff"/>'),
    'pezzo': B_(f'<path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z" fill="{INK}"/><path d="M12 2 L21 7 L12 12 L3 7 Z" fill="{BL}"/>'),
    'esploso': B_(f'<rect x="3" y="13" width="9" height="8" rx="1.5" fill="{INK}"/><rect x="12" y="3" width="9" height="8" rx="1.5" fill="{BL}"/>'
                  f'<path d="M10 11 L14 13" stroke="{CH}" stroke-width="1.6" stroke-dasharray="1.6 1.4"/>'),
    'linea': B_(f'<path d="M5 19 L19 5" stroke="{INK}" stroke-width="2.4" stroke-linecap="round"/><circle cx="5" cy="19" r="2.6" fill="{BL}"/>'
                f'<circle cx="19" cy="5" r="2.6" fill="{BL}"/>'),
    'rettangolo': B_(f'<rect x="3" y="5" width="18" height="14" rx="2" fill="{CH}"/><rect x="5.5" y="7.5" width="13" height="9" rx="1" fill="#fff"/>'
                     f'<circle cx="4" cy="6" r="2.4" fill="{BL}"/><circle cx="20" cy="18" r="2.4" fill="{BL}"/>'),
    'quota': B_(f'<rect x="3" y="14" width="18" height="7" rx="1.5" fill="{INK}"/><path d="M3 9 L7 6 V12 Z M21 9 L17 6 V12 Z" fill="{BL}"/>'
                f'<rect x="6" y="8.2" width="12" height="1.6" fill="{BL}"/>'),
    'specchia': B_(f'<rect x="11.2" y="2" width="1.6" height="20" rx=".8" fill="{CH}"/><path d="M9.5 5 L2.5 18 H9.5 Z" fill="{INK}"/>'
                   f'<path d="M14.5 5 L21.5 18 H14.5 Z" fill="{BL}"/>'),
}

# ------------------------------------------------------------------------------------------- C: tratto deciso
K, AC, LF = '#26303B', '#2F7DE1', '#DDE7F2'


def C_(corpo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
            f'{corpo}</svg>')


C = {
    'piega': C_(f'<path d="M2.5 17 H12" stroke="{K}" stroke-width="2.4"/><path d="M12 17 L20 5" stroke="{AC}" stroke-width="2.6"/>'
                f'<path d="M12 17 A3 3 0 0 0 14 14.5" stroke="{K}" stroke-width="1.4"/>'),
    'flangia': C_(f'<path d="M2.5 14.5 L12 19.5 L21.5 14.5 L12 9.5 Z" fill="{LF}" stroke="{K}" stroke-width="2"/>'
                  f'<path d="M12 9.5 L21.5 14.5 V7 L12 2 Z" fill="#B9D6F7" stroke="{AC}" stroke-width="2"/>'),
    'orlo': C_(f'<path d="M2.5 15 H17 A3.2 3.2 0 0 0 17 8.6 H9" stroke="{K}" stroke-width="2.4"/>'
               f'<path d="M17 15 A3.2 3.2 0 0 0 17 8.6 H9" stroke="{AC}" stroke-width="2.6"/>'),
    'spiega': C_(f'<rect x="3" y="4" width="18" height="16" rx="2" fill="{LF}" stroke="{K}" stroke-width="2"/>'
                 f'<path d="M3 10 H21 M3 14.5 H21" stroke="{AC}" stroke-width="2" stroke-dasharray="2.5 2"/>'),
    'taglio': C_(f'<path d="M3 4 H12 V12 H21 V20 H3 Z" fill="{LF}" stroke="{K}" stroke-width="2"/><path d="M12 4 V12 H21" stroke="{AC}" stroke-width="2.6"/>'),
    'foro': C_(f'<rect x="3" y="3" width="18" height="18" rx="3" fill="{LF}" stroke="{K}" stroke-width="2"/>'
               f'<circle cx="12" cy="12" r="4.5" fill="#fff" stroke="{AC}" stroke-width="2.4"/>'),
    'pezzo': C_(f'<path d="M12 2.5 L20.5 7.2 V16.8 L12 21.5 L3.5 16.8 V7.2 Z" fill="{LF}" stroke="{K}" stroke-width="2"/>'
                f'<path d="M12 2.5 L20.5 7.2 L12 12 L3.5 7.2 Z" fill="#B9D6F7" stroke="{AC}" stroke-width="2"/>'),
    'esploso': C_(f'<rect x="3" y="13" width="8.5" height="8" rx="1.5" fill="{LF}" stroke="{K}" stroke-width="2"/>'
                  f'<rect x="12.5" y="3" width="8.5" height="8" rx="1.5" fill="#B9D6F7" stroke="{AC}" stroke-width="2"/>'
                  f'<path d="M10 11.5 L14 12.5" stroke="{K}" stroke-width="1.4" stroke-dasharray="1.6 1.4"/>'),
    'linea': C_(f'<path d="M5.5 18.5 L18.5 5.5" stroke="{K}" stroke-width="2.4"/><circle cx="5" cy="19" r="2.3" fill="#fff" stroke="{AC}" stroke-width="2"/>'
                f'<circle cx="19" cy="5" r="2.3" fill="#fff" stroke="{AC}" stroke-width="2"/>'),
    'rettangolo': C_(f'<rect x="4" y="6" width="16" height="12" rx="1" fill="{LF}" stroke="{K}" stroke-width="2"/>'
                     f'<circle cx="4" cy="6" r="2.2" fill="#fff" stroke="{AC}" stroke-width="2"/><circle cx="20" cy="18" r="2.2" fill="#fff" stroke="{AC}" stroke-width="2"/>'),
    'quota': C_(f'<path d="M4 6 V18 M20 6 V18" stroke="{K}" stroke-width="2"/><path d="M4 12 H20" stroke="{AC}" stroke-width="2.4"/>'
                f'<path d="M7.5 9 L4 12 L7.5 15 M16.5 9 L20 12 L16.5 15" stroke="{AC}" stroke-width="2.4"/>'),
    'specchia': C_(f'<path d="M12 2.5 V21.5" stroke="{K}" stroke-width="1.6" stroke-dasharray="2.5 2"/>'
                   f'<path d="M9 6 L3 17 H9 Z" fill="{LF}" stroke="{K}" stroke-width="2"/><path d="M15 6 L21 17 H15 Z" fill="#B9D6F7" stroke="{AC}" stroke-width="2"/>'),
}

NOMI = [('piega', 'Piega', 'fold'), ('flangia', 'Flangia', 'flange'), ('orlo', 'Orlo', 'hem'), ('spiega', 'Spiega', 'flat'),
        ('taglio', 'Taglio', 'cut'), ('foro', 'Foro', 'hole'), ('pezzo', 'Pezzo', 'box'), ('esploso', 'Esploso', 'explode'),
        ('linea', 'Linea', 'line'), ('rettangolo', 'Rettangolo', 'rect'), ('quota', 'Quota', 'dimension'), ('specchia', 'Specchia', 'mirror')]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for st, d in (('A', A), ('B', B), ('C', C)):
        for k, v in d.items():
            (OUT / f'{st}_{k}.svg').write_text(v, encoding='utf-8')
    stili = [('A', 'Isometrico ombreggiato', 'Come i CAD (SolidWorks, Fusion): i pezzi in 3D con le facce in tre toni, il risultato del comando in blu.'),
             ('B', 'Pieno a due toni', 'Forme piene e morbide, senza contorni: grigio ardesia e blu. Moderno, alla Windows 11.'),
             ('C', 'Tratto deciso', 'Contorni spessi, riempimenti chiari, accento blu: leggibili anche piccole.')]
    blocchi = []
    for st, titolo, spieg in stili:
        celle = ''.join(f'<div class="c"><img class="g" src="proposte/{st}_{k}.svg"><img class="p" src="proposte/{st}_{k}.svg">'
                        f'<span>{it}</span></div>' for k, it, _ in NOMI)
        scuro = ''.join(f'<img src="proposte/{st}_{k}.svg">' for k, _, _ in NOMI)
        blocchi.append(f'<section><h2><b>{st}</b> {titolo}</h2><p>{spieg}</p><div class="riga">{celle}</div>'
                       f'<div class="barra"><span>nella barra, tema chiaro</span>{scuro}</div>'
                       f'<div class="barra scura"><span>nella barra, tema scuro</span>{scuro}</div></section>')
    vecchie = ''.join(f'<img src="../icons/{old}.svg">' for _, _, old in NOMI)
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Icone: tre stili</title><style>
body {{ font: 13px/1.4 "Segoe UI", system-ui, sans-serif; margin: 24px 36px; background: #F3F5F7; color: #1C2228; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} section {{ background: #fff; border: 1px solid #DDE2E7; border-radius: 12px; padding: 16px 20px; margin: 16px 0; }}
h2 {{ margin: 0; font-size: 17px; }} h2 b {{ display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 6px; background: #2F7DE1; color: #fff; margin-right: 6px; }}
section p {{ margin: 4px 0 12px; color: #5B6670; }}
.riga {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 8px; }}
.c {{ display: grid; justify-items: center; gap: 6px; padding: 8px 2px; border-radius: 8px; background: #F7F9FB; }}
.c img.g {{ width: 48px; height: 48px; }} .c img.p {{ width: 24px; height: 24px; }} .c span {{ font-size: 11.5px; color: #3A4552; }}
.barra {{ display: flex; align-items: center; gap: 18px; margin-top: 10px; padding: 9px 14px; border-radius: 8px; background: #F0F2F5; }}
.barra span {{ width: 160px; color: #8A949D; font-size: 11.5px; }} .barra img {{ width: 24px; height: 24px; }}
.barra.scura {{ background: #1B2027; }} .barra.scura span {{ color: #8A949D; }}
.barra.scura img {{ filter: invert(.88) hue-rotate(180deg) brightness(1.15); }}
</style></head><body><h1>Icone: tre stili a confronto</h1><p style="color:#5B6670;margin:0">12 comandi campione. Scegli lo stile, poi faccio tutte le 70 icone in quello.</p>
<section><h2><b style="background:#8A949D">—</b> Quelle di adesso</h2><p>Per confronto.</p><div class="barra"><span>nella barra</span>{vecchie}</div></section>
{''.join(blocchi)}</body></html>'''
    (R / 'proposte.html').write_text(html, encoding='utf-8')
    print('ok', len(A), len(B), len(C))


if __name__ == '__main__':
    main()
