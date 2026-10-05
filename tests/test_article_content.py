"""Offline regression coverage for conservative article retrieval."""

import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import article_content as content
from scripts.generate_report import Item, enrich_article_bodies, reading_time_label

BODY = "Technical findings explain measured results and implementation tradeoffs. " * 30


class ArticleContentTests(unittest.TestCase):
    def test_semantic_body_excludes_boilerplate(self):
        document = (
            Path(__file__).parent / "fixtures" / "article-body.html"
        ).read_text()
        body, reason = content.extract_body(document)
        self.assertEqual(body, BODY.strip())
        self.assertEqual(reason, "")

    def test_template_class_body(self):
        body, reason = content.extract_body(
            f'<div class="post-content"><p>{BODY}</p></div>'
        )
        self.assertEqual(body, BODY.strip())
        self.assertFalse(reason)

    def test_unavailable_excerpts_and_gates(self):
        for document in (
            "<article><p>Short excerpt.</p></article>",
            f"<nav>{BODY}</nav>",
            f'<article>{BODY}</article><div class="paywall">Subscribe</div>',
            f'<article>{BODY}</article><script type="application/ld+json">{{"isAccessibleForFree":false}}</script>',
            f"<main><article>{BODY}</article><article>{BODY}</article></main>",
            "<html>Please sign in to continue</html>",
        ):
            with self.subTest(document=document[:50]):
                body, reason = content.extract_body(document)
                self.assertFalse(body)
                self.assertTrue(reason)

    def response(self, raw, media_type="text/html"):
        response = MagicMock()
        response.headers = Message()
        response.headers["Content-Type"] = media_type
        response.read.return_value = raw
        response.__enter__.return_value = response
        return response

    @patch("scripts.article_content.urllib.request.build_opener")
    def test_bounded_html_fetch(self, opener):
        response = self.response(f"<article>{BODY}</article>".encode())
        opener.return_value.open.return_value = response
        body, reason = content.fetch_body("https://example.com/story", "test-agent")
        self.assertEqual(body, BODY.strip())
        self.assertFalse(reason)
        response.read.assert_called_once_with(content.MAX_BYTES + 1)
        self.assertEqual(
            opener.return_value.open.call_args.kwargs["timeout"], content.TIMEOUT
        )

    @patch("scripts.article_content.urllib.request.build_opener")
    def test_fetch_failures_do_not_estimate(self, opener):
        for response in (
            self.response(b"x" * (content.MAX_BYTES + 1)),
            self.response(b"document", "application/pdf"),
        ):
            opener.return_value.open.return_value = response
            body, reason = content.fetch_body("https://example.com/story", "test-agent")
            self.assertFalse(body)
            self.assertTrue(reason)
        opener.return_value.open.side_effect = TimeoutError()
        self.assertFalse(
            content.fetch_body("https://example.com/story", "test-agent")[0]
        )

    def test_redirect_policy_rejects_non_http(self):
        handler = content.BoundedRedirects()
        with self.assertRaises(ValueError):
            handler.redirect_request(None, None, 302, "Found", {}, "file:///tmp/body")
        self.assertEqual(handler.max_redirections, 3)

    @patch("scripts.article_content.urllib.request.build_opener")
    def test_unsupported_scheme_never_requested(self, opener):
        self.assertFalse(content.fetch_body("file:///tmp/story", "test-agent")[0])
        opener.assert_not_called()

    @patch("scripts.generate_report.fetch_body", return_value=(BODY, ""))
    def test_feed_preference_and_body_provenance(self, fetch):
        feed = Item(
            "AI research",
            "https://example.com/feed",
            "Example",
            3,
            content=BODY,
            content_format="text",
            content_provenance="rss_content",
        )
        missing = Item("AI research", "https://example.com/body", "Example", 3)
        self.assertEqual(enrich_article_bodies([feed, missing]), [])
        fetch.assert_called_once()
        self.assertIn("feed content", reading_time_label(feed))
        self.assertIn("extracted body", reading_time_label(missing))

    @patch("scripts.generate_report.fetch_body", return_value=(BODY, ""))
    def test_cache_budget_and_alternate_coverage(self, fetch):
        first = Item("AI research", "https://example.com/a", "Example", 3)
        duplicate = Item(
            "AI research", "https://example.com/a?utm_source=test", "Example", 3
        )
        second = Item("AI research", "https://example.com/b", "Example", 3)
        first.related_coverage = [second]
        failures = enrich_article_bodies([first, duplicate, second], request_limit=1)
        fetch.assert_called_once()
        self.assertIsNotNone(duplicate.read_minutes)
        self.assertIsNone(second.read_minutes)
        self.assertEqual(len(failures), 1)
        self.assertIn("budget", failures[0][1])

    @patch("scripts.generate_report.fetch_body", return_value=("", "Timeout"))
    def test_failure_preserves_story_and_unknown_time(self, fetch):
        item = Item(
            "AI research", "https://example.com/a", "Example", 3, summary="Excerpt"
        )
        failures = enrich_article_bodies([item])
        self.assertEqual(item.summary, "Excerpt")
        self.assertIsNone(item.read_minutes)
        self.assertIn("unknown", reading_time_label(item))
        self.assertIn("Timeout", failures[0][1])


if __name__ == "__main__":
    unittest.main()
