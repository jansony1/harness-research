#!/usr/bin/env python3
"""
Input Modifier adapted for Kiro CLI.
Tests whether Kiro supports updatedInput in PreToolUse hook output.

Kiro hook protocol:
- STDIN: JSON with hook_event_name, tool_name, tool_input
- STDOUT: captured but not shown to user (exit 0)
- STDERR + exit 2: block tool execution
- Question: Does Kiro support reading STDOUT JSON with updatedInput to modify params?
"""
import json
import re
import sys

input_data = json.load(sys.stdin)
tool_name = input_data.get("tool_name", "")
tool_input = input_data.get("tool_input", {})

if tool_name in ("shell", "execute_bash", "execute_cmd"):
    command = tool_input.get("command", "")
    
    # git push → git push --dry-run
    if re.search(r"git\s+push\b", command) and "--dry-run" not in command and "--force" not in command:
        modified = re.sub(r"(git\s+push)", r"\1 --dry-run", command)
        # Try Claude Code style output (updatedInput)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {"command": modified},
                "additionalContext": "[Input Modified] Added --dry-run to preview push",
            }
        }
        json.dump(output, sys.stdout)
        sys.exit(0)

# Pass through
json.dump({}, sys.stdout)
