# Assiemi

Più pezzi SteelCAD messi insieme. Un assieme è un file `.steelcad-asm` che **richiama** i file dei pezzi
(`.steelcad`): se un pezzo cambia, l'assieme lo rilegge da solo (guarda la data del file).

## Come si usa
1. Pagina iniziale → **Assieme** (o palette: "Nuovo assieme").
2. Scheda **ASSIEME** → **Inserisci pezzo**: ogni pezzo entra a destra di quelli che ci sono. Lo stesso file si può
   inserire più volte (quantità in distinta).
3. **Faccia su faccia**: clic sulla faccia del pezzo che sta fermo, poi su quella del pezzo da appoggiare (normali
   opposte). Nel pannello dell'accoppiamento: distanza, "Allinea invece di affacciare", Sospendi, Elimina.
4. **Foro su foro**: clic su un foro (faccia cilindrica) del pezzo fermo, poi su un foro dell'altro: stesso asse.
   Con faccia su faccia + due fori il pezzo è fissato del tutto.
5. Il pannello del pezzo: sposta (X, Y, Z), ruota di 90° attorno a X/Y/Z, **Fermo** (gli altri si appoggiano a lui;
   di base è il primo inserito), **Apri il pezzo** (si lavora sul pezzo; **← Assieme** in alto per tornare, dopo
   aver salvato), Togli dall'assieme.
6. **Interferenze**: le coppie di pezzi che si compenetrano, con il volume in comune; si accendono in giallo.
7. **Distinta** (in basso): una riga per pezzo con quantità, materiale, spessore, sviluppo e peso; totale.
8. **STEP**: tutto l'assieme, ogni pezzo al suo posto. DXF e tabella pieghe si fanno per ogni pezzo (aprilo).

## Incastri tra due pezzi
Clic sulla **punta di una flangia** che appoggia su una faccia di un altro pezzo: nel pannello compare **Incastri con
…** (quante, larghezza, gioco, sporgenza). Le linguette vanno nel file del primo pezzo (nel piano della flangia,
attraverso l'altra lamiera), le asole nel file del secondo: **i due file vengono modificati e salvati** (resta la
copia `.bak`), e cambiano tutte le copie di quei pezzi. Le linguette si distribuiscono solo sul tratto dove la punta
appoggia davvero.

## Come funziona il risolutore
Ogni copia ha una rotazione R e una traslazione T (punto nel mondo = R · punto del pezzo + T). Il pezzo fermo non si
muove; gli altri, in ordine di collegamento, prima ruotano (le direzioni delle facce e degli assi: la rotazione più
piccola, o Kabsch se le direzioni sono più di una; con due fori paralleli si fissa anche la rotazione attorno
all'asse), poi traslano del minimo che rispetta tutti gli accoppiamenti (minimi quadrati partendo da dov'erano).
I gradi di libertà liberi restano come li hai lasciati. Gli accoppiamenti salvano nome e punto della faccia: se il
pezzo cambia, si ritrova la faccia con quel nome più vicina. Se un accoppiamento non si riesce a rispettare compare
un avviso con lo scarto.

## Limiti
- Incastri tra pezzi: per ora dalla punta di una flangia.
- Niente vista esplosa né accoppiamenti ad angolo o distanza tra assi (si aggiungono se servono).
