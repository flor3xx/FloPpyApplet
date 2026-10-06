// Plugin legacy per opencode 1.18.x. L'osservabilità non deve mai influenzare la TUI.
import { appendFile, mkdir, readFile, chmod } from "node:fs/promises"
import { dirname } from "node:path"

const ENDPOINT = "http://127.0.0.1:47321/event"
const DATA_HOME = process.env.XDG_DATA_HOME || `${process.env.HOME || "."}/.local/share`
const SPOOL = `${DATA_HOME}/opencode-agent-dashboard/events.jsonl`
const TOKEN_FILE = `${DATA_HOME}/opencode-agent-dashboard/daemon.token`
const TIMEOUT_MS = 350

const safe = (value) => {
  try {
    return JSON.parse(JSON.stringify(value ?? null))
  } catch (_) {
    return String(value ?? "")
  }
}

const contextOf = (context) => {
  try {
    return {
      pid: process.pid,
      directory: context?.project?.directory || context?.directory || process.cwd(),
      timestamp: new Date().toISOString(),
    }
  } catch (_) {
    return { pid: process.pid, directory: process.cwd(), timestamp: new Date().toISOString() }
  }
}

const spool = (payload) => {
  Promise.resolve().then(async () => {
    try {
      await mkdir(dirname(SPOOL), { recursive: true })
      await chmod(dirname(SPOOL), 0o700)
      try { await chmod(SPOOL, 0o600) } catch (_) {}
      await appendFile(SPOOL, `${JSON.stringify(payload)}\n`, { encoding: "utf8", mode: 0o600 })
    } catch (_) {
      // Il monitoraggio è opzionale: nessun errore deve arrivare a opencode.
    }
  }).catch(() => {})
}

const send = (payload) => {
  Promise.resolve().then(async () => {
    let timer
    try {
      const controller = new AbortController()
      timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-flo-agent-token": (await readFile(TOKEN_FILE, "utf8")).trim(),
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      if (!response.ok) spool(payload)
    } catch (_) {
      spool(payload)
    } finally {
      if (timer) clearTimeout(timer)
    }
  }).catch(() => spool(payload))
}

const report = (context, kind, data, extra = {}) => {
  try {
    send({ ...contextOf(context), kind, data: safe(data), ...safe(extra) })
  } catch (_) {
    // Difesa finale contro payload non serializzabili o contesti incompleti.
  }
}

export const AgentPlugin = async (context = {}) => {
  try {
    const hook = (kind, value, extra) => {
      report(context, kind, value, extra)
      return undefined
    }

    return {
      event: async (input = {}) => hook("event", input.event ?? input),
      "tool.execute.before": async (input = {}, output = {}) =>
        hook("tool.execute.before", { input, output }),
      "tool.execute.after": async (input = {}, output = {}) =>
        hook("tool.execute.after", { input, output }),
      "todo.updated": async (input = {}) => hook("todo.updated", input),
      "permission.ask": async (input = {}) => hook("permission.ask", input),
      "permission.asked": async (input = {}) => hook("permission.asked", input),
      "permission.replied": async (input = {}) => hook("permission.replied", input),
      "permission.updated": async (input = {}) => hook("permission.updated", input),
    }
  } catch (_) {
    return {}
  }
}
