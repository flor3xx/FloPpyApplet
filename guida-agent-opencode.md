# Guida per opencode: costruire il comando `agent` (dashboard delle sessioni e dei sotto agenti)

> Questo documento è un'istruzione completa per te, opencode. Leggilo tutto prima di scrivere codice. Se nel progetto o nella home esiste un `AGENTS.md`, rispetta anche le sue regole. Lavora per fasi, testa ogni fase e fermati a chiedermi conferma solo dove indicato.

---

## 1. Obiettivo

Costruire un programma che io avvio scrivendo **`agent`** nel terminale. Si apre una finestra che mostra, **in tempo reale**, tutte le sessioni di opencode aperte sul mio PC, con l'agente master e i sotto agenti di ciascuna sessione, cosa stanno facendo e il loro stato. Inoltre, quando un agente cambia stato o finisce un task, devo ricevere una **notifica desktop**.

### Ambiente (vincoli fissi)
- Sistema: **LMDE (Linux Mint Debian Edition)** con desktop **Cinnamon**.
- Uso opencode con i **modelli di OmniRoute** (gateway/proxy locale per i modelli). Non dare per scontato che i modelli siano Anthropic e non toccare la configurazione dei provider di OmniRoute in `opencode.json`.
- Il programma deve funzionare in locale, senza servizi cloud e senza account.
- Sono un utente non esperto di sistemi: preferisco soluzioni semplici, poche dipendenze, e istruzioni di installazione chiare in italiano.

---

## 2. Cosa deve vedere l'utente (specifica della finestra)

### 2.1 Layout
```
┌──────────────────────────────────────────────────┬──────┐
│  BARRA TOKEN (sessione selezionata)              │  1   │
├──────────────────────────────────────────────────┤  2   │
│                                                  │  3   │
│            [SVG]  AGENTE MASTER (grande)         │  …   │
│                   cosa sta facendo               │      │
│                                                  │ barra│
│   [SVG] sotto agente 1 — cosa fa                 │ sess.│
│   [SVG] sotto agente 2 — cosa fa                 │      │
│   [SVG] sotto agente 3 — cosa fa                 │      │
└──────────────────────────────────────────────────┴──────┘
```

- **Barra a destra (sessioni)**: una colonna verticale di pulsanti numerati `1`, `2`, `3`, … uno per ogni istanza di opencode attualmente aperta. Cliccando un numero, il resto della finestra mostra quella sessione. Ogni pulsante ha un pallino di stato (vedi colori) che riassume lo stato **peggiore** tra tutti gli agenti di quella sessione, così vedo subito se la sessione 3 ha bisogno di me anche mentre guardo la 1. Tooltip al passaggio del mouse: nome della cartella di progetto e da quanto tempo è aperta.
- **Barra in alto (token)**: mostra i token usati **fino a quel momento nella sessione selezionata**: input, output, reasoning (se presente), cache (lettura/scrittura) e totale. Aggiornata in tempo reale.
- **Agente master**: **grande e centrato**. Con **affianco** scritto cosa sta facendo in questo momento. Il master è l'agente con cui parlo nella chat (quello principale, es. `build` o `plan`).
- **Sotto agenti**: **più piccoli, sotto il master**, in elenco o griglia. Ognuno con **affianco** scritto cosa sta facendo (nome/tipo del sotto agente + descrizione del task).
- Se non ci sono sessioni aperte: schermata vuota con il messaggio "Nessuna sessione di opencode aperta".
- Se una sessione non ha sotto agenti: mostra solo il master.

### 2.2 SVG e colori
- **Tutti gli agenti (master e sotto agenti) usano lo stesso SVG** (un semplice robot/avatar disegnato da te, minimale). Cambia **solo il colore**, controllato da una variabile CSS, così esiste un unico file SVG.
- Stati e colori:
  | Stato | Quando | Colore |
  |---|---|---|
  | **Normale** | sta lavorando regolarmente **oppure** ha finito il task | colore base (es. azzurro/verde neutro) |
  | **Viola** | **serve una mia conferma o risposta** (richiesta di permesso, domanda a me) | viola `#8b5cf6` |
  | **Rosso** | **ci sono problemi** (errori) | rosso `#ef4444` |
