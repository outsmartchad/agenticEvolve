"""Provider Chain — resilient invocation layer wrapping Claude calls.

Implements the Decorator pattern: Retry → CircuitBreaker → Cache → RawProvider.
Each layer is transparent — same invoke() interface in, InvokeResult out.

Usage:
    from .provider_chain import build_provider_chain
    chain = build_provider_chain(invoke_claude_streaming, config)
    result = chain.invoke(prompt="hello", model="sonnet")
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypedDict

log = logging.getLogger("agenticEvolve.provider_chain")


# ── Result type ──────────────────────────────────────────────────

class InvokeResult(TypedDict, total=False):
    text: str
    cost: float
    input_tokens: int
    output_tokens: int
    error: str | None
    success: bool


# ── Provider protocol ────────────────────────────────────────────

class Provider(Protocol):
    def invoke(self, **kwargs: Any) -> InvokeResult: ...


# ── Exceptions ───────────────────────────────────────────────────

class RetryableError(Exception):
    """Raised when an invoke result contains a retryable error."""


# ── RawProvider adapter ──────────────────────────────────────────

class RawProvider:
    """Adapts an existing invoke function to the Provider interface.

    Passes all keyword arguments through to the underlying function.
    The wrapped function should return a dict with at least 'text',
    'cost', 'success' keys.

    For invoke_claude_streaming: prompt→message, plus on_progress, history, etc.
    For invoke_claude: prompt→message, plus history, session_context, etc.
    """

    def __init__(self, invoke_fn):
        self._invoke = invoke_fn

    def invoke(self, **kwargs: Any) -> InvokeResult:
        result = self._invoke(**kwargs)
        # Normalize: ensure 'error' key exists for downstream consumers
        if not result.get("success") and not result.get("error"):
            result["error"] = result.get("text", "Unknown error")
        return result


# ── RetryProvider ────────────────────────────────────────────────

class RetryProvider:
    """Wraps an inner Provider with exponential-backoff retry on transient errors.

    Retryable errors are identified by keyword matching against the error string.
    Non-retryable errors (auth, billing) pass through immediately.

    Args:
        inner: The next Provider in the chain.
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay_ms: Base delay before first retry, in milliseconds.
    """

    _RETRYABLE_KEYWORDS = [
        "rate limit", "429", "500", "502", "503", "timeout",
        "connection", "overloaded", "capacity",
    ]

    def __init__(self, inner: Provider, max_retries: int = 3,
                 base_delay_ms: int = 1000):
        self.inner = inner
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms

    def invoke(self, **kwargs: Any) -> InvokeResult:
        for attempt in range(self.max_retries + 1):
            try:
                result = self.inner.invoke(**kwargs)
                if result.get("error") and self._is_retryable(result["error"]):
                    raise RetryableError(result["error"])
                return result
            except RetryableError as e:
                if attempt == self.max_retries:
                    return InvokeResult(
                        text="", cost=0, input_tokens=0, output_tokens=0,
                        error=str(e), success=False,
                    )
                delay = self._backoff(attempt)
                log.warning(
                    f"Retry {attempt + 1}/{self.max_retries} after {delay:.1f}s: {e}"
                )
                time.sleep(delay)

        # Should never reach here, but satisfy type checker
        return InvokeResult(text="", cost=0, error="Exhausted retries", success=False)

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with ±25% jitter."""
        base = (self.base_delay_ms / 1000) * (2 ** attempt)
        jitter = base * 0.25 * (2 * random.random() - 1)
        return max(0.1, base + jitter)

    def _is_retryable(self, error: str) -> bool:
        error_lower = error.lower()
        return any(kw in error_lower for kw in self._RETRYABLE_KEYWORDS)


