const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const Soup = imports.gi.Soup;
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const Mainloop = imports.mainloop;

const STATE_URL = "http://127.0.0.1:47321/state";
const DATA_HOME = GLib.getenv("XDG_DATA_HOME") || (GLib.get_home_dir() + "/.local/share");
const TOKEN_PATH = DATA_HOME + "/opencode-agent-dashboard/daemon.token";
const POLL_MS = 3000;

function value(object, keys, fallback) {
    if (!object) return fallback;
    for (let i = 0; i < keys.length; i++) {
        if (object[keys[i]] !== undefined && object[keys[i]] !== null) return object[keys[i]];
    }
    return fallback;
}

function number(object, keys) {
    let result = Number(value(object, keys, 0));
    return isNaN(result) ? 0 : result;
}

function shorten(text, length) {
    text = String(text || "");
    return text.length > length ? text.substring(0, length - 1) + "…" : text;
}

function formatNumber(amount) {
    if (!amount) return "0";
    if (amount >= 1000000) return (amount / 1000000).toFixed(1).replace(".0", "") + "M";
    if (amount >= 1000) return (amount / 1000).toFixed(1).replace(".0", "") + "k";
    return String(Math.round(amount));
}

function tokenTotals(agent) {
    let tokens = value(agent, ["tokens", "tokenUsage", "usage"], {}) || {};
    return {
        input: number(tokens, ["input", "inputTokens"]),
        output: number(tokens, ["output", "outputTokens"]),
        reasoning: number(tokens, ["reasoning", "reasoningTokens"]),
        cacheRead: number(tokens, ["cacheRead", "cache_read", "cacheReadTokens"]),
        cacheWrite: number(tokens, ["cacheWrite", "cache_write", "cacheWriteTokens"])
    };
}

function addTokens(target, source) {
    target.input += source.input;
    target.output += source.output;
    target.reasoning += source.reasoning;
    target.cacheRead += source.cacheRead;
    target.cacheWrite += source.cacheWrite;
}

function statusInfo(agent) {
    let raw = String(value(agent, ["status", "state"], "working")).toLowerCase();
    if (raw.indexOf("error") >= 0 || raw.indexOf("fail") >= 0 || raw === "problem") return ["problema", "Problema", "#ef4444"];
    if (raw.indexOf("ask") >= 0 || raw.indexOf("permission") >= 0 || raw.indexOf("confirm") >= 0 || raw === "waiting") return ["conferma", "Serve la tua conferma", "#8b5cf6"];
    if (raw === "idle" || raw === "done" || raw === "completed" || raw === "complete" || raw === "finished") return ["completato", "Completato", "#55c7d9"];
    return ["lavoro", "In lavoro", "#55c7d9"];
}

function sessionName(session) {
    let directory = String(value(session, ["directory", "project", "cwd", "name"], "Sessione opencode"));
    let parts = directory.split("/");
    return parts[parts.length - 1] || directory;
}

function daemonToken() {
    try {
        let file = Gio.file_new_for_path(TOKEN_PATH);
        let loaded = file.load_contents(null);
        return ByteArray.toString(loaded[1]).trim();
    } catch (error) {
        return "";
    }
}

function avatarPath(metadata, status) {
    let filename = status === "lavoro" ? "avatar-working.svg" :
        (status === "conferma" || status === "problema" ? "avatar-confirm.svg" : "avatar.svg");
    return metadata.path + "/" + filename;
}

