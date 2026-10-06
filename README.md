# FloPpy Applet

Applet Cinnamon locale per monitorare le sessioni opencode, gli agenti master e i sotto-agenti.
Il popup mostra repository, attivita', stato, token e notifiche senza modificare i provider OmniRoute.

## Sicurezza

- Il daemon ascolta solo su `127.0.0.1:47321`.
- Le API richiedono un token casuale salvato in `~/.local/share/opencode-agent-dashboard/daemon.token` con permessi `0600`.
- Il body degli eventi e' limitato a 2 MiB.
- Il plugin usa uno spool locale protetto (`0700` per la directory, `0600` per il file) se il daemon non e' disponibile.
- Gli eventi possono contenere prompt, percorsi e output degli strumenti: il file dati deve restare privato.

## Installazione

Dalla directory del progetto:

```bash
mkdir -p ~/.local/share/cinnamon/applets
cp -a applet/flo-agent@florexx ~/.local/share/cinnamon/applets/
./bin/agent install-plugin
./bin/agent start
```

Poi apri **Impostazioni di Cinnamon > Applet** e aggiungi **Flo Agent** al pannello. Dopo gli aggiornamenti, rimuovi e aggiungi nuovamente l'applet per ricaricare il codice.
Il plugin viene caricato solo dalle nuove istanze di opencode: riavvia quelle gia' aperte.

## Uso

```bash
./bin/agent
./bin/agent status
./bin/agent logs
./bin/agent stop
./bin/agent uninstall-plugin
```

`./bin/agent status` controlla il daemon. `./bin/agent logs` mostra il log di avvio.

Per usare il comando globale `agent`:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/bin/agent" ~/.local/bin/agent
```

Se `~/.local/bin` non e' nel `PATH`, aggiungi `export PATH="$HOME/.local/bin:$PATH"` a `~/.bashrc`.

## Architettura

- `daemon/`: Python standard library, API locali autenticate su `127.0.0.1:47321`.
- `plugin/agent-plugin.js`: inoltra eventi senza bloccare opencode e usa uno spool se il daemon e' spento.
- `applet/`: popup Cinnamon con SVG condiviso e colori per stato.
- Dati e log: `~/.local/share/opencode-agent-dashboard/`.

Il pacchetto `notify-send` appartiene a `libnotify-bin`. Se manca, installalo manualmente con `sudo apt install libnotify-bin`.

## Test

```bash
python3 -m unittest
python3 -m py_compile daemon/*.py
git diff --check
```

Il test runtime dell'applet richiede Cinnamon/GJS nella sessione grafica.
