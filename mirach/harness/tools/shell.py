"""bash tool — runs a shell command and returns stdout + stderr."""

from __future__ import annotations

import subprocess
from typing import Any

from mirach.harness.providers.base import ToolDef

BASH_DEF = ToolDef(
    name="bash",
    description=(
        "Run a shell command and return its output. "
        "Use for file listings, git operations, running scripts, etc."
    ),
    parameters={
        "type": "object",
        "required": ["command"],
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds (default 30).",
            },
        },
    },
)

_DEFAULT_TIMEOUT = 30


def bash(args: dict[str, Any]) -> str:
    command: str = args["command"]
    timeout: float = float(args.get("timeout", _DEFAULT_TIMEOUT))

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"[error] Command timed out after {timeout}s: {command}"

    output = result.stdout
    if result.returncode != 0:
        stderr = result.stderr.strip()
        suffix = f"\n[exit {result.returncode}]"
        if stderr:
            suffix += f" {stderr}"
        output = (output or "") + suffix

    return output.strip() or "(no output)"