- Per non affidarsi al solo colore: accanto a ogni agente mostra anche una piccola etichetta di testo dello stato: `In lavoro`, `Completato`, `Serve la tua conferma`, `Problema`. Un'animazione leggera (pulsazione) è ammessa solo per viola e rosso.
- Tema scuro, testo leggibile, interfaccia in **italiano**.

### 2.3 "Cosa sta facendo" (testo accanto a ogni agente)
Ricavalo in questo ordine di priorità:
1. Se l'agente ha una lista di todo (strumento `todowrite` / evento `todo.updated`), la voce `in_progress`.
2. Altrimenti lo strumento in esecuzione, scritto in modo umano: `Modifica src/app.js`, `Esegue: npm test`, `Legge README.md`, `Cerca nel web`, ecc.
3. Altrimenti, se ha finito il turno: `In attesa di un tuo messaggio`.
4. Per i sotto agenti, usa come titolo il tipo + la descrizione del task con cui sono stati lanciati (parametri `subagent_type` e `description` dello strumento `task`, oppure il titolo della sessione figlia), seguito dall'attività corrente se la conosci.
Testo breve (max ~80 caratteri, con ellissi) e il testo completo in tooltip.

---

## 3. Notifiche (requisito importante)

Per **ogni agente di ogni sessione** (master e sotto agenti), quando:
- **cambia stato** (es. da lavoro a viola, da lavoro a rosso, da viola a lavoro), oppure
- **finisce il task**,

devo ricevere una **notifica desktop Cinnamon** con questo contenuto:

```
Sessione <N> · <compito> · <stato>
```
Esempi: `Sessione 2 · Refactoring del login · Completato` / `Sessione 3 · Esegue i test · Serve la tua conferma` / `Sessione 1 · Sotto agente "ricerca API" · Problema`.

Dettagli:
- Usa `notify-send` (pacchetto `libnotify-bin`; se manca, dimmelo e indicami il comando `apt` per installarlo, non installarlo da solo senza avvisarmi).
- Urgenza: `critical` per viola e rosso, `normal` per Completato.
- Non mandare notifiche al **primo avvio** di un agente (nessun cambio di stato reale) e non mandare duplicati: se lo stato non cambia, nessuna notifica. Raggruppa eventi identici arrivati entro 1 secondo.
- Le notifiche devono partire **anche se la finestra è chiusa**, finché il programma in background è attivo (vedi architettura).
- Il numero di sessione nella notifica è lo stesso numero del pulsante nella barra a destra.

---

## 4. Architettura consigliata

Tre pezzi, tutti locali:

1. **Plugin di opencode** (`agent-plugin.js`): opencode supporta i *plugin* (file JavaScript/TypeScript caricati all'avvio) che ricevono gli eventi interni (sessione creata, strumento eseguito, richiesta di permesso, sessione inattiva, errore, ecc.). Sostituisce gli "hook" di Claude Code ed è la fonte principale degli stati.
2. **Daemon in background** (Python 3): riceve gli eventi, mantiene lo stato di sessioni/agenti, calcola i token, manda le notifiche e serve la pagina web della dashboard.
3. **Finestra della dashboard**: una pagina web (HTML + CSS + JS vanilla, **nessun build step**, aggiornata via **Server-Sent Events**) mostrata in una finestra dedicata.

### Scelte tecniche
- **Python 3** (già presente su LMDE) per il daemon. Usa un venv nella cartella del progetto. Preferisci la libreria standard; se serve un framework leggero, `FastAPI + uvicorn` va bene. Evita Node/Electron per il daemon e la dashboard. Il solo file JavaScript ammesso è il plugin, perché opencode lo richiede (gira dentro opencode, **non** devi installare nulla per eseguirlo).
- Server **solo su `127.0.0.1`** (mai `0.0.0.0`), porta fissa configurabile (default `47321`).
- Finestra: prova in quest'ordine e usa il primo che funziona davvero su questa macchina: (a) `google-chrome` / `chromium` con `--app=http://127.0.0.1:47321` e una `--user-data-dir` dedicata; (b) `pywebview` (richiede `python3-gi` e `gir1.2-webkit2-4.1`); (c) `xdg-open` come ultima spiaggia. Testa quale browser è installato prima di scegliere.
- Cartella di lavoro del progetto: `~/opencode-agent-dashboard/`. Dati/spool in `~/.local/share/opencode-agent-dashboard/`. Comandi installati in `~/.local/bin/` (verifica che sia nel `PATH`, altrimenti spiegami come aggiungerlo).

### Comando `agent`
- `agent` → se il daemon non è attivo lo avvia in background (istanza **singola**, usa un lock file), poi apre la finestra. Se è già attivo, apre/porta in primo piano solo la finestra.
- `agent stop` → ferma il daemon. `agent status` → dice se è attivo, quante sessioni vede. `agent logs` → mostra le ultime righe di log.
- `agent uninstall-plugin` → rimuove il plugin (vedi sezione 7).
- Chiudere la finestra **non** ferma il daemon (così le notifiche continuano).

---

## 5. Come rilevare sessioni, agenti e stati

> **Attenzione:** i nomi esatti di eventi e campi di opencode cambiano tra le versioni. **Non fidarti della memoria**: nella Fase 0 verifica la documentazione ufficiale (cerca "opencode plugins" e "opencode server / SDK / events") e gli eventi reali sulla macchina. Quanto scritto qui sotto è il punto di partenza, da confermare.

### 5.1 Sessioni
- Ogni istanza di opencode (ogni terminale/TUI aperto) carica il plugin nel **proprio processo**. Quindi la **chiave stabile della sessione = il PID del processo opencode** (`process.pid` dentro il plugin), che invii al daemon insieme a ogni evento. Non servono salti tra processi padre come con Claude Code.
- Dentro la stessa istanza possono esistere più `sessionID` (nuova chat, `/new`, cambio sessione): il pulsante numerato rappresenta l'**istanza** (PID) e mostra la sessione attualmente attiva.
- Il plugin riceve il contesto del progetto (cartella di lavoro, client SDK): usalo per leggere la cartella di progetto da mostrare nel tooltip.
- **Numerazione**: assegna i numeri 1, 2, 3… in ordine di apertura; quando un'istanza si chiude il suo numero si libera e può essere riusato dalla successiva. Un numero non deve cambiare finché l'istanza è aperta.
- **Pulizia**: ogni ~5 secondi controlla che il PID esista ancora (`/proc/<pid>`). Se è sparito (terminale chiuso, crash), rimuovi la sessione.
- **Istanze già aperte prima dell'installazione del plugin**: opencode carica i plugin all'avvio, quindi queste non riporteranno nulla finché non vengono riavviate. Scrivilo chiaramente nelle istruzioni finali.

### 5.2 Master e sotto agenti
- Il **master** esiste sempre quando c'è una sessione.
- In opencode un **sotto agente** è una **sessione figlia** creata dallo strumento `task` (o da una menzione `@agente`): ha un `parentID` che punta alla sessione del master. Rileva l'evento di creazione sessione e controlla `parentID`: se presente, è un sotto agente di quella sessione.
- Il tipo e la descrizione del task li trovi nei parametri dello strumento `task` nel master (evento di esecuzione strumento, prima della chiamata) e/o nel titolo della sessione figlia.
- La **fine** del sotto agente: la sessione figlia torna inattiva (idle) o il `task` del master restituisce il risultato; con errore = problema.
- Più sotto agenti in parallelo devono essere tutti visibili, ognuno col suo stato.
- **Fallback robusto**: se gli eventi non bastano, interroga il server locale di opencode (API HTTP / SDK: elenco sessioni, messaggi e figli di una sessione) oppure leggi lo storage su disco (di norma sotto `~/.local/share/opencode/`). Verifica nella Fase 0 cosa è disponibile nella mia versione.

### 5.3 Stati
- **Normale / In lavoro**: sessione "busy", messaggi dell'assistente in corso, strumenti in esecuzione o completati senza problemi.
- **Normale / Completato**: la sessione diventa inattiva (`session.idle` o stato idle equivalente) per il master; fine della sessione figlia / risultato del `task` per i sotto agenti.
- **Viola (serve conferma)**:
  - richiesta di permesso (eventi tipo `permission.asked` / `permission.updated`, o l'hook `permission.ask` del plugin: verifica il nome nella mia versione);
  - strumento che pone una domanda all'utente (es. strumento `question`, se esiste nella mia versione);
  - esce dal viola quando il permesso viene risposto o arriva il primo evento successivo di attività.
  - Se il blocco avviene in un sotto agente, colora viola **sia il master sia i sotto agenti in corso**.
- **Rosso (problema)**: errori che richiedono attenzione, non un singolo comando fallito normale (un test che non passa è normale durante il lavoro). Considera problema: evento di errore di sessione (`session.error`) o errore API / del provider (utile con OmniRoute: modello non raggiungibile, rate limit, tentativi ripetuti "retry", ecc.), **3 o più errori di strumento consecutivi**, sotto agente terminato con errore. Torna normale quando l'agente riprende a lavorare con successo.

---

## 6. Token usati

- Gli eventi dei messaggi dell'assistente contengono già i token (campo `tokens` con input, output, reasoning e cache lettura/scrittura, nella versione attuale: **verificalo**). Calcola dai messaggi dell'assistente, in modo incrementale.
- **Deduplica**: lo stesso messaggio viene aggiornato più volte durante lo streaming. Conta ogni messaggio **una sola volta** (usa l'ultimo valore per `message id`, sostituendo il precedente, non sommando).
- Includi anche i token delle sessioni figlie (sotto agenti) nel totale della sessione selezionata.
- Mostra: input · output · reasoning · cache letta · cache scritta · **totale**. Numeri formattati (es. `12.4k`).
- **OmniRoute**: i campi dei token dipendono da cosa il gateway restituisce. Se per un modello risultano assenti o a zero, mostra `n/d` oppure una stima (caratteri/4) **chiaramente indicata come "stima"**. Non calcolare costi in euro/dollari (ignora il campo `cost` di opencode). Non sapendo la finestra di contesto dei modelli di OmniRoute, non mostrare percentuali di contesto (al massimo rendile opzionali via file di configurazione).

---

## 7. Installazione del plugin (sicura)

1. Il plugin è **un singolo file** in una cartella dei plugin di opencode: a livello utente di norma `~/.config/opencode/plugin/` (controlla il nome esatto della cartella, `plugin` o `plugins`, nella documentazione della mia versione). **Non** modificare `opencode.json` se non è strettamente necessario; se lo è, fai prima un **backup** (`opencode.json.bak-AAAAMMGG`), **unisci** senza sovrascrivere e mostrami il diff prima di salvare.
2. Se nella cartella esistono già altri plugin, **non toccarli**.
3. Il plugin si iscrive agli eventi utili: creazione/aggiornamento/eliminazione sessione, stato sessione (busy/idle/retry), errore di sessione, aggiornamento messaggi e parti (strumenti), todo aggiornati, richieste di permesso e relative risposte, esecuzione strumenti prima/dopo.
4. Regole d'oro del plugin `agent-plugin.js`:
   - **Non deve mai scrivere sul terminale** (niente `console.log` / stdout / stderr: sporcherebbe la TUI) e **non deve mai lanciare eccezioni**: tutto in `try/catch`.
   - **Deve essere velocissimo** e **non bloccare mai** opencode: invia gli eventi al daemon in modo asincrono (`fetch` a `127.0.0.1` con timeout breve, senza `await` bloccante). Se il daemon non risponde, scrive l'evento in uno **spool** (`events.jsonl`) che il daemon legge all'avvio.
   - Aggiunge all'evento: timestamp, PID di opencode, cartella di progetto e i campi originali dell'evento.
   - Se non riesce a inviare nulla, opencode deve funzionare normalmente.
5. Fornisci `agent uninstall-plugin` che rimuove **solo** il file che hai aggiunto (e l'eventuale voce aggiunta in `opencode.json`, ripristinando il backup) e lascia tutto il resto intatto.

---

## 8. Fasi di lavoro (segui questo ordine)

**Fase 0: Scoperta (nessun codice definitivo)**
- Controlla versione di opencode, Python, browser installati, presenza di `notify-send`, desktop (Cinnamon).
- Leggi la documentazione ufficiale di plugin, eventi e server/SDK di opencode.
- Installa **temporaneamente** un plugin che salva su file i payload grezzi di tutti gli eventi, apri una sessione di prova che lanci un sotto agente, e studia i campi reali (sessioni figlie con `parentID`, permessi, errori, `tokens`).
- Riassumimi in 10 righe cosa hai scoperto e come questo cambia il piano. **Fermati e aspetta il mio ok.**

**Fase 1: Daemon + modello di stato** (istanze, numerazione, master, sotto agenti, stati, pulizia PID) con un simulatore di eventi per testare senza opencode.

**Fase 2: Plugin** (`agent-plugin.js`, installazione sicura, spool, disinstallazione).

**Fase 3: Token** (calcolo incrementale, deduplica per id messaggio, sotto agenti).

**Fase 4: Interfaccia** (layout della sezione 2, SVG unico, colori, SSE, stato vuoto, responsive nella finestra).

**Fase 5: Notifiche** (sezione 3, anti-duplicati, nessuna al primo avvio).

**Fase 6: Comando `agent`** (`agent`, `stop`, `status`, `logs`, `uninstall-plugin`, istanza singola, finestra).

**Fase 7: Test end-to-end** con 2-3 istanze reali di opencode in terminali diversi.

**Fase 8: Documentazione**: un `README.md` in italiano con installazione, uso, come disinstallare, risoluzione problemi.

---

## 9. Criteri di accettazione (controlla uno per uno prima di dirmi "finito")

- [ ] Scrivendo `agent` nel terminale si apre la finestra; ripetendolo non crea una seconda istanza.
- [ ] Aprendo 3 istanze di opencode in 3 terminali, la barra a destra mostra `1 2 3`; chiudendone una sparisce entro ~5 secondi.
- [ ] Cliccando un numero vedo i dati di **quella** sessione.
- [ ] In alto vedo i token della sessione selezionata e crescono mentre lavora.
- [ ] Il master è grande e centrato con accanto cosa sta facendo; i sotto agenti sono piccoli sotto il master, ciascuno con il proprio compito.
- [ ] Tutti gli agenti hanno lo stesso SVG; è normale se lavorano o hanno finito, **viola** quando opencode mi chiede un permesso, **rosso** in caso di problemi.
- [ ] Ricevo una notifica `Sessione N · compito · stato` a ogni cambio di stato o fine task, per master e sotto agenti, anche con la finestra chiusa, senza duplicati.
- [ ] Il plugin non rallenta opencode, non scrive nulla nella TUI; se il daemon è spento, opencode funziona normalmente.
- [ ] Se ho toccato `opencode.json` esiste il backup, e `agent uninstall-plugin` ripristina tutto.
- [ ] Funziona con i modelli di OmniRoute (verificato con almeno una sessione che li usa).

---

## 10. Cose da NON fare

- Non modificare la configurazione dei provider di OmniRoute in `opencode.json` né le variabili d'ambiente di opencode.
- Non sovrascrivere `opencode.json` o altri plugin esistenti: backup e merge.
- Non esporre il server fuori da `127.0.0.1`.
- Non inviare dati a servizi esterni, né telemetria.
- Non installare pacchetti di sistema (`apt`) senza dirmelo prima e darmi il comando.
- Non usare Electron/Node per daemon e dashboard se Python basta (il plugin JS è l'unica eccezione).
- Non dirmi "fatto" senza aver eseguito i test della sezione 9.

---

## 11. Quando fermarti e chiedermi

- Alla fine della **Fase 0** (obbligatorio).
- Se una scelta tecnica cambia in modo importante il comportamento descritto qui.
- Se qualcosa di quanto richiesto non è realizzabile con i plugin/eventi della mia versione di opencode (spiegami l'alternativa più vicina).
