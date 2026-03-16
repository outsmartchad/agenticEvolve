"""Evolve orchestrator — multi-stage pipeline with review gate.

Stages:
  1. COLLECT  — run signal collectors (bash scripts)
  2. ANALYZE  — score signals, pick top candidates
  2.5 RETRO   — mandatory reflection: what failed, what's missing, what regressed
  3. BUILD    — create skills in queue (NOT installed yet)
  4. REVIEW   — separate agent validates quality, security, correctness
  5. REPORT   — summary with pending approvals

Skills go to ~/.agenticEvolve/skills-queue/<name>/ and require
human approval via /approve <name> before installing to ~/.claude/skills/.
"""
import hashlib
import json
import logging
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("agenticEvolve.evolve")

EXODIR = Path.home() / ".agenticEvolve"
QUEUE_DIR = EXODIR / "skills-queue"
SKILLS_DIR = Path.home() / ".claude" / "skills"
SIGNALS_DIR = EXODIR / "signals"
COLLECTORS_DIR = EXODIR / "collectors"

# Per-stage tool allowlists — enforces least-privilege on read-only stages.
# Stages not listed here (BUILD, COLLECT) get None → full access (--dangerously-skip-permissions).
STAGE_TOOLS: dict[str, list[str]] = {
    "ANALYZE": ["Read", "Bash", "Glob", "Grep"],
    "REVIEW": ["Read", "Glob", "Grep"],
}

# Per-stage model overrides — cheaper models for classification/read-only tasks.
# ANALYZE and REVIEW are classification-only; Haiku handles them at ~20x lower cost.
# BUILD uses the orchestrator's default model (sonnet). COLLECT has no LLM call.
STAGE_MODELS: dict[str, str] = {
    "ANALYZE": "claude-haiku-4-5-20251001",
    "REVIEW":  "claude-sonnet-4-6",
}


