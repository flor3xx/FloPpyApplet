Stato: completato
Aggiornato: 2026-10-06

# Componenti

`daemon/server.py` espone `/state` per lo stato iniziale, `/events` come SSE e `/event` per ricevere eventi JSON dal plugin su `127.0.0.1:47321`.
`daemon/state.py` assegna i numeri alle istanze, collega le sessioni figlie tramite `parentID`, aggrega token e calcola lo stato peggiore.
`plugin/agent-plugin.js` usa gli hook legacy di opencode 1.18.x, invia gli eventi con fetch breve e usa uno spool locale in caso di daemon non disponibile.
L'applet usa le API legacy di Cinnamon (`Applet.Applet`, `PopupMenu`) e aggiorna il popup tramite polling HTTP.
