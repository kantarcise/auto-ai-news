import datetime as dt
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts import publication_history as history
from scripts.compare_rankings import compare

NOW = dt.datetime(2026, 10, 9, 12, tzinfo=dt.timezone.utc)


def release(date, urls=None, **kwargs):
    return {
        "tag_name": f"daily-{date}",
        "body": "Legacy notes" if urls is None else history.receipt_comment(date, urls),
        "draft": False,
        "prerelease": False,
        **kwargs,
    }


class PublicationHistoryTest(unittest.TestCase):
    def test_only_successful_daily_releases_are_history_across_pages(self):
        result = history.history_from_releases(
            [
                [release("2026-10-08", ["https://example.com/a"])],
                [
                    release("2026-10-09", ["https://example.com/b"]),
                    release("2026-10-07"),
                    release("2026-10-06", ["https://example.com/draft"], draft=True),
                    release("2026-10-10", ["https://example.com/future"]),
                    release("2026-10-05", ["https://example.com/pre"], prerelease=True),
                    {"tag_name": "v1", "body": "Other release"},
                ],
            ],
            "2026-10-09",
        )
        self.assertEqual(
            result["published"],
            {
                "2026-10-08": ["https://example.com/a"],
                "2026-10-09": ["https://example.com/b"],
            },
        )
        self.assertEqual(result["legacy_release_count"], 1)
        self.assertEqual(result["report_dates"], ["2026-10-08", "2026-10-07"])

    def test_corrupt_receipt_stops_instead_of_silently_losing_history(self):
        valid = release("2026-10-08", ["https://example.com/a"])
        for body in (
            "<!-- " + history.MARKER + " broken",
            valid["body"] * 2,
            history.receipt_comment("2026-10-07", []),
            "<!-- " + history.MARKER + ' {"schema_version":2} -->',
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                history.history_from_releases([[{**valid, "body": body}]], "2026-10-09")

    def test_external_url_cannot_close_comment(self):
        url = "https://example.com/-->evil<text>"
        comment = history.receipt_comment("2026-10-09", [url])
        self.assertEqual(comment.count("-->"), 1)
        value = history.history_from_releases(
            [[release("2026-10-09", body=comment)]], "2026-10-09"
        )
        self.assertEqual(value["published"]["2026-10-09"], [url])

    def test_failed_api_does_not_write_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            with (
                patch.object(
                    history.subprocess,
                    "run",
                    side_effect=subprocess.CalledProcessError(1, ["gh", "api"]),
                ),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                history.main(["--output", str(path)])
            self.assertFalse(path.exists())

    def test_history_capture_uses_complete_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            with patch.object(
                history.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, stdout="[[]]"),
            ) as run:
                history.main(["--output", str(path)])
            self.assertIn("--paginate", run.call_args.args[0])
            self.assertIn("--slurp", run.call_args.args[0])
            self.assertEqual(json.loads(path.read_text())["published"], {})

    def test_repeat_rejected_before_link_checks_and_recorded_in_capture(self):
        source = report.Source("Example", "https://example.com", "https://feed.test", 3)
        entries = [
            report.Item(
                "AI repeat",
                "https://example.com/a?utm_source=feed",
                "Example",
                3,
                published=NOW,
            ),
            report.Item(
                "AI new model", "https://example.com/b", "Example", 3, published=NOW
            ),
        ]
        evaluation = {}
        catch_up = []
        with (
            patch.object(report, "fetch_url", return_value=(200, source.feed_url, "")),
            patch.object(report, "parse_source", return_value=entries),
            patch.object(
                report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            items, diagnostics = report.collect_items(
                [source],
                NOW,
                evaluation=evaluation,
                evaluation_excerpts=True,
                published_urls={"https://example.com/a": "2026-10-08"},
                previously_included=catch_up,
            )
        self.assertEqual([item.url for item in items], ["https://example.com/b"])
        check.assert_called_once_with("https://example.com/b")
        rejected = evaluation["collection"][0]
        self.assertEqual(rejected["rejection_reason"], "previously published")
        self.assertEqual(rejected["previous_report_date"], "2026-10-08")
        self.assertEqual(len(evaluation["ranking_inputs"]), 1)
        compare(evaluation)
        rendered = report.render_report(
            items, diagnostics, NOW, history_enabled=True, previously_included=catch_up
        )
        self.assertEqual(len(catch_up), 1)
        self.assertIn("Previously included — catch up (1)", rendered)
        self.assertIn("[AI repeat](https://example.com/a?utm_source=feed)", rendered)
        self.assertIn(
            "Last included: [2026\\-10\\-08](https://github.com/kantarcise/auto-ai-news/releases/tag/daily-2026-10-08)",
            rendered,
        )
        self.assertIn("Selection exclusions (0)", rendered)
        self.assertNotIn("repeated URL excluded", rendered)

    def test_generation_rerun_union_alternates_and_next_day(self):
        selected = report.Item(
            "AI new",
            "https://example.com/new?utm_source=feed",
            "Example",
            3,
            published=NOW,
        )
        selected.related_coverage = [
            report.Item(
                "AI new", "https://other.test/analysis", "Other", 3, published=NOW
            )
        ]
        original = history.history_from_releases(
            [
                [
                    release("2026-10-08", ["https://example.com/prior?utm_source=old"]),
                    release("2026-10-09", ["https://example.com/earlier-today"]),
                ]
            ],
            "2026-10-09",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            output = Path(directory) / "report.md"
            snapshot = Path(directory) / "capture.json"
            path.write_text(json.dumps(original))
            with (
                patch.object(report.dt, "datetime", wraps=dt.datetime) as clock,
                patch.object(report, "load_sources", return_value=[]),
                patch.object(
                    report, "collect_items", return_value=([selected], [])
                ) as collect,
            ):
                clock.now.return_value = NOW
                report.main(
                    [
                        "--publication-history",
                        str(path),
                        "--output",
                        str(output),
                        "--evaluation-output",
                        str(snapshot),
                        "--no-article-bodies",
                    ]
                )
            self.assertEqual(
                collect.call_args.kwargs["published_urls"],
                {"https://example.com/prior": "2026-10-08"},
            )
            self.assertEqual(json.loads(path.read_text()), original)
            captured = json.loads(snapshot.read_text())
            self.assertEqual(captured["publication_history"], original)
            # Only publishing these notes makes the new links part of future history.
            notes = output.read_text()
            next_day = history.history_from_releases(
                [[release("2026-10-09", body=notes)]], "2026-10-10"
            )
            self.assertEqual(
                next_day["published"]["2026-10-09"],
                [
                    "https://example.com/earlier-today",
                    "https://example.com/new",
                    "https://other.test/analysis",
                ],
            )
            self.assertNotIn("https://example.com/prior", notes)

    def test_catch_up_is_deduplicated_escaped_and_does_not_refresh_history(self):
        source = report.Source(
            "Example <lab>", "https://example.com", "https://feed.test", 3
        )
        entries = [
            report.Item(
                "AI <old> & " + "technical " * 30,
                "https://example.com/a?utm_source=feed",
                source.name,
                3,
                published=NOW,
            ),
            report.Item(
                "AI duplicate",
                "https://example.com/a?utm_source=other",
                source.name,
                3,
                published=NOW,
            ),
            report.Item(
                "AI new model", "https://example.com/new", source.name, 3, published=NOW
            ),
            report.Item(
                "AI stale",
                "https://example.com/stale",
                source.name,
                3,
                published=NOW - dt.timedelta(hours=73),
            ),
            report.Item("AI undated", "https://example.com/undated", source.name, 3),
        ]
        previous = release(
            "2026-10-08",
            [
                "https://example.com/a",
                "https://example.com/stale",
                "https://example.com/undated",
            ],
        )
        original = history.history_from_releases([[previous]], "2026-10-09")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            output = Path(directory) / "report.md"
            snapshot = Path(directory) / "capture.json"
            path.write_text(json.dumps(original))
            with (
                patch.object(report.dt, "datetime", wraps=dt.datetime) as clock,
                patch.object(report, "load_sources", return_value=[source]),
                patch.object(
                    report, "fetch_url", return_value=(200, source.feed_url, "")
                ),
                patch.object(report, "parse_source", return_value=entries),
                patch.object(
                    report, "check_url_accessible", return_value=(True, "")
                ) as check,
            ):
                clock.now.return_value = NOW
                report.main(
                    [
                        "--publication-history",
                        str(path),
                        "--output",
                        str(output),
                        "--evaluation-output",
                        str(snapshot),
                        "--evaluation-excerpts",
                        "--no-article-bodies",
                    ]
                )
            notes = output.read_text()
            check.assert_called_once_with("https://example.com/new")
            self.assertIn("1 new story", notes)
            self.assertIn("<summary>Previous daily reports</summary>", notes)
            self.assertEqual(notes.count("releases/tag/daily-2026-10-08"), 2)
            self.assertLess(
                notes.index("## New articles"),
                notes.index("Previously included — catch up (1)"),
            )
            self.assertIn("https://example.com/a?utm_source=feed", notes)
            self.assertIn("AI &lt;old&gt; &amp;", notes)
            self.assertIn("Example &lt;lab&gt;", notes)
            self.assertNotIn("https://example.com/stale", notes)
            self.assertNotIn("https://example.com/undated", notes)
            self.assertEqual(notes.count("<details>"), notes.count("</details>"))
            current_receipt = history.history_from_releases(
                [[release("2026-10-09", body=notes)]], "2026-10-10"
            )
            self.assertEqual(
                current_receipt["published"]["2026-10-09"], ["https://example.com/new"]
            )
            captured = json.loads(snapshot.read_text())
            self.assertEqual(len(captured["previously_included"]), 2)
            self.assertEqual(len(captured["policies"]["frontier"]["selected"]), 1)
            compare(captured)

    def test_catch_up_only_and_empty_catch_up_reports(self):
        old = report.Item(
            "AI yesterday", "https://example.com/a", "Example", 3, published=NOW
        )
        notes = report.render_report(
            [],
            [("Broken", "HTTP 403.")],
            NOW,
            history_enabled=True,
            previously_included=[(old, "2026-10-08")],
        )
        self.assertIn("0 new stories", notes)
        self.assertIn("No new accessible", notes)
        self.assertIn("[AI yesterday](https://example.com/a)", notes)
        self.assertIn("Links have not been checked again today", notes)
        self.assertIn("Skipped sources and links (1)", notes)
        empty = report.render_report(
            [], [], NOW, history_enabled=True, previously_included=[]
        )
        self.assertIn("Previously included — catch up (0)", empty)
        self.assertIn("- None today.", empty)
        self.assertEqual(empty.count("<details>"), empty.count("</details>"))

    def test_previous_reports_are_bounded_sorted_and_include_legacy_dates(self):
        dates = [(NOW.date() - dt.timedelta(days=i)).isoformat() for i in range(1, 21)]
        captured = history.history_from_releases(
            [[release(date) for date in reversed(dates)]], NOW.date().isoformat()
        )
        self.assertEqual(captured["report_dates"], dates)
        self.assertEqual(captured["published"], {})
        notes = report.render_report(
            [],
            [],
            NOW,
            history_enabled=True,
            previous_report_dates=captured["report_dates"] + dates[:1],
        )
        self.assertIn("Previous daily reports", notes)
        self.assertEqual(notes.count("releases/tag/daily-"), 14)
        self.assertLess(
            notes.index(dates[0].replace("-", "\\-")),
            notes.index(dates[1].replace("-", "\\-")),
        )
        self.assertIn("daily-" + dates[13], notes)
        self.assertNotIn("daily-" + dates[14], notes)
        self.assertIn(
            "[View full report history](https://github.com/kantarcise/auto-ai-news/releases)",
            notes,
        )
        self.assertEqual(notes.count("<details>"), notes.count("</details>"))
        local = report.render_report([], [], NOW)
        self.assertNotIn("Previous daily reports", local)

    def test_previous_report_dates_are_validated(self):
        original = history.history_from_releases([[]], "2026-10-09")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            for invalid in (
                ["2026-10-09"],
                ["2026-10-10"],
                ["invalid"],
                ["20261008"],
                [None],
                "2026-10-08",
            ):
                path.write_text(json.dumps(dict(original, report_dates=invalid)))
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    history.load_history(path, "2026-10-09")
        empty = report.render_report(
            [], [], NOW, history_enabled=True, previous_report_dates=[]
        )
        self.assertIn("No earlier reports recorded", empty)
        self.assertIn("View full report history", empty)

    def test_empty_selection_records_no_unpublished_candidates(self):
        original = history.history_from_releases([[]], "2026-10-09")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            output = Path(directory) / "report.md"
            path.write_text(json.dumps(original))
            with (
                patch.object(report.dt, "datetime", wraps=dt.datetime) as clock,
                patch.object(report, "load_sources", return_value=[]),
                patch.object(
                    report,
                    "collect_items",
                    return_value=([], [("Blocked", "HTTP 403.")]),
                ),
            ):
                clock.now.return_value = NOW
                report.main(
                    [
                        "--publication-history",
                        str(path),
                        "--output",
                        str(output),
                        "--no-article-bodies",
                    ]
                )
            notes = output.read_text()
            self.assertIn("No accessible AI-related articles", notes)
            self.assertEqual(notes.count("<details>"), notes.count("</details>"))
            saved = history.history_from_releases(
                [[release("2026-10-09", body=notes)]], "2026-10-10"
            )
            self.assertEqual(saved["published"]["2026-10-09"], [])

    def test_output_cannot_overwrite_history(self):
        with self.assertRaises(SystemExit):
            report.parse_args(
                [
                    "--publication-history",
                    "/tmp/history.json",
                    "--output",
                    "/tmp/history.json",
                ]
            )
        with self.assertRaises(SystemExit):
            report.parse_args(
                [
                    "--publication-history",
                    "/tmp/history.json",
                    "--evaluation-output",
                    "/tmp/history.json",
                ]
            )

    def test_stale_or_invalid_history_stops_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            value = history.history_from_releases([[]], "2026-10-08")
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                history.load_history(path, "2026-10-09")
            value["report_date"] = "2026-10-09"
            value["published"] = {"2026-10-08": ["javascript:alert(1)"]}
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                history.load_history(path, "2026-10-09")


if __name__ == "__main__":
    unittest.main()
