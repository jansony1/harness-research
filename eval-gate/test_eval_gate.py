#!/usr/bin/env python3
"""Integration tests for eval_gate.py

Since eval_gate invokes an external LLM (claude --print), tests mock the reviewer
by overriding EVAL_GATE_REVIEWER env var with a script that returns controlled output.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT = str(Path(__file__).parent / "eval_gate.py")
STATE_FILE = Path.home() / ".agent-harness" / "state" / "eval_gate.json"


def reset():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def make_mock_reviewer(response: str) -> str:
    """Create a temp script that echoes a fixed response (simulates claude --print)."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
    f.write(f'#!/bin/bash\necho "{response}"\n')
    f.close()
    os.chmod(f.name, 0o755)
    return f.name


TEST_REPO = None

def setup_test_repo():
    """Create a temp git repo with an uncommitted change for diff."""
    global TEST_REPO
    TEST_REPO = tempfile.mkdtemp()
    subprocess.run(["git", "init"], cwd=TEST_REPO, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=TEST_REPO, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=TEST_REPO, capture_output=True)
    # Initial commit
    Path(TEST_REPO, "main.py").write_text("def hello():\n    return 'hi'\n")
    subprocess.run(["git", "add", "."], cwd=TEST_REPO, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=TEST_REPO, capture_output=True)
    # Uncommitted change (this creates the diff)
    Path(TEST_REPO, "main.py").write_text("def hello():\n    return 'hello world'\n\ndef new_func():\n    pass\n")


def call_gate(reviewer_response: str, has_diff: bool = True) -> tuple[dict, int]:
    mock = make_mock_reviewer(reviewer_response)
    env = os.environ.copy()
    env["EVAL_GATE_REVIEWER"] = mock

    cwd = TEST_REPO if has_diff else tempfile.mkdtemp()

    inp = json.dumps({"hook_event_name": "TaskCompleted"})
    r = subprocess.run(
        [sys.executable, SCRIPT],
        input=inp, capture_output=True, text=True, env=env, cwd=cwd,
    )
    os.unlink(mock)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return out, r.returncode


setup_test_repo()


print("=" * 60)
print("Eval Gate Tests")
print("=" * 60)

# --- Test 1: Reviewer approves → pass through ---
print("\n[Test 1: Reviewer says APPROVED → task completes]")
reset()
out, code = call_gate("APPROVED")
assert code == 0, f"Expected pass, got exit {code}"
assert out == {}
print("  PASS: APPROVED → task completion allowed")

# --- Test 2: Reviewer rejects → blocked ---
print("\n[Test 2: Reviewer finds bugs → task blocked]")
reset()
out, code = call_gate("Bug: missing null check on line 42. Edge case: empty input not handled.")
assert code == 2, f"Expected block, got exit {code}"
assert "Review did not pass" in out.get("reason", "")
assert "null check" in out.get("reason", "")
print("  PASS: blocked with review feedback")
print(f"        → {out['reason'].splitlines()[2][:60]}")

# --- Test 3: No diff → pass through ---
print("\n[Test 3: No changes to review → pass through]")
reset()
out, code = call_gate("should not be called", has_diff=False)
assert code == 0
print("  PASS: no diff, no review needed")

# --- Test 4: Safety valve — max 2 consecutive blocks ---
print("\n[Test 4: Safety valve after 2 consecutive rejections]")
reset()
# First rejection
call_gate("Bug found")
# Second rejection
call_gate("Still buggy")
# Third should pass (safety valve)
out, code = call_gate("Bug found")
assert code == 0, f"Expected safety valve pass, got exit {code}"
print("  PASS: safety valve triggered after 2 blocks")

# --- Test 5: Reviewer timeout → pass through (don't block) ---
print("\n[Test 5: Reviewer returns empty → pass through]")
reset()
out, code = call_gate("")
assert code == 0
print("  PASS: empty reviewer response → graceful pass")

# --- Test 6: APPROVED with extra text still passes ---
print("\n[Test 6: APPROVED with comments still passes]")
reset()
out, code = call_gate("Looks good overall. Minor style nit but not blocking. APPROVED")
assert code == 0
print("  PASS: APPROVED keyword found despite extra commentary")

# --- Test 7: State tracks stats ---
print("\n[Test 7: State tracks review statistics]")
reset()
call_gate("APPROVED")
call_gate("Bug found")
call_gate("APPROVED")
state = json.loads(STATE_FILE.read_text())
assert state["reviews_done"] == 3
assert state["approvals"] == 2
assert state["rejections"] == 1
print(f"  PASS: stats tracked — {state['reviews_done']} reviews, {state['approvals']} approved, {state['rejections']} rejected")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
