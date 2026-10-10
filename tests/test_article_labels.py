import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts.article_content import extract_body_evidence
from scripts.article_labels import MAX_CONTENT_CHARS, label_article
from scripts.compare_rankings import compare, render

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)


class ArticleLabelsTest(unittest.TestCase):
    def test_promotion_and_technical_details_can_coexist(self):
        text = "Customer story: we deployed a new implementation using KV caches. Profiling measured p95 latency of 14 ms; we discuss limitations and dependencies. Book a demo."
        result = label_article("How we deploy an inference service", text)
        self.assertIn("promotion_testimonial", result["labels"])
        self.assertIn("technical_walkthrough", result["labels"])
        self.assertIn("practical_experience", result["labels"])
        self.assertEqual(result["technical_depth"], "some")
        self.assertEqual(result["evidence"], "feed_summary")
        self.assertTrue(result["provisional"])
        body = label_article(
            "Service guide", content=text, content_provenance="rss_content"
        )
        self.assertEqual(body["technical_depth"], "some")
        self.assertEqual(body["evidence"], "feed_content")
        self.assertEqual(body["depth_scope"], "available_text_only")

    def test_difficult_infrastructure_paragraph_has_positive_depth_clues(self):
        result = label_article(
            "Session-aware serving",
            "We explain routing with shared KV caches, cache indexing and programmatic cache movement.",
        )
        self.assertEqual(result["technical_depth"], "some")
        self.assertIn("technical_walkthrough", result["labels"])

    def test_title_only_and_missing_evidence_never_establish_depth(self):
        title = label_article("Introducing GPU implementation configuration benchmarks")
        self.assertIn("model_tool_release", title["labels"])
        self.assertEqual(title["technical_depth"], "uncertain")
        self.assertEqual(title["evidence"], "title_only")
        missing = label_article("")
        self.assertEqual(missing["technical_depth"], "uncertain")
        self.assertEqual(missing["labels"], [])
        self.assertEqual(missing["evidence"], "missing")

    def test_announcement_and_opinion_are_not_assumed_shallow(self):
        event = label_article(
            "Conference guide", "Join us for a webinar. Register now."
        )
        self.assertIn("event_announcement", event["labels"])
        self.assertEqual(event["technical_depth"], "uncertain")
        opinion = label_article("An essay", "I think this approach is promising.")
        self.assertIn("opinion_discussion", opinion["labels"])
        self.assertEqual(opinion["technical_depth"], "uncertain")
        long_text = label_article(
            "A long post",
            "ordinary words " * 2000,
            content="ordinary words " * 2000,
            content_provenance="atom_content",
        )
        self.assertEqual(long_text["technical_depth"], "uncertain")

    def test_negated_signals_and_scripts_do_not_create_depth(self):
        result = label_article(
            "Overview", "No implementation. Without benchmarks. No configuration."
        )
        self.assertNotIn("technical_walkthrough", result["labels"])
        self.assertNotIn("research_evaluation", result["labels"])
        self.assertEqual(result["technical_depth"], "uncertain")
        html = "<script>implementation configuration benchmarks</script><nav>Book a demo</nav><article>Our ordinary overview.</article>"
        result = label_article(
            "Overview",
            content=html,
            content_format="html",
            content_provenance="rss_content",
        )
        self.assertEqual(result["labels"], [])
        self.assertEqual(result["signals"], [])

    def test_nonempty_html_code_and_available_text_are_bounded(self):
        result = label_article(
            "Implementation guide",
            content="<article>Implementation and configuration.<pre>import torch; x = model()</pre></article>",
            content_format="html",
            content_provenance="atom_content",
        )
        self.assertIn("code", result["signals"])
        self.assertEqual(result["technical_depth"], "some")
        empty = label_article(
            "Overview",
            content="<article><code></code>Plain notes.</article>",
            content_format="html",
            content_provenance="rss_content",
        )
        self.assertNotIn("code", empty["signals"])
        tail = label_article(
            "Overview",
            content="ordinary " * 4000 + " implementation configuration benchmarks",
            content_provenance="article_body",
        )
        self.assertTrue(tail["truncated"])
        self.assertLessEqual(tail["analyzed_characters"], MAX_CONTENT_CHARS)
        self.assertEqual(tail["technical_depth"], "uncertain")
        self.assertNotIn("ordinary ordinary", json.dumps(tail))
        late_code = label_article(
            "Overview",
            content="<article>"
            + "ordinary words " * 1000
            + "<pre>import torch; x = model()</pre></article>",
            content_format="html",
            content_provenance="atom_content",
        )
        self.assertNotIn("code", late_code["signals"])
        self.assertEqual(late_code["technical_depth"], "uncertain")

    def test_feed_and_downloaded_code_evidence_are_equal(self):
        filler = (
            "We describe each operation and its effect on the running service. " * 12
        )
        html = f"<article><p>Configuration and profiling.</p><pre>import torch; x = model()</pre><p>{filler}</p></article>"
        body, reason, structure = extract_body_evidence(html)
        self.assertFalse(reason)
        feed = label_article(
            "Service guide",
            content=html,
            content_format="html",
            content_provenance="rss_content",
        )
        downloaded = label_article(
            "Service guide",
            content=body,
            content_provenance="article_body",
            content_structure=structure,
        )
        self.assertEqual(feed["signals"], downloaded["signals"])
        self.assertEqual(feed["technical_depth"], "substantial")
        self.assertEqual(feed["technical_depth"], downloaded["technical_depth"])
        self.assertNotEqual(feed["evidence"], downloaded["evidence"])
        # Both paths ignore empty, navigation, hidden and out-of-window code.
        for code in (
            "<code></code>",
            "<nav><code>import torch</code></nav>",
            "<div hidden><code>import torch</code></div>",
            "ordinary words " * 1000 + "<pre>import torch</pre>",
        ):
            document = (
                f"<article><p>Configuration and profiling. {filler}</p>{code}</article>"
            )
            body, _, structure = extract_body_evidence(document)
            for assessed in (
                label_article(
                    "Guide",
                    content=document,
                    content_format="html",
                    content_provenance="rss_content",
                ),
                label_article(
                    "Guide",
                    content=body,
                    content_provenance="article_body",
                    content_structure=structure,
                ),
            ):
                self.assertNotIn("code", assessed["signals"])
                self.assertEqual(assessed["technical_depth"], "some")

    def test_independent_fields_preserve_summary_and_deduplicate_signals(self):
        summary = "Customer story: we deployed an implementation using configuration and profiling. Book a demo."
        result = label_article(
            "Service",
            summary,
            content="Read more on our website.",
            content_provenance="rss_content",
        )
        self.assertIn("promotion_testimonial", result["labels"])
        self.assertIn("technical_walkthrough", result["labels"])
        self.assertEqual(result["technical_depth"], "some")
        self.assertTrue(
            all(row["field"] == "summary" for row in result["signal_evidence"])
        )
        repeated = label_article(
            "Guide",
            "Configuration.",
            content="Configuration. " * 150,
            content_provenance="rss_content",
        )
        self.assertEqual(repeated["signals"], ["configuration"])
        self.assertEqual(repeated["technical_depth"], "uncertain")
        split = label_article(
            "Guide",
            "Profiling and limitations.",
            content="Configuration. " * 150,
            content_provenance="rss_content",
        )
        self.assertEqual(
            split["technical_depth"], "some"
        )  # Summary cannot promote weak content to substantial.
        informative = label_article(
            "Guide",
            "Read more.",
            content="Implementation configuration profiling.",
            content_provenance="rss_content",
        )
        self.assertEqual(informative["technical_depth"], "some")
        title_only = label_article(
            "Implementation configuration profiling",
            "Read more.",
            content="Visit our website.",
            content_provenance="rss_content",
        )
        self.assertEqual(title_only["signals"], [])

    def test_labels_explain_their_own_rules_even_without_depth(self):
        assessed = label_article("Customer story", "Book a demo.")
        self.assertEqual(assessed["technical_depth"], "uncertain")
        self.assertIn(
            {
                "label": "promotion_testimonial",
                "rule_id": "sales-demo-invitation",
                "field": "summary",
                "description": "Sales or demo invitation",
            },
            assessed["label_evidence"],
        )
        self.assertIn(
            {
                "label": "promotion_testimonial",
                "rule_id": "customer-promotion",
                "field": "title",
                "description": "Customer story, sponsorship or partnership language",
            },
            assessed["label_evidence"],
        )

    def test_paired_comparison_keeps_both_stages_and_prioritizes_changes(self):
        snapshot = self.collect(True)[2]
        row = snapshot["ranking_inputs"][0]
        row["article_labels"] = label_article("Service", "A teaser.")
        enriched = label_article(
            "Service",
            content="Implementation configuration profiling.",
            content_provenance="article_body",
        )
        snapshot["selected_article_labels"] = [
            {
                "title": row["title"],
                "url": row["url"],
                "source": row["source"],
                "assessment": enriched,
            }
        ]
        result = compare(snapshot)
        review = result["article_label_reviews"][0]
        self.assertTrue(review["changed"])
        self.assertEqual(
            review["differences"]["added_signals"],
            ["configuration", "implementation", "measurement"],
        )
        rendered = render(result)
        self.assertIn("| Feed | Unclassified", rendered)
        self.assertIn("| Selected | Technical walkthrough", rendered)
        self.assertIn("feed\\_summary", rendered)
        self.assertIn("article\\_body", rendered)
        self.assertLess(
            rendered.index("| Selected |"), rendered.index("| Feed | Opinion")
        )
        self.assertNotIn("| Depth |", rendered)
        self.assertEqual(
            result["orders"],
            compare({**snapshot, "selected_article_labels": []})["orders"],
        )

    def test_comparative_testing_and_marketing_are_clues_not_quality(self):
        testing = label_article(
            "Results",
            "We tested 12 frontier models. The new version improves performance by 61 percentage points.",
        )
        self.assertIn("research_evaluation", testing["labels"])
        self.assertIn("measurement", testing["signals"])
        marketing = label_article(
            "Customer story", "Our customers lead the benchmarks. Book a demo."
        )
        self.assertIn("promotion_testimonial", marketing["labels"])
        # Merely mentioning benchmarks is not verified evaluation or technical depth.
        self.assertEqual(marketing["technical_depth"], "uncertain")
        self.assertEqual(testing["technical_depth"], "uncertain")
        self.assertNotIn(
            "comparative-testing",
            [row["rule_id"] for row in marketing["label_evidence"]],
        )

    def test_representative_evidence_controls(self):
        dataset = json.loads(
            (Path(__file__).parent / "fixtures/article-label-evidence.json").read_text()
        )
        for row in dataset["cases"]:
            with self.subTest(case=row["id"]):
                assessed = label_article(
                    row["title"],
                    row.get("summary", ""),
                    content=row.get("content", ""),
                    content_format=row.get("content_format", "text"),
                    content_provenance=row.get("content_provenance", "missing"),
                )
                self.assertEqual(set(assessed["labels"]), set(row["expected_labels"]))
                self.assertEqual(set(assessed["signals"]), set(row["expected_signals"]))

    def collect(self, excerpts):
        source = report.Source(
            "Example forum", "https://example.com", "https://feed.test", 3
        )
        rows = [
            report.Item(
                "AI implementation guide",
                "https://example.com/guide",
                source.name,
                3,
                summary="Routing implementation with KV caches and profiling.",
                published=NOW,
                content="PRIVATE_ARTICLE_BODY",
                content_provenance="rss_content",
            ),
            report.Item(
                "An opinion",
                "https://example.com/opinion",
                source.name,
                3,
                summary="I think gardening is rewarding.",
                published=NOW,
            ),
        ]
        snapshot = {}
        with (
            patch.object(
                report, "fetch_url", return_value=(200, source.feed_url, "")
            ) as fetch,
            patch.object(report, "parse_source", return_value=copy.deepcopy(rows)),
            patch.object(
                report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            selected, diagnostics = report.collect_items(
                [source], NOW, evaluation=snapshot, evaluation_excerpts=excerpts
            )
        return selected, diagnostics, snapshot, (fetch.call_count, check.call_count)

    def test_capture_has_labels_for_admitted_and_rejected_without_selection_effect(
        self,
    ):
        baseline = self.collect(False)
        labeled = self.collect(True)
        self.assertEqual(
            [row.url for row in baseline[0]], [row.url for row in labeled[0]]
        )
        self.assertEqual(baseline[1], labeled[1])
        self.assertEqual(baseline[3], labeled[3])
        snapshot = labeled[2]
        self.assertNotIn("PRIVATE_ARTICLE_BODY", json.dumps(snapshot))
        result = compare(snapshot)
        self.assertEqual(len(result["article_labels"]), 2)
        self.assertEqual(
            [row["admitted"] for row in result["article_labels"]], [True, False]
        )
        rendered = render(result)
        self.assertIn("Best-effort article labels", rendered)
        self.assertIn("Opinion / discussion", rendered)
        self.assertIn("no ranking effect", rendered)
        self.assertNotIn("ranking_inputs", baseline[2])

    def test_selected_body_annotations_reuse_existing_retrieval_without_exporting_text(
        self,
    ):
        source = report.Source("Example", "https://example.com", "https://feed.test", 3)
        entry = report.Item(
            "AI implementation guide",
            "https://example.com/guide",
            source.name,
            3,
            summary="A brief teaser.",
            published=NOW,
        )
        body = (
            "PRIVATE_BODY_MARKER. Implementation uses configuration and KV caches. Profiling measures latency and documents trade-offs. "
            * 30
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            snapshot_path = Path(directory) / "candidates.json"
            with (
                patch.object(report, "load_sources", return_value=[source]),
                patch.object(
                    report, "fetch_url", return_value=(200, source.feed_url, "")
                ),
                patch.object(report, "parse_source", return_value=[entry]),
                patch.object(report, "check_url_accessible", return_value=(True, "")),
                patch.object(
                    report, "fetch_body", return_value=(body, "")
                ) as fetch_body,
                patch.object(report.dt, "datetime", wraps=dt.datetime) as clock,
            ):
                clock.now.return_value = NOW
                report.main(
                    [
                        "--output",
                        str(output),
                        "--evaluation-output",
                        str(snapshot_path),
                        "--evaluation-excerpts",
                    ]
                )
            fetch_body.assert_called_once()
            raw = snapshot_path.read_text()
            self.assertNotIn("PRIVATE_BODY_MARKER", raw)
            snapshot = json.loads(raw)
            initial = snapshot["ranking_inputs"][0]["article_labels"]
            enriched = snapshot["selected_article_labels"][0]["assessment"]
            self.assertEqual(initial["evidence"], "feed_summary")
            self.assertEqual(initial["technical_depth"], "uncertain")
            self.assertEqual(enriched["evidence"], "article_body")
            self.assertEqual(enriched["technical_depth"], "substantial")
            compared = compare(snapshot)
            self.assertEqual(len(compared["selected_article_labels"]), 1)
            self.assertIn("article\\_body", render(compared))
            snapshot["selected_article_labels"][0]["url"] = (
                "https://not-selected.test/article"
            )
            with self.assertRaises(ValueError):
                compare(snapshot)

    def test_frozen_owner_review_examples_reproduce_without_inferring_labels_from_grades(
        self,
    ):
        root = Path(__file__).resolve().parents[1]
        examples = json.loads(
            (
                root / "docs/evaluation/article-label-examples-2026-10-09.json"
            ).read_text()
        )["examples"]
        for example in examples:
            with self.subTest(url=example["url"]):
                actual = label_article(example["title"], example["summary_excerpt"])
                self.assertEqual(actual, example["reassessment_v2"])
                self.assertEqual(actual["technical_depth"], "uncertain")
                self.assertLessEqual(len(example["summary_excerpt"]), 1000)

    def test_historical_snapshot_and_external_text_render_safely(self):
        snapshot = self.collect(True)[2]
        legacy = copy.deepcopy(snapshot)
        for row in legacy["ranking_inputs"]:
            row.pop("article_labels")
        self.assertIn("No article labels captured", render(compare(legacy)))
        snapshot["ranking_inputs"][0]["title"] = "<script>alert(1)</script> | title"
        snapshot["ranking_inputs"][0]["article_labels"]["label_evidence"][0][
            "description"
        ] = "<img onerror=bad> | reason"
        rendered = render(compare(snapshot))
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;img", rendered)
        self.assertIn("\\| reason", rendered)


if __name__ == "__main__":
    unittest.main()
