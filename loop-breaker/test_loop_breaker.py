#!/usr/bin/env python3
"""Integration tests for loop_breaker.py"""
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = str(Path(__file__).parent / "loop_breaker.py")
STATE_FILE = Path.home() / ".agent-harness" / "state" / "loop_breaker.json"


def reset():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def call_hook(tool_calls: list) -> tuple[dict, int]:
    inp = json.dumps({"hook_event_name": "PostToolBatch", "tool_calls": tool_calls})
    r = subprocess.run([sys.executable, SCRIPT], input=inp, capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return out, r.returncode


def make_bash_call(command, exit_code=0, stdout=""):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "tool_response": {"stdout": stdout, "exitCode": exit_code}}


def make_edit_call(file_path):
    return {"tool_name": "Edit", "tool_input": {"file_path": file_path}, "tool_response": {}}


print("=" * 60)
print("Loop Breaker Tests")
print("=" * 60)

# --- Test 1: Same command repeated ---
print("\n[Test 1: Identical command repeated 4 times]")
reset()
batch = [make_bash_call("npm test")]
# Need 3 in history + 1 current = trigger
for i in range(3):
    out, code = call_hook(batch)
    assert code == 0, f"Should not trigger at iteration {i+1}"

out, code = call_hook(batch)
assert code == 2, f"Expected block at iteration 4, got exit {code}"
assert "Same command" in out.get("reason", "")
print("  PASS: blocked after 4 identical 'npm test' commands")
print(f"        → {out['reason'].splitlines()[2].strip()}")

# --- Test 2: Similar commands (same base) ---
print("\n[Test 2: Similar commands with different args]")
reset()
commands = [
    "git add src/a.py",
    "git add src/b.py",
    "git add src/c.py",
    "git add src/d.py",
]
for i, cmd in enumerate(commands):
    out, code = call_hook([make_bash_call(cmd)])
    if i < 3:
        assert code == 0, f"Should not trigger at '{cmd}'"

# 5th similar command should trigger (history has 4, current makes 5)
out, code = call_hook([make_bash_call("git add src/e.py")])
assert code == 2, f"Expected block for similar commands, got exit {code}"
assert "Similar commands" in out.get("reason", "")
print("  PASS: blocked after 5 similar 'git add' commands")

# --- Test 3: File edited too many times ---
print("\n[Test 3: Same file edited 5 times]")
reset()
for i in range(4):
    out, code = call_hook([make_edit_call("/src/app.py")])
    assert code == 0, f"Should not trigger at edit {i+1}"

out, code = call_hook([make_edit_call("/src/app.py")])
assert code == 2, f"Expected block for file churn, got exit {code}"
assert "File edited" in out.get("reason", "")
print("  PASS: blocked after 5 edits to same file")

# --- Test 4: Alternating pattern (edit → test fail → edit → test fail) ---
print("\n[Test 4: Alternating edit/test-fail pattern]")
reset()
batch_a = [make_edit_call("/src/handler.py")]
batch_b = [make_bash_call("npm test", exit_code=1, stdout="3 failing")]

# ABAB pattern needs 4 batches minimum
call_hook(batch_a)
call_hook(batch_b)
call_hook(batch_a)

out, code = call_hook(batch_b)
assert code == 2, f"Expected block for alternating pattern, got exit {code}"
assert "Alternating pattern" in out.get("reason", "")
print("  PASS: blocked on ABAB pattern (edit → test fail → edit → test fail)")

# --- Test 5: Normal workflow (no loop) ---
print("\n[Test 5: Normal workflow — no false positive]")
reset()
call_hook([make_bash_call("ls src/")])
call_hook([make_edit_call("/src/app.py")])
call_hook([make_bash_call("npm test", exit_code=0, stdout="12 passing")])
call_hook([make_edit_call("/src/helper.py")])
out, code = call_hook([make_bash_call("npm run build")])
assert code == 0, f"Normal workflow should not trigger, got exit {code}"
print("  PASS: no trigger during varied normal workflow")

# --- Test 6: Budget exceeded ---
print("\n[Test 6: Session batch budget exceeded]")
reset()
# Create state with batch_count near budget
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.write_text(json.dumps({
    "last_activity": time.time(),
    "batch_count": 49,
    "command_history": [],
    "file_edit_counts": {},
    "batch_signatures": [],
    "loop_detected_count": 0,
}))

out, code = call_hook([make_bash_call("echo done")])
assert code == 2, f"Expected block at budget limit, got exit {code}"
assert "budget exceeded" in out.get("reason", "")
print("  PASS: blocked at session budget limit (50 batches)")

# --- Test 7: git checkout does NOT trigger (pivot-gate's job, not loop-breaker's) ---
print("\n[Test 7: git checkout passes through (no false positive)]")
reset()
out, code = call_hook([make_bash_call("git checkout -- src/main.py")])
assert code == 0, f"git checkout should not trigger loop-breaker, got exit {code}"
print("  PASS: git checkout not falsely detected as loop")

# --- Test 8: Explicit PIVOT declaration ---
print("\n[Test 8: Explicit PIVOT: marker in output]")
reset()
out, code = call_hook([make_bash_call('echo "PIVOT: switching from REST to GraphQL"',
                                       stdout="PIVOT: switching from REST to GraphQL")])
assert code == 2, f"Expected block for PIVOT, got exit {code}"
assert "switching from REST to GraphQL" in out.get("reason", "")
print("  PASS: explicit PIVOT declaration detected")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
