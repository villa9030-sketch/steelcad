# Lamiera piegata

## Come si costruisce
Uno sketch chiuso (il contorno del piano) → feature **Lamiera** (`sheet`) con lo spessore →
**flange** sui lati dritti del contorno esterno. Le flange stanno dentro la feature (come le aste
dentro una struttura): una sola voce nell'albero, con una riga per flangia.

Dall'interfaccia:
- File → Nuovo → Lamiera;
- clic su un fianco della lamiera → "Flangia su questo lato";
- clic su una flangia → lunghezza, angolo, verso, posizione, fessura d'angolo e fori;
- scheda **Lamiera** in basso: dati di piega, tabella delle pieghe, anteprima dello sviluppo ed export DXF.

## Convenzioni (come un disegno d'officina)
- **Contorno = quota esterna** del pezzo finito (posizione "quota esterna sul contorno", default):
  una U 500×300 con ali da 30 misura fuori tutto 500 × 300 × 30.
  Con "piega dal bordo" il piano resta intero e la flangia si aggiunge fuori.
- **Lunghezza della flangia** = dallo spigolo vivo esterno (intersezione delle facce esterne) alla
  punta. Per 90° è l'altezza esterna dell'ala.
- **Fori sulla flangia**: `u` lungo il lato, dal primo punto della linea dello sketch; `v` dallo
  spigolo vivo esterno verso la punta. Un foro che tocca la zona di piega è rifiutato.
- **Angoli tra due flange**: ogni flangia si ferma dove incontra la linea di fine piano della
  vicina; nello sviluppo resta uno scarico quadrato. La "fessura d'angolo" aggiunge gioco.

## Angoli chiusi (scatole)
Tra due flange vicine, entrambe a 90° e piegate dallo stesso lato, l'angolo si sceglie nel
pannello della flangia:
- **aperto**: ogni flangia si ferma all'incrocio delle linee di fine piano; resta lo scarico quadrato;
- **chiuso, X sopra**: X si allunga fino a coprire lo spessore dell'altra, a filo della sua faccia
  esterna; l'altra arriva fino alla faccia interna di X, meno la fessura. La fessura la scegli tu:
  0 vuol dire a contatto;
- solo il tratto dritto si allunga, quindi in fondo all'angolo resta lo scarico della piega;
- le alette entrano nello sviluppo e la verifica area × spessore = volume con K 0,5 vale ancora.

## Flange sulla punta di altre flange (omega, scatole bordate, Z)
Una flangia si può piegare sul bordo libero (la punta) di un'altra flangia, anche a catena:
`{"id": "FL5", "parent": "FL1", "length": 20, "angle": 90, "direction": "up"}` (niente `edge`).
- Dall'interfaccia: passa col mouse vicino al bordo dove vuoi piegare: i bordi liberi (lati della base
  senza flangia e punte delle flange) si accendono in arancione con il nome e la lunghezza; clic →
  pannello "Flangia su questo bordo" solo per quello. I bordi nascosti dietro al pezzo non si accendono.
  Oppure clic su una flangia → sezione **Piega sulla punta**.
- **Verso**: "su" = verso dentro, continua a chiudere (bordo di una scatola, C); "giù" = verso fuori
  (tesa di un omega, Z).
- **Quote**: la lunghezza della madre resta misurata fino allo spigolo vivo esterno della nuova piega,
  quindi con "quota esterna sul contorno" tutte le quote sono esterne e il tratto dritto della madre si
  accorcia del setback della figlia. La figlia si misura dallo spigolo vivo esterno della sua piega: per
  una piega "giù" quello spigolo sta sulla faccia interna della madre (omega 60 con ali 40 e tese 25:
  fuori tutto 60 + 2·(25 − sp)).
