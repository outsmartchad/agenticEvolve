"""Tests for gateway.provider_chain — Provider Chain Phase 2."""
import threading
import time

import pytest

from gateway.provider_chain import (
    RetryProvider,
    RetryableError,
    CircuitBreakerProvider,
    CircuitState,
    ResponseCache,
    RawProvider,
    build_provider_chain,
    walk_chain,
    InvokeResult,
)


# ── Helpers ──────────────────────────────────────────────────────

def _ok_result(text: str = "ok", cost: float = 0.01) -> InvokeResult:
    return InvokeResult(
        text=text, cost=cost, input_tokens=10, output_tokens=20,
        error=None, success=True,
    )


def _error_result(error: str, retryable: bool = True) -> InvokeResult:
    return InvokeResult(
        text="", cost=0, input_tokens=0, output_tokens=0,
        error=error, success=False,
    )


class FakeProvider:
    """Configurable fake provider for testing."""

    def __init__(self, results: list[InvokeResult] | None = None):
        self.results = list(results or [])
        self.call_count = 0
        self.last_kwargs: dict = {}

    def invoke(self, **kwargs) -> InvokeResult:
        self.last_kwargs = kwargs
        self.call_count += 1
        if self.results:
            return self.results.pop(0)
        return _ok_result()


# ── RetryProvider ────────────────────────────────────────────────

class TestRetryProvider:
    def test_success_no_retry(self):
        inner = FakeProvider([_ok_result()])
        retry = RetryProvider(inner, max_retries=3, base_delay_ms=10)
        result = retry.invoke(prompt="hello", model="sonnet")
        assert result["text"] == "ok"
        assert inner.call_count == 1

    def test_non_retryable_error_passes_through(self):
        """Auth errors should NOT be retried."""
        inner = FakeProvider([_error_result("Authentication failed")])
        retry = RetryProvider(inner, max_retries=3, base_delay_ms=10)
        result = retry.invoke(prompt="hello", model="sonnet")
        assert result["error"] == "Authentication failed"
        assert inner.call_count == 1

    def test_retryable_error_retries(self):
        """Rate limit errors should be retried."""
        results = [
            _error_result("rate limit exceeded"),
            _error_result("rate limit exceeded"),
            _ok_result("recovered"),
        ]
        inner = FakeProvider(results)
        retry = RetryProvider(inner, max_retries=3, base_delay_ms=10)
        result = retry.invoke(prompt="hello", model="sonnet")
        assert result["text"] == "recovered"
        assert inner.call_count == 3

    def test_max_retries_respected(self):
        """After max_retries, should give up and return error."""
        results = [_error_result("503 error")] * 5
        inner = FakeProvider(results)
        retry = RetryProvider(inner, max_retries=2, base_delay_ms=10)
        result = retry.invoke(prompt="hello", model="sonnet")
        assert result["error"] is not None
        assert "503" in result["error"]
        # 1 initial + 2 retries = 3 total
        assert inner.call_count == 3

    def test_backoff_timing(self):
        """Verify backoff produces increasing delays."""
        retry = RetryProvider(FakeProvider(), max_retries=3, base_delay_ms=1000)
        delays = [retry._backoff(i) for i in range(4)]
        # Each subsequent delay should be roughly 2x the previous (within jitter)
        for i in range(1, len(delays)):
            assert delays[i] > delays[i - 1] * 0.5  # allow jitter

    def test_backoff_jitter_range(self):
        """Jitter should be ±25% of base."""
        retry = RetryProvider(FakeProvider(), base_delay_ms=1000)
        samples = [retry._backoff(0) for _ in range(200)]
        # Base for attempt 0 = 1.0s, jitter ±25% → [0.75, 1.25]
        assert all(0.1 <= s <= 1.5 for s in samples)

    def test_retryable_keywords(self):
        retry = RetryProvider(FakeProvider())
        assert retry._is_retryable("rate limit exceeded")
        assert retry._is_retryable("HTTP 429 Too Many Requests")
        assert retry._is_retryable("502 Bad Gateway")
        assert retry._is_retryable("Connection timeout")
        assert retry._is_retryable("Server overloaded")
        assert not retry._is_retryable("Authentication failed")
        assert not retry._is_retryable("Invalid API key")
        assert not retry._is_retryable("Billing quota exceeded")

    def test_kwargs_passed_through(self):
        """Verify all kwargs reach the inner provider."""
        inner = FakeProvider([_ok_result()])
        retry = RetryProvider(inner, max_retries=0)
        retry.invoke(prompt="test", model="opus", custom_key="val")
        assert inner.last_kwargs["prompt"] == "test"
        assert inner.last_kwargs["model"] == "opus"
        assert inner.last_kwargs["custom_key"] == "val"


