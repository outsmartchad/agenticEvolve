"""Tests for gateway/evolve.py — pure logic functions only, no Claude API calls."""
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gateway.evolve import (
    EvolveOrchestrator,
    approve_skill,
    approve_skill_force,
    reject_skill,
    verify_skill_hashes,
    list_queue,
    QUEUE_DIR,
    SKILLS_DIR,
)


@pytest.fixture()
def orch() -> EvolveOrchestrator:
    """Bare orchestrator — never calls _invoke (we only test _prefilter_signals)."""
    return EvolveOrchestrator(model="test", on_progress=lambda x: None)


# ── Helpers ──────────────────────────────────────────────────


def _write_signals(signals_dir: Path, filename: str, data) -> Path:
    """Write a JSON signal file into the signals directory."""
    p = signals_dir / filename
    p.write_text(json.dumps(data))
    return p


# ── _prefilter_signals: basic loading ────────────────────────


class TestPrefilterBasic:
    def test_loads_json_array(self, signals_dir, orch):
        signals = [
            {"title": "Tool Alpha", "url": "https://example.com/alpha",
             "metadata": {"points": 100}},
            {"title": "Tool Beta", "url": "https://example.com/beta",
             "metadata": {"points": 50}},
        ]
        _write_signals(signals_dir, "hn.json", signals)

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 2

    def test_loads_json_object(self, signals_dir, orch):
        """A file with a single dict (not array) should be loaded as one signal."""
        signal = {"title": "Solo Signal", "url": "https://example.com/solo",
                  "metadata": {"points": 42}}
        _write_signals(signals_dir, "single.json", signal)

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1
        assert result[0]["title"] == "Solo Signal"

    def test_merges_multiple_files(self, signals_dir, orch):
        _write_signals(signals_dir, "a.json", [
            {"title": "Signal A1", "url": "https://a.com/1", "metadata": {"points": 10}},
        ])
        _write_signals(signals_dir, "b.json", [
            {"title": "Signal B1", "url": "https://b.com/1", "metadata": {"points": 20}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 2


# ── _prefilter_signals: ranking ──────────────────────────────


class TestPrefilterRanking:
    def test_ranked_by_engagement(self, signals_dir, orch):
        signals = [
            {"title": "Low engagement item", "url": "https://x.com/low",
             "metadata": {"points": 5}},
            {"title": "High engagement item", "url": "https://x.com/high",
             "metadata": {"points": 500}},
            {"title": "Mid engagement item", "url": "https://x.com/mid",
             "metadata": {"points": 50}},
        ]
        _write_signals(signals_dir, "mixed.json", signals)

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert result[0]["title"] == "High engagement item"
        assert result[1]["title"] == "Mid engagement item"
        assert result[2]["title"] == "Low engagement item"

    def test_top_n_caps_output(self, signals_dir, orch):
        signals = [
            {"title": f"Signal {i}", "url": f"https://x.com/{i}",
             "metadata": {"points": 100 - i}}
            for i in range(20)
        ]
        _write_signals(signals_dir, "many.json", signals)

        result = orch._prefilter_signals(str(signals_dir), top_n=5)
        assert len(result) == 5

    def test_ranks_by_stars(self, signals_dir, orch):
        """GitHub signals use 'stars' instead of 'points'."""
        signals = [
            {"title": "Low stars repo", "url": "https://gh.com/low",
             "metadata": {"stars": 10}},
            {"title": "High stars repo", "url": "https://gh.com/high",
             "metadata": {"stars": 5000}},
        ]
        _write_signals(signals_dir, "gh.json", signals)

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert result[0]["title"] == "High stars repo"


# ── _prefilter_signals: deduplication by URL ─────────────────


class TestPrefilterDedupByURL:
    def test_same_url_from_different_sources(self, signals_dir, orch):
        """Same URL appearing in two source files → kept once."""
        _write_signals(signals_dir, "hn.json", [
            {"title": "Cool Tool (HN)", "url": "https://example.com/cool",
             "metadata": {"points": 100}},
        ])
        _write_signals(signals_dir, "github.json", [
            {"title": "Cool Tool (GH)", "url": "https://example.com/cool",
             "metadata": {"stars": 200}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        urls = [s.get("url", "").rstrip("/").lower() for s in result]
        assert urls.count("https://example.com/cool") == 1

    def test_url_dedup_is_case_insensitive(self, signals_dir, orch):
        _write_signals(signals_dir, "mixed.json", [
            {"title": "Upper", "url": "HTTPS://EXAMPLE.COM/TOOL",
             "metadata": {"points": 10}},
            {"title": "Lower", "url": "https://example.com/tool",
             "metadata": {"points": 20}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1

    def test_url_dedup_strips_trailing_slash(self, signals_dir, orch):
        _write_signals(signals_dir, "slashes.json", [
            {"title": "With slash", "url": "https://example.com/tool/",
             "metadata": {"points": 10}},
            {"title": "Without slash", "url": "https://example.com/tool",
             "metadata": {"points": 20}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1


# ── _prefilter_signals: deduplication by title ───────────────


class TestPrefilterDedupByTitle:
    def test_same_long_title_deduped(self, signals_dir, orch):
        """Titles >15 chars that are identical should be deduped."""
        title = "A Really Cool New Developer Tool"  # >15 chars
        _write_signals(signals_dir, "src1.json", [
            {"title": title, "url": "https://a.com/tool1",
             "metadata": {"points": 10}},
        ])
        _write_signals(signals_dir, "src2.json", [
            {"title": title, "url": "https://b.com/tool2",
             "metadata": {"points": 20}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        # First occurrence kept, second deduped
        assert len(result) == 1

    def test_short_titles_not_deduped(self, signals_dir, orch):
        """Titles <= 15 chars should NOT be deduped (too generic)."""
        _write_signals(signals_dir, "short.json", [
            {"title": "Go", "url": "https://a.com/1", "metadata": {"points": 10}},
            {"title": "Go", "url": "https://b.com/2", "metadata": {"points": 20}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 2

    def test_title_dedup_is_case_insensitive(self, signals_dir, orch):
        _write_signals(signals_dir, "case.json", [
            {"title": "awesome developer tool for testing",
             "url": "https://a.com/1", "metadata": {"points": 10}},
            {"title": "Awesome Developer Tool For Testing",
             "url": "https://b.com/2", "metadata": {"points": 20}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1


# ── _prefilter_signals: edge cases ──────────────────────────


class TestPrefilterEdgeCases:
    def test_empty_directory(self, signals_dir, orch):
        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert result == []

    def test_malformed_json(self, signals_dir, orch):
        """Malformed JSON files should be skipped gracefully."""
        (signals_dir / "bad.json").write_text("{not valid json!!")
        _write_signals(signals_dir, "good.json", [
            {"title": "Valid Signal", "url": "https://ok.com", "metadata": {"points": 5}},
        ])

        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1
        assert result[0]["title"] == "Valid Signal"

    def test_empty_json_array(self, signals_dir, orch):
        _write_signals(signals_dir, "empty.json", [])
        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert result == []

    def test_signals_missing_metadata(self, signals_dir, orch):
        """Signals without metadata should still load (ranked at 0)."""
        _write_signals(signals_dir, "bare.json", [
            {"title": "No metadata signal", "url": "https://bare.com"},
        ])
        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1

    def test_nonexistent_directory(self, orch):
        """Non-existent signals directory should return empty list."""
        result = orch._prefilter_signals("/tmp/nonexistent_xyzzy_dir_99999", top_n=10)
        assert result == []

    def test_non_json_files_ignored(self, signals_dir, orch):
        """Non-.json files in the directory should be ignored."""
        (signals_dir / "notes.txt").write_text("some notes")
        _write_signals(signals_dir, "real.json", [
            {"title": "Real Signal", "url": "https://real.com", "metadata": {"points": 1}},
        ])
        result = orch._prefilter_signals(str(signals_dir), top_n=10)
        assert len(result) == 1


# ── _run_collector: subprocess with retry ────────────────────


class TestRunCollector:
    """Tests for _run_collector — mocks subprocess.run to avoid real commands."""

    def test_success_returns_output(self, orch):
        fake_proc = MagicMock(returncode=0, stdout="collected 5 signals", stderr="")
        with patch("gateway.evolve.subprocess.run", return_value=fake_proc) as mock_run:
            result = orch._run_collector(["bash", "test.sh"], "test-collector")
        assert result["success"] is True
        assert "collected 5 signals" in result["output"]
        assert result["error"] == ""
        mock_run.assert_called_once()

    def test_failure_returns_error(self, orch):
        fake_proc = MagicMock(returncode=1, stdout="", stderr="file not found")
        with patch("gateway.evolve.subprocess.run", return_value=fake_proc):
            result = orch._run_collector(["bash", "bad.sh"], "bad", max_retries=0)
        assert result["success"] is False
        assert "file not found" in result["error"]

    def test_timeout_returns_error(self, orch):
        with patch("gateway.evolve.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = orch._run_collector(["bash", "slow.sh"], "slow", timeout=5, max_retries=0)
        assert result["success"] is False
        assert result["error"] == "timeout"

    def test_generic_exception_returns_error(self, orch):
        with patch("gateway.evolve.subprocess.run", side_effect=FileNotFoundError("no bash")):
            result = orch._run_collector(["bash", "x.sh"], "x")
        assert result["success"] is False
        assert "no bash" in result["error"]

    def test_retry_on_failure_then_success(self, orch):
        fail = MagicMock(returncode=1, stdout="", stderr="transient")
        ok = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("gateway.evolve.subprocess.run", side_effect=[fail, ok]):
            with patch("time.sleep"):  # skip real sleep
                result = orch._run_collector(["bash", "flaky.sh"], "flaky", max_retries=1)
        assert result["success"] is True

    def test_retry_on_timeout_then_success(self, orch):
        ok = MagicMock(returncode=0, stdout="recovered", stderr="")
        with patch("gateway.evolve.subprocess.run",
                   side_effect=[subprocess.TimeoutExpired("cmd", 5), ok]):
            with patch("time.sleep"):
                result = orch._run_collector(["bash", "t.sh"], "t", max_retries=1)
        assert result["success"] is True
        assert "recovered" in result["output"]

    def test_max_retries_exhausted(self, orch):
        fail = MagicMock(returncode=1, stdout="", stderr="always fail")
        with patch("gateway.evolve.subprocess.run", return_value=fail):
            with patch("time.sleep"):
                result = orch._run_collector(["bash", "x.sh"], "x", max_retries=2)
        assert result["success"] is False

    def test_output_truncated_to_500_chars(self, orch):
        long_output = "x" * 1000
        fake_proc = MagicMock(returncode=0, stdout=long_output, stderr="")
        with patch("gateway.evolve.subprocess.run", return_value=fake_proc):
            result = orch._run_collector(["bash", "verbose.sh"], "verbose")
        assert len(result["output"]) == 500

    def test_stderr_used_when_stdout_empty(self, orch):
        fake_proc = MagicMock(returncode=0, stdout="", stderr="stderr output")
        with patch("gateway.evolve.subprocess.run", return_value=fake_proc):
            result = orch._run_collector(["bash", "t.sh"], "t")
        assert result["success"] is True
        assert "stderr output" in result["output"]


# ── approve_skill / approve_skill_force / reject_skill ───────


class TestApproveSkill:
    """Tests for approve_skill — uses monkeypatch to redirect QUEUE_DIR/SKILLS_DIR."""

    @pytest.fixture(autouse=True)
    def _setup_dirs(self, tmp_path, monkeypatch):
        self.queue = tmp_path / "skills-queue"
        self.skills = tmp_path / "skills"
        self.queue.mkdir()
        self.skills.mkdir()
        monkeypatch.setattr("gateway.evolve.QUEUE_DIR", self.queue)
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", self.skills)

    def _create_queued_skill(self, name: str, content: str = "# Test Skill"):
        d = self.queue / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(content)
        return d

    def test_approve_installs_skill(self):
        self._create_queued_skill("my-skill", "# My Skill\nContent here")
        ok, msg = approve_skill("my-skill")
        assert ok is True
        assert (self.skills / "my-skill" / "SKILL.md").exists()
        assert not (self.queue / "my-skill").exists()  # cleaned up

    def test_approve_writes_hash(self):
        content = "# My Skill\nContent"
        self._create_queued_skill("hashed", content)
        approve_skill("hashed")
        hash_file = self.skills / "hashed" / ".hash"
        assert hash_file.exists()
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert hash_file.read_text().strip() == expected

    def test_approve_not_found(self):
        ok, msg = approve_skill("nonexistent")
        assert ok is False
        assert "not found" in msg

    def test_approve_rejected_skill_blocked(self):
        d = self._create_queued_skill("bad-skill")
        (d / ".rejected").write_text(json.dumps({
            "issues": ["hardcoded secrets"],
        }))
        ok, msg = approve_skill("bad-skill")
        assert ok is False
        assert "rejected" in msg.lower()
        assert "hardcoded secrets" in msg

    def test_approve_copies_subdirectories(self):
        d = self._create_queued_skill("complex-skill")
        refs = d / "references"
        refs.mkdir()
        (refs / "guide.md").write_text("# Guide")
        approve_skill("complex-skill")
        assert (self.skills / "complex-skill" / "references" / "guide.md").exists()

    def test_approve_skips_dotfiles(self):
        d = self._create_queued_skill("dot-skill")
        (d / ".internal").write_text("hidden")
        approve_skill("dot-skill")
        assert not (self.skills / "dot-skill" / ".internal").exists()


class TestApproveSkillForce:

    @pytest.fixture(autouse=True)
    def _setup_dirs(self, tmp_path, monkeypatch):
        self.queue = tmp_path / "skills-queue"
        self.skills = tmp_path / "skills"
        self.queue.mkdir()
        self.skills.mkdir()
        monkeypatch.setattr("gateway.evolve.QUEUE_DIR", self.queue)
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", self.skills)

    def test_force_approve_removes_rejection_and_installs(self):
        d = self.queue / "rejected-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Skill")
        (d / ".rejected").write_text(json.dumps({"issues": ["something"]}))

        ok, msg = approve_skill_force("rejected-skill")
        assert ok is True
        assert (self.skills / "rejected-skill" / "SKILL.md").exists()

    def test_force_approve_not_found(self):
        ok, msg = approve_skill_force("ghost")
        assert ok is False
        assert "not found" in msg


class TestRejectSkill:

    @pytest.fixture(autouse=True)
    def _setup_dirs(self, tmp_path, monkeypatch):
        self.queue = tmp_path / "skills-queue"
        self.queue.mkdir()
        monkeypatch.setattr("gateway.evolve.QUEUE_DIR", self.queue)

    def test_reject_removes_from_queue(self):
        d = self.queue / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Bad")
        ok, msg = reject_skill("bad-skill", reason="not useful")
        assert ok is True
        assert "rejected" in msg.lower()
        assert "not useful" in msg
        assert not d.exists()

    def test_reject_not_found(self):
        ok, msg = reject_skill("nonexistent")
        assert ok is False
        assert "not found" in msg

    def test_reject_no_reason(self):
        d = self.queue / "meh"
        d.mkdir()
        (d / "SKILL.md").write_text("# Meh")
        ok, msg = reject_skill("meh")
        assert ok is True
        assert "Reason:" not in msg


# ── verify_skill_hashes ─────────────────────────────────────


class TestVerifySkillHashes:

    @pytest.fixture(autouse=True)
    def _setup_dirs(self, tmp_path, monkeypatch):
        self.skills = tmp_path / "skills"
        self.skills.mkdir()
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", self.skills)

    def _install_skill(self, name: str, content: str = "# Skill", write_hash: bool = True):
        d = self.skills / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(content)
        if write_hash:
            digest = hashlib.sha256(content.encode()).hexdigest()
            (d / ".hash").write_text(digest)
        return d

    def test_valid_hash_returns_empty(self):
        self._install_skill("good")
        assert verify_skill_hashes() == []

    def test_missing_hash_returns_name(self):
        self._install_skill("no-hash", write_hash=False)
        assert "no-hash" in verify_skill_hashes()

    def test_tampered_content_detected(self):
        d = self._install_skill("tampered")
        (d / "SKILL.md").write_text("# MODIFIED CONTENT")
        assert "tampered" in verify_skill_hashes()

    def test_no_skills_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", tmp_path / "nonexistent")
        assert verify_skill_hashes() == []

    def test_dir_without_skill_md_ignored(self):
        (self.skills / "empty-dir").mkdir()
        assert verify_skill_hashes() == []

    def test_multiple_skills_mixed(self):
        self._install_skill("ok-skill")
        self._install_skill("missing-hash", write_hash=False)
        d = self._install_skill("bad-hash")
        (d / "SKILL.md").write_text("tampered!")
        result = verify_skill_hashes()
        assert "ok-skill" not in result
        assert "missing-hash" in result
        assert "bad-hash" in result


# ── list_queue ───────────────────────────────────────────────


class TestListQueue:

    @pytest.fixture(autouse=True)
    def _setup_dirs(self, tmp_path, monkeypatch):
        self.queue = tmp_path / "skills-queue"
        self.skills = tmp_path / "skills"
        self.queue.mkdir()
        self.skills.mkdir()
        monkeypatch.setattr("gateway.evolve.QUEUE_DIR", self.queue)
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", self.skills)

    def test_empty_queue(self):
        assert list_queue() == []

    def test_pending_skill_listed(self):
        d = self.queue / "new-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# New")
        items = list_queue()
        names = [i["name"] for i in items]
        assert "new-skill" in names
        skill_item = next(i for i in items if i["name"] == "new-skill")
        assert skill_item["status"] == "pending"

    def test_rejected_skill_listed(self):
        d = self.queue / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Bad")
        (d / ".rejected").write_text(json.dumps({"issues": ["secret found"]}))
        items = list_queue()
        skill_item = next(i for i in items if i["name"] == "bad-skill")
        assert skill_item["status"] == "rejected"
        assert skill_item["review"]["issues"] == ["secret found"]

    def test_dir_without_skill_md_ignored(self):
        (self.queue / "incomplete").mkdir()
        items = [i for i in list_queue() if i["name"] != "__integrity_warning__"]
        assert items == []

    def test_integrity_warning_surfaced(self):
        """If installed skills have hash issues, list_queue surfaces a warning."""
        # Install a skill without a hash
        d = self.skills / "unhashed"
        d.mkdir()
        (d / "SKILL.md").write_text("# No hash")
        items = list_queue()
        warning = next((i for i in items if i["name"] == "__integrity_warning__"), None)
        assert warning is not None
        assert "unhashed" in warning["tampered_skills"]

    def test_queue_dir_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr("gateway.evolve.QUEUE_DIR", tmp_path / "nonexistent")
        assert list_queue() == []


# ── stage_report: pure formatting ────────────────────────────


class TestStageReport:

    def test_report_with_all_stages(self, orch):
        collect = {
            "collectors": {"github": {"success": True}, "hn": {"success": False}},
            "signal_count": 42,
        }
        analyze = {
            "candidates": [
                {"name": "cool-tool", "score": 8.5, "summary": "A cool tool"},
            ],
        }
        build = {"built": [{"name": "cool-tool", "path": "/tmp/cool-tool/SKILL.md"}]}
        review = {
            "reviewed": [
                {"name": "cool-tool", "approved": True, "summary": "Looks good", "issues": []},
            ],
        }

        report = orch.stage_report(collect, analyze, build, review)
        assert "github: ok" in report
        assert "hn: failed" in report
        assert "42" in report
        assert "cool-tool" in report
        assert "8.5" in report
        assert "/approve cool-tool" in report

    def test_report_no_candidates(self, orch):
        collect = {"collectors": {}, "signal_count": 0}
        analyze = {"candidates": []}
        build = {"built": []}
        review = {"reviewed": []}

        report = orch.stage_report(collect, analyze, build, review)
        assert "No skills built" in report
        assert "$0.00" in report

    def test_report_rejected_skills(self, orch):
        collect = {"collectors": {}, "signal_count": 5}
        analyze = {"candidates": [{"name": "bad", "score": 7.1, "summary": "bad skill"}]}
        build = {"built": [{"name": "bad", "path": "/tmp/bad/SKILL.md"}]}
        review = {
            "reviewed": [
                {"name": "bad", "approved": False, "summary": "Has issues",
                 "issues": ["hardcoded secret"]},
            ],
        }

        report = orch.stage_report(collect, analyze, build, review)
        assert "Rejected" in report
        assert "hardcoded secret" in report

    def test_report_auto_installed(self, orch):
        collect = {"collectors": {}, "signal_count": 1}
        analyze = {"candidates": [{"name": "auto", "score": 9.0, "summary": "auto install"}]}
        build = {"built": [{"name": "auto", "path": "/tmp/auto/SKILL.md"}]}
        review = {
            "reviewed": [
                {"name": "auto", "approved": True, "summary": "OK", "issues": []},
            ],
            "auto_installed": ["auto"],
        }

        report = orch.stage_report(collect, analyze, build, review)
        assert "Auto-installed" in report
        assert "auto" in report

    def test_report_cost_tracking(self, orch):
        orch._cost_total = 1.23
        collect = {"collectors": {}, "signal_count": 0}
        analyze = {"candidates": []}
        build = {"built": []}
        review = {"reviewed": []}

        report = orch.stage_report(collect, analyze, build, review)
        assert "$1.23" in report


# ── _dry_run_report ──────────────────────────────────────────


class TestDryRunReport:

    def test_dry_run_shows_candidates(self, orch):
        collect = {"collectors": {"github": {"success": True}}, "signal_count": 10}
        analyze = {
            "candidates": [
                {"name": "tool-a", "score": 8.0, "summary": "Tool A desc",
                 "url": "https://example.com/a", "skill_idea": "Automate A"},
                {"name": "tool-b", "score": 7.5, "summary": "Tool B desc",
                 "url": "", "skill_idea": ""},
            ],
        }

        report = orch._dry_run_report(collect, analyze)
        assert "dry run" in report.lower()
        assert "tool-a" in report
        assert "tool-b" in report
        assert "Would build 2" in report
        assert "https://example.com/a" in report
        assert "Automate A" in report

    def test_dry_run_no_candidates(self, orch):
        collect = {"collectors": {}, "signal_count": 0}
        analyze = {"candidates": []}

        report = orch._dry_run_report(collect, analyze)
        assert "No candidates scored" in report

    def test_dry_run_caps_at_3(self, orch):
        candidates = [
            {"name": f"t{i}", "score": 9 - i, "summary": f"Tool {i}", "url": "", "skill_idea": ""}
            for i in range(5)
        ]
        collect = {"collectors": {}, "signal_count": 20}
        analyze = {"candidates": candidates}

        report = orch._dry_run_report(collect, analyze)
        assert "Would build 3" in report
        assert "2 more candidates" in report

    def test_dry_run_cost(self, orch):
        orch._cost_total = 0.05
        collect = {"collectors": {}, "signal_count": 0}
        analyze = {"candidates": []}
        report = orch._dry_run_report(collect, analyze)
        assert "$0.05" in report


# ── stage_analyze: JSON extraction from LLM text ─────────────


class TestStageAnalyzeJsonParsing:
    """Tests that stage_analyze correctly extracts JSON from _invoke output."""

    def test_extracts_json_array(self, orch):
        candidates_json = json.dumps([
            {"name": "cool-tool", "source": "github", "score": 8.3,
             "summary": "desc", "url": "https://x.com", "skill_idea": "idea"},
        ])
        fake_text = f"Here are the results:\n```json\n{candidates_json}\n```"
        with patch.object(orch, "_invoke", return_value={"text": fake_text}):
            with patch.object(orch, "_prefilter_signals", return_value=[]):
                result = orch.stage_analyze({"signals_dir": "/tmp/fake"})
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["name"] == "cool-tool"

    def test_empty_array(self, orch):
        with patch.object(orch, "_invoke", return_value={"text": "No good candidates: []"}):
            with patch.object(orch, "_prefilter_signals", return_value=[]):
                result = orch.stage_analyze({"signals_dir": "/tmp/fake"})
        assert result["candidates"] == []

    def test_malformed_json_returns_empty(self, orch):
        with patch.object(orch, "_invoke", return_value={"text": "broken {{{"}):
            with patch.object(orch, "_prefilter_signals", return_value=[]):
                result = orch.stage_analyze({"signals_dir": "/tmp/fake"})
        assert result["candidates"] == []

    def test_no_json_in_response(self, orch):
        with patch.object(orch, "_invoke", return_value={"text": "Sorry, I cannot help."}):
            with patch.object(orch, "_prefilter_signals", return_value=[]):
                result = orch.stage_analyze({"signals_dir": "/tmp/fake"})
        assert result["candidates"] == []


# ── stage_review: JSON extraction from LLM text ─────────────


class TestStageReviewJsonParsing:
    """Tests that stage_review correctly parses review JSON from _invoke output.

    Uses skip_security_scan=True to avoid importing the security module.
    """

    @pytest.fixture()
    def review_orch(self) -> EvolveOrchestrator:
        return EvolveOrchestrator(
            model="test", on_progress=lambda x: None, skip_security_scan=True,
        )

    def test_parses_approved_review(self, review_orch, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", tmp_path / "skills")
        skill_path = tmp_path / "test-skill" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# Test")

        review_json = json.dumps({
            "name": "test-skill", "approved": True,
            "issues": [], "summary": "Looks great",
        })
        with patch.object(review_orch, "_invoke", return_value={"text": f"Review:\n{review_json}"}):
            result = review_orch.stage_review({
                "built": [{"name": "test-skill", "path": str(skill_path), "score": 8}],
            })
        assert len(result["reviewed"]) == 1
        assert result["reviewed"][0]["approved"] is True

    def test_parses_rejected_review(self, review_orch, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", tmp_path / "skills")
        skill_path = tmp_path / "bad-skill" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# Bad")

        review_json = json.dumps({
            "name": "bad-skill", "approved": False,
            "issues": ["hardcoded API key"], "summary": "Security issue",
        })
        with patch.object(review_orch, "_invoke", return_value={"text": review_json}):
            result = review_orch.stage_review({
                "built": [{"name": "bad-skill", "path": str(skill_path), "score": 7}],
            })
        assert result["reviewed"][0]["approved"] is False
        # Rejection marker file should exist
        assert (skill_path.parent / ".rejected").exists()

    def test_malformed_review_output(self, review_orch, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.evolve.SKILLS_DIR", tmp_path / "skills")
        skill_path = tmp_path / "x-skill" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# X")

        with patch.object(review_orch, "_invoke", return_value={"text": "garbled nonsense"}):
            result = review_orch.stage_review({
                "built": [{"name": "x-skill", "path": str(skill_path), "score": 7}],
            })
        reviewed = result["reviewed"][0]
        assert reviewed["approved"] is False  # default when parse fails
        assert "Parse failed" in reviewed.get("summary", "") or "Failed to parse" in str(reviewed.get("issues", []))

    def test_empty_built_list(self, review_orch):
        result = review_orch.stage_review({"built": []})
        assert result["reviewed"] == []


# ── _report: progress callback ───────────────────────────────


class TestReportCallback:

    def test_callback_invoked(self):
        messages = []
        orch = EvolveOrchestrator(model="test", on_progress=messages.append)
        orch._report("hello")
        assert "hello" in messages

    def test_callback_exception_swallowed(self):
        def bad_cb(msg):
            raise RuntimeError("boom")
        orch = EvolveOrchestrator(model="test", on_progress=bad_cb)
        # Should not raise
        orch._report("this should not crash")

    def test_default_callback_noop(self):
        orch = EvolveOrchestrator(model="test")
        # Should not raise
        orch._report("noop")


# ── EvolveOrchestrator.__init__ ──────────────────────────────


class TestOrchestratorInit:

    def test_default_values(self):
        orch = EvolveOrchestrator()
        assert orch.model == "sonnet"
        assert orch._cost_total == 0.0
        assert orch.skip_security_scan is False

    def test_custom_values(self):
        orch = EvolveOrchestrator(model="haiku", skip_security_scan=True)
        assert orch.model == "haiku"
        assert orch.skip_security_scan is True
