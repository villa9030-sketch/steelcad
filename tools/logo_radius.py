"""Il marchio Radius in vettoriale (23/10), ridisegnato sulle immagini del cliente.

Il segno è una «r» di lamiera piegata: il gambo, la piega col raggio e, sopra, il quarto di lastra tagliato da un arco
(cerchio vero: centro (967, 967), raggio 703, nelle coordinate dell'immagine originale 1254 × 1254). La piega esterna
è la curva dell'originale ricalcata (scarto < 1 px), quella interna un raggio 90.

    python tools/logo_radius.py   → app/ui/img/radius_mark.svg, radius_mark_bianco.svg, radius_logo.svg,
                                    radius_app.svg (l'icona del programma) e radius.ico / radius.png
"""
from pathlib import Path

R = Path(__file__).resolve().parents[1] / 'app' / 'ui' / 'img'
BLU = '#00308E'
# il segno, coordinate dell'originale
SEGNO = ('M336 265 H918 A703 703 0 0 0 336 662 Z '
         'M473 1018 V780 C473 590 678 443 918 443 V619 H729 A90 90 0 0 0 639 709 V1018 Z')
X0, Y0, LS, HS = 336, 265, 582, 753          # il riquadro del segno


def segno(colore=BLU):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{X0} {Y0} {LS} {HS}"><path d="{SEGNO}" fill="{colore}"/></svg>'


def scritta(colore=BLU):
    """«radius»: il segno al posto della r, poi lettere geometriche a tratto costante (misure prese dal logo
    del cliente: altezza della x 65, tratto 9, la d sale a 87; unità = pixel dell'immagine 441 × 260)."""
    k = 72 / HS                                  # il segno alto 72 (da 103 a 175)
    dx = 6.7                                     # il segno ridisegnato è un filo più largo di quello della scritta
    g = f'<g transform="translate(40 103) scale({k:.6f}) translate({-X0} {-Y0})"><path d="{SEGNO}" fill="{colore}"/></g>'
    w = 9
    lettere = (f'<circle cx="{134.5 + dx}" cy="142.5" r="28"/><path d="M{164.5 + dx} 110 V175"/>'                     # a
               f'<circle cx="{211.5 + dx}" cy="142.5" r="28"/><path d="M{242.5 + dx} 87 V175"/>'                      # d
               f'<path d="M{263 + dx} 110 V175"/>'                                                                    # i
               f'<path d="M{282.5 + dx} 110 V150 A25 25 0 0 0 {332.5 + dx} 150 M{332.5 + dx} 110 V175"/>'             # u
               f'<path transform="translate({dx} 0)" d="M397.5 122 C393 116.5 385 114.5 375 114.5 C362 114.5 352 118.5 352 128 '
               'C352 137.5 362 140 375 142.5 C388 145 398.5 148 398.5 157.5 C398.5 167 389 170.5 375 170.5 '
               'C363.5 170.5 355 167.5 350.5 161.5"/>')                                                               # s
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="34 80 {380 + dx} 102">{g}'
            f'<g fill="none" stroke="{colore}" stroke-width="{w}">{lettere}</g></svg>')


def icona_app():
    """L'icona del programma: piastrella blu con la sfumatura dell'acciaio blu delle icone, il segno in bianco."""
    s = 1024
    h = 600                                       # altezza del segno nella piastrella
    k = h / HS
    tx = (s - LS * k) / 2 - X0 * k
    ty = (s - h) / 2 - Y0 * k
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}"><defs>'
            '<linearGradient id="f" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2F63E8"/>'
            f'<stop offset=".55" stop-color="#0B3FB5"/><stop offset="1" stop-color="{BLU}"/></linearGradient>'
            '<linearGradient id="l" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".22"/>'
            '<stop offset=".5" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient></defs>'
            f'<rect x="32" y="32" width="{s - 64}" height="{s - 64}" rx="200" fill="url(#f)"/>'
            f'<rect x="32" y="32" width="{s - 64}" height="{s - 64}" rx="200" fill="url(#l)"/>'
            f'<path d="{SEGNO}" fill="#FFFFFF" transform="translate({tx:.2f} {ty:.2f}) scale({k:.6f})"/></svg>')


def main():
    R.mkdir(parents=True, exist_ok=True)
    (R / 'radius_mark.svg').write_text(segno(), encoding='utf-8')
    (R / 'radius_mark_bianco.svg').write_text(segno('#FFFFFF'), encoding='utf-8')
    (R / 'radius_logo.svg').write_text(scritta(), encoding='utf-8')
    (R / 'radius_logo_bianco.svg').write_text(scritta('#FFFFFF'), encoding='utf-8')
    (R / 'radius_app.svg').write_text(icona_app(), encoding='utf-8')
    print('ok')


if __name__ == '__main__':
    main()
