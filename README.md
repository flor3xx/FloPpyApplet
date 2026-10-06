# FloPpy Applet

Applet Cinnamon locale per vedere nel pannello le sessioni di opencode, il master e i sotto-agenti.
Il popup e' in italiano e mostra token, attivita', stato e notifiche. Funziona con i modelli OmniRoute senza modificare i provider.

## Installazione

Dalla directory del progetto:

```bash
mkdir -p ~/.local/share/cinnamon/applets
cp -r applet/flo-agent@florexx ~/.local/share/cinnamon/applets/
./bin/agent install-plugin
```

Poi apri **Impostazioni di Cinnamon > Applet**, aggiungi **Flo Agent** al pannello e riavvia Cinnamon con `Alt+F2`, quindi `r`.
Il plugin viene caricato solo dalle nuove istanze di opencode: riavvia quelle gia' aperte.

## Uso

```bash
./bin/agent
./bin/agent status
./bin/agent logs
./bin/agent stop
./bin/agent uninstall-plugin
```

Per usare il comando globale `agent`:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/bin/agent" ~/.local/bin/agent
```

Se `~/.local/bin` non e' nel `PATH`, aggiungi `export PATH="$HOME/.local/bin:$PATH"` a `~/.bashrc`.

## Architettura

- `daemon/`: Python standard library, server solo su `127.0.0.1:47321`.
- `plugin/agent-plugin.js`: inoltra eventi senza bloccare opencode e usa uno spool se il daemon e' spento.
- `applet/`: popup Cinnamon con SVG condiviso e colori per stato.
- Dati e log: `~/.local/share/opencode-agent-dashboard/`.

Il pacchetto `notify-send` appartiene a `libnotify-bin`. Se manca, installalo manualmente con `sudo apt install libnotify-bin`.

## Test

```bash
python3 -m unittest
python3 -m py_compile daemon/*.py
```

Il test runtime dell'applet richiede Cinnamon/GJS nella sessione grafica.
