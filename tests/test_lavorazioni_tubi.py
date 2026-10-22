"""Lavorazioni sui tubi: sketch su una faccia di un'asta, la sagoma buca la parete (22/10)."""
import pytest

from cad_engine import Document, project_io, templates
from cad_engine.exporters import step
from cad_engine.structures import cut_list, lavorazioni


def _telaio(L=2000):
    doc = templates.telaio('Tavolo', L=L, P=1000, H=900, profilo='40x40x3', gambe='40x40x3')
    r = doc.rebuild()
    assert r.ok, [f.message for f in r.errors]
    return doc, r


def _asta(r, mid):
    return next(m for m in r.structures[0].members if m.id == mid)


def _sketch_su(doc, r, mid, normale=(0, 0, 1)):
    m = _asta(r, mid)
    side = lavorazioni.side_from_normal(m, normale)
    sk = doc.add_sketch({'tube': r.structures[0].id, 'member': mid, 'side': side}, f'Lavorazione {mid}')
    return sk, side


def _foro(doc, r, mid, x=150, d=10, through=False, members=None):
    sk, side = _sketch_su(doc, r, mid)
    m = _asta(r, mid)
    larga = m.profile.width if side[0] == 'y' else m.profile.height
    sk.circle(sk.point(x, larga / 2), d / 2)
    doc.add_feature('tube_cut', 'Foro', sketch=sk.id, structure=r.structures[0].id, side=side,
                    members=members or [mid], through=through)
    return sk


def test_lo_zero_dello_sketch_e_la_testa_del_tubo_sul_bordo_della_faccia():
    doc, r = _telaio()
    m = _asta(r, 'M1')                       # traverso del telaio sopra, tagliato a 45° alle due teste
    pl = lavorazioni.face_plane(m, lavorazioni.side_from_normal(m, (0, 0, 1)))
    assert pl.z_dir.Z == pytest.approx(1)    # la faccia di sopra guarda in su
    assert lavorazioni.describe_side(m, lavorazioni.side_from_normal(m, (0, 0, 1))) == 'sopra'
    # l'origine sta sullo spigolo della punta: X lungo il tubo, tutta la faccia (40) in Y positivo
    bb = pl.to_local_coords(m.solid).bounding_box()
    assert bb.min.X == pytest.approx(0, abs=1e-6)
    assert bb.max.X == pytest.approx(m.length, abs=1e-6)
    assert bb.min.Y == pytest.approx(0, abs=1e-6) and bb.max.Y == pytest.approx(40, abs=1e-6)
    assert bb.max.Z == pytest.approx(0, abs=1e-6)       # la faccia è a z = 0, il tubo sotto


def test_un_foro_buca_solo_la_parete_di_sopra():
    doc, r = _telaio()
    v0 = _asta(r, 'M1').solid.volume
    _foro(doc, r, 'M1')
    r2 = doc.rebuild()
    assert r2.ok, [f.message for f in r2.errors]
    m = _asta(r2, 'M1')
    tolto = v0 - m.solid.volume
    assert tolto == pytest.approx(3.14159 * 25 * 3, rel=0.02)      # Ø10 in una parete da 3
    assert m.lavorazioni and not _asta(r2, 'M2').lavorazioni


def test_passante_buca_le_due_pareti():
    doc, r = _telaio()
    v0 = _asta(r, 'M1').solid.volume
    _foro(doc, r, 'M1', through=True)
    r2 = doc.rebuild()
    assert r2.ok
    assert v0 - _asta(r2, 'M1').solid.volume == pytest.approx(2 * 3.14159 * 25 * 3, rel=0.02)


def test_la_stessa_lavorazione_sui_tubi_uguali_e_la_cut_list_li_separa():
    doc, r = _telaio()
    cl0 = cut_list(r.structures)
    _foro(doc, r, 'M1', members=['M1', 'M3'])           # i due lati lunghi
    r2 = doc.rebuild()
    assert r2.ok, [f.message for f in r2.errors]
    assert _asta(r2, 'M1').lavorazioni == _asta(r2, 'M3').lavorazioni != ()
    cl = cut_list(r2.structures)
    lavorate = [x for x in cl['rows'] if x['lavorata']]
    assert len(lavorate) == 1 and lavorate[0]['qty'] == 2
    assert cl['pieces'] == cl0['pieces']