var AgentApplet = class AgentApplet extends Applet.TextIconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this._metadata = metadata;
        this._state = { sessions: [] };
        this._selected = 0;
        this._session = Soup.Session.new();
        this._session.timeout = 2;
        this.set_applet_icon_path(this._metadata.path + "/avatar.svg");
        this.set_applet_label(" Flo Agent");
        this.set_applet_tooltip("Mostra lo stato delle sessioni opencode");
        this._menu = new Applet.AppletPopupMenu(this, orientation);
        this._menu.actor.add_style_class_name("flo-agent-menu");
        this._menuManager = new PopupMenu.PopupMenuManager(this);
        this._menuManager.addMenu(this._menu);
        this._buildMenu();
        this._poll();
    }

    _buildMenu() {
        this._root = new St.BoxLayout({ vertical: true, style_class: "flo-dashboard" });
        this._menu.addActor(this._root);
        this._render();
    }

    _poll() {
        let message = Soup.Message.new("GET", STATE_URL);
        message.request_headers.append("X-Flo-Agent-Token", daemonToken());
        try {
            let body;
            if (typeof this._session.send_and_read === "function") {
                // Soup 3: la chiamata sincrona evita callback non disponibili in alcune build GJS.
                body = ByteArray.toString(this._session.send_and_read(message, null).get_data());
            } else {
                // Soup 2, presente in alcune versioni Cinnamon.
                let response = this._session.send_message(message);
                body = response && response.response_body ? ByteArray.toString(response.response_body.data) : "";
            }
            this._state = JSON.parse(body || "{}");
        } catch (error) {
            this._state = { sessions: [], error: "Daemon non raggiungibile" };
        }
        this._render();
        this._pollId = Mainloop.timeout_add(POLL_MS, () => { this._poll(); return false; });
    }

    _sessions() {
        let sessions = value(this._state, ["sessions", "instances"], []);
        if (!Array.isArray(sessions) && sessions && typeof sessions === "object") sessions = Object.keys(sessions).map((key) => sessions[key]);
        return sessions || [];
    }

    _agents(session) {
        let agents = value(session, ["agents", "children"], []);
        if (!Array.isArray(agents)) agents = [];
        let sessions = this._sessions();
        agents = agents.map((agent) => {
            if (typeof agent !== "string") return agent;
            return sessions.find((item) => String(item.sessionID) === agent) || { sessionID: agent };
        });
        let master = value(session, ["master", "agent"], null);
        if (master) return [master === true ? session : master].concat(agents);
        return agents.length ? agents : [session];
    }

    _worstAgent(session) {
        let agents = this._agents(session);
        let order = { lavoro: 0, completato: 0, conferma: 1, problema: 2 };
        return agents.reduce((worst, agent) => {
            let candidate = statusInfo(agent);
            return order[candidate[0]] > order[worst[0]] ? candidate : worst;
        }, statusInfo(agents[0] || session));
    }

    _label(text, style) {
        return new St.Label({ text: text, style_class: style || "" });
    }

    _clear() {
        this._root.get_children().forEach((child) => this._root.remove_child(child));
    }

    _render() {
        if (!this._root) return;
        this._clear();
        let sessions = this._sessions();
        if (this._selected >= sessions.length) this._selected = Math.max(0, sessions.length - 1);
        let body = new St.BoxLayout({ style_class: "flo-dashboard-body" });
        let content = new St.BoxLayout({ vertical: true, style_class: "flo-dashboard-content" });
        let sessionBar = new St.BoxLayout({ vertical: true, style_class: "flo-session-bar" });
        body.add_child(content);
        body.add_child(sessionBar);
        this._root.add_child(body);
        content.add_child(this._label("Sessioni rilevate: " + sessions.length, "flo-session-count"));
        if (!sessions.length) {
            content.add_child(this._label(value(this._state, ["error"], "Nessuna sessione di opencode aperta"), "flo-empty"));
            return;
        }
        let session = sessions[this._selected];
        content.add_child(this._label("Selezionata: " + sessionName(session), "flo-selected-session"));
        let totals = { input: 0, output: 0, reasoning: 0, cacheRead: 0, cacheWrite: 0 };
        this._agents(session).forEach((agent) => addTokens(totals, tokenTotals(agent)));
        let tokenBar = new St.BoxLayout({ style_class: "flo-token-bar" });
        [["Input", totals.input], ["Output", totals.output], ["Reasoning", totals.reasoning], ["Cache letta", totals.cacheRead], ["Cache scritta", totals.cacheWrite], ["Totale", totals.input + totals.output + totals.reasoning + totals.cacheRead + totals.cacheWrite]].forEach((item) => {
            let cell = new St.BoxLayout({ vertical: true, style_class: "flo-token-cell" });
            cell.add_child(this._label(item[0], "flo-token-name"));
            cell.add_child(this._label(formatNumber(item[1]), "flo-token-value"));
            tokenBar.add_child(cell);
        });
        content.add_child(tokenBar);
        let agents = this._agents(session);
        if (!agents.length) content.add_child(this._label("Nessun agente attivo", "flo-empty"));
        agents.forEach((agent, index) => content.add_child(this._agentCard(agent, index === 0)));
        sessions.forEach((item, index) => {
            let info = this._worstAgent(item);
            let selected = index === this._selected ? " selezionata" : "";
            let button = new St.Button({ label: String(index + 1), style_class: "flo-session-button " + info[0] + selected, reactive: true, can_focus: true });
            button.connect("clicked", () => { this._selected = index; this._render(); });
            sessionBar.add_child(button);
        });
    }

    _agentCard(agent, master) {
        let info = statusInfo(agent);
        let card = new St.BoxLayout({ style_class: "flo-agent-card " + (master ? "flo-master " : "flo-child ") + info[0] });
        let icon = new St.Icon({ gicon: Gio.icon_new_for_string(avatarPath(this._metadata, info[0])), icon_size: master ? 72 : 42, style_class: "flo-avatar " + info[0] });
        let details = new St.BoxLayout({ vertical: true, style_class: "flo-agent-details" });
        let name = value(agent, ["name", "type", "title"], master ? "Agente master" : "Sotto agente");
        let task = value(agent, ["activity", "task", "description", "doing", "message"], "In attesa di un tuo messaggio");
        details.add_child(this._label(String(name), master ? "flo-agent-name master" : "flo-agent-name"));
        details.add_child(this._label(shorten(task, 80), "flo-agent-task"));
        details.add_child(this._label(info[1], "flo-agent-status"));
        card.add_child(icon);
        card.add_child(details);
        return card;
    }

    on_applet_clicked() {
        this._menu.toggle();
    }

    on_applet_removed_from_panel() {
        if (this._pollId) Mainloop.source_remove(this._pollId);
        if (this._session && this._session.abort) this._session.abort();
    }
};

function main(metadata, orientation, panelHeight, instanceId) {
    return new AgentApplet(metadata, orientation, panelHeight, instanceId);
}
