"""ContextManager — token-budget compaction strategies for AgentLoop._messages."""

from __future__ import annotations

from mirach.harness.providers.base import Message, Provider
from mirach.logging_setup import log


def count_tokens(messages: list[Message]) -> int:
    """Approximate token count for a list of messages.

    Uses tiktoken (cl100k_base) when available; falls back to chars/4 heuristic.
    Accurate enough for a compaction threshold — not billing-grade.
    """
    try:
        import tiktoken  # optional dep

        enc = tiktoken.get_encoding("cl100k_base")
        return sum(len(enc.encode(m.content or "")) for m in messages)
    except ImportError:
        return sum(len(m.content or "") // 4 + 1 for m in messages)


class ContextManager:
    """Token-budget compaction for a conversation message list.

    Strategies
    ----------
    none      Passes messages through unchanged (default — no behaviour change).
    sliding   Drops the oldest complete user/assistant/tool rounds from the front
              until the count falls under max_tokens.
    summarize Replaces the oldest prefix with an LLM-generated two-message summary
              pair (``role="user"`` marker + ``role="assistant"`` summary text), then
              appends the remaining recent tail.  The pair maintains strict
              user→assistant alternation so all models/providers accept it.
    """

    def __init__(self, strategy: str, max_tokens: int) -> None:
        self._strategy = strategy
        self._max_tokens = max_tokens

    # ── public ───────────────────────────────────────────────────────────────

    def compact_if_needed(
        self,
        messages: list[Message],
        provider: Provider,
    ) -> list[Message]:
        """Return compacted messages if the budget is exceeded, else unchanged."""
        if self._strategy == "none" or not messages:
            return messages
        if count_tokens(messages) <= self._max_tokens:
            return messages
        if self._strategy == "sliding":
            log.info("ContextManager: sliding compaction (budget=%d)", self._max_tokens)
            return self._slide(messages)
        if self._strategy == "summarize":
            log.info("ContextManager: summarize compaction (budget=%d)", self._max_tokens)
            return self._summarize(messages, provider)
        return messages  # unknown strategy → no-op

    # ── strategies ───────────────────────────────────────────────────────────

    def _slide(self, messages: list[Message]) -> list[Message]:
        """Drop the oldest complete conversation rounds until under budget.

        A "round" is one user message plus all following assistant/tool messages
        up to (but not including) the next user message.  We always drop whole
        rounds so the tail is still a valid conversation prefix.  Never drops
        the last round (when no second user message exists, we stop).
        """
        result = list(messages)
        while count_tokens(result) > self._max_tokens:
            # Find where the SECOND user message starts (that's the start of round 2).
            next_user = next(
                (i for i in range(1, len(result)) if result[i].role == "user"),
                None,
            )
            if next_user is None:
                # Only one round (or fewer) remaining — never drop the last round.
                break
            result = result[next_user:]
        return result

    def _summarize(self, messages: list[Message], provider: Provider) -> list[Message]:
        """Replace the oldest prefix with an LLM-generated summary pair."""
        split_at = self._find_split(messages)
        prefix = messages[:split_at]
        tail = messages[split_at:]

        if not prefix:
            # Nothing left to summarize — fall back to sliding.
            return self._slide(messages)

        summary_text = self._call_summarize(prefix, provider)
        summary_pair = [
            Message(
                role="user",
                content="[Earlier conversation summary — not a live message]",
            ),
            Message(role="assistant", content=summary_text),
        ]
        return summary_pair + tail

    # ── helpers ───────────────────────────────────────────────────────────────

    def _find_split(self, messages: list[Message]) -> int:
        """Return the index where prefix ends and the recent tail begins.

        We keep roughly the most recent half (by token heuristic) and ensure
        the split lands on a user-message boundary so the tail is a complete round.
        """
        target_keep = self._max_tokens // 2
        accumulated = 0
        for i in range(len(messages) - 1, 0, -1):  # stop at 1 so prefix is non-empty
            accumulated += len(messages[i].content or "") // 4 + 1
            if accumulated >= target_keep:
                # Found enough tokens for the tail.  Scan forward from i to
                # the nearest user-message boundary (j > 0) so the tail starts
                # at a clean round.
                for j in range(i, len(messages)):
                    if messages[j].role == "user" and j > 0:
                        return j
                break  # no clean boundary found after i
        return 0  # summarize the whole history (caller handles empty-prefix case)

    def _call_summarize(self, prefix: list[Message], provider: Provider) -> str:
        """Ask the provider to produce a compact summary of the prefix messages."""
        lines: list[str] = []
        for m in prefix:
            if m.role == "user":
                lines.append(f"User: {m.content}")
            elif m.role == "assistant":
                lines.append(f"Assistant: {m.content}")
            elif m.role == "tool":
                lines.append(f"Tool result: {m.content[:300]}")
        transcript = "\n".join(lines)

        request = [
            Message(
                role="user",
                content=(
                    "Summarize the following conversation concisely, capturing key facts, "
                    "decisions, and context so the assistant can continue without losing "
                    "important information:\n\n" + transcript
                ),
            )
        ]
        try:
            response = provider.send(request, [])
            text = response.content or "[Summary unavailable]"
            log.info("ContextManager: summary generated (%d chars)", len(text))
            return text
        except Exception as exc:
            log.warning("ContextManager: summary call failed: %s", exc)
            return "[Summary unavailable]"
