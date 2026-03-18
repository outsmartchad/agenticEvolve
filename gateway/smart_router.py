"""Smart Model Router — per-message complexity scoring for model selection.

13-dimension regex-based complexity scorer inspired by IronClaw's smart_routing.rs.
Routes messages to FLASH/STANDARD/PRO/FRONTIER tiers based on content analysis,
with cascade detection for uncertainty in lower-tier responses.

Phase 1 of the agenticEvolve upgrade plan.
"""
import re
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger("agenticEvolve.smart_router")


# ── Tier definitions ─────────────────────────────────────────────────


class Tier(Enum):
    FLASH = "flash"        # 0-15: greetings, quick lookups
    STANDARD = "standard"  # 16-40: simple writing, comparisons
    PRO = "pro"            # 41-65: multi-step analysis, code review
    FRONTIER = "frontier"  # 66+: security audits, complex reasoning


# ── Observability ────────────────────────────────────────────────────


@dataclass
class RoutingStats:
    """Thread-safe atomic counters for routing observability."""

    total: int = 0
    flash: int = 0
    standard: int = 0
    pro: int = 0
    frontier: int = 0
    cascade_triggered: int = 0
    cascade_escalated: int = 0  # actually used Opus after cascade
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, tier: Tier, cascaded: bool = False) -> None:
        with self._lock:
            self.total += 1
            if tier == Tier.FLASH:
                self.flash += 1
            elif tier == Tier.STANDARD:
                self.standard += 1
            elif tier == Tier.PRO:
                self.pro += 1
            elif tier == Tier.FRONTIER:
                self.frontier += 1
            if cascaded:
                self.cascade_escalated += 1

    def record_cascade_triggered(self) -> None:
        with self._lock:
            self.cascade_triggered += 1

    def record_cascade_escalated(self) -> None:
        with self._lock:
            self.cascade_escalated += 1

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total": self.total,
                "flash": self.flash,
                "standard": self.standard,
                "pro": self.pro,
                "frontier": self.frontier,
                "cascade_triggered": self.cascade_triggered,
                "cascade_escalated": self.cascade_escalated,
            }


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class SmartRouterConfig:
    enabled: bool = True
    cascade_enabled: bool = True
    domain_keywords: list[str] = field(default_factory=list)  # extends defaults


# ── Compiled patterns ────────────────────────────────────────────────

# Dimension regexes (compiled once)
_RE_REASONING_WORDS = re.compile(
    r"\b(analyze|explain|prove|compare|optimize|evaluate|assess|critique"
    r"|derive|justify|reason|deduce|infer|hypothesize)\b",
    re.IGNORECASE,
)

_RE_CODE_KEYWORDS = re.compile(
    r"\b(function|class|import|def|const|let|var|return|async|await)\b",
    re.IGNORECASE,
)
_RE_CODE_BACKTICKS = re.compile(r"```")
_RE_CODE_FILEPATH = re.compile(
    r"(?:[a-zA-Z0-9_\-]+/)+[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+",
)

_RE_MULTI_STEP = re.compile(
    r"(?:step[- ]by[- ]step|first\s.*then|^\d+\.\s|\bplan\b|\boutline\b|\bwalkthrough\b)",
    re.IGNORECASE | re.MULTILINE,
)

_RE_DOMAIN_CRYPTO = re.compile(
    r"\b(solidity|defi|MEV|blockchain|ERC|uniswap|smart\s?contract|onchain"
    r"|web3|ethereum|token|swap|liquidity|yield|staking|airdrop|NFT|DAO|vault)\b",
    re.IGNORECASE,
)
_RE_DOMAIN_TECH = re.compile(
    r"\b(kubernetes|docker|terraform|postgres|redis|nginx|webpack"
    r"|typescript|react|nextjs|prisma|graphql)\b",
    re.IGNORECASE,
)

_RE_CREATIVITY = re.compile(
    r"\b(design|create|imagine|brainstorm|invent|propose|architect"
    r"|prototype|sketch|draft)\b",
    re.IGNORECASE,
)

_RE_OPEN_ENDED = re.compile(
    r"\b(how would|what if|why does|can you explain)\b",
    re.IGNORECASE,
)

_RE_PRECISION = re.compile(
    r"\b(exact|specific|precisely|calculate|compute|measure|quantify)\b",
    re.IGNORECASE,
)
_RE_MATH_SYMBOLS = re.compile(r"[+\-*/=<>\u2264\u2265\u2211\u222B]")

_RE_CONTEXT_DEP = re.compile(
    r"\b(above|previous|earlier|before|mentioned|said|that|those|these|it)\b",
    re.IGNORECASE,
)

_RE_AMBIGUITY = re.compile(
    r"\b(maybe|perhaps|possibly|not sure|might|could be|uncertain)\b",
    re.IGNORECASE,
)

_RE_TOOL_LIKELIHOOD = re.compile(
    r"\b(run|execute|check|search|find|install|deploy|build|test|debug|fix|refactor)\b",
    re.IGNORECASE,
)

