"""Tests for gateway.diagnostics."""
import pytest
from gateway.diagnostics import (
    emit, on_event, get_recent, get_status_summary,
    emit_message, emit_usage, emit_loop,
    MessageEvent, UsageEvent, LoopEvent, DiagnosticEvent,
    _listeners, _recent,
)


class TestEventBus:
    def setup_method(self):
        _listeners.clear()
        _recent.clear()

    def test_emit_and_receive(self):
        received = []
        on_event(lambda e: received.append(e))
        emit(DiagnosticEvent(type="test"))
        assert len(received) == 1
        assert received[0].type == "test"

    def test_sequence_numbers(self):
        events = []
        on_event(lambda e: events.append(e))
        emit(DiagnosticEvent(type="a"))
        emit(DiagnosticEvent(type="b"))
        assert events[1].seq > events[0].seq

    def test_unsubscribe(self):
        received = []
        unsub = on_event(lambda e: received.append(e))
        emit(DiagnosticEvent(type="a"))
        unsub()
        emit(DiagnosticEvent(type="b"))
        assert len(received) == 1

    def test_get_recent(self):
        _recent.clear()
        for i in range(10):
            emit(DiagnosticEvent(type=f"t{i}"))
        recent = get_recent(5)
        assert len(recent) == 5

    def test_get_recent_filtered(self):
        _recent.clear()
        emit(MessageEvent(phase="completed"))
        emit(UsageEvent(model="sonnet"))
        emit(MessageEvent(phase="queued"))
        recent = get_recent(10, event_type="message")
        assert len(recent) == 2

    def test_listener_error_ignored(self):
        def bad_listener(e):
            raise ValueError("boom")
        on_event(bad_listener)
        # Should not raise
        emit(DiagnosticEvent(type="test"))


class TestConvenienceEmitters:
    def setup_method(self):
        _listeners.clear()
        _recent.clear()

    def test_emit_message(self):
        emit_message("telegram", "123", "456", "completed", cost=0.05)
        recent = get_recent(1)
        assert len(recent) == 1
        assert recent[0].type == "message"

    def test_emit_usage(self):
        emit_usage("sonnet", 1000, 500, 0.02, 3500)
        recent = get_recent(1)
        assert recent[0].type == "usage"

    def test_emit_loop(self):
        emit_loop("sess1", "generic_repeat", "warning", 10, "Read", "stuck")
        recent = get_recent(1)
        assert recent[0].type == "tool_loop"


class TestStatusSummary:
    def setup_method(self):
        _recent.clear()

    def test_empty_summary(self):
        summary = get_status_summary()
        assert summary["total_events"] == 0
        assert summary["messages_processed"] == 0

    def test_populated_summary(self):
        emit_message("telegram", "c", "u", "completed")
        emit_usage("sonnet", 1000, 500, 0.05, 2000)
        emit_usage("opus", 2000, 1000, 0.10, 5000)
        summary = get_status_summary()
        assert summary["messages_processed"] == 1
        assert summary["total_cost_recent"] == 0.15
        assert summary["avg_latency_ms"] == 3500
