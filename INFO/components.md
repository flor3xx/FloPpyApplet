Stato: completato
Aggiornato: 2026-10-06

# Componenti

`daemon/server.py` espone `/state` per lo stato iniziale, `/events` come SSE e `/event` per ricevere eventi JSON dal plugin su `127.0.0.1:47321`.
`daemon/state.py` assegna i numeri alle istanze, collega le sessioni figlie tramite `parentID`, aggrega token e calcola lo stato peggiore. Notifica solo completamento, errore e richiesta di conferma/permesso, non l'inizio del lavoro.
`plugin/agent-plugin.js` usa gli hook legacy di opencode 1.18.x, invia gli eventi con fetch breve e usa uno spool locale in caso di daemon non disponibile.
L'applet usa le API legacy di Cinnamon (`Applet.Applet`, `PopupMenu`) e aggiorna il popup tramite polling HTTP locale sincrono compatibile con Soup 3 e Soup 2; il pannello usa `avatar.svg`, mostra il conteggio, il nome della repository selezionata e un bordo evidente sul pulsante selezionato. Le card usano asset SVG espressivi distinti per lavoro, conferma/errore e completamento. Se una sessione non ha sotto-agenti, la sessione stessa viene mostrata come master. Il comando `bin/agent` avvia il daemon come modulo Python, così gli import relativi funzionano anche fuori dalla directory del progetto. Il modello appiattisce `data.properties`, gestisce `session.created`, gli stati `busy/idle`, i token annidati in `info.tokens` con cache, ignora gli eventi senza sessione, corregge parent che sono ID messaggio e conserva la directory del progetto negli eventi reali di opencode 1.18.x. Notifica il completamento quando una sessione passa da `working` a `normal`.