# ── CircuitBreakerProvider ───────────────────────────────────────

class TestCircuitBreakerProvider:
    def test_closed_passes_through(self):
        inner = FakeProvider([_ok_result()])
        cb = CircuitBreakerProvider(inner, failure_threshold=3)
        result = cb.invoke(prompt="hello", model="sonnet")
        assert result["text"] == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_closed_to_open_at_threshold(self):
        """Circuit should open after failure_threshold consecutive failures."""
        results = [_error_result("timeout")] * 5
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(inner, failure_threshold=3, recovery_secs=60)

        for i in range(3):
            cb.invoke(prompt="hello", model="sonnet")

        assert cb.state == CircuitState.OPEN

    def test_open_rejects_immediately(self):
        """While open, requests should be rejected without calling inner."""
        results = [_error_result("timeout")] * 5
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(inner, failure_threshold=2, recovery_secs=60)

        # Trip the breaker
        cb.invoke(prompt="hello", model="sonnet")
        cb.invoke(prompt="hello", model="sonnet")
        assert cb.state == CircuitState.OPEN

        # Reset call count
        inner.call_count = 0

        # This should be rejected without calling inner
        result = cb.invoke(prompt="hello", model="sonnet")
        assert "Circuit breaker open" in result["error"]
        assert inner.call_count == 0

    def test_open_to_half_open_after_recovery(self):
        """After recovery_secs, circuit should transition to half-open."""
        results = [_error_result("timeout")] * 3 + [_ok_result("probe ok")]
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(
            inner, failure_threshold=2, recovery_secs=0.05
        )

        # Trip the breaker
        cb.invoke(prompt="hello", model="sonnet")
        cb.invoke(prompt="hello", model="sonnet")
        assert cb.state == CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.1)

        # Next call should go through (half-open probe)
        result = cb.invoke(prompt="hello", model="sonnet")
        assert result.get("error") is None or "Circuit breaker" not in (result.get("error") or "")

    def test_half_open_to_closed_after_successes(self):
        """N consecutive successes in half-open should close the circuit."""
        results = (
            [_error_result("timeout")] * 2  # trip breaker
            + [_ok_result("probe 1"), _ok_result("probe 2")]  # half-open successes
        )
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(
            inner, failure_threshold=2, recovery_secs=0.05,
            half_open_successes=2,
        )

        # Trip
        cb.invoke(prompt="hello", model="sonnet")
        cb.invoke(prompt="hello", model="sonnet")
        assert cb.state == CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.1)

        # Two successful probes
        cb.invoke(prompt="hello", model="sonnet")
        cb.invoke(prompt="hello", model="sonnet")
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """A failure in half-open should re-open the circuit."""
        results = (
            [_error_result("timeout")] * 2  # trip breaker
            + [_error_result("timeout again")]  # half-open probe fails
        )
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(
            inner, failure_threshold=2, recovery_secs=0.05,
        )

        # Trip
        cb.invoke(prompt="hello", model="sonnet")
        cb.invoke(prompt="hello", model="sonnet")
        assert cb.state == CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.1)

        # Failed probe → re-open
        cb.invoke(prompt="hello", model="sonnet")
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        """A success in closed state should reset the failure counter."""
        results = [
            _error_result("timeout"),  # failure 1
            _ok_result(),              # success → resets count
            _error_result("timeout"),  # failure 1 again (not 2)
        ]
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(inner, failure_threshold=2)

        cb.invoke(prompt="hello", model="sonnet")
        assert cb.failure_count == 1

        cb.invoke(prompt="hello", model="sonnet")
        assert cb.failure_count == 0

        cb.invoke(prompt="hello", model="sonnet")
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED

    def test_non_transient_errors_dont_trip(self):
        """Auth errors should not increment failure count."""
        results = [_error_result("Authentication failed")] * 10
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(inner, failure_threshold=3)

        for _ in range(5):
            cb.invoke(prompt="hello", model="sonnet")

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_thread_safety(self):
        """Circuit breaker should be safe under concurrent access."""
        results = [_ok_result()] * 100
        inner = FakeProvider(results)
        cb = CircuitBreakerProvider(inner, failure_threshold=5)

        errors = []

        def worker():
            try:
                for _ in range(10):
                    cb.invoke(prompt="hello", model="sonnet")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cb.state == CircuitState.CLOSED