- **Bordi che si incontrano negli angoli** (scatola bordata): al primo angolo il programma chiede come
  chiuderli (`"tip_corners"` della lamiera, vale per tutti gli angoli, si cambia dal pannello di un bordo):
  - *dritti, lati lunghi interi* (`long`, il default): i bordi dei lati lunghi passano, quelli dei corti si
    fermano contro (più la fessura d'angolo);
  - *dritti, lati corti interi* (`short`): il contrario;
  - *tagliati a 45°* (`miter`): i due bordi si incontrano sulla bisettrice; il taglio passa per l'incrocio
    delle linee dove cominciano i loro tratti dritti, così non entra nelle pieghe; la fessura d'angolo si
    divide a metà. Se i due bordi non sono complanari si fa dritto.
  Una flangia sulla punta che tocca qualcos'altro (non un bordo dello stesso livello) si accorcia sempre.
- **Sviluppo**: la striscia della figlia continua quella della madre dopo il suo tratto dritto
  (BA + tratto dritto per ogni piega). La verifica area × spessore = volume con K 0,5 vale anche qui
  (omega, scatola bordata, Z con piega a 45°, in `tests/test_flange_chain.py`).
- Eliminando una flangia se ne vanno anche quelle piegate sulla sua punta.

## Aggiungi materiale (linguetta)
Su una faccia piana della lamiera (base sopra/sotto, flangia dentro/fuori): "Disegna su questa faccia" →
disegna il contorno del materiale da aggiungere, attaccato al bordo della faccia → **Aggiungi materiale**.
- Diventa lamiera dello stesso spessore nel piano della faccia, senza pieghe; entra nello sviluppo attaccato
  alla striscia di quella faccia (feature `sheet_cut` con `"mode": "add"`).
- Se la spezzata parte e finisce sullo stesso bordo della faccia (le linee arancio), la si chiude da sola
  lungo quel bordo: basta disegnare la sagoma fuori dalla faccia.
- Esempio: una parete sull'estremità di un profilo piegato si allarga fino a coprirne la sezione.
- Controlli: deve attaccarsi al pezzo; un contorno tutto dentro la faccia non aggiunge niente; area aggiunta
  allo sviluppo × spessore = volume aggiunto, se no tocca un'altra parte o una piega ed è rifiutata.
- La linguetta e la faccia su cui è disegnata diventano **una faccia sola** (`ShapeUpgrade_UnifySameDomain`
  con lo storico dei nomi): la faccia unita tiene il nome della parete (es. `SM1/FL4/esterno`), così ci si
  ridisegna sopra e i bordi arancio sono il contorno intero.

## Bordo unico sopra una linguetta (angolo a 45°)
- Una flangia sulla punta di una parete che ha una linguetta fino alla punta continua anche sopra la
  linguetta (`"extend": [inizio, fine]`, mm oltre la madre): in automatico quando la si aggiunge, oppure con
  **Prolunga sopra la linguetta** nel pannello della flangia.
- La linguetta si ferma dove comincia la piega di quella flangia (nelle coordinate della faccia: uguale nel
  pezzo e nello sviluppo); la parte che nello sviluppo cadrebbe su lamiera che c'è già si toglie.
- Con gli angoli dei bordi **a 45°** il taglio vale anche tra bordi di livelli diversi (es. il bordo in cima
  a un profilo e quello della parete che lo chiude), se le loro facce stanno nello stesso piano (entro
  0,01 mm). Il prolungamento arriva fino alla linea del taglio. Se l'altezza è diversa l'angolo resta dritto e
  compare un avviso con la differenza.

## Raccordo/smusso degli spigoli del pezzo
Disegnando su una faccia, **Raccordo** o **Smusso** su uno spigolo del pezzo (dove si incontrano due bordi
arancio, oppure cliccando i due bordi) arrotondano il pezzo vero, non lo sketch:
- spigolo verso fuori → si toglie la punta (`sheet_cut`); spigolo verso dentro (es. dove una linguetta
  incontra la parete) → si aggiunge materiale (`sheet_cut` con `"mode": "add"`);
- diventa un piccolo sketch "raccordo spigolo" + la sua feature, messi subito dopo lo sketch aperto (vedono
  la stessa faccia); i bordi arancio dello sketch aperto prendono la forma nuova (arco/smusso di riferimento);
- vale anche per lo sviluppo (solo spigoli verso fuori) e per le piastre (taglio passante).

## Lamiera a contorno (la sezione disegnata diventa lamiera)
Scheda LAMIERA → **Contorno** (le istruzioni), oppure: clic sulla faccia di estremità (testata) della lamiera
→ "Disegna su questa faccia" → con la Linea disegna la **sezione** della lamiera partendo dallo spigolo di un
bordo libero (lato della base o punta di una flangia: gli spigoli arancio) → **Lamiera a contorno**.
- Ogni tratto diventa una flangia della catena: angolo e verso dal disegno, lunghezza = il tratto (da
  spigolo vivo a spigolo vivo, come le quote esterne), raggio della lamiera. La prima flangia sta sul bordo
  da cui parte la sezione, le altre ognuna sulla punta della precedente.
- Lo sketch si consuma: poi lunghezze, angoli, fori e chiusure si cambiano come in tutte le flange.
- Rifiutata, con il motivo, se non parte da un bordo libero perpendicolare alla faccia, se è chiusa, se
  ha cerchi, se due tratti sono in fila o se torna indietro oltre 170°.

## Chiudere la testata di un profilo chiuso (aletta di chiusura)
Su un profilo chiuso fatto di flange in catena (parete, tesa, ritorno…), dal pannello di una flangia →
**Chiudi la testata** → l'estremità (indicata con la direzione, es. "estremità X−") e la fessura verso le
altre pareti (`"end_tabs": [{"end": "u0"|"u1", "gap": 0.5}]` nella flangia).
- Dalla parete parte un'aletta piegata a 90° verso il vuoto del profilo, con il raggio della lamiera; la sua
  faccia esterna sta a filo dell'estremità (la lunghezza del pezzo non cambia); la parete si accorcia di
  (r + sp) dove parte la piega.
- La forma dell'aletta è il vuoto del profilo (dentro l'involucro delle pareti della catena, quindi anche se
  alla giunzione resta una fessura) ristretto della fessura; comincia a r dalla parete.
