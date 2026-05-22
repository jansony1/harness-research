#!/usr/bin/env python3
"""Integration tests for context_injector.py"""
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = str(Path(__file__).parent / "context_injector.py")
STATE_FILE = Path.home() / ".agent-harness" / "state" / "context_injector.json"


def reset():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def call_hook(hook_event: str, extra_data: dict = None) -> tuple[dict, int]:
    data = {"hook_event_name": hook_event}
    if extra_data:
        data.update(extra_data)
    inp = json.dumps(data)
    r = subprocess.run([sys.executable, SCRIPT], input=inp, capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return out, r.returncode


print("=" * 60)
print("Context Injector Tests")
print("=" * 60)

# --- Test 1: SessionStart fresh ---
print("\n[Test 1: SessionStart (fresh) — no context injected]")
reset()
out, code = call_hook("SessionStart", {"source": "startup"})
assert code == 0
assert out == {}
print("  PASS: clean start, no injection needed")

# --- Test 2: SessionStart resume with prior state ---
print("\n[Test 2: SessionStart (resume) — injects prior state]")
reset()
# Pre-populate state
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.write_text(json.dumps({
    "last_activity": time.time(),
    "consecutive_failures": 0,
    "total_failures": 7,
    "batch_count": 15,
    "tools_used": {"Bash": 5},
    "files_touched": ["src/app.py", "src/db.py", "test/app.test.py"],
    "last_checkpoint": 10,
}))

out, code = call_hook("SessionStart", {"source": "compact"})
assert "additionalContext" in out
assert "7 total failures" in out["additionalContext"]
assert "src/app.py" in out["additionalContext"]
print(f"  PASS: injected: '{out['additionalContext'][:80]}...'")

# --- Test 3: PostToolUseFailure — warning at threshold ---
print("\n[Test 3: PostToolUseFailure — warning after 2 failures]")
reset()
# First failure: no warning
out, _ = call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "command not found"})
assert out == {}

# Second failure: warning
out, _ = call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "npm ERR! test failed"})
assert "additionalContext" in out
assert "2 consecutive failures" in out["additionalContext"]
print(f"  PASS: warning injected at failure #2")
print(f"        → {out['additionalContext'].splitlines()[0]}")

# --- Test 4: PostToolUseFailure — escalating guidance ---
print("\n[Test 4: PostToolUseFailure — escalation at 3 and 5]")
reset()
for i in range(4):
    out, _ = call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "err"})

# At failure 5
out, _ = call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "still broken"})
assert "STRONGLY" in out.get("additionalContext", "")
print("  PASS: strong guidance at failure #5")

# --- Test 5: PostToolBatch — checkpoint every 10 batches ---
print("\n[Test 5: PostToolBatch — checkpoint at batch #10]")
reset()
for i in range(9):
    out, _ = call_hook("PostToolBatch", {"tool_calls": [
        {"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"exitCode": 0}}
    ]})
    assert "additionalContext" not in out, f"Should not checkpoint at batch {i+1}"

# Batch #10: checkpoint
out, _ = call_hook("PostToolBatch", {"tool_calls": [
    {"tool_name": "Bash", "tool_input": {"command": "test"}, "tool_response": {"exitCode": 0}}
]})
assert "CHECKPOINT" in out.get("additionalContext", "")
print(f"  PASS: checkpoint injected at batch #10")
print(f"        → {out['additionalContext']}")

# --- Test 6: PostToolBatch resets consecutive failures ---
print("\n[Test 6: PostToolBatch resets failure counter on success]")
reset()
# Accumulate failures
call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "err"})
call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "err"})
call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "err"})

# Success in batch
call_hook("PostToolBatch", {"tool_calls": [
    {"tool_name": "Bash", "tool_input": {"command": "npm test"}, "tool_response": {"exitCode": 0}}
]})

# Next failure should NOT be at count 4
out, _ = call_hook("PostToolUseFailure", {"tool_name": "Bash", "error": "new error"})
assert out == {}  # count = 1, below threshold
print("  PASS: failure counter reset after successful batch")

# --- Test 7: SubagentStop — insufficient output blocked ---
print("\n[Test 7: SubagentStop — too-brief output blocked]")
reset()
out, code = call_hook("SubagentStop", {"last_assistant_message": "Done."})
assert code == 2
assert out.get("decision") == "block"
assert "lacks actionable detail" in out.get("reason", "")
print("  PASS: subagent blocked — 'Done.' has no substance")

# --- Test 7b: SubagentStop — completion signal passes even if short ---
print("\n[Test 7b: SubagentStop — 'No issues found' passes (completion signal)]")
reset()
out, code = call_hook("SubagentStop", {"last_assistant_message": "No issues found, all tests pass."})
assert code == 0, f"Completion signal should pass, got exit {code}"
print("  PASS: completion signal whitelisted")

# --- Test 8: SubagentStop — short but with quality indicators passes ---
print("\n[Test 8: SubagentStop — short output with file path passes]")
reset()
short_with_path = "Fixed in /src/auth.py:42"
out, code = call_hook("SubagentStop", {"last_assistant_message": short_with_path})
assert code == 0
assert out == {}
print("  PASS: short output with quality indicator passes")

# --- Test 9: SubagentStop — long output always passes ---
print("\n[Test 9: SubagentStop — long output passes regardless]")
reset()
long_message = "I found the issue in src/auth.py line 42. The token validation is not checking expiry. Here's my recommendation: add a datetime comparison before proceeding."
out, code = call_hook("SubagentStop", {"last_assistant_message": long_message})
assert code == 0
assert out == {}
print("  PASS: long output passes through")

# --- Test 10: UserPromptSubmit — injects reminder when files modified but no tests ---
print("\n[Test 10: UserPromptSubmit — reminder to run tests]")
reset()
# Simulate state with files modified but no tests
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.write_text(json.dumps({
    "last_activity": time.time(), "consecutive_failures": 0,
    "total_failures": 0, "batch_count": 5, "tools_used": {},
    "files_touched": ["src/a.py", "src/b.py"], "last_checkpoint": 0,
    "tests_verified": False,
}))
out, code = call_hook("UserPromptSubmit", {"prompt": "how's it going?"})
assert "additionalContext" in out
assert "modified but tests not yet verified" in out["additionalContext"]
print(f"  PASS: reminder injected: '{out['additionalContext']}'")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
