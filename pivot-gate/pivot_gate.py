#!/usr/bin/env python3
"""
Pivot Gate — PostToolUse hook that detects when an agent is pivoting
(changing approach/design) and forces a pause for human review.

Two detection layers:
  1. Automatic: behavioral signals (consecutive failures, reverts, file churn)
  2. Explicit: agent declares pivot via `echo "PIVOT: <reason>"`

State is persisted per-session in ~/.pivot-gate/session.json
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# --- Configuration ---
SCORE_THRESHOLD = 8
SESSION_TIMEOUT_SECONDS = 1800  # 30 min
STATE_DIR = Path.home() / ".pivot-gate"
STATE_FILE = STATE_DIR / "session.json"

# Signal scores
SCORE_CONSECUTIVE_FAILURE = 2  # per failure
SCORE_GIT_REVERT = 5
SCORE_DELETE_RECENT_FILE = 4
SCORE_EDIT_REVERT = 3
SCORE_FILE_CHURN = 2  # same file edited 3+ times
SCORE_TOOL_OVERRUN = 1  # per call over 30

TOOL_CALL_BASELINE = 30

REVERT_COMMANDS = re.compile(
    r"git\s+(checkout|restore|reset|revert)|rm\s+-rf?\s|rmdir"
)
PIVOT_SIGNAL = re.compile(r"PIVOT:\s*(.+)", re.IGNORECASE)


# --- State Management ---

def load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            elapsed = time.time() - state.get("last_activity", 0)
            if elapsed > SESSION_TIMEOUT_SECONDS:
                return new_state()
            return state
        except (json.JSONDecodeError, KeyError):
            return new_state()
    return new_state()


def new_state() -> dict:
    return {
        "started_at": time.time(),
        "last_activity": time.time(),
        "tool_calls": 0,
        "consecutive_failures": 0,
        "score": 0,
        "files_created": [],
        "files_modified": {},
        "paused": False,
        "pause_history": [],
        "signals": [],
    }


def save_state(state: dict):
    state["last_activity"] = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --- Signal Detection ---

def detect_signals(state: dict, tool_name: str, tool_input: dict, tool_response: dict) -> list[tuple[str, int]]:
    signals = []

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        stdout = tool_response.get("stdout", "")
        stderr = tool_response.get("stderr", "")
        exit_code = tool_response.get("exitCode", 0)

        # Layer 2: Explicit pivot declaration
        pivot_match = PIVOT_SIGNAL.search(stdout)
        if pivot_match:
            signals.append((f"EXPLICIT PIVOT: {pivot_match.group(1)}", SCORE_THRESHOLD))
            return signals

        # Consecutive failures — score once threshold reached
        if exit_code != 0:
            state["consecutive_failures"] += 1
            n = state["consecutive_failures"]
            if n >= 2:
                signals.append(
                    (f"consecutive failures: {n}", 3)
                )
        else:
            state["consecutive_failures"] = 0

        # Git revert commands
        if REVERT_COMMANDS.search(command):
            signals.append((f"revert command: {command[:80]}", SCORE_GIT_REVERT))

        # Deleting recently created files
        rm_match = re.findall(r"rm\s+(?:-rf?\s+)?([^\s;|&]+)", command)
        for path in rm_match:
            if path in state["files_created"]:
                signals.append((f"deleted recently created: {path}", SCORE_DELETE_RECENT_FILE))

    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        if path and path not in state["files_created"]:
            state["files_created"].append(path)

    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        if path:
            count = state["files_modified"].get(path, 0) + 1
            state["files_modified"][path] = count
            if count >= 3:
                signals.append((f"file churn ({count}x): {path}", SCORE_FILE_CHURN))

    # Tool call overrun
    state["tool_calls"] += 1
    if state["tool_calls"] > TOOL_CALL_BASELINE:
        signals.append((f"tool calls: {state['tool_calls']}/{TOOL_CALL_BASELINE}", SCORE_TOOL_OVERRUN))

    return signals


# --- Main Hook Logic ---

def make_pause_output(state: dict, trigger_signals: list[tuple[str, int]]) -> dict:
    reasons = "\n".join(f"  - {sig} (+{score})" for sig, score in trigger_signals)
    recent = "\n".join(f"  - {s}" for s in state["signals"][-5:])

    message = f"""
╔══════════════════════════════════════════════════════╗
║  PIVOT GATE — Human Review Required                  ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  The agent appears to be changing approach.           ║
║  Score: {state['score']}/{SCORE_THRESHOLD} (threshold reached)             ║
║                                                      ║
║  Trigger signals:                                    ║
{reasons}
║                                                      ║
║  Recent activity:                                    ║
{recent}
║                                                      ║
║  Session stats:                                      ║
║    Tool calls: {state['tool_calls']}                                  ║
║    Consecutive failures: {state['consecutive_failures']}                       ║
║    Files modified: {len(state['files_modified'])}                              ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║  Please review the agent's direction before          ║
║  allowing it to continue.                            ║
╚══════════════════════════════════════════════════════╝
"""

    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": {
                "stdout": message.strip(),
                "stderr": "",
                "interrupted": True,
                "isImage": False,
            },
        }
    }


def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    state = load_state()

    # Detect signals
    signals = detect_signals(state, tool_name, tool_input, tool_response)

    # Accumulate score
    for sig_name, sig_score in signals:
        state["score"] += sig_score
        state["signals"].append(f"[{time.strftime('%H:%M:%S')}] {sig_name}")

    # Check threshold
    if state["score"] >= SCORE_THRESHOLD and not state["paused"]:
        state["paused"] = True
        state["pause_history"].append({
            "time": time.time(),
            "score": state["score"],
            "trigger": [s[0] for s in signals],
        })
        save_state(state)
        json.dump(make_pause_output(state, signals), sys.stdout)
        return

    # Reset pause if human has intervened (score goes back to 0 after resume)
    if state["paused"]:
        state["paused"] = False
        state["score"] = 0
        state["consecutive_failures"] = 0

    save_state(state)
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
