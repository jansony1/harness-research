#!/bin/bash
# Stop hook test for Kiro CLI
# Tests whether exit 2 on stop hook can block the agent from stopping
# Kiro docs say: stop hook exit 0 = succeeded, other = show STDERR warning
# No mention of exit 2 blocking stop

echo "[STOP GATE] Tests not run in this session. Please run tests before stopping." >&2
exit 2