- Nello sviluppo l'aletta sta oltre la fine della striscia della sua parete: BA della piega a 90°, poi
  l'aletta stesa; la linea di piega si chiama "FLx chiusura 90° Rr". Verifica: con K 0,5 area × spessore =
  volume anche con le alette.
- Su un profilo aperto (o troppo stretto per il raggio) è rifiutata con il motivo.

## Disegnare su una faccia
Clic su una faccia piana → "Disegna su questa faccia": la faccia diventa il piano di lavoro dello
sketch. Si vede solo quella faccia, di fronte e inquadrata; il resto del pezzo si accende in
trasparenza con **Pezzo 3D** (tasto G). I bordi della faccia entrano nello sketch come linee di
costruzione fisse ("bordo del pezzo"): ci si aggancia, si quota da lì e si fa l'offset (doppio clic su un
bordo = tutto il contorno, poi Offset… verso dentro). Lo stesso sullo sviluppo. Uno sketch lasciato vuoto
sparisce uscendo. Poi:
- su una lamiera (base sopra o sotto, flangia dentro o fuori) → **Taglia attraverso**: il contorno
  attraversa lo spessore ed entra nello sviluppo, portato in piano nella posizione giusta.
  Un taglio che tocca una piega è rifiutato;
- su un pezzo pieno → **Taglia attraverso** (tasca passante) oppure **Estrudi** di una distanza.

I bordi complanari di una scatola che si toccano diventano un'unica faccia, col nome di uno solo: il
taglio va comunque al bordo su cui cade il contorno.

## Spiega: disegnare sullo sviluppo
**Spiega** (pulsante sulla vista, tasto U, scheda Lamiera) mostra lo sviluppo al posto del pezzo
piegato: contorno, linee di piega tratteggiate e, in rosso chiaro, le strisce delle pieghe.
**Disegna sullo sviluppo** apre uno sketch sul piano dello sviluppo (`{"flat": "SM1"}`). Con
**Taglia attraverso** ogni contorno chiuso:
- si taglia nello sviluppo esattamente dove l'hai disegnato;
- nel pezzo piegato va sul tratto piano dove cade (la base o una flangia, anche sulla punta di un'altra),
  portato al suo posto con le stesse coordinate locali usate per i tagli disegnati sulle facce.

- può attraversare le pieghe (asole, scarichi, finestre su più tratti): il contorno si divide sulle strisce
  di piega; i pezzi nei tratti piani vanno al loro posto, quelli nelle strisce si avvolgono sulla piega
  (faccia sul cilindro a metà spessore, angolo = distanza dall'inizio della striscia / BA × angolo della
  piega, cioè misurata sulla fibra neutra), poi attraverso lo spessore.

Controllo per ogni taglio: volume tolto dal pezzo piegato = area tolta dallo sviluppo × spessore nei tratti
piani, e area × spessore × (raggio medio / raggio neutro) nelle pieghe (uguale solo con K = 0,5); se non
torna il taglio è rifiutato.

## Regole di lamiera e tabella pieghe
- **Regole** (scheda LAMIERA → Regole): i dati di piega di una lamiera (materiale, spessore, raggio
  interno, metodo, K o deduzione) salvati con un nome in `Documenti/SteelCAD/regole_lamiera.json`
  (variabile `STEELCAD_RULES` per cambiarlo). "Usa" li applica alla lamiera aperta; se lo spessore è un
  parametro (sp), cambia il parametro. Non sono valori inventati: sono quelli che hai inserito tu.
- **Tabella pieghe** (scheda LAMIERA → Tabella pieghe): CSV con punto e virgola e virgola decimale
  (si apre in Excel): per ogni piega flangia, su cosa, lunghezza, angolo, verso, raggio, K, BA, BD,
  larghezza; in fondo spessore, materiale e sviluppo.

## Calcolo della piega
Nessun valore di default: spessore, raggio interno e metodo li dà l'utente (sono dati della
piegatrice). Se manca qualcosa la lamiera non si costruisce e la scheda dice cosa manca.

