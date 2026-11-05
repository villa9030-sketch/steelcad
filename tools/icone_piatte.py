"""Le icone di Radius, stile «piatto» (notte 03→04/11/2026): tratto + un dettaglio pieno di accento.

Regole (uguali per tutte):
- griglia 24×24, tratto 1,75 arrotondato in `currentColor` (prende il colore del testo del pulsante:
  funziona da solo nel tema scuro, nei pulsanti blu, in quelli disattivi);
- UN dettaglio pieno (o un tratto) di accento: `var(--accento-icona, #1F5EFF)`; nella barra dei comandi
  `--accento-icona` è il colore della modalità (lamiera blu, disegno verde acqua, tubi arancio, assieme viola,
  tavole grafite), vedi «ICONE» in style.css;
- in accento va quello che il comando fa o aggiunge (la piega che sale, il foro, il pezzo che si appoggia);
- forme da officina, poche linee, niente sfumature.

    python tools/icone_piatte.py
      → app/ui/icons/*.svg        (stessi nomi di prima: un file per icona, per chi le usa come <img>)
      → app/ui/icone.js           (le stesse come <symbol>: l'app le mette in linea al posto delle <img>)
      → app/ui/icons_nuove/tavola_piatte.html   (la tavola di controllo: grandi, piccole, chiaro, scuro)

Per un comando nuovo: aggiungere qui l'icona con le stesse regole e rigenerare.
"""
from pathlib import Path

R = Path(__file__).resolve().parents[1] / 'app' / 'ui'
ACC = 'var(--accento-icona, #1F5EFF)'
TRATTO = 'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"'


def s(d, extra=''):
    """Tratto normale."""
    return f'<path d="{d}"{extra}/>'


def tr(d):
    """Tratteggio (linee guida, assi, la parte che va via)."""
    return f'<path d="{d}" stroke-dasharray="2.2 2.8"/>'


def a(d, evenodd=False):
    """Pieno di accento, senza bordo."""
    fr = ' fill-rule="evenodd"' if evenodd else ''
    return f'<path d="{d}"{fr} style="fill:{ACC};stroke:none"/>'


def af(d, evenodd=False):
    """Pieno di accento col bordo del tratto sopra: la parte nuova del pezzo."""
    return a(d, evenodd) + s(d)


def at(d, w=2.25, dash=False):
    """Tratto di accento (raccordo, smusso, la linea che si aggiunge)."""
    da = ' stroke-dasharray="2.2 2.8"' if dash else ''
    return f'<path d="{d}" style="stroke:{ACC}" stroke-width="{w}"{da}/>'


def pallino(x, y, r=2):
    return a(f'M{x - r:g} {y:g}a{r:g} {r:g} 0 1 0 {2 * r:g} 0a{r:g} {r:g} 0 1 0 {-2 * r:g} 0z')


def cerchio(x, y, r):
    return f'M{x - r:g} {y:g}a{r:g} {r:g} 0 1 0 {2 * r:g} 0a{r:g} {r:g} 0 1 0 {-2 * r:g} 0z'


def rett(x, y, w, h, r=0):
    if not r:
        return f'M{x:g} {y:g}h{w:g}v{h:g}h{-w:g}z'
    return (f'M{x + r:g} {y:g}h{w - 2 * r:g}a{r:g} {r:g} 0 0 1 {r:g} {r:g}v{h - 2 * r:g}a{r:g} {r:g} 0 0 1 {-r:g} {r:g}'
            f'h{-(w - 2 * r):g}a{r:g} {r:g} 0 0 1 {-r:g} {-r:g}v{-(h - 2 * r):g}a{r:g} {r:g} 0 0 1 {r:g} {-r:g}z')


def cubo(cx, cy, l, accento=True):
    """Un cubo isometrico: centro della faccia di sopra in (cx, cy - l/2), lato l; sopra in accento."""
    h = l / 2
    top = f'M{cx:g} {cy - l:g}l{l:g} {h:g}l{-l:g} {h:g}l{-l:g} {-h:g}z'
    giro = f'M{cx:g} {cy - l:g}l{l:g} {h:g}v{l:g}l{-l:g} {h:g}l{-l:g} {-h:g}v{-l:g}z'
    dentro = f'M{cx - l:g} {cy - h:g}l{l:g} {h:g}l{l:g} {-h:g}M{cx:g} {cy:g}v{l:g}'
    return (a(top) if accento else '') + s(giro) + s(dentro)


