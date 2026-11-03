"""Per le prove a schermo: i comandi della barra in alto.

Dal 04/11 la barra dei comandi sta su una riga: i comandi che si usano meno di ogni gruppo stanno nel menu
del gruppo, col suo nome («Bordi e tagli ▾», «Forme ▾», «Modifica ▾»…). Sono gli stessi pulsanti di prima (stessi id e data-…), ma per cliccarli bisogna aprire
il menu, come farebbe una persona. Queste due funzioni lo fanno da sole:

    comando(pg, '#ribbon [data-tool="fillet"]')            # apre il menu del gruppo se serve, poi clic
    comando_visibile(pg, '#ribbon [data-azione="asola"]')  # c'è (anche se dentro un menu chiuso)?
"""

APRI = """(s) => { const b = document.querySelector(s); if (!b) return false;
  const m = b.closest('.drop') && b.closest('.rmenu');
  if (m && !m.classList.contains('open')) {
    document.querySelectorAll('.menu-item.open').forEach(x => x.classList.remove('open')); m.classList.add('open'); }
  return true; }"""

VEDE = """(s) => { const b = document.querySelector(s); if (!b) return false;
  for (let e = b; e && e !== document.body; e = e.parentElement) {
    if (e.hidden) return false;
    if (!e.classList.contains('drop') && getComputedStyle(e).display === 'none') return false; }
  return true; }"""


def comando(pg, sel, **kw):
    """Clic su un comando della barra: se sta dentro un menu del gruppo chiuso, prima lo apre."""
    pg.wait_for_function(APRI, arg=sel, timeout=kw.get('timeout', 30000))
    pg.click(sel, **kw)


def comando_visibile(pg, sel):
    """Il comando si può usare da qui (si vede, o si vede aprendo il menu del suo gruppo)."""
    return pg.evaluate(VEDE, sel)


APRI_SCHEDA = """(t) => { const b = document.querySelector('#bottom .tabs button[data-tab="' + t + '"]');
  if (document.body.classList.contains('bottom-closed') || !b.classList.contains('on')) b.click(); }"""


def scheda(pg, tab):
    """Apre il cassetto in basso sulla scheda (bom, cut, sheet, info). Dal 04/11 un clic sulla scheda già aperta
    chiude il cassetto: qui si clicca solo se serve."""
    pg.evaluate(APRI_SCHEDA, tab)


def chiudi_cassetto(pg):
    """Chiude il cassetto in basso se è aperto (dal 04/11 è alto quanto le sue righe: la vista si accorcia)."""
    pg.evaluate("""() => { if (document.body.classList.contains('bottom-closed')) return;
      const b = document.querySelector('#bottom .tabs button.on'); if (b) b.click(); }""")


def pannello_intero(pg, attesa, timeout=10000):
    """Dopo il clic su un tubo: «⋯» della barretta apre il pannello intero. Se la risposta del motore arriva tardi
    (più di 2,5 s dal clic, PC carico) il pannello si apre già da solo, senza barretta: va bene lo stesso."""
    pg.wait_for_function(f"""() => document.querySelector('#mini-barra button.piu')
      || document.querySelector({attesa!r})""", timeout=timeout)
    if pg.is_visible('#mini-barra button.piu'):
        pg.click('#mini-barra button.piu')
    pg.wait_for_selector(attesa, timeout=timeout, state='attached')
