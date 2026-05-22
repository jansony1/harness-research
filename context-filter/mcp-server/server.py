#!/usr/bin/env python3
"""
Context-Filtered Shell MCP Server

A platform-agnostic MCP server that wraps shell execution with output filtering.
Any MCP-compatible agent (Claude Code, Kiro, Cursor, etc.) can use this server
to get filtered tool results, reducing context window pollution.

Tools provided:
  - filtered_bash: Execute shell commands with automatic output filtering
  - filter_text: Apply filtering to arbitrary text (for post-processing)
"""

import json
import re
import subprocess
import sys
from typing import Any

# --- Configuration ---
BLOCKED_KEYWORDS = ["SECRET", "PASSWORD", "PRIVATE_KEY", "AWS_SECRET_ACCESS_KEY"]
MAX_OUTPUT_BYTES = 4000
MAX_LINES = 80
HEAD_LINES = 30
TAIL_LINES = 20
JSON_KEEP_FIELDS = [
    "status", "error", "error_message", "message", "code",
    "request_id", "id", "name", "state", "reason", "description",
]
COMMAND_TIMEOUT = 120


# --- Filters ---

def block_sensitive(text: str) -> str | None:
    for kw in BLOCKED_KEYWORDS:
        if kw in text:
            return f"[BLOCKED: output contained sensitive keyword '{kw}']"
    return None


def filter_log(text: str) -> str | None:
    lines = text.splitlines()
    log_re = re.compile(r"^\d{4}-\d{2}-\d{2}[T ].*?(INFO|DEBUG|WARN|ERROR|FATAL)")
    if sum(1 for l in lines if log_re.match(l)) < len(lines) * 0.5:
        return None

    important = []
    for i, line in enumerate(lines):
        if any(k in line for k in ["ERROR", "FATAL", "WARN", "Exception", "Traceback"]):
            start = max(0, i - 1)
            end = min(len(lines), i + 4)
            important.extend(lines[start:end])
            important.append("")

    if not important:
        return f"[LOG: {len(lines)} lines, all INFO/DEBUG, no errors]"

    seen = set()
    deduped = []
    for line in important:
        if line not in seen:
            seen.add(line)
            deduped.append(line)

    return f"[LOG: {len(lines)} total lines, filtered to errors/warnings]\n" + "\n".join(deduped)


def filter_test(text: str) -> str | None:
    lines = text.splitlines()
    if not any("✓" in l or "PASS" in l or "passing" in l for l in lines):
        return None
    if not any("✗" in l or "FAIL" in l or "failing" in l or "AssertionError" in l for l in lines):
        return None

    important = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if any(m in line for m in ["✗", "FAIL", "Error:", "AssertionError", "failing", "failed"]):
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

    pass_count = sum(1 for l in lines if "✓" in l or "PASS" in l.split())
    return f"[TESTS: {pass_count} passed, failures below]\n" + "\n".join(important)


def filter_json(text: str) -> str | None:
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return None
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

    if len(stripped) < MAX_OUTPUT_BYTES:
        return None

    if isinstance(data, dict):
        extracted = {k: v for k, v in data.items() if k in JSON_KEEP_FIELDS}
        omitted = [k for k in data.keys() if k not in JSON_KEEP_FIELDS]
        if extracted:
            suffix = f"{'...' if len(omitted) > 10 else ''}"
            header = f"[JSON: {len(stripped)} bytes, key fields extracted. Omitted: {', '.join(omitted[:10])}{suffix}]\n"
            return header + json.dumps(extracted, indent=2, ensure_ascii=False)

    if isinstance(data, list):
        sample = list(data[0].keys()) if data and isinstance(data[0], dict) else "N/A"
        return f"[JSON: array with {len(data)} items, {len(stripped)} bytes. First item keys: {sample}]"

    return None


def generic_truncate(text: str) -> str | None:
    lines = text.splitlines()
    byte_size = len(text.encode("utf-8"))
    if byte_size <= MAX_OUTPUT_BYTES and len(lines) <= MAX_LINES:
        return None

    head = lines[:HEAD_LINES]
    tail = lines[-TAIL_LINES:]
    omitted = len(lines) - HEAD_LINES - TAIL_LINES
    return (
        "\n".join(head)
        + f"\n\n[... {omitted} lines, {byte_size} bytes total — truncated ...]\n\n"
        + "\n".join(tail)
    )


def apply_filters(text: str) -> str:
    for f in [block_sensitive, filter_log, filter_test, filter_json, generic_truncate]:
        result = f(text)
        if result is not None:
            return result
    return text


