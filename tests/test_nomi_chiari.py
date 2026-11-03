"""03/11: i nomi che si vedono, in parole da officina: lo sketch nuovo «Disegno 1» (non «Vuoto»), gli accoppiamenti
dell'assieme coi due pezzi («Staffa su Piastra», senza il codice M1)."""
from app.assembly_service import _frase_mate
from app.service import Service


def _nodi(n):
    yield n
    for c in n.get('children', []):
        yield from _nodi(c)


def test_sketch_vuoto_si_chiama_disegno():
    s = Service()
    s.new_project('lamiera', {'name': 'Piastra', 'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 2, 'k': 0.4})
    s.sketch_on_face('SM1/sopra')
    s.sketch_on_face('SM1/sotto')
    nomi = [n['label'] for n in _nodi(s.state()['tree']) if n['kind'] == 'sketch' and n.get('vuoto')]
    assert nomi == ['Disegno 1', 'Disegno 2']
    assert not any(n['label'] == 'Vuoto' for n in _nodi(s.state()['tree']))


def test_accoppiamento_in_parole():
    nomi = {'I1': 'Telaio', 'I2': 'Piastra base'}
    m = {'id': 'M1', 'type': 'faccia', 'a': {'inst': 'I1'}, 'b': {'inst': 'I2'}}
    assert _frase_mate(m, nomi) == 'Piastra base su Telaio'
    assert _frase_mate({**m, 'flip': True}, nomi) == 'Piastra base a filo di Telaio'
    assert _frase_mate({**m, 'offset': 10}, nomi) == 'Piastra base su Telaio, distanza 10 mm'
    assert _frase_mate({**m, 'type': 'asse'}, nomi) == 'Piastra base in asse con Telaio'
    assert _frase_mate({**m, 'type': 'distanza', 'offset': 20}, nomi) == 'Piastra base a 20 mm da Telaio'
    assert _frase_mate({**m, 'type': 'angolo', 'angle': 90}, nomi) == 'Piastra base a 90° con Telaio'
    assert _frase_mate({**m, 'off': True}, nomi).endswith('(sospeso)')
    assert all('M1' not in _frase_mate({**m, 'type': t}, nomi) for t in
               ('faccia', 'asse', 'parallelo', 'perpendicolare', 'tangente', 'centra', 'blocca', 'spigolo', 'cono', 'testa'))


def test_accoppiamento_accordato_al_femminile():
    """04/11: «Piastra parallelo a Telaio», «Piastra bloccato su…» non si accordavano: forme che vanno con tutti e due."""
    nomi = {'I1': 'Telaio', 'I2': 'Piastra base'}
    m = {'id': 'M1', 'type': 'parallelo', 'a': {'inst': 'I1'}, 'b': {'inst': 'I2'}}
    assert _frase_mate(m, nomi) == 'Piastra base in parallelo con Telaio'
    assert _frase_mate({**m, 'type': 'blocca'}, nomi) == 'Piastra base in blocco con Telaio'
    # da «Appoggia»: quale coppia di lati e da quale bordo
    assert _frase_mate({**m, 'type': 'centra', 'lato': 'sinistra/destra'}, nomi) == 'Piastra base in mezzo a Telaio (sinistra/destra)'
    assert _frase_mate({**m, 'type': 'distanza', 'offset': 20, 'lato': 'davanti'}, nomi) == 'Piastra base a 20 mm dal bordo di Telaio (davanti)'
