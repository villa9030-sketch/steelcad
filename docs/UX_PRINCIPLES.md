# SteelCAD — Principi di esperienza d'uso

1. **Il modo più veloce per fare carpenteria.** Se un'operazione comune
   richiede più di 2-3 azioni, il flusso è sbagliato.
2. **Si lavora su quello che si vede.** Clic su una faccia, uno spigolo, una
   linea: compaiono solo i comandi che hanno senso lì.
   - Faccia: Estrudi, Foro, Tasca, Sposta, Lamiera, Flangia (se compatibile).
   - Spigolo: Raccordo, Smusso, Piega, Misura.
   - Linea di struttura: Assegna profilo, Cambia, Ruota, Taglia, Estendi, Giunto, Copia.
3. **Nessun concetto del kernel in vista.** Mai Workbench, Body, Part,
   Datum, ShapeBinder, "entra/esci dallo sketch", Face7, Edge12.
4. **Le quote si cambiano dove stanno.** Clic su 1200, scrivo 1500, Invio.
5. **Tre modalità, non dieci ambienti:** Parte, Struttura, Lamiera.
6. **L'albero parla di carpenteria:** "Gambe: 4 × 70×70×4 — 890", non "Pad003".
7. **Ogni operazione mostra un'anteprima**; se è impossibile l'anteprima è
   rossa e c'è una frase che spiega perché.
8. **Messaggi in italiano semplice.** "Lo sketch ha ancora 2 gradi di
   libertà." "Questa quota è in conflitto con la quota 300 sul lato sotto."
9. **Il numero è sempre disponibile.** Si può trascinare, ma si può sempre
   scrivere il valore esatto.
10. **Pochi strumenti fissi**: barra piccola + menu contestuali + palette
    comandi (Ctrl+K) + pannello proprietà con solo ciò che serve.
11. **Niente funzioni finte.** Un pulsante che c'è funziona davvero.
12. **Undo sempre.** Ogni modifica si annulla con Ctrl+Z.

## Il motore serve la UX

Questi principi vincolano anche il motore: per esempio, i messaggi dello
sketch e delle feature li produce il motore (`cad_engine.sketch.solver`,
`cad_engine.errors`), così la UI non deve tradurre matematica in parole.
