#!/usr/bin/env python3
"""
PostToolUse hook: filter/truncate tool output to reduce context pollution.

Strategies:
1. Sensitive keyword blocking
2. Log output: only keep ERROR/WARN + summary
3. Test output: only keep failures + summary
4. JSON output: extract key fields if too large
5. Generic: head/tail truncation for oversized output
"""
import json
import re
import sys

# --- Configuration ---
BLOCKED_KEYWORDS = ["SECRET", "PASSWORD", "PRIVATE_KEY"]
MAX_OUTPUT_BYTES = 4000  # ~1000 tokens
MAX_LINES = 80
HEAD_LINES = 30
TAIL_LINES = 20

# JSON fields to keep when truncating large JSON responses
JSON_KEEP_FIELDS = ["status", "error", "error_message", "message", "code", "request_id", "id", "name"]


def block_sensitive(stdout: str) -> str | None:
    for keyword in BLOCKED_KEYWORDS:
        if keyword in stdout:
            return f"[BLOCKED: output contained sensitive keyword '{keyword}']"
    return None


def filter_log_output(stdout: str) -> str | None:
    """If output looks like application logs, keep only ERROR/WARN + context."""
    lines = stdout.splitlines()
    log_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}[T ].*?(INFO|DEBUG|WARN|ERROR|FATAL)")

    log_lines = [l for l in lines if log_pattern.match(l)]
    if len(log_lines) < len(lines) * 0.5:
        return None  # doesn't look like logs

    important = []
    for i, line in enumerate(lines):
        if any(level in line for level in ["ERROR", "FATAL", "WARN", "Exception", "Traceback"]):
            # include context: 1 line before, 3 lines after
            start = max(0, i - 1)
            end = min(len(lines), i + 4)
            important.extend(lines[start:end])
            important.append("")

    if not important:
        return f"[LOG: {len(lines)} lines, all INFO/DEBUG, no errors detected]"

    # deduplicate while preserving order
    seen = set()
    deduped = []
    for line in important:
        if line not in seen:
            seen.add(line)
            deduped.append(line)

    header = f"[LOG: {len(lines)} total lines, filtered to errors/warnings only]\n"
    return header + "\n".join(deduped)


def filter_test_output(stdout: str) -> str | None:
    """If output looks like test results, keep only failures + summary."""
    lines = stdout.splitlines()

    has_pass = any("✓" in l or "PASS" in l or "passing" in l for l in lines)
    has_fail = any("✗" in l or "FAIL" in l or "failing" in l or "AssertionError" in l for l in lines)

    if not (has_pass or has_fail):
        return None

    important = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if any(marker in line for marker in ["✗", "FAIL", "Error:", "AssertionError", "failing", "passed", "failed"]):
            # grab failure block: up to next empty line or next test
            important.append(line)
            i += 1
            while i < len(lines) and lines[i].strip() and "✓" not in lines[i]:
                important.append(lines[i])
                i += 1
            important.append("")
        else:
            i += 1

    if not important:
        return None

    # count passes
    pass_count = sum(1 for l in lines if "✓" in l or "PASS" in l.split())
    header = f"[TESTS: {pass_count} passed, failures shown below]\n"
    return header + "\n".join(important)


def filter_json_output(stdout: str) -> str | None:
    """If output is large JSON, extract only important fields."""
    stripped = stdout.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return None

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

    if len(stripped) < MAX_OUTPUT_BYTES:
        return None  # small enough, pass through

    if isinstance(data, dict):
        extracted = {k: v for k, v in data.items() if k in JSON_KEEP_FIELDS}
        omitted_keys = [k for k in data.keys() if k not in JSON_KEEP_FIELDS]
        if extracted:
            header = f"[JSON: {len(stripped)} bytes, extracted key fields. Omitted: {', '.join(omitted_keys[:10])}{'...' if len(omitted_keys) > 10 else ''}]\n"
            return header + json.dumps(extracted, indent=2, ensure_ascii=False)

    # fallback: just report structure
    if isinstance(data, list):
        return f"[JSON: array with {len(data)} items, {len(stripped)} bytes total. First item keys: {list(data[0].keys()) if data and isinstance(data[0], dict) else 'N/A'}]"

    return None


def generic_truncate(stdout: str) -> str | None:
    """Last resort: head + tail truncation."""
    lines = stdout.splitlines()
    byte_size = len(stdout.encode("utf-8"))

    if byte_size <= MAX_OUTPUT_BYTES and len(lines) <= MAX_LINES:
        return None  # small enough

    head = lines[:HEAD_LINES]
    tail = lines[-TAIL_LINES:]
    omitted = len(lines) - HEAD_LINES - TAIL_LINES

    return "\n".join(head) + f"\n\n[... {omitted} lines, {byte_size} bytes total — truncated ...]\n\n" + "\n".join(tail)


def make_output(new_stdout: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": {
                "stdout": new_stdout,
                "stderr": "",
                "interrupted": False,
                "isImage": False,
            },
        }
    }


def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_response = input_data.get("tool_response", {})

    if tool_name != "Bash":
        json.dump({}, sys.stdout)
        return

    stdout = tool_response.get("stdout", "")
    if not stdout:
        json.dump({}, sys.stdout)
        return

    # Pipeline: first match wins
    filters = [
        block_sensitive,
        filter_log_output,
        filter_test_output,
        filter_json_output,
        generic_truncate,
    ]

    for f in filters:
        result = f(stdout)
        if result is not None:
            json.dump(make_output(result), sys.stdout)
            return

    # pass through unchanged
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
