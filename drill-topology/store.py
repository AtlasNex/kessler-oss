#!/usr/bin/env python3
"""drill-shared-store — the estate's shared team-notes store (OWNED, loopback-only).

The drill conductor executes the agents' expressed note writes here (it plays the tool
layer), and the store carries the planted instruction across hops mechanically, so a
conductor step can honestly say "the state the attacker planted is now in the estate's
shared notes" and the next hop reads it back.

API (tiny on purpose):
  GET  /health            -> ok
  POST /note {key,content}-> store a note
  GET  /note/<key>        -> the note (404 when absent)
  GET  /notes             -> JSON list of {key, content, at}
SQLite in /data so the evidence survives a restart; C-2 stdlib only.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

DB = os.environ.get("DRILL_DB", "/data/notes.db")
PORT = int(os.environ.get("DRILL_PORT", "8095"))


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS notes (key TEXT PRIMARY KEY, content TEXT, at TEXT)")
    return conn


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, b"ok\n")
        elif self.path == "/notes":
            with db() as conn:
                rows = conn.execute("SELECT key, content, at FROM notes ORDER BY at").fetchall()
            self._send(200, json.dumps([{"key": k, "content": c, "at": a}
                                        for k, c, a in rows]).encode("utf-8"),
                       "application/json")
        elif self.path.startswith("/note/"):
            key = unquote(self.path[len("/note/"):])
            with db() as conn:
                row = conn.execute("SELECT content, at FROM notes WHERE key=?", (key,)).fetchone()
            if row is None:
                self._send(404, b"no such note\n")
            else:
                self._send(200, json.dumps({"key": key, "content": row[0], "at": row[1]})
                           .encode("utf-8"), "application/json")
        else:
            self._send(404, b"not found\n")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/note":
            self._send(404, b"not found\n")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8", "replace") or "{}")
            key, content = data["key"], data["content"]
            with db() as conn:
                conn.execute("INSERT INTO notes (key, content, at) VALUES (?, ?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET content=excluded.content, "
                             "at=excluded.at",
                             (key, content, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            self._send(200, b'{"stored": true}\n', "application/json")
        except Exception as exc:  # noqa: BLE001
            self._send(400, f"bad note: {exc}\n".encode("utf-8"))

    def log_message(self, fmt, *args):  # quiet
        return


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    print(f"[drill-shared-store] listening on :{PORT} (db: {DB})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
