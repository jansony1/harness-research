#!/usr/bin/env python3
"""
Compact Guard Collector — PostToolUse hook that accumulates critical
context markers for the Compact Guard to save/restore.

When agent outputs contain markers like:
  DECISION: <text>
  TASK: <text>
  CRITICAL: <text>

These are extracted and stored for recovery after compaction.
Also tracks files being modified (in-progress work).
"""

import json
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".agent-harness" / "state"
MEMORY_FILE = STATE_DIR / "compact_memory.json"

DECISION_PATTERN = re.compile(r"DECISION:\s*(.+)", re.IGNORECASE)
TASK_PATTERN = re.compile(r"TASK:\s*(.+)", re.IGNORECASE)
CRITICAL_PATTERN = re.compile(r"CRITICAL:\s*(.+)", re.IGNORECASE)


def load_memory() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {
        "saved_at": None,
        "session_start": time.time(),
        "critical_context": [],
        "decisions": [],
        "current_task": None,
        "files_in_progress": [],
        "compact_count": 0,
    }


def save_memory(memory: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))


def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    memory = load_memory()

    # Track file modifications
    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        if path and path not in memory["files_in_progress"]:
            memory["files_in_progress"].append(path)
            memory["files_in_progress"] = memory["files_in_progress"][-10:]

    # Scan Bash output for markers
    if tool_name == "Bash":
        stdout = tool_response.get("stdout", "")

        for match in DECISION_PATTERN.finditer(stdout):
            decision = match.group(1).strip()[:200]
            if decision not in memory["decisions"]:
                memory["decisions"].append(decision)
                memory["decisions"] = memory["decisions"][-10:]

        for match in TASK_PATTERN.finditer(stdout):
            memory["current_task"] = match.group(1).strip()[:200]

        for match in CRITICAL_PATTERN.finditer(stdout):
            ctx = match.group(1).strip()[:200]
            if ctx not in memory["critical_context"]:
                memory["critical_context"].append(ctx)
                memory["critical_context"] = memory["critical_context"][-10:]

    save_memory(memory)
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