# documento con l'orecchia (nuovo, dxf, esporta)
DOC = 'M6.5 3H14l5 5v11.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 19.5v-15A1.5 1.5 0 0 1 6.5 3zM14 3v5h5'

ICONE = {
    # ------------------------------------------------------------------ disegno (sketch)
    'line': s('M5 19L19 5') + pallino(5, 19, 2.3) + pallino(19, 5, 2.3),
    'rect': s(rett(4, 6, 16, 12, 1.5)) + pallino(4, 18, 2.3) + pallino(20, 6, 2.3),
    'rect_center': s(rett(4, 6, 16, 12, 1.5)) + tr('M7 9l10 6') + pallino(12, 12, 2.3),
    'circle': s(cerchio(12, 12, 8)) + pallino(12, 12, 2.2),
    'arc3': s('M4 17A8 8 0 0 1 20 17') + pallino(4, 17, 2.2) + pallino(12, 9, 2.2) + pallino(20, 17, 2.2),
    'arc_tangent': s('M3 18h6A10 10 0 0 0 19 8') + tr('M9 8l7 7') + pallino(9, 18, 2.3),
    'slot': af('M8 8h8a4 4 0 0 1 0 8H8a4 4 0 0 1 0-8z') + s('M8 12h8'),
    'polygon': s('M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z') + pallino(12, 12, 2.2),
    'text': a(rett(4.5, 3.5, 15, 3.2, 1)) + s('M12 6.7V20M9 20h6'),
    'offset': s(rett(8.5, 8.5, 7, 7, 1.2)) + at('M8 3.5h8a4.5 4.5 0 0 1 4.5 4.5v8a4.5 4.5 0 0 1-4.5 4.5H8A4.5 4.5 0 0 1 3.5 16V8A4.5 4.5 0 0 1 8 3.5z', 1.9),
    'trim': s('M13 3v18M3 12h10') + at('M13 12h8', 2.25, True) + pallino(13, 12, 2.2),
    'extend': s('M20 3v18M3 12h8') + at('M11 12h4', 2, True) + a('M19 12l-4.5-3.2v6.4z'),
    # 05/11: Scala (il pezzo piccolo, il grande tratteggiato, il punto che resta fermo) e Spezza (una linea, due pezzi)
    'scale': s(rett(3.5, 11.5, 9, 9, 1.2)) + at('M3.5 8V3.5h17v17H16', 1.9, True) + s('M10 14l7.5-7.5M13 6.5h4.5V11')
    + pallino(3.5, 20.5, 2.2),
    'break': s('M3 18l7-4') + at('M14 11.7l7-4', 2.4) + pallino(12, 12.8, 2.3),
    'fillet': s('M4 20v-8M12 4h8') + at('M4 12a8 8 0 0 1 8-8', 2.6),
    'chamfer': s('M4 20V11M13 4h7') + at('M4 11l7-7', 2.6),
    'mirror': tr('M12 3v18') + s('M9 6L3 18h6z') + af('M15 6l6 12h-6z'),
    'copy': s(rett(3.5, 3.5, 11, 11, 2)) + a('M16.5 9H18a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-6a3 3 0 0 1-3-3v-1.5h7.5z'),
    'move': s('M12 3v18M3 12h18M9 5.5L12 2.8l3 2.7M9 18.5l3 2.7 3-2.7M5.5 9L2.8 12l2.7 3M18.5 9l2.7 3-2.7 3') + pallino(12, 12, 2.6),
    'pattern_rect': af(rett(3.5, 3.5, 7, 7, 1.5)) + s(rett(13.5, 3.5, 7, 7, 1.5) + rett(3.5, 13.5, 7, 7, 1.5) + rett(13.5, 13.5, 7, 7, 1.5)),
    'construction': tr('M4 20L20 4') + pallino(4, 20, 2.2) + pallino(20, 4, 2.2),
    'dimension': s('M4 4v16M20 4v16M5 12h14') + a('M4.9 12l4.2-3v6z') + a('M19.1 12l-4.2-3v6z'),
    'select': af('M5.5 3.5l13 6.2-5.6 1.9-2.4 6z') + s('M13 11.7l5.5 6.3'),
    'point': s('M3 8.5h18M3 15.5h18M8.5 3v18M15.5 3v18') + pallino(15.5, 8.5, 2.8),
    'delete': s('M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5') + a(rett(3.5, 5.6, 17, 2.4, 1.2)),
    'sketch': s('M3 19c2.5-4 4.5-4 6-1.5s3.5 2.5 5-1') + af('M13.5 11.5l6-6 2.5 2.5-6 6-3.5 1z'),
    # ------------------------------------------------------------------ vincoli e accoppiamenti
    'c_coincident': s('M2.5 18l5-5h14l-5 5z') + s('M12 3.5v9.5') + pallino(12, 15.2, 2.4),
    'c_collinear': s(rett(3, 5, 7, 10, 1) + rett(14, 8, 7, 7, 1)) + a(rett(2, 16.6, 20, 2.6, 1.3)),
    'c_fix': s(rett(5, 10.5, 14, 10, 2) + 'M8 10.5V7.5a4 4 0 0 1 8 0v3') + pallino(12, 15.5, 2),
    'c_parallel': af(rett(3, 5, 18, 4, 1)) + s(rett(3, 15, 18, 4, 1)),
    'c_perpendicular': a(rett(5, 14.5, 4.5, 4.5)) + s('M5 3.5V19h15.5M5 14.5h4.5V19'),
    'c_symmetry': s('M4 4v16M20 4v16') + af(rett(10, 6, 4, 12, 1)) + s('M6.5 12h2M15.5 12h2'),
    'c_tangent': s(cerchio(12, 9.8, 6.2) + 'M3 17h18') + pallino(12, 17, 2.2),
    'joint': s('M9.5 14.5l5-5M10.5 7l1.8-1.8a3.6 3.6 0 0 1 5.1 5.1L15.6 12M13.5 17l-1.8 1.8a3.6 3.6 0 0 1-5.1-5.1L8.4 12') + pallino(12, 12, 2.1),
    'appoggia': s(rett(3, 15.5, 18, 5, 1.2)) + af(rett(7, 8.5, 10, 5, 1)) + s('M12 2.5v3.5M9.8 4.2L12 6.4l2.2-2.2'),
    'faccia_su_faccia': s(rett(6, 3.5, 12, 7.5, 1.2) + rett(3, 13.5, 18, 7, 1.2)) + a(rett(5.5, 11, 13, 2.5, 1)),
    'foro_su_foro': s('M3 6h6.5v4H3zM14.5 6H21v4h-6.5zM3 14h6.5v4H3zM14.5 14H21v4h-6.5z') + a(rett(10.4, 3, 3.2, 18, 1.2)),
    'saldatura': s(rett(9.5, 3, 4, 12) + rett(3, 15, 18, 5, 1)) + a('M13.5 15v-4.2l4.2 4.2zM9.5 15v-4.2L5.3 15z'),
    'fastener': a(rett(6.5, 3, 11, 4.5, 1.2)) + s(rett(6.5, 3, 11, 4.5, 1.2) + 'M9.5 7.5v12a1.5 1.5 0 0 0 1.5 1.5h2a1.5 1.5 0 0 0 1.5-1.5v-12M9.5 11.5h5M9.5 15h5M9.5 18.5h5'),
    'interferenze': a('M10 10h4v4h-4z') + s(rett(3, 3, 11, 11, 1.5) + rett(10, 10, 11, 11, 1.5)),
    'assieme': cubo(8.5, 13.5, 5.5, False) + cubo(15.5, 10.5, 5.5),
    # ------------------------------------------------------------------ lamiera
    'lamiera': a('M2.5 11.5L12 6.8l9.5 4.7-9.5 4.7z') + s('M2.5 11.5L12 6.8l9.5 4.7-9.5 4.7zM2.5 11.5v2.8l9.5 4.7 9.5-4.7v-2.8M12 16.2V19'),
    'box': cubo(12, 12, 8.5),
    'flange': s('M2.5 19.5H13l6-6H8.5z') + af('M13 19.5l6-6V4l-6 6z'),
    'fold': s('M2.5 18h5l3.5-11h2l3.5 11h5') + pallino(7.5, 18, 1.9) + pallino(11, 7, 1.9) + pallino(13, 7, 1.9) + pallino(16.5, 18, 1.9),
    'hem': s('M3 8.5h12.5a4.25 4.25 0 0 1 0 8.5H9') + a('M7.6 17l4-3v6z'),
    'flat': af(rett(8, 8, 8, 8)) + s('M8 3.5h8V8h4.5v8H16v4.5H8V16H3.5V8H8z'),
    'refold': s(rett(3, 5, 18, 14, 1.5)) + tr('M8.5 5v14M15.5 5v14') + pallino(12, 12, 2.4),
    'project': s('M2.5 17.5l5.5-7.5h13.5l-5.5 7.5z') + af('M8.6 15.4l2.3-3.3h5.6l-2.3 3.3z') + s('M14 3.5l2.5 2.5-4 4-3 .5.5-3z'),
    'hole': a(cerchio(12, 12, 6)) + s(cerchio(12, 12, 6) + 'M12 2.5v19M2.5 12h19'),
    'cut': s('M4 7a1 1 0 0 1 1-1h8v7h7v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z') + a(rett(15.5, 2.5, 6, 6, 1.2)),
    'testa': s('M3 7.5h9.5L8 16.5H3z') + af('M15.5 7.5H21v9h-10z'),
    'extrude': af('M3.5 16l8.5 4.2 8.5-4.2-8.5-4.2z') + s('M12 9V3M9.3 5.6L12 2.9l2.7 2.7'),
    'perforate': s(rett(3, 4, 18, 16, 2) + 'M6.5 10h11M6.5 16h11') + a('M6.5 10a5.5 3.2 0 0 1 11 0zM6.5 16a5.5 3.2 0 0 1 11 0z'),
    # 05/11: lamiera forata, la lastra con i fori sfalsati a 60°
    'forata': s(rett(3, 4, 18, 16, 2)) + a(''.join(cerchio(x, y, 1.35) for x, y in
                                                ((7.5, 8.5), (12, 8.5), (16.5, 8.5), (9.75, 12), (14.25, 12),
                                                 (7.5, 15.5), (12, 15.5), (16.5, 15.5)))),
    'chiudi_angoli': s(rett(7.5, 3, 13.5, 3.5) + rett(3, 7.5, 3.5, 13.5)) + tr('M6.5 21H21V6.5') + a(rett(3, 3, 3.5, 3.5, .6)),
    'incastri': s('M3 10h11v4H3zM15 3h3.5v7H15zM15 14h3.5v7H15z') + af(rett(14, 10, 7, 4, 1)),
    'convert_sheet': cubo(8.5, 13, 5.5, False) + s('M14 12.5h3') + a('M21 12.5l-4.2-3.1v6.2z'),
    'bendtable': a('M6 4h12a2 2 0 0 1 2 2v3H4V6a2 2 0 0 1 2-2z') + s(rett(4, 4, 16, 16, 2) + 'M4 9h16M4 14.5h16M10 9v11'),
    'library': s('M5 18.5V5a2 2 0 0 1 2-2h12v15H7a2 2 0 0 0-2 2 2 2 0 0 0 2 2h12v-4') + a('M13 3h4.5v8l-2.25-1.6L13 11z'),
    'params': s('M4 6.5h16M4 12h16M4 17.5h16') + a(cerchio(8.5, 6.5, 2.4)) + a(cerchio(15.5, 12, 2.4)) + a(cerchio(10.5, 17.5, 2.4)),
    'section': s('M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9') + af('M1.5 12.5L12 7l10.5 5.5L12 18z'),
    'rivoluzione': af(rett(12, 4, 4.5, 9, 1)) + tr('M12 2.5v19') + s('M5.5 15.2a7.5 3.2 0 1 0 6.5-3.2') + a('M3.6 15.6l2-3.4 2 3.4z'),
    'measure': af('M3.2 15.5L15.5 3.2l5.3 5.3L8.5 20.8z') + s('M7 11.7l2 2M10 8.7l2 2M13 5.7l2 2'),
    # ------------------------------------------------------------------ tubi e strutture
    'tubo': a('M3 10h9v9H3zM5.6 12.6v3.8h3.8v-3.8z', True) + s(rett(3, 10, 9, 9) + rett(5.6, 12.6, 3.8, 3.8) + 'M3 10l8-6h10v9l-9 6M12 10l9-6'),
    'traverso': s(rett(3, 3, 4, 18, 1) + rett(17, 3, 4, 18, 1)) + af(rett(7, 10, 10, 4)),
    'struttura': af(rett(3, 3, 18, 4, 1)) + s(rett(3.5, 7, 4, 14) + rett(16.5, 7, 4, 14)),
    'piedi': s('M10 3v13M14 3v13') + af(rett(4.5, 16, 15, 4, 1.2)),
    'tappi': s('M8 21V10M16 21V10') + af('M7 10V6.5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2V10z'),
    'giunto': s('M3 3h5v13h13v5H3z') + at('M3.4 20.6L8 16', 2.6),
    # ------------------------------------------------------------------ assieme
    'explode': a(rett(9, 9, 6, 6, 1.2)) + s('M12 2.5v4M10 4.5l2-2 2 2M12 21.5v-4M10 19.5l2 2 2-2M2.5 12h4M4.5 10l-2 2 2 2M21.5 12h-4M19.5 10l2 2-2 2'),
    # ------------------------------------------------------------------ vista
    'eye': s('M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z') + pallino(12, 12, 3.2),
    'fit': s('M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4') + a(rett(8.5, 8.5, 7, 7, 1.5)),
    'home': s('M3.5 11L12 3.8l8.5 7.2M6 9v11h12V9') + a(rett(10, 13.5, 4, 6.5, .8)),
    'lookat': s(rett(3.5, 3.5, 17, 17, 2)) + s('M12 7v3M12 14v3M7 12h3M14 12h3') + pallino(12, 12, 2),
    'orbit': s('M20 12a8 8 0 1 1-2.3-5.7') + a('M20.5 3v6.2h-6.2z'),
    'pan': s('M12 3v18M3 12h18') + a('M12 2l3 3.5H9zM12 22l-3-3.5h6zM2 12l3.5-3v6zM22 12l-3.5 3V9z'),
    'zoom': s(cerchio(10.5, 10.5, 6.5) + 'M15.3 15.3L20.5 20.5') + at('M10.5 7.8v5.4M7.8 10.5h5.4', 2.2),
    'search': s(cerchio(10.5, 10.5, 6.5)) + at('M15.6 15.6L20.5 20.5', 3),
    # ------------------------------------------------------------------ file e comandi generali
    'new': s(DOC) + at('M12 11.5v6M9 14.5h6', 2.2),
    'open': s('M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z') + af('M3 11h18v6.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'),
    'save': a(rett(7.5, 13.5, 9, 7.5)) + s('M5.5 3.5h10.8L20.5 7.7V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5.5a2 2 0 0 1 2-2zM8 3.5v4.5h7V3.5M7.5 20.5v-7h9v7'),
    'export': s('M4 14v5a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 19v-5M12 7.5V15') + a('M12 2.5l5.2 5.5H6.8z'),
    'dxf': s(DOC) + a('M8 12h8v6H8zM12 13.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z', True),
    'undo': s('M4.5 9h10a5.5 5.5 0 0 1 0 11H11') + a('M3 9l5.5-5v10z'),
    'redo': s('M19.5 9h-10a5.5 5.5 0 0 0 0 11H13') + a('M21 9l-5.5-5v10z'),
    'list': s('M9 6h11M9 12h11M9 18h11') + pallino(4.8, 6, 1.6) + pallino(4.8, 12, 1.6) + pallino(4.8, 18, 1.6),
    'settings': s('M20.98 9.99L20.98 14.01L18.18 14.33L18.01 14.72L19.77 16.93L16.93 19.77L14.72 18.01L14.33 18.18L14.01 20.98L9.99 20.98L9.67 18.18L9.28 18.01L7.07 19.77L4.23 16.93L5.99 14.72L5.82 14.33L3.02 14.01L3.02 9.99L5.82 9.67L5.99 9.28L4.23 7.07L7.07 4.23L9.28 5.99L9.67 5.82L9.99 3.02L14.01 3.02L14.33 5.82L14.72 5.99L16.93 4.23L19.77 7.07L18.01 9.28L18.18 9.67z') + a(cerchio(12, 12, 3.2)),
    'finish': s(cerchio(12, 12, 9)) + at('M7.8 12.3l3 3 5.4-6', 2.4),
    'plane_angle': s('M4 20h16M4 20L16 6') + a('M4 20h7A7 7 0 0 0 8.56 14.69z'),
}

