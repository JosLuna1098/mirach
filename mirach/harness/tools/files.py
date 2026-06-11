"""File tools: read_file, write_file, edit_file, search."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mirach.harness.providers.base import ToolDef

# Maximum bytes to return from read_file before truncating.
_READ_LIMIT = 64_000  # ~64 KB, enough for most source files

READ_FILE_DEF = ToolDef(
    name="read_file",
    description="Read the contents of a file. Returns up to 64 KB.",
    parameters={
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path."},
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-based).",
            },
            "limit": {"type": "integer", "description": "Maximum number of lines to return."},
        },
    },
)

WRITE_FILE_DEF = ToolDef(
    name="write_file",
    description="Write content to a file, creating it if it does not exist.",
    parameters={
        "type": "object",
        "required": ["path", "content"],
        "properties": {
            "path": {"type": "string", "description": "File path to write."},
            "content": {"type": "string", "description": "Content to write."},
        },
    },
)

EDIT_FILE_DEF = ToolDef(
    name="edit_file",
    description=(
        "Replace an exact string in a file. old_string must appear exactly once in the file."
    ),
    parameters={
        "type": "object",
        "required": ["path", "old_string", "new_string"],
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string", "description": "Exact text to replace."},
            "new_string": {"type": "string", "description": "Replacement text."},
        },
    },
)

SEARCH_DEF = ToolDef(
    name="search",
    description=(
        "Search for files by name pattern (glob) or text content (grep/ripgrep). "
        "Returns matching file paths or lines."
    ),
    parameters={
        "type": "object",
        "required": ["pattern"],
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern for filenames (e.g. '**/*.py') or text to grep.",
            },
            "directory": {
                "type": "string",
                "description": "Directory to search (default: current working dir).",
            },
            "type": {
                "type": "string",
                "enum": ["glob", "grep"],
                "description": "'glob' searches filenames, 'grep' searches file contents (default: glob).",
            },
        },
    },
)


# ── implementations ───────────────────────────────────────────────────────────


def read_file(args: dict[str, Any]) -> str:
    path = Path(args["path"]).expanduser()
    if not path.exists():
        return f"[error] File not found: {path}"
    if not path.is_file():
        return f"[error] Not a file: {path}"

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return f"[error] Cannot read {path}: {exc}"

    text = raw[:_READ_LIMIT].decode(errors="replace")
    truncated = len(raw) > _READ_LIMIT

    offset: int = max(0, int(args.get("offset", 1)) - 1)  # convert to 0-based
    limit: int | None = args.get("limit")

    lines = text.splitlines(keepends=True)
    lines = lines[offset:]
    if limit:
        lines = lines[: int(limit)]

    result = "".join(lines)
    if truncated:
        result += f"\n[truncated — file is {len(raw)} bytes, showing first {_READ_LIMIT}]"
    return result or "(empty file)"


def write_file(args: dict[str, Any]) -> str:
    path = Path(args["path"]).expanduser()
    content: str = args["content"]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"[error] Cannot write {path}: {exc}"
    return f"Written {len(content)} bytes to {path}"


def edit_file(args: dict[str, Any]) -> str:
    path = Path(args["path"]).expanduser()
    old: str = args["old_string"]
    new: str = args["new_string"]

    if not path.exists():
        return f"[error] File not found: {path}"

    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"[error] Cannot read {path}: {exc}"

    count = original.count(old)
    if count == 0:
        return f"[error] old_string not found in {path}"
    if count > 1:
        return f"[error] old_string appears {count} times in {path} — must be unique"

    updated = original.replace(old, new, 1)
    try:
        path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return f"[error] Cannot write {path}: {exc}"
    return f"Edited {path} — replaced 1 occurrence"


def search(args: dict[str, Any]) -> str:
    pattern: str = args["pattern"]
    directory: str = args.get("directory", ".")
    search_type: str = args.get("type", "glob")
    base = Path(directory).expanduser()

    if search_type == "glob":
        try:
            matches = sorted(str(p) for p in base.rglob(pattern) if p.is_file())
        except (OSError, ValueError) as exc:
            return f"[error] {exc}"
        if not matches:
            return "(no matches)"
        return "\n".join(matches[:200])  # cap at 200 results

    # grep mode — prefer ripgrep, fall back to grep
    for rg_cmd in (
        ["rg", "--line-number", pattern, str(base)],
        ["grep", "-rn", pattern, str(base)],
    ):
        try:
            result = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=30)
            output = result.stdout.strip()
            return output or "(no matches)"
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return "[error] Search timed out"

    return "[error] Neither ripgrep nor grep is available"
