"""Offline evidence tests; snapshots must not alter production selection."""

import copy
import unittest
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import article_evidence as evidence
from scripts import generate_report as report

FIXTURES = Path(__file__).parent / "fixtures/article-evidence"
BODY = "Measured AI inference results with implementation details. " * 120
NOW = datetime(2026, 10, 11, tzinfo=UTC)


class ArticleEvidenceTest(unittest.TestCase):
    def test_visible_preview_excludes_gate_hidden_and_subsequent_text(self):
        result = evidence.extract((FIXTURES / "public-preview.html").read_text())
        self.assertEqual(result["provenance"], "public_preview")
        self.assertEqual(result["completeness"], "partial")
        self.assertIn("decision API", result["text"])
        for unwanted in [
            "Subscribe",
            "free trial",
            "Hidden",
            "Subscriber text",
            "after the gate",
            "Previous",
        ]:
            self.assertNotIn(unwanted, result["text"])

    def test_short_page_is_usable_but_marked_short(self):
        result = evidence.extract((FIXTURES / "short-entry.html").read_text())
        self.assertEqual(result["provenance"], "article_body")
        self.assertTrue(result["short"])
        self.assertIn("short quotation", result["text"])
        self.assertNotIn("Tags and comments", result["text"])
        self.assertEqual(result["completeness"], "unknown")

    def test_body_container_wins_over_sibling_cards(self):
        document = (
            (FIXTURES / "multiple-articles.html")
            .read_text()
            .replace("FIRST_BODY", BODY)
        )
        result = evidence.extract(document)
        self.assertIn(BODY.strip(), result["text"])
        self.assertNotIn("teaser", result["text"])
        self.assertNotIn("recommended", result["text"])

    def test_multiple_substantial_regions_remain_unknown(self):
        result = evidence.extract(
            f"<article>{BODY}</article><article>{BODY} Another.</article>"
        )
        self.assertFalse(result["text"])
        self.assertIn("Multiple", result["reason"])

    def test_main_with_one_substantial_article_and_short_card(self):
        result = evidence.extract(
            f"<main><article>{BODY}</article><article>Card.</article></main>"
        )
        self.assertEqual(result["text"], BODY.strip())

    def test_substantial_main_body_excludes_short_article_cards(self):
        result = evidence.extract(
            f"<main><h1>Research</h1><p>{BODY}</p>"
            "<article>Recommendation one.</article>"
            "<article>Recommendation two.</article></main>"
        )
        self.assertEqual(result["provenance"], "article_body")
        self.assertIn(BODY.strip(), result["text"])
        self.assertNotIn("Recommendation", result["text"])

    def test_feed_fragment_keeps_nested_body_text_in_order(self):
        result = evidence.feed_text(
            "Before <div class='prose'>Inside</div> After", "html"
        )
        self.assertEqual(result, "Before Inside After")

    def test_metadata_only_gate_marks_preview_without_reading_json(self):
        result = evidence.extract(
            '<article>Visible preview.</article><script>{"isAccessibleForFree": false, "articleBody":"hidden"}</script>'
        )
        self.assertEqual(result["text"], "Visible preview.")
        self.assertEqual(result["completeness"], "partial")

    def test_truncation_and_hash_describe_exact_excerpt(self):
        result = evidence.extract(f"<article>{BODY * 4}</article>")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), evidence.MAX_CONTENT_CHARS)
        self.assertEqual(
            result["text_sha256"],
            evidence.hashlib.sha256(result["text"].encode()).hexdigest(),
        )
        self.assertGreater(result["characters_before_limit"], len(result["text"]))

    def response(self, raw):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = Message()
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.geturl.return_value = "https://example.com/final"
        response.read.return_value = raw
        return response

    @patch("scripts.article_evidence.urllib.request.build_opener")
    def test_script_heavy_html_fits_larger_bounded_response(self, opener):
        raw = (
            "<script>" + "x" * 1_100_000 + f"</script><article>{BODY}</article>"
        ).encode()
        response = self.response(raw)
        opener.return_value.open.return_value = response
        result = evidence.fetch("https://example.com/a", "test-agent")
        self.assertEqual(result["text"], BODY.strip())
        self.assertEqual(result["final_url"], "https://example.com/final")
        self.assertIn("+00:00", result["fetched_at"])
        response.read.assert_called_once_with(evidence.MAX_BYTES + 1)
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertEqual(
            opener.return_value.open.call_args.kwargs["timeout"], evidence.TIMEOUT
        )

    @patch("scripts.article_evidence.urllib.request.build_opener")
    def test_oversized_response_never_parsed_as_partial_body(self, opener):
        opener.return_value.open.return_value = self.response(
            b"x" * (evidence.MAX_BYTES + 1)
        )
        result = evidence.fetch("https://example.com/a", "test-agent")
        self.assertFalse(result["text"])
        self.assertIn("3 MB", result["reason"])

    @patch("scripts.article_evidence.urllib.request.build_opener")
    def test_fetch_errors_and_unsupported_responses(self, opener):
        for media, encoding in [("application/pdf", "identity"), ("text/html", "br")]:
            response = self.response(b"ignored")
            response.headers.replace_header("Content-Type", media)
            response.headers["Content-Encoding"] = encoding
            opener.return_value.open.return_value = response
            self.assertFalse(evidence.fetch("https://example.com/a", "agent")["text"])
        opener.return_value.open.side_effect = TimeoutError()
        self.assertIn(
            "TimeoutError", evidence.fetch("https://example.com/a", "agent")["reason"]
        )

    @patch("scripts.article_evidence.urllib.request.build_opener")
    def test_gzip_response_has_bounded_decoded_size(self, opener):
        for raw, expected in [
            (f"<article>{BODY}</article>".encode(), True),
            (b"x" * (evidence.MAX_BYTES + 1), False),
        ]:
            response = self.response(evidence.gzip.compress(raw))
            response.headers["Content-Encoding"] = "gzip"
            opener.return_value.open.return_value = response
            result = evidence.fetch("https://example.com/a", "agent")
            self.assertEqual(bool(result["text"]), expected)
            if not expected:
                self.assertIn("Decoded", result["reason"])
        response = self.response(b"invalid gzip")
        response.headers["Content-Encoding"] = "gzip"
        opener.return_value.open.return_value = response
        self.assertFalse(evidence.fetch("https://example.com/a", "agent")["text"])

    @patch("scripts.article_evidence.urllib.request.build_opener")
    def test_unsupported_scheme_never_requested(self, opener):
        self.assertFalse(evidence.fetch("file:///tmp/article", "agent")["text"])
        opener.assert_not_called()

    @patch("scripts.article_evidence.fetch")
    def test_feed_content_preferred_without_network(self, fetch):
        item = report.Item(
            "Title",
            "https://example.com/a",
            "Example",
            3,
            content=f"<p>{BODY}</p>",
            content_format="html",
            content_provenance="atom_content",
        )
        result = evidence.EvidenceCollector("agent").capture(item)
        self.assertEqual(result["provenance"], "atom_content")
        fetch.assert_not_called()

    @patch(
        "scripts.article_evidence.fetch",
        return_value=evidence.evidence("Body.", "article_body"),
    )
    def test_url_cache_budget_and_no_item_mutation(self, fetch):
        collector = evidence.EvidenceCollector("agent", request_limit=1)
        item = report.Item(
            "Title",
            "https://example.com/a",
            "Example",
            3,
            canonical_url="https://example.com/a",
        )
        before = copy.deepcopy(item)
        first = collector.capture(item)
        duplicate = copy.deepcopy(item)
        duplicate.url += "?utm_source=test"
        self.assertEqual(collector.capture(duplicate), first)
        other = report.Item("Other", "https://example.com/b", "Example", 3)
        result = collector.capture(other)
        self.assertEqual(result["provenance"], "title_only")
        self.assertIn("budget", result["retrieval"]["reason"])
        fetch.assert_called_once()
        self.assertEqual(item, before)

    @patch(
        "scripts.article_evidence.fetch",
        return_value=evidence.evidence("", "unavailable", reason="Timeout"),
    )
    def test_fallback_retains_missing_evidence_diagnostic(self, fetch):
        collector = evidence.EvidenceCollector("agent")
        item = report.Item(
            "Title", "https://example.com/a", "Example", 3, summary="<p>A summary.</p>"
        )
        result = collector.capture(item)
        self.assertEqual(result["provenance"], "feed_summary")
        self.assertEqual(result["text"], "A summary.")
        self.assertEqual(result["retrieval"]["reason"], "Timeout")
        item.content = "Short feed content."
        self.assertEqual(collector.capture(item)["provenance"], "feed_excerpt")

    @patch(
        "scripts.article_evidence.fetch",
        return_value=evidence.evidence("", "unavailable", reason="Timeout"),
    )
    def test_empty_or_hidden_summary_falls_back_to_title(self, fetch):
        item = report.Item(
            "Title",
            "https://example.com/a",
            "Example",
            3,
            summary="<script>Not visible.</script>",
        )
        result = evidence.EvidenceCollector("agent").capture(item)
        self.assertEqual(result["provenance"], "title_only")
        self.assertEqual(result["text"], "Title")

    def test_opt_in_capture_includes_relevance_rejects_but_leaves_report_identical(
        self,
    ):
        source = report.Source(
            "Example", "https://example.com", "https://example.com/feed", 3
        )
        rows = [
            report.Item(
                "AI inference guide",
                "https://example.com/yes",
                "Example",
                3,
                published=NOW,
            ),
            report.Item(
                "He Built This City",
                "https://example.com/no",
                "Example",
                3,
                published=NOW,
            ),
            report.Item(
                "Old AI news",
                "https://example.com/old",
                "Example",
                3,
                published=NOW - timedelta(days=10),
            ),
            report.Item(
                "Published AI news",
                "https://example.com/published",
                "Example",
                3,
                published=NOW,
            ),
        ]
        snapshots, rendered = [], []
        for enabled in [False, True]:
            snapshot = {}
            with (
                patch.object(
                    report, "fetch_url", return_value=(200, source.feed_url, "feed")
                ),
                patch.object(report, "parse_source", return_value=copy.deepcopy(rows)),
                patch.object(report, "check_url_accessible", return_value=(True, "")),
                patch.object(
                    evidence,
                    "fetch",
                    return_value=evidence.evidence(BODY, "article_body"),
                ) as fetch,
            ):
                items, diagnostics = report.collect_items(
                    [source],
                    NOW,
                    evaluation=snapshot,
                    evaluation_article_content=enabled,
                    published_urls={"https://example.com/published": "2026-10-10"},
                )
            self.assertEqual(fetch.call_count, 2 if enabled else 0)
            self.assertEqual([i.url for i in items], ["https://example.com/yes"])
            self.assertEqual(items[0].content, "")
            rendered.append(report.render_report(items, diagnostics, NOW))
            snapshots.append(snapshot)
        self.assertEqual(rendered[0], rendered[1])
        captured = [r for r in snapshots[1]["collection"] if "article_evidence" in r]
        self.assertEqual(
            {r["url"] for r in captured},
            {"https://example.com/yes", "https://example.com/no"},
        )
        self.assertFalse(
            any("article_evidence" in r for r in snapshots[0]["collection"])
        )

    def test_cli_requires_explicit_capture_and_respects_body_disable(self):
        for args in [
            ["--evaluation-article-content"],
            [
                "--evaluation-article-content",
                "--evaluation-output",
                "/tmp/evidence.json",
                "--no-article-bodies",
            ],
        ]:
            with self.assertRaises(SystemExit):
                report.parse_args(args)
        with self.assertRaises(ValueError):
            report.collect_items([], NOW, evaluation_article_content=True)