# --- MCP Protocol (stdio JSON-RPC) ---

def send_response(id: Any, result: dict):
    msg = {"jsonrpc": "2.0", "id": id, "result": result}
    out = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(out)}\r\n\r\n{out}")
    sys.stdout.flush()


def send_error(id: Any, code: int, message: str):
    msg = {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
    out = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(out)}\r\n\r\n{out}")
    sys.stdout.flush()


def send_notification(method: str, params: dict):
    msg = {"jsonrpc": "2.0", "method": method, "params": params}
    out = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(out)}\r\n\r\n{out}")
    sys.stdout.flush()


def handle_initialize(id: Any, params: dict):
    send_response(id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": "context-filter",
            "version": "1.0.0",
        },
    })


def handle_tools_list(id: Any):
    send_response(id, {
        "tools": [
            {
                "name": "filtered_bash",
                "description": (
                    "Execute a shell command and return filtered output. "
                    "Automatically removes noise (verbose logs, large JSON, passing tests) "
                    "to preserve context window budget. Use this instead of raw shell execution "
                    "when output might be large or noisy."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default 120)",
                        },
                        "filter_mode": {
                            "type": "string",
                            "enum": ["auto", "log", "test", "json", "truncate", "none"],
                            "description": "Force a specific filter. Default 'auto' applies best match.",
                        },
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "filter_text",
                "description": (
                    "Apply context-reduction filters to arbitrary text. "
                    "Useful for post-processing output from other tools before including in context."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to filter",
                        },
                        "filter_mode": {
                            "type": "string",
                            "enum": ["auto", "log", "test", "json", "truncate"],
                            "description": "Filter to apply. Default 'auto'.",
                        },
                    },
                    "required": ["text"],
                },
            },
        ]
    })


def execute_bash(command: str, timeout: int = COMMAND_TIMEOUT) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"[TIMEOUT: command exceeded {timeout}s]", 124


def handle_tools_call(id: Any, params: dict):
    tool_name = params.get("name")
    args = params.get("arguments", {})

    if tool_name == "filtered_bash":
        command = args.get("command", "")
        timeout = args.get("timeout", COMMAND_TIMEOUT)
        mode = args.get("filter_mode", "auto")

        stdout, stderr, code = execute_bash(command, timeout)

        if mode == "none":
            filtered = stdout
        elif mode == "auto":
            filtered = apply_filters(stdout)
        else:
            filter_map = {
                "log": filter_log,
                "test": filter_test,
                "json": filter_json,
                "truncate": generic_truncate,
            }
            fn = filter_map.get(mode)
            filtered = fn(stdout) if fn else apply_filters(stdout)
            if filtered is None:
                filtered = stdout

        content_parts = []
        if filtered:
            content_parts.append({"type": "text", "text": filtered})
        if stderr:
            content_parts.append({"type": "text", "text": f"[stderr]: {stderr[:1000]}"})
        if code != 0:
            content_parts.append({"type": "text", "text": f"[exit code: {code}]"})
        if not content_parts:
            content_parts.append({"type": "text", "text": "(no output)"})

        send_response(id, {"content": content_parts, "isError": code != 0})

    elif tool_name == "filter_text":
        text = args.get("text", "")
        mode = args.get("filter_mode", "auto")

        if mode == "auto":
            filtered = apply_filters(text)
        else:
            filter_map = {
                "log": filter_log,
                "test": filter_test,
                "json": filter_json,
                "truncate": generic_truncate,
            }
            fn = filter_map.get(mode)
            filtered = fn(text) if fn else text
            if filtered is None:
                filtered = text

        send_response(id, {"content": [{"type": "text", "text": filtered}]})
    else:
        send_error(id, -32601, f"Unknown tool: {tool_name}")


def read_message() -> dict | None:
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if line == "":
            break
        if ":" in line:
            key, val = line.split(":", 1)
            headers[key.strip()] = val.strip()

    length = int(headers.get("Content-Length", 0))
    if length == 0:
        return None

    body = sys.stdin.read(length)
    return json.loads(body)


def main():
    while True:
        msg = read_message()
        if msg is None:
            break

        method = msg.get("method")
        id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            handle_initialize(id, params)
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            handle_tools_list(id)
        elif method == "tools/call":
            handle_tools_call(id, params)
        elif method == "shutdown":
            send_response(id, {})
            break
        elif id is not None:
            send_error(id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
