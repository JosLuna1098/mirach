"""LLMResult, LLMBackend protocol, and _strip_markdown — no audio dependencies.

Kept separate from llm.py so the harness and its tests can import these types
without pulling in sounddevice / faster_whisper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class LLMResult:
    """Outcome of a single LLM query."""

    response: str
    new_session: bool
    interrupted: bool
    elapsed: float


@runtime_checkable
class LLMBackend(Protocol):
    """Structural protocol for LLM backends."""

    def query(self, text: str, system_prompt: str, obsidian_context: str = "") -> LLMResult: ...
    def interrupt(self) -> None: ...
    def session_expired(self) -> bool: ...
    def reset_session(self) -> None: ...


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting so TTS reads naturally."""
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"\|[-: ]+\|[-| :]*\n?", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
