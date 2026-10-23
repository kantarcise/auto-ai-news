"""Production selection, publication receipts and full-report fallback offline."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import production_model_report as production
from scripts.article_evidence import evidence
from scripts.cloudflare_assessment import CloudflareAssessmentProvider
from scripts.model_assessment import AssessmentAnswers
from scripts.publication_history import RECEIPT, history_from_releases, receipt_comment
from tests.test_compare_model_reports import NOW, Provider, row, snapshot
from tests.test_model_assessment import ACCOUNT, TOKEN, response_body


class ProductionTests(unittest.TestCase):
    def baseline(self):
        return "# Daily AI News\n\nOriginal rules report.\n" + receipt_comment(
            NOW.date().isoformat(), ["https://example.com/0"]
        )

    def test_recovered_selection_and_receipt_replace_baseline(self):
        value = snapshot([row(0), row(1, admit=False)])
        day = NOW.date().isoformat()
        value["publication_history"] = {
            "report_date": day,
            "published": {day: ["https://example.com/already-today?utm_source=old"]},
        }
        provider = Provider(
            {"AI topic 0": AssessmentAnswers("no", "no", "opinion or discussion")}
        )
        text, status = production.select_report(
            self.baseline(), value, provider=provider
        )
        self.assertEqual(status["selection"], "model-assisted")
        self.assertNotIn("Unpublished", text)
        self.assertIn("Cloudflare Clef-flash", text)
        self.assertIn("Supplemental article evidence", text)
        self.assertIn("AI topic 1", text)
        self.assertNotIn("AI topic 0", text)
        receipt = json.loads(RECEIPT.findall(text)[0])
        self.assertEqual(
            receipt["urls"],
            ["https://example.com/1", "https://example.com/already-today"],
        )
        history = history_from_releases(
            [[{"tag_name": f"daily-{day}", "body": text, "prerelease": False}]],
            day,
        )
        self.assertIn("https://example.com/1", history["published"][day])
        self.assertNotIn("https://example.com/0", history["published"][day])

    def test_large_multilingual_evidence_does_not_disable_model_report(self):
        rows = [row(0), row(1, admit=False), row(2, admit=False)]
        rows[1]["article_evidence"] = evidence("한" * 12_000, "article_body")
        provider = CloudflareAssessmentProvider(
            ACCOUNT, TOKEN, request_limit=100, input_byte_limit=1_000_000
        )
        provider._opener = MagicMock()
        response = provider._opener.open.return_value.__enter__.return_value
        response.status = 200
        response.headers = {}
        response.read.return_value = json.dumps(response_body()).encode()

        value = snapshot(rows)
        value["publication_history"] = {
            "report_date": NOW.date().isoformat(),
            "published": {},
        }
        text, status = production.select_report(
            self.baseline(), value, provider=provider
        )

        self.assertEqual(status["selection"], "model-assisted")
        self.assertIsNone(status["failure"])
        self.assertEqual(provider.requests_attempted, 3)
        self.assertEqual(status["model_selected"], 3)
        self.assertTrue(all(decision["applied"] for decision in status["decisions"]))
        self.assertNotIn("entire report uses the existing rules fallback", text)
        self.assertIn("AI topic 1", text)
        self.assertIn("AI topic 2", text)
        self.assertEqual(
            json.loads(RECEIPT.findall(text)[0])["urls"],
            ["https://example.com/0", "https://example.com/1", "https://example.com/2"],
        )

    def test_alternate_links_enter_production_receipt(self):
        value = snapshot(
            [
                row(0, title="An AI release with six detailed title tokens"),
                row(1, title="An AI release with six detailed title tokens"),
            ]
        )
        day = NOW.date().isoformat()
        value["publication_history"] = {"report_date": day, "published": {}}
        text, status = production.select_report(
            self.baseline(), value, provider=Provider()
        )
        self.assertEqual(status["model_selected"], 1)
        self.assertEqual(
            json.loads(RECEIPT.findall(text)[0])["urls"],
            ["https://example.com/0", "https://example.com/1"],
        )

    def test_partial_provider_failure_discards_all_model_choices(self):
        value = snapshot([row(0), row(1, admit=False)])
        text, status = production.select_report(
            self.baseline(), value, provider=Provider(fail_after=1)
        )
        self.assertEqual(status["selection"], "rules-fallback")
        self.assertEqual(status["failure"]["code"], "network_error")
        self.assertEqual(status["usage"]["new_assessment_attempts"], 2)
        self.assertTrue(all(not row["applied"] for row in status["decisions"]))
        self.assertIn("Original rules report.", text)
        self.assertIn("entire report uses the existing rules fallback", text)
        self.assertEqual(RECEIPT.findall(text), RECEIPT.findall(self.baseline()))
        self.assertNotIn("AI topic 1", text)

    def test_unexpected_comparison_error_is_sanitized_fallback(self):
        with patch.object(
            production.comparison,
            "compare",
            side_effect=RuntimeError("SECRET_SENTINEL"),
        ):
            text, status = production.select_report(self.baseline(), {})
        self.assertEqual(status["selection"], "rules-fallback")
        self.assertNotIn("SECRET_SENTINEL", text + json.dumps(status))

    def test_missing_credentials_retains_original_receipt(self):
        with patch.dict(os.environ, {}, clear=True):
            text, status = production.select_report(
                self.baseline(),
                snapshot([row(0)]),
                provider=production.comparison.LazyCloudflare(100, 1_000_000),
            )
        self.assertEqual(status["selection"], "rules-fallback")
        self.assertEqual(status["failure"]["code"], "missing_or_invalid_credentials")
        self.assertEqual(RECEIPT.findall(text), RECEIPT.findall(self.baseline()))

    def test_cli_success_publishes_model_report_with_sanitized_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.md"
            baseline.write_text(self.baseline())
            capture = root / "capture.json"
            capture.write_text(json.dumps(snapshot([row(0), row(1, admit=False)])))
            output, status = root / "report.md", root / "status.json"
            with patch.object(
                production.comparison, "LazyCloudflare", return_value=Provider()
            ) as factory:
                production.main(
                    [
                        "--baseline-report",
                        str(baseline),
                        "--snapshot",
                        str(capture),
                        "--output",
                        str(output),
                        "--status-output",
                        str(status),
                    ]
                )
            factory.assert_called_once_with(100, 1_000_000)
            self.assertIn("AI topic 1", output.read_text())
            self.assertIn("Cloudflare Clef-flash", output.read_text())
            self.assertEqual(
                json.loads(status.read_text())["selection"], "model-assisted"
            )
            self.assertNotIn("Synthetic AI measurements", status.read_text())
            audit = json.loads(status.read_text())
            self.assertIn("question_version", audit)
            self.assertEqual(audit["model"], "@cf/cloudflare/clef-flash")
            self.assertEqual(len(audit["decisions"]), 2)
            self.assertEqual(audit["decisions"][1]["reason"], "model_ai_subject_yes")
            self.assertEqual(
                audit["decisions"][1]["evidence"]["provenance"], "article_body"
            )
            self.assertEqual(audit["decisions"][1]["answers"]["ai_subject"], "yes")

    def test_rules_rollback_needs_no_snapshot_provider_or_network(self):
        with patch.object(production.comparison, "compare") as compare:
            text, status = production.select_report(self.baseline(), mode="rules")
        compare.assert_not_called()
        self.assertEqual(text, self.baseline())
        self.assertEqual(status["selection"], "rules")

    def test_empty_model_report_keeps_history_and_disclosure(self):
        value = snapshot([])
        day = NOW.date().isoformat()
        value["publication_history"] = {"report_date": day, "published": {}}
        text, status = production.select_report(
            self.baseline(), value, provider=Provider()
        )
        self.assertEqual(status["selection"], "model-assisted")
        self.assertEqual(status["model_selected"], 0)
        self.assertEqual(json.loads(RECEIPT.findall(text)[0])["urls"], [])
        self.assertIn("Cloudflare Clef-flash", text)

    def test_cli_missing_capture_and_step_failure_publish_labeled_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.md"
            baseline.write_text(self.baseline())
            output, status_path = root / "report.md", root / "status.json"
            args = [
                "--baseline-report",
                str(baseline),
                "--output",
                str(output),
                "--status-output",
                str(status_path),
            ]
            for extra in ([], ["--force-fallback"], ["--mode", "rules"]):
                with patch.object(production.comparison, "LazyCloudflare") as factory:
                    self.assertEqual(production.main(args + extra), 0)
                status = json.loads(status_path.read_text())
                if extra == ["--mode", "rules"]:
                    factory.assert_not_called()
                    self.assertEqual(output.read_text(), self.baseline())
                else:
                    self.assertEqual(status["selection"], "rules-fallback")
                    self.assertEqual(
                        RECEIPT.findall(output.read_text()),
                        RECEIPT.findall(self.baseline()),
                    )
                self.assertNotIn("Synthetic AI measurements", status_path.read_text())
            with self.assertRaises(SystemExit):
                production.main(args + ["--output", str(baseline)])


if __name__ == "__main__":
    unittest.main()