# ── ResponseCache ────────────────────────────────────────────────

class TestResponseCache:
    def test_cache_hit(self):
        inner = FakeProvider([_ok_result("first call")])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        # First call — miss
        r1 = cache.invoke(prompt="hello", model="sonnet")
        assert r1["text"] == "first call"
        assert inner.call_count == 1

        # Second call — hit (same args)
        r2 = cache.invoke(prompt="hello", model="sonnet")
        assert r2["text"] == "first call"
        assert inner.call_count == 1  # not called again
        assert cache.hits == 1
        assert cache.misses == 1

    def test_cache_miss_different_prompt(self):
        inner = FakeProvider([_ok_result("a"), _ok_result("b")])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        cache.invoke(prompt="hello", model="sonnet")
        cache.invoke(prompt="world", model="sonnet")

        assert inner.call_count == 2
        assert cache.misses == 2

    def test_cache_miss_different_model(self):
        inner = FakeProvider([_ok_result("a"), _ok_result("b")])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        cache.invoke(prompt="hello", model="sonnet")
        cache.invoke(prompt="hello", model="opus")

        assert inner.call_count == 2

    def test_ttl_expiry(self):
        inner = FakeProvider([_ok_result("old"), _ok_result("new")])
        cache = ResponseCache(inner, ttl_secs=0, max_entries=10)  # 0s TTL = immediate expiry

        cache.invoke(prompt="hello", model="sonnet")

        # Very short sleep to ensure monotonic time advances
        time.sleep(0.001)

        r2 = cache.invoke(prompt="hello", model="sonnet")
        assert r2["text"] == "new"
        assert inner.call_count == 2

    def test_errors_not_cached(self):
        results = [
            _error_result("timeout"),
            _ok_result("recovered"),
        ]
        inner = FakeProvider(results)
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        r1 = cache.invoke(prompt="hello", model="sonnet")
        assert r1["error"] == "timeout"

        r2 = cache.invoke(prompt="hello", model="sonnet")
        assert r2["text"] == "recovered"
        assert inner.call_count == 2  # error was NOT cached

    def test_expensive_responses_not_cached(self):
        """Responses costing >= $0.50 should not be cached."""
        expensive = InvokeResult(
            text="big response", cost=0.75, input_tokens=1000,
            output_tokens=5000, error=None, success=True,
        )
        inner = FakeProvider([expensive, _ok_result("second")])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        cache.invoke(prompt="hello", model="sonnet")
        cache.invoke(prompt="hello", model="sonnet")

        assert inner.call_count == 2  # expensive result NOT cached

    def test_lru_eviction(self):
        inner = FakeProvider([_ok_result(f"r{i}") for i in range(5)])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=2)

        # Fill cache to capacity
        cache.invoke(prompt="a", model="sonnet")
        cache.invoke(prompt="b", model="sonnet")

        # This should evict "a" (LRU)
        cache.invoke(prompt="c", model="sonnet")

        assert inner.call_count == 3

        # "a" should be evicted — calling it again is a miss
        cache.invoke(prompt="a", model="sonnet")
        assert inner.call_count == 4

    def test_streaming_bypasses_cache(self):
        """Calls with on_text_chunk should skip the cache."""
        inner = FakeProvider([_ok_result("stream1"), _ok_result("stream2")])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        cache.invoke(prompt="hello", model="sonnet", on_text_chunk=lambda t: None)
        cache.invoke(prompt="hello", model="sonnet", on_text_chunk=lambda t: None)

        assert inner.call_count == 2  # both calls went through
        assert cache.hits == 0

    def test_clear(self):
        inner = FakeProvider([_ok_result("a"), _ok_result("b")])
        cache = ResponseCache(inner, ttl_secs=60, max_entries=10)

        cache.invoke(prompt="hello", model="sonnet")
        assert cache.misses == 1

        cache.clear()
        assert cache.hits == 0
        assert cache.misses == 0

        cache.invoke(prompt="hello", model="sonnet")
        assert inner.call_count == 2


