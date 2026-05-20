"""Per-session conversation transcript written to human-readable Markdown.

Each session creates a new file with a timestamped name. A `latest.md`
symlink always points to the most recent conversation for quick access.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mirach import config
from mirach.logging_setup import log


class ConversationLog:
    """Manages conversation files: one Markdown per session plus a `latest.md` symlink."""

    def __init__(self) -> None:
        self.path: Path | None = None

    def start(self) -> Path:
        """Create a new conversation file with a timestamp header and update the latest symlink."""
        config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = config.CONVERSATIONS_DIR / f"conversation_{ts}.md"
        self.path.write_text(f"# Conversation {ts}\n\n")

        # Update the symlink to point to the new file
        link = config.CONVERSATIONS_DIR / "latest.md"
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(self.path.name)
        except OSError as e:
            log.warning("Could not create latest.md symlink: %s", e)
        return self.path

    def append(self, role: str, text: str) -> None:
        """Append a turn (role + text) to the current conversation file."""
        if self.path is None:
            return
        try:
            with open(self.path, "a") as f:
                ts = datetime.now().strftime("%H:%M:%S")
                f.write(f"**{role}** _({ts})_\n\n{text}\n\n---\n\n")
        except OSError as e:
            log.warning("Could not save turn: %s", e)
