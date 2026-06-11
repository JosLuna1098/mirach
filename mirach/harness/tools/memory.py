"""Memory tools: remember / recall backed by the existing ObsidianCache vault."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mirach.harness.providers.base import ToolDef

REMEMBER_DEF = ToolDef(
    name="remember",
    description=(
        "Store a piece of information persistently in the Obsidian vault "
        "(recordatorios.md). Use for tasks, reminders, and notes."
    ),
    parameters={
        "type": "object",
        "required": ["content"],
        "properties": {
            "content": {"type": "string", "description": "The information to remember."},
            "file": {
                "type": "string",
                "description": (
                    "Vault file to append to: 'recordatorios', 'conocimiento', "
                    "or 'preferencias'. Default: 'recordatorios'."
                ),
            },
        },
    },
)

RECALL_DEF = ToolDef(
    name="recall",
    description=(
        "Search the Obsidian vault memory for information matching a query. "
        "Returns relevant lines from all memory files."
    ),
    parameters={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords or phrase to search for.",
            },
        },
    },
)

_VALID_FILES = {"recordatorios", "conocimiento", "preferencias"}
_DEFAULT_FILE = "recordatorios"


def make_remember(vault_path: Path):
    """Return a remember() fn bound to the given vault directory."""

    def remember(args: dict[str, Any]) -> str:
        content: str = args["content"].strip()
        file_key: str = args.get("file", _DEFAULT_FILE)
        if file_key not in _VALID_FILES:
            return f"[error] Unknown memory file {file_key!r}. Choose from: {', '.join(sorted(_VALID_FILES))}"

        target = vault_path / f"{file_key}.md"
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        entry = f"\n- [{timestamp}] {content}"

        try:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(entry)
        except OSError as exc:
            return f"[error] Cannot write to vault: {exc}"

        return f"Remembered in {file_key}.md"

    return remember


def make_recall(vault_path: Path):
    """Return a recall() fn that searches the vault directory."""

    def recall(args: dict[str, Any]) -> str:
        query: str = args["query"].lower()
        results: list[str] = []

        for file_key in sorted(_VALID_FILES):
            target = vault_path / f"{file_key}.md"
            if not target.exists():
                continue
            try:
                lines = target.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                if query in line.lower():
                    results.append(f"[{file_key}] {line.strip()}")

        if not results:
            return f"No memory found matching: {query!r}"
        return "\n".join(results)

    return recall
