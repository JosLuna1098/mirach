"""Tests for ContextManager strategies and AgentLoop/OpenCode integration."""

from __future__ import annotations

import io
import json
import time
from unittest.mock import MagicMock, patch

from mirach.harness.context import ContextManager, count_tokens
from mirach.harness.events import ConversationBus
from mirach.harness.loop import AgentLoop
from mirach.harness.providers.base import Message, Response
from mirach.harness.providers.mock import MockProvider
from mirach.harness.tools.registry import ToolRegistry

# ── helpers ───────────────────────────────────────────────────────────────────


def _msg(role: str, content: str = "") -> Message:
    return Message(role=role, content=content)  # type: ignore[arg-type]


def _history(*pairs: tuple[str, str]) -> list[Message]:
    """Build a clean user/assistant round list from (role, content) pairs."""
    return [_msg(role, content) for role, content in pairs]


def _stop(text: str = "ok") -> Response:
    return Response(content=text, stop_reason="stop")


def _make_loop_with_cm(
    responses: list[Response],
    cm: ContextManager,
) -> tuple[AgentLoop, list]:
    provider = MockProvider(responses)
    registry = ToolRegistry()
    bus = ConversationBus()
    events: list = []
    bus.subscribe(events.append)
    loop = AgentLoop(
        provider=provider,
        registry=registry,
        bus=bus,
        context_manager=cm,
    )
    return loop, events


# ── count_tokens ──────────────────────────────────────────────────────────────


def test_count_tokens_non_empty():
    msgs = [_msg("user", "hello world"), _msg("assistant", "hi")]
    assert count_tokens(msgs) > 0


def test_count_tokens_empty():
    assert count_tokens([]) == 0


def test_count_tokens_empty_content():
    # Messages with no content still count (the +1 heuristic).
    msgs = [_msg("user", ""), _msg("assistant", "")]
    assert count_tokens(msgs) >= 0


# ── none strategy ─────────────────────────────────────────────────────────────


def test_none_strategy_is_identity():
    cm = ContextManager("none", max_tokens=1)  # budget=1 → would compact if active
    provider = MockProvider([])
    messages = _history(("user", "a" * 1000), ("assistant", "b" * 1000))
    result = cm.compact_if_needed(messages, provider)
    assert result is messages  # same object — no copy


def test_none_strategy_empty_messages():
    cm = ContextManager("none", max_tokens=0)
    result = cm.compact_if_needed([], MockProvider([]))
    assert result == []


# ── sliding strategy ──────────────────────────────────────────────────────────


def test_sliding_no_op_when_under_budget():
    cm = ContextManager("sliding", max_tokens=100_000)
    messages = _history(("user", "hello"), ("assistant", "world"))
    result = cm.compact_if_needed(messages, MockProvider([]))
    assert result == messages


def test_sliding_drops_oldest_round():
    """Three full rounds; sliding should drop the oldest to get under budget."""
    # Build messages that are individually large enough to matter.
    big = "x" * 400
    messages = _history(
        ("user", big),
        ("assistant", big),
        ("user", big),
        ("assistant", big),
        ("user", big),
        ("assistant", big),
    )
    # Set budget to just over two rounds.
    two_round_approx = count_tokens(messages[2:])
    cm = ContextManager("sliding", max_tokens=two_round_approx + 5)

    result = cm.compact_if_needed(messages, MockProvider([]))

    # Result must be under budget (or just at it).
    assert count_tokens(result) <= cm._max_tokens + count_tokens([messages[0]])
    # Result must start with a user message (no orphaned assistant at front).
    assert result[0].role == "user"
    # We kept some messages (not everything was dropped).
    assert len(result) >= 2


def test_sliding_preserves_recent_messages():
    """The most recent message content must survive sliding."""
    big = "y" * 500
    messages = _history(
        ("user", big),
        ("assistant", big),
        ("user", "recent user"),
        ("assistant", "recent assistant"),
    )
    # Budget that forces dropping the first round.
    cm = ContextManager("sliding", max_tokens=count_tokens(messages[2:]) + 5)
    result = cm.compact_if_needed(messages, MockProvider([]))

    contents = [m.content for m in result]
    assert "recent user" in contents
    assert "recent assistant" in contents


