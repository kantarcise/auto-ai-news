"""Optional evidence must never remove a saved rules report or change its pool."""

import copy
import http.client
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import (
    article_evidence,
    enrich_model_snapshot,
    generate_report,
    production_model_report,
)
from scripts.publication_history import RECEIPT
from tests.test_compare_model_reports import NOW


class DeferredEvidenceTests(unittest.TestCase):
    def generate(self, root):
        source = generate_report.Source(
            "Example", "https://example.com", "https://example.com/feed", 3
        )
        items = [
            generate_report.Item(
                "AI inference guide",
                "https://example.com/yes",
                "Example",
                3,
                published=NOW,
            ),
            generate_report.Item(
                "An opaque engineering headline",
                "https://example.com/no",
                "Example",
                3,
                published=NOW,
                summary="A short summary.",
            ),
        ]
        history = root / "history.json"
        history.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "report_date": NOW.date().isoformat(),
                    "published": {},
                    "report_dates": [],
                }
            )
        )
        baseline, snapshot = root / "baseline.md", root / "candidates.json"
        with (
            patch.object(generate_report, "load_sources", return_value=[source]),
            patch.object(
                generate_report,
                "fetch_url",
                return_value=(200, source.feed_url, "feed"),
            ),
            patch.object(
                generate_report, "parse_source", return_value=copy.deepcopy(items)
            ),
            patch.object(
                generate_report, "check_url_accessible", return_value=(True, "")
            ),
            patch.object(generate_report, "enrich_article_bodies", return_value=[]),
            patch.object(
                article_evidence.EvidenceCollector,
                "capture",
                side_effect=AssertionError("Optional evidence ran before baseline"),
            ),
        ):
            generate_report.main(
                [
                    "--output",
                    str(baseline),
                    "--publication-history",
                    str(history),
                    "--evaluation-output",
                    str(snapshot),
                    "--evaluation-defer-article-content",
                ]
            )
        return baseline, snapshot

    def test_optional_read_failure_and_timeout_preserve_publishable_baseline(self):
        for failure in (http.client.IncompleteRead(b"partial", 100), TimeoutError()):
            with (
                self.subTest(failure=type(failure).__name__),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                baseline, frozen = self.generate(root)
                original, original_snapshot = baseline.read_bytes(), frozen.read_bytes()
                enriched = root / "enriched.json"
                with (
                    patch.object(
                        article_evidence.EvidenceCollector,
                        "capture",
                        side_effect=failure,
                    ),
                    self.assertRaises(type(failure)),
                ):
                    enrich_model_snapshot.main([str(frozen), "--output", str(enriched)])
                self.assertFalse(enriched.exists())
                output, status = root / "daily.md", root / "status.json"
                with patch.object(
                    production_model_report.comparison, "LazyCloudflare"
                ) as provider:
                    production_model_report.main(
                        [
                            "--baseline-report",
                            str(baseline),
                            "--force-fallback",
                            "--output",
                            str(output),
                            "--status-output",
                            str(status),
                        ]
                    )
                provider.assert_not_called()
                self.assertEqual(baseline.read_bytes(), original)
                self.assertEqual(frozen.read_bytes(), original_snapshot)
                self.assertEqual(
                    RECEIPT.findall(output.read_text()),
                    RECEIPT.findall(original.decode()),
                )
                self.assertIn(
                    "entire report uses the existing rules fallback", output.read_text()
                )
                self.assertEqual(
                    json.loads(status.read_text())["selection"], "rules-fallback"
                )

    def test_enrichment_reuses_exact_pool_clock_scores_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            _, frozen = self.generate(Path(directory))
            value = json.loads(frozen.read_text())
            original = copy.deepcopy(value)
            with (
                patch.object(
                    generate_report,
                    "fetch_url",
                    side_effect=AssertionError("Feed refetched"),
                ),
                patch.object(
                    article_evidence,
                    "fetch",
                    return_value=article_evidence.evidence(
                        "Measured AI engineering details.", "article_body"
                    ),
                ),
            ):
                enriched = enrich_model_snapshot.enrich(value)
            self.assertEqual(value, original)
            for key in (
                "captured_at",
                "publication_history",
                "model_comparison",
                "link_outcomes",
                "policies",
            ):
                self.assertEqual(enriched[key], value[key])
            self.assertEqual(len(enriched["collection"]), 2)
            for before, after in zip(value["collection"], enriched["collection"]):
                self.assertEqual(before["url"], after["url"])
                self.assertEqual(
                    before["comparison_candidate"], after["comparison_candidate"]
                )
                self.assertNotIn("evidence_input", after)
                self.assertIn("article_evidence", after)
            self.assertFalse(
                enriched["collection"][1]["comparison_candidate"]["baseline_admit"]
            )

    def test_evidence_process_timeout_leaves_baseline_available_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, frozen = self.generate(root)
            enriched = root / "enriched.json"
            program = (
                "import sys,time; from unittest.mock import patch; "
                "from scripts import enrich_model_snapshot as e; "
                "from scripts.article_evidence import EvidenceCollector; "
                "p=patch.object(EvidenceCollector, 'capture', side_effect=lambda item: time.sleep(10)); "
                "p.start(); e.main([sys.argv[1], '--output', sys.argv[2]])"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run(
                    [sys.executable, "-c", program, str(frozen), str(enriched)],
                    timeout=0.2,
                    check=True,
                )
            self.assertFalse(enriched.exists())
            output, status = root / "daily.md", root / "status.json"
            production_model_report.main(
                [
                    "--baseline-report",
                    str(baseline),
                    "--force-fallback",
                    "--output",
                    str(output),
                    "--status-output",
                    str(status),
                ]
            )
            self.assertIn("rules fallback", output.read_text())
            self.assertEqual(
                RECEIPT.findall(output.read_text()),
                RECEIPT.findall(baseline.read_text()),
            )

    def test_http_protocol_failures_become_missing_evidence(self):
        for failure in (
            http.client.IncompleteRead(b"partial", 100),
            http.client.RemoteDisconnected("Closed"),
        ):
            response = MagicMock()
            response.headers.get_content_type.return_value = "text/html"
            response.headers.get.return_value = "identity"
            response.read.side_effect = failure
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = response
            with patch.object(
                article_evidence.urllib.request, "build_opener", return_value=opener
            ):
                result = article_evidence.fetch("https://example.com/article", "test")
            self.assertEqual(result["provenance"], "unavailable")
            self.assertIn(type(failure).__name__, result["reason"])
            self.assertEqual(result["text"], "")

    def test_deferred_capture_requires_separate_evaluation_output(self):
        for args in (
            ["--evaluation-defer-article-content"],
            [
                "--evaluation-output",
                "/tmp/example.json",
                "--evaluation-defer-article-content",
                "--evaluation-article-content",
            ],
        ):
            with self.assertRaises(SystemExit):
                generate_report.parse_args(args)


if __name__ == "__main__":
    unittest.main()
