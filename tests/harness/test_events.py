"""Tests for ConversationBus and event serialization (mobile-readiness criteria)."""

from __future__ import annotations

import json
import threading

import pytest

from mirach.harness.events import (
    AwaitingConfirmationEvent,
    ConversationBus,
    CostEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)

# ── ConversationBus ──────────────────────────────────────────────────────────


class TestConversationBus:
    def test_single_subscriber_receives_event(self):
        bus = ConversationBus()
        received = []
        bus.subscribe(received.append)
        bus.publish(DoneEvent(content="hi"))
        assert len(received) == 1
        assert isinstance(received[0], DoneEvent)

    def test_multiple_subscribers_all_receive(self):
        bus = ConversationBus()
        r1, r2, r3 = [], [], []
        bus.subscribe(r1.append)
        bus.subscribe(r2.append)
        bus.subscribe(r3.append)
        bus.publish(TextDeltaEvent(delta="hello"))
        assert len(r1) == len(r2) == len(r3) == 1

    def test_unsubscribe_stops_delivery(self):
        bus = ConversationBus()
        received = []
        unsub = bus.subscribe(received.append)
        bus.publish(DoneEvent(content="a"))
        unsub()
        bus.publish(DoneEvent(content="b"))
        assert len(received) == 1

    def test_unsubscribe_is_idempotent(self):
        bus = ConversationBus()
        unsub = bus.subscribe(lambda e: None)
        unsub()
        unsub()  # second call must not raise

    def test_history_accumulates_in_order(self):
        bus = ConversationBus()
        bus.publish(TextDeltaEvent(delta="a"))
        bus.publish(DoneEvent(content="b"))
        h = bus.history()
        assert len(h) == 2
        assert isinstance(h[0], TextDeltaEvent)
        assert isinstance(h[1], DoneEvent)

    def test_history_returns_independent_copy(self):
        bus = ConversationBus()
        bus.publish(DoneEvent(content="x"))
        h = bus.history()
        h.clear()
        assert len(bus.history()) == 1

    def test_concurrent_publish_from_multiple_threads(self):
        """All events reach all subscribers regardless of which thread publishes."""
        bus = ConversationBus()
        received = []
        lock = threading.Lock()

        def safe_append(e):
            with lock:
                received.append(e)

        bus.subscribe(safe_append)

        threads = [
            threading.Thread(target=bus.publish, args=(TextDeltaEvent(delta=str(i)),))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 20


# ── Event serialization (mobile-readiness) ───────────────────────────────────


_SAMPLE_EVENTS = [
    TextDeltaEvent(delta="hello"),
    ToolCallEvent(id="1", name="bash", arguments={"cmd": "ls"}),
    ToolResultEvent(tool_call_id="1", result="file.txt"),
    ToolResultEvent(tool_call_id="2", result="oops", error=True),
    AwaitingConfirmationEvent(tool_call_id="3", name="bash", arguments={"cmd": "rm"}),
    DoneEvent(content="all done"),
    ErrorEvent(message="interrupted"),
    CostEvent(input_tokens=10, output_tokens=5),
]


class TestEventSerialization:
    @pytest.mark.parametrize("event", _SAMPLE_EVENTS)
    def test_to_dict_is_json_serializable(self, event):
        d = event.to_dict()
        serialized = json.dumps(d)  # raises TypeError if not serializable
        assert isinstance(serialized, str)

    @pytest.mark.parametrize("event", _SAMPLE_EVENTS)
    def test_to_dict_has_type_discriminator(self, event):
        d = event.to_dict()
        assert "type" in d
        assert isinstance(d["type"], str)

    @pytest.mark.parametrize("event", _SAMPLE_EVENTS)
    def test_to_dict_has_version_field(self, event):
        d = event.to_dict()
        assert "version" in d
        assert isinstance(d["version"], int)
        assert d["version"] >= 1

    def test_type_values_are_stable(self):
        assert TextDeltaEvent(delta="").type == "text_delta"
        assert ToolCallEvent(id="", name="", arguments={}).type == "tool_call"
        assert ToolResultEvent(tool_call_id="", result="").type == "tool_result"
        assert (
            AwaitingConfirmationEvent(tool_call_id="", name="", arguments={}).type
            == "awaiting_confirmation"
        )
        assert DoneEvent(content="").type == "done"
        assert ErrorEvent(message="").type == "error"
        assert CostEvent(input_tokens=0, output_tokens=0).type == "cost"