_RE_CONJUNCTIONS = re.compile(
    r"\b(and|but|however|although|whereas|furthermore|moreover|nevertheless)\b",
    re.IGNORECASE,
)

_RE_SAFETY = re.compile(
    r"\b(production|deploy|delete|security|mainnet|credentials|password"
    r"|token|secret|private\s?key|rm\s+-rf)\b",
    re.IGNORECASE,
)

# Explicit tier hints
_RE_HINT = re.compile(
    r"\[tier:(flash|sonnet|opus|frontier)\]",
    re.IGNORECASE,
)

# Pattern overrides (priority classification)
_RE_FLASH_GREETING = re.compile(
    r"^(hi|hello|hey|thanks|ok|yes|no|sure|cool|nice|good|great|thx|ty"
    r"|gm|gn|lol|haha|\u54C8\u54C8|\u597D|\u55EF|\u8C22\u8C22"
    r"|\u65E9\u5B89|\u665A\u5B89)[\s!?.]*$",
    re.IGNORECASE,
)

_RE_FRONTIER_SECURITY = [
    re.compile(r"security.*(audit|review|scan)", re.IGNORECASE),
    re.compile(r"vulnerabilit.*(review|scan|check)", re.IGNORECASE),
    re.compile(r"(analyze|review).*(codebase|architecture|system)", re.IGNORECASE),
]

_RE_PRO_DEPLOY = [
    re.compile(r"deploy.*(mainnet|production)", re.IGNORECASE),
    re.compile(r"production.*(deploy|release|push)", re.IGNORECASE),
]

# Cascade uncertainty patterns
_UNCERTAINTY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"I'm not sure",
        r"I cannot determine",
        r"I don't have enough",
        r"this requires more analysis",
        r"beyond my (current )?capabilities",
        r"I would need more (context|information)",
        r"it's difficult to say",
        r"I can't confidently",
        r"unclear without more",
    ]
]


# ── Dimension weights ────────────────────────────────────────────────

_DIMENSION_WEIGHTS: dict[str, float] = {
    "reasoning_words":     0.14,
    "token_estimate":      0.12,
    "code_indicators":     0.10,
    "multi_step":          0.10,
    "domain_specific":     0.10,
    "creativity":          0.07,
    "question_complexity": 0.07,
    "precision":           0.06,
    "context_dependency":  0.05,
    "ambiguity":           0.05,
    "tool_likelihood":     0.05,
    "sentence_complexity": 0.05,
    "safety_sensitivity":  0.04,
}


# ── SmartRouter ──────────────────────────────────────────────────────


