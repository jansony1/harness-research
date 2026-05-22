#!/usr/bin/env python3
"""
Loop Breaker — PostToolBatch hook that detects when an agent is stuck
in a loop OR pivoting without approval.

Detection signals:
1. Same command executed N+ times (exact or fuzzy match)
2. Same file edited N+ times in a batch window
3. Alternating pattern (edit → test fail → edit → test fail → ...)
4. Total batch count exceeds session budget
5. Revert/reset operations (git checkout, git reset, rm of recent files)
6. Explicit PIVOT declaration (agent says "PIVOT: reason")

Fires on PostToolBatch — after a parallel batch completes, before next LLM call.
Can block (exit 2) to stop the agent from continuing.
"""

import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

# --- Configuration ---
STATE_DIR = Path.home() / ".agent-harness" / "state"
STATE_FILE = STATE_DIR / "loop_breaker.json"

MAX_IDENTICAL_COMMANDS = 3      # same command repeated
MAX_SIMILAR_COMMANDS = 5        # similar commands (same base, different args)
MAX_FILE_EDITS = 5              # same file edited too many times
MAX_BATCHES_PER_SESSION = 50    # total batch budget
PATTERN_WINDOW = 6              # how many recent batches to check for alternating pattern
SESSION_TIMEOUT = 1800

REVERT_PATTERN = re.compile(
    r"git\s+(checkout|restore|reset\s+--hard|revert)\b|rm\s+-rf?\s"
)
PIVOT_PATTERN = re.compile(r"PIVOT:\s*(.+)", re.IGNORECASE)


def load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            if time.time() - state.get("last_activity", 0) > SESSION_TIMEOUT:
                return new_state()
            return state
        except (json.JSONDecodeError, KeyError):
            return new_state()
    return new_state()


def new_state() -> dict:
    return {
        "last_activity": time.time(),
        "batch_count": 0,
        "command_history": [],   # last 20 commands
        "file_edit_counts": {},  # path → count
        "batch_signatures": [],  # last N batch signatures for pattern detection
        "loop_detected_count": 0,
    }


def save_state(state: dict):
    state["last_activity"] = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def normalize_command(cmd: str) -> str:
    """Normalize command for similarity comparison."""
    # Remove timestamps, PIDs, random strings
    cmd = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\b", "<TS>", cmd)
    cmd = re.sub(r"\b[0-9a-f]{8,}\b", "<HASH>", cmd)
    cmd = re.sub(r"\b\d+\b", "<N>", cmd)
    return cmd.strip()


def command_base(cmd: str) -> str:
    """Extract base command (first word/tool)."""
    parts = cmd.strip().split()
    if not parts:
        return ""
    # Handle common patterns
    if parts[0] in ("cd", "pushd"):
        return "cd"
    return " ".join(parts[:2]) if len(parts) > 1 else parts[0]


def batch_signature(tool_calls: list) -> str:
    """Create a fingerprint of a batch for pattern detection."""
    parts = []
    for call in tool_calls:
        name = call.get("tool_name", "")
        if name == "Bash":
            cmd = call.get("tool_input", {}).get("command", "")
            base = command_base(cmd)
            exit_code = call.get("tool_response", {}).get("exitCode", 0)
            parts.append(f"Bash({base})={'OK' if exit_code == 0 else 'FAIL'}")
        elif name in ("Edit", "Write"):
            path = call.get("tool_input", {}).get("file_path", "")
            filename = Path(path).name if path else "?"
            parts.append(f"{name}({filename})")
        else:
            parts.append(name)
    return "|".join(sorted(parts))


def detect_loops(state: dict, tool_calls: list) -> list[str]:
    """Detect loop patterns. Returns list of reasons if loop detected."""
    reasons = []

    # Extract commands from this batch
    commands = []
    for call in tool_calls:
        if call.get("tool_name") == "Bash":
            cmd = call.get("tool_input", {}).get("command", "")
            if cmd:
                commands.append(cmd)
        elif call.get("tool_name") in ("Edit", "Write"):
            path = call.get("tool_input", {}).get("file_path", "")
            if path:
                state["file_edit_counts"][path] = state["file_edit_counts"].get(path, 0) + 1

    # 1. Identical command repetition
    for cmd in commands:
        normalized = normalize_command(cmd)
        exact_count = sum(1 for h in state["command_history"] if normalize_command(h) == normalized)
        if exact_count >= MAX_IDENTICAL_COMMANDS:
            reasons.append(
                f"Same command executed {exact_count + 1} times: '{cmd[:60]}...'"
            )

    # 2. Similar command repetition (history + current batch)
    all_commands = state["command_history"] + commands
    for cmd in commands:
        base = command_base(cmd)
        similar_count = sum(1 for h in all_commands if command_base(h) == base)
        if similar_count >= MAX_SIMILAR_COMMANDS:
            reasons.append(
                f"Similar commands ({base}) executed {similar_count} times"
            )

    # 3. Same file edited too many times
    for path, count in state["file_edit_counts"].items():
        if count >= MAX_FILE_EDITS:
            reasons.append(
                f"File edited {count} times: {Path(path).name}"
            )

    # 4. Alternating pattern (A→B→A→B→...) — requires exactly 2 distinct signatures
    sig = batch_signature(tool_calls)
    state["batch_signatures"].append(sig)
    sigs = state["batch_signatures"][-PATTERN_WINDOW:]
    if len(sigs) >= 4:
        unique = set(sigs)
        if len(unique) == 2 and sigs[-1] == sigs[-3] and sigs[-2] == sigs[-4]:
            reasons.append(
                f"Alternating pattern detected over last {len(sigs)} batches"
            )

    # 5. Session budget exceeded
    if state["batch_count"] >= MAX_BATCHES_PER_SESSION:
        reasons.append(
            f"Session budget exceeded: {state['batch_count']}/{MAX_BATCHES_PER_SESSION} batches"
        )

    # 6. Revert/reset operations (pivot signal)
    for cmd in commands:
        if REVERT_PATTERN.search(cmd):
            reasons.append(
                f"Design pivot detected — revert operation: '{cmd[:60]}'"
            )

    # 7. Explicit PIVOT declaration
    for call in tool_calls:
        if call.get("tool_name") == "Bash":
            stdout = call.get("tool_response", {}).get("stdout", "")
            pivot_match = PIVOT_PATTERN.search(stdout)
            if pivot_match:
                reasons.append(
                    f"Explicit pivot declared: {pivot_match.group(1)[:100]}"
                )

    # Update command history (keep last 20)
    state["command_history"].extend(commands)
    state["command_history"] = state["command_history"][-20:]

    return reasons


def make_block_output(reasons: list[str], state: dict) -> dict:
    reasons_str = "\n".join(f"  • {r}" for r in reasons)
    return {
        "decision": "block",
        "reason": (
            f"LOOP BREAKER — Agent appears stuck (detected {len(reasons)} signal(s)):\n\n"
            f"{reasons_str}\n\n"
            f"Session stats: {state['batch_count']} batches, "
            f"{len(state['command_history'])} commands tracked.\n\n"
            "Please step back and reconsider your approach before continuing."
        ),
    }


def main():
    input_data = json.load(sys.stdin)
    tool_calls = input_data.get("tool_calls", [])

    state = load_state()
    state["batch_count"] += 1

    reasons = detect_loops(state, tool_calls)

    if reasons:
        state["loop_detected_count"] += 1
        save_state(state)
        json.dump(make_block_output(reasons, state), sys.stdout)
        sys.exit(2)

    save_state(state)
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