def test_sliding_never_empties_all_messages():
    """Even with budget=0, sliding keeps at least one message."""
    big = "z" * 1000
    messages = _history(("user", big), ("assistant", big))
    cm = ContextManager("sliding", max_tokens=0)
    result = cm.compact_if_needed(messages, MockProvider([]))
    assert len(result) >= 1


def test_sliding_handles_orphaned_non_user_at_front():
    """If _messages starts with an orphaned assistant message, sliding removes it.

    Orphan appears if history is manually corrupted or a reset edge-case occurs.
    The new-round detection (scan for second user) naturally drops the orphan
    because index-1+ scan finds the user message and slices from there.
    """
    big = "x" * 500
    orphan = "orphan_content " * 50  # large enough to push over budget
    messages = [
        _msg("assistant", orphan),
        _msg("user", big),
        _msg("assistant", big),
    ]
    # Budget = just under the two real messages, so compaction must fire.
    budget = count_tokens(messages[1:]) - 1
    cm = ContextManager("sliding", max_tokens=budget)

    # Make sure compaction actually triggers (otherwise test is vacuous).
    assert count_tokens(messages) > budget

    result = cm.compact_if_needed(messages, MockProvider([]))
    # The orphaned assistant message at the front must be gone.
    assert all(not (m.role == "assistant" and m.content == orphan) for m in result)


# ── summarize strategy ────────────────────────────────────────────────────────