| Metodo | Da dove viene K |
|---|---|
| K-factor | scritto dall'utente (0–1) |
| DIN 6935 | k = 0,65 + 0,5·log10(r/s) per r/s < 5, altrimenti 1; K = k/2 |
| Deduzione a 90° | dalla tabella della pressa: BA = 2·setback − BD; vale solo per pieghe a 90° |

    BA      = θ · (r + K·t)
    setback = (r + t) · tan(θ/2)
    BD      = 2 · setback − BA
    sviluppo di un'ala = L − BD   (dallo spigolo vivo esterno)

## Lo sviluppo è verificabile
- È calcolato dalle stesse quote del 3D, non "srotolando" il solido. Le strisce delle flange sono
  lunghe BA + tratto dritto e partono dalla linea di fine piano.
- **Verifica incrociata**: con K = 0,5 la fibra neutra è a metà spessore, quindi area dello
  sviluppo × spessore = volume del solido di OpenCascade. I test lo controllano su U, vasca a 4
  flange, flange su/giù, "dal bordo", 45°/135° e fori; coincide a 1e-9.
- `test_parts/sheetmetal_u_2mm/expected.json` ha i conti a mano della U di riferimento.
- **Da fare con un pezzo vero**: piegare la U sulla pressa e misurare lo sviluppo. Poi si scrivono
  in quel file il raggio e il K reali.

## DXF dello sviluppo
- **CUT**: contorno e fori.
- **BEND**: linea tratteggiata al centro della piega, con scritta tipo "FL1 SU 90° R2".
- I controlli (contorni chiusi, doppioni, microsegmenti, unità mm) guardano solo il layer CUT.

## Limiti attuali
- Flange sui lati dritti del contorno esterno del piano e sulla punta di altre flange; non ancora sui
  fianchi di una flangia.
- Angoli chiusi (alette) solo tra flange sul contorno; i bordi sulle punte negli angoli si accorciano.
- Angoli chiusi solo tra flange a 90° nello stesso verso, con quota esterna sul contorno.
- Niente risvolti (oltre 170°).
- Estrusioni dopo la lamiera non entrano nello sviluppo, e l'export lo dice. I tagli disegnati su una
  faccia della lamiera invece ci entrano.
- Solid-to-sheet (da un STEP importato) è della Milestone 4.


## Orlo, fori speciali, persiane, imbutiture
- **Orlo (risvolto)**: flangia sulla punta a **180°** (pulsante "Orlo 180°" nella sezione Piega sulla punta). Lo
  spigolo vivo non esiste: la quota della parete arriva al bordo esterno della piega (raggio + spessore), il
  tratto dritto dell'orlo è lunghezza − (raggio + spessore). Tra 170° e 180° non si può (la quota esterna andrebbe
  all'infinito).
- **Tipo di foro** (sketch su faccia: seleziona i cerchi → "Tipo di foro…"):
  - *svasato*: Ø svasatura e angolo; dopo il taglio un cono coassiale sulla faccia dove hai disegnato; rifiutato se
    più profondo dello spessore. È una lavorazione: lo sviluppo resta quello del foro dritto;
  - *filettato*: M3…M16, il cerchio diventa il preforo da tabella (M6 → Ø5); la filettatura va nell'albero;
  - *inserto*: codice e Ø foro scritti da te (dal catalogo del fornitore), nell'albero col codice.
- **Persiane**: sketch su faccia con una linea per persiana (il bordo aperto) → "Persiane…" (larghezza, altezza).
  La cappa sale a sinistra della linea; nello sviluppo resta il taglio di lancia (fessura di 0,2 mm). Lo sketch con
  linee aperte va bene per le persiane.
- **Imbutiture**: un cerchio per bugna → "Imbutiture…" (profondità); calotta sferica verso fuori. Lo sviluppo non
  cambia. Persiane e imbutiture sono deformazioni: niente controllo sviluppo × spessore = volume.
