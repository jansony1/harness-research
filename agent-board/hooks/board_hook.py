#!/usr/bin/env python3
"""
Agent Board Hook — PostToolUse/PostToolBatch/Stop hook that auto-reports
agent status to the board.

Attaches to Claude Code hooks to automatically track:
- Current status (working/idle)
- What file is being worked on
- Test results
- Failure accumulation
- Session completion

Agent name defaults to "Claude" but can be set via AGENT_BOARD_NAME env var.
"""

import json
import os
import sys
import time
from pathlib import Path

BOARD_STATE = Path(os.environ.get("AGENT_BOARD_STATE", Path(__file__).parent.parent / "state.json"))
AGENT_NAME = os.environ.get("AGENT_BOARD_NAME", "Claude")


def load_state() -> dict:
    try:
        return json.loads(BOARD_STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"agents": [], "tasks": [], "messages": []}


def save_state(state: dict):
    BOARD_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def update_agent(state: dict, updates: dict):
    for a in state["agents"]:
        if a["name"] == AGENT_NAME:
            a.update(updates)
            return
    state["agents"].append({"name": AGENT_NAME, "status": "idle", "current_task": None, "progress": 0, **updates})


def add_log(state: dict, text: str, msg_type: str = ""):
    state["messages"].append({
        "time": time.strftime("%H:%M"),
        "agent": AGENT_NAME,
        "text": text,
        "type": msg_type,
    })
    state["messages"] = state["messages"][-50:]


def handle_post_tool_use(input_data: dict):
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    state = load_state()

    # Determine what agent is doing
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        exit_code = tool_response.get("exitCode", 0)
        stdout = tool_response.get("stdout", "")

        # Detect test runs
        if any(k in command for k in ["test", "pytest", "jest", "vitest"]):
            if exit_code == 0:
                add_log(state, f"Tests passed: {command[:40]}", "success")
            else:
                add_log(state, f"Tests failed: {command[:40]}", "error")

        # Detect git push
        if "git push" in command:
            if exit_code == 0:
                add_log(state, "Pushed to remote", "success")

        # Update task description
        task_desc = command[:50] if len(command) > 50 else command
        update_agent(state, {"status": "working", "current_task": task_desc})

    elif tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        filename = Path(file_path).name if file_path else "unknown"
        update_agent(state, {"status": "working", "current_task": f"Editing {filename}"})

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        filename = Path(file_path).name if file_path else "unknown"
        update_agent(state, {"status": "working", "current_task": f"Reading {filename}"})

    save_state(state)


def handle_post_tool_batch(input_data: dict):
    tool_calls = input_data.get("tool_calls", [])
    state = load_state()

    # Count operations in this batch
    n = len(tool_calls)
    failures = sum(1 for c in tool_calls if c.get("tool_response", {}).get("exitCode", 0) != 0)

    if failures > 0:
        update_agent(state, {"status": "working", "current_task": f"Batch done ({failures}/{n} failed)"})
    else:
        update_agent(state, {"status": "working"})

    save_state(state)


def handle_stop(input_data: dict):
    state = load_state()
    update_agent(state, {"status": "idle", "current_task": None, "progress": 0})
    add_log(state, "Session ended", "")
    save_state(state)


def main():
    input_data = json.load(sys.stdin)
    hook_event = input_data.get("hook_event_name", "")

    if hook_event == "PostToolUse":
        handle_post_tool_use(input_data)
    elif hook_event == "PostToolBatch":
        handle_post_tool_batch(input_data)
    elif hook_event == "Stop":
        handle_stop(input_data)

    # Always pass through — this hook only observes
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
