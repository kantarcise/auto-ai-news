import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts.review_candidates import evaluate, prepare

NOW = dt.datetime(2026, 10, 6, 12, tzinfo=dt.timezone.utc)


def item(title, url, published=NOW):
    return report.Item(
        title, url, "Example", 3, "private summary", published, content="private body"
    )


class EvaluationCaptureTest(unittest.TestCase):
    def collect(self, entries, evaluation=None):
        source = report.Source("Example", "https://example.com", "https://feed.test", 3)
        with (
            patch.object(
                report, "fetch_url", return_value=(200, "https://example.com/feed", "")
            ) as fetch,
            patch.object(report, "parse_source", return_value=copy.deepcopy(entries)),
            patch.object(
                report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            result = report.collect_items([source], NOW, evaluation=evaluation)
        return result, fetch.call_count, check.call_count

    def test_rejects_at_each_collection_gate_and_capture_does_not_change_report(self):
        entries = [
            item("AI selected", "/selected"),
            item("AI old", "/old", NOW - dt.timedelta(hours=73)),
            item("AI future", "/future", NOW + dt.timedelta(seconds=1)),
            item("AI undated", "/undated", None),
            item("AI no link", ""),
            item("Gardening tips", "/garden"),
            item("AI duplicate", "/selected"),
        ]
        ordinary, feeds, links = self.collect(entries)
        snapshot = {}
        captured, audit_feeds, audit_links = self.collect(entries, snapshot)
        self.assertEqual(ordinary, captured)
        self.assertEqual((feeds, links), (audit_feeds, audit_links))
        self.assertEqual(len(snapshot["collection"]), 7)
        self.assertEqual(
            [row["rejection_reason"] for row in snapshot["collection"]],
            [
                "",
                "older than coverage window",
                "future publication date",
                "missing or invalid publication date",
                "missing link",
                "title relevance filter",
                "",
            ],
        )
        pool = snapshot["policies"]["frontier"]["candidates"]
        self.assertEqual(len(pool), 5)
        self.assertEqual(pool[0]["url"], "https://example.com/selected")
        self.assertNotIn("private summary", json.dumps(snapshot))
        self.assertNotIn("private body", json.dumps(snapshot))
        review = prepare(snapshot)
        self.assertEqual(len(review["items"]), 5)
        self.assertTrue(all(row["include"] is None for row in review["items"]))
        review["reviewer"] = "Test reviewer"
        rejected = next(row for row in review["items"] if row["url"].endswith("garden"))
        rejected.update(
            include="yes",
            relevant="yes",
            importance=2,
            story_id="miss",
            evidence="article",
        )
        metrics = evaluate(snapshot, review)
        self.assertEqual(
            metrics["policies"]["frontier"]["recall_on_reviewed_candidates"], 0
        )
        self.assertEqual(metrics["candidate_scope"], snapshot["candidate_scope"])

    def test_quiet_day_and_source_failures_remain_visible(self):
        source = report.Source("Latent Space", "https://example.com", "https://feed", 3)
        disabled = report.Source("Disabled", "", "", 3, enabled=False)
        missing = report.Source("Missing", "", "", 3)
        broken = report.Source("Broken", "", "https://broken", 3)
        snapshot = {}
        quiet = item("[AINews] not much happened today", "/quiet")
        quiet.source = source.name
        with (
            patch.object(
                report,
                "fetch_url",
                side_effect=[(200, source.feed_url, ""), (503, "", "")],
            ),
            patch.object(
                report,
                "parse_source",
                return_value=[quiet],
            ),
            patch.object(report, "check_url_accessible") as check,
        ):
            selected, diagnostics = report.collect_items(
                [source, disabled, missing, broken], NOW, evaluation=snapshot
            )
        self.assertEqual(selected, [])
        check.assert_not_called()
        self.assertEqual(
            snapshot["collection"][0]["rejection_reason"], "quiet-day title policy"
        )
        self.assertEqual(snapshot["diagnostics"], diagnostics)
        self.assertTrue(
            {"Disabled", "Missing", "Broken"} <= {row[0] for row in diagnostics}
        )

    def test_story_group_is_frozen_before_blocked_representative_fallback(self):
        title = "Introducing a detailed new AI model for research"
        lab = report.Source("Lab", "", "https://lab/feed", 3, category="frontier_lab")
        other = report.Source("Other", "", "https://other/feed", 3)
        snapshot = {}
        with (
            patch.object(
                report, "fetch_url", return_value=(200, "https://example.com", "")
            ),
            patch.object(
                report,
                "parse_source",
                side_effect=[
                    [item(title, "https://lab/post")],
                    [item(title, "https://other/post")],
                ],
            ),
            patch.object(
                report,
                "check_url_accessible",
                side_effect=[(False, "HTTP 403."), (True, "")],
            ),
        ):
            selected, _ = report.collect_items([lab, other], NOW, evaluation=snapshot)
        self.assertEqual(selected[0].url, "https://other/post")
        self.assertEqual(
            snapshot["story_groups"], [["https://lab/post", "https://other/post"]]
        )
        self.assertEqual(
            snapshot["link_outcomes"]["https://lab/post"],
            {"accessible": False, "reason": "HTTP 403."},
        )
        self.assertEqual(
            snapshot["policies"]["frontier"]["selected"][0]["url"], "https://other/post"
        )

    def test_unchecked_links_are_absent_when_report_limit_is_reached(self):
        snapshot = {}
        with patch.object(report, "MAX_ITEMS", 1):
            self.collect(
                [item("AI first", "/first"), item("AI second", "/second")], snapshot
            )
        self.assertEqual(set(snapshot["link_outcomes"]), {"https://example.com/first"})
        self.assertEqual(len(snapshot["policies"]["frontier"]["candidates"]), 2)
        self.assertIn("links not checked", snapshot["diagnostics"][-1][1])

    def test_publisher_cap_preserves_omitted_row_without_fabricating_link_outcome(self):
        snapshot = {}
        self.collect(
            [item(f"AI article {i}", f"/article-{i}") for i in range(5)], snapshot
        )
        policy = snapshot["policies"]["frontier"]
        self.assertEqual(len(policy["candidates"]), 5)
        self.assertEqual(len(policy["selected"]), 4)
        self.assertNotIn("https://example.com/article-4", snapshot["link_outcomes"])
        self.assertIn("publisher cap", snapshot["diagnostics"][-1][1])

    def test_accessible_alternate_is_attributed_without_an_extra_selected_headline(
        self,
    ):
        title = "Introducing a detailed new AI model for research"
        snapshot = {}
        self.collect([item(title, "/one"), item(title, "/two")], snapshot)
        policy = snapshot["policies"]["frontier"]
        self.assertEqual(len(policy["candidates"]), 2)
        self.assertEqual(len(policy["selected"]), 1)
        self.assertEqual(
            policy["alternate_coverage"],
            [
                {
                    "representative_url": "https://example.com/one",
                    "urls": ["https://example.com/two"],
                }
            ],
        )

    def test_cli_writes_separate_snapshot_and_report_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            audit = Path(directory) / "snapshot.json"
            with patch.object(report, "load_sources", return_value=[]):
                report.main(
                    [
                        "--output",
                        str(output),
                        "--evaluation-output",
                        str(audit),
                        "--no-article-bodies",
                    ]
                )
            snapshot = json.loads(audit.read_text())
            self.assertEqual(snapshot["policies"]["frontier"]["candidates"], [])
            self.assertEqual(snapshot["collection"], [])
            self.assertEqual(
                dt.datetime.fromisoformat(snapshot["captured_at"]).utcoffset(),
                dt.timedelta(0),
            )
            self.assertIn("0 stories", output.read_text())
            with self.assertRaises(SystemExit):
                report.parse_args(
                    ["--output", str(output), "--evaluation-output", str(output)]
                )

    def test_naive_capture_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            report.collect_items([], NOW.replace(tzinfo=None), evaluation={})
