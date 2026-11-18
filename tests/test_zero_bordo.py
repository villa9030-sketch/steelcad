"""18/11 (carrello di Stefano): negli sketch sulle facce di una lamiera lo zero era l'angolo della faccia. Cambiando gli
angoli sopra/sotto delle pieghe la faccia si accorciava di 4 mm e i fori disegnati lì sopra si spostavano con lei, senza
dirlo (fori a 20 e 772 invece che 24 e 776). Ora: gli sketch nuovi partono dal bordo esterno del pezzo e non si
spostano; quelli vecchi restano come sono, ma se una modifica li sposta Radius lo dice."""
import build123d as bd

from app.service import Service


def _vaschetta():
    s = Service()
    assert s.new_project('lamiera', {'name': 'Ripiano', 'larghezza': 800, 'profondita': 600, 'spessore': 3,
                                     'raggio': 1, 'k': 0.21})['ok']
    for lato in ('L1', 'L2', 'L3', 'L4'):
        assert s.add_flange('SM1', lato, {'length': 50})['ok']
    fl = {f['edge']: f['id'] for f in s.doc.feature('SM1')['flanges']}
    return s, fl


def _x_foro(s, fid):
    fs = [bd.Face(f) for f in s.result.body.names.get(f'{fid}/parete', [])]
    b = bd.Compound(children=fs).bounding_box()
    return round((b.min.X + b.max.X) / 2, 3)


def _taglio_di(s, sid):
    return next(f['id'] for f in s.doc.features if not hasattr(f, 'entities') and f.get('sketch') == sid)


def test_sketch_nuovo_sulla_lamiera_parte_dal_bordo_e_non_si_sposta():
    s, fl = _vaschetta()
    davanti, sinistra = fl['L1'], fl['L4']
    sid = s.sketch_on_face(f'SM1/{davanti}/esterno')['sketch']
    assert s.doc.sketch(sid).plane.get('zero') == 'bordo'
    assert s.sketch_add_circle(sid, [23, 21], 4.5)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    tg = _taglio_di(s, sid)
    assert _x_foro(s, tg) == 23.0                                       # 23 dal bordo esterno del pezzo
    for modo in ('over', 'under'):
        r = s.set_corner('SM1', davanti, sinistra, modo)
        assert r['ok'], r
        assert _x_foro(s, tg) == 23.0 and not r.get('avviso'), (modo, r.get('avviso'))


def test_sketch_vecchio_che_si_sposta_lo_dice():
    s, fl = _vaschetta()
    davanti, sinistra = fl['L1'], fl['L4']
    sid = s.sketch_on_face(f'SM1/{davanti}/esterno')['sketch']
    del s.doc.sketch(sid).plane['zero']                                  # come uno sketch fatto prima del 18/11
    assert s.sketch_add_circle(sid, [23, 21], 4.5)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    tg = _taglio_di(s, sid)
    assert _x_foro(s, tg) == 27.0                                       # 23 dall'angolo della faccia, che sta a 4
    r = s.set_corner('SM1', davanti, sinistra, 'over')
    assert r['ok'], r
    assert _x_foro(s, tg) == 23.0                                       # la faccia si è allungata: il foro si sposta
    assert 'spostati i fori' in (r.get('avviso') or '') and '4 mm' in r['avviso'], r.get('avviso')
