"""Base platform adapter interface."""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

log = logging.getLogger(__name__)

# Circuit-breaker thresholds
_CB_FAIL_THRESHOLD = 5   # consecutive failures before opening
_CB_RECOVERY_SECS = 60   # seconds to wait before half-open probe


class CircuitBreaker:
    """Simple async circuit breaker: closed -> open -> half-open -> closed."""

    def __init__(self, name: str, fail_threshold: int = _CB_FAIL_THRESHOLD,
                 recovery_secs: float = _CB_RECOVERY_SECS):
        self.name = name
        self.fail_threshold = fail_threshold
        self.recovery_secs = recovery_secs
        self._failures = 0
        self._opened_at: float | None = None
        self._open = False

    def record_success(self) -> None:
        self._failures = 0
        self._open = False
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_threshold and not self._open:
            import time
            self._open = True
            self._opened_at = time.monotonic()
            log.warning(
                f"[{self.name}] circuit breaker OPEN after "
                f"{self._failures} consecutive failures"
            )

    def is_open(self) -> bool:
        if not self._open:
            return False
        import time
        if time.monotonic() - (self._opened_at or 0) >= self.recovery_secs:
            log.info(f"[{self.name}] circuit breaker half-open — probing")
            self._open = False  # allow one probe attempt
            return False
        return True


async def retry_with_backoff(
    coro_fn,
    *,
    name: str,
    breaker: CircuitBreaker | None = None,
    max_attempts: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 120.0,
    jitter: float = 0.2,
) -> None:
    """Run coro_fn() with exponential backoff on failure.

    coro_fn is a zero-argument callable that returns a coroutine.
    Stops after max_attempts or if the circuit breaker is open.
    """
    import random

    attempt = 0
    delay = base_delay
    while True:
        if breaker and breaker.is_open():
            log.warning(f"[{name}] circuit breaker open, backing off")
            await asyncio.sleep(breaker.recovery_secs)
            continue

        try:
            await coro_fn()
            if breaker:
                breaker.record_success()
            return  # clean exit
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            attempt += 1
            if breaker:
                breaker.record_failure()
            if attempt >= max_attempts:
                log.error(f"[{name}] giving up after {attempt} attempts: {exc}")
                return
            sleep = min(delay * (2 ** (attempt - 1)), max_delay)
            sleep *= 1 + random.uniform(-jitter, jitter)
            log.warning(
                f"[{name}] attempt {attempt}/{max_attempts} failed: {exc} "
                f"— retrying in {sleep:.1f}s"
            )
            await asyncio.sleep(sleep)


class BasePlatformAdapter(ABC):
    """All platform adapters must implement this interface."""

    def __init__(self, config: dict, on_message: Callable):
        self.config = config
        self.on_message = on_message  # async callback(platform, chat_id, user_id, text) -> str

    @abstractmethod
    async def start(self):
        """Connect to the platform and start listening."""
        ...

    @abstractmethod
    async def stop(self):
        """Disconnect gracefully."""
        ...

    @abstractmethod
    async def send(self, chat_id: str, text: str):
        """Send a message to a specific chat."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform name (telegram, discord, whatsapp)."""
        ...
