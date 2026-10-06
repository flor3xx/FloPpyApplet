# Guida Completa allo Sviluppo di Applet per Cinnamon (LMDE)

Cinnamon, il desktop environment predefinito di Linux Mint e LMDE, permette di estendere le proprie funzionalità tramite gli "Spices", di cui gli **Applet** (i piccoli programmi che risiedono sul pannello) sono una delle categorie principali.

Gli applet di Cinnamon sono scritti in **JavaScript** (utilizzando GJS, il binding JavaScript per GNOME/Cinnamon) e comunicano con le librerie di sistema tramite *GObject Introspection* (GI).

---

## 1. Struttura di Base e Posizione

Tutti gli applet utente vengono installati localmente nella cartella:
`~/.local/share/cinnamon/applets/`

Ogni applet deve avere un identificatore univoco chiamato **UUID** (es. `mio-applet@dominio.it`). La struttura minima di un applet richiede una cartella nominata esattamente come l'UUID e al suo interno due file fondamentali:

```text
~/.local/share/cinnamon/applets/mio-applet@dominio.it/
 ├── metadata.json  # Descrive l'applet a Cinnamon
 └── applet.js      # Contiene la logica JavaScript
```

---

## 2. Il File `metadata.json`

Questo file viene letto dalle impostazioni di Cinnamon per mostrare l'applet nella lista di quelli disponibili.

**Esempio di `metadata.json`:**
```json
{
    "uuid": "mio-applet@dominio.it",
    "name": "Il Mio Primo Applet",
    "description": "Un semplice applet di test per LMDE.",
    "icon": "face-smile-symbolic",
    "max-instance": 1
}
```

*   **`uuid`**: Deve coincidere *esattamente* con il nome della cartella. Usa la convenzione `nome@autore`.
*   **`max-instance`**: Definisce quante volte l'applet può essere aggiunto ai pannelli (`-1` per illimitato).
*   **`icon`**: Il nome di un'icona di sistema o il percorso di un'icona inclusa nella cartella.

---

## 3. Il File `applet.js`

Questo file contiene la logica vera e propria. Inizia sempre con l'importazione delle librerie necessarie (come l'API base degli Applet).

**Esempio di base (`applet.js`):**

```javascript
const Applet = imports.ui.applet;
const Util = imports.misc.util; // Utile per eseguire comandi da terminale

// Definiamo la classe dell'applet ereditando da TextIconApplet
class MioApplet extends Applet.TextIconApplet {
    
    constructor(orientation, panel_height, instance_id) {
        // Inizializza la classe genitore
        super(orientation, panel_height, instance_id);
        
        // Imposta un'icona e un testo
        this.set_applet_icon_name("face-smile-symbolic");
        this.set_applet_label(" Ciao LMDE!");
        this.set_applet_tooltip("Clicca qui per una notifica");
    }

    // Metodo integrato nell'API, richiamato al click sull'applet
    on_applet_clicked(event) {
        // Esegue un comando bash in modo asincrono (es. invia una notifica di sistema)
        let comando = `notify-send "Applet Cinnamon" "Hai cliccato l'applet!"`;
        Util.spawnCommandLineAsync(comando);
    }
}

// Funzione di entry-point richiesta da Cinnamon
function main(metadata, orientation, panel_height, instance_id) {
    return new MioApplet(orientation, panel_height, instance_id);
}
```

### Classi Principali Disponibili
A seconda di cosa vuoi mostrare sul pannello, puoi far ereditare la tua classe da:
*   `Applet.Applet`: Classe base vuota, ottima se vuoi costruire un'interfaccia personalizzata da zero usando `St` (Shell Toolkit).
*   `Applet.IconApplet`: Mostra solo un'icona.
*   `Applet.TextApplet`: Mostra solo del testo.
*   `Applet.TextIconApplet`: Mostra sia un'icona che del testo.

---

## 4. Testare e Riavviare l'Applet

Quando scrivi codice per Cinnamon, le modifiche non appaiono in tempo reale. Dopo aver salvato i file, devi:

1.  Aprire le **Impostazioni degli Applet** di Cinnamon, cercare il tuo applet e aggiungerlo al pannello.
2.  Ad ogni modifica del file `applet.js`, devi riavviare l'ambiente grafico. In LMDE puoi farlo premendo `Alt + F2`, digitando la lettera `r` (minuscola) e premendo Invio. Il desktop farà un refresh rapido ricaricando il tuo codice.

---

## 5. Debugging (Trovare gli Errori)

La parte più complessa dello sviluppo in Cinnamon è la mancanza di una console nel browser. Per fare debug devi usare il sistema interno:

### Looking Glass (La Console di Cinnamon)
Looking Glass è lo strumento di debug di Cinnamon. 
*   **Come aprirlo**: Usa la scorciatoia da tastiera `Alt + F2`, digita `lg` e premi Invio.
*   **Sezioni**: Nella scheda "Errors" (Errori) vedrai eventuali crash di JavaScript relativi al tuo applet. Nella scheda "Log" puoi vedere l'output dei comandi di stampa.

### Scrivere nei Log
Per capire cosa sta facendo il tuo codice, puoi stampare dei messaggi che finiranno in Looking Glass e nel file `~/.cinnamon/glass.log`:
```javascript
global.log("Questo è un messaggio di debug dal mio applet!");
global.logError("Questo è un errore gestito!");
```

Inoltre, molti errori "critici" finiscono nel file di log di sessione di sistema, che puoi leggere da terminale con:
`tail -f ~/.xsession-errors`

---

## 6. Risorse Utili e Moduli Extra

Nello sviluppo degli applet ti capiterà di dover interagire con il sistema operativo. Puoi importare i moduli `gi` (GObject Introspection):

```javascript
const GLib = imports.gi.GLib; // Per timer, percorsi di file, ecc.
const Gio = imports.gi.Gio;   // Per I/O di sistema
const St = imports.gi.St;     // Shell Toolkit (per creare elementi UI custom)
const Mainloop = imports.mainloop; // Per eseguire funzioni cicliche (es. orologi)
```

**Esempio di Loop Temporale (Aggiornamento ogni 5 secondi):**
```javascript
    _update_loop() {
        this.set_applet_label("Aggiornato alle: " + new Date().toLocaleTimeString());
        
        // Richiama questa stessa funzione tra 5000 millisecondi (5 secondi)
        this._updateLoopID = Mainloop.timeout_add(5000, () => this._update_loop());
    }

    on_applet_removed_from_panel() {
        // Importante: pulire i loop quando l'applet viene rimosso
        if (this._updateLoopID) {
            Mainloop.source_remove(this._updateLoopID);
        }
    }
```

### Dove trovare ispirazione
Dal momento che la documentazione ufficiale è frammentata, il modo migliore per imparare è **studiare il codice altrui**. Vai nella cartella `~/.local/share/cinnamon/applets/` oppure ` /usr/share/cinnamon/applets/` e apri i file sorgente degli applet che usi già per capire come hanno implementato determinate funzioni (menu a tendina, interruttori, slider, ecc.).