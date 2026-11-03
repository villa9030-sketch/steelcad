"""03/11, struttura di Stefano (due sagome 807 × 725 collegate, tolto il lato sotto davanti): negli angoli davanti in
basso aveva scelto «A 45°», ma il montante di collegamento restava dritto e solo il fianco era a 45°. Il 45° scelto a
mano vale per tutti e due i tubi."""
import shutil
from pathlib import Path

import pytest

from app.service import Service

DATI = Path(__file__).parent / 'data' / 'struttura_45_collegamento.steelcad'


def test_45_scelto_a_mano_vale_anche_per_il_collegamento(tmp_path):
    f = tmp_path / 'struttura.steelcad'
    shutil.copy(DATI, f)
    s = Service()
    assert s.open(str(f))['ok']
    st = s.result.structures[0]
    for k in ('K1.1.P1', 'K1.1.P2'):
        x, y = (0, 0) if k.endswith('P1') else (807, 0)
        # i due tubi che arrivano nell'angolo (fianco della sagoma e montante di collegamento): tutti e due a 45°
        qui = [m for m in st.members
               if any(abs(p.X - x) < 1e-6 and abs(p.Y - y) < 1e-6 and abs(p.Z) < 1e-6 for p in (m.start, m.end))]
        assert len(qui) == 2, k
        for m in qui:
            assert any(abs(abs(c) - 45) < 0.01 for c in m.cuts), (k, m.id, m.cuts)
    assert st.warnings == []                                   # niente tubi uno dentro l'altro
