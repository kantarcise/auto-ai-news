import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts.compare_source_priority import compare, main

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)


class SourcePriorityTest(unittest.TestCase):
    def test_configured_engineering_beats_forum_without_excluding_forum(self):
        sources = {
            source.name: source
            for source in report.load_sources(report.DEFAULT_SOURCES)
        }
        forum = report.Item(
            "GPU cluster throughput notes",
            "https://forum.test/article",
            "LessWrong AI",
            sources["LessWrong AI"].priority,
            summary="AI inference with LLM agents and transformer language models",
            published=NOW,
        )
        engineering = report.Item(
            "GPU framework memory throughput",
            "https://engineering.test/article",
            "PyTorch",
            sources["PyTorch"].priority,
            summary=forum.summary,
            published=NOW,
        )
        self.assertTrue(report.is_ai_related(forum))
        report.score_item(forum, NOW)
        report.score_item(engineering, NOW)
        self.assertGreater(engineering.rank_score, forum.rank_score)
        previous = copy.deepcopy(forum)
        previous.source_priority = 5
        report.score_item(previous, NOW)
        self.assertGreater(previous.rank_score, engineering.rank_score)
        self.assertEqual(previous.rank_score - forum.rank_score, 1.25)
        for item in (forum, engineering):
            item.canonical_url = report.canonicalize_url(item.url)
        with patch.object(report, "check_url_accessible", return_value=(True, "")):
            selected, _ = report.filter_accessible_items(
                report.dedupe_items([forum, engineering]), 30, 4
            )
        self.assertEqual(
            [item.source for item in selected], ["PyTorch", "LessWrong AI"]
        )
        self.assertEqual(report.render_report(selected, [], NOW).count("<details>"), 5)

    def test_recent_substantive_forum_can_outrank_older_generic_engineering(self):
        sources = {
            source.name: source
            for source in report.load_sources(report.DEFAULT_SOURCES)
        }
        forum = report.Item(
            "GPU cluster throughput notes",
            "https://forum.test/article",
            "LessWrong AI",
            sources["LessWrong AI"].priority,
            summary="AI inference with LLM agents and transformer language models",
            published=NOW,
        )
        generic = report.Item(
            "AI update",
            "https://engineering.test/article",
            "PyTorch",
            sources["PyTorch"].priority,
            published=NOW - dt.timedelta(hours=25),
        )
        report.score_item(forum, NOW)
        report.score_item(generic, NOW)
        self.assertGreater(forum.rank_score, generic.rank_score)

    def test_both_frozen_selections_replay_and_preserve_article_sets(self):
        priorities = {
            source.name: source.priority
            for source in report.load_sources(report.DEFAULT_SOURCES)
        }
        for date in ("2026-10-09", "2026-10-10"):
            snapshot = json.loads(
                (
                    ROOT / f"docs/evaluation/source-priority-input-{date}.json"
                ).read_text()
            )
            with (
                self.subTest(date=date),
                patch.object(
                    report, "fetch_url", side_effect=AssertionError("No network")
                ),
                patch.object(
                    report,
                    "check_url_accessible",
                    side_effect=AssertionError("No network"),
                ),
            ):
                result = compare(snapshot, priorities)
            self.assertEqual(result["entered"], [])
            self.assertEqual(result["left"], [])
            self.assertEqual(len(result["after"]["selected"]), 30)
            self.assertEqual(
                result["before"]["publisher_counts"],
                result["after"]["publisher_counts"],
            )
            changes = {row["title"]: row for row in result["position_changes"]}
            dynamo = changes["Session-Aware Agentic Inference with NVIDIA Dynamo"]
            self.assertEqual(
                (dynamo["before"], dynamo["after"]),
                (5, 2) if date.endswith("09") else (9, 8),
            )
            # Only LessWrong scores change; none of these ratings are human grades.
            previous = {row["url"]: row for row in result["before"]["selected"]}
            for row in result["after"]["selected"]:
                delta = previous[row["url"]]["score"] - row["score"]
                self.assertEqual(delta, 1.25 if row["source"] == "LessWrong AI" else 0)

    def test_invalid_scores_orders_and_unknown_access_stop_replay(self):
        original = json.loads(
            (ROOT / "docs/evaluation/source-priority-input-2026-10-09.json").read_text()
        )
        mutations = [
            lambda s: s["items"][0].update(current_score=999),
            lambda s: s.update(current_order=[]),
            lambda s: s.update(selected_urls=[]),
            lambda s: s.update(link_outcomes={}),
            lambda s: s["items"][0].update(published="2026-10-01T00:00:00+00:00"),
            lambda s: s.update(captured_at="2026-10-09T12:00:00"),
        ]
        for mutate in mutations:
            snapshot = copy.deepcopy(original)
            mutate(snapshot)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                compare(snapshot, {"LessWrong AI": 2})

    def test_cli_preserves_inputs_and_saves_provenance(self):
        input_path = ROOT / "docs/evaluation/source-priority-input-2026-10-09.json"
        original = input_path.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            main([str(input_path), "--output", str(output)])
            result = json.loads(output.read_text())
            self.assertEqual(len(result["input_sha256"]), 64)
            self.assertEqual(len(result["sources_sha256"]), 64)
        self.assertEqual(input_path.read_bytes(), original)
        with self.assertRaises(SystemExit):
            main([str(input_path), "--output", str(input_path)])


if __name__ == "__main__":
    unittest.main()