# i nomi «a parole» per la tavola: a cosa serve ogni icona nell'app
NOMI = {
    'line': 'Linea', 'rect': 'Rettangolo', 'rect_center': 'Rettangolo dal centro', 'circle': 'Cerchio', 'arc3': 'Arco',
    'arc_tangent': 'Arco col raggio', 'slot': 'Asola', 'polygon': 'Poligono', 'text': 'Testo / marca', 'offset': 'Offset',
    'trim': 'Accorcia', 'extend': 'Allunga', 'scale': 'Scala', 'break': 'Spezza', 'fillet': 'Raccordo', 'chamfer': 'Smusso', 'mirror': 'Specchia / capovolgi',
    'copy': 'Copia', 'move': 'Sposta', 'pattern_rect': 'Serie / dividi', 'construction': 'Costruzione', 'dimension': 'Quota',
    'select': 'Seleziona', 'point': 'Griglia', 'delete': 'Elimina', 'sketch': 'Contorno libero', 'c_coincident': 'Spigolo su faccia',
    'c_collinear': 'Spigolo su spigolo', 'c_fix': 'Blocca / fisso', 'c_parallel': 'Parallele', 'c_perpendicular': 'Perpendicolari',
    'c_symmetry': 'In mezzo', 'c_tangent': 'Tangente', 'joint': 'Accoppiamento', 'appoggia': 'Appoggia',
    'faccia_su_faccia': 'Faccia su faccia', 'foro_su_foro': 'Foro su foro', 'saldatura': 'Saldatura', 'fastener': 'Viteria',
    'interferenze': 'Interferenze', 'project': 'Su una faccia', 'assieme': 'Assieme', 'lamiera': 'Crea lamiera', 'box': 'Pezzo', 'flange': 'Piega',
    'fold': 'Profilo piegato', 'hem': 'Orlo', 'flat': 'Spiega', 'refold': 'Sullo sviluppo', 'hole': 'Foro', 'cut': 'Taglio',
    'testa': 'Taglio a 45° / testa a testa', 'extrude': 'Linguetta / estrudi', 'perforate': 'Persiane, bugne', 'forata': 'Lamiera forata',
    'chiudi_angoli': 'Chiudi angoli', 'incastri': 'Incastri', 'convert_sheet': 'Converti in lamiera', 'bendtable': 'Tabella pieghe',
    'library': 'Regole piega', 'params': 'Misure', 'section': 'Sezione', 'rivoluzione': 'Rivoluzione', 'measure': 'Righello',
    'tubo': 'Tubo', 'traverso': 'Traverso', 'struttura': 'Struttura', 'piedi': 'Piedi', 'tappi': 'Tappi', 'giunto': 'Angoli dei tubi',
    'explode': 'Esploso', 'eye': 'Vedi / nascondi', 'fit': 'Inquadra', 'home': 'Vista iso', 'lookat': 'Guarda la faccia',
    'orbit': 'Gira', 'pan': 'Sposta la vista', 'zoom': 'Dettaglio', 'search': 'Cerca', 'new': 'Nuovo / inserisci',
    'open': 'Apri / cartella', 'save': 'Salva', 'export': 'Esporta', 'dxf': 'DXF', 'undo': 'Annulla', 'redo': 'Rifai',
    'list': 'Altro', 'settings': 'Impostazioni', 'finish': 'Fatto / esci', 'plane_angle': 'Angolo',
}


