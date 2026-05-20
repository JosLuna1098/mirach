"""Obsidian vault cache for persistent LLM memory.

Reads designated vault files (conocimiento.md, recordatorios.md, preferencias.md)
once per session and keeps their contents in RAM. This avoids redundant disk I/O
on every LLM turn and provides context for session bootstrap.
"""

from __future__ import annotations

import time
from pathlib import Path

from mirach.logging_setup import log

# Vault files that contain persistent memory. Loaded at session start.
MEMORY_FILES = [
    "conocimiento.md",  # Persistent instructions and rules
    "recordatorios.md",  # Pending tasks and reminders
    "preferencias.md",  # User preferences and habits
]


class ObsidianCache:
    """In-memory cache for Obsidian vault memory files.

    Files are read once per session via refresh() and served as formatted
    context text via get_context(). The cache can be checked for staleness.
    """

    def __init__(self, vault_path: str | Path) -> None:
        self._vault = Path(vault_path)
        self._cache: dict[str, str] = {}
        self._loaded_at: float = 0.0

    def refresh(self) -> None:
        """Read all memory files from disk into the cache, replacing previous contents."""
        t0 = time.time()
        new_cache: dict[str, str] = {}
        for filename in MEMORY_FILES:
            target = self._vault / filename
            if target.exists():
                content = target.read_text().strip()
                if content:
                    new_cache[filename] = content
        self._cache = new_cache
        self._loaded_at = time.time()
        log.info(
            "Obsidian cache refreshed (%d files, %.2fs)",
            len(self._cache),
            time.time() - t0,
        )

    def get_context(self) -> str:
        """Return a formatted context string for LLM injection.

        Each file is wrapped under a '## Filename' header. Returns empty
        string if the cache has no files.
        """
        if not self._cache:
            return ""

        parts = []
        for filename in MEMORY_FILES:
            content = self._cache.get(filename)
            if content:
                label = filename.replace(".md", "").capitalize()
                parts.append(f"## {label}\n{content}")

        return "\n\n".join(parts)

    def is_stale(self, max_age: float = 300.0) -> bool:
        """Check if the cache is older than max_age seconds."""
        if self._loaded_at == 0.0:
            return True
        return (time.time() - self._loaded_at) > max_age

    @property
    def is_loaded(self) -> bool:
        """True if the cache contains at least one file."""
        return bool(self._cache)
