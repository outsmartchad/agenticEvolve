"""Absorb orchestrator — deep scan, analyze gaps, and implement improvements.

Unlike /learn (which reports) and /evolve (which scans signals), /absorb
takes a specific target and actually modifies our system to absorb its
strengths.

Stages:
  1. SCAN      — deep read target (clone repo, read source, understand architecture)
  2. GAP       — compare against our system, identify what we're missing or doing worse
  3. PLAN      — concrete file-level implementation plan
  4. IMPLEMENT — execute changes via claude -p with full tool access
  5. REPORT    — summary of what was absorbed, files changed, learnings stored

Safety:
  - All changes are made to ~/.agenticEvolve/ (our system) or ~/.claude/skills/
  - Changes are logged in the learnings DB
  - Gateway is NOT auto-restarted (user must restart manually or via /heartbeat)
"""
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("agenticEvolve.absorb")

# ── Loop detection ────────────────────────────────────────────────────────────

MAX_TOOL_CALLS = 30  # configurable ceiling per absorb run
MAX_IDENTICAL_CALLS = 3  # raise AbsorbLoopError after this many repeated calls


class AbsorbLoopError(Exception):
    """Raised when the absorb pipeline detects a repeated tool-call loop."""
    def __init__(self, tool_name: str, args_preview: str, count: int):
        self.tool_name = tool_name
        self.args_preview = args_preview
        self.count = count
        super().__init__(
            f"Loop detected: {tool_name}({args_preview}) called {count}x"
        )