def file_svg(corpo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" color="#3C4A57">'
            f'<g {TRATTO}>{corpo}</g></svg>\n')


def simboli():
    return ''.join(f'<symbol id="ico-{k}" viewBox="0 0 24 24"><g {TRATTO}>{v}</g></symbol>' for k, v in sorted(ICONE.items()))


JS = r'''/* Radius: le icone in linea (generato da tools/icone_piatte.py: non modificare a mano).
   Le <img src="icons/NOME.svg"> dell'interfaccia diventano <svg class="ico"><use href="#ico-NOME"></svg>:
   così il tratto prende il colore del testo (currentColor, anche nel tema scuro) e il dettaglio pieno
   prende --accento-icona (il colore della modalità nella barra dei comandi). Funziona da solo anche per
   le <img> che app.js mette dopo (un MutationObserver): app.js non deve cambiare. */
(function () {
  'use strict';
  const SIMBOLI = '__SIMBOLI__';
  const NOMI = new Set(__NOMI__);
  const NS = 'http://www.w3.org/2000/svg';
  const RE = /(?:^|\/)icons\/([\w-]+)\.svg(?:[?#].*)?$/;
  function nome(img) {
    const m = RE.exec(img.getAttribute('src') || '');
    return m && NOMI.has(m[1]) ? m[1] : null;
  }
  function sostituisci(img) {
    const n = nome(img);
    if (!n || !img.parentNode) return;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', ('ico ' + (img.getAttribute('class') || '')).trim());
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.dataset.ico = n;
    for (const at of ['id', 'title', 'hidden']) if (img.hasAttribute(at)) svg.setAttribute(at, img.getAttribute(at));
    if (img.getAttribute('style')) svg.setAttribute('style', img.getAttribute('style'));
    const use = document.createElementNS(NS, 'use');
    use.setAttribute('href', '#ico-' + n);
    svg.appendChild(use);
    img.replaceWith(svg);
  }
  function giro(radice) {
    if (radice.nodeType !== 1) return;
    if (radice.tagName === 'IMG') { sostituisci(radice); return; }
    const l = radice.getElementsByTagName('img');
    if (!l.length) return;
    for (const img of Array.from(l)) sostituisci(img);
  }
  function parti() {
    if (!document.getElementById('ico-simboli')) {
      const box = document.createElementNS(NS, 'svg');
      box.id = 'ico-simboli';
      box.setAttribute('aria-hidden', 'true');
      box.setAttribute('style', 'position:absolute;width:0;height:0;overflow:hidden');
      box.innerHTML = SIMBOLI;
      document.body.prepend(box);
    }
    giro(document.body);
    new MutationObserver(lista => {
      for (const m of lista) {
        if (m.type === 'attributes') { if (m.target.tagName === 'IMG') sostituisci(m.target); continue; }
        for (const n of m.addedNodes) giro(n);
      }
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
  }
  window.radiusIcona = (n, cls) => `<svg class="ico${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true" data-ico="${n}"><use href="#ico-${n}"></use></svg>`;
  if (document.body) parti(); else document.addEventListener('DOMContentLoaded', parti);
})();
'''


