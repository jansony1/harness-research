#!/usr/bin/env python3
"""
Safety Guard — PreToolUse hook that blocks destructive operations.

Intercepts dangerous commands BEFORE execution:
- Destructive git operations (push --force, reset --hard, branch -D)
- File system destruction (rm -rf, chmod 777)
- Credential exposure (cat .env, echo $SECRET)
- Production-affecting commands (deploy, migrate in prod)
- Unsafe file modifications (writing to protected paths)
"""

import json
import re
import sys
from pathlib import Path

# --- Configuration ---

DESTRUCTIVE_BASH_PATTERNS = [
    (r"git\s+push\s+.*--force", "force push can overwrite remote history"),
    (r"git\s+push\s+.*-f\b", "force push can overwrite remote history"),
    (r"git\s+reset\s+--hard", "hard reset discards uncommitted work"),
    (r"git\s+clean\s+-f", "git clean permanently deletes untracked files"),
    (r"git\s+branch\s+-D", "force-deleting branch without merge check"),
    (r"rm\s+-rf?\s+/(?!tmp)", "deleting from root filesystem"),
    (r"rm\s+-rf?\s+~", "deleting from home directory"),
    (r"rm\s+-rf?\s+\.\s*$", "deleting entire current directory"),
    (r"rm\s+-rf?\s+\*", "wildcard deletion"),
    (r"chmod\s+777", "world-writable permissions are a security risk"),
    (r"chmod\s+-R\s+777", "recursive world-writable permissions"),
    (r">\s*/dev/sd[a-z]", "writing directly to block device"),
    (r"dd\s+.*of=/dev/", "writing directly to block device"),
    (r"mkfs\.", "formatting filesystem"),
    (r":(){ :\|:& };:", "fork bomb"),
    (r"\bsudo\b", "elevated privileges — confirm intent"),
    (r"curl\s+.*\|\s*(ba)?sh", "piping remote script to shell"),
    (r"wget\s+.*\|\s*(ba)?sh", "piping remote script to shell"),
]

CREDENTIAL_PATTERNS = [
    (r"cat\s+.*\.env\b", "reading .env file may expose secrets"),
    (r"cat\s+.*credentials", "reading credentials file"),
    (r"cat\s+.*\.pem\b", "reading private key file"),
    (r"cat\s+.*id_rsa", "reading SSH private key"),
    (r"echo\s+.*\$[A-Z_]*SECRET", "echoing secret environment variable"),
    (r"echo\s+.*\$[A-Z_]*PASSWORD", "echoing password environment variable"),
    (r"echo\s+.*\$[A-Z_]*TOKEN", "echoing token environment variable"),
    (r"echo\s+.*\$[A-Z_]*KEY", "echoing key environment variable"),
    (r"printenv\s+(SECRET|PASSWORD|TOKEN|KEY|AWS_)", "printing sensitive env var"),
    (r"env\s*\|", "dumping all environment variables"),
]

PRODUCTION_PATTERNS = [
    (r"(deploy|release)\s+.*(prod|production|live)", "deploying to production"),
    (r"migrate\s+.*(prod|production)", "running migration on production"),
    (r"kubectl\s+.*--context.*(prod|production)", "kubectl targeting production"),
    (r"aws\s+.*--profile\s+prod", "AWS command targeting production profile"),
    (r"terraform\s+(apply|destroy)(?!.*-target)", "terraform apply/destroy without target"),
]

PROTECTED_PATHS = [
    r"^/etc/",
    r"^/usr/",
    r"^/System/",
    r"\.env$",
    r"\.env\.local$",
    r"credentials\.json$",
    r"\.ssh/",
    r"settings\.json$",     # claude code settings
    r"settings\.local\.json$",
]


def check_bash(command: str) -> tuple[bool, str] | None:
    """Check a bash command against all safety rules. Returns (blocked, reason) or None."""
    command_lower = command.lower()

    for pattern, reason in DESTRUCTIVE_BASH_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return (True, f"[DESTRUCTIVE] {reason}\n  Command: {command[:100]}")

    for pattern, reason in CREDENTIAL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return (True, f"[CREDENTIAL RISK] {reason}\n  Command: {command[:100]}")

    for pattern, reason in PRODUCTION_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return (True, f"[PRODUCTION] {reason}\n  Command: {command[:100]}")

    return None


def check_file_write(file_path: str) -> tuple[bool, str] | None:
    """Check if a file write targets a protected path."""
    for pattern in PROTECTED_PATHS:
        if re.search(pattern, file_path):
            return (True, f"[PROTECTED PATH] Write to protected file blocked\n  Path: {file_path}")
    return None


def make_block_output(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    result = None

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        result = check_bash(command)

    elif tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        result = check_file_write(file_path)

    if result:
        blocked, reason = result
        if blocked:
            json.dump(make_block_output(reason), sys.stdout)
            sys.exit(2)

    # Pass through
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
