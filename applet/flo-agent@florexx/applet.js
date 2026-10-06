const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const Soup = imports.gi.Soup;
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const Mainloop = imports.mainloop;

const STATE_URL = "http://127.0.0.1:47321/state";
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

var AgentApplet = class AgentApplet extends Applet.TextIconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this._metadata = metadata;
        this._state = { sessions: [] };
        this._selected = 0;
        this._session = Soup.Session.new();
        this._session.timeout = 2;
        // Cinnamon 6.6 does not expose set_applet_icon_path; the custom SVG
        // is used by the dashboard cards while the panel uses a theme icon.
        this.set_applet_icon_name("applications-system-symbolic");
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
        this._session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (session, result) => {
            try {
                let response = session.send_and_read_finish(result);
                let body = ByteArray.toString(response.get_data());
                this._state = JSON.parse(body || "{}");
                this._render();
            } catch (error) {
                this._state = { sessions: [] };
                this._render();
            }
            this._pollId = Mainloop.timeout_add(POLL_MS, () => { this._poll(); return false; });
        });
    }

    _sessions() {
        let sessions = value(this._state, ["sessions", "instances"], []);
        if (!Array.isArray(sessions) && sessions && typeof sessions === "object") sessions = Object.keys(sessions).map((key) => sessions[key]);
        return sessions || [];
    }

    _agents(session) {
        let agents = value(session, ["agents", "children"], []);
        if (!Array.isArray(agents)) agents = [];
        let master = value(session, ["master", "agent"], null);
        if (master) return [master].concat(agents);
        return agents;
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
        if (!sessions.length) {
            content.add_child(this._label("Nessuna sessione di opencode aperta", "flo-empty"));
            return;
        }
        let session = sessions[this._selected];
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
            let info = statusInfo((this._agents(item)[0]) || item);
            let button = new St.Button({ label: String(index + 1), style_class: "flo-session-button " + info[0], reactive: true, can_focus: true });
            button.set_tooltip_text(String(value(item, ["project", "cwd", "directory", "name"], "Sessione opencode")));
            button.connect("clicked", () => { this._selected = index; this._render(); });
            sessionBar.add_child(button);
        });
    }

    _agentCard(agent, master) {
        let info = statusInfo(agent);
        let card = new St.BoxLayout({ style_class: "flo-agent-card " + (master ? "flo-master " : "flo-child ") + info[0] });
        let icon = new St.Icon({ gicon: Gio.icon_new_for_string(this._metadata.path + "/avatar.svg"), icon_size: master ? 72 : 42, style_class: "flo-avatar " + info[0] });
        let details = new St.BoxLayout({ vertical: true, style_class: "flo-agent-details" });
        let name = value(agent, ["name", "type", "title"], master ? "Agente master" : "Sotto agente");
        let task = value(agent, ["activity", "task", "description", "doing", "message"], "In attesa di un tuo messaggio");
        details.add_child(this._label(String(name), master ? "flo-agent-name master" : "flo-agent-name"));
        details.add_child(this._label(shorten(task, 80), "flo-agent-task"));
        details.add_child(this._label(info[1], "flo-agent-status"));
        card.add_child(icon);
        card.add_child(details);
        card.set_tooltip_text(String(task));
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
