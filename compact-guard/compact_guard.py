#!/usr/bin/env python3
"""
Compact Guard — PreCompact + PostCompact hooks to protect critical
context from being lost during compaction.

PreCompact:
  - Saves critical session state (decisions, design choices, progress)
    to a file before compaction happens
  - Can optionally block compaction if critical work is in progress

PostCompact:
  - After compaction, injects saved critical context back
    so the agent doesn't lose track of key decisions
"""

import json
import os
import sys
import time
from pathlib import Path

# --- Configuration ---
STATE_DIR = Path.home() / ".agent-harness" / "state"
MEMORY_FILE = STATE_DIR / "compact_memory.json"
BLOCK_AUTO_COMPACT_IF_RECENT = int(os.environ.get("COMPACT_GUARD_BLOCK_SECONDS", "60"))


def load_memory() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return new_memory()


def new_memory() -> dict:
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


def handle_pre_compact(input_data: dict, memory: dict) -> tuple[dict, int]:
    """Save critical state before compaction. Optionally block."""
    trigger = input_data.get("trigger", "auto")

    # Save snapshot of critical state
    memory["saved_at"] = time.time()
    memory["compact_count"] += 1

    # Block auto-compact if session just started (first 60s)
    # to avoid losing initial context setup
    if trigger == "auto":
        elapsed = time.time() - memory.get("session_start", 0)
        if elapsed < BLOCK_AUTO_COMPACT_IF_RECENT:
            save_memory(memory)
            return {
                "decision": "block",
                "reason": (
                    f"Blocking auto-compact: session only {int(elapsed)}s old. "
                    "Initial context setup may be lost."
                ),
            }, 2

    save_memory(memory)
    return {}, 0


def handle_post_compact(input_data: dict, memory: dict) -> dict:
    """After compaction, inject saved critical context back."""
    compact_summary = input_data.get("compact_summary", "")

    # Build recovery context
    recovery_parts = []

    if memory.get("current_task"):
        recovery_parts.append(f"[TASK IN PROGRESS] {memory['current_task']}")

    if memory.get("files_in_progress"):
        files = ", ".join(memory["files_in_progress"][-5:])
        recovery_parts.append(f"[FILES BEING MODIFIED] {files}")

    if memory.get("decisions"):
        decisions = memory["decisions"][-3:]  # last 3 decisions
        recovery_parts.append("[KEY DECISIONS MADE]")
        for d in decisions:
            recovery_parts.append(f"  - {d}")

    if memory.get("critical_context"):
        recovery_parts.append("[CRITICAL CONTEXT]")
        for ctx in memory["critical_context"][-5:]:
            recovery_parts.append(f"  - {ctx}")

    recovery_parts.append(f"[COMPACT #{memory['compact_count']}] Previous context was compacted.")

    if recovery_parts:
        return {"additionalContext": "\n".join(recovery_parts)}

    return {}


def main():
    input_data = json.load(sys.stdin)
    hook_event = input_data.get("hook_event_name", "")

    memory = load_memory()

    if hook_event == "PreCompact":
        output, exit_code = handle_pre_compact(input_data, memory)
        json.dump(output, sys.stdout)
        sys.exit(exit_code)

    elif hook_event == "PostCompact":
        output = handle_post_compact(input_data, memory)
        save_memory(memory)
        json.dump(output, sys.stdout)

    else:
        json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