# ── CircuitBreakerProvider ───────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerProvider:
    """Wraps an inner Provider with circuit-breaker protection.

    State machine:
        CLOSED  → (failure_threshold failures) → OPEN
        OPEN    → (recovery_secs elapsed)      → HALF_OPEN
        HALF_OPEN → (half_open_successes OK)   → CLOSED
        HALF_OPEN → (any failure)              → OPEN

    Args:
        inner: The next Provider in the chain.
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_secs: Seconds to wait in OPEN before probing with HALF_OPEN.
        half_open_successes: Consecutive successes in HALF_OPEN to close.
    """

    _TRANSIENT_KEYWORDS = [
        "rate limit", "429", "500", "502", "503", "timeout",
        "connection", "overloaded", "capacity",
    ]

    def __init__(self, inner: Provider, failure_threshold: int = 5,
                 recovery_secs: float = 30, half_open_successes: int = 2):
        self.inner = inner
        self.failure_threshold = failure_threshold
        self.recovery_secs = recovery_secs
        self.half_open_successes = half_open_successes
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    def invoke(self, **kwargs: Any) -> InvokeResult:
        # Pre-flight: check if circuit is open
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_secs:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    log.info("Circuit breaker: transitioning to half-open")
                else:
                    remaining = self.recovery_secs - (
                        time.monotonic() - self._last_failure_time
                    )
                    return InvokeResult(
                        text="", cost=0, input_tokens=0, output_tokens=0,
                        error=f"Circuit breaker open (recovery in {remaining:.0f}s)",
                        success=False,
                    )

        result = self.inner.invoke(**kwargs)

        # Post-flight: update state
        with self._lock:
            if result.get("error") and self._is_transient(result["error"]):
                self._failure_count += 1
                self._success_count = 0
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_failure_time = time.monotonic()
                    log.error(
                        f"Circuit breaker OPEN after {self._failure_count} failures"
                    )
                elif self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.OPEN
                    self._last_failure_time = time.monotonic()
                    log.warning(
                        "Circuit breaker: half-open probe failed, re-opening"
                    )
            else:
                # Success path
                if self._state == CircuitState.HALF_OPEN:
                    self._success_count += 1
                    if self._success_count >= self.half_open_successes:
                        self._state = CircuitState.CLOSED
                        self._failure_count = 0
                        log.info("Circuit breaker: closed (recovered)")
                else:
                    self._failure_count = 0  # reset on success in closed state

        return result

    def _is_transient(self, error: str) -> bool:
        error_lower = error.lower()
        return any(kw in error_lower for kw in self._TRANSIENT_KEYWORDS)


# ── ResponseCache ────────────────────────────────────────────────

@dataclass
class CacheEntry:
    result: InvokeResult
    created: float
    last_accessed: float


class ResponseCache:
    """Wraps an inner Provider with a TTL + LRU response cache.

    Cache key is sha256(model | prompt | system_prompt[:200]).
    Errors and expensive responses (>$0.50) are not cached.

    Args:
        inner: The next Provider in the chain.
        ttl_secs: Time-to-live for cache entries, in seconds.
        max_entries: Maximum number of cached responses (LRU eviction).
    """

    def __init__(self, inner: Provider, ttl_secs: int = 3600,
                 max_entries: int = 200):
        self.inner = inner
        self.ttl_secs = ttl_secs
        self.max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    def invoke(self, **kwargs: Any) -> InvokeResult:
        # Skip cache for streaming calls (on_text_chunk is a callback)
        if kwargs.get("on_text_chunk") is not None:
            return self.inner.invoke(**kwargs)

        key = self._cache_key(kwargs)

        # Check cache
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.monotonic() - entry.created < self.ttl_secs:
                self._hits += 1
                entry.last_accessed = time.monotonic()
                if (self._hits + self._misses) % 100 == 0:
                    total = self._hits + self._misses
                    log.info(
                        f"Response cache: {self._hits}/{total} hits "
                        f"({100 * self._hits / total:.0f}%)"
                    )
                return entry.result
            self._misses += 1

        # Cache miss — invoke
        result = self.inner.invoke(**kwargs)

        # Don't cache errors or expensive responses
        if not result.get("error") and result.get("cost", 0) < 0.50:
            with self._lock:
                self._evict_if_needed()
                self._cache[key] = CacheEntry(
                    result=result,
                    created=time.monotonic(),
                    last_accessed=time.monotonic(),
                )

        return result

    def _cache_key(self, kwargs: dict) -> str:
        h = hashlib.sha256()
        h.update(kwargs.get("model", "").encode())
        h.update(b"|")
        h.update(kwargs.get("prompt", "").encode())
        h.update(b"|")
        h.update(kwargs.get("system_prompt", "")[:200].encode())
        return h.hexdigest()

    def _evict_if_needed(self):
        """LRU eviction + TTL cleanup. Must be called under self._lock."""
        now = time.monotonic()
        # Remove expired entries
        expired = [
            k for k, v in self._cache.items()
            if now - v.created >= self.ttl_secs
        ]
        for k in expired:
            del self._cache[k]
        # LRU eviction if still over limit
        while len(self._cache) >= self.max_entries:
            oldest_key = min(
                self._cache, key=lambda k: self._cache[k].last_accessed
            )
            del self._cache[oldest_key]

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# ── Chain helpers ────────────────────────────────────────────────

