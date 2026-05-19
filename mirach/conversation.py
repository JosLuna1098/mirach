"""Per-session conversation transcript written to a human-readable markdown file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mirach import config
from mirach.logging_setup import log


class ConversationLog:
    """One markdown file per session, plus a `latest.md` symlink for quick access."""

    def __init__(self) -> None:
        self.path: Path | None = None

    def start(self) -> Path:
        config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = config.CONVERSATIONS_DIR / f"conversation_{ts}.md"
        self.path.write_text(f"# Conversation {ts}\n\n")

        link = config.CONVERSATIONS_DIR / "latest.md"
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(self.path.name)
        except OSError as e:
            log.warning("Could not create latest.md symlink: %s", e)
        return self.path

    def append(self, role: str, text: str) -> None:
        if self.path is None:
            return
        try:
            with open(self.path, "a") as f:
                ts = datetime.now().strftime("%H:%M:%S")
                f.write(f"**{role}** _({ts})_\n\n{text}\n\n---\n\n")
        except OSError as e:
            log.warning("Could not save turn: %s", e)
