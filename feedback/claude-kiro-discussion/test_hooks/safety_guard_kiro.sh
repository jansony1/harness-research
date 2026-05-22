#!/bin/bash
# Safety Guard hook adapted for Kiro CLI
# Kiro uses tool names: execute_bash, fs_write, fs_read (not Bash/Edit/Write)
# Kiro sends hook event via STDIN as JSON with tool_name and tool_input

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))")

if [ "$TOOL_NAME" = "shell" ] || [ "$TOOL_NAME" = "execute_bash" ] || [ "$TOOL_NAME" = "execute_cmd" ]; then
    COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))")
    
    # Check for destructive patterns
    if echo "$COMMAND" | grep -qiE "git\s+push\s+.*--force|git\s+push\s+.*-f\b"; then
        echo "[BLOCKED] force push can overwrite remote history. Command: $COMMAND" >&2
        exit 2
    fi
    if echo "$COMMAND" | grep -qiE "rm\s+-rf?\s+/[^t]|rm\s+-rf?\s+~|rm\s+-rf?\s+\.\s*$"; then
        echo "[BLOCKED] destructive filesystem operation. Command: $COMMAND" >&2
        exit 2
    fi
    if echo "$COMMAND" | grep -qiE "cat\s+.*\.env\b|cat\s+.*id_rsa"; then
        echo "[BLOCKED] credential exposure risk. Command: $COMMAND" >&2
        exit 2
    fi
fi

if [ "$TOOL_NAME" = "write" ] || [ "$TOOL_NAME" = "fs_write" ] || [ "$TOOL_NAME" = "fsWrite" ]; then
    FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); ti=d.get('tool_input',{}); print(ti.get('path','') or ti.get('file_path',''))")
    
    if echo "$FILE_PATH" | grep -qE "\.env$|\.env\.local$|credentials\.json$|\.ssh/|^/etc/"; then
        echo "[BLOCKED] write to protected path: $FILE_PATH" >&2
        exit 2
    fi
fi

exit 0
