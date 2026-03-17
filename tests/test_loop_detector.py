"""Tests for gateway.loop_detector."""
import pytest
from gateway.loop_detector import (
    LoopDetectorState, DetectionMode, Severity,
    hash_tool_call, hash_result,
)


class TestHashing:
    def test_same_args_same_hash(self):
        h1 = hash_tool_call("Read", {"path": "/foo"})
        h2 = hash_tool_call("Read", {"path": "/foo"})
        assert h1 == h2

    def test_different_args_different_hash(self):
        h1 = hash_tool_call("Read", {"path": "/foo"})
        h2 = hash_tool_call("Read", {"path": "/bar"})
        assert h1 != h2

    def test_key_order_irrelevant(self):
        h1 = hash_tool_call("Read", {"a": 1, "b": 2})
        h2 = hash_tool_call("Read", {"b": 2, "a": 1})
        assert h1 == h2

    def test_result_hash(self):
        h1 = hash_result("output text")
        h2 = hash_result("output text")
        assert h1 == h2

    def test_error_hash(self):
        h1 = hash_result(None, error="timeout")
        h2 = hash_result(None, error="timeout")
        assert h1 == h2
        h3 = hash_result(None, error="other")
        assert h1 != h3


class TestLoopDetector:
    def test_no_detection_on_clean(self):
        state = LoopDetectorState()
        state.record_call("Read", "h1")
        state.record_outcome("Read", "h1", "r1")
        assert state.detect("Read", "h1") is None

    def test_generic_repeat_warning(self):
        state = LoopDetectorState(warning_threshold=5)
        for i in range(5):
            state.record_call("Write", "same_hash")
            state.record_outcome("Write", "same_hash", f"result_{i}")
        detection = state.detect("Write", "same_hash")
        assert detection is not None
        assert detection.mode == DetectionMode.GENERIC_REPEAT
        assert detection.level == Severity.WARNING

    def test_no_progress_streak(self):
        state = LoopDetectorState(warning_threshold=3, critical_threshold=5, global_breaker_threshold=8)
        for _ in range(5):
            state.record_call("Bash", "h1")
            state.record_outcome("Bash", "h1", "same_result")
        # Bash is in KNOWN_POLL_TOOLS, so known_poll detection applies
        detection = state.detect("Bash", "h1")
        assert detection is not None
        assert detection.mode == DetectionMode.KNOWN_POLL
        assert detection.level == Severity.CRITICAL

    def test_global_circuit_breaker(self):
        state = LoopDetectorState(
            warning_threshold=3, critical_threshold=5, global_breaker_threshold=8
        )
        for _ in range(8):
            state.record_call("Bash", "h1")
            state.record_outcome("Bash", "h1", "same")
        detection = state.detect("Bash", "h1")
        assert detection is not None
        assert detection.mode == DetectionMode.GLOBAL_BREAKER
        assert detection.level == Severity.CRITICAL

    def test_ping_pong_detection(self):
        state = LoopDetectorState(warning_threshold=5)
        for i in range(6):
            if i % 2 == 0:
                state.record_call("Write", "a")
                state.record_outcome("Write", "a", "ra")
            else:
                state.record_call("Write", "b")
                state.record_outcome("Write", "b", "rb")
        detection = state.detect("Write", "a")
        assert detection is not None
        assert detection.mode == DetectionMode.PING_PONG

    def test_warning_dedup(self):
        state = LoopDetectorState(warning_threshold=3)
        for _ in range(3):
            state.record_call("Write", "h1")
            state.record_outcome("Write", "h1", f"r")
        d1 = state.detect("Write", "h1")
        assert d1 is not None
        # Second detect with same key should return None (already warned)
        d2 = state.detect("Write", "h1")
        assert d2 is None

    def test_stats(self):
        state = LoopDetectorState()
        state.record_call("Read", "h1")
        state.record_call("Write", "h2")
        state.record_call("Read", "h1")
        stats = state.get_stats()
        assert stats["total_calls"] == 3
        assert stats["unique_tools"] == 2
        assert stats["tool_counts"]["Read"] == 2

    def test_history_size_cap(self):
        state = LoopDetectorState(history_size=5)
        for i in range(10):
            state.record_call("Read", f"h{i}")
        assert len(state.history) == 5
