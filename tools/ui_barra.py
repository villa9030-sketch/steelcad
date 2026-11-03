"""Per le prove a schermo: i comandi della barra in alto.

Dal 04/11 la barra dei comandi sta su una riga: i comandi che si usano meno di ogni gruppo stanno nel menu
«Altro ▾» del gruppo. Sono gli stessi pulsanti di prima (stessi id e data-…), ma per cliccarli bisogna aprire
il menu, come farebbe una persona. Queste due funzioni lo fanno da sole:

    comando(pg, '#ribbon [data-tool="fillet"]')            # apre «Altro ▾» se serve, poi clic
    comando_visibile(pg, '#ribbon [data-azione="asola"]')  # c'è (anche se dentro un «Altro» chiuso)?
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
    """Clic su un comando della barra: se sta dentro «Altro ▾» chiuso, prima apre il menu."""
    pg.wait_for_function(APRI, arg=sel, timeout=kw.get('timeout', 30000))
    pg.click(sel, **kw)


def comando_visibile(pg, sel):
    """Il comando si può usare da qui (si vede, o si vede aprendo il suo «Altro ▾»)."""
    return pg.evaluate(VEDE, sel)
