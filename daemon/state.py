"""Thread-safe in-memory state model for the local agent daemon."""

import os
import queue
import subprocess
import threading
import time
from collections import defaultdict


STATUS_ORDER = {"normal": 0, "confirm": 1, "error": 2}


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
        self._seen_messages = defaultdict(set)
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
        session_id = _first(event, "sessionID", "sessionId", "session_id",
                            "session", "id")
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
            if parent is not None:
                session["parentID"] = str(parent)
                session["master"] = False
            session["master"] = bool(_first(event, "master", default=session["master"]))
            status = _first(event, "status", default=None)
            if status is None:
                kind = str(_first(event, "kind", "type", default=""))
                if "permission" in kind or "question" in kind:
                    status = "confirm"
                elif "error" in kind or "failed" in kind:
                    status = "error"
                elif "idle" in kind or "completed" in kind:
                    status = "normal"
            if status in STATUS_ORDER:
                session["status"] = status
            activity = _first(event, "activity", "message", "task")
            if activity is None and _first(event, "tool", default=None) is not None:
                activity = "Esegue: " + str(event["tool"])
            if activity is not None:
                session["activity"] = str(activity)
            todo = _first(event, "todo", "todos")
            if todo is not None:
                session["todo"] = list(todo) if isinstance(todo, (list, tuple)) else [todo]

            message_id = _first(event, "messageID", "messageId", "message_id")
            token_data = _first(event, "tokens", "tokenUsage", "usage", default=event)
            if message_id is None:
                message_id = _first(event, "id", default=None)
            if message_id is None or message_id not in self._seen_messages[session_id]:
                if message_id is not None:
                    self._seen_messages[session_id].add(str(message_id))
                self._add_tokens(session["tokens"], token_data)

            old_status = session.get("_last_status")
            session["_last_status"] = session["status"]
            session["lastEvent"] = self.clock()
            if not first_event and old_status != session["status"]:
                key = (session_id, old_status, session["status"])
                if key not in self._notified:
                    self._notified.add(key)
                    self.notifier("Agent " + session["status"],
                                  session.get("activity") or session_id)
            self._rebuild_links()
            snapshot = self.snapshot()
            self._broadcast(snapshot)
            return snapshot

    @staticmethod
    def _add_tokens(target, data):
        if not isinstance(data, dict):
            return
        input_count = _first(data, "input", "inputTokens", "prompt_tokens", default=0)
        output_count = _first(data, "output", "outputTokens", "completion_tokens", default=0)
        reasoning_count = _first(data, "reasoning", "reasoningTokens", default=0)
        cache_read = _first(data, "cacheRead", "cache_read", "cacheReadTokens", default=0)
        cache_write = _first(data, "cacheWrite", "cache_write", "cacheWriteTokens", default=0)
        total = _first(data, "total", "totalTokens", "total_tokens", default=None)
        try:
            target["input"] += int(input_count or 0)
            target["output"] += int(output_count or 0)
            target["reasoning"] = target.get("reasoning", 0) + int(reasoning_count or 0)
            target["cacheRead"] = target.get("cacheRead", 0) + int(cache_read or 0)
            target["cacheWrite"] = target.get("cacheWrite", 0) + int(cache_write or 0)
            target["total"] += int(total if total is not None else (input_count or 0) + (output_count or 0))
        except (TypeError, ValueError):
            return

    def _rebuild_links(self):
        for session in self._sessions.values():
            session["children"] = []
        for session in self._sessions.values():
            parent = self._sessions.get(session["parentID"])
            if parent is not None:
                parent["children"].append(session["sessionID"])

    def cleanup_stale(self):
        with self._lock:
            removed = [sid for sid, session in self._sessions.items()
                       if session["pid"] is not None and not self.pid_checker(session["pid"])]
            for sid in removed:
                del self._sessions[sid]
                self._seen_messages.pop(sid, None)
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
