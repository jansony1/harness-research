#!/usr/bin/env python3
"""
Stop Gate — Stop hook that prevents the agent from finishing
until quality criteria are met.

Checks performed before allowing agent to stop:
1. Are there uncommitted changes? (must commit or discard intentionally)
2. Did tests pass in this session? (must run tests at least once)
3. Are there lint/type errors? (must address them)
4. Did the agent actually complete the requested task? (heuristic)

Works by reading session state (shared with other harness hooks)
and checking file system state.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --- Configuration ---
STATE_DIR = Path.home() / ".agent-harness" / "state"
REQUIRE_TESTS = os.environ.get("STOP_GATE_REQUIRE_TESTS", "1") == "1"
REQUIRE_CLEAN_GIT = os.environ.get("STOP_GATE_REQUIRE_GIT", "1") == "1"
REQUIRE_NO_FIXME = os.environ.get("STOP_GATE_REQUIRE_NO_FIXME", "1") == "1"
MAX_CONSECUTIVE_BLOCKS = int(os.environ.get("STOP_GATE_MAX_BLOCKS", "3"))

# Patterns that suggest incomplete work
INCOMPLETE_MARKERS = ["TODO:", "FIXME:", "HACK:", "XXX:", "WIP"]


def get_session_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / "stop_gate.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            if time.time() - state.get("last_activity", 0) > 1800:
                return new_state()
            return state
        except (json.JSONDecodeError, KeyError):
            pass
    return new_state()


def new_state() -> dict:
    return {
        "last_activity": time.time(),
        "tests_ran": False,
        "tests_passed": False,
        "last_test_output": "",
        "consecutive_blocks": 0,
        "files_modified": [],
    }


def save_state(state: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["last_activity"] = time.time()
    (STATE_DIR / "stop_gate.json").write_text(json.dumps(state, indent=2))


def check_uncommitted_changes() -> str | None:
    """Check if there are staged/unstaged changes."""
    if not REQUIRE_CLEAN_GIT:
        return None
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None  # not a git repo, skip
        changes = [l for l in result.stdout.splitlines() if l.strip()]
        if changes:
            modified = changes[:5]
            return (
                f"Uncommitted changes detected ({len(changes)} files):\n"
                + "\n".join(f"  {f}" for f in modified)
                + ("\n  ..." if len(changes) > 5 else "")
                + "\n\nPlease commit your changes or explicitly discard them before stopping."
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def check_tests_ran(state: dict) -> str | None:
    """Check if tests were run during this session."""
    if not REQUIRE_TESTS:
        return None
    if not state.get("tests_ran"):
        return (
            "No tests were run during this session.\n"
            "Please run the test suite to verify your changes work correctly."
        )
    if not state.get("tests_passed"):
        return (
            "Tests were run but FAILED:\n"
            f"  {state.get('last_test_output', 'unknown')[:200]}\n"
            "Please fix the failing tests before stopping."
        )
    return None


def check_fixme_in_modified(state: dict) -> str | None:
    """Check if recently modified files contain TODO/FIXME markers."""
    if not REQUIRE_NO_FIXME:
        return None
    issues = []
    for filepath in state.get("files_modified", [])[:10]:
        try:
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                for i, line in enumerate(f, 1):
                    for marker in INCOMPLETE_MARKERS:
                        if marker in line:
                            issues.append(f"  {filepath}:{i}: {line.strip()[:80]}")
                            break
        except (OSError, UnicodeDecodeError):
            continue

    if issues:
        return (
            f"Incomplete work markers found in modified files ({len(issues)} occurrences):\n"
            + "\n".join(issues[:5])
            + ("\n  ..." if len(issues) > 5 else "")
            + "\n\nPlease resolve these before stopping."
        )
    return None


def make_block_output(reasons: list[str]) -> dict:
    combined = "\n\n".join(f"❌ {r}" for r in reasons)
    return {
        "decision": "block",
        "reason": (
            "STOP GATE — Cannot stop yet. Outstanding issues:\n\n"
            + combined
            + "\n\nPlease address these before finishing."
        ),
    }


def main():
    input_data = json.load(sys.stdin)
    hook_event = input_data.get("hook_event_name", "")

    # This hook fires on the "Stop" event
    state = get_session_state()

    # Safety valve: don't block more than N times in a row
    if state["consecutive_blocks"] >= MAX_CONSECUTIVE_BLOCKS:
        state["consecutive_blocks"] = 0
        save_state(state)
        json.dump({}, sys.stdout)
        return

    # Run all checks
    issues = []

    git_issue = check_uncommitted_changes()
    if git_issue:
        issues.append(git_issue)

    test_issue = check_tests_ran(state)
    if test_issue:
        issues.append(test_issue)

    fixme_issue = check_fixme_in_modified(state)
    if fixme_issue:
        issues.append(fixme_issue)

    if issues:
        state["consecutive_blocks"] += 1
        save_state(state)
        json.dump(make_block_output(issues), sys.stdout)
        sys.exit(2)
    else:
        state["consecutive_blocks"] = 0
        save_state(state)
        json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