class EvolveOrchestrator:
    """Runs the evolve pipeline stage by stage, reporting progress."""

    def __init__(self, model: str = "sonnet",
                 on_progress: Callable[[str], None] = None,
                 skip_security_scan: bool = False):
        self.model = model
        self.on_progress = on_progress or (lambda x: None)
        self.skip_security_scan = skip_security_scan
        self._cost_total = 0.0
        from .session_db import generate_trace_id
        self.trace_id: str = generate_trace_id()

    def _report(self, msg: str):
        """Send progress update."""
        log.info(f"[evolve] {msg}")
        try:
            self.on_progress(msg)
        except Exception:
            pass

    def _invoke(self, prompt: str, stage: str,
                model_override: str | None = None,
                use_workspace: bool = False) -> dict:
        """Invoke Claude Code for a specific stage.

        Derives the stage key (text before first space or paren) and looks up
        STAGE_TOOLS to enforce per-stage tool allowlists. Stages not in STAGE_TOOLS
        run with full access (--dangerously-skip-permissions).

        Model resolution order:
          1. Explicit model_override argument
          2. STAGE_MODELS lookup for the stage key
          3. self.model (orchestrator default)

        Args:
            use_workspace: If True, run in a UUID-scoped isolated workspace so
                concurrent BUILD tasks cannot clobber each other's skill files.
        """
        from .agent import invoke_claude_streaming

        self._report(f"*Stage: {stage}*")

        # Derive stage key: "REVIEW (name)" → "REVIEW", "BUILD (name)" → "BUILD"
        stage_key = stage.split("(")[0].split()[0].upper()
        allowed_tools = STAGE_TOOLS.get(stage_key)

        # Resolve model: explicit override > stage map > orchestrator default
        model = model_override or STAGE_MODELS.get(stage_key, self.model)
        if model != self.model:
            log.info(f"[evolve] Stage {stage_key}: using model override '{model}'")

        # Pass context_mode if a matching overlay exists for this stage
        context_mode = stage_key.lower()

        result = invoke_claude_streaming(
            prompt,
            on_progress=self.on_progress,
            model=model,
            session_context=f"[Evolve/{stage}] trace={self.trace_id}",
            allowed_tools=allowed_tools,
            context_mode=context_mode,
            use_workspace=use_workspace,
        )

        cost = result.get("cost", 0)
        self._cost_total += cost

        # Audit: record every Claude invocation with outcome
        try:
            from .session_db import log_audit
            log_audit(
                trace_id=self.trace_id,
                stage=stage_key,
                action="invoke_claude",
                result="ok" if result.get("success") else "fail",
                metadata={"model": model, "cost": cost},
            )
        except Exception as _ae:
            log.debug(f"Audit log failed: {_ae}")

        return result

    # ── Stage 1: Collect ─────────────────────────────────────────

    def _run_collector(self, cmd: list[str], name: str, timeout: int = 120,
                       max_retries: int = 1) -> dict:
        """Run a single collector with retry on failure. Returns result dict."""
        import time
        env = {**os.environ, "SIGNALS_DIR": str(SIGNALS_DIR)}

        for attempt in range(max_retries + 1):
            try:
                self._report(f"  Running `{name}`..." + (f" (retry {attempt})" if attempt else ""))
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout,
                    cwd=str(EXODIR), env=env,
                )
                if proc.returncode == 0:
                    self._report(f"  {name} done")
                    return {
                        "success": True,
                        "output": (proc.stdout or proc.stderr or "")[:500],
                        "error": "",
                    }
                else:
                    error = (proc.stderr or "")[:200]
                    if attempt < max_retries:
                        self._report(f"  {name} failed (exit {proc.returncode}), retrying in 5s...")
                        time.sleep(5)
                        continue
                    self._report(f"  {name} failed (exit {proc.returncode})")
                    return {"success": False, "output": "", "error": error}
            except subprocess.TimeoutExpired:
                if attempt < max_retries:
                    self._report(f"  {name} timed out, retrying...")
                    time.sleep(5)
                    continue
                self._report(f"  {name} timed out")
                return {"success": False, "error": "timeout"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "max retries exceeded"}

    def stage_collect(self) -> dict:
        """Run signal collectors and return collected file paths."""
        self._report("Collecting signals from GitHub, HN, X, WeChat groups...")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        signals_today = SIGNALS_DIR / today
        signals_today.mkdir(parents=True, exist_ok=True)

        results = {}

        # Bash collectors
        for collector in ["github.sh", "hackernews.sh", "x-search.sh"]:
            path = COLLECTORS_DIR / collector
            if not path.exists():
                self._report(f"  Skipped {collector} (not found)")
                continue
            name = collector.replace(".sh", "")
            results[name] = self._run_collector(["bash", str(path)], name)

        # Python collectors
        for collector in [
            "wechat.py", "reddit.py", "lobsters.py", "producthunt.py",
            "github-trending.py", "arxiv.py", "huggingface.py", "bestofjs.py",
        ]:
            path = COLLECTORS_DIR / collector
            if not path.exists():
                self._report(f"  Skipped {collector} (not found)")
                continue
            name = collector.replace(".py", "")
            results[name] = self._run_collector(["python3", str(path), "--no-refresh"], name)

        # Count signal files
        signal_files = list(signals_today.glob("*.json")) if signals_today.exists() else []
        self._report(f"  Collected {len(signal_files)} signal files")

        return {"today": today, "signals_dir": str(signals_today),
                "collectors": results, "signal_count": len(signal_files)}

    # ── Stage 2: Analyze ─────────────────────────────────────────

    def _prefilter_signals(self, signals_dir: str, top_n: int = 30) -> list[dict]:
        """Load all signal files and return top N by engagement proxy.

        Ranking heuristic: HN points > GitHub stars > recency.
        Caps input to Haiku at top_n to avoid context dilution.
        """
        signals: list[dict] = []
        sig_path = Path(signals_dir)
        for f in sig_path.glob("*.json"):
            try:
                raw = f.read_text()
                batch = json.loads(raw)
                if isinstance(batch, list):
                    signals.extend(batch)
                elif isinstance(batch, dict):
                    signals.append(batch)
            except (json.JSONDecodeError, OSError):
                pass

        # Deduplicate across sources by URL (persistent SQLite, 7-day TTL), then by title.
        # Falls back to in-memory set if session_db is unavailable.
        # _url_seen_fn(url) -> bool: returns True if already seen, records it if not.
        try:
            from .session_db import signal_url_seen as _db_seen
            _url_seen_fn = _db_seen
        except Exception:
            _mem_seen: set[str] = set()

            def _url_seen_fn(u: str) -> bool:
                if u in _mem_seen:
                    return True
                _mem_seen.add(u)
                return False

        seen_titles: set[str] = set()
        unique: list[dict] = []
        for s in signals:
            url = s.get("url", "").rstrip("/").lower()
            if url and _url_seen_fn(url):
                continue
            title_key = s.get("title", "").lower().strip()
            if title_key and len(title_key) > 15 and title_key in seen_titles:
                continue
            if title_key and len(title_key) > 15:
                seen_titles.add(title_key)
            unique.append(s)

        if len(unique) < len(signals):
            log.info(f"[evolve] Deduped {len(signals)} → {len(unique)} signals")
        signals = unique

        def _rank(s: dict) -> int:
            meta = s.get("metadata", {})
            return (meta.get("points", 0) or meta.get("stars", 0)
                    or meta.get("message_count", 0) or meta.get("replies", 0)
                    or meta.get("likes", 0) or meta.get("stars_today", 0))

        signals.sort(key=_rank, reverse=True)
        return signals[:top_n]

    def stage_analyze(self, collect_result: dict) -> dict:
        """Analyze signals and score them. Returns top candidates."""
        signals_dir = collect_result.get("signals_dir", "")

        top_signals = self._prefilter_signals(signals_dir, top_n=30)
        self._report(f"  Pre-filtered to {len(top_signals)} top signals for scoring")

        signals_json = json.dumps(top_signals, indent=2)

        prompt = (
            "You are the ANALYZER agent in the agenticEvolve pipeline.\n\n"
            "Below are the top signals collected today (pre-ranked by engagement).\n\n"
            f"```json\n{signals_json}\n```\n\n"
            "Signals may come from GitHub, HN, X, or WeChat group chats.\n"
            "WeChat group signals contain real developer conversations — extract mentioned\n"
            "repos, tools, techniques, and ideas from the chat content.\n\n"
            "For each signal, evaluate on a 0-9 scale:\n"
            "  - RELEVANCE: Is this useful for AI agents, TypeScript, React, or developer tooling?\n"
            "  - NOVELTY: Is this genuinely new, or a rehash of known tools?\n"
            "  - ACTIONABILITY: Can we use this RIGHT NOW to improve our workflow?\n\n"
            "Compute a composite score: (relevance + novelty + actionability) / 3\n\n"
            "Return ONLY a JSON array of the top candidates (score >= 7.0):\n"
            "```json\n"
            "[\n"
            '  {"name": "tool-name", "source": "github|hn|x", "score": 8.3, '
            '"summary": "one-line description", "url": "...", '
            '"skill_idea": "what a Claude Code skill for this would do"}\n'
            "]\n"
            "```\n\n"
            "If nothing scores >= 7.0, return an empty array `[]`.\n"
            "Do NOT create any files. ONLY analyze and return JSON."
        )

        result = self._invoke(prompt, "ANALYZE")
        text = result.get("text", "[]")

        # Try to extract JSON array from response
        candidates = []
        try:
            # Find JSON array in response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                candidates = json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            log.warning(f"Failed to parse analyzer output as JSON: {text[:200]}")

        self._report(f"  Found {len(candidates)} candidates scoring >= 7.0")
        return {"candidates": candidates, "raw": text}

    # ── Stage 3: Build ───────────────────────────────────────────

    def stage_build(self, analyze_result: dict) -> dict:
        """Build skills for top candidates — into QUEUE, not installed.

        Uses patterns from the official skill-creator plugin:
        - Pushy descriptions with "Use when..." trigger clauses
        - Progressive disclosure (SKILL.md < 500 lines, heavy docs in references/)
        - Explain the "why" instead of rigid MUSTs
        - Source attribution at bottom
        """
        candidates = analyze_result.get("candidates", [])
        if not candidates:
            self._report("  No candidates to build. Skipping.")
            return {"built": []}

        # Only build top 3 — run concurrently for 3× wall-clock speedup.
        # A BoundedSemaphore caps concurrent Claude invocations at 3 structurally,
        # not just by prompt instruction.
        candidates = candidates[:3]
        built: list[dict] = []
        _build_semaphore = threading.BoundedSemaphore(3)

        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        def _build_candidate(candidate: dict) -> dict | None:
            """Build a single skill candidate. Returns built-entry dict or None."""
            name = candidate.get("name", "unknown").lower().replace(" ", "-")
            summary = candidate.get("summary", "")
            skill_idea = candidate.get("skill_idea", summary)
            url = candidate.get("url", "")
            score = candidate.get("score", 0)

            skill_dir = QUEUE_DIR / name
            if skill_dir.exists():
                self._report(f"  {name}: already in queue, skipping")
                return None

            if (SKILLS_DIR / name / "SKILL.md").exists():
                self._report(f"  {name}: already installed, skipping")
                return None

            prompt = (
                f"You are the BUILDER agent in the agenticEvolve pipeline.\n\n"
                f"Build a Claude Code skill for: {name}\n"
                f"Summary: {summary}\n"
                f"URL: {url}\n"
                f"Skill idea: {skill_idea}\n\n"
                f"Create the skill file at: {skill_dir}/SKILL.md\n\n"

                f"## Skill-Creator Quality Standards\n\n"

                f"### YAML Frontmatter (required fields):\n"
                f"- `name`: lowercase, hyphenated identifier\n"
                f"- `description`: This is the PRIMARY trigger mechanism. It must include:\n"
                f"  1. What the skill does (concise)\n"
                f"  2. A 'Use when...' clause listing specific user phrases and contexts that should trigger it\n"
                f"  3. Be slightly 'pushy' — lean toward triggering rather than undertriggering\n"
                f"  Example: 'Deploy apps to cloud providers. Use when the user mentions deploying, hosting, "
                f"pushing to production, setting up CI/CD, or wants to get their app online, even if they "
                f"don\\'t say \"deploy\" explicitly.'\n"
                f"- `argument-hint`: show example invocation pattern\n"
                f"- `allowed-tools`: minimum tools needed (prefer specific patterns over broad globs)\n"
                f"- `disable-model-invocation: true` if the skill should only run when explicitly invoked\n\n"

                f"### SKILL.md Body:\n"
                f"- Keep under 100 lines (ideal for queue skills; 500 lines is the hard max)\n"
                f"- Use imperative form in instructions\n"
                f"- Explain WHY things are important rather than using heavy-handed MUSTs\n"
                f"- Include concrete examples with Input/Output where helpful\n"
                f"- If the tool requires installation, include the install command first\n"
                f"- End with a `Source: <url>` line for attribution\n\n"

                f"### Progressive Disclosure:\n"
                f"- Level 1 (always loaded): name + description in frontmatter (~100 words)\n"
                f"- Level 2 (on trigger): SKILL.md body (the instructions)\n"
                f"- Level 3 (as needed): bundled resources in references/, scripts/, assets/\n"
                f"- If the skill needs extensive docs, put them in a `references/` subdirectory "
                f"and reference them from SKILL.md with guidance on when to read them\n\n"

                f"### Security:\n"
                f"- No hardcoded API keys, tokens, secrets, or credentials\n"
                f"- No placeholder values — only real, working instructions\n"
                f"- Nothing destructive without explicit guards\n\n"

                f"Use absolute paths only — the workspace cwd is isolated.\n"
                f"Create ONLY the SKILL.md file (and references/ if needed). Nothing else."
            )

            with _build_semaphore:
                self._invoke(prompt, f"BUILD ({name})", use_workspace=True)

            if (skill_dir / "SKILL.md").exists():
                self._report(f"  Built: {name} (score {score})")
                return {"name": name, "summary": summary, "score": score,
                        "path": str(skill_dir / "SKILL.md")}
            else:
                self._report(f"  Failed to build: {name}")
                return None

        # Run up to 3 build tasks concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_build_candidate, c): c for c in candidates}
            for future in as_completed(futures):
                try:
                    entry = future.result()
                    if entry:
                        built.append(entry)
                except Exception as e:
                    name = futures[future].get("name", "?")
                    log.error(f"BUILD ({name}) raised: {e}")
                    self._report(f"  Error building {name}: {e}")

        return {"built": built}

    # ── Stage 4: Review ──────────────────────────────────────────

    def stage_review(self, build_result: dict) -> dict:
        """Review agent validates each built skill. Includes security scan. READ-ONLY — does not modify."""
        built = build_result.get("built", [])
        if not built:
            return {"reviewed": []}

        # Security scan all built skill files before LLM review
        from .security import scan_file, format_telegram_report
        blocked_names = set()
        reviewed = []
        if self.skip_security_scan:
            self._report("*Security scan: skipped (--skip-security-scan)*")
        else:
            for skill in built:
                sec_result = scan_file(skill["path"], label=skill["name"])
                if sec_result.verdict == "BLOCKED":
                    self._report(f"*Security BLOCKED skill `{skill['name']}`*")
                    self._report(format_telegram_report(sec_result))
                    reject_file = Path(skill["path"]).parent / ".rejected"
                    reject_file.write_text(json.dumps({
                        "name": skill["name"],
                        "approved": False,
                        "issues": [f.pattern_desc for f in sec_result.findings if f.severity == "critical"],
                        "summary": "Blocked by security scan — potential malicious content"
                    }, indent=2))
                    reviewed.append({
                        "name": skill["name"], "approved": False,
                        "issues": ["SECURITY: " + f.pattern_desc for f in sec_result.findings if f.severity == "critical"],
                        "summary": "Blocked by automated security scan",
                        "skill_path": skill["path"],
                    })
                    blocked_names.add(skill["name"])

        for skill in built:
            if skill["name"] in blocked_names:
                continue
            name = skill["name"]
            path = skill["path"]

            prompt = (
                f"You are the REVIEWER agent in the agenticEvolve pipeline.\n"
                f"You are READ-ONLY. Do NOT modify any files.\n\n"
                f"Review the skill at: {path}\n\n"
                f"Check for:\n"
                f"1. SECURITY: No hardcoded secrets, API keys, tokens, or credentials\n"
                f"2. QUALITY: Clear instructions, proper YAML frontmatter, under 100 lines\n"
                f"3. CORRECTNESS: Commands and paths are valid, no placeholder values\n"
                f"4. REDUNDANCY: Would this overlap with an existing skill in ~/.claude/skills/?\n"
                f"5. SAFETY: Nothing destructive (rm -rf, force push, etc.) without guards\n\n"
                f"Return ONLY a JSON object:\n"
                f'{{"name": "{name}", "approved": true/false, '
                f'"issues": ["list of issues if any"], '
                f'"summary": "one-line review verdict"}}'
            )

            result = self._invoke(prompt, f"REVIEW ({name})")
            text = result.get("text", "{}")

            # Parse review result
            review = {"name": name, "approved": False, "issues": [], "summary": "Parse failed"}
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    review = json.loads(text[start:end])
            except (json.JSONDecodeError, ValueError):
                review["issues"] = ["Failed to parse reviewer output"]

            review["skill_path"] = path
            reviewed.append(review)

            status = "APPROVED" if review.get("approved") else "REJECTED"
            self._report(f"  {name}: {status} — {review.get('summary', '')}")

            # If reviewer rejected, add a .rejected marker
            if not review.get("approved"):
                reject_file = Path(path).parent / ".rejected"
                reject_file.write_text(json.dumps(review, indent=2))

        return {"reviewed": reviewed}

    # ── Stage 4.75: AgentShield scan (Layer 2) ────────────────────

    def _agentshield_scan(self, auto_installed: list, review_result: dict):
        """Run AgentShield (ecc-agentshield) on ~/.claude/ after skill install.

        Layer 1: gateway/security.py regex scanner (runs on raw skill files before install)
        Layer 2: AgentShield (runs on installed ~/.claude/ config — checks for injection,
                 misconfiguration, and interaction risks between skills/config)
        """
        import subprocess as sp

        self._report("*AgentShield scan: scanning ~/.claude/ config post-install...*")

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

            # Parse JSON output
            try:
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

                    # Rollback: uninstall the skills that were just installed
                    self._report("*Rolling back auto-installed skills due to critical findings...*")
                    for name in auto_installed:
                        skill_dir = Path.home() / ".claude" / "skills" / name
                        if skill_dir.exists():
                            import shutil
                            shutil.rmtree(skill_dir)
                            self._report(f"  Removed: {name}")
                    review_result["auto_installed"] = []
                    review_result["agentshield_rollback"] = True

                elif high:
                    self._report(f"  High findings: {len(high)}")
                    for f in high[:3]:
                        self._report(f"    - {f.get('message', '?')}")
                    self._report("  Skills kept installed — review high findings manually.")

                else:
                    self._report("  No critical/high findings. All clear.")

                review_result["agentshield"] = {"grade": grade, "score": score,
                                                 "critical": len(critical), "high": len(high)}

            except (json.JSONDecodeError, ValueError):
                # Non-JSON output — just report the text summary
                lines = output.splitlines()
                summary = "\n".join(lines[:10])
                self._report(f"*AgentShield output:*\n{summary}")

        except sp.TimeoutExpired:
            self._report("*AgentShield scan: timed out (120s)*")
        except FileNotFoundError:
            self._report("*AgentShield scan: npx not found — install Node.js*")
        except Exception as e:
            self._report(f"*AgentShield scan: error — {e}*")

    # ── Stage 5: Report ──────────────────────────────────────────

    def stage_report(self, collect_result: dict, analyze_result: dict,
                     build_result: dict, review_result: dict) -> str:
        """Generate final summary."""
        lines = ["*Evolution cycle complete*\n"]

        # Collect stats
        collectors = collect_result.get("collectors", {})
        for name, info in collectors.items():
            status = "ok" if info.get("success") else "failed"
            lines.append(f"  {name}: {status}")

        lines.append(f"  Total signals: {collect_result.get('signal_count', 0)}")
        lines.append("")

        # Candidates
        candidates = analyze_result.get("candidates", [])
        if candidates:
            lines.append(f"*Top candidates ({len(candidates)}):*")
            for c in candidates:
                lines.append(f"  {c.get('name')} (score {c.get('score', '?')}): {c.get('summary', '')}")
            lines.append("")

        # Built skills
        built = build_result.get("built", [])
        reviewed = review_result.get("reviewed", [])

        if reviewed:
            auto_installed = review_result.get("auto_installed", [])
            approved = [r for r in reviewed if r.get("approved")]
            rejected = [r for r in reviewed if not r.get("approved")]

            # Show auto-installed skills
            installed_names = set(auto_installed)
            if installed_names:
                lines.append(f"*Auto-installed ({len(installed_names)}):*")
                for name in installed_names:
                    lines.append(f"  {name}")
                lines.append("")

            # Show remaining pending (if auto_approve is off)
            pending = [r for r in approved if r["name"] not in installed_names]
            if pending:
                lines.append(f"*Skills pending approval ({len(pending)}):*")
                for r in pending:
                    lines.append(f"  /approve {r['name']}")
                lines.append("")

            if rejected:
                lines.append(f"*Rejected by reviewer ({len(rejected)}):*")
                for r in rejected:
                    issues = ", ".join(r.get("issues", []))
                    lines.append(f"  {r['name']}: {issues}")
                lines.append("")
        elif not built:
            lines.append("No skills built this cycle.")
            lines.append("")

        lines.append(f"Cost: ${self._cost_total:.2f}")
        return "\n".join(lines)

    # ── Full pipeline ────────────────────────────────────────────

    def run(self, dry_run: bool = False) -> tuple[str, float]:
        """Run the evolve pipeline. If dry_run=True, stops after ANALYZE and shows what would happen."""
        mode = "DRY RUN" if dry_run else "full"
        self._report(f"*Starting evolution cycle ({mode})... [trace={self.trace_id}]*")
        self._cost_total = 0.0

        # Audit: pipeline start
        try:
            from .session_db import log_audit
            log_audit(
                trace_id=self.trace_id,
                stage="PIPELINE",
                action="start",
                result="ok",
                metadata={"mode": mode, "model": self.model},
            )
        except Exception as _ae:
            log.debug(f"Audit log failed: {_ae}")

        # Stage 1
        collect_result = self.stage_collect()

        # Stage 2
        analyze_result = self.stage_analyze(collect_result)

        if dry_run:
            summary = self._dry_run_report(collect_result, analyze_result)
            self._report("*Dry run complete. Run `/evolve` to execute.*")
            return summary, self._cost_total

        # Stage 2.5: Retro — reflect before building
        try:
            from .retro import run_retro
            analyze_summary = "\n".join(
                f"- {c.get('name')} (score {c.get('score')}): {c.get('summary', '')}"
                for c in analyze_result.get("candidates", [])
            ) or "No candidates found."
            retro_text, retro_cost = run_retro(
                "evolve", analyze_summary,
                on_progress=self.on_progress,
                model=STAGE_MODELS.get("ANALYZE", self.model),
            )
            self._cost_total += retro_cost
            self._report(f"*Retro*\n{retro_text}")
        except Exception as e:
            log.warning(f"Retro stage failed (non-fatal): {e}")

        # Stage 3
        build_result = self.stage_build(analyze_result)

        # Stage 4
        review_result = self.stage_review(build_result)

        # Stage 4.5: Auto-install approved skills if config allows
        from .config import load_config
        cfg = load_config()
        if cfg.get("auto_approve_skills", False):
            auto_installed = []
            for r in review_result.get("reviewed", []):
                if r.get("approved"):
                    ok, msg = approve_skill(r["name"])
                    if ok:
                        auto_installed.append(r["name"])
                        self._report(f"  Auto-installed: {r['name']}")
                    else:
                        self._report(f"  Auto-install failed for {r['name']}: {msg}")
            review_result["auto_installed"] = auto_installed

            # Stage 4.75: AgentShield scan on ~/.claude/ after skill install (Layer 2 security)
            if auto_installed and not self.skip_security_scan:
                self._agentshield_scan(auto_installed, review_result)

        # Stage 5
        summary = self.stage_report(collect_result, analyze_result,
                                     build_result, review_result)

        # Audit: pipeline complete
        try:
            from .session_db import log_audit
            log_audit(
                trace_id=self.trace_id,
                stage="PIPELINE",
                action="complete",
                result="ok",
                metadata={"total_cost": self._cost_total},
            )
        except Exception as _ae:
            log.debug(f"Audit log failed: {_ae}")

        self._report("*Pipeline complete.*")
        return summary, self._cost_total

    def _dry_run_report(self, collect_result: dict, analyze_result: dict) -> str:
        """Report for dry run — shows what WOULD happen without building/reviewing."""
        lines = ["*Evolution dry run — preview only*\n"]

        # Collect stats
        collectors = collect_result.get("collectors", {})
        for name, info in collectors.items():
            status = "ok" if info.get("success") else "failed"
            lines.append(f"  {name}: {status}")
        lines.append(f"  Total signals: {collect_result.get('signal_count', 0)}")
        lines.append("")

        # Candidates that would be built
        candidates = analyze_result.get("candidates", [])
        if candidates:
            lines.append(f"*Would build {min(len(candidates), 3)} skill(s):*")
            for c in candidates[:3]:
                name = c.get("name", "?")
                score = c.get("score", "?")
                summary = c.get("summary", "")
                url = c.get("url", "")
                lines.append(f"  *{name}* (score {score})")
                lines.append(f"    {summary}")
                if url:
                    lines.append(f"    {url}")
                skill_idea = c.get("skill_idea", "")
                if skill_idea:
                    lines.append(f"    Skill: {skill_idea}")
                lines.append("")

            skipped = len(candidates) - 3
            if skipped > 0:
                lines.append(f"  ({skipped} more candidates below threshold)")
                lines.append("")
        else:
            lines.append("No candidates scored >= 7.0. Nothing would be built.")
            lines.append("")

        lines.append(f"Cost so far: ${self._cost_total:.2f}")
        lines.append(f"\nRun `/evolve` to execute BUILD → REVIEW → REPORT.")
        return "\n".join(lines)


