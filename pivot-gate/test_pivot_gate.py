#!/usr/bin/env python3
"""
Integration tests for pivot_gate.py

Simulates sequences of tool calls and verifies that the gate triggers
at the right moments.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

STATE_FILE = Path.home() / ".pivot-gate" / "session.json"
SCRIPT = str(Path(__file__).parent / "pivot_gate.py")


def reset_state():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def call_hook(tool_name: str, tool_input: dict, tool_response: dict) -> dict:
    input_data = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    }
    result = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}", file=sys.stderr)
    return json.loads(result.stdout) if result.stdout else {}


def test_consecutive_failures():
    """4 consecutive bash failures should trigger (scores: 0, 3, 6, 9 >= 8)"""
    reset_state()
    print("TEST: consecutive failures")

    for i in range(3):
        out = call_hook("Bash", {"command": "make build"}, {"stdout": "", "stderr": "error", "exitCode": 1})
        assert out == {}, f"Should not trigger at failure {i+1}"

    out = call_hook("Bash", {"command": "make build"}, {"stdout": "", "stderr": "error", "exitCode": 1})
    assert "hookSpecificOutput" in out, "Should trigger at failure 4"
    print("  PASS: triggered after 4 consecutive failures")


def test_git_revert():
    """git checkout should trigger quickly (score 5 + any other signal)"""
    reset_state()
    print("TEST: git revert command")

    # One failure (score 0, consecutive < 3) then a revert (score +5)
    call_hook("Bash", {"command": "npm test"}, {"stdout": "", "stderr": "fail", "exitCode": 1})
    call_hook("Bash", {"command": "npm test"}, {"stdout": "", "stderr": "fail", "exitCode": 1})
    call_hook("Bash", {"command": "npm test"}, {"stdout": "", "stderr": "fail", "exitCode": 1})

    out = call_hook("Bash", {"command": "git checkout -- src/main.py"}, {"stdout": "", "stderr": "", "exitCode": 0})
    assert "hookSpecificOutput" in out, "Should trigger on git revert after failures"
    print("  PASS: triggered on git checkout after consecutive failures")


def test_explicit_pivot():
    """echo PIVOT should trigger immediately"""
    reset_state()
    print("TEST: explicit PIVOT signal")

    out = call_hook("Bash", {"command": 'echo "PIVOT: current approach is wrong, need to use Redis instead"'},
                    {"stdout": "PIVOT: current approach is wrong, need to use Redis instead", "stderr": "", "exitCode": 0})
    assert "hookSpecificOutput" in out, "Should trigger immediately on PIVOT"
    assert "EXPLICIT PIVOT" in out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    print("  PASS: triggered immediately on explicit PIVOT declaration")


def test_file_churn():
    """Same file edited 3+ times (score +2) combined with failures triggers sooner"""
    reset_state()
    print("TEST: file churn")

    for i in range(3):
        call_hook("Edit", {"file_path": "/src/app.py", "old_string": "a", "new_string": "b"}, {})

    # churn score = 2, then failures: f1=0, f2=+3 (total 5), f3=+3 (total 8 -> trigger)
    call_hook("Bash", {"command": "test"}, {"stdout": "", "stderr": "err", "exitCode": 1})
    call_hook("Bash", {"command": "test"}, {"stdout": "", "stderr": "err", "exitCode": 1})

    out = call_hook("Bash", {"command": "test"}, {"stdout": "", "stderr": "err", "exitCode": 1})
    assert "hookSpecificOutput" in out, "Should trigger from combined churn + failures"
    print("  PASS: triggered from combined file churn + consecutive failures (3 failures instead of 4)")


def test_no_false_positive():
    """Normal workflow should not trigger"""
    reset_state()
    print("TEST: no false positive")

    # Normal: success, edit, success, write, success
    call_hook("Bash", {"command": "ls"}, {"stdout": "files", "stderr": "", "exitCode": 0})
    call_hook("Edit", {"file_path": "/src/a.py"}, {})
    call_hook("Bash", {"command": "npm test"}, {"stdout": "all pass", "stderr": "", "exitCode": 0})
    call_hook("Write", {"file_path": "/src/b.py"}, {})
    call_hook("Bash", {"command": "npm test"}, {"stdout": "all pass", "stderr": "", "exitCode": 0})

    state = json.loads(STATE_FILE.read_text())
    assert state["score"] == 0, f"Score should be 0 for normal workflow, got {state['score']}"
    print("  PASS: no trigger during normal workflow")


def test_resume_after_pause():
    """After pause, next call should reset score"""
    reset_state()
    print("TEST: resume after pause")

    # Trigger a pause
    call_hook("Bash", {"command": 'echo "PIVOT: testing"'},
              {"stdout": "PIVOT: testing", "stderr": "", "exitCode": 0})

    # Next call should reset
    out = call_hook("Bash", {"command": "ls"}, {"stdout": "files", "stderr": "", "exitCode": 0})
    assert out == {}, "Should pass through after resume"

    state = json.loads(STATE_FILE.read_text())
    assert state["score"] == 0, f"Score should be reset after resume, got {state['score']}"
    assert state["paused"] is False
    print("  PASS: score reset after pause/resume cycle")


if __name__ == "__main__":
    print("=" * 50)
    print("Pivot Gate Integration Tests")
    print("=" * 50)
    print()

    tests = [
        test_consecutive_failures,
        test_git_revert,
        test_explicit_pivot,
        test_file_churn,
        test_no_false_positive,
        test_resume_after_pause,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        print()

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    sys.exit(0 if failed == 0 else 1)