- I tagli disegnati su una faccia passano dallo sviluppo: possono uscire dalla faccia e attraversare le pieghe.
  Una spezzata aperta che parte e finisce sul bordo dove comincia una piega si chiude **verso fuori**: lo scasso
  passa la piega e le flange che seguono (bordi, ritorni).

## Piega lungo una linea
Sketch sulla faccia di sopra/sotto della base (o sullo sviluppo): **una** linea che attraversa la lamiera da parte a
parte → **Piega su questa linea…** (angolo, verso, "piega l'altra parte"). La linea è lo spigolo vivo esterno della
piega; si piega la parte più piccola. La base si divide sulla linea e la parte piegata diventa una flangia sul nuovo
lato (`"folds": [{"id": "PL1", "a": [x, y], "b": [x, y], "angle", "direction", "flip"}]` nella lamiera), lunga
distanza massima dalla linea + deduzione di piega: **lo sviluppo resta quello disegnato**. Se la parte piegata non è
un rettangolo (linea obliqua, fianchi inclinati) la flangia si allarga e quello in più si toglie con un taglio sullo
sviluppo (anche nella piega). Sulla punta della piega si possono mettere altre flange. Limite: una flangia su un lato
che la linea taglia o porta via va tolta prima.

## Incastri automatici
Quando la punta di una flangia appoggia su un'altra faccia del pezzo (es. un profilo chiuso che torna sulla base), nel
pannello della flangia compare **Incastri sulla punta**: numero, larghezza, gioco, sporgenza → n linguette sulla punta
(nel piano della flangia, attraverso la lamiera di sotto) e n asole (larghezza + 2 gioco) × (spessore + 2 gioco)
sull'altra faccia. Sono uno sketch + taglio e uno sketch + "Aggiungi materiale": restano modificabili.
I tagli disegnati sulle facce partono a filo della faccia (prima sporgevano di 0,01 mm e rosicchiavano quello che ci
appoggia sopra).


## Coni e raccordi quadro-tondo (forme "a geometria")
Nuovo → **Cono / tronco di cono** oppure **Raccordo quadro-tondo**.

- **Misure finite.** Ø, lati e altezza sono quelli del pezzo finito: esterni di default, oppure interni o in
  asse lamiera. Lo sviluppo si calcola in asse lamiera.
  - Cono: l'asse si sposta di t/(2·cos α) in pianta.
  - Raccordo: di t/2 sui lati e sul tondo. È un'approssimazione: sulle facce inclinate la differenza è di qualche
    decimo.
- **Cono calandrato**: lo sviluppo è la corona circolare esatta.
  - raggi = distanze dall'apice lungo la generatrice;
  - angolo = 2π·r / L.
- **A pieghe (piegatrice)**: la superficie è divisa in facce piane, trapezi tra due generatrici per il cono e
  ventagli di triangoli dagli angoli della base per il raccordo. Le facce si ribaltano una dopo l'altra con le
  lunghezze vere; ogni linea tra due facce è una piega, con l'angolo tra le facce.
- **Numero di pieghe dal raggio**: passo sul bordo tondo = raggio/5, tra 8 e 40 mm. Si può scrivere a mano.
- **Correzione di piega messa nello sviluppo**: Δ = θ·(r + K·t) − 2·(r + t/2)·tan(θ/2) per ogni piega. Con R1 e
  K 0,21 sono circa −0,1 mm a piega, e su 30–40 pieghe fanno qualche millimetro: senza correzione la
  giunzione non chiuderebbe. Ogni faccia si sposta di Δ perpendicolare alla sua piega.
- **Uscite**: DXF dello sviluppo (contorno su CUT, pieghe numerate "P3 10,7°" su BEND), tabella pieghe CSV
  (numero, angolo, lunghezza della linea, correzione), tavole.
- **Raccordo eccentrico**: il centro del tondo si sposta di (ex, ey). La giunzione è a metà del lato davanti.
- **Controlli** (`tests/test_forme.py`):
  - corona del cono calandrato uguale al conto a mano;
  - senza correzione lo sviluppo ha l'area esatta delle facce 3D e ogni lato la sua lunghezza vera;
  - con la correzione lo sviluppo cambia della somma delle strisce Δ × lunghezza della piega.
- **Limiti**: sviluppo in un pezzo solo (non ancora a spicchi o a metà); tondo-tondo eccentrico e
  rettangolo-rettangolo da fare con lo stesso motore.
