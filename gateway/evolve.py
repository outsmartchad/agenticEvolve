"""Evolve orchestrator — multi-stage pipeline with review gate.

Stages:
  1. COLLECT  — run signal collectors (bash scripts)
  2. ANALYZE  — score signals, pick top candidates
  3. BUILD    — create skills in queue (NOT installed yet)
  4. REVIEW   — separate agent validates quality, security, correctness
  5. REPORT   — summary with pending approvals

Skills go to ~/.agenticEvolve/skills-queue/<name>/ and require
human approval via /approve <name> before installing to ~/.claude/skills/.
"""
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("agenticEvolve.evolve")

EXODIR = Path.home() / ".agenticEvolve"
QUEUE_DIR = EXODIR / "skills-queue"
SKILLS_DIR = Path.home() / ".claude" / "skills"
SIGNALS_DIR = EXODIR / "signals"
COLLECTORS_DIR = EXODIR / "collectors"


class EvolveOrchestrator:
    """Runs the evolve pipeline stage by stage, reporting progress."""

    def __init__(self, model: str = "sonnet",
                 on_progress: Callable[[str], None] = None):
        self.model = model
        self.on_progress = on_progress or (lambda x: None)
        self._cost_total = 0.0

    def _report(self, msg: str):
        """Send progress update."""
        log.info(f"[evolve] {msg}")
        try:
            self.on_progress(msg)
        except Exception:
            pass

    def _invoke(self, prompt: str, stage: str) -> dict:
        """Invoke Claude Code for a specific stage."""
        from .agent import invoke_claude_streaming

        self._report(f"*Stage: {stage}*")

        result = invoke_claude_streaming(
            prompt,
            on_progress=self.on_progress,
            model=self.model,
            session_context=f"[Evolve/{stage}]"
        )

        cost = result.get("cost", 0)
        self._cost_total += cost
        return result

    # ── Stage 1: Collect ─────────────────────────────────────────

    def stage_collect(self) -> dict:
        """Run signal collectors and return collected file paths."""
        self._report("Collecting signals from GitHub, HN, X...")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        signals_today = SIGNALS_DIR / today
        signals_today.mkdir(parents=True, exist_ok=True)

        results = {}
        collectors = ["github.sh", "hackernews.sh", "x-search.sh"]

        for collector in collectors:
            path = COLLECTORS_DIR / collector
            if not path.exists():
                self._report(f"  Skipped {collector} (not found)")
                continue
            try:
                self._report(f"  Running `{collector}`...")
                proc = subprocess.run(
                    ["bash", str(path)],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(EXODIR),
                    env={**os.environ, "SIGNALS_DIR": str(SIGNALS_DIR)}
                )
                name = collector.replace(".sh", "")
                results[name] = {
                    "success": proc.returncode == 0,
                    "output": proc.stdout[:500] if proc.stdout else "",
                    "error": proc.stderr[:200] if proc.stderr else "",
                }
                if proc.returncode == 0:
                    self._report(f"  {collector} done")
                else:
                    self._report(f"  {collector} failed (exit {proc.returncode})")
            except subprocess.TimeoutExpired:
                results[collector] = {"success": False, "error": "timeout"}
                self._report(f"  {collector} timed out")
            except Exception as e:
                results[collector] = {"success": False, "error": str(e)}

        # Count signal files
        signal_files = list(signals_today.glob("*.json")) if signals_today.exists() else []
        self._report(f"  Collected {len(signal_files)} signal files")

        return {"today": today, "signals_dir": str(signals_today),
                "collectors": results, "signal_count": len(signal_files)}

    # ── Stage 2: Analyze ─────────────────────────────────────────

    def stage_analyze(self, collect_result: dict) -> dict:
        """Analyze signals and score them. Returns top candidates."""
        signals_dir = collect_result.get("signals_dir", "")

        prompt = (
            "You are the ANALYZER agent in the agenticEvolve pipeline.\n\n"
            f"Read all signal files from {signals_dir}/ (JSON files).\n\n"
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
        """Build skills for top candidates — into QUEUE, not installed."""
        candidates = analyze_result.get("candidates", [])
        if not candidates:
            self._report("  No candidates to build. Skipping.")
            return {"built": []}

        # Only build top 3
        candidates = candidates[:3]
        built = []

        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        for candidate in candidates:
            name = candidate.get("name", "unknown").lower().replace(" ", "-")
            summary = candidate.get("summary", "")
            skill_idea = candidate.get("skill_idea", summary)
            url = candidate.get("url", "")
            score = candidate.get("score", 0)

            skill_dir = QUEUE_DIR / name
            if skill_dir.exists():
                self._report(f"  {name}: already in queue, skipping")
                continue

            # Check if already installed
            if (SKILLS_DIR / name / "SKILL.md").exists():
                self._report(f"  {name}: already installed, skipping")
                continue

            prompt = (
                f"You are the BUILDER agent in the agenticEvolve pipeline.\n\n"
                f"Build a Claude Code skill for: {name}\n"
                f"Summary: {summary}\n"
                f"URL: {url}\n"
                f"Skill idea: {skill_idea}\n\n"
                f"Create the skill file at: {skill_dir}/SKILL.md\n\n"
                f"Requirements:\n"
                f"- YAML frontmatter with: name, description, argument-hint, allowed-tools\n"
                f"- Clear step-by-step procedure\n"
                f"- Under 100 lines total\n"
                f"- No hardcoded API keys, tokens, or secrets\n"
                f"- No placeholder values — only real, working instructions\n"
                f"- If the tool requires installation, include the install command\n\n"
                f"Create ONLY the SKILL.md file. Nothing else."
            )

            result = self._invoke(prompt, f"BUILD ({name})")

            # Verify skill was created
            if (skill_dir / "SKILL.md").exists():
                built.append({
                    "name": name,
                    "summary": summary,
                    "score": score,
                    "path": str(skill_dir / "SKILL.md")
                })
                self._report(f"  Built: {name} (score {score})")
            else:
                self._report(f"  Failed to build: {name}")

        return {"built": built}

    # ── Stage 4: Review ──────────────────────────────────────────

    def stage_review(self, build_result: dict) -> dict:
        """Review agent validates each built skill. READ-ONLY — does not modify."""
        built = build_result.get("built", [])
        if not built:
            return {"reviewed": []}

        reviewed = []

        for skill in built:
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
            approved = [r for r in reviewed if r.get("approved")]
            rejected = [r for r in reviewed if not r.get("approved")]

            if approved:
                lines.append(f"*Skills pending approval ({len(approved)}):*")
                for r in approved:
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
        self._report(f"*Starting evolution cycle ({mode})...*")
        self._cost_total = 0.0

        # Stage 1
        collect_result = self.stage_collect()

        # Stage 2
        analyze_result = self.stage_analyze(collect_result)

        if dry_run:
            summary = self._dry_run_report(collect_result, analyze_result)
            self._report("*Dry run complete. Run `/evolve` to execute.*")
            return summary, self._cost_total

        # Stage 3
        build_result = self.stage_build(analyze_result)

        # Stage 4
        review_result = self.stage_review(build_result)

        # Stage 5
        summary = self.stage_report(collect_result, analyze_result,
                                     build_result, review_result)

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
        shutil.copy2(str(f), str(install_dir / f.name))

    # Clean up queue
    shutil.rmtree(str(QUEUE_DIR / name))

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
    return True, f"Skill `{name}` rejected and removed." + (f" Reason: {reason}" if reason else "")


def list_queue() -> list[dict]:
    """List skills in the queue with their review status."""
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

    return items