class ToolCallTracker:
    """Tracks (tool_name, args_hash) pairs to detect repeated calls."""

    def __init__(self, max_identical: int = MAX_IDENTICAL_CALLS,
                 max_total: int = MAX_TOOL_CALLS):
        self._counts: dict[str, int] = {}
        self._total = 0
        self.max_identical = max_identical
        self.max_total = max_total

    def record(self, tool_name: str, args: object) -> None:
        """Record a tool call. Raises AbsorbLoopError if limits are exceeded."""
        self._total += 1
        if self._total > self.max_total:
            raise AbsorbLoopError(tool_name, str(args)[:60], self._total)

        args_hash = hashlib.sha256(
            json.dumps(args, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        key = f"{tool_name}:{args_hash}"
        self._counts[key] = self._counts.get(key, 0) + 1

        if self._counts[key] >= self.max_identical:
            raise AbsorbLoopError(tool_name, str(args)[:60], self._counts[key])

    @property
    def total(self) -> int:
        return self._total


# ── Fetch helper ──────────────────────────────────────────────────────────────

def _fetch_with_retry(url: str, max_attempts: int = 2,
                      backoff: float = 2.0) -> str | None:
    """Fetch a URL with retry cap. Returns content or None on failure.

    Wraps requests.get with a ceiling so fetch loops have a hard stop.
    Failed URLs are logged; callers should mark them fetch_failed and continue.
    """
    try:
        import requests
    except ImportError:
        log.warning("[absorb] requests not installed — fetch skipped for %s", url)
        return None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.warning("[absorb] fetch attempt %d/%d failed for %s: %s",
                        attempt, max_attempts, url, exc)
            if attempt < max_attempts:
                time.sleep(backoff)

    log.error("[absorb] fetch_with_retry: all %d attempts failed for %s",
              max_attempts, url)
    return None

EXODIR = Path.home() / ".agenticEvolve"
SKILLS_DIR = Path.home() / ".claude" / "skills"

# Our system files that the absorb agent can read/modify
OUR_SYSTEM_FILES = """
Key files in our system (~/.agenticEvolve/):
  gateway/run.py          — GatewayRunner, main event loop, session routing, cron scheduler
  gateway/agent.py        — Claude Code wrapper (invoke_claude, invoke_claude_streaming, build_system_prompt)
  gateway/session_db.py   — SQLite+FTS5 for sessions + learnings persistence
  gateway/evolve.py       — 5-stage evolve pipeline (COLLECT→ANALYZE→BUILD→REVIEW→REPORT)
  gateway/absorb.py       — this absorb pipeline
  gateway/gc.py           — garbage collection (stale sessions, orphan skills, memory, logs)
  gateway/config.py       — YAML + .env config loader
  gateway/platforms/base.py       — BasePlatformAdapter ABC
  gateway/platforms/telegram.py   — Telegram adapter (~950 lines, 20+ commands)
  gateway/platforms/discord.py    — Discord adapter (untested)
  gateway/platforms/whatsapp.py   — WhatsApp adapter (untested)
  memory/MEMORY.md        — agent's bounded notes (2200 char limit)
  memory/USER.md          — user profile (1375 char limit)
  memory/sessions.db      — SQLite with FTS5
  SOUL.md                 — agent personality
  AGENTS.md               — project conventions and agent roles
  config.yaml             — settings (model, platforms, cost caps)
  cron/jobs.json          — scheduled jobs

Skills (~/.claude/skills/):
  memory/SKILL.md                  — memory management
  session-search/SKILL.md          — FTS5 session search
  cron-manager/SKILL.md            — job scheduling
  brave-search/SKILL.md            — web search via Brave API
  nah/SKILL.md                     — PreToolUse permission guard
  agent-browser-protocol/SKILL.md  — Chromium browser automation MCP
  unf/SKILL.md                     — auto file versioning daemon
"""


class AbsorbOrchestrator:
    """Runs the absorb pipeline — scan, analyze gaps, plan, implement, report."""

    def __init__(self, target: str, target_type: str,
                 model: str = "sonnet",
                 on_progress: Callable[[str], None] = None,
                 skip_security_scan: bool = False):
        self.target = target
        self.target_type = target_type  # "github", "url", "topic"
        self.model = model
        self.on_progress = on_progress or (lambda x: None)
        self.skip_security_scan = skip_security_scan
        self._cost_total = 0.0
        self._changes_made = []
        # Loop detection
        self._tool_tracker = ToolCallTracker()
        self.loop_detected = False
        self._loop_error: AbsorbLoopError | None = None
        # Fetch state
        self._skipped_urls: list[str] = []
        self._failed_urls: list[str] = []
        # Session state (populated by run())
        self.session_id: str = ""

    def _report(self, msg: str):
        log.info(f"[absorb] {msg}")
        try:
            self.on_progress(msg)
        except Exception:
            pass

    def _check_url_relevance(self, url: str, absorb_goal: str) -> bool:
        """Quick Haiku relevance gate before spending a full Claude invocation.

        Fetches the URL title + first 500 chars, asks Haiku if it's relevant
        to absorb_goal. Returns True (relevant) or False (skip).
        Irrelevant URLs are logged to absorb_skips.jsonl.
        """
        content = _fetch_with_retry(url, max_attempts=2)
        if content is None:
            self._failed_urls.append(url)
            log.warning("[absorb] relevance check: fetch failed for %s", url)
            return False

        snippet = content[:500]

        try:
            from .agent import invoke_claude_streaming
            check = invoke_claude_streaming(
                f"Is this page relevant to: '{absorb_goal}'?\n\nPage content:\n{snippet}\n\nReply with exactly 'yes' or 'no'.",
                model="haiku",
                session_context="[Absorb/relevance-check]",
            )
            answer = check.get("text", "").strip().lower()
            relevant = answer.startswith("yes")
        except Exception as exc:
            log.warning("[absorb] relevance Haiku call failed: %s — defaulting to relevant", exc)
            return True

        if not relevant:
            self._skipped_urls.append(url)
            skip_record = {
                "url": url,
                "goal": absorb_goal,
                "snippet": snippet[:200],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            skip_log = EXODIR / "absorb_skips.jsonl"
            try:
                with open(skip_log, "a") as fh:
                    fh.write(json.dumps(skip_record) + "\n")
            except OSError as exc:
                log.warning("[absorb] could not write absorb_skips.jsonl: %s", exc)
            log.info("[absorb] skipped irrelevant URL: %s", url)

        return relevant

    def _invoke(self, prompt: str, stage: str) -> dict:
        """Invoke Claude with loop-detection guard around the tool tracker."""
        from .agent import invoke_claude_streaming

        self._report(f"*Stage: {stage}*")

        # Record this high-level invoke as a tracked call
        try:
            self._tool_tracker.record("_invoke", {"stage": stage})
        except AbsorbLoopError as err:
            self.loop_detected = True
            self._loop_error = err
            log.error("[absorb] loop detected in _invoke: %s", err)
            return {"text": f"[LOOP DETECTED] {err}", "cost": 0}

        result = invoke_claude_streaming(
            prompt,
            on_progress=self.on_progress,
            model=self.model,
            session_context=f"[Absorb/{stage}: {self.target[:40]}]"
        )

        cost = result.get("cost", 0)
        self._cost_total += cost
        return result

    # ── Security scan ────────────────────────────────────────────

    def _security_scan(self):
        """Scan cloned repo at /tmp/absorb-scan/ for security threats."""
        from .security import scan_directory, format_telegram_report

        scan_path = Path("/tmp/absorb-scan")
        if not scan_path.exists():
            return None

        self._report("*Security scan: scanning cloned repo for threats...*")
        result = scan_directory(scan_path, label=self.target)
        self._report(format_telegram_report(result))
        return result

    def _load_wechat_messages(self) -> str:
        """Load recent WeChat group messages for absorb pipeline."""
        import sqlite3 as _sqlite3
        from pathlib import Path as _Path

        decrypted_dir = _Path.home() / ".agenticEvolve" / "tools" / "wechat-decrypt" / "decrypted"
        if not decrypted_dir.exists():
            return "(No decrypted WeChat DBs found. Run decrypt pipeline first.)"

        # Parse hours from target string (e.g. "wechat --hours 48")
        hours = 24
        parts = self.target.split()
        for i, p in enumerate(parts):
            if p == "--hours" and i + 1 < len(parts):
                try:
                    hours = int(parts[i + 1])
                except ValueError:
                    pass

        # Import collector logic
        import sys
        tools_dir = str(_Path.home() / ".agenticEvolve" / "collectors")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "wechat_collector",
                str(_Path.home() / ".agenticEvolve" / "collectors" / "wechat.py")
            )
            wechat_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wechat_mod)
            signals = wechat_mod.extract_group_messages(decrypted_dir, hours=hours)
        except Exception:
            signals = []

        if not signals:
            return f"(No WeChat group messages in the last {hours} hours)"

        lines = []
        for s in signals:
            meta = s.get("metadata", {})
            lines.append(f"## {meta.get('group_name', 'Unknown group')} "
                         f"({meta.get('message_count', 0)} msgs, "
                         f"{meta.get('unique_senders', 0)} senders)")
            lines.append(s.get("content", ""))
            lines.append("")

        return "\n".join(lines)

    # ── Stage 1: SCAN ────────────────────────────────────────────

    def stage_scan(self) -> dict:
        """Deep scan the target — understand its architecture, patterns, and key decisions."""

        if self.target_type == "wechat":
            # WeChat absorb: read group chat messages and extract knowledge
            wechat_content = self._load_wechat_messages()
            scan_instructions = (
                f"You are reading recent WeChat group chat conversations from the user's own local data.\n\n"
                f"Here are the messages:\n\n{wechat_content}\n\n"
                f"Analyze these conversations deeply:\n"
                f"1. Identify all mentioned tools, libraries, repos, APIs, and techniques\n"
                f"2. Extract key technical insights, opinions, and recommendations\n"
                f"3. Note any URLs shared (GitHub repos, articles, docs)\n"
                f"4. Identify recurring themes and hot topics\n"
                f"5. Find actionable ideas — things Vincent could use or build\n"
            )
        elif self.target_type == "github":
            scan_instructions = (
                f"Clone this repo to /tmp/absorb-scan/ (rm -rf first if exists): {self.target}\n\n"
                f"Then do a DEEP read:\n"
                f"1. Read README.md, ARCHITECTURE.md, AGENTS.md, any design docs\n"
                f"2. Read the core source files — not just the surface, go into the engine\n"
                f"3. Map the full architecture: how components connect, data flows, state management\n"
                f"4. Identify the KEY DESIGN DECISIONS that make this system work well\n"
                f"5. Find patterns that are novel or unusually well-executed\n"
            )
        elif self.target_type == "url":
            scan_instructions = (
                f"Fetch this URL and research deeply: {self.target}\n\n"
                f"1. Read all available content\n"
                f"2. Find the source repo if it exists, clone and read it\n"
                f"3. Understand the architecture and key design decisions\n"
                f"4. Identify patterns that are novel or well-executed\n"
            )
        else:
            scan_instructions = (
                f"Research this technology/architecture deeply: {self.target}\n\n"
                f"1. Find the primary repo, docs, papers, and implementations\n"
                f"2. Clone the best reference implementation to /tmp/absorb-scan/\n"
                f"3. Read the source code — understand HOW it works, not just WHAT it does\n"
                f"4. Map the architecture and key design decisions\n"
                f"5. Identify patterns that are novel or well-executed\n"
            )

        if self.target_type == "wechat":
            prompt = (
                f"You are the SCAN agent for agenticEvolve's /absorb pipeline.\n\n"
                f"{scan_instructions}\n"
                f"Return a structured analysis:\n"
                f"1. TOOLS & REPOS: All tools, libraries, GitHub repos mentioned (with URLs if shared)\n"
                f"2. KEY INSIGHTS: Technical insights, best practices, debugging tips discussed\n"
                f"3. TRENDS: Recurring themes, hot topics, emerging technologies\n"
                f"4. ACTIONABLE IDEAS: Things that could be built, integrated, or learned from\n"
                f"5. NOTABLE OPINIONS: Strong opinions or recommendations from experienced developers\n\n"
                f"Be thorough. Extract maximum knowledge from these conversations.\n"
                f"ALWAYS respond in simplified Chinese (简体中文) since the messages are from Chinese group chats."
            )
        else:
            prompt = (
                f"You are the SCAN agent for agenticEvolve's /absorb pipeline.\n\n"
                f"{scan_instructions}\n"
                f"Return a structured analysis:\n"
                f"1. ARCHITECTURE: How is the system structured? What are the key components?\n"
                f"2. KEY PATTERNS: What design patterns or techniques does it use? (be specific — show code snippets)\n"
                f"3. NOVEL IDEAS: What does this do that's genuinely different or better than common approaches?\n"
                f"4. IMPLEMENTATION DETAILS: Important details about how things are wired together\n\n"
                f"Be thorough. The next stage will compare this against our system to find gaps."
            )

        return self._invoke(prompt, "SCAN")

    # ── Stage 2: GAP ANALYSIS ────────────────────────────────────

    def stage_gap(self, scan_result: dict) -> dict:
        """Compare scanned target against our system, identify gaps and weaknesses."""

        scan_text = scan_result.get("text", "")

        if self.target_type == "wechat":
            prompt = (
                f"You are the GAP ANALYSIS agent for agenticEvolve's /absorb pipeline.\n\n"
                f"The SCAN stage extracted knowledge from WeChat group chats:\n\n"
                f"## Extracted knowledge\n"
                f"{scan_text[:6000]}\n\n"
                f"## Our current system\n"
                f"{OUR_SYSTEM_FILES}\n\n"
                f"Read our system files, then identify GAPS — things mentioned in the chats "
                f"that we could adopt, build, or improve:\n\n"
                f"For each gap:\n"
                f"- WHAT: A tool, technique, pattern, or improvement we should adopt\n"
                f"- WHY IT MATTERS: Why this would make our system or workflow better\n"
                f"- HOW: Concrete approach (new skill, config change, dependency, etc.)\n"
                f"- PRIORITY: high (immediately useful) / medium (worth exploring) / low (interesting FYI)\n\n"
                f"Also store any pure knowledge learnings (tips, warnings, best practices) "
                f"as low-priority gaps with action 'store as learning'.\n\n"
                f"At the END, return a JSON array:\n"
                f"```json\n"
                f'[{{"gap": "description", "why": "impact", "priority": "high|medium|low", "files_affected": ["list"]}}]\n'
                f"```"
            )
        else:
            prompt = (
                f"You are the GAP ANALYSIS agent for agenticEvolve's /absorb pipeline.\n\n"
                f"You have two inputs:\n\n"
                f"## What we scanned\n"
                f"{scan_text[:6000]}\n\n"
                f"## Our current system\n"
                f"{OUR_SYSTEM_FILES}\n\n"
                f"Read our actual source files to understand our current implementation:\n"
                f"- Read ~/.agenticEvolve/gateway/run.py\n"
                f"- Read ~/.agenticEvolve/gateway/agent.py\n"
                f"- Read ~/.agenticEvolve/gateway/session_db.py\n"
                f"- Read ~/.agenticEvolve/gateway/evolve.py\n"
                f"- Read ~/.agenticEvolve/gateway/platforms/telegram.py\n"
                f"- Read ~/.agenticEvolve/SOUL.md\n"
                f"- Read ~/.agenticEvolve/memory/MEMORY.md\n"
                f"- Read any other files needed to understand our system\n\n"
                f"Now identify GAPS — things the scanned target does better or has that we're missing:\n\n"
                f"For each gap:\n"
                f"- WHAT: What's missing or weaker in our system?\n"
                f"- WHY IT MATTERS: Why would fixing this make our system meaningfully better?\n"
                f"- HOW: High-level approach to fixing it\n"
                f"- PRIORITY: high (core weakness) / medium (nice improvement) / low (polish)\n\n"
                f"Be brutally honest. Only list gaps that are REAL and ACTIONABLE.\n"
                f"Skip anything trivial or cosmetic.\n\n"
                f"At the END, return a JSON array:\n"
                f"```json\n"
                f'[{{"gap": "description", "why": "impact", "priority": "high|medium|low", "files_affected": ["list"]}}]\n'
                f"```"
            )

        return self._invoke(prompt, "GAP ANALYSIS")

    # ── Stage 3: PLAN ────────────────────────────────────────────

    def stage_plan(self, gap_result: dict) -> dict:
        """Create concrete file-level implementation plan for high/medium priority gaps."""

        gap_text = gap_result.get("text", "")

        prompt = (
            f"You are the PLANNER agent for agenticEvolve's /absorb pipeline.\n\n"
            f"Gap analysis results:\n{gap_text[:6000]}\n\n"
            f"Our system files:\n{OUR_SYSTEM_FILES}\n\n"
            f"Create a CONCRETE implementation plan for the high and medium priority gaps.\n\n"
            f"For each change:\n"
            f"- FILE: exact path to create or modify\n"
            f"- ACTION: create / modify / extend\n"
            f"- WHAT: specific description of the change (function names, logic, data structures)\n"
            f"- WHY: which gap this addresses\n"
            f"- RISK: what could break (low/medium/high)\n\n"
            f"Rules:\n"
            f"- Do NOT plan changes that would break the running gateway\n"
            f"- Prefer extending existing files over creating new ones\n"
            f"- New features should integrate with existing patterns (async gateway, sync claude -p calls, etc.)\n"
            f"- If a change requires gateway restart, note it\n"
            f"- Max 5 changes per absorb cycle — focus on highest impact\n\n"
            f"At the END, return a JSON array:\n"
            f"```json\n"
            f'[{{"file": "path", "action": "create|modify|extend", "what": "description", "risk": "low|medium|high"}}]\n'
            f"```"
        )

        return self._invoke(prompt, "PLAN")

    # ── Stage 4: IMPLEMENT ───────────────────────────────────────

    def stage_implement(self, plan_result: dict) -> dict:
        """Execute the plan — actually modify our system files."""

        plan_text = plan_result.get("text", "")

        prompt = (
            f"You are the IMPLEMENTER agent for agenticEvolve's /absorb pipeline.\n\n"
            f"Implementation plan:\n{plan_text[:6000]}\n\n"
            f"Our system files:\n{OUR_SYSTEM_FILES}\n\n"
            f"NOW IMPLEMENT THE PLAN. For each planned change:\n"
            f"1. Read the current file\n"
            f"2. Make the changes using the Edit or Write tool\n"
            f"3. Verify the changes are correct (read back if needed)\n\n"
            f"Rules:\n"
            f"- Write clean, production-quality code\n"
            f"- Follow existing code style (logging via log = logging.getLogger, async/await for gateway, etc.)\n"
            f"- Add docstrings for new functions\n"
            f"- Do NOT break existing functionality — extend, don't rewrite\n"
            f"- Do NOT modify .env or config.yaml\n"
            f"- Do NOT restart the gateway\n"
            f"- If creating a new skill, install it directly to ~/.claude/skills/<name>/SKILL.md\n\n"

            f"## Skill-Creator Standards (if creating or modifying skills):\n"
            f"When creating SKILL.md files, follow these quality standards:\n"
            f"- **Description**: Must include a 'Use when...' clause listing specific user phrases and contexts "
            f"that should trigger the skill. Be slightly 'pushy' to avoid undertriggering.\n"
            f"- **Progressive disclosure**: Keep SKILL.md under 500 lines. Put heavy docs in references/ subdirectory.\n"
            f"- **Explain the why**: Use reasoning over rigid MUSTs. Models respond better to understanding intent.\n"
            f"- **allowed-tools**: Use specific patterns (e.g., `Bash(npm *)`) not broad globs like `Bash(*)`. "
            f"Omit Bash entirely if the skill only needs Read/Edit/Write.\n"
            f"- **disable-model-invocation: true**: Add this for skills that should only run when explicitly invoked "
            f"(install/config tools, not general-purpose skills).\n"
            f"- **Source attribution**: End with `Source: <url>` line.\n"
            f"- **Security**: No hardcoded secrets, no placeholder values, no destructive commands without guards.\n\n"

            f"After implementing, list every file you changed and what you did.\n\n"
            f"At the END, return a JSON array of changes:\n"
            f"```json\n"
            f'[{{"file": "path", "action": "created|modified", "summary": "what changed"}}]\n'
            f"```"
        )

        return self._invoke(prompt, "IMPLEMENT")

    # ── Stage 5: REPORT ──────────────────────────────────────────

    def _emit_loop_incident(self) -> None:
        """Send a structured loop incident summary to the progress channel.

        Called at the end of REPORT stage when loop_detected=True.
        Surfaces the loop to Vincent proactively instead of silent failure.
        """
        if not self._loop_error:
            return
        err = self._loop_error
        lines = [
            f"⚠️ *Absorb loop detected*",
            f"  Session: `{self.session_id or 'unknown'}`",
            f"  Repeated: `{err.tool_name}({err.args_preview})` — {err.count}x",
            f"  Skipped to REPORT stage.",
        ]
        if self._skipped_urls:
            lines.append(f"  Skipped URLs: {len(self._skipped_urls)}")
        lines.append(f"  Review: `~/.agenticEvolve/absorb_skips.jsonl`")
        self._report("\n".join(lines))

    def generate_report(self, scan_result: dict, gap_result: dict,
                        plan_result: dict, impl_result: dict) -> str:
        """Generate final absorb report, including loop incident if detected."""
        lines = [f"*Absorb complete: {self.target}*\n"]

        # Loop incident — emit to progress channel and include in report
        if self.loop_detected:
            self._emit_loop_incident()
            err = self._loop_error
            lines.append(
                f"⚠️ *Loop detected during run* — "
                f"`{err.tool_name}` called {err.count}x. "
                f"Pipeline skipped to REPORT."
            )
            lines.append("")

        # Parse implementation changes
        impl_text = impl_result.get("text", "")
        changes = []
        try:
            json_start = impl_text.rfind("```json")
            json_end = impl_text.rfind("```", json_start + 7) if json_start >= 0 else -1
            if json_start >= 0 and json_end > json_start:
                changes = json.loads(impl_text[json_start + 7:json_end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

        if changes:
            lines.append(f"*Changes made ({len(changes)}):*")
            for c in changes:
                lines.append(f"  `{c.get('file', '?')}` — {c.get('summary', c.get('action', '?'))}")
            lines.append("")
        else:
            lines.append("No file changes detected in implementation output.")
            lines.append("")

        # Parse gaps addressed
        gap_text = gap_result.get("text", "")
        gaps = []
        try:
            json_start = gap_text.rfind("```json")
            json_end = gap_text.rfind("```", json_start + 7) if json_start >= 0 else -1
            if json_start >= 0 and json_end > json_start:
                gaps = json.loads(gap_text[json_start + 7:json_end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

        if gaps:
            high = [g for g in gaps if g.get("priority") == "high"]
            medium = [g for g in gaps if g.get("priority") == "medium"]
            low = [g for g in gaps if g.get("priority") == "low"]
            lines.append(f"*Gaps identified:* {len(high)} high, {len(medium)} medium, {len(low)} low")
            for g in gaps:
                lines.append(f"  [{g.get('priority', '?')}] {g.get('gap', '?')}")
            lines.append("")

        lines.append(f"*Cost:* ${self._cost_total:.2f}")
        lines.append(f"\nRestart gateway to activate changes: send any message or use `/heartbeat`")
        return "\n".join(lines)

    # ── Full pipeline ────────────────────────────────────────────

    def _dry_run_report(self, scan_result: dict, gap_result: dict) -> str:
        """Report for dry run — shows gaps found without planning/implementing."""
        lines = [f"*Absorb dry run: {self.target}*\n"]

        # Parse gaps
        gap_text = gap_result.get("text", "")
        gaps = []
        try:
            json_start = gap_text.rfind("```json")
            json_end = gap_text.rfind("```", json_start + 7) if json_start >= 0 else -1
            if json_start >= 0 and json_end > json_start:
                gaps = json.loads(gap_text[json_start + 7:json_end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

        if gaps:
            high = [g for g in gaps if g.get("priority") == "high"]
            medium = [g for g in gaps if g.get("priority") == "medium"]
            low = [g for g in gaps if g.get("priority") == "low"]

            if high:
                lines.append(f"*High priority gaps ({len(high)}):*")
                for g in high:
                    lines.append(f"  {g.get('gap', '?')}")
                    if g.get('why'):
                        lines.append(f"    ↳ {g['why']}")
                    if g.get('files_affected'):
                        lines.append(f"    Files: {', '.join(g['files_affected'])}")
                lines.append("")

            if medium:
                lines.append(f"*Medium priority gaps ({len(medium)}):*")
                for g in medium:
                    lines.append(f"  {g.get('gap', '?')}")
                    if g.get('why'):
                        lines.append(f"    ↳ {g['why']}")
                lines.append("")

            if low:
                lines.append(f"*Low priority gaps ({len(low)}):*")
                for g in low:
                    lines.append(f"  {g.get('gap', '?')}")
                lines.append("")
        else:
            lines.append("No gaps identified. Our system may already cover this well.")
            lines.append("")

        lines.append(f"*Cost so far:* ${self._cost_total:.2f}")
        lines.append(f"\nRun `/absorb {self.target}` to execute PLAN → IMPLEMENT.")
        return "\n".join(lines)

    def run(self, dry_run: bool = False) -> tuple[str, float]:
        """Run the absorb pipeline. If dry_run, stops after GAP analysis.

        Loop detection is active throughout. If AbsorbLoopError is raised
        in any stage, the pipeline skips directly to REPORT with
        loop_detected=True so the incident is surfaced rather than silently
        failing or retrying indefinitely.
        """
        import uuid
        self.session_id = str(uuid.uuid4())[:8]

        mode = "DRY RUN" if dry_run else "full"
        self._report(f"*Absorbing ({mode}): {self.target}*")
        if dry_run:
            self._report("Stages: SCAN → GAP (then stop)")
        else:
            self._report("Stages: SCAN → GAP → PLAN → IMPLEMENT → REPORT")
        self._cost_total = 0.0

        # Persist initial absorb state
        from . import session_db as _sdb
        _sdb.save_absorb_state(
            session_id=self.session_id,
            stage="SCAN",
            tool_call_count=self._tool_tracker.total,
            loop_detected=False,
            skipped_urls=self._skipped_urls,
        )

        # Stage 1: Deep scan
        scan_result = self.stage_scan()
        if self.loop_detected:
            return self._loop_bailout(scan_result, {}, {}, {})

        # Stage 1.5: Security scan (before any code execution or implementation)
        if self.skip_security_scan:
            self._report("*Security scan: skipped (--skip-security-scan)*")
            security_result = None
        else:
            security_result = self._security_scan()
        if security_result and security_result.verdict == "BLOCKED":
            from .security import format_telegram_report
            report = format_telegram_report(security_result)
            self._report(report)
            return report, self._cost_total

        # Stage 2: Gap analysis against our system
        _sdb.save_absorb_state(
            session_id=self.session_id, stage="GAP",
            tool_call_count=self._tool_tracker.total,
            loop_detected=self.loop_detected, skipped_urls=self._skipped_urls,
        )
        gap_result = self.stage_gap(scan_result)
        if self.loop_detected:
            return self._loop_bailout(scan_result, gap_result, {}, {})

        if dry_run:
            summary = self._dry_run_report(scan_result, gap_result)
            self._report("*Dry run complete. Run `/absorb` without --dry-run to implement.*")
            return summary, self._cost_total

        # Stage 3: Concrete plan
        _sdb.save_absorb_state(
            session_id=self.session_id, stage="PLAN",
            tool_call_count=self._tool_tracker.total,
            loop_detected=self.loop_detected, skipped_urls=self._skipped_urls,
        )
        plan_result = self.stage_plan(gap_result)
        if self.loop_detected:
            return self._loop_bailout(scan_result, gap_result, plan_result, {})

        # Stage 4: Implement
        _sdb.save_absorb_state(
            session_id=self.session_id, stage="IMPLEMENT",
            tool_call_count=self._tool_tracker.total,
            loop_detected=self.loop_detected, skipped_urls=self._skipped_urls,
        )
        impl_result = self.stage_implement(plan_result)

        # Stage 4.5: AgentShield scan (Layer 2) — check ~/.claude/ config after implementation
        if not self.skip_security_scan:
            self._agentshield_scan()

        # Stage 5: Report
        _sdb.save_absorb_state(
            session_id=self.session_id, stage="REPORT",
            tool_call_count=self._tool_tracker.total,
            loop_detected=self.loop_detected, skipped_urls=self._skipped_urls,
        )
        summary = self.generate_report(scan_result, gap_result, plan_result, impl_result)

        self._report("*Absorb pipeline complete.*")
        return summary, self._cost_total

    def _loop_bailout(self, scan_result: dict, gap_result: dict,
                      plan_result: dict, impl_result: dict) -> tuple[str, float]:
        """Skip directly to REPORT when a loop is detected mid-pipeline."""
        log.warning("[absorb] bailing out to REPORT due to loop detection")
        from . import session_db as _sdb
        _sdb.save_absorb_state(
            session_id=self.session_id, stage="REPORT(loop-bailout)",
            tool_call_count=self._tool_tracker.total,
            loop_detected=True, skipped_urls=self._skipped_urls,
        )
        summary = self.generate_report(scan_result, gap_result, plan_result, impl_result)
        return summary, self._cost_total

    def _agentshield_scan(self):
        """Run AgentShield on ~/.claude/ after absorb implements changes.

        Layer 1: gateway/security.py (pre-implementation repo scan)
        Layer 2: AgentShield (post-implementation config scan)
        """
        import subprocess as sp

        self._report("*AgentShield scan: scanning ~/.claude/ config post-implementation...*")

        try:
            result = sp.run(
                ["npx", "ecc-agentshield", "scan", "--path", str(Path.home() / ".claude"), "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0 and not result.stdout:
                self._report(f"*AgentShield scan: failed to run* ({result.stderr[:200]})")
                return

            output = result.stdout.strip()

            try:
                import json
                scan_data = json.loads(output)
                grade = scan_data.get("grade", "?")
                score = scan_data.get("score", "?")
                findings = scan_data.get("findings", [])
                critical = [f for f in findings if f.get("severity") == "critical"]
                high = [f for f in findings if f.get("severity") == "high"]

                self._report(f"*AgentShield: Grade {grade} ({score}/100)*")

                if critical:
                    self._report(f"  CRITICAL findings: {len(critical)}")
                    for f in critical[:3]:
                        self._report(f"    - {f.get('message', '?')}")
                    self._report("  Review critical findings before using new skills.")
                elif high:
                    self._report(f"  High findings: {len(high)}")
                    for f in high[:3]:
                        self._report(f"    - {f.get('message', '?')}")
                else:
                    self._report("  No critical/high findings. All clear.")

            except (json.JSONDecodeError, ValueError):
                lines = output.splitlines()
                self._report(f"*AgentShield:*\n" + "\n".join(lines[:10]))

        except sp.TimeoutExpired:
            self._report("*AgentShield scan: timed out (120s)*")
        except FileNotFoundError:
            self._report("*AgentShield scan: npx not found — install Node.js*")
        except Exception as e:
            self._report(f"*AgentShield scan: error — {e}*")
