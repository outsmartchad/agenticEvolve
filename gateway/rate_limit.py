"""Per-user sliding-window rate limiting (OpenClaw pattern).

Prevents a single user from exhausting the Claude API quota.
Configurable via config.yaml:

  rate_limit:
    per_user_per_minute: 5      # max messages per user per minute
    per_user_per_hour: 30       # max messages per user per hour
    per_chat_per_minute: 10     # max messages per chat per minute (group chats)
    cooldown_seconds: 60        # cooldown after hitting limit
"""
import logging
import time
from collections import defaultdict, deque

log = logging.getLogger("agenticEvolve.rate_limit")


class RateLimiter:
    """Sliding-window rate limiter with per-user and per-chat counters."""

    def __init__(self, config: dict | None = None):
        rl_cfg = (config or {}).get("rate_limit", {})
        self.per_user_per_minute = rl_cfg.get("per_user_per_minute", 5)
        self.per_user_per_hour = rl_cfg.get("per_user_per_hour", 30)
        self.per_chat_per_minute = rl_cfg.get("per_chat_per_minute", 10)
        self.cooldown_seconds = rl_cfg.get("cooldown_seconds", 60)

        # user_id -> deque of timestamps
        self._user_hits: dict[str, deque] = defaultdict(deque)
        # chat_id -> deque of timestamps
        self._chat_hits: dict[str, deque] = defaultdict(deque)
        # user_id -> cooldown expiry timestamp
        self._cooldowns: dict[str, float] = {}

    def check(self, user_id: str, chat_id: str | None = None) -> tuple[bool, str]:
        """Check if a request is allowed.

        Returns (allowed, reason). If not allowed, reason explains why.
        """
        now = time.monotonic()

        # Check cooldown first
        if user_id in self._cooldowns:
            if now < self._cooldowns[user_id]:
                remaining = int(self._cooldowns[user_id] - now)
                return False, f"Rate limited. Try again in {remaining}s."
            else:
                del self._cooldowns[user_id]

        # Per-user per-minute check
        user_q = self._user_hits[user_id]
        self._prune(user_q, now, 60)
        if len(user_q) >= self.per_user_per_minute:
            self._cooldowns[user_id] = now + self.cooldown_seconds
            log.warning(f"Rate limit hit: user {user_id} ({len(user_q)}/{self.per_user_per_minute} per min)")
            return False, f"Too many messages. Limit: {self.per_user_per_minute}/min. Try again in {self.cooldown_seconds}s."

        # Per-user per-hour check
        self._prune(user_q, now, 3600)
        # Count only last hour's hits (the deque may have been pruned to 60s above,
        # so we need a separate count)
        hour_hits = self._user_hits.get(f"{user_id}:hour", deque())
        self._prune(hour_hits, now, 3600)
        self._user_hits[f"{user_id}:hour"] = hour_hits
        if len(hour_hits) >= self.per_user_per_hour:
            self._cooldowns[user_id] = now + self.cooldown_seconds * 5
            log.warning(f"Rate limit hit: user {user_id} ({len(hour_hits)}/{self.per_user_per_hour} per hour)")
            return False, f"Hourly limit reached ({self.per_user_per_hour}/hr). Take a break."

        # Per-chat per-minute check (for group chats)
        if chat_id and chat_id != user_id:
            chat_q = self._chat_hits[chat_id]
            self._prune(chat_q, now, 60)
            if len(chat_q) >= self.per_chat_per_minute:
                log.warning(f"Rate limit hit: chat {chat_id} ({len(chat_q)}/{self.per_chat_per_minute} per min)")
                return False, f"This chat is too active. Limit: {self.per_chat_per_minute}/min."

        return True, ""

    def record(self, user_id: str, chat_id: str | None = None):
        """Record a successful request (call after check passes)."""
        now = time.monotonic()
        self._user_hits[user_id].append(now)
        # Also track hourly
        hour_key = f"{user_id}:hour"
        if hour_key not in self._user_hits:
            self._user_hits[hour_key] = deque()
        self._user_hits[hour_key].append(now)

        if chat_id and chat_id != user_id:
            self._chat_hits[chat_id].append(now)

    def _prune(self, q: deque, now: float, window: float):
        """Remove entries older than window seconds."""
        while q and q[0] < now - window:
            q.popleft()

    def prune_stale(self):
        """Remove stale entries to prevent memory growth. Call periodically."""
        now = time.monotonic()
        stale_users = [k for k, q in self._user_hits.items() if not q or q[-1] < now - 7200]
        for k in stale_users:
            del self._user_hits[k]
        stale_chats = [k for k, q in self._chat_hits.items() if not q or q[-1] < now - 7200]
        for k in stale_chats:
            del self._chat_hits[k]
        expired_cooldowns = [k for k, v in self._cooldowns.items() if v < now]
        for k in expired_cooldowns:
            del self._cooldowns[k]

    def status(self, user_id: str) -> dict:
        """Get rate limit status for a user."""
        now = time.monotonic()
        user_q = self._user_hits.get(user_id, deque())
        self._prune(user_q, now, 60)
        hour_q = self._user_hits.get(f"{user_id}:hour", deque())
        self._prune(hour_q, now, 3600)
        cooldown_remaining = max(0, self._cooldowns.get(user_id, 0) - now)

        return {
            "per_minute": f"{len(user_q)}/{self.per_user_per_minute}",
            "per_hour": f"{len(hour_q)}/{self.per_user_per_hour}",
            "cooldown_remaining": int(cooldown_remaining),
        }
