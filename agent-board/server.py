#!/usr/bin/env python3
"""
Agent Board Server — serves the pixel UI and handles state updates.

Usage:
    python3 server.py [port]        # default port 8420

Agents update state via:
    1. HTTP POST /update (from scripts/hooks)
    2. Direct file write to state.json (from CLI agents)

UI polls state.json every 2 seconds.
"""

import json
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
STATE_FILE = Path(__file__).parent / "state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"agents": [], "tasks": [], "messages": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/update":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            state = load_state()

            action = body.get("action")

            if action == "add_task":
                state["tasks"].append(body["task"])

            elif action == "update_task":
                for t in state["tasks"]:
                    if t["title"] == body.get("title"):
                        t.update(body.get("updates", {}))
                        break

            elif action == "add_agent":
                state["agents"].append(body["agent"])

            elif action == "update_agent":
                for a in state["agents"]:
                    if a["name"] == body.get("name"):
                        a.update(body.get("updates", {}))
                        break

            elif action == "log":
                state["messages"].append({
                    "time": time.strftime("%H:%M"),
                    "agent": body.get("agent", "system"),
                    "text": body.get("text", ""),
                    "type": body.get("type", ""),
                })
                state["messages"] = state["messages"][-50:]

            elif action == "clear_log":
                state["messages"] = []

            save_state(state)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logging


def main():
    import os
    os.chdir(Path(__file__).parent)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"⚔️  Agent Board running at http://localhost:{PORT}")
    print(f"   State file: {STATE_FILE}")
    print(f"   Ctrl+C to stop")
    server.serve_forever()


if __name__ == "__main__":
    main()
