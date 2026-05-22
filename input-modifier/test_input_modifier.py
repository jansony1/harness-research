#!/usr/bin/env python3
"""Integration tests for input_modifier.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = str(Path(__file__).parent / "input_modifier.py")

os.environ["INPUT_MOD_DRY_RUN_PUSH"] = "1"
os.environ["INPUT_MOD_DRY_RUN_RM"] = "1"
os.environ["INPUT_MOD_LIMIT_READS"] = "1"
os.environ["INPUT_MOD_TIMEOUTS"] = "1"


def call_hook(tool_name: str, tool_input: dict) -> dict:
    inp = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    r = subprocess.run([sys.executable, SCRIPT], input=inp, capture_output=True, text=True, env=os.environ)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def get_updated_input(out):
    return out.get("hookSpecificOutput", {}).get("updatedInput", {})


def get_context(out):
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


print("=" * 60)
print("Input Modifier Tests")
print("=" * 60)

# --- git push → --dry-run ---
print("\n[Test 1: git push gets --dry-run]")
out = call_hook("Bash", {"command": "git push origin main"})
updated = get_updated_input(out)
assert "--dry-run" in updated.get("command", ""), f"Expected --dry-run, got: {updated}"
assert "git push --dry-run origin main" == updated["command"]
print(f"  PASS: '{updated['command']}'")
print(f"        Context: {get_context(out)}")

# --- git push --force is NOT modified (left for safety-guard to block) ---
print("\n[Test 2: git push --force is not modified (safety-guard's job)]")
out = call_hook("Bash", {"command": "git push --force origin main"})
assert out == {}, f"Should pass through, got: {out}"
print("  PASS: force push not modified (deferred to safety-guard)")

# --- rm -rf → dry-run preview ---
print("\n[Test 3: rm -rf becomes preview]")
out = call_hook("Bash", {"command": "rm -rf src/old_module"})
updated = get_updated_input(out)
assert "find" in updated.get("command", ""), f"Expected find command, got: {updated}"
assert "Would delete" in updated["command"]
print(f"  PASS: Converted to: {updated['command'][:70]}...")

# --- rm on temp/build dirs is not modified ---
print("\n[Test 4: rm node_modules not modified]")
out = call_hook("Bash", {"command": "rm -rf node_modules"})
assert out == {}, f"Should pass through for build artifacts, got: {out}"
print("  PASS: rm node_modules passes through (known build artifact)")

# --- Long-running command gets timeout ---
print("\n[Test 5: npm install gets timeout]")
out = call_hook("Bash", {"command": "npm install"})
updated = get_updated_input(out)
assert updated["command"].startswith("timeout 30 "), f"Expected timeout prefix, got: {updated}"
print(f"  PASS: '{updated['command']}'")

print("\n[Test 6: cargo build gets timeout]")
out = call_hook("Bash", {"command": "cargo build --release"})
updated = get_updated_input(out)
assert "timeout 30" in updated["command"]
print(f"  PASS: '{updated['command']}'")

# --- Already has timeout → no double-wrap ---
print("\n[Test 7: command with timeout not double-wrapped]")
out = call_hook("Bash", {"command": "timeout 60 npm run build"})
assert out == {}, f"Should not double-wrap, got: {out}"
print("  PASS: no double-wrap")

# --- Large file Read gets limit ---
print("\n[Test 8: Large file read gets limit]")
# Create a 100KB temp file
tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False)
tmpfile.write("x\n" * 60000)
tmpfile.close()

out = call_hook("Read", {"file_path": tmpfile.name})
updated = get_updated_input(out)
assert updated.get("limit") == 500, f"Expected limit=500, got: {updated}"
print(f"  PASS: limit={updated['limit']} injected for {os.path.getsize(tmpfile.name)//1024}KB file")
os.unlink(tmpfile.name)

# --- Small file Read not modified ---
print("\n[Test 9: Small file read not modified]")
tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
tmpfile.write("print('hello')\n")
tmpfile.close()

out = call_hook("Read", {"file_path": tmpfile.name})
assert out == {}, f"Small file should pass through, got: {out}"
print("  PASS: small file passes through")
os.unlink(tmpfile.name)

# --- Read with existing limit not modified ---
print("\n[Test 10: Read with explicit limit not modified]")
out = call_hook("Read", {"file_path": "/some/big/file.log", "limit": 100})
assert out == {}, f"Existing limit should not be overridden, got: {out}"
print("  PASS: existing limit respected")

# --- Normal commands pass through ---
print("\n[Test 11: Normal commands pass through]")
for cmd in ["ls -la", "cat README.md", "grep -r 'foo' src/", "git status", "echo hello"]:
    out = call_hook("Bash", {"command": cmd})
    assert out == {}, f"'{cmd}' should pass through, got: {out}"
print("  PASS: 5 normal commands all pass through")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
