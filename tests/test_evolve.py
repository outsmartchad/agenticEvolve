"""Tests for gateway/evolve.py — pure logic functions only, no Claude API calls."""
import json
from pathlib import Path

import pytest

from gateway.evolve import EvolveOrchestrator


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