class SmartRouter:
    """Per-message complexity scorer and model router."""

    def __init__(self, config: dict | None = None):
        raw = (config or {}).get("smart_routing", {})
        self.config = SmartRouterConfig(
            enabled=raw.get("enabled", True),
            cascade_enabled=raw.get("cascade_enabled", True),
            domain_keywords=raw.get("domain_keywords", []),
        )
        self.stats = RoutingStats()

        # Build extended domain regex if extra keywords provided
        self._extra_domain_re: Optional[re.Pattern] = None
        if self.config.domain_keywords:
            escaped = [re.escape(k) for k in self.config.domain_keywords]
            self._extra_domain_re = re.compile(
                r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE
            )

    # ── Dimension scorers ────────────────────────────────────

    def _score_reasoning_words(self, text: str) -> int:
        matches = len(_RE_REASONING_WORDS.findall(text))
        return min(100, matches * 50)

    def _score_token_estimate(self, text: str) -> int:
        return min(100, max(0, (len(text) - 20)) // 5)

    def _score_code_indicators(self, text: str) -> int:
        matches = (
            len(_RE_CODE_BACKTICKS.findall(text))
            + len(_RE_CODE_KEYWORDS.findall(text))
            + len(_RE_CODE_FILEPATH.findall(text))
        )
        return min(100, matches * 50)

    def _score_multi_step(self, text: str) -> int:
        matches = len(_RE_MULTI_STEP.findall(text))
        return min(100, matches * 50)

    def _score_domain_specific(self, text: str) -> int:
        matches = (
            len(_RE_DOMAIN_CRYPTO.findall(text))
            + len(_RE_DOMAIN_TECH.findall(text))
        )
        if self._extra_domain_re:
            matches += len(self._extra_domain_re.findall(text))
        return min(100, matches * 50)

    def _score_creativity(self, text: str) -> int:
        matches = len(_RE_CREATIVITY.findall(text))
        return min(100, matches * 50)

    def _score_question_complexity(self, text: str) -> int:
        question_marks = text.count("?")
        open_ended = len(_RE_OPEN_ENDED.findall(text))
        return min(100, question_marks * 20 + open_ended * 25)

    def _score_precision(self, text: str) -> int:
        matches = (
            len(_RE_PRECISION.findall(text))
            + len(_RE_MATH_SYMBOLS.findall(text))
        )
        return min(100, matches * 50)

    def _score_context_dependency(self, text: str) -> int:
        matches = len(_RE_CONTEXT_DEP.findall(text))
        return min(100, matches * 50)

    def _score_ambiguity(self, text: str) -> int:
        matches = len(_RE_AMBIGUITY.findall(text))
        return min(100, matches * 25)

    def _score_tool_likelihood(self, text: str) -> int:
        matches = len(_RE_TOOL_LIKELIHOOD.findall(text))
        return min(100, matches * 50)

    def _score_sentence_complexity(self, text: str) -> int:
        commas = text.count(",")
        semicolons = text.count(";")
        conjunctions = len(_RE_CONJUNCTIONS.findall(text))
        return min(100, (commas + semicolons * 2 + conjunctions) * 12)

    def _score_safety_sensitivity(self, text: str) -> int:
        matches = len(_RE_SAFETY.findall(text))
        return min(100, matches * 50)

    # ── Scoring engine ───────────────────────────────────────

    _DIMENSION_SCORERS = {
        "reasoning_words":     "_score_reasoning_words",
        "token_estimate":      "_score_token_estimate",
        "code_indicators":     "_score_code_indicators",
        "multi_step":          "_score_multi_step",
        "domain_specific":     "_score_domain_specific",
        "creativity":          "_score_creativity",
        "question_complexity": "_score_question_complexity",
        "precision":           "_score_precision",
        "context_dependency":  "_score_context_dependency",
        "ambiguity":           "_score_ambiguity",
        "tool_likelihood":     "_score_tool_likelihood",
        "sentence_complexity": "_score_sentence_complexity",
        "safety_sensitivity":  "_score_safety_sensitivity",
    }

    def score(self, text: str) -> tuple[int, dict[str, int]]:
        """Score a message across 13 dimensions. Returns (total, dimension_scores)."""
        text = text or ""
        dimension_scores: dict[str, int] = {}
        for dim, method_name in self._DIMENSION_SCORERS.items():
            scorer = getattr(self, method_name)
            dimension_scores[dim] = scorer(text)

        # Weighted sum
        total = sum(
            dimension_scores[dim] * _DIMENSION_WEIGHTS[dim]
            for dim in _DIMENSION_WEIGHTS
        )

        # Multi-dimensional boost
        triggered = sum(1 for s in dimension_scores.values() if s > 20)
        if triggered >= 3:
            total *= 1.3
        elif triggered >= 2:
            total *= 1.15

        total = min(100, int(total))
        return total, dimension_scores

    # ── Classification ───────────────────────────────────────

    def classify(self, text: str) -> Tier:
        """Classify a message into a routing tier.

        Priority:
        1. Explicit hints [tier:flash], [tier:sonnet], etc.
        2. Pattern overrides (greetings -> Flash, security audit -> Frontier)
        3. Score-based thresholds
        """
        text = text or ""
        # 1. Explicit hints
        hint_match = _RE_HINT.search(text)
        if hint_match:
            hint = hint_match.group(1).lower()
            if hint == "flash":
                return Tier.FLASH
            elif hint == "sonnet":
                return Tier.STANDARD
            elif hint == "opus":
                return Tier.FRONTIER
            elif hint == "frontier":
                return Tier.FRONTIER

        # 2. Pattern overrides — Flash (greetings)
        if _RE_FLASH_GREETING.match(text.strip()):
            return Tier.FLASH

        # 2. Pattern overrides — Frontier (security / architecture)
        for pattern in _RE_FRONTIER_SECURITY:
            if pattern.search(text):
                return Tier.FRONTIER

        # 2. Pattern overrides — Pro (deployment)
        for pattern in _RE_PRO_DEPLOY:
            if pattern.search(text):
                return Tier.PRO

        # 3. Score-based
        total, _ = self.score(text)
        if total <= 15:
            return Tier.FLASH
        elif total <= 40:
            return Tier.STANDARD
        elif total <= 65:
            return Tier.PRO
        else:
            return Tier.FRONTIER

    # ── Model selection ──────────────────────────────────────

    def select_model(self, text: str, config: dict) -> tuple[str, Tier, bool]:
        """Select the model for a message.

        Returns (model_name, tier, cascade_enabled).
        """
        tier = self.classify(text)

        if tier in (Tier.FLASH, Tier.STANDARD):
            model = config.get("serve_model", config.get("model", "sonnet"))
            return model, tier, False
        elif tier == Tier.PRO:
            model = config.get("serve_model", config.get("model", "sonnet"))
            cascade = self.config.cascade_enabled
            return model, tier, cascade
        else:  # FRONTIER
            model = config.get(
                "serve_reasoning_model", config.get("model", "sonnet")
            )
            return model, tier, False

    # ── Cascade detection ────────────────────────────────────

    def should_cascade(self, response_text: str) -> bool:
        """Check if a Sonnet response indicates uncertainty, warranting Opus retry.

        Only checks the first 500 chars of the response.
        """
        text_start = response_text[:500]
        return any(p.search(text_start) for p in _UNCERTAINTY_PATTERNS)
