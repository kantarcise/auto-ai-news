import unittest
import urllib.error
from unittest.mock import Mock

from scripts.preview_clairic import (
    preview,
    read_response,
    select_articles,
    source_state,
)
from scripts.publication_history import receipt_comment


class ClairicPreviewTest(unittest.TestCase):
    def test_selection_requires_a_new_article_and_preserves_requested_order(self):
        first = "https://example.com/first"
        second = "https://example.com/second"
        report = receipt_comment("2026-11-21", [first, second])
        row = {"comparison_candidate": {"canonical_url": first}, "article_evidence": {}}
        snapshot = {"collection": [row]}
        self.assertEqual(
            select_articles(report, snapshot, [second, first]),
            ("2026-11-21", [(second, None), (first, row)]),
        )
        for urls in ([first, first + "/"], ["https://example.com/old"]):
            with self.subTest(urls=urls), self.assertRaises(ValueError):
                select_articles(report, snapshot, urls)

    def test_only_source_backed_fields_survive_partial_response(self):
        source = "⚡ A10 and A10 with 24 GB per GPU"
        body = {
            "success": True,
            "result": {
                "truncated": True,
                "usage": {"input_tokens": 700, "passes": 3},
                "answers": {
                    "model": {"value": "invented"},
                    "hardware": {"value": "A10"},
                    "detail": {"value": "24 GB per GPU", "span": [18, 31]},
                },
            },
        }
        usage, fields, warning = read_response(body, source)
        self.assertEqual(fields, {"detail": ("24 GB per GPU", source)})
        self.assertEqual(usage["input_tokens"], 700)
        self.assertEqual(warning, "partial_response")
        with self.assertRaises(ValueError):
            read_response([], source)

    def test_unknown_usage_stops_further_calls_and_escapes_text(self):
        url = "https://example.com/a"
        row = {"title": "<script>\n# Heading"}
        collect = Mock(
            return_value={"text": "12 GB per GPU", "provenance": "rss_content"}
        )
        extract = Mock(side_effect=urllib.error.HTTPError(url, 429, "", None, None))
        markdown = preview("2026-11-21", [(url, row), (url, row)], extract, collect)
        extract.assert_called_once()
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("HTTP 429", markdown)
        self.assertIn("1 requests with unknown usage", markdown)

    def test_input_byte_limit_preserves_unicode(self):
        self.assertEqual(source_state({"text": "⚡" * 3000}), "⚡" * 2666)
