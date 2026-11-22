import unittest
import urllib.error
from unittest.mock import Mock

from scripts.enrich_daily_clairic import enrich
from scripts.generate_report import markdown_link
from scripts.publication_history import receipt_comment


def report_inputs(count):
    articles = [
        {"title": f"GPU (test) {i}", "url": f"https://example.com/{i}"}
        for i in range(count)
    ]
    snapshot = {
        "collection": [
            {
                "title": article["title"],
                "article_evidence": {
                    "text": "Measured 32 GB per GPU.",
                    "provenance": "article_body",
                },
            }
            for article in articles
        ]
    }
    selection = {
        "selection": "model-assisted",
        "selected_articles": articles,
        "decisions": [
            {
                "url": article["url"],
                "id": i,
                "applied": True,
                "candidate_admit": True,
                "answers": {"engineering_detail": "yes"},
            }
            for i, article in enumerate(articles)
        ],
    }
    report = "## New articles\n\n" + "".join(
        f"{i}. **{markdown_link(row['title'], row['url'])}**  \n   Metadata\n\n"
        for i, row in enumerate(articles, 1)
    )
    receipt = receipt_comment("2026-11-22", [row["url"] for row in articles])
    return report + receipt, snapshot, selection, receipt


class DailyClairicTest(unittest.TestCase):
    def test_decorates_up_to_five_ranked_stories_and_preserves_receipt(self):
        report, snapshot, selection, receipt = report_inputs(7)
        extract = Mock(
            return_value=(
                {"input_tokens": 100, "passes": 1},
                {"detail": ("32 GB per GPU <example>", "source context")},
                None,
            )
        )
        updated, status = enrich(report, snapshot, selection, extract)
        self.assertEqual(extract.call_count, 5)
        self.assertEqual(
            status,
            {
                "attempts": 5,
                "shown": 5,
                "input_tokens": 500,
                "passes": 5,
                "stop": "budget",
            },
        )
        self.assertEqual(updated.count("Source detail (Clairic)"), 5)
        self.assertIn(
            "Metadata  \n   Source detail (Clairic) · “32 GB per GPU &lt;example&gt;”",
            updated,
        )
        self.assertTrue(updated.endswith(receipt))

    def test_skips_ineligible_and_stops_on_unknown_usage(self):
        report, snapshot, selection, _ = report_inputs(4)
        selection["decisions"][0]["answers"]["engineering_detail"] = "no"
        extract = Mock(
            side_effect=[
                ({"input_tokens": 200, "passes": 1}, {}, None),
                urllib.error.HTTPError("https://example.com", 429, "", None, None),
            ]
        )
        updated, status = enrich(report, snapshot, selection, extract)
        self.assertEqual(updated, report)
        self.assertEqual(status["attempts"], 2)
        self.assertEqual(status["input_tokens"], 200)
        self.assertEqual(status["stop"], "request_usage_unknown")

    def test_rules_fallback_uses_no_clairic(self):
        report, snapshot, selection, _ = report_inputs(1)
        selection["selection"] = "rules-fallback"
        extract = Mock()
        self.assertEqual(enrich(report, snapshot, selection, extract)[0], report)
        extract.assert_not_called()
