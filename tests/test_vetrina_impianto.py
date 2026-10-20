"""Difetti trovati dalla prova di carico «impianto» del 20/10 (tools/vetrina_impianto.py)."""
import build123d as bd

from app.service import Service
from cad_engine.features.base import volume


def _deflettore():
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 600, 'profondita': 400, 'spessore': 2, 'raggio': 1, 'k': 0.21})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_polyline(sid, [[0, 150], [600, 150]], False)['ok']
    return s, sid


def test_bumping_a_raggio_verso_giu_non_va_a_zigzag():
    """Con «giù» tutti i colpi in «giù» andavano a zig-zag: 8 colpi per 90° scendevano di 9 mm."""
    alti = {}
    for verso in ('up', 'down'):
        s, sid = _deflettore()
        assert s.sheet_fold(sid, 90, verso, False, {'colpi': 8, 'raggio': 60})['ok']
        b = bd.Solid(s.result.body.shape).bounding_box()
        alti[verso] = b.max.Z if verso == 'up' else -b.min.Z
        assert abs(b.size.Y - 305.7) < 1                       # la parte da 150 è girata a 90°
    assert abs(alti['up'] - alti['down']) < 5 and alti['down'] > 100


def test_bumping_a_raggio_e_a_linee_nello_stesso_pezzo():
    """Prima un bumping a raggio, poi 6 linee: «la linea della piega PL3 non attraversa la lamiera»."""
    s, sid = _deflettore()
    assert s.sheet_fold(sid, 90, 'up', False, {'colpi': 8, 'raggio': 60})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    for k in range(6):
        assert s.sketch_add_polyline(sid, [[0, 190 - 8 * k], [600, 190 - 8 * k]], False)['ok']
    r = s.sheet_fold(sid, 15, 'down')
    assert r['ok'], r.get('message')
    sh = s.result.body.sheet
    assert len(sh.flanges) == 14 and all(abs(a - b) < 1e-6 for a, b in zip(sh.flat_size, (600, 400)))


def test_togli_materiale_con_linee_arrotondate_al_decimo():
    """Faccia profonda 249,7045 dopo i colpi, linee fino a 249,7: per 4 millesimi «la spezzata è aperta»."""
    s, sid = _deflettore()
    assert s.sheet_fold(sid, 90, 'up', False, {'colpi': 8, 'raggio': 60})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    v0 = volume(s.result.body.shape)
    for x in (30, 570):
        assert s.sketch_add_polyline(sid, [[x, 0], [x, 249.7]], False)['ok']
    r = s.create_from_sketch(sid, 'cut', {})
    assert r['ok'], r.get('message')
    assert abs((v0 - volume(s.result.body.shape)) - 2 * 30 * 249.7045 * 2) < 5


def test_svasatura_che_rompe_il_pezzo_si_rifiuta():
    """Su un foro già fatto, una svasatura più profonda dello spessore restava applicata e il pezzo in errore."""
    s = Service()
    assert s.new_project('lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 1.5, 'raggio': 1, 'k': 0.21})['ok']
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sid, [100, 100], 3.25)['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    r = s.sketch_hole_type(sid, ['C1'], {'tipo': 'svasato', 'D': 12, 'angolo': 90})
    assert not r['ok'] and 'profonda' in r['message']
    assert not s.state()['errors'] and not s.doc.sketch(sid).entities['C1'].get('hole')
    assert s.sketch_hole_type(sid, ['C1'], {'tipo': 'svasato', 'D': 8, 'angolo': 90})['ok']


def test_tabella_pieghe_con_i_colpi_in_fila():
    """I colpi del bumping a raggio (PL1.2…) andavano in testa alla tabella, prima di PL1."""
    s, sid = _deflettore()
    assert s.sheet_fold(sid, 90, 'up', False, {'colpi': 8, 'raggio': 60})['ok']
    nomi = [r['flange'] for r in s.result.body.sheet.summary()['bends']]
    assert nomi == ['PL1'] + [f'PL1.{k}' for k in range(2, 9)]
