#!/bin/bash
# Install agent-board hooks into the current project's Claude Code settings.
# Usage: bash install.sh [agent-name]
#
# This adds PostToolUse/PostToolBatch/Stop hooks that auto-report to the board.

BOARD_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_NAME="${1:-Claude}"
SETTINGS_DIR=".claude"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

echo "⚔️  Agent Board Installer"
echo "   Board dir: $BOARD_DIR"
echo "   Agent name: $AGENT_NAME"
echo ""

# Create .claude dir if needed
mkdir -p "$SETTINGS_DIR"

# Build hook command
HOOK_CMD="AGENT_BOARD_NAME=$AGENT_NAME AGENT_BOARD_STATE=$BOARD_DIR/state.json python3 $BOARD_DIR/hooks/board_hook.py"

# Check if settings exists
if [ -f "$SETTINGS_FILE" ]; then
    echo "⚠️  $SETTINGS_FILE already exists."
    echo "   Add these hooks manually:"
    echo ""
    echo "   \"PostToolUse\": [{\"matcher\": \"\", \"hooks\": [{\"type\": \"command\", \"command\": \"$HOOK_CMD\"}]}]"
    echo "   \"PostToolBatch\": [{\"hooks\": [{\"type\": \"command\", \"command\": \"$HOOK_CMD\"}]}]"
    echo "   \"Stop\": [{\"hooks\": [{\"type\": \"command\", \"command\": \"$HOOK_CMD\"}]}]"
else
    cat > "$SETTINGS_FILE" << EOF
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "$HOOK_CMD"}]
      }
    ],
    "PostToolBatch": [
      {
        "hooks": [{"type": "command", "command": "$HOOK_CMD"}]
      }
    ],
    "Stop": [
      {
        "hooks": [{"type": "command", "command": "$HOOK_CMD"}]
      }
    ]
  }
}
EOF
    echo "✅ Created $SETTINGS_FILE with board hooks"
fi

echo ""
echo "To start the board UI:"
echo "   python3 $BOARD_DIR/server.py"
echo "   open http://localhost:8420"
