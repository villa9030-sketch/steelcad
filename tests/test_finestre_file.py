"""Le finestre Apri/Salva di Windows: i filtri dei tipi di file devono passare il controllo di pywebview."""
import importlib


def test_filtri_dei_file_validi_anche_col_trattino():
    """'.steelcad-asm' ha il trattino: il controllo di pywebview lo rifiutava e "Apri un progetto…" dava errore."""
    main = importlib.import_module('app.main')
    import webview.util
    import webview.window
    for filtri in (main.FILTRO_PROGETTO, main.FILTRO_PEZZO, main.FILTRO_ASSIEME, main.FILTRO_DISEGNO):
        for f in filtri:
            assert webview.window.parse_file_type(f)
            assert webview.util.parse_file_type(f)
    assert webview.window.parse_file_type(main.FILTRO_PROGETTO[0]) == ('Progetto Radius', '*.steelcad;*.steelcad-asm')
