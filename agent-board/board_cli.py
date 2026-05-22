#!/usr/bin/env python3
"""
Agent Board CLI — let coding agents update the board from scripts/hooks.

Usage (direct file mode, no server needed):
    python3 board_cli.py status Claude working "Implementing feature X" 60
    python3 board_cli.py log Claude "Tests passing" success
    python3 board_cli.py task add "New task title" Claude high
    python3 board_cli.py task move "Task title" done
    python3 board_cli.py idle Claude

Usage (HTTP mode, if server.py is running):
    BOARD_URL=http://localhost:8420 python3 board_cli.py log Claude "hello"
"""

import json
import os
import sys
import time
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state.json"
BOARD_URL = os.environ.get("BOARD_URL")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"agents": [], "tasks": [], "messages": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def http_post(action: str, data: dict):
    import urllib.request
    payload = json.dumps({"action": action, **data}).encode()
    req = urllib.request.Request(
        f"{BOARD_URL}/update",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req)


def cmd_status(args):
    """Update agent status: status <name> <working|idle|blocked> [task] [progress%]"""
    name = args[0]
    status = args[1] if len(args) > 1 else "idle"
    task = args[2] if len(args) > 2 else None
    progress = int(args[3]) if len(args) > 3 else (50 if status == "working" else 0)

    if BOARD_URL:
        http_post("update_agent", {"name": name, "updates": {"status": status, "current_task": task, "progress": progress}})
    else:
        state = load_state()
        found = False
        for a in state["agents"]:
            if a["name"] == name:
                a["status"] = status
                a["current_task"] = task
                a["progress"] = progress
                found = True
                break
        if not found:
            state["agents"].append({"name": name, "status": status, "current_task": task, "progress": progress})
        save_state(state)


def cmd_idle(args):
    """Set agent to idle: idle <name>"""
    cmd_status([args[0], "idle", "", "0"])


def cmd_log(args):
    """Add log message: log <agent> <text> [type: success|error|""]"""
    agent = args[0]
    text = args[1] if len(args) > 1 else ""
    msg_type = args[2] if len(args) > 2 else ""

    if BOARD_URL:
        http_post("log", {"agent": agent, "text": text, "type": msg_type})
    else:
        state = load_state()
        state["messages"].append({"time": time.strftime("%H:%M"), "agent": agent, "text": text, "type": msg_type})
        state["messages"] = state["messages"][-50:]
        save_state(state)


def cmd_task(args):
    """Manage tasks: task add <title> [assignee] [priority] | task move <title> <status>"""
    sub = args[0]
    if sub == "add":
        title = args[1]
        assignee = args[2] if len(args) > 2 else ""
        priority = args[3] if len(args) > 3 else "mid"
        task = {"title": title, "assignee": assignee, "priority": priority, "status": "planning"}
        if BOARD_URL:
            http_post("add_task", {"task": task})
        else:
            state = load_state()
            state["tasks"].append(task)
            save_state(state)
    elif sub == "move":
        title = args[1]
        new_status = args[2] if len(args) > 2 else "done"
        if BOARD_URL:
            http_post("update_task", {"title": title, "updates": {"status": new_status}})
        else:
            state = load_state()
            for t in state["tasks"]:
                if t["title"] == title:
                    t["status"] = new_status
                    break
            save_state(state)


COMMANDS = {
    "status": cmd_status,
    "idle": cmd_idle,
    "log": cmd_log,
    "task": cmd_task,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: board_cli.py <status|idle|log|task> [args...]")
        print("  status <name> <working|idle|blocked> [task] [progress%]")
        print("  idle <name>")
        print("  log <agent> <text> [success|error]")
        print("  task add <title> [assignee] [priority]")
        print("  task move <title> <planning|progress|done>")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])
