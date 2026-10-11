"""Offline trial boundaries and public-export regressions."""

import copy
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import compare_model_reports as comparison
from scripts import public_model_evaluation as public
from scripts.publication_history import history_from_releases, receipt_comment
from tests.test_compare_model_reports import Provider, row, snapshot


class TrialTests(unittest.TestCase):
    def test_window_is_exactly_seven_calendar_dates(self):
        start = date(2026, 10, 12)
        self.assertFalse(public.trial_active("", start))
        self.assertFalse(
            public.trial_active(start.isoformat(), start - timedelta(days=1))
        )
        for offset in range(7):
            self.assertTrue(
                public.trial_active(start.isoformat(), start + timedelta(days=offset))
            )
        self.assertFalse(
            public.trial_active(start.isoformat(), start + timedelta(days=7))
        )
        for invalid in ("20261012", "2026-10-32", "not-a-date"):
            with self.assertRaises(ValueError):
                public.trial_active(invalid, start)

    def test_evaluation_release_never_consumes_production_history(self):
        release = {
            "tag_name": "evaluation-model-2026-10-10",
            "prerelease": False,
            "body": receipt_comment("2026-10-10", ["https://example.com/recovered"]),
        }
        history = history_from_releases([[release]], "2026-10-11")
        self.assertEqual(history["published"], {})
        self.assertEqual(history["report_dates"], [])

    def test_unset_window_disables_workflow_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with patch.dict(os.environ, {"MODEL_EVALUATION_START_DATE": ""}):
                public.main(["window", "--github-output", str(output)])
            self.assertEqual(output.read_text(), "active=false\n")

    def test_public_notes_allowlist_and_escape_external_text(self):
        value = snapshot([row(0, title="<script>alert(1)</script> | [AI]")])
        result = comparison.compare(value, mode="shadow", provider=Provider())
        result["revision"] = "safe-revision"
        value["collection"][0]["article_evidence"]["text"] = "PRIVATE_ARTICLE_SENTINEL"
        result["raw_response"] = "RAW_RESPONSE_SENTINEL"
        result["credentials"] = "TOKEN_SENTINEL"
        _, notes = public.export(value, result)
        for secret in (
            "PRIVATE_ARTICLE_SENTINEL",
            "RAW_RESPONSE_SENTINEL",
            "TOKEN_SENTINEL",
            "<script>",
        ):
            self.assertNotIn(secret, notes)
        self.assertIn("&lt;script&gt;", notes)
        self.assertIn("safe\\-revision", notes)
        self.assertIn("https://example.com/0", notes)

    def test_unavailable_report_is_explicitly_fallback(self):
        value = snapshot([row(0)])
        result = comparison.compare(value, mode="shadow")
        result["revision"] = "test"
        _, notes = public.export(value, result)
        self.assertIn("Model arm unavailable", notes)
        self.assertIn("entire rules fallback", notes)
        self.assertIn("unavailable", notes)
        attachment = public.public_report(result["candidate_report"])
        self.assertNotIn("Unpublished frozen rules replay.", attachment)
        self.assertIn("entire candidate report falls back", attachment)
        self.assertIn("not the production daily report", attachment)

    def test_wrong_arm_or_capture_is_rejected(self):
        value = snapshot([row(0)])
        result = comparison.compare(value, mode="shadow", provider=Provider())
        result["revision"] = "test"
        for field, bad in [
            ("evidence_arm", "title"),
            ("mode", "rules"),
            ("status", "not_requested"),
            ("captured_at", "2020-01-01T00:00:00"),
        ]:
            changed = copy.deepcopy(result)
            changed[field] = bad
            with self.assertRaises(ValueError):
                public.export(value, changed)

    def test_cli_exports_only_four_public_markdown_files(self):
        value = snapshot([row(0, title="Unpublished AI research")])
        result = comparison.compare(value, mode="shadow", provider=Provider())
        result["revision"] = "test"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture.json"
            capture.write_text(json.dumps(value))
            paired = root / "paired"
            paired.mkdir()
            (paired / "comparison.json").write_text(json.dumps(result))
            for name, text in [
                ("baseline.md", result["baseline_report"]),
                ("candidate.md", result["candidate_report"]),
                ("comparison.md", comparison.render_comparison(result)),
            ]:
                (paired / name).write_text(text)

            output = root / "public"
            github_output = root / "github-output"
            argv = [
                "export",
                str(capture),
                str(paired),
                "--output-dir",
                str(output),
                "--github-output",
                str(github_output),
            ]
            public.main(argv)
            self.assertEqual(
                {p.name for p in output.iterdir()},
                {"review.md", "rules.md", "content.md", "differences.md"},
            )
            for name in ("rules.md", "content.md", "differences.md"):
                text = (output / name).read_text()
                self.assertIn("Experimental", text)
                self.assertIn("not the production daily report", text)
                self.assertNotIn("Unpublished frozen rules replay.", text)
                self.assertNotIn("Unpublished content-shadow-v1 comparison.", text)
                self.assertNotIn("# Unpublished paired report comparison", text)
                self.assertIn("Unpublished AI research", text)
            self.assertIn("report_date=", github_output.read_text())
            with self.assertRaises(SystemExit):
                public.main(argv)


if __name__ == "__main__":
    unittest.main()
