#!/usr/bin/env python3
"""
Stop Gate Tracker — PostToolUse hook that feeds state to Stop Gate.

Tracks:
- Whether tests were run and their results
- Which files were modified
- Test pass/fail status

This runs on every PostToolUse; the actual gating happens in stop_gate.py (Stop hook).
"""

import json
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".agent-harness" / "state"

TEST_COMMANDS = re.compile(
    r"(npm\s+test|yarn\s+test|pytest|python\s+-m\s+pytest|"
    r"go\s+test|cargo\s+test|jest|vitest|mocha|rspec|"
    r"make\s+test|gradle\s+test|mvn\s+test)"
)

TEST_PASS_SIGNALS = ["passing", "passed", "ok", "✓", "PASS", "All tests passed", "Tests:.*passed"]
TEST_FAIL_SIGNALS = ["failing", "failed", "FAIL", "✗", "Error:", "AssertionError"]


def load_state() -> dict:
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


def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    state = load_state()

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        stdout = tool_response.get("stdout", "")
        exit_code = tool_response.get("exitCode", 0)

        # Track test execution
        if TEST_COMMANDS.search(command):
            state["tests_ran"] = True
            state["last_test_output"] = stdout[-500:]  # keep last 500 chars

            has_pass = any(re.search(sig, stdout, re.IGNORECASE) for sig in TEST_PASS_SIGNALS)
            has_fail = any(re.search(sig, stdout, re.IGNORECASE) for sig in TEST_FAIL_SIGNALS)

            if has_fail:
                state["tests_passed"] = False
            elif has_pass and exit_code == 0:
                state["tests_passed"] = True

    elif tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        if file_path and file_path not in state["files_modified"]:
            state["files_modified"].append(file_path)

    save_state(state)
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