def walk_chain(provider: Provider) -> dict[str, Any]:
    """Walk the provider chain and return references to each layer.

    Returns dict with keys: 'cache', 'circuit_breaker', 'retry', 'raw'.
    Values are None if the layer is not present.
    """
    found: dict[str, Any] = {
        "cache": None,
        "circuit_breaker": None,
        "retry": None,
        "raw": None,
    }
    current = provider
    while current is not None:
        if isinstance(current, ResponseCache):
            found["cache"] = current
        elif isinstance(current, CircuitBreakerProvider):
            found["circuit_breaker"] = current
        elif isinstance(current, RetryProvider):
            found["retry"] = current
        elif isinstance(current, RawProvider):
            found["raw"] = current
        current = getattr(current, "inner", None)
    return found


# ── Chain builder ────────────────────────────────────────────────

def build_provider_chain(raw_invoke_fn, config: dict) -> Provider:
    """Build the provider chain from config.

    Chain order (outer → inner): Retry → CircuitBreaker → Cache → RawProvider

    Config keys under 'provider_chain':
        cache.enabled (bool, default True)
        cache.ttl_secs (int, default 3600)
        cache.max_entries (int, default 200)
        circuit_breaker.threshold (int, default 5)
        circuit_breaker.recovery_secs (float, default 30)
        circuit_breaker.half_open_successes (int, default 2)
        retry.max_retries (int, default 3)
        retry.base_delay_ms (int, default 1000)

    Args:
        raw_invoke_fn: The raw invocation function (e.g. invoke_claude_streaming).
        config: Full gateway config dict.

    Returns:
        The outermost Provider in the chain.
    """
    chain_cfg = config.get("provider_chain", {})

    provider: Provider = RawProvider(raw_invoke_fn)

    # Cache (innermost — closest to raw)
    cache_cfg = chain_cfg.get("cache", {})
    if cache_cfg.get("enabled", True):
        provider = ResponseCache(
            provider,
            ttl_secs=cache_cfg.get("ttl_secs", 3600),
            max_entries=cache_cfg.get("max_entries", 200),
        )

    # Circuit breaker
    cb_cfg = chain_cfg.get("circuit_breaker", {})
    provider = CircuitBreakerProvider(
        provider,
        failure_threshold=cb_cfg.get("threshold", 5),
        recovery_secs=cb_cfg.get("recovery_secs", 30),
        half_open_successes=cb_cfg.get("half_open_successes", 2),
    )

    # Retry (outermost)
    retry_cfg = chain_cfg.get("retry", {})
    provider = RetryProvider(
        provider,
        max_retries=retry_cfg.get("max_retries", 3),
        base_delay_ms=retry_cfg.get("base_delay_ms", 1000),
    )

    log.info(
        f"Provider chain built: Retry(max={retry_cfg.get('max_retries', 3)}) → "
        f"CircuitBreaker(threshold={cb_cfg.get('threshold', 5)}) → "
        f"Cache(enabled={cache_cfg.get('enabled', True)}, "
        f"ttl={cache_cfg.get('ttl_secs', 3600)}s) → RawProvider"
    )

    return provider
