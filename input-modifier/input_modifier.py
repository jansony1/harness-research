#!/usr/bin/env python3
"""
Input Modifier — PreToolUse hook that modifies tool parameters before execution.

Unlike safety-guard which blocks, this hook CHANGES what the tool does:
- git push → git push --dry-run (preview before real push)
- rm -rf dir → echo "Would delete: dir" (dry-run destructive ops)
- Read large files → inject limit parameter
- Bash without timeout → add timeout prefix

Uses PreToolUse with `updatedInput` to transparently modify parameters.
"""

import json
import os
import re
import sys
from pathlib import Path

# --- Configuration ---
DRY_RUN_GIT_PUSH = os.environ.get("INPUT_MOD_DRY_RUN_PUSH", "1") == "1"
DRY_RUN_DESTRUCTIVE = os.environ.get("INPUT_MOD_DRY_RUN_RM", "1") == "1"
LIMIT_FILE_READS = os.environ.get("INPUT_MOD_LIMIT_READS", "1") == "1"
ADD_TIMEOUTS = os.environ.get("INPUT_MOD_TIMEOUTS", "1") == "1"

MAX_READ_LINES = 500
DEFAULT_TIMEOUT = 30  # seconds

# Commands that should be wrapped with timeout
LONG_RUNNING_PATTERNS = re.compile(
    r"^(npm\s+(install|ci|run|build)|yarn\s+(install|build)|"
    r"pip\s+install|cargo\s+build|make\b|gradle\b|mvn\b|"
    r"docker\s+build|apt-get\s+install)"
)


def modify_bash(command: str) -> tuple[str, str] | None:
    """Returns (modified_command, reason) or None to pass through."""

    # git push → git push --dry-run
    if DRY_RUN_GIT_PUSH and re.search(r"git\s+push\b", command):
        if "--dry-run" not in command and "--force" not in command:
            modified = re.sub(r"(git\s+push)", r"\1 --dry-run", command)
            return modified, "Added --dry-run to preview push before executing"

    # rm -rf / rm -r → preview with find
    if DRY_RUN_DESTRUCTIVE:
        rm_match = re.match(r"rm\s+(-rf?|-fr?)\s+(.+)", command)
        if rm_match:
            target = rm_match.group(2).strip()
            # Don't modify rm on clearly temp/build artifacts
            if not any(p in target for p in ["/tmp", "node_modules", "__pycache__", ".cache", "dist/", "build/"]):
                modified = f'echo "[DRY-RUN] Would delete:" && find {target} -maxdepth 1 -print | head -20 && echo "... use rm directly if intended"'
                return modified, f"Converted destructive rm to preview (target: {target})"

    # Long-running commands → add timeout prefix
    if ADD_TIMEOUTS and LONG_RUNNING_PATTERNS.match(command.strip()):
        if not command.strip().startswith("timeout"):
            modified = f"timeout {DEFAULT_TIMEOUT} {command}"
            return modified, f"Added {DEFAULT_TIMEOUT}s timeout to long-running command"

    return None


def modify_read(file_path: str, current_limit: int | None) -> tuple[dict, str] | None:
    """Returns (updated_input_fields, reason) or None."""
    if not LIMIT_FILE_READS:
        return None

    # Only limit if no limit already set and file might be large
    if current_limit is not None:
        return None

    try:
        size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    except OSError:
        return None

    if size > 50000:  # > 50KB
        return {"limit": MAX_READ_LINES}, f"Limited read to {MAX_READ_LINES} lines (file is {size // 1024}KB)"

    return None


def make_modify_output(updated_input: dict, reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated_input,
            "additionalContext": f"[Input Modified] {reason}",
        }
    }


def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        result = modify_bash(command)
        if result:
            modified_cmd, reason = result
            json.dump(make_modify_output({"command": modified_cmd}, reason), sys.stdout)
            return

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        current_limit = tool_input.get("limit")
        result = modify_read(file_path, current_limit)
        if result:
            updated_fields, reason = result
            new_input = {**tool_input, **updated_fields}
            json.dump(make_modify_output(new_input, reason), sys.stdout)
            return

    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
