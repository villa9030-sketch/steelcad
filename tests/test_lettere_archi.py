"""Lettere tagliate fatte di archi veri (02/11, «non riesci a raggiare tutto anziché avere migliaia di tratti?»): pochi
pezzi, fedeli al carattere entro 0,01 mm, niente microsegmenti nel DXF."""
import math

from cad_engine.sketch import testo


def _vicino(p, giro) -> float:
    """Quanto il punto p sta lontano dal contorno (linee e archi)."""
    d = math.inf
    for pz in giro:
        a, b = pz[1], pz[-1]
        if pz[0] == 'A':
            c = testo._centro(*pz[1:])
            if c is not None:
                r = math.dist(c, a)
                d = min(d, abs(math.dist(p, c) - r) if _sull_arco(p, c, *pz[1:]) else math.inf)
        lung2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        t = 0 if lung2 == 0 else max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / lung2))
        d = min(d, math.dist(p, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) if pz[0] == 'L' else
                min(math.dist(p, a), math.dist(p, b)))
    return d


def _sull_arco(p, c, a, m, b) -> bool:
    ang = lambda q: math.atan2(q[1] - c[1], q[0] - c[0]) % (2 * math.pi)  # noqa: E731
    giro = (ang(b) - ang(a)) % (2 * math.pi)
    if (ang(m) - ang(a)) % (2 * math.pi) > giro:
        return (ang(a) - ang(p)) % (2 * math.pi) <= (ang(a) - ang(b)) % (2 * math.pi)
    return (ang(p) - ang(a)) % (2 * math.pi) <= giro


def test_archi_fedeli_e_senza_microsegmenti():
    for font in ('allerta', 'saira'):
        curve = testo.contorni_curve('NK 10/15 ABRS8', 5.0, 0, 0, 0, font)
        pezzi = [pz for c in curve for pz in c]
        assert sum(pz[0] == 'A' for pz in pezzi) > 20
        prima = sum(1 if pz[0] == 'L' else 8 for ch in 'NK 10/15 ABRS8'   # prima: 8 trattini per curva
                    for gr in testo._glifo_stencil(font, ch)[0] for pz in gr)
        assert len(pezzi) < prima / 3, (len(pezzi), prima)
        assert min(math.dist(pz[1], pz[-1]) for pz in pezzi) >= testo.CORTO
        for giro in curve:                                          # contorni chiusi, pezzi attaccati esatti
            assert all(giro[i][-1] == giro[(i + 1) % len(giro)][1] for i in range(len(giro)))
        # ogni punto della curva del carattere sta sul contorno nuovo (entro la tolleranza, più i pezzi uniti)
        *_, alto = testo._font_stencil(font)
        k = 5.0 / alto
        avanti = 0.0
        peggio = 0.0
        for ch in 'NK 10/15 ABRS8':
            giri, larg = testo._glifo_stencil(font, ch)
            for gr in giri:
                for pz in gr:
                    f = testo._bezier((pz[0], *[(avanti + q[0] * k, q[1] * k) for q in pz[1:]]))
                    for i in range(11):
                        peggio = max(peggio, min(_vicino(f(i / 10), g) for g in curve))
            avanti += larg * k
        assert peggio < 0.025, (font, peggio)


def test_dxf_delle_lettere_tagliate_esce(tmp_path, monkeypatch):
    import ezdxf

    from app.service import Service
    monkeypatch.setenv('STEELCAD_HOME', str(tmp_path))
    s = Service()
    s.new_project('lamiera', {'name': 'T', 'larghezza': 120, 'profondita': 60, 'spessore': 2, 'raggio': 1, 'k': 0.4})
    sid = s.sketch_on_face('SM1/sopra')['sketch']
    assert s.sketch_add_text(sid, [10, 20], 'NK 10/15', 5, 0, 'allerta')['ok']
    assert s.create_from_sketch(sid, 'cut', {})['ok']
    r = s.export_dxf(str(tmp_path / 'l.dxf'))
    assert r['ok'] and 'Controlli superati' in r['message'], r
    archi = [e for e in ezdxf.readfile(tmp_path / 'l.dxf').modelspace() if e.dxftype() == 'ARC']
    assert len(archi) > 20                                          # archi veri, non trattini
