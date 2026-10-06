"""Loopback-only HTTP and SSE server for the agent daemon."""

import argparse
import json
import queue
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .state import StateStore
except ImportError:
    from state import StateStore


class AgentServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address=("127.0.0.1", 8765), state=None):
        self.state = state or StateStore()
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server_version = "agent-daemon/1.0"

    def _json(self, status, data):
        body = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/event":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            event = json.loads(self.rfile.read(length))
            self.server.state.apply_event(event)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(202, {"ok": True})

    def do_GET(self):
        if self.path == "/state":
            self._json(200, self.server.state.snapshot())
            return
        if self.path != "/events":
            self._json(404, {"error": "not found"})
            return
        subscriber = self.server.state.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(("data: " + json.dumps(self.server.state.snapshot()) + "\n\n").encode())
            self.wfile.flush()
            while True:
                try:
                    snapshot = subscriber.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(("data: " + json.dumps(snapshot) + "\n\n").encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError, socket.timeout):
            pass
        finally:
            self.server.state.unsubscribe(subscriber)

    def log_message(self, *_args):
        pass


def serve_forever(host="127.0.0.1", port=8765, state=None):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("daemon accepts loopback addresses only")
    store = state or StateStore()
    spool = Path.home() / ".local/share/opencode-agent-dashboard/events.jsonl"
    if spool.is_file():
        try:
            for line in spool.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    store.apply_event(json.loads(line))
            spool.unlink()
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    server = AgentServer((host, port), store)
    stopping = threading.Event()

    def cleanup_loop():
        while not stopping.wait(5):
            if server.state.cleanup_stale():
                server.state._broadcast(server.state.snapshot())

    threading.Thread(target=cleanup_loop, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        stopping.set()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daemon locale FloPpy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47321)
    args = parser.parse_args()
    serve_forever(args.host, args.port)
