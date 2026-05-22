#!/usr/bin/env python3
"""Integration tests for stop_gate.py + stop_gate_tracker.py"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TRACKER = str(Path(__file__).parent / "stop_gate_tracker.py")
GATE = str(Path(__file__).parent / "stop_gate.py")

# Disable git check in tests (can't control repo state)
os.environ["STOP_GATE_REQUIRE_GIT"] = "0"
STATE_DIR = Path.home() / ".agent-harness" / "state"
STATE_FILE = STATE_DIR / "stop_gate.json"


def reset():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def call_tracker(tool_name, tool_input, tool_response):
    inp = json.dumps({"tool_name": tool_name, "tool_input": tool_input, "tool_response": tool_response})
    subprocess.run([sys.executable, TRACKER], input=inp, capture_output=True, text=True)


def call_gate() -> tuple[dict, int]:
    inp = json.dumps({"hook_event_name": "Stop", "session_id": "test"})
    r = subprocess.run([sys.executable, GATE], input=inp, capture_output=True, text=True, env=os.environ)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return out, r.returncode


print("=" * 60)
print("Stop Gate Tests")
print("=" * 60)

# --- Test 1: No tests ran → blocked ---
print("\n[Test 1: Agent stops without running tests]")
reset()
call_tracker("Edit", {"file_path": "/tmp/test_app.py"}, {})
out, code = call_gate()
assert code == 2, f"Expected block, got exit {code}"
assert "No tests were run" in out.get("reason", "")
print("  PASS: blocked — 'No tests were run during this session'")

# --- Test 2: Tests ran but failed → blocked ---
print("\n[Test 2: Tests ran but failed]")
reset()
call_tracker("Bash", {"command": "npm test"}, {
    "stdout": "  3 failing\n  ✗ should validate input\n  AssertionError: expected 200 to equal 400",
    "exitCode": 1
})
out, code = call_gate()
assert code == 2, f"Expected block, got exit {code}"
assert "FAILED" in out.get("reason", "")
print("  PASS: blocked — 'Tests were run but FAILED'")

# --- Test 3: Tests passed → allowed ---
print("\n[Test 3: Tests passed, clean state]")
reset()
call_tracker("Bash", {"command": "pytest"}, {
    "stdout": "===== 12 passed in 2.1s =====",
    "exitCode": 0
})
# Ensure no FIXME files
out, code = call_gate()
assert code == 0, f"Expected allow, got exit {code}"
assert out == {}
print("  PASS: allowed — tests passed, no issues")

# --- Test 4: FIXME in modified file → blocked ---
print("\n[Test 4: FIXME marker in modified file]")
reset()
# Create a temp file with FIXME
tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
tmpfile.write("def foo():\n    # TODO: implement this\n    pass\n")
tmpfile.close()

call_tracker("Bash", {"command": "pytest"}, {"stdout": "5 passed", "exitCode": 0})
call_tracker("Edit", {"file_path": tmpfile.name}, {})
out, code = call_gate()
assert code == 2, f"Expected block, got exit {code}"
assert "TODO:" in out.get("reason", "")
print(f"  PASS: blocked — found TODO in {tmpfile.name}")
os.unlink(tmpfile.name)

# --- Test 5: Safety valve — max 3 blocks then allow ---
print("\n[Test 5: Safety valve after 3 consecutive blocks]")
reset()
# Simulate 3 blocks
for i in range(3):
    call_gate()  # each one increments consecutive_blocks

# 4th call should pass through (safety valve)
out, code = call_gate()
assert code == 0, f"Expected allow after safety valve, got exit {code}"
print("  PASS: allowed after 3 consecutive blocks (safety valve)")

# --- Test 6: Test state updates correctly ---
print("\n[Test 6: State updates — fail then pass]")
reset()
# First: fail
call_tracker("Bash", {"command": "npm test"}, {
    "stdout": "2 failing", "exitCode": 1
})
state = json.loads(STATE_FILE.read_text())
assert state["tests_ran"] is True
assert state["tests_passed"] is False

# Then: fix and pass
call_tracker("Bash", {"command": "npm test"}, {
    "stdout": "All tests passed\n  10 passing (3s)", "exitCode": 0
})
state = json.loads(STATE_FILE.read_text())
assert state["tests_passed"] is True
print("  PASS: state correctly tracks fail → pass transition")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
