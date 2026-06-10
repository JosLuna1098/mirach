"""MockProvider — pre-programmed responses; zero tokens, no network."""

from __future__ import annotations

from collections.abc import Iterator

from mirach.harness.providers.base import Message, Response, ToolDef


class MockProvider:
    """Iterates through a list of pre-programmed Responses. Raises StopIteration when exhausted."""

    def __init__(self, responses: list[Response]) -> None:
        self._iter: Iterator[Response] = iter(responses)

    def send(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        ctx: dict[str, None] | None = None,
    ) -> Response:
        return next(self._iter)
