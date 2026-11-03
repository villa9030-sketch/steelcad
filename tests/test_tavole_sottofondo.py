"""03/11: le tavole preparate in sottofondo tenevano il motore 20-26 s (assieme Ufficio): «Apri il pezzo» cliccato in
quel momento aspettava. Ora chi chiede qualcosa ferma la preparazione."""
import threading
import time

from app.main import Api


def test_una_richiesta_ferma_le_tavole_in_sottofondo(monkeypatch):
    api = Api()

    def lenta():                                       # come una preparazione lunga (tanti fogli)
        t = time.time()
        while time.time() - t < 15:
            pass
        return {'ok': True, 'fatto': True}
    monkeypatch.setattr(api._svc, 'prepara_tavole', lenta)
    esito = []
    th = threading.Thread(target=lambda: esito.append(api.prepara_tavole()))
    th.start()
    time.sleep(0.3)
    t = time.time()
    r = api.state()
    assert time.time() - t < 3 and r is not None
    th.join(5)
    assert esito and esito[0].get('interrotto')
    # dopo, tutto normale: niente fermate arrivate in ritardo
    assert api.state() is not None
    monkeypatch.setattr(api._svc, 'prepara_tavole', lambda: {'ok': True, 'fatto': True})
    assert api.prepara_tavole() == {'ok': True, 'fatto': True}