def test_il_foro_resta_a_150_dalla_testa_se_il_telaio_si_allunga():
    doc, r = _telaio()
    _foro(doc, r, 'M1', x=150)
    doc.set_parameter('L', 2400)
    r2 = doc.rebuild()
    assert r2.ok, [f.message for f in r2.errors]
    m = _asta(r2, 'M1')
    pl = lavorazioni.face_plane(m, 'y+' if lavorazioni.side_from_normal(m, (0, 0, 1)) == 'y+' else
                                lavorazioni.side_from_normal(m, (0, 0, 1)))
    # il centro del foro: i bordi tondi del foro (Ø10), a 150 dalla testa
    tondi = [e for e in m.solid.edges() if e.geom_type.name == 'CIRCLE' and abs(e.radius - 5) < 1e-6]
    assert tondi
    c = pl.to_local_coords(tondi[0].arc_center)
    assert c.X == pytest.approx(150, abs=0.01) and c.Y == pytest.approx(20, abs=0.01)


def test_intaglio_sulla_testa_e_sagoma_fuori_dal_tubo():
    doc, r = _telaio()
    sk, side = _sketch_su(doc, r, 'M1')
    sk.rectangle(-10, 10, 30, 30)                        # esce dalla testa: un intaglio 30 × 20
    doc.add_feature('tube_cut', 'Intaglio', sketch=sk.id, structure='ST1', side=side, members=['M1'])
    r2 = doc.rebuild()
    assert r2.ok, [f.message for f in r2.errors]
    sk2, side2 = _sketch_su(doc, r2, 'M2')
    sk2.circle(sk2.point(-200, 20), 5)                              # prima della testa: non tocca niente
    doc.add_feature('tube_cut', 'Foro', sketch=sk2.id, structure='ST1', side=side2, members=['M2'])
    r3 = doc.rebuild()
    msg = [f.message for f in r3.errors]
    assert len(msg) == 1 and 'non tocca' in msg[0]


def test_tubo_tondo_non_ancora():
    doc = templates.telaio('Tavolo', profilo='Ø48.3x3.2', gambe='40x40x3')
    r = doc.rebuild()
    m = _asta(r, 'M1')
    with pytest.raises(Exception, match='tondi'):
        lavorazioni.face_plane(m, 'y+')


def test_si_salva_si_riapre_e_va_nello_step(tmp_path):
    doc, r = _telaio()
    _foro(doc, r, 'M1')
    p = tmp_path / 'tavolo.steelcad'
    project_io.save(doc, p)
    doc2 = project_io.load(p)
    r2 = doc2.rebuild()
    assert r2.ok, [f.message for f in r2.errors]
    assert _asta(r2, 'M1').lavorazioni
    step.export_project(doc2, r2, tmp_path / 'tavolo.step')
    assert (tmp_path / 'tavolo.step').stat().st_size > 1000


def test_dal_servizio_clic_sul_tubo_sketch_e_lavorazione():
    from app.service import Service
    svc = Service()
    svc._set(templates.telaio('Tavolo', L=2000, P=1000, H=900))
    assert sorted(svc.tubi_uguali('ST1/M1')) == ['M1', 'M3']
    r = svc.sketch_on_tube('ST1/M1', [0, 0, 1])
    assert r['ok'], r.get('message')
    sk = svc.doc.sketch(r['sketch'])
    assert any(e.get('ref') for e in sk.entities.values())        # i bordi della faccia in arancio
    sk.circle(sk.point(300, 20), 6)
    r = svc.lavora_tubo(r['sketch'], through=True, anche_uguali=True, nome='Fori Ø12')
    assert r['ok'], r.get('message')
    assert all(m.lavorazioni for m in svc.result.structures[0].members if m.id in ('M1', 'M3'))
    from cad_engine.tree import as_text, project_tree
    testo = as_text(project_tree(svc.doc, svc.result))
    assert 'Lavorazioni sui tubi' in testo and 'Fori Ø12 su M1, M3 (passante)' in testo and 'lavorati' in testo
    assert 'TAVOLO' in testo.splitlines()[0]
