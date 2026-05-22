#!/usr/bin/env python3
"""
Eval Gate — TaskCompleted/Stop hook that invokes a second LLM pass
to review the agent's work before allowing completion.

Unlike stop-gate (mechanical checks: tests ran? FIXME?), eval-gate
performs semantic review: is the logic correct? are there edge cases?

Trigger points:
- TaskCompleted: review before task is marked done
- Stop: review before session ends (if changes exist)

The reviewer is invoked via `claude --print` with a reviewer prompt.
If the reviewer doesn't say APPROVED, the task/stop is blocked.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# --- Configuration ---
REVIEWER_CMD = os.environ.get("EVAL_GATE_REVIEWER", "claude")
MAX_DIFF_CHARS = 8000
MAX_REVIEW_TIMEOUT = 60  # seconds
REQUIRE_APPROVAL_KEYWORD = "APPROVED"
SKIP_IF_NO_CHANGES = True
MAX_CONSECUTIVE_BLOCKS = 2  # don't loop forever

STATE_DIR = Path.home() / ".agent-harness" / "state"
STATE_FILE = STATE_DIR / "eval_gate.json"

REVIEWER_PROMPT = """You are a code reviewer. Review the following diff for:
1. Logic errors or bugs
2. Missing edge cases
3. Security issues
4. Obvious regressions

If the code is acceptable, respond with exactly: APPROVED
If there are issues, explain them concisely (max 3 bullet points).

Diff:
{diff}
"""


def load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            if time.time() - state.get("last_activity", 0) > 1800:
                return new_state()
            return state
        except (json.JSONDecodeError, KeyError):
            return new_state()
    return new_state()


def new_state() -> dict:
    return {
        "last_activity": time.time(),
        "consecutive_blocks": 0,
        "reviews_done": 0,
        "approvals": 0,
        "rejections": 0,
    }


def save_state(state: dict):
    state["last_activity"] = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_diff() -> str:
    """Get staged + unstaged changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout[:MAX_DIFF_CHARS]

        # Fallback: try staged only
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout[:MAX_DIFF_CHARS]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def invoke_reviewer(diff: str) -> tuple[bool, str]:
    """Call the reviewer LLM. Returns (approved, review_text)."""
    prompt = REVIEWER_PROMPT.format(diff=diff)

    try:
        result = subprocess.run(
            [REVIEWER_CMD, "--print", prompt],
            capture_output=True, text=True, timeout=MAX_REVIEW_TIMEOUT
        )
        review = result.stdout.strip()

        if not review:
            # Reviewer failed to respond — don't block
            return True, "(reviewer returned empty response, passing through)"

        approved = REQUIRE_APPROVAL_KEYWORD in review
        return approved, review

    except subprocess.TimeoutExpired:
        return True, "(reviewer timed out, passing through)"
    except FileNotFoundError:
        return True, f"(reviewer command '{REVIEWER_CMD}' not found, passing through)"


def make_block_output(review_text: str) -> dict:
    return {
        "decision": "block",
        "reason": (
            "EVAL GATE — Review did not pass:\n\n"
            f"{review_text}\n\n"
            "Please address the review feedback before completing."
        ),
    }


def main():
    input_data = json.load(sys.stdin)
    hook_event = input_data.get("hook_event_name", "")

    state = load_state()

    # Safety valve
    if state["consecutive_blocks"] >= MAX_CONSECUTIVE_BLOCKS:
        state["consecutive_blocks"] = 0
        save_state(state)
        json.dump({}, sys.stdout)
        return

    # Get diff
    diff = get_diff()

    if not diff and SKIP_IF_NO_CHANGES:
        state["consecutive_blocks"] = 0
        save_state(state)
        json.dump({}, sys.stdout)
        return

    # Invoke reviewer
    approved, review_text = invoke_reviewer(diff)
    state["reviews_done"] += 1

    if approved:
        state["approvals"] += 1
        state["consecutive_blocks"] = 0
        save_state(state)
        json.dump({}, sys.stdout)
    else:
        state["rejections"] += 1
        state["consecutive_blocks"] += 1
        save_state(state)
        json.dump(make_block_output(review_text), sys.stdout)
        sys.exit(2)


if __name__ == "__main__":
    main()
