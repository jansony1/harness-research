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

ARCHITECTURE_PATTERN = re.compile(r"ARCHITECTURE:\s*(.+)", re.IGNORECASE)
DECISION_PATTERN = re.compile(r"DECISION:\s*(.+)", re.IGNORECASE)
TASK_PATTERN = re.compile(r"TASK:\s*(.+)", re.IGNORECASE)
TASK_DONE_PATTERN = re.compile(r"TASK_DONE:\s*(.+)", re.IGNORECASE)
CRITICAL_PATTERN = re.compile(r"CRITICAL:\s*(.+)", re.IGNORECASE)
CONTEXT_PATTERN = re.compile(r"CONTEXT:\s*(.+)", re.IGNORECASE)

# Type grading: ARCHITECTURE/CRITICAL never auto-expire, TASK clears on TASK_DONE, CONTEXT is FIFO(5)
MAX_CONTEXT_ITEMS = 5


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
        "architecture": [],      # never auto-expire
        "critical_context": [],  # never auto-expire
        "decisions": [],         # FIFO(10)
        "context": [],           # FIFO(5), first to expire
        "current_task": None,    # cleared on TASK_DONE
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

    # Scan Bash output for typed markers
    if tool_name == "Bash":
        stdout = tool_response.get("stdout", "")

        for match in ARCHITECTURE_PATTERN.finditer(stdout):
            item = match.group(1).strip()[:200]
            if item not in memory.get("architecture", []):
                memory.setdefault("architecture", []).append(item)

        for match in CRITICAL_PATTERN.finditer(stdout):
            item = match.group(1).strip()[:200]
            if item not in memory["critical_context"]:
                memory["critical_context"].append(item)

        for match in DECISION_PATTERN.finditer(stdout):
            item = match.group(1).strip()[:200]
            if item not in memory["decisions"]:
                memory["decisions"].append(item)
                memory["decisions"] = memory["decisions"][-10:]

        for match in TASK_PATTERN.finditer(stdout):
            memory["current_task"] = match.group(1).strip()[:200]

        for match in TASK_DONE_PATTERN.finditer(stdout):
            memory["current_task"] = None

        for match in CONTEXT_PATTERN.finditer(stdout):
            item = match.group(1).strip()[:200]
            memory.setdefault("context", []).append(item)
            memory["context"] = memory["context"][-MAX_CONTEXT_ITEMS:]

    save_memory(memory)
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
