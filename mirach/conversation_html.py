"""Generate a styled HTML view of the latest conversation and open it in the browser.

Parses the Markdown conversation file, renders it as a chat-style HTML page
with dark theme, and opens it via xdg-open (Linux) or open (macOS). The
temporary file is placed in /tmp/ for automatic OS cleanup.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from mirach import config
from mirach.logging_setup import log

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mirach — Conversation</title>
<style>
  :root {{
    --bg: #1a1a2e;
    --surface: #16213e;
    --user: #0f3460;
    --assistant: #533483;
    --text: #e8e8e8;
    --muted: #a0a0b0;
    --accent: #e94560;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
    max-width: 800px;
    margin: 0 auto;
  }}
  h1 {{
    text-align: center;
    margin-bottom: 0.5rem;
    color: var(--accent);
    font-size: 1.5rem;
  }}
  .timestamp {{
    text-align: center;
    color: var(--muted);
    font-size: 0.85rem;
    margin-bottom: 2rem;
  }}
  .message {{
    padding: 1rem 1.25rem;
    border-radius: 12px;
    margin-bottom: 1rem;
    white-space: pre-wrap;
    word-wrap: break-word;
  }}
  .message.user {{
    background: var(--user);
    margin-left: 2rem;
  }}
  .message.assistant {{
    background: var(--assistant);
    margin-right: 2rem;
  }}
  .message .label {{
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.25rem;
  }}
  .separator {{
    text-align: center;
    color: var(--muted);
    margin: 1.5rem 0;
    font-size: 0.8rem;
  }}
</style>
</head>
<body>
<h1>Mirach — Latest Conversation</h1>
<p class="timestamp">{timestamp}</p>
{messages}
</body>
</html>"""


def _escape_html(text: str) -> str:
    """Escape special HTML characters to prevent injection."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _parse_conversation(path: Path) -> list[tuple[str, str]]:
    """Parse a Markdown conversation file into (role, content) pairs.

    Recognizes headers starting with '## ' as role separators. Lines containing
    'said' or 'user' map to the user role; everything else is assistant.
    """
    if not path.exists():
        return []

    messages: list[tuple[str, str]] = []
    current_role: str | None = None
    current_lines: list[str] = []

    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("## "):
                # Flush previous message
                if current_role is not None:
                    messages.append((current_role, "\n".join(current_lines).strip()))
                role = stripped[3:].strip().lower()
                current_role = "user" if "said" in role or "user" in role else "assistant"
                current_lines = []
            elif current_role is not None:
                current_lines.append(line.rstrip())

    # Flush last message
    if current_role is not None:
        messages.append((current_role, "\n".join(current_lines).strip()))

    return messages


def generate_and_open() -> str | None:
    """Generate HTML from latest.md and open it in the default browser.

    Returns the path to the generated HTML file, or None if no conversation exists.
    """
    latest = config.CONVERSATIONS_DIR / "latest.md"
    if not latest.exists():
        log.warning("No conversation file found")
        return None

    messages = _parse_conversation(latest)
    if not messages:
        log.warning("Conversation file is empty")
        return None

    # Build message HTML
    msg_html = ""
    for role, content in messages:
        label = "You" if role == "user" else "Mirach"
        escaped = _escape_html(content)
        msg_html += (
            f'<div class="message {role}">'
            f'<div class="label">{label}</div>'
            f"<div>{escaped}</div>"
            f"</div>\n"
        )

    # Render template
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest.stat().st_mtime))
    html = _HTML_TEMPLATE.format(timestamp=ts, messages=msg_html)

    # Write to temp file
    fd, path = tempfile.mkstemp(suffix=".html", prefix="mirach_conversation_")
    with open(fd, "w") as f:
        f.write(html)

    log.info("Conversation HTML generated: %s", path)

    # Open in browser
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", path])
    elif shutil.which("open"):
        subprocess.Popen(["open", path])
    else:
        log.warning("No browser opener available — file at %s", path)

    return path
