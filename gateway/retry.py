"""Retry utility — exponential backoff with jitter for transient failures.

Adapted from OpenClaw's retry.ts. Provides:
- Configurable attempts, min/max delay, jitter
- Server-directed retry (Retry-After header support)
- Conditional retry via shouldRetry predicate
- Callback hooks for logging/metrics
"""
import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Callable, TypeVar

log = logging.getLogger("agenticEvolve.retry")

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Retry configuration."""
    attempts: int = 3
    min_delay: float = 0.3       # seconds
    max_delay: float = 30.0      # seconds
    jitter: float = 0.1          # 0-1, fraction of delay to randomize

    def __post_init__(self):
        self.attempts = max(1, self.attempts)
        self.min_delay = max(0, self.min_delay)
        self.max_delay = max(self.min_delay, self.max_delay)
        self.jitter = max(0.0, min(1.0, self.jitter))


@dataclass
class RetryInfo:
    """Information about a retry attempt."""
    attempt: int
    max_attempts: int
    delay: float
    error: Exception
    label: str = ""


# Default config
DEFAULT_CONFIG = RetryConfig()


def _apply_jitter(delay: float, jitter: float) -> float:
    """Apply symmetric jitter to delay."""
    if jitter <= 0:
        return delay
    offset = random.uniform(-jitter, jitter)
    return max(0, delay * (1 + offset))


async def retry_async(
    fn: Callable[..., T],
    *,
    config: RetryConfig | None = None,
    label: str = "",
    should_retry: Callable[[Exception, int], bool] | None = None,
    retry_after: Callable[[Exception], float | None] | None = None,
    on_retry: Callable[[RetryInfo], None] | None = None,
) -> T:
    """Execute fn with exponential backoff retry.

    Args:
        fn: Async callable to execute.
        config: Retry configuration (defaults to 3 attempts, 0.3s-30s delay, 0.1 jitter).
        label: Label for logging.
        should_retry: Predicate to decide if an error is retryable.
        retry_after: Extract server-suggested delay from error (e.g., Retry-After header).
        on_retry: Callback invoked before each retry sleep.

    Returns:
        Result of fn.

    Raises:
        The last exception if all retries are exhausted.
    """
    cfg = config or DEFAULT_CONFIG
    last_err: Exception | None = None

    for attempt in range(1, cfg.attempts + 1):
        try:
            return await fn()
        except Exception as e:
            last_err = e
            if attempt >= cfg.attempts:
                break
            if should_retry and not should_retry(e, attempt):
                break

            # Calculate delay
            server_delay = retry_after(e) if retry_after else None
            if server_delay is not None:
                base_delay = max(server_delay, cfg.min_delay)
            else:
                base_delay = cfg.min_delay * (2 ** (attempt - 1))

            delay = min(base_delay, cfg.max_delay)
            delay = _apply_jitter(delay, cfg.jitter)
            delay = max(cfg.min_delay, min(delay, cfg.max_delay))

            info = RetryInfo(
                attempt=attempt,
                max_attempts=cfg.attempts,
                delay=delay,
                error=e,
                label=label,
            )
            if on_retry:
                on_retry(info)
            else:
                log.warning(
                    f"Retry {label or 'op'} attempt {attempt}/{cfg.attempts} "
                    f"after {delay:.1f}s: {e}"
                )

            await asyncio.sleep(delay)

    raise last_err  # type: ignore[misc]


# ── Convenience: Telegram retry helper ───────────────────────

def _is_telegram_retryable(e: Exception, attempt: int) -> bool:
    """Check if a Telegram API error is retryable."""
    msg = str(e).lower()
    return any(kw in msg for kw in ("429", "retry_after", "timeout", "reset", "flood"))


def _telegram_retry_after(e: Exception) -> float | None:
    """Extract retry_after seconds from Telegram error."""
    import re
    m = re.search(r"retry.?after[:\s=]+(\d+)", str(e), re.I)
    if m:
        return float(m.group(1))
    return None


TELEGRAM_RETRY = RetryConfig(attempts=3, min_delay=1.0, max_delay=60.0, jitter=0.15)


async def telegram_retry(fn: Callable[..., T], label: str = "telegram") -> T:
    """Retry a Telegram API call with appropriate error handling."""
    return await retry_async(
        fn,
        config=TELEGRAM_RETRY,
        label=label,
        should_retry=_is_telegram_retryable,
        retry_after=_telegram_retry_after,
    )