def approve_skill(name: str) -> tuple[bool, str]:
    """Move a skill from queue to installed."""
    queue_path = QUEUE_DIR / name / "SKILL.md"
    if not queue_path.exists():
        return False, f"Skill `{name}` not found in queue."

    # Check for rejection marker
    rejected_path = QUEUE_DIR / name / ".rejected"
    if rejected_path.exists():
        review = json.loads(rejected_path.read_text())
        issues = review.get("issues", [])
        return False, (
            f"Skill `{name}` was rejected by reviewer:\n"
            + "\n".join(f"  - {i}" for i in issues)
            + "\n\nUse `/approve {name} force` to override."
        )

    # Install
    install_dir = SKILLS_DIR / name
    install_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files from queue to skills
    import shutil
    for f in (QUEUE_DIR / name).iterdir():
        if f.name.startswith("."):
            continue  # skip .rejected marker
        if f.is_dir():
            shutil.copytree(str(f), str(install_dir / f.name), dirs_exist_ok=True)
        else:
            shutil.copy2(str(f), str(install_dir / f.name))

    # Write SHA256 hash of SKILL.md for integrity verification
    skill_md = install_dir / "SKILL.md"
    if skill_md.exists():
        digest = hashlib.sha256(skill_md.read_bytes()).hexdigest()
        (install_dir / ".hash").write_text(digest)
        log.info(f"Wrote integrity hash for {name}: {digest[:12]}...")

    # Clean up queue
    shutil.rmtree(str(QUEUE_DIR / name))

    # Audit: record approval
    try:
        from .session_db import log_audit, generate_trace_id
        log_audit(
            trace_id=generate_trace_id(),
            stage="APPROVE",
            action="skill_approved",
            result="ok",
            metadata={"skill": name},
        )
    except Exception as _ae:
        log.debug(f"Audit log failed: {_ae}")

    return True, f"Skill `{name}` installed to `~/.claude/skills/{name}/`"


