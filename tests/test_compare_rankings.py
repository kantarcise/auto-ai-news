import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts.compare_rankings import compare, main, render
from scripts.editorial_relevance import assess

NOW = dt.datetime(2026, 10, 8, 12, tzinfo=dt.timezone.utc)


def collect(entries, *, excerpts=True, capture=True):
    snapshot = {} if capture else None
    source = report.Source("Example", "https://example.com", "https://feed", 3)
    with (
        patch.object(
            report, "fetch_url", return_value=(200, "https://feed", "")
        ) as fetch,
        patch.object(report, "parse_source", return_value=copy.deepcopy(entries)),
        patch.object(report, "check_url_accessible", return_value=(True, "")) as check,
    ):
        selected, diagnostics = report.collect_items(
            [source], NOW, evaluation=snapshot, evaluation_excerpts=excerpts
        )
    return selected, diagnostics, snapshot, (fetch.call_count, check.call_count)


def entries():
    return [
        report.Item("AI update", "https://example.com/ai", "Example", 3, published=NOW),
        report.Item(
            "GPU cluster runtime configuration",
            "https://example.com/gpu",
            "Example",
            3,
            summary="GPU runtime throughput memory",
            published=NOW - dt.timedelta(seconds=1),
        ),
        report.Item(
            "Gardening tips",
            "https://example.com/garden",
            "Example",
            3,
            summary="private body marker",
            published=NOW,
        ),
    ]


class CompareRankingsTest(unittest.TestCase):
    def test_fixed_weights_stay_stable_while_adaptive_weights_follow_pool(self):
        rows = [{"title": "GPU cluster runtime", "url": "https://example.com/story"}]
        alone = assess(rows)[0]
        crowded = assess(
            rows
            + [
                {"title": rows[0]["title"], "url": f"https://other/{i}"}
                for i in range(20)
            ]
        )[0]
        self.assertEqual(alone.fixed_similarity, crowded.fixed_similarity)
        self.assertNotEqual(alone.similarity, crowded.similarity)

    def test_capture_preserves_report_selection_and_network_requests(self):
        ordinary = collect(entries(), excerpts=False, capture=False)
        captured = collect(entries())
        self.assertEqual(ordinary[:2], captured[:2])
        self.assertEqual(ordinary[3], captured[3])
        before = copy.deepcopy(captured[2])
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network")):
            result = compare(captured[2], revision="test")
        self.assertEqual(captured[2], before)
        self.assertEqual(
            result["orders"]["current"],
            ["https://example.com/ai", "https://example.com/gpu"],
        )
        self.assertEqual(
            result["orders"]["fixed"], list(reversed(result["orders"]["current"]))
        )
        self.assertEqual(result["orders"]["adaptive"], result["orders"]["fixed"])
        self.assertEqual(result["fresh_rejected_count"], 1)

    def test_replay_includes_summary_features_but_bounded_excerpts_no_article_body(
        self,
    ):
        entry = entries()[1]
        entry.summary = "GPU runtime " * 500 + "tail-marker"
        entry.content = "never-export-this-body"
        snapshot = collect([entry])[2]
        self.assertLessEqual(
            len(snapshot["ranking_inputs"][0]["summary_excerpt"]), 1000
        )
        self.assertNotIn("tail-marker", json.dumps(snapshot))
        self.assertNotIn("never-export-this-body", json.dumps(snapshot))
        self.assertIn("runtime", snapshot["ranking_inputs"][0]["document_counts"])
        compare(snapshot)
        metadata_only = collect([entry], excerpts=False)[2]
        self.assertNotIn("ranking_inputs", metadata_only)
        self.assertNotIn("GPU runtime GPU runtime", json.dumps(metadata_only))

    def test_duplicate_urls_and_group_alternates_replay_exact_member_identity(self):
        rows = entries()[:2]
        rows[1].title = "GPU cluster runtime configuration for deployment engineering"
        rows.append(
            report.Item(
                rows[1].title,
                rows[1].url,
                "Example",
                3,
                summary="different words",
                published=rows[1].published,
            )
        )
        alternate = copy.deepcopy(rows[1])
        alternate.url = "https://example.com/alternate"
        rows.append(alternate)
        snapshot = collect(rows)[2]
        self.assertEqual(len(snapshot["ranking_inputs"]), 4)
        self.assertEqual(len(snapshot["shadow_ranking"]["scores"]), 2)
        self.assertEqual(
            len(snapshot["story_groups"][0]) + len(snapshot["story_groups"][1]), 3
        )
        compare(snapshot)

    def test_empty_and_no_disagreement_runs(self):
        result = compare(collect([])[2])
        self.assertEqual(result["orders"], {"current": [], "fixed": [], "adaptive": []})
        self.assertIn("No ordering disagreements", render(result))
        self.assertEqual(compare(collect(entries()[:1])[2])["disagreement_count"], 0)

    def test_tampered_scores_counts_order_and_identity_are_rejected(self):
        original = collect(entries())[2]
        for mutate in (
            lambda s: s["shadow_ranking"]["scores"][0].update(proposed_score=99),
            lambda s: s["ranking_inputs"][0].update(current_score=99),
            lambda s: s["ranking_inputs"][0]["document_counts"].update(ai=-1),
            lambda s: s["ranking_inputs"].append(s["ranking_inputs"][0]),
            lambda s: s["shadow_ranking"].update(current_order=[]),
            lambda s: s.update(captured_at="2026-10-08T12:00:00"),
        ):
            snapshot = copy.deepcopy(original)
            mutate(snapshot)
            with self.assertRaises(ValueError):
                compare(snapshot)

    def test_unknown_access_and_external_text_are_not_misrepresented(self):
        rows = entries()
        rows[1].title = "GPU *runtime* | <script>headline</script> configuration"
        result = compare(collect(rows)[2])
        result["link_outcomes"] = {}
        output = render(result)
        self.assertIn("Not checked", output)
        self.assertIn(r"\| &lt;script&gt;headline&lt;/script&gt;", output)
        self.assertNotIn("<script>", output)
        self.assertIn("not three published reports", output)

    def test_cli_writes_replay_outputs_and_rejects_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot.json"
            snapshot.write_text(json.dumps(collect(entries())[2]))
            args = [
                "compare",
                str(snapshot),
                "--output",
                str(root / "comparison.md"),
                "--json-output",
                str(root / "comparison.json"),
                "--revision",
                "test",
            ]
            with patch("sys.argv", args):
                main()
            self.assertEqual(
                json.loads((root / "comparison.json").read_text())["revision"], "test"
            )
            args[3] = str(snapshot)
            with patch("sys.argv", args), self.assertRaises(SystemExit):
                main()
        with self.assertRaises(SystemExit):
            report.parse_args(["--evaluation-excerpts"])
