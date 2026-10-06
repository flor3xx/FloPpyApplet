"""Thread-safe in-memory state model for the local agent daemon."""

import os
import queue
import subprocess
import threading
import time
from collections import defaultdict


STATUS_ORDER = {"working": 0, "normal": 0, "confirm": 1, "error": 2}


def _first(event, *names, default=None):
    for name in names:
        if name in event and event[name] is not None:
            return event[name]
    return default


class StateStore:
    """Collect events and expose a JSON-serialisable snapshot."""

    def __init__(self, clock=time.time, pid_checker=None, notifier=None):
        self.clock = clock
        self.pid_checker = pid_checker or self._pid_exists
        self.notifier = notifier or self._notify
        self._sessions = {}
        self._message_tokens = defaultdict(dict)
        self._notified = set()
        self._subscribers = []
        self._lock = threading.RLock()

    @staticmethod
    def _pid_exists(pid):
        try:
            os.kill(int(pid), 0)
        except (OSError, ValueError, TypeError):
            return False
        return True

    @staticmethod
    def _notify(title, message):
        try:
            urgency = "critical" if "confirm" in title or "error" in title else "normal"
            subprocess.run(["notify-send", "-u", urgency, title, message], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def subscribe(self):
        subscriber = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, queue):
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _broadcast(self, snapshot):
        for subscriber in self._subscribers:
            subscriber.put(snapshot)

    def apply_event(self, event):
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        if isinstance(event.get("data"), dict):
            raw = dict(event["data"])
            for key in ("pid", "directory", "timestamp"):
                if key in event and key not in raw:
                    raw[key] = event[key]
            raw.setdefault("kind", event.get("kind"))
            event = raw
        # Gli eventi di opencode 1.18.x espongono i dati utili in properties.
        properties = event.get("properties")
        if isinstance(properties, dict):
            event = {**properties, **event}
        session_info = properties.get("info") if isinstance(properties, dict) else None
        session_id = _first(event, "sessionID", "sessionId", "session_id", "session")
        if session_id is None and isinstance(session_info, dict):
            session_id = _first(session_info, "sessionID", "sessionId", "session_id", "id")
        if session_id is None and isinstance(properties, dict):
            for nested_name in ("part", "message", "permission"):
                nested = properties.get(nested_name)
                if isinstance(nested, dict):
                    session_id = _first(nested, "sessionID", "sessionId", "session_id")
                    if session_id is not None:
                        break
        if session_id is None and isinstance(event.get("input"), dict):
            session_id = _first(event["input"], "sessionID", "sessionId", "session_id")
        if session_id is None:
            raise ValueError("event has no session id")
        session_id = str(session_id)
        with self._lock:
            session = self._sessions.get(session_id)
            first_event = session is None
            if session is None:
                session = {
                    "sessionID": session_id, "pid": None, "instanceNumber": 1,
                    "parentID": None, "master": True, "children": [],
                    "directory": None,
                    "status": "normal", "activity": None, "todo": [],
                    "tokens": {"input": 0, "output": 0, "reasoning": 0,
                                "cacheRead": 0, "cacheWrite": 0, "total": 0},
                    "lastEvent": self.clock(),
                }
                self._sessions[session_id] = session

            pid = _first(event, "pid", "PID")
            if pid is not None:
                try:
                    pid = int(pid)
                except (TypeError, ValueError):
                    pid = None
                if pid is not None and pid != session["pid"]:
                    session["pid"] = pid
                    siblings = [s for s in self._sessions.values()
                                if s is not session and s["pid"] == pid]
                    session["instanceNumber"] = 1 + len(siblings)

            parent = _first(event, "parentID", "parentId", "parent_id")
            if parent is None and isinstance(session_info, dict):
                parent = _first(session_info, "parentID", "parentId", "parent_id")
            if parent is not None:
                session["parentID"] = str(parent)
                session["master"] = False
            session["master"] = bool(_first(event, "master", default=session["master"]))
            directory = _first(event, "directory", "cwd", "worktree", "projectDirectory")
            if directory is not None:
                session["directory"] = str(directory)
            status = _first(event, "status", default=None)
            if isinstance(status, dict):
                status = _first(status, "type", "status")
            if status is None:
                kind = str(_first(event, "kind", "type", default=""))
                if "permission" in kind or "question" in kind:
                    status = "confirm"
                elif "error" in kind or "failed" in kind:
                    status = "error"
                elif "idle" in kind or "completed" in kind:
                    status = "normal"
            if status in ("busy", "working", "running"):
                status = "working"
            elif status in ("idle", "done", "completed", "complete", "finished"):
                status = "normal"
            elif status in ("retry", "error", "failed"):
                status = "error"
            kind = str(_first(event, "kind", "type", default=""))
            if any(marker in kind for marker in ("permission.replied", "question.replied", "question.rejected")):
                status = "normal"
            output = event.get("output")
            if isinstance(output, dict) and (output.get("error") or output.get("status") == "error"):
                status = "error"
            if status in STATUS_ORDER:
                session["status"] = status
            activity = _first(event, "activity", "message", "task")
            input_data = event.get("input") if isinstance(event.get("input"), dict) else {}
            args = input_data.get("args") if isinstance(input_data.get("args"), dict) else {}
            if args.get("description") is not None:
                activity = str(args["description"])
            if activity is None and isinstance(output, dict):
                activity = _first(output, "title", "message")
            tool = _first(event, "tool", default=None)
            if tool is None and isinstance(event.get("input"), dict):
                tool = _first(event["input"], "tool", default=None)
            if activity is None and tool is not None:
                activity = "Esegue: " + str(tool)
            if activity is not None:
                session["activity"] = str(activity)
            todo = _first(event, "todo", "todos")
            if todo is not None:
                session["todo"] = list(todo) if isinstance(todo, (list, tuple)) else [todo]

            message_id = _first(event, "messageID", "messageId", "message_id")
            token_data = _first(event, "tokens", "tokenUsage", "usage", default=None)
            if token_data is None:
                for nested_name in ("info", "message", "part", "output"):
                    nested = event.get(nested_name)
                    if isinstance(nested, dict):
                        token_data = _first(nested, "tokens", "tokenUsage", "usage", default=None)
                        if token_data is not None:
                            break
            if message_id is None:
                message_id = _first(event, "id", default=None)
            if message_id is not None and token_data is not None:
                message_id = str(message_id)
                current = self._token_counts(token_data)
                previous = self._message_tokens[session_id].get(message_id)
                if previous is not None:
                    self._add_token_counts(session["tokens"], previous, -1)
                self._message_tokens[session_id][message_id] = current
                self._add_token_counts(session["tokens"], current, 1)
            elif message_id is None and token_data is not None:
                self._add_token_counts(session["tokens"], self._token_counts(token_data), 1)

            old_status = session.get("_last_status")
            session["_last_status"] = session["status"]
            session["lastEvent"] = self.clock()
            if not first_event and old_status != session["status"]:
                key = (session_id, old_status, session["status"])
                title = None
                if session["status"] == "normal" and old_status == "working":
                    title = "Agent completato"
                elif session["status"] == "error":
                    title = "Agent error"
                elif session["status"] == "confirm":
                    title = "Agent richiede conferma"
                if title is not None and key not in self._notified:
                    self._notified.add(key)
                    self.notifier(title,
                                  session.get("activity") or session_id)
            self._rebuild_links()
            snapshot = self.snapshot()
            self._broadcast(snapshot)
            return snapshot

    @staticmethod
    def _token_counts(data):
        if not isinstance(data, dict):
            return None
        cache = data.get("cache") if isinstance(data.get("cache"), dict) else {}
        values = {
            "input": _first(data, "input", "inputTokens", "prompt_tokens", default=0),
            "output": _first(data, "output", "outputTokens", "completion_tokens", default=0),
            "reasoning": _first(data, "reasoning", "reasoningTokens", default=0),
            "cacheRead": _first(data, "cacheRead", "cache_read", "cacheReadTokens", default=cache.get("read", 0)),
            "cacheWrite": _first(data, "cacheWrite", "cache_write", "cacheWriteTokens", default=cache.get("write", 0)),
        }
        total = _first(data, "total", "totalTokens", "total_tokens", default=None)
        try:
            values = {key: int(value or 0) for key, value in values.items()}
            values["total"] = int(total if total is not None else values["input"] + values["output"])
            return values
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _add_token_counts(target, values, sign):
        if values:
            for key, value in values.items():
                target[key] += sign * value

    @classmethod
    def _add_tokens(cls, target, data):
        cls._add_token_counts(target, cls._token_counts(data), 1)

    def _rebuild_links(self):
        for session in self._sessions.values():
            session["children"] = []
        for session in self._sessions.values():
            parent = self._sessions.get(session["parentID"])
            if parent is not None:
                session["master"] = False
                parent["children"].append(session["sessionID"])
            elif session["parentID"] is not None and (str(session["parentID"]).startswith("msg_") or session["parentID"] == "message"):
                # Alcuni eventi usano come parent l'ID del messaggio, non della sessione.
                session["parentID"] = None
                session["master"] = True

    def cleanup_stale(self):
        with self._lock:
            removed = [sid for sid, session in self._sessions.items()
                       if session["pid"] is not None and not self.pid_checker(session["pid"])]
            for sid in removed:
                del self._sessions[sid]
                self._message_tokens.pop(sid, None)
            self._rebuild_links()
            return removed

    def snapshot(self):
        with self._lock:
            sessions = []
            for session in self._sessions.values():
                item = dict(session)
                item.pop("_last_status", None)
                item["tokens"] = dict(session["tokens"])
                item["children"] = list(session["children"])
                item["todo"] = list(session["todo"])
                sessions.append(item)
            return {"sessions": sessions, "timestamp": self.clock()}
