#!/usr/bin/env python3
"""Integration tests for compact_guard.py + compact_guard_collector.py"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

GUARD = str(Path(__file__).parent / "compact_guard.py")
COLLECTOR = str(Path(__file__).parent / "compact_guard_collector.py")
STATE_DIR = Path.home() / ".agent-harness" / "state"
MEMORY_FILE = STATE_DIR / "compact_memory.json"

os.environ["COMPACT_GUARD_BLOCK_SECONDS"] = "60"


def reset():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()


def call_guard(hook_event: str, extra: dict = None) -> tuple[dict, int]:
    data = {"hook_event_name": hook_event}
    if extra:
        data.update(extra)
    r = subprocess.run([sys.executable, GUARD], input=json.dumps(data),
                       capture_output=True, text=True, env=os.environ)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return out, r.returncode


def call_collector(tool_name: str, tool_input: dict, tool_response: dict):
    data = {"tool_name": tool_name, "tool_input": tool_input, "tool_response": tool_response}
    subprocess.run([sys.executable, COLLECTOR], input=json.dumps(data),
                   capture_output=True, text=True)


print("=" * 60)
print("Compact Guard Tests")
print("=" * 60)

# --- Test 1: Block auto-compact on fresh session ---
print("\n[Test 1: Block auto-compact within first 60s]")
reset()
# Create fresh state with recent session_start
STATE_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE.write_text(json.dumps({
    "saved_at": None,
    "session_start": time.time(),  # just started
    "critical_context": [],
    "decisions": [],
    "current_task": None,
    "files_in_progress": [],
    "compact_count": 0,
}))

out, code = call_guard("PreCompact", {"trigger": "auto"})
assert code == 2, f"Expected block, got exit {code}"
assert "block" in out.get("decision", "")
assert "session only" in out.get("reason", "")
print(f"  PASS: auto-compact blocked — '{out['reason'][:60]}'")

# --- Test 2: Allow manual compact always ---
print("\n[Test 2: Manual compact always allowed]")
reset()
MEMORY_FILE.write_text(json.dumps({
    "saved_at": None,
    "session_start": time.time(),
    "critical_context": [],
    "decisions": [],
    "current_task": None,
    "files_in_progress": [],
    "compact_count": 0,
}))

out, code = call_guard("PreCompact", {"trigger": "manual"})
assert code == 0, f"Manual compact should be allowed, got exit {code}"
print("  PASS: manual compact passes through")

# --- Test 3: Allow auto-compact after 60s ---
print("\n[Test 3: Allow auto-compact after session matures]")
reset()
MEMORY_FILE.write_text(json.dumps({
    "saved_at": None,
    "session_start": time.time() - 120,  # 2 minutes ago
    "critical_context": [],
    "decisions": [],
    "current_task": None,
    "files_in_progress": [],
    "compact_count": 0,
}))

out, code = call_guard("PreCompact", {"trigger": "auto"})
assert code == 0, f"Should allow after 60s, got exit {code}"
print("  PASS: auto-compact allowed after 120s")

# --- Test 4: Collector captures markers from Bash output ---
print("\n[Test 4: Collector captures DECISION/TASK/CRITICAL markers]")
reset()
call_collector("Bash", {"command": "echo info"}, {
    "stdout": "DECISION: Use Redis instead of Memcached for session store\nTASK: Implement caching layer\nCRITICAL: Must maintain backward compat with v1 API",
    "exitCode": 0,
})

memory = json.loads(MEMORY_FILE.read_text())
assert "Use Redis instead of Memcached" in memory["decisions"][0]
assert memory["current_task"] == "Implement caching layer"
assert "backward compat" in memory["critical_context"][0]
print("  PASS: all markers captured")
print(f"        Decision: {memory['decisions'][0]}")
print(f"        Task: {memory['current_task']}")
print(f"        Critical: {memory['critical_context'][0]}")

# --- Test 5: Collector tracks file modifications ---
print("\n[Test 5: Collector tracks file modifications]")
call_collector("Edit", {"file_path": "/src/cache.py"}, {})
call_collector("Write", {"file_path": "/src/redis_client.py"}, {})

memory = json.loads(MEMORY_FILE.read_text())
assert "/src/cache.py" in memory["files_in_progress"]
assert "/src/redis_client.py" in memory["files_in_progress"]
print(f"  PASS: tracking {len(memory['files_in_progress'])} files in progress")

# --- Test 6: PostCompact restores critical context ---
print("\n[Test 6: PostCompact injects recovery context]")
out, code = call_guard("PostCompact", {"compact_summary": "Previous conversation was about caching..."})
assert "additionalContext" in out
ctx = out["additionalContext"]
assert "TASK IN PROGRESS" in ctx
assert "caching layer" in ctx
assert "DECISIONS" in ctx
assert "Redis" in ctx
assert "CRITICAL" in ctx
assert "backward compat" in ctx
assert "FILES BEING MODIFIED" in ctx
print("  PASS: full context recovery injected")
print(f"        Preview:\n{ctx[:300]}")

# --- Test 7: Empty state → minimal PostCompact ---
print("\n[Test 7: Empty state — only compact count injected]")
reset()
STATE_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE.write_text(json.dumps({
    "saved_at": None, "session_start": time.time() - 300,
    "critical_context": [], "decisions": [],
    "current_task": None, "files_in_progress": [], "compact_count": 1,
}))

out, code = call_guard("PostCompact", {"compact_summary": ""})
assert "additionalContext" in out
assert "COMPACT #" in out["additionalContext"]
print("  PASS: minimal recovery (just compact count)")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
