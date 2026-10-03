import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report
from scripts.generate_report import (
    Item,
    Source,
    canonicalize_url,
    dedupe_items,
    estimate_reading_time,
    extract_text_from_html,
    filter_accessible_items,
    is_ai_related,
    is_quiet_day_roundup,
    parse_feed,
    parse_source,
    render_report,
    score_item,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 4, 25, 12, 0, tzinfo=dt.timezone.utc)


class GenerateReportTest(unittest.TestCase):
    def test_freshness_boundaries_and_timezone_offsets(self):
        for stamp, expected in (
            ("2026-04-23T12:00:00Z", ""),
            ("2026-04-23T14:00:00+02:00", ""),
            ("2026-04-25T12:00:00Z", ""),
            ("2026-04-23T11:59:59Z", "older than coverage window"),
            ("2026-04-25T12:00:01Z", "future publication date"),
            ("invalid", "missing or invalid publication date"),
            ("", "missing or invalid publication date"),
        ):
            with self.subTest(stamp=stamp):
                item = Item(
                    "AI news",
                    "https://example.com",
                    "Test",
                    3,
                    published=generate_report.parse_datetime(stamp),
                )
                self.assertEqual(
                    generate_report.freshness_reason(item, NOW, 48), expected
                )

    def test_collection_filters_dates_before_link_checks_and_groups_reasons(self):
        source = Source("Test", "https://example.com", "https://example.com/feed", 3)
        dates = [
            "2026-04-23T12:00:00Z",
            "2026-04-23T11:59:59Z",
            "2026-04-22T12:00:00Z",
            "invalid",
            "2026-04-25T12:00:01Z",
        ]
        feed = (
            "<rss><channel>"
            + "".join(
                f"<item><title>AI news {i}</title><link>https://example.com/{i}</link><pubDate>{date}</pubDate></item>"
                for i, date in enumerate(dates)
            )
            + "</channel></rss>"
        )
        with (
            patch.object(
                generate_report, "fetch_url", return_value=(200, source.feed_url, feed)
            ),
            patch.object(
                generate_report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            items, diagnostics = generate_report.collect_items([source], NOW)
        self.assertEqual(len(items), 1)
        check.assert_called_once_with("https://example.com/0")
        self.assertIn(
            ("Test", "Freshness: 2 entries excluded: older than coverage window."),
            diagnostics,
        )
        self.assertIn(
            (
                "Test",
                "Freshness: 1 entries excluded: missing or invalid publication date.",
            ),
            diagnostics,
        )
        self.assertIn(
            ("Test", "Freshness: 1 entries excluded: future publication date."),
            diagnostics,
        )
        with (
            patch.object(
                generate_report, "fetch_url", return_value=(200, source.feed_url, feed)
            ),
            patch.object(
                generate_report, "check_url_accessible", return_value=(True, "")
            ),
        ):
            wider, _ = generate_report.collect_items([source], NOW, 72)
        self.assertEqual(len(wider), 3)

    def test_stale_feed_empty_report_and_separate_diagnostics(self):
        source = Source("Old", "https://example.com", "https://example.com/feed", 3)
        feed = "<rss><channel><item><title>AI news</title><link>https://example.com/old</link><pubDate>2026-04-01T00:00:00Z</pubDate></item></channel></rss>"
        with (
            patch.object(
                generate_report, "fetch_url", return_value=(200, source.feed_url, feed)
            ),
            patch.object(generate_report, "check_url_accessible") as check,
        ):
            items, diagnostics = generate_report.collect_items([source], NOW)
        check.assert_not_called()
        self.assertEqual(items, [])
        self.assertIn(
            ("Old", "Freshness: no dated entries within the coverage window."),
            diagnostics,
        )
        report = render_report(items, diagnostics + [("Broken", "Network error")], NOW)
        self.assertIn("0 articles · 0 sources", report)
        self.assertIn("Coverage: last 48 hours", report)
        self.assertIn("Freshness exclusions (2 source diagnostics)", report)
        self.assertIn("Skipped sources and links (1)", report)
        self.assertIn(
            "No accessible AI-related articles found within the coverage window.",
            report,
        )

    def test_positive_window_cli_validation(self):
        self.assertEqual(generate_report.parse_args([]).lookback_hours, 48)
        self.assertEqual(
            generate_report.parse_args(["--lookback-hours", "72"]).lookback_hours, 72
        )
        import contextlib
        import io

        for value in ("0", "-1", "abc"):
            with (
                self.subTest(value=value),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                generate_report.parse_args(["--lookback-hours", value])
        with self.assertRaises(ValueError):
            generate_report.collect_items([], NOW, 0)

    def test_engineering_and_korean_ai_headlines_are_relevant(self):
        for title in (
            "Building an agentic development platform",
            "Lessons from software factories",
            "The software factory workflow",
            "Spatial intelligence for developers",
            "인공지능 서비스 개발",
        ):
            with self.subTest(title=title):
                self.assertTrue(
                    is_ai_related(Item(title, "https://example.com", "Engineering", 3))
                )
        self.assertFalse(
            is_ai_related(
                Item(
                    "Improving database backups",
                    "https://example.com",
                    "Engineering",
                    3,
                )
            )
        )

    def test_world_labs_title_and_date_card(self):
        source = Source(
            "World Labs",
            "https://example.com",
            "https://example.com/blog",
            4,
            format="dated_html",
        )
        items = parse_source(
            '<a href="/blog/atlas"><h3>Atlas: A World Model for Spatial Intelligence</h3><span>September 1, 2026</span></a>',
            source,
        )
        self.assertEqual(
            items[0].title, "Atlas: A World Model for Spatial Intelligence"
        )
        self.assertEqual(
            items[0].published, dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
        )

    def test_quiet_day_filter_is_scoped_to_publisher_and_exact_title(self):
        for source, title in (
            ("Latent Space", "[AINews] not much happened today"),
            ("smol.ai", "  Not Much Happened Today.  "),
            ("Latent Space", "[AINews]\nnot much happened today!"),
        ):
            with self.subTest(source=source, title=title):
                self.assertTrue(
                    is_quiet_day_roundup(Item(title, "https://example.com", source, 5))
                )
        for source, title in (
            ("Simon Willison", "Not much happened today"),
            (
                "Latent Space",
                "Why ‘not much happened today’ misses important AI research",
            ),
            ("smol.ai", "A new AI model launched today"),
        ):
            with self.subTest(source=source, title=title):
                self.assertFalse(
                    is_quiet_day_roundup(Item(title, "https://example.com", source, 5))
                )

    def test_collection_skips_quiet_day_before_link_checks_and_reports_reason(self):
        source = Source(
            "Latent Space", "https://example.com", "https://example.com/feed", 5
        )
        feed = """<rss><channel>
        <item><title>[AINews] not much happened today</title><pubDate>Sat, 25 Apr 2026 12:00:00 GMT</pubDate><link>https://example.com/quiet</link>
        <description>A substantial recap about AI models and agents.</description></item>
        <item><title>New AI model</title><pubDate>Sat, 25 Apr 2026 12:00:00 GMT</pubDate><link>https://example.com/model</link></item>
        </channel></rss>"""
        with (
            patch.object(
                generate_report, "fetch_url", return_value=(200, source.feed_url, feed)
            ),
            patch.object(
                generate_report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            items, skipped = generate_report.collect_items([source], NOW)
        self.assertEqual([item.title for item in items], ["New AI model"])
        check.assert_called_once_with("https://example.com/model")
        self.assertEqual(
            skipped,
            [
                (
                    "Latent Space: [AINews] not much happened today",
                    "Quiet-day roundup excluded by title policy.",
                )
            ],
        )

    def test_parse_dated_html_news_and_research_cards(self):
        source = Source(
            "DeepSeek",
            "https://example.com",
            "https://example.com/news",
            4,
            format="dated_html",
        )
        content = """<a href="/news/model"><span>News September 10, 2026</span>
        <h3>DeepSeek model &amp; research</h3><p>Summary</p></a>
        <a href="https://arxiv.org/abs/1234"><span>June 24, 2026</span>
        <span class="ds-research-title">Inference research</span></a>
        <a href="/nav"><h3>Navigation</h3></a>"""
        items = parse_source(content, source)
        self.assertEqual(
            [item.title for item in items],
            ["DeepSeek model & research", "Inference research"],
        )
        self.assertEqual(
            items[0].published, dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc)
        )
        self.assertEqual(items[1].url, "https://arxiv.org/abs/1234")

    def test_parse_anthropic_card_and_detect_layout_failure(self):
        source = Source(
            "Anthropic",
            "https://example.com",
            "https://example.com",
            4,
            format="dated_html",
        )
        items = parse_source(
            '<a href="/research/claude"><time>Oct 1, 2026</time>'
            '<span class="PublicationList__title">Claude science</span></a>',
            source,
        )
        self.assertEqual(items[0].title, "Claude science")
        self.assertEqual(
            items[0].published, dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
        )
        with self.assertRaisesRegex(ValueError, "no recognized article cards"):
            parse_source('<a href="/other">Oct 1, 2026</a>', source)

    def test_canonicalize_url_removes_tracking_and_fragments(self):
        url = "HTTPS://Example.com/story/?utm_source=x&keep=1#comments"
        self.assertEqual(canonicalize_url(url), "https://example.com/story?keep=1")

    def test_parse_rss_and_filter_ai_items(self):
        source = Source("Example", "https://example.com", "https://example.com/feed", 3)
        items = parse_feed((FIXTURES / "rss.xml").read_text(encoding="utf-8"), source)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "New AI model improves code generation")
        self.assertTrue(is_ai_related(items[0]))
        self.assertFalse(is_ai_related(items[1]))

    def test_parse_atom_feed(self):
        source = Source(
            "Example Atom", "https://example.com", "https://example.com/feed", 3
        )
        items = parse_feed((FIXTURES / "atom.xml").read_text(encoding="utf-8"), source)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://example.com/frontier-llm/")
        self.assertEqual(
            items[0].published, dt.datetime(2026, 4, 25, 8, 0, tzinfo=dt.timezone.utc)
        )

    def test_dedupe_keeps_highest_ranked_item(self):
        source = Source("Example", "https://example.com", "https://example.com/feed", 3)
        items = parse_feed((FIXTURES / "rss.xml").read_text(encoding="utf-8"), source)
        first = items[0]
        first.canonical_url = canonicalize_url(first.url)
        first.stars = 2
        duplicate = parse_feed(
            (FIXTURES / "rss.xml").read_text(encoding="utf-8"), source
        )[0]
        duplicate.url = "https://example.com/ai-code/"
        duplicate.canonical_url = canonicalize_url(duplicate.url)
        duplicate.stars = 5

        deduped = dedupe_items([first, duplicate])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].stars, 5)

    def test_extract_text_and_reading_time(self):
        source = Source("Example", "https://example.com", "https://example.com/feed", 3)
        item = parse_feed((FIXTURES / "rss.xml").read_text(encoding="utf-8"), source)[0]
        article_html = (FIXTURES / "article.html").read_text(encoding="utf-8")

        self.assertIn(
            "Artificial intelligence systems", extract_text_from_html(article_html)
        )
        self.assertEqual(estimate_reading_time(item, article_html), 1)
        self.assertGreater(item.word_count, 5)

    def test_score_is_bounded_to_five_stars(self):
        source = Source(
            "High Priority", "https://example.com", "https://example.com/feed", 5
        )
        item = parse_feed((FIXTURES / "rss.xml").read_text(encoding="utf-8"), source)[0]
        item.source_priority = 5

        self.assertEqual(score_item(item, NOW), 5)

    def test_render_report_contains_links_and_skipped_sources(self):
        source = Source("Example", "https://example.com", "https://example.com/feed", 3)
        item = parse_feed((FIXTURES / "rss.xml").read_text(encoding="utf-8"), source)[0]
        item.canonical_url = canonicalize_url(item.url)
        item.read_minutes = 2
        item.stars = 4
        report = render_report([item], [("Blocked", "HTTP 403 from source.")], NOW)

        self.assertIn(
            "[New AI model improves code generation](https://example.com/ai-code?utm_source=test#section)",
            report,
        )
        self.assertIn("HTTP 403 from source\\.", report)
        self.assertIn("1 article · 1 source", report)
        self.assertIn("★★★★☆ · Example · 2026-04-25 · ~2 min (feed text)", report)
        self.assertIn("<summary>Skipped sources and links (1)</summary>", report)
        self.assertIn("This report was generated automatically by auto-ai-news", report)
        self.assertIn("original articles, titles, and linked content belong", report)

    def test_render_report_escapes_external_text_and_link_destinations(self):
        item = Item(
            "[AINews] *AI* | <b>model</b> \\ notes\nnext",
            "https://example.com/a_(b)?q=two words&keep=1",
            "Source_One",
            3,
        )
        report = render_report([item], [("<script>bad</script>", "*timeout*")], NOW)

        self.assertIn(
            r"\[AINews\] \*AI\* \| &lt;b&gt;model&lt;/b&gt; \\ notes next", report
        )
        self.assertIn("(https://example.com/a_%28b%29?q=two%20words&keep=1)", report)
        self.assertIn(r"Source\_One · Date unknown", report)
        self.assertIn(r"&lt;script&gt;bad&lt;/script&gt;**: \*timeout\*", report)

    def test_render_report_empty_state_and_balanced_details(self):
        report = render_report([], [], NOW)

        self.assertIn("0 articles · 0 sources", report)
        self.assertIn(
            "No accessible AI-related articles found within the coverage window.",
            report,
        )
        self.assertIn(
            "<summary>Skipped sources and links (0)</summary>\n\n- None.", report
        )
        self.assertEqual(report.count("<details>"), 3)
        self.assertEqual(report.count("</details>"), 3)
        self.assertLess(report.index("## Source policy"), report.rindex("</details>"))

    def test_render_report_keeps_double_digit_metadata_inside_list(self):
        items = [
            Item(f"Article {index}", f"https://example.com/{index}", "Example", 3)
            for index in range(12)
        ]
        report = render_report(items, [], NOW)

        self.assertIn("12 articles · 1 source", report)
        self.assertIn("10. **[Article 9](https://example.com/9)**  \n    ★☆☆☆☆", report)
        self.assertLess(report.index("[Article 0]"), report.index("[Article 11]"))

    def test_filter_accessible_items_reports_failed_links(self):
        source = Source("Example", "https://example.com", "https://example.com/feed", 3)
        items = parse_feed((FIXTURES / "rss.xml").read_text(encoding="utf-8"), source)
        old_check = generate_report.check_url_accessible
        try:
            generate_report.check_url_accessible = lambda url: (
                url.endswith("/garden"),
                "HTTP 404.",
            )
            accessible, failures = filter_accessible_items(items, 5)
        finally:
            generate_report.check_url_accessible = old_check

        self.assertEqual(
            [item.title for item in accessible], ["Gardening notes for spring"]
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("New AI model improves code generation", failures[0][0])
        self.assertEqual(failures[0][1], "HTTP 404.")


if __name__ == "__main__":
    unittest.main()