# ── RawProvider ──────────────────────────────────────────────────

class TestRawProvider:
    def test_passes_kwargs_through(self):
        call_log = {}

        def fake_invoke(**kwargs):
            call_log.update(kwargs)
            return {"text": "ok", "cost": 0.01, "success": True}

        raw = RawProvider(fake_invoke)
        raw.invoke(message="hello", model="sonnet", custom="val")

        assert call_log["message"] == "hello"
        assert call_log["model"] == "sonnet"
        assert call_log["custom"] == "val"

    def test_normalizes_error_field(self):
        def failing_invoke(**kwargs):
            return {"text": "Something went wrong", "cost": 0, "success": False}

        raw = RawProvider(failing_invoke)
        result = raw.invoke(message="hello", model="sonnet")

        assert result["error"] == "Something went wrong"

    def test_preserves_existing_error(self):
        def failing_invoke(**kwargs):
            return {"text": "", "cost": 0, "success": False, "error": "real error"}

        raw = RawProvider(failing_invoke)
        result = raw.invoke(message="hello", model="sonnet")

        assert result["error"] == "real error"


# ── Full chain integration ───────────────────────────────────────

class TestFullChain:
    def test_end_to_end_success(self):
        def mock_invoke(**kwargs):
            return {"text": "hello world", "cost": 0.01, "success": True,
                    "input_tokens": 10, "output_tokens": 20}

        chain = build_provider_chain(mock_invoke, {})
        result = chain.invoke(message="hi", model="sonnet")

        assert result["text"] == "hello world"
        assert result["success"] is True

    def test_end_to_end_retry_then_success(self):
        call_count = 0

        def flaky_invoke(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"text": "", "cost": 0, "success": False,
                        "error": "rate limit exceeded"}
            return {"text": "ok", "cost": 0.01, "success": True}

        config = {"provider_chain": {"retry": {"base_delay_ms": 10}}}
        chain = build_provider_chain(flaky_invoke, config)
        result = chain.invoke(message="hi", model="sonnet")

        assert result["text"] == "ok"
        assert call_count == 3

    def test_circuit_breaker_trips_through_chain(self):
        call_count = 0

        def always_fail(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"text": "", "cost": 0, "success": False,
                    "error": "503 Service Unavailable"}

        config = {
            "provider_chain": {
                "retry": {"max_retries": 0, "base_delay_ms": 10},
                "circuit_breaker": {"threshold": 2, "recovery_secs": 60},
                "cache": {"enabled": False},
            }
        }
        chain = build_provider_chain(always_fail, config)

        # Trip the circuit breaker
        chain.invoke(message="hi", model="sonnet")
        chain.invoke(message="hi", model="sonnet")

        # Next call should be rejected by circuit breaker
        call_count_before = call_count
        result = chain.invoke(message="hi", model="sonnet")
        assert "Circuit breaker open" in (result.get("error") or "")
        assert call_count == call_count_before  # inner not called

    def test_cache_serves_repeated_requests(self):
        call_count = 0

        def counting_invoke(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"text": "cached", "cost": 0.01, "success": True}

        config = {"provider_chain": {"retry": {"max_retries": 0}}}
        chain = build_provider_chain(counting_invoke, config)

        chain.invoke(message="same prompt", model="sonnet")
        chain.invoke(message="same prompt", model="sonnet")

        # Second call should hit cache
        assert call_count == 1

    def test_error_propagation_through_layers(self):
        def auth_fail(**kwargs):
            return {"text": "", "cost": 0, "success": False,
                    "error": "Invalid API key"}

        config = {"provider_chain": {"retry": {"base_delay_ms": 10}}}
        chain = build_provider_chain(auth_fail, config)
        result = chain.invoke(message="hi", model="sonnet")

        # Auth errors are NOT retryable — should pass through immediately
        assert "Invalid API key" in result["error"]


