"""Obsidian vault cache for persistent memory.

Reads vault files once per session and keeps them in RAM,
avoiding redundant disk I/O on every LLM turn.
"""

from __future__ import annotations

import time
from pathlib import Path

from mirach.logging_setup import log

MEMORY_FILES = [
    "conocimiento.md",
    "recordatorios.md",
    "preferencias.md",
]


class ObsidianCache:
    """Cache for Obsidian vault memory files."""

    def __init__(self, vault_path: str | Path) -> None:
        self._vault = Path(vault_path)
        self._cache: dict[str, str] = {}
        self._loaded_at: float = 0.0

    def refresh(self) -> None:
        """Read all memory files from disk into the cache."""
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

        Returns empty string if cache is empty.
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
        """Check if cache is older than max_age seconds."""
        if self._loaded_at == 0.0:
            return True
        return (time.time() - self._loaded_at) > max_age

    @property
    def is_loaded(self) -> bool:
        return bool(self._cache)
