"""
Platform adapter — shared by all harness modules.

Usage:
    from shared.adapter import is_bash_tool, is_write_tool, is_read_tool, get_stdout, get_exit_code

Set platform via environment variable:
    export HARNESS_PLATFORM=kiro    # or claude_code (default)
"""

import os

PLATFORM = os.environ.get("HARNESS_PLATFORM", "claude_code")

TOOL_MAP = {
    "claude_code": {
        "bash": ["Bash"],
        "write": ["Edit", "Write"],
        "read": ["Read"],
    },
    "kiro": {
        "bash": ["shell", "execute_bash", "execute_cmd"],
        "write": ["fs_write", "write", "write_file"],
        "read": ["fs_read", "read", "read_file"],
    },
    "cursor": {
        "bash": ["terminal", "run_command"],
        "write": ["edit_file", "write_file"],
        "read": ["read_file"],
    },
}

RESPONSE_MAP = {
    "claude_code": {"stdout": "stdout", "stderr": "stderr", "exit_code": "exitCode"},
    "kiro": {"stdout": "stdout", "stderr": "stderr", "exit_code": "exitCode"},
    "cursor": {"stdout": "output", "stderr": "error", "exit_code": "exit_code"},
}


def _get_tools(category: str) -> list[str]:
    return TOOL_MAP.get(PLATFORM, TOOL_MAP["claude_code"]).get(category, [])


def is_bash_tool(tool_name: str) -> bool:
    return tool_name in _get_tools("bash")


def is_write_tool(tool_name: str) -> bool:
    return tool_name in _get_tools("write")


def is_read_tool(tool_name: str) -> bool:
    return tool_name in _get_tools("read")


def get_stdout(tool_response: dict) -> str:
    field = RESPONSE_MAP.get(PLATFORM, RESPONSE_MAP["claude_code"])["stdout"]
    return tool_response.get(field, "")


def get_stderr(tool_response: dict) -> str:
    field = RESPONSE_MAP.get(PLATFORM, RESPONSE_MAP["claude_code"])["stderr"]
    return tool_response.get(field, "")


def get_exit_code(tool_response: dict) -> int:
    field = RESPONSE_MAP.get(PLATFORM, RESPONSE_MAP["claude_code"])["exit_code"]
    return tool_response.get(field, 0)
