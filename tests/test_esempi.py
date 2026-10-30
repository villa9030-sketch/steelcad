"""Gli esempi della pagina iniziale (24/10): si aprono tutti, senza errori né avvisi, come lavoro nuovo."""
import pytest

from app.esempi import ESEMPI
from app.service import Service


@pytest.mark.parametrize('eid', [e['id'] for e in ESEMPI])
def test_esempio_si_apre_pulito(eid):
    s = Service()
    r = s.esempio(eid)
    assert r['ok'], r
    st = r['state']
    assert st['name'].startswith('Esempio') and st['path'] is None
    assert st['errors'] == [] and st['warnings'] == []
    assert st['undo'] == []                                      # Annulla non smonta l'esempio