TAVOLA = '''<!doctype html><html lang="it"><meta charset="utf-8"><title>Icone Radius: tavola di controllo</title>
<link rel="stylesheet" href="../fonts/archivo.css" onerror="">
<style>
body {{ margin: 0; font: 13px/1.4 Archivo, "Segoe UI", system-ui, sans-serif; background: #EDF0F3; color: #15202B; }}
.tema {{ padding: 20px 24px 28px; }} .tema.scuro {{ background: #14191F; color: #E8EDF2; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }} h2 {{ font-size: 16px; margin: 18px 0 8px; font-weight: 600; }}
p {{ margin: 0 0 8px; color: #586675; }} .scuro p {{ color: #9AA7B4; }}
.griglia {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 6px; }}
.c {{ background: #fff; border: 1px solid #D9DEE4; border-radius: 6px; padding: 8px 6px 6px; display: grid; grid-template-columns: 1fr auto; gap: 2px 6px; align-items: center; }}
.scuro .c {{ background: #1C232B; border-color: #2C3640; }}
.c .g {{ width: 48px; height: 48px; grid-row: 1 / span 2; }} .c .p {{ width: 24px; height: 24px; }} .c .pp {{ width: 18px; height: 18px; }}
.c span {{ grid-column: 1 / -1; font-size: 11.5px; color: #586675; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.c b {{ font-weight: 500; font-size: 10.5px; color: #8C98A4; grid-column: 1 / -1; }}
.scuro .c span {{ color: #9AA7B4; }}
.barra {{ display: flex; gap: 2px; background: #fff; border: 1px solid #D9DEE4; border-radius: 6px; padding: 6px 8px; margin: 0 0 8px; align-items: flex-end; flex-wrap: wrap; }}
.scuro .barra {{ background: #1C232B; border-color: #2C3640; }}
.barra .nome {{ width: 86px; font-size: 12px; color: #586675; align-self: center; }}
.barra button {{ all: unset; display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 4px 6px; min-width: 52px; font-size: 12px; border-radius: 6px; color: inherit; }}
.barra button svg {{ width: 24px; height: 24px; }}
.barra button.pri {{ background: #1F5EFF; color: #fff; --accento-icona: currentColor; }}
.barra button.via {{ --accento-icona: #E5383B; }}
.barra button[disabled] {{ color: #8C98A4; --accento-icona: currentColor; }}
.m-lamiera {{ --accento-icona: #1F5EFF; }} .m-disegno {{ --accento-icona: #00A88F; }} .m-tubi {{ --accento-icona: #FF6B1A; }}
.m-assieme {{ --accento-icona: #7A4DFF; }} .m-tavole {{ --accento-icona: #3C4A57; }}
.scuro .m-lamiera {{ --accento-icona: #4F7FFF; }} .scuro .m-disegno {{ --accento-icona: #1EC4A8; }} .scuro .m-tubi {{ --accento-icona: #FF7F3A; }}
.scuro .m-assieme {{ --accento-icona: #9373FF; }} .scuro .m-tavole {{ --accento-icona: #8D9DAE; }}
.scuro {{ --accento-icona: #4F7FFF; }}
.prima img {{ width: 24px; height: 24px; }}
</style>
<svg style="position:absolute;width:0;height:0">{simboli}</svg>
<body>{temi}</body></html>
'''

