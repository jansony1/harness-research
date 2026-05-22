#!/usr/bin/env python3
"""
Context Injector — Multi-event hook that injects contextual information
into the agent's context at strategic moments.

Hook events handled:
- SessionStart: inject session rules, project context, memory from prior sessions
- PostToolUseFailure: inject failure count warning + guidance
- PostToolBatch: inject progress checkpoint summary
- SubagentStop: inject quality feedback if output is insufficient

Uses `additionalContext` field to add information without modifying tool output.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# --- Configuration ---
STATE_DIR = Path.home() / ".agent-harness" / "state"
STATE_FILE = STATE_DIR / "context_injector.json"
SESSION_TIMEOUT = 1800

# Thresholds
FAILURE_WARNING_AT = 2        # warn after N consecutive failures
CHECKPOINT_EVERY_N_BATCHES = 10  # inject checkpoint every N batches
MIN_SUBAGENT_OUTPUT_LENGTH = 100  # below this, check for substance

QUALITY_INDICATORS = re.compile(
    r"/[\w./]+|"           # file path
    r"`[^`]+`|"            # code reference
    r"line\s+\d+|:\d+|"   # line number
    r"\b(should|recommend|suggest|consider)\b",
    re.IGNORECASE
)

COMPLETION_SIGNALS = re.compile(
    r"\b(pass|passed|succeed|success|complete|fixed|resolved|"
    r"no issues|no errors|no warnings|all tests|already)\b",
    re.IGNORECASE
)


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
        "consecutive_failures": 0,
        "total_failures": 0,
        "batch_count": 0,
        "tools_used": {},
        "files_touched": [],
        "last_checkpoint": 0,
        "tests_verified": False,
    }


def save_state(state: dict):
    state["last_activity"] = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --- Event Handlers ---

def handle_session_start(input_data: dict, state: dict) -> dict:
    """Inject session-level context at startup."""
    source = input_data.get("source", "startup")

    context_parts = []

    # On resume after compact, remind of key state
    if source in ("resume", "compact"):
        if state["total_failures"] > 0:
            context_parts.append(
                f"[Session State] Prior to compaction: {state['total_failures']} total failures, "
                f"{len(state['files_touched'])} files modified."
            )
        if state["files_touched"]:
            context_parts.append(
                f"[Modified Files] {', '.join(state['files_touched'][-10:])}"
            )

    # Always inject session rules on fresh start
    if source == "startup":
        state.update(new_state())  # reset for new session

    if context_parts:
        return {"additionalContext": "\n".join(context_parts)}
    return {}


def handle_post_tool_failure(input_data: dict, state: dict) -> dict:
    """Inject warning when failures accumulate."""
    state["consecutive_failures"] += 1
    state["total_failures"] += 1

    tool_name = input_data.get("tool_name", "")
    error = input_data.get("error", "")

    # Track which tools are failing
    state["tools_used"][tool_name] = state["tools_used"].get(tool_name, 0) + 1

    if state["consecutive_failures"] >= FAILURE_WARNING_AT:
        n = state["consecutive_failures"]
        guidance = []
        guidance.append(f"[WARNING] {n} consecutive failures detected.")
        guidance.append(f"  Last error: {error[:150]}")

        if n >= 3:
            guidance.append("  Consider: Is the current approach working? You may need to step back and rethink.")
        if n >= 5:
            guidance.append("  STRONGLY consider stopping and explaining the blocker to the user.")

        return {"additionalContext": "\n".join(guidance)}

    return {}


def handle_post_tool_batch(input_data: dict, state: dict) -> dict:
    """Inject progress checkpoint every N batches."""
    state["batch_count"] += 1

    # Reset consecutive failures if any tool in batch succeeded
    tool_calls = input_data.get("tool_calls", [])
    for call in tool_calls:
        resp = call.get("tool_response", {})
        if resp.get("exitCode", 0) == 0:
            state["consecutive_failures"] = 0
            break

    # Track files
    for call in tool_calls:
        if call.get("tool_name") in ("Edit", "Write"):
            path = call.get("tool_input", {}).get("file_path", "")
            if path and path not in state["files_touched"]:
                state["files_touched"].append(path)

    # Periodic checkpoint
    if state["batch_count"] - state["last_checkpoint"] >= CHECKPOINT_EVERY_N_BATCHES:
        state["last_checkpoint"] = state["batch_count"]
        checkpoint = (
            f"[CHECKPOINT — Batch #{state['batch_count']}] "
            f"Failures: {state['total_failures']}, "
            f"Files modified: {len(state['files_touched'])}. "
            f"Pause and verify you're still on track."
        )
        return {"additionalContext": checkpoint}

    return {}


def handle_user_prompt_submit(input_data: dict, state: dict) -> dict:
    """Inject status reminders when user sends a new message."""
    reminders = []

    if state["total_failures"] >= 3:
        reminders.append(
            f"[STATUS] {state['total_failures']} failures this session, "
            f"{state['consecutive_failures']} consecutive."
        )

    files = state.get("files_touched", [])
    if files and not state.get("tests_verified"):
        reminders.append(
            f"[REMINDER] {len(files)} files modified but tests not yet verified."
        )

    if reminders:
        return {"additionalContext": "\n".join(reminders)}
    return {}


def handle_subagent_stop(input_data: dict, state: dict) -> dict:
    """Block subagent only if output is short AND lacks any substance or completion signal."""
    last_message = input_data.get("last_assistant_message", "")
    stripped = last_message.strip()

    if not stripped:
        return {
            "decision": "block",
            "reason": "Empty response. Please provide findings or conclusions.",
        }

    if len(stripped) >= MIN_SUBAGENT_OUTPUT_LENGTH:
        return {}

    if COMPLETION_SIGNALS.search(stripped):
        return {}

    if QUALITY_INDICATORS.search(stripped):
        return {}

    return {
        "decision": "block",
        "reason": (
            "Your response lacks actionable detail. Please include:\n"
            "- Specific file paths or line numbers\n"
            "- Code references or concrete conclusions"
        ),
    }


def main():
    input_data = json.load(sys.stdin)
    hook_event = input_data.get("hook_event_name", "")

    state = load_state()
    output = {}

    if hook_event == "SessionStart":
        output = handle_session_start(input_data, state)
    elif hook_event == "UserPromptSubmit":
        output = handle_user_prompt_submit(input_data, state)
    elif hook_event == "PostToolUseFailure":
        output = handle_post_tool_failure(input_data, state)
    elif hook_event == "PostToolBatch":
        output = handle_post_tool_batch(input_data, state)
    elif hook_event == "SubagentStop":
        output = handle_subagent_stop(input_data, state)

    save_state(state)
    json.dump(output, sys.stdout)

    # SubagentStop with block needs exit 2
    if output.get("decision") == "block":
        sys.exit(2)


if __name__ == "__main__":
    main()
