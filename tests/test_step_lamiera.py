"""STEP di una lamiera → sviluppo (21/10). Prova senza file dei clienti: una lamiera fatta in SteelCAD, esportata in
STEP e riaperta: lo sviluppo dallo STEP deve tornare con quello di SteelCAD (stesso raggio e K)."""
import build123d as bd
import pytest

from app.service import Service


def _scatola(tmp_path):
    s = Service()
    assert s.new_project('lamiera', {'name': 'Vaschetta', 'larghezza': 300, 'profondita': 200, 'spessore': 2,
                                     'raggio': 2, 'k': 0.33})['ok']
    for e in ('L1', 'L2', 'L3', 'L4'):
        assert s.add_flange('SM1', e, {'length': 40})['ok']
    sk = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_circle(sk, [150, 100], 10)['ok'] and s.create_from_sketch(sk, 'cut', {})['ok']
    p = tmp_path / 'vaschetta.step'
    assert s.export_step(str(p))['ok']
    return s.result.body.sheet, p


def test_sviluppo_dallo_step_come_quello_di_steelcad(tmp_path):
    vero, p = _scatola(tmp_path)
    s = Service()
    r = s.import_step(str(p), 0.33)
    assert r['ok'], r.get('message')
    d = s.result.body.sheet
    assert abs(d.thickness - 2) < 1e-6 and len(d.bend_rows) == 4
    assert abs(d.flat_area - vero.flat_area) < 1.0                              # mm²
    assert sorted(round(x, 1) for x in d.flat_size) == sorted(round(x, 1) for x in vero.flat_size)
    assert sum(1 for e in d.flat.edges() if e.geom_type == bd.GeomType.CIRCLE) >= 1   # il foro c'è
    r = s.export_dxf(str(tmp_path / 'v.dxf'))
    assert r['ok'] and 'Controlli superati' in r['message']
    assert s.save(str(tmp_path / 'v.steelcad'))['ok']
    s2 = Service()
    assert s2.open(str(tmp_path / 'v.steelcad'))['ok'] and abs(s2.result.body.sheet.flat_area - d.flat_area) < 1e-6


def test_non_lamiera_si_rifiuta(tmp_path):
    s = Service()
    assert s.new_project('zero', {'name': 'Blocco'})['ok']
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    assert s.sketch_add_rectangle(sid, [0, 0], [50, 30])['ok'] and s.create_from_sketch(sid, 'plate', {'thickness': 40})['ok']
    p = tmp_path / 'blocco.step'
    assert s.export_step(str(p))['ok']
    r = Service().import_step(str(p))
    assert r['ok'] or 'lamiera' in r['message']


def test_step_assieme_elenco_pezzo_scelto_e_dxf_di_tutti(tmp_path):
    """28/10: lo STEP del cliente con più pezzi: l'elenco, si apre quello scelto, i DXF di tutte le lamiere."""
    s1 = Service()
    s1.esempio('staffa')
    blocco = bd.Cylinder(20, 60).moved(bd.Location((0, 0, 500)))           # un pezzo che non è lamiera (un perno)
    s0 = Service()
    s0.new_project('lamiera', {'name': 'V', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.33})
    for e in ('L1', 'L2', 'L3', 'L4'):
        s0.add_flange('SM1', e, {'length': 40})
    a = bd.Shape.cast(s0.result.body.shape)
    b = bd.Shape.cast(s1.result.body.shape).moved(bd.Location((0, 400, 0)))
    p = tmp_path / 'assieme.step'
    bd.export_step(bd.Compound(children=[a, b, blocco]), str(p))
    s = Service()
    r = s.import_step(str(p), 0.33)
    assert not r['ok'] and r['code'] == 'assieme' and len(r['pezzi']) == 3
    lam = [x for x in r['pezzi'] if x['lamiera']]
    assert len(lam) == 2 and {x['pieghe'] for x in lam} == {4, 1}
    assert any(not x['lamiera'] for x in r['pezzi'])
    i = next(x['i'] for x in lam if x['pieghe'] == 1)
    r = s.import_step(str(p), 0.33, i)
    assert r['ok'], r.get('message')
    assert len(s.result.body.sheet.bend_rows) == 1
    assert s.save(str(tmp_path / 'scelto.steelcad'))['ok']               # si riapre con lo stesso pezzo
    s2 = Service()
    assert s2.open(str(tmp_path / 'scelto.steelcad'))['ok'] and len(s2.result.body.sheet.bend_rows) == 1
    r = s.step_dxf_tutti(str(p), str(tmp_path / 'dxf'), 0.33)
    assert r['ok'] and len(r['fatti']) == 2 and len(r['saltati']) == 1, r
    assert all((tmp_path / 'dxf' / n).exists() for n in r['fatti'])


def test_step_assieme_diventa_assieme_di_radius(tmp_path):
    """29/10: lo STEP di un assieme si apre come assieme: un file per pezzo diverso (lamiere con lo sviluppo, il resto
    importato), i nomi del cliente, i pezzi ripetuti come copie, tutto al suo posto."""
    from cad_engine import assembly as A
    s1 = Service()
    s1.esempio('staffa')
    staffa = bd.Shape.cast(s1.result.body.shape)
    s0 = Service()
    s0.new_project('lamiera', {'name': 'V', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.33})
    for e in ('L1', 'L2', 'L3', 'L4'):
        s0.add_flange('SM1', e, {'length': 40})
    vasca = bd.Shape.cast(s0.result.body.shape)
    tutto = bd.Compound(label='Telaio', children=[
        bd.Compound(label='Vasca', children=[vasca]),
        bd.Compound(label='Staffa', children=[staffa.moved(bd.Location((0, -100, 0)))]),
        bd.Compound(label='Staffa', children=[staffa.moved(bd.Location((300, -100, 0), (0, 0, 1), 90))]),
        bd.Compound(label='Perno', children=[bd.Cylinder(10, 50).moved(bd.Location((150, 100, 60)))])])
    p = tmp_path / 'telaio.step'
    bd.export_step(tutto, str(p))
    s = Service()
    r = s.step_assieme(str(p), 0.33)
    assert r['ok'], r.get('message')
    assert '2 in lamiera' in r['message'] and '1 importati' in r['message']
    righe = {b['description'].split(',')[0]: b for b in s.state()['bom']}
    assert set(righe) == {'Vasca', 'Staffa', 'Perno'} and righe['Staffa']['qty'] == 2
    messo = bd.Compound(children=[A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']) for i in s.asm.instances])
    vero = bd.import_step(str(p))
    assert messo.volume == pytest.approx(vero.volume, rel=1e-4)
    assert all(abs(a - b) < 0.01 for a, b in zip(messo.bounding_box().size, vero.bounding_box().size))
    asm = next(tmp_path.glob('*.steelcad-asm'))                        # si riapre da file
    s2 = Service()
    assert s2.open(str(asm))['ok'] and len(s2.asm.instances) == 4
    assert s2.drawing_preview(s2.drawing_fields()['fields'])['ok']    # e ha le sue tavole