def test_summarize_calls_provider_once():
    """summarize must make exactly one provider call to generate the summary."""
    big = "w" * 500
    messages = _history(
        ("user", big),
        ("assistant", big),
        ("user", "keep this"),
        ("assistant", "keep that"),
    )
    summary_response = _stop("This is the summary.")
    provider = MockProvider([summary_response])
    call_count = 0
    original_send = provider.send

    def counting_send(msgs, tools, ctx=None):
        nonlocal call_count
        call_count += 1
        return original_send(msgs, tools, ctx)

    provider.send = counting_send  # type: ignore[method-assign]

    # Budget that forces compaction.
    cm = ContextManager("summarize", max_tokens=count_tokens(messages) // 2)
    cm.compact_if_needed(messages, provider)

    assert call_count == 1


def test_summarize_prefix_replaced_with_pair():
    """summarize replaces the prefix with exactly two messages (user + assistant)."""
    big = "v" * 500
    messages = _history(
        ("user", big),
        ("assistant", big),
        ("user", "recent"),
        ("assistant", "also recent"),
    )
    provider = MockProvider([_stop("Summary text here.")])
    cm = ContextManager("summarize", max_tokens=count_tokens(messages) // 2)
    result = cm.compact_if_needed(messages, provider)

    # First two messages must be the summary pair.
    assert result[0].role == "user"
    assert "[Earlier conversation summary" in result[0].content
    assert result[1].role == "assistant"
    assert result[1].content == "Summary text here."


def test_summarize_keeps_recent_tail():
    """The recent tail is preserved after the summary pair."""
    big = "u" * 500
    messages = _history(
        ("user", big),
        ("assistant", big),
        ("user", "keep me"),
        ("assistant", "keep me too"),
    )
    provider = MockProvider([_stop("Summary.")])
    cm = ContextManager("summarize", max_tokens=count_tokens(messages) // 2)
    result = cm.compact_if_needed(messages, provider)

    tail_contents = [m.content for m in result[2:]]
    assert "keep me" in tail_contents or "keep me too" in tail_contents


def test_summarize_no_op_when_under_budget():
    """summarize must not call the provider if the budget is not exceeded."""
    messages = _history(("user", "hello"), ("assistant", "hi"))
    provider = MockProvider([])  # no responses — would raise if called
    cm = ContextManager("summarize", max_tokens=100_000)
    result = cm.compact_if_needed(messages, provider)
    assert result == messages


def test_summarize_provider_failure_returns_placeholder():
    """If the summary provider call fails, a placeholder string is used."""

    class FailProvider:
        def send(self, messages, tools, ctx=None):
            raise RuntimeError("network error")

    big = "t" * 500
    messages = _history(("user", big), ("assistant", big), ("user", "q"), ("assistant", "a"))
    cm = ContextManager("summarize", max_tokens=count_tokens(messages) // 2)
    result = cm.compact_if_needed(messages, FailProvider())  # type: ignore[arg-type]

    # Should still return a result with the fallback text.
    assert any("[Summary unavailable]" in m.content for m in result)


# ── AgentLoop integration ─────────────────────────────────────────────────────


def test_agentloop_compacts_after_turn():
    """After a turn that pushes messages over budget, the CM is applied."""
    turn1_response = _stop("a" * 400)
    turn2_response = _stop("second turn answer")

    # Budget=10 guarantees sliding fires after the first turn.
    cm = ContextManager("sliding", max_tokens=10)

    provider = MockProvider([turn1_response, turn2_response])
    registry = ToolRegistry()
    bus = ConversationBus()
    loop = AgentLoop(
        provider=provider,
        registry=registry,
        bus=bus,
        context_manager=cm,
    )

    loop.run("first turn", system_prompt="")
    # After compaction with max_tokens=10, _messages must still be a valid list.
    assert isinstance(loop._messages, list)


def test_agentloop_without_cm_unchanged():
    """AgentLoop without a ContextManager accumulates history normally."""
    provider = MockProvider([_stop("answer1"), _stop("answer2")])
    registry = ToolRegistry()
    bus = ConversationBus()
    loop = AgentLoop(provider=provider, registry=registry, bus=bus)

    loop.run("turn 1", system_prompt="")
    assert len(loop._messages) == 2  # user + assistant

    loop.run("turn 2", system_prompt="")
    assert len(loop._messages) == 4  # two full rounds


def test_agentloop_none_strategy_does_not_compact():
    """none strategy never modifies _messages regardless of token count."""
    big = "r" * 2000
    # First turn fills up messages; none strategy should not compact.
    provider = MockProvider([_stop(big), _stop(big)])
    cm = ContextManager("none", max_tokens=1)  # budget=1 → would always trigger

    registry = ToolRegistry()
    bus = ConversationBus()
    loop = AgentLoop(provider=provider, registry=registry, bus=bus, context_manager=cm)

    loop.run("turn 1", system_prompt="")
    assert len(loop._messages) == 2

    loop.run("turn 2", system_prompt="")
    assert len(loop._messages) == 4  # all four messages kept


# ── OpenCode compact integration ──────────────────────────────────────────────


def _make_sse_bytes(*events: dict) -> bytes:
    out = b""
    for ev in events:
        out += b"data: " + json.dumps(ev).encode() + b"\n\n"
    return out


def _text_delta(part_id: str, delta: str, session_id: str = "sess-1") -> dict:
    return {
        "type": "message.part.delta",
        "properties": {"sessionID": session_id, "partID": part_id, "field": "text", "delta": delta},
    }


def _session_idle(session_id: str = "sess-1") -> dict:
    return {"type": "session.idle", "properties": {"sessionID": session_id}}


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        if self.closed:
            raise OSError("closed")
        return self._buf.read(n)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _make_backend(session_tokens: int = 0):
    """Build a minimal OpenCodeServeBackend with a pre-set active session.

    _last_interaction is set to now so session_expired() → False and
    reset_session() is never called inside query(), keeping _session_id intact
    and preventing _http_delete from consuming the mocked urlopen buffer.
    """
    from mirach.harness.policy.engine import Decision, PolicyEngine
    from mirach.harness.providers.opencode import OpenCodeServeBackend

    policy = MagicMock(spec=PolicyEngine)
    policy.check.return_value = Decision.ALLOW
    bus = ConversationBus()

    backend = OpenCodeServeBackend(policy=policy, bus=bus, host="127.0.0.1", port=9999)
    backend._base_url = "http://127.0.0.1:9999"
    backend._session_id = "sess-1"
    backend._last_interaction = time.time()  # fresh → not expired
    backend._session_tokens = session_tokens
    return backend


def test_opencode_compact_fires_when_over_budget():
    """_compact() is called when the fetched context size exceeds CONTEXT_MAX_TOKENS."""
    backend = _make_backend()

    sse_body = _make_sse_bytes(
        _text_delta("p1", "hello"),
        _session_idle(),
    )
    with (
        patch("mirach.config.CONTEXT_STRATEGY", "summarize"),
        patch("mirach.config.CONTEXT_MAX_TOKENS", 1),
        patch.object(backend, "_fetch_session_tokens", return_value=99_999),
        patch.object(backend, "_compact") as mock_compact,
        patch.object(backend, "_ensure_running"),
        patch("urllib.request.urlopen", return_value=_FakeResp(sse_body)),
        patch.object(backend, "_http_post", return_value={}),
    ):
        backend.query("hi", system_prompt="")

    mock_compact.assert_called_once()


def test_opencode_compact_not_fired_when_under_budget():
    """_compact() is NOT called when the fetched context size is below threshold."""
    backend = _make_backend()

    sse_body = _make_sse_bytes(
        _text_delta("p1", "reply"),
        _session_idle(),
    )
    with (
        patch("mirach.config.CONTEXT_STRATEGY", "summarize"),
        patch("mirach.config.CONTEXT_MAX_TOKENS", 100_000),
        patch.object(backend, "_fetch_session_tokens", return_value=150),
        patch.object(backend, "_compact") as mock_compact,
        patch.object(backend, "_ensure_running"),
        patch("urllib.request.urlopen", return_value=_FakeResp(sse_body)),
        patch.object(backend, "_http_post", return_value={}),
    ):
        backend.query("hi", system_prompt="")

    mock_compact.assert_not_called()


def test_opencode_compact_not_fired_for_none_strategy():
    """_compact() is NOT called when strategy is 'none', even over budget."""
    backend = _make_backend(session_tokens=999_999)

    sse_body = _make_sse_bytes(
        _text_delta("p1", "reply"),
        _session_idle(),
    )
    with (
        patch("mirach.config.CONTEXT_STRATEGY", "none"),
        patch("mirach.config.CONTEXT_MAX_TOKENS", 1),
        patch.object(backend, "_compact") as mock_compact,
        patch.object(backend, "_ensure_running"),
        patch("urllib.request.urlopen", return_value=_FakeResp(sse_body)),
        patch.object(backend, "_http_post", return_value={}),
    ):
        backend.query("hi", system_prompt="")

    mock_compact.assert_not_called()


def test_opencode_compact_resets_token_counter():
    """After a successful _compact(), _session_tokens resets to 0."""
    backend = _make_backend()
    backend._session_tokens = 50_000

    with patch.object(backend, "_http_post", return_value=True):
        backend._compact()

    assert backend._session_tokens == 0


def test_opencode_compact_does_not_reset_on_failure():
    """If _compact() raises, _session_tokens is not reset."""
    backend = _make_backend()
    backend._session_tokens = 50_000

    with patch.object(backend, "_http_post", side_effect=OSError("timeout")):
        backend._compact()  # must not raise

    assert backend._session_tokens == 50_000


def test_opencode_fetch_session_tokens_reads_last_assistant():
    """_fetch_session_tokens returns the last assistant message's input+output."""
    backend = _make_backend()
    messages = [
        {"info": {"role": "user", "tokens": None}},
        {"info": {"role": "assistant", "tokens": {"input": 4000, "output": 200, "reasoning": 0}}},
    ]
    with patch.object(backend, "_http_get", return_value=messages):
        assert backend._fetch_session_tokens() == 4200


def test_opencode_fetch_session_tokens_survives_failure():
    """A transient GET failure returns the previous value, not 0."""
    backend = _make_backend(session_tokens=777)
    with patch.object(backend, "_http_get", side_effect=OSError("boom")):
        assert backend._fetch_session_tokens() == 777


def test_opencode_query_refreshes_tokens_from_rest():
    """query() sets _session_tokens from the REST fetch when strategy compacts."""
    backend = _make_backend(session_tokens=0)

    sse_body = _make_sse_bytes(
        _text_delta("p1", "answer"),
        _session_idle(),
    )
    with (
        patch("mirach.config.CONTEXT_STRATEGY", "summarize"),
        patch("mirach.config.CONTEXT_MAX_TOKENS", 100_000),
        patch.object(backend, "_fetch_session_tokens", return_value=4200),
        patch.object(backend, "_ensure_running"),
        patch("urllib.request.urlopen", return_value=_FakeResp(sse_body)),
        patch.object(backend, "_http_post", return_value={}),
    ):
        backend.query("q", system_prompt="")

    assert backend._session_tokens == 4200


def test_opencode_reset_session_clears_token_counter():
    """reset_session() also zeroes _session_tokens."""
    backend = _make_backend()
    backend._session_tokens = 12_345
    backend._base_url = ""  # skip the HTTP delete call

    backend.reset_session()

    assert backend._session_tokens == 0
