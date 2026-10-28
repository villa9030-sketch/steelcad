"""Esempi pronti nella pagina iniziale (24/10): pezzi veri da aprire, guardare e modificare, per capire come si lavora.

Si costruiscono con gli stessi comandi dell'app (niente file da tenere allineati): si aprono come lavoro nuovo, non
salvato, e Annulla non li smonta.
"""
from __future__ import annotations

from cad_engine.errors import SteelCADError

ESEMPI = [
    {'id': 'staffa', 'nome': 'Staffa a L', 'testo': 'Lamiera piegata con due fori Ø10', 'img': 'lamiera_piegata.png'},
    {'id': 'cassa', 'nome': 'Cassetta piegata', 'testo': 'Quattro pareti da 80 mm, sp. 2', 'img': 'lamiera.png'},
    {'id': 'piastra', 'nome': 'Piastra con foro', 'testo': 'Piastra di base 300 × 200, sp. 5', 'img': 'piastra.png'},
    {'id': 'tramoggia', 'nome': 'Tramoggia con cassone', 'testo': 'Divisa in pezzi da piegare', 'img': 'tramoggia.png'},
    {'id': 'telaio', 'nome': 'Telaio in tubolare', 'testo': 'Banco con quattro gambe', 'img': 'telaio.png'},
]


def _ok(r):
    if not r.get('ok'):
        raise SteelCADError(r.get('message') or 'L’esempio non si è costruito.', code='esempio')
    return r


def _piega(s, t: float) -> dict:
    """Raggio e K: quelli della tua piegatrice (Impostazioni); se non ci sono ancora, per l'esempio raggio = spessore
    e K 0,4, e si dice (sono dati della macchina: nei pezzi veri non si inventano)."""
    d = s.bend_default() or {}
    out = {}
    if not d.get('radius'):
        out['raggio'] = t
    if not d.get('k') and not d.get('method'):
        out['k'] = 0.4
    return out


def crea(s, eid: str) -> str | None:
    """Costruisce l'esempio nel servizio s (il lavoro aperto viene sostituito, come con «Nuovo»). Dà un avviso se ha
    dovuto mettere raggio e K d'esempio."""
    voce = next((e for e in ESEMPI if e['id'] == eid), None)
    if voce is None:
        raise SteelCADError('Esempio sconosciuto.', code='esempio')
    avviso = None
    if eid in ('staffa', 'cassa', 'tramoggia'):
        extra = _piega(s, 3 if eid == 'staffa' else 2)
        if extra:
            avviso = ('Nell’esempio raggio e K sono di prova (raggio = spessore, K 0,4): per i tuoi pezzi mettili in '
                      'Impostazioni → Piegatrice.')
    else:
        extra = {}
    if eid == 'staffa':
        _ok(s.new_project('lamiera', {'name': voce['nome'], 'larghezza': 120, 'profondita': 60, 'spessore': 3, **extra}))
        _ok(s.add_flange('SM1', 'L1', {'length': '40'}))
        sid = _ok(s.sketch_on_face('SM1/sopra'))['sketch']
        for x in (30, 90):
            _ok(s.sketch_add_circle(sid, [x, 32], 5))
        _ok(s.create_from_sketch(sid, 'cut', {}))
    elif eid == 'cassa':
        _ok(s.new_project('lamiera', {'name': voce['nome'], 'larghezza': 400, 'profondita': 300, 'spessore': 2, **extra}))
        for lato in ('L1', 'L2', 'L3', 'L4'):
            _ok(s.add_flange('SM1', lato, {'length': '80'}))
    elif eid == 'piastra':
        _ok(s.new_project('piastra', {}))
    elif eid == 'tramoggia':
        _ok(s.new_project('tramoggia_cassone', dict(extra)))
    elif eid == 'telaio':
        _ok(s.new_project('telaio', {}))
    s.doc.meta['name'] = f'Esempio — {voce["nome"]}'
    s._set(s.doc)                 # da qui il lavoro è suo: Annulla non smonta l'esempio pezzo per pezzo
    s.path = None
    return avviso
