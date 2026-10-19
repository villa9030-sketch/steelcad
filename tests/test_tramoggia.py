"""Lamiera da facce piane (poliedro) e il modello "Tramoggia con cassone": sviluppo, pezzi, pieghe e saldature."""
import math
import os
import tempfile

import build123d as bd
import pytest

os.environ.setdefault('STEELCAD_HOME', tempfile.mkdtemp())

from app.service import Service  # noqa: E402
from cad_engine import templates  # noqa: E402
from cad_engine.sheetmetal import poliedro as P  # noqa: E402

T, R, K = 3.0, 3.0, 0.4


@pytest.fixture(autouse=True)
def regole_a_parte(tmp_path, monkeypatch):
    monkeypatch.setenv('STEELCAD_RULES', str(tmp_path / 'regole.json'))


def guscio(A=600, B=600, Hc=400, a=200, b=200, Ht=500, bordo=40, aperti=True):
    sez = [P.Sezione(a, b, 0), P.Sezione(A, B, Ht), P.Sezione(A, B, Ht + Hc)]
    fasce = ['tramoggia', 'cassone']
    if bordo:
        sez.append(P.Sezione(A + 2 * bordo, B + 2 * bordo, Ht + Hc))
        fasce.append('bordo')
    return P.guscio_da_sezioni(sez, fasce, {2} if bordo and aperti else set())


def bd90():
    """La deduzione di una piega a 90° con misure esterne: 2·(r+t) − BA."""
    return 2 * (R + T) - math.pi / 2 * (R + K * T)


def test_spigoli_e_angoli():
    G = guscio()
    assert len(G.facce) == 12
    a = {k: s['angolo'] for k, s in G.spigoli.items()}
    assert a['lato:cassone:0'] == pytest.approx(90)
    assert a['giro:bordo:0'] == pytest.approx(90)
    # cambio di pendenza: tra la parete verticale e la falda (alta 500, rientra di 200)
    assert a['giro:cassone:0'] == pytest.approx(math.degrees(math.atan2(200, 500)), abs=1e-6)


def test_fascia_verticale_come_il_conto_a_mano():
    """Pieghe sugli spigoli verticali: le 4 pareti in fila, 3 pieghe a 90° → 4·600 − 3·BD."""
    G = guscio(bordo=0)
    tec = P.Tecnologia(T, R, K, 'esterno')
    pieghe = P.proponi(G, tec, (1500, 3000), P._forzati_divisione(G, 'verticali'))
    ps = P.pezzi(G, pieghe, tec)
    assert len(ps) == 1
    corto, lungo, _ = P.ingombro_minimo(ps[0].punti())
    assert lungo == pytest.approx(4 * 600 - 3 * bd90(), abs=0.05)
    # le saldature: i 4 spigoli della tramoggia e la giunzione verticale
    sald, _ = P.metri_saldatura(G, pieghe)
    falda = math.hypot(math.hypot(200, 500), 0)                  # (non serve la lunghezza esatta, solo che ci siano tutte)
    assert sald == pytest.approx((4 * G.spigoli['lato:tramoggia:0']['lung'] + 400) / 1000, abs=1e-6)
    assert falda > 0


def test_un_pezzo_per_lato_e_scelte_dell_utente():
    G = guscio()
    tec = P.Tecnologia(T, R, K, 'esterno')
    pieghe = P.proponi(G, tec, (1500, 3000), P._forzati_divisione(G, 'lati'))
    assert len(P.pezzi(G, pieghe, tec)) == 4
    # una saldatura scelta dall'utente resta saldatura, una piega scelta resta piega
    forzati = {'giro:cassone:0': 'saldatura', 'lato:cassone:1': 'piega'}
    pieghe = P.proponi(G, tec, (1500, 3000), forzati)
    assert 'giro:cassone:0' not in pieghe and 'lato:cassone:1' in pieghe