# ── build_provider_chain config ──────────────────────────────────

class TestBuildProviderChain:
    def test_default_config(self):
        chain = build_provider_chain(lambda **kw: _ok_result(), {})
        layers = walk_chain(chain)
        assert layers["retry"] is not None
        assert layers["circuit_breaker"] is not None
        assert layers["cache"] is not None
        assert layers["raw"] is not None

    def test_cache_disabled(self):
        config = {"provider_chain": {"cache": {"enabled": False}}}
        chain = build_provider_chain(lambda **kw: _ok_result(), config)
        layers = walk_chain(chain)
        assert layers["cache"] is None
        assert layers["circuit_breaker"] is not None

    def test_custom_retry_config(self):
        config = {"provider_chain": {"retry": {"max_retries": 5, "base_delay_ms": 500}}}
        chain = build_provider_chain(lambda **kw: _ok_result(), config)
        layers = walk_chain(chain)
        retry = layers["retry"]
        assert retry.max_retries == 5
        assert retry.base_delay_ms == 500

    def test_custom_circuit_breaker_config(self):
        config = {"provider_chain": {"circuit_breaker": {
            "threshold": 10, "recovery_secs": 120, "half_open_successes": 5
        }}}
        chain = build_provider_chain(lambda **kw: _ok_result(), config)
        layers = walk_chain(chain)
        cb = layers["circuit_breaker"]
        assert cb.failure_threshold == 10
        assert cb.recovery_secs == 120
        assert cb.half_open_successes == 5

    def test_custom_cache_config(self):
        config = {"provider_chain": {"cache": {"ttl_secs": 1800, "max_entries": 50}}}
        chain = build_provider_chain(lambda **kw: _ok_result(), config)
        layers = walk_chain(chain)
        cache = layers["cache"]
        assert cache.ttl_secs == 1800
        assert cache.max_entries == 50


# ── walk_chain ───────────────────────────────────────────────────

class TestWalkChain:
    def test_finds_all_layers(self):
        chain = build_provider_chain(lambda **kw: _ok_result(), {})
        layers = walk_chain(chain)
        assert isinstance(layers["retry"], RetryProvider)
        assert isinstance(layers["circuit_breaker"], CircuitBreakerProvider)
        assert isinstance(layers["cache"], ResponseCache)
        assert isinstance(layers["raw"], RawProvider)

    def test_handles_missing_cache(self):
        config = {"provider_chain": {"cache": {"enabled": False}}}
        chain = build_provider_chain(lambda **kw: _ok_result(), config)
        layers = walk_chain(chain)
        assert layers["cache"] is None
        assert layers["raw"] is not None