BARRE = [
    ('m-lamiera', 'Lamiera', ['flange', 'hole', 'slot', 'cut', 'project', 'flat', 'dimension', 'list', 'export']),
    ('m-disegno', 'Disegno', ['line', 'rect', 'circle', 'arc3', 'trim', 'offset', 'mirror', 'dimension', 'finish']),
    ('m-tubi', 'Strutture', ['tubo', 'traverso', 'pattern_rect', 'piedi', 'tappi', 'giunto', 'params', 'sketch']),
    ('m-assieme', 'Assieme', ['new', 'fastener', 'appoggia', 'faccia_su_faccia', 'foro_su_foro', 'interferenze', 'explode']),
    ('m-tavole', 'Tavole', ['select', 'dimension', 'text', 'hole', 'plane_angle', 'saldatura', 'zoom']),
]


def u(k, cls):
    return f'<svg class="{cls}" viewBox="0 0 24 24"><use href="#ico-{k}"/></svg>'


def tavola():
    temi = []
    for tema in ('chiaro', 'scuro'):
        celle = ''.join(f'<div class="c">{u(k, "g")}{u(k, "p")}{u(k, "pp")}<span>{NOMI.get(k, k)}</span><b>{k}</b></div>'
                        for k in sorted(ICONE, key=lambda k: list(NOMI).index(k) if k in NOMI else 999))
        barre = ''.join(f'<div class="barra {cls}"><span class="nome">{nome}</span>'
                        + ''.join(f'<button>{u(k, "")}<span>{NOMI.get(k, k).split(" /")[0]}</span></button>' for k in ks)
                        + (f'<button class="pri">{u("lamiera", "")}<span>Crea lamiera</span></button>' if cls == 'm-disegno' else '')
                        + (f'<button class="via">{u("delete", "")}<span>Elimina</span></button><button disabled>{u("box", "")}<span>Spento</span></button>' if cls == 'm-lamiera' else '')
                        + '</div>' for cls, nome, ks in BARRE)
        temi.append(f'<section class="tema {tema}"><h1>Icone Radius, tema {tema}</h1>'
                    f'<p>{len(ICONE)} icone: 48, 24 e 18 px. Tratto del colore del testo, un dettaglio pieno nel colore di accento.</p>'
                    f'<h2>Nella barra dei comandi, col colore di ogni modalità</h2>{barre}<h2>Tutte</h2><div class="griglia">{celle}</div></section>')
    return TAVOLA.format(simboli=simboli(), temi=''.join(temi))


def main():
    cartella = R / 'icons'
    for k, v in ICONE.items():
        (cartella / f'{k}.svg').write_text(file_svg(v), encoding='utf-8', newline='\n')
    sim = simboli().replace('\\', '\\\\').replace("'", "\\'")
    nomi = '[' + ','.join(f"'{k}'" for k in sorted(ICONE)) + ']'
    (R / 'icone.js').write_text(JS.replace("'__SIMBOLI__'", f"'{sim}'").replace('__NOMI__', nomi), encoding='utf-8', newline='\n')
    (R / 'icons_nuove').mkdir(exist_ok=True)
    (R / 'icons_nuove' / 'tavola_piatte.html').write_text(tavola(), encoding='utf-8', newline='\n')
    print(len(ICONE), 'icone')


if __name__ == '__main__':
    main()
