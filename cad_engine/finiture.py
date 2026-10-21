"""Finiture dei pezzi: grezzo, zincato, inox, verniciato (colore RAL). Il colore serve a vedere il pezzo nel 3D come
sarà; la finitura va in distinta. I colori RAL sono quelli di riferimento (sRGB indicativo, non per il colorificio)."""
from __future__ import annotations

RAL = {
    '1003': ('Giallo segnale', '#F2A900'), '1013': ('Bianco perla', '#E3D9C6'), '1023': ('Giallo traffico', '#F7B500'),
    '2004': ('Arancio puro', '#E75B12'), '3000': ('Rosso fuoco', '#A72920'), '3002': ('Rosso carminio', '#9B2321'),
    '3020': ('Rosso traffico', '#C1121C'), '5010': ('Blu genziana', '#0E4C92'), '5012': ('Blu luce', '#0089B6'),
    '5015': ('Blu cielo', '#2271B3'), '6005': ('Verde muschio', '#114232'), '6018': ('Verde giallastro', '#4C9141'),
    '7016': ('Grigio antracite', '#383E42'), '7021': ('Grigio nerastro', '#2F3234'), '7035': ('Grigio luce', '#CBD0CC'),
    '7037': ('Grigio polvere', '#7D7F7D'), '7040': ('Grigio finestra', '#9DA3A6'), '9005': ('Nero intenso', '#0A0A0A'),
    '9006': ('Alluminio brillante', '#A5A8A6'), '9010': ('Bianco puro', '#F1ECE1'), '9016': ('Bianco traffico', '#F1F0EA'),
}
TIPI = {'grezzo': 'Grezzo', 'zincato': 'Zincato', 'inox': 'Inox spazzolato', 'verniciato': 'Verniciato'}


def colore(fin: dict | None) -> dict | None:
    """Colore e lucentezza per il 3D: {'color': '#rrggbb', 'metal': 0..1, 'rough': 0..1}; None = quello normale."""
    if not fin:
        return None
    t = fin.get('tipo')
    if t == 'zincato':
        return {'color': '#B9C0C6', 'metal': 0.55, 'rough': 0.35}
    if t == 'inox':
        return {'color': '#D3D7DB', 'metal': 0.7, 'rough': 0.25}
    if t == 'verniciato':
        r = RAL.get(str(fin.get('ral') or '').replace('RAL', '').strip())
        return {'color': r[1] if r else '#8A9099', 'metal': 0.05, 'rough': 0.6}
    return None


def testo(fin: dict | None) -> str:
    if not fin or fin.get('tipo') in (None, '', 'grezzo'):
        return 'Grezzo'
    if fin['tipo'] == 'verniciato':
        ral = str(fin.get('ral') or '').replace('RAL', '').strip()
        nome = RAL.get(ral, ('', ''))[0]
        return f'Verniciato RAL {ral}' + (f' {nome.lower()}' if nome else '')
    return TIPI.get(fin['tipo'], fin['tipo'])