def approve_skill_force(name: str) -> tuple[bool, str]:
    """Force-approve a rejected skill."""
    queue_path = QUEUE_DIR / name / "SKILL.md"
    if not queue_path.exists():
        return False, f"Skill `{name}` not found in queue."

    # Remove rejection marker and install
    rejected_path = QUEUE_DIR / name / ".rejected"
    if rejected_path.exists():
        rejected_path.unlink()

    return approve_skill(name)


def reject_skill(name: str, reason: str = "") -> tuple[bool, str]:
    """Remove a skill from the queue."""
    queue_path = QUEUE_DIR / name
    if not queue_path.exists():
        return False, f"Skill `{name}` not found in queue."

    import shutil
    shutil.rmtree(str(queue_path))

    # Audit: record rejection
    try:
        from .session_db import log_audit, generate_trace_id
        log_audit(
            trace_id=generate_trace_id(),
            stage="APPROVE",
            action="skill_rejected",
            result="ok",
            metadata={"skill": name, "reason": reason},
        )
    except Exception as _ae:
        log.debug(f"Audit log failed: {_ae}")

    return True, f"Skill `{name}` rejected and removed." + (f" Reason: {reason}" if reason else "")


def verify_skill_hashes() -> list[str]:
    """Check installed skills for hash integrity.

    For each skill in ~/.claude/skills/ with a SKILL.md, compares its current
    SHA256 against the stored .hash file written at approval time.

    Returns list of skill names where hash is missing or mismatched.
    Skills installed before this feature was added will appear as 'unverified'
    (not quarantined — conservative default).
    """
    tampered: list[str] = []
    if not SKILLS_DIR.exists():
        return tampered

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        hash_file = skill_dir / ".hash"
        if not skill_md.exists():
            continue
        if not hash_file.exists():
            tampered.append(skill_dir.name)
            continue
        expected = hash_file.read_text().strip()
        actual = hashlib.sha256(skill_md.read_bytes()).hexdigest()
        if actual != expected:
            log.warning(f"Hash mismatch for skill {skill_dir.name}: expected {expected[:12]}... got {actual[:12]}...")
            tampered.append(skill_dir.name)

    return tampered


def list_queue() -> list[dict]:
    """List skills in the queue with their review status.

    Also surfaces any installed skill hash mismatches as a warning entry.
    """
    if not QUEUE_DIR.exists():
        return []

    items = []
    for d in sorted(QUEUE_DIR.iterdir()):
        if not d.is_dir():
            continue
        skill_file = d / "SKILL.md"
        if not skill_file.exists():
            continue

        rejected_file = d / ".rejected"
        status = "rejected" if rejected_file.exists() else "pending"
        review = {}
        if rejected_file.exists():
            try:
                review = json.loads(rejected_file.read_text())
            except Exception:
                pass

        items.append({
            "name": d.name,
            "status": status,
            "review": review,
            "path": str(skill_file),
        })

    # Surface installed skill hash mismatches as a warning
    tampered = verify_skill_hashes()
    if tampered:
        items.append({
            "name": "__integrity_warning__",
            "status": "warning",
            "review": {},
            "path": "",
            "tampered_skills": tampered,
        })

    return items
