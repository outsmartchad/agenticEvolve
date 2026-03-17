"""Tests for gateway.retry."""
import asyncio
import pytest
from gateway.retry import RetryConfig, retry_async, _apply_jitter


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.attempts == 3
        assert cfg.min_delay == 0.3
        assert cfg.max_delay == 30.0
        assert cfg.jitter == 0.1

    def test_clamps_attempts(self):
        cfg = RetryConfig(attempts=-1)
        assert cfg.attempts == 1

    def test_clamps_jitter(self):
        cfg = RetryConfig(jitter=2.0)
        assert cfg.jitter == 1.0

    def test_max_delay_at_least_min(self):
        cfg = RetryConfig(min_delay=10.0, max_delay=5.0)
        assert cfg.max_delay >= cfg.min_delay


class TestApplyJitter:
    def test_zero_jitter(self):
        assert _apply_jitter(1.0, 0.0) == 1.0

    def test_jitter_within_bounds(self):
        for _ in range(100):
            result = _apply_jitter(1.0, 0.5)
            assert 0.5 <= result <= 1.5


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        calls = 0
        async def fn():
            nonlocal calls
            calls += 1
            return "ok"
        result = await retry_async(fn, config=RetryConfig(attempts=3))
        assert result == "ok"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        calls = 0
        async def fn():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("fail")
            return "ok"
        result = await retry_async(fn, config=RetryConfig(attempts=3, min_delay=0.01))
        assert result == "ok"
        assert calls == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        async def fn():
            raise ValueError("always fail")
        with pytest.raises(ValueError, match="always fail"):
            await retry_async(fn, config=RetryConfig(attempts=2, min_delay=0.01))

    @pytest.mark.asyncio
    async def test_should_retry_predicate(self):
        calls = 0
        async def fn():
            nonlocal calls
            calls += 1
            raise ValueError("non-retryable")

        with pytest.raises(ValueError):
            await retry_async(
                fn,
                config=RetryConfig(attempts=5, min_delay=0.01),
                should_retry=lambda e, a: False,
            )
        assert calls == 1  # stopped after first failure

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        infos = []
        calls = 0
        async def fn():
            nonlocal calls
            calls += 1
            if calls < 2:
                raise ValueError("fail")
            return "ok"

        await retry_async(
            fn,
            config=RetryConfig(attempts=3, min_delay=0.01),
            on_retry=lambda info: infos.append(info),
        )
        assert len(infos) == 1
        assert infos[0].attempt == 1