def test_i_pezzi_stanno_nel_foglio_e_non_si_sovrappongono():
    for kw in ({}, {'A': 1000, 'B': 1000, 'Hc': 700, 'a': 250, 'b': 250, 'Ht': 700}, {'A': 800, 'B': 600, 'Hc': 300}):
        G = guscio(**kw)
        tec = P.Tecnologia(T, R, K, 'esterno')
        pieghe = P.proponi(G, tec, (1500, 3000))
        for p in P.pezzi(G, pieghe, tec):
            assert P.sta_nel_foglio(p, (1500, 3000))
            assert P.sovrapposizione(p, G, {q['spigolo'] for q in p.pieghe}) <= 1.0


def test_foglio_piccolo_piu_pezzi():
    G = guscio()
    tec = P.Tecnologia(T, R, K, 'esterno')
    grande = P.pezzi(G, P.proponi(G, tec, (1500, 3000)), tec)
    piccolo = P.pezzi(G, P.proponi(G, tec, (700, 1000)), tec)
    assert len(piccolo) > len(grande)


def test_modello_nel_progetto(tmp_path):
    s = Service()
    r = s.new_project('tramoggia_cassone', {'name': 'Silo', 'A': 1000, 'B': 1000, 'Hc': 700, 'a': 250, 'b': 250, 'Ht': 700,
                                            'bordo': 40, 'flangia': 40, 'spessore': 3, 'raggio': 3, 'k': 0.4,
                                            'divisione': 'verticali'})
    assert r['ok'] and not s.state()['errors']
    solido = bd.Shape.cast(s.result.body.shape)
    assert solido.is_valid and len(solido.solids()) == 1
    sel = s.select('body')['selection']
    forma = sel['forma']
    assert forma['pezzi'] and all(p['nel_foglio'] for p in forma['pezzi'])
    # scelta di uno spigolo, che resta quando cambia una misura
    spig = next(x for x in forma['spigoli'] if x['key'].startswith('giro:cassone'))
    assert s.set_shape_edge(sel['tpl_id'], spig['key'], 'saldatura')['ok']
    assert s.structure_template_apply(sel['tpl_id'], {'A': 900})['ok']
    dopo = {x['key']: x for x in s.select('body')['selection']['forma']['spigoli']}
    assert dopo[spig['key']]['scelta'] == 'saldatura' and dopo[spig['key']]['scelto_da'] == 'te'
    # sviluppo per il laser, tavole, tabella pieghe; Annulla e Salva/Apri
    assert s.export_dxf(str(tmp_path / 'silo.dxf'))['ok']
    assert s.drawing_preview(None, False)['ok']
    assert s.export_bend_table(str(tmp_path / 'silo.csv'))['ok']
    assert s.save(str(tmp_path / 'silo.steelcad'))['ok']
    s2 = Service()
    assert s2.open(str(tmp_path / 'silo.steelcad'))['ok'] and not s2.state()['errors']
    assert s.undo()['ok'] and s.undo()['ok']


@pytest.mark.parametrize('valori', [{'Ht': 0}, {'a': -5}, {'foglio': '1500'}, {'angoli_bordo': 'boh'}, {'smusso': 600},
                                    {'divisione': 'boh'}])
def test_misure_assurde(valori):
    """O si rifiuta con un messaggio chiaro, o il pezzo nasce ma con l'errore segnalato: mai in silenzio."""
    s = Service()
    r = s.new_project('tramoggia_cassone', {'raggio': 3, 'k': 0.4, **valori})
    if r['ok']:
        assert s.state()['errors'], valori
    else:
        assert 'Errore interno' not in r['message'], r['message']


def test_senza_cassone_e_con_smusso():
    for kw in ({'Hc': 0}, {'smusso': 80}, {'ex': 150, 'ey': -100}, {'angoli_bordo': '45'}):
        doc = templates.tramoggia_cassone(raggio=3, k=0.4, **kw)
        r = doc.rebuild()
        assert r.ok, (kw, [e.message for e in r.errors])
        assert bd.Shape.cast(r.body.shape).is_valid
