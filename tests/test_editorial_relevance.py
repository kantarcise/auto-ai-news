import copy
import datetime as dt
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts.compare_contextual_admission import compare_context
from scripts.compare_editorial import compare_editorial
from scripts.editorial_relevance import assess, load_config, tokens

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 10, 8, 12, tzinfo=dt.timezone.utc)


def row(title, summary="", url="https://example.com/story"):
    return {"title": title, "summary": summary, "url": url}


class EditorialRelevanceTest(unittest.TestCase):
    def test_future_versions_and_configured_new_families(self):
        config = load_config()
        for title in ("Qwen99.17 27B", "Claude-42", "Gemini 73 Argon", "GLM8.2"):
            self.assertIn("model_family", tokens(title, config["model_families"]))
            self.assertTrue(assess([row(title)], config)[0].admitted)
        for title in ("Qwen99foo", "Qwen99.17foo", "myclaudeutility", "gptish"):
            self.assertNotIn("model_family", tokens(title, config["model_families"]))
        config["model_families"].append("newfamily")
        self.assertTrue(assess([row("Introducing Newfamily100.7")], config)[0].admitted)
        self.assertFalse(assess([row("Introducing Newfamily100.7")])[0].admitted)

    def test_ambiguous_family_names_need_model_context_or_a_version(self):
        for title in ("Seed funding tips", "Nova garden show", "An inkling of spring"):
            self.assertFalse(assess([row(title)])[0].admitted)
        for title in ("Nova99 released", "Introducing Seed language model"):
            self.assertTrue(assess([row(title)])[0].admitted)

    def test_summary_context_changes_score_but_cannot_admit_unrelated_headline(self):
        plain = row("GPU cluster configuration")
        detailed = row(
            plain["title"],
            "GPU CUDA runtime deployment throughput latency memory performance kernel",
        )
        self.assertGreater(
            assess([detailed])[0].similarity, assess([plain])[0].similarity
        )
        spam = row("Gardening tips", "GPU CUDA PyTorch " * 10000)
        self.assertFalse(assess([spam])[0].admitted)
        self.assertFalse(assess([row("GPUish gardening")])[0].admitted)

    def test_pool_weights_adapt_without_duplicates_or_input_mutation(self):
        rows = [row("GPU cluster runtime"), row("TTS leaderboard", url="https://other")]
        original = copy.deepcopy(rows)
        scores = assess(rows)
        duplicate = assess(rows + [rows[0]])
        self.assertEqual(scores, duplicate[:2])
        self.assertEqual(scores, list(reversed(assess(list(reversed(rows))))))
        larger = rows + [
            row("GPU cluster runtime", url=f"https://example.com/{i}") for i in range(8)
        ]
        self.assertNotEqual(scores[0].similarity, assess(larger)[0].similarity)
        self.assertEqual(rows, original)

    def test_event_listing_exclusion_keeps_technical_conference_guides(self):
        rows = [
            row("March to Stop Building AI", url="https://lesswrong.com/events/march"),
            row("A PyTorch conference guide", url="https://example.com/events/guide"),
        ]
        first, second = assess(rows)
        self.assertTrue(first.event_listing)
        self.assertFalse(second.event_listing)
        self.assertTrue(second.admitted)

    def test_bonus_is_shadow_only_and_is_bounded(self):
        generic = report.Item(
            "AI update", "https://example.com/ai", "Example", 3, published=NOW
        )
        technical = report.Item(
            "GPU cluster runtime configuration",
            "https://example.com/gpu",
            "Example",
            3,
            published=NOW,
        )
        rows = [row(item.title, url=item.url) for item in (generic, technical)]
        for item, assessment in zip((generic, technical), assess(rows)):
            item.editorial_relevance = assessment
            report.score_item(item, NOW)
            self.assertLessEqual(assessment.proposed_rank_bonus, 1)
        self.assertEqual(technical.rank_score, generic.rank_score)
        self.assertGreater(
            technical.rank_score + technical.editorial_relevance.proposed_rank_bonus,
            generic.rank_score + generic.editorial_relevance.proposed_rank_bonus,
        )

    def test_ambiguous_topic_anchors_need_supporting_technical_context(self):
        for title in (
            "A speech at the wedding",
            "Vector illustration tips for designers",
            "Olympic torch arrives in Paris",
        ):
            assessment = assess([row(title)])[0]
            self.assertFalse(assessment.admitted, title)
            self.assertEqual(assessment.proposed_rank_bonus, 0)
            self.assertFalse(
                report.is_ai_related(
                    report.Item(title, "https://example.com", "Example", 3)
                )
            )
        for title in (
            "Vector search joins",
            "Speech voice cloning evaluation",
            "Torch compiler integration",
        ):
            self.assertTrue(assess([row(title)])[0].admitted, title)

    def test_eligibility_survives_cross_url_syndication(self):
        title = "What work can robots do?"
        rows = [row(title, url=f"https://example.com/{i}") for i in range(21)]
        alone = assess(rows[:1])[0]
        repeated = assess(rows)
        self.assertTrue(alone.admitted)
        self.assertTrue(all(assessment.admitted for assessment in repeated))
        self.assertNotEqual(alone.similarity, repeated[0].similarity)

    def test_technical_events_outside_profiles_preserve_legacy_eligibility(self):
        for title in (
            "AI inference optimization workshop",
            "Machine learning research conference",
        ):
            item = report.Item(
                title, "https://example.com/events/workshop", "Example", 3
            )
            item.editorial_relevance = assess([row(title, url=item.url)])[0]
            self.assertFalse(item.editorial_relevance.event_listing)
            self.assertTrue(report.is_ai_related(item))

    def test_shadow_capture_records_order_without_changing_selection(self):
        source = report.Source("Example", "https://example.com", "https://feed", 3)
        entries = [
            report.Item(
                "AI update", "https://example.com/ai", "Example", 3, published=NOW
            ),
            report.Item(
                "GPU cluster runtime configuration",
                "https://example.com/gpu",
                "Example",
                3,
                published=NOW - dt.timedelta(seconds=1),
            ),
        ]
        snapshot = {}
        with (
            patch.object(report, "fetch_url", return_value=(200, "https://feed", "")),
            patch.object(report, "parse_source", return_value=entries),
            patch.object(report, "check_url_accessible", return_value=(True, "")),
        ):
            selected, _ = report.collect_items([source], NOW, evaluation=snapshot)
        ranking = snapshot["shadow_ranking"]
        self.assertEqual([item.url for item in selected], ranking["current_order"])
        self.assertEqual(ranking["current_order"], [entry.url for entry in entries])
        self.assertEqual(
            ranking["proposed_order"], [entry.url for entry in reversed(entries)]
        )

    def test_normalized_future_model_receives_existing_lab_classification(self):
        item = report.Item(
            "Qwen99.17 released",
            "https://example.com/model",
            "Example",
            3,
            category="frontier_lab",
        )
        item.editorial_relevance = assess([row(item.title)])[0]
        self.assertEqual(report.classify_story(item), "lab_announcement")
        item.title = "Introducing Qwen99.17 GPU cluster runtime performance"
        item.editorial_relevance = assess([row(item.title)])[0]
        self.assertEqual(
            item.editorial_relevance.topic, "GPU and framework engineering"
        )
        self.assertTrue(item.editorial_relevance.model_family)
        self.assertEqual(report.classify_story(item), "lab_announcement")

    def test_collection_integration_preserves_freshness_and_records_explanations(self):
        source = report.Source("Example", "https://example.com", "https://feed", 3)
        titles = [
            "What work can robots do?",
            "Open TTS leaderboard",
            "March to Stop Building AI",
        ]
        entries = [
            report.Item(
                title,
                f"https://example.com/{'events/' if i == 2 else ''}{i}",
                "Example",
                3,
                published=NOW,
            )
            for i, title in enumerate(titles)
        ]
        entries.append(
            report.Item(
                "GPU old",
                "https://example.com/old",
                "Example",
                3,
                published=NOW - dt.timedelta(hours=73),
            )
        )
        snapshot = {}
        with (
            patch.object(report, "fetch_url", return_value=(200, "https://feed", "")),
            patch.object(report, "parse_source", return_value=entries),
            patch.object(
                report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            selected, _ = report.collect_items([source], NOW, evaluation=snapshot)
        self.assertEqual({item.title for item in selected}, set(titles[:2]))
        self.assertEqual(check.call_count, 2)
        self.assertEqual(
            snapshot["collection"][2]["rejection_reason"],
            "event listing without technical topic",
        )
        self.assertEqual(
            snapshot["collection"][3]["rejection_reason"], "older than coverage window"
        )
        self.assertNotIn("editorial_relevance", snapshot["collection"][3])
        self.assertEqual(
            snapshot["collection"][0]["editorial_relevance"]["topic"],
            "robotics research",
        )

    def test_frozen_comparison_is_reproducible_offline_and_keeps_uncertainty(self):
        totals = [0, 0]
        for date in ("2026-10-06", "2026-09-30"):
            directory = ROOT / "docs/evaluation"
            paths = [
                directory / f"relevance-input-{date}.json",
                directory / f"owner-feedback-{date}.json",
            ]
            snapshot, feedback = [json.loads(path.read_text()) for path in paths]
            before = copy.deepcopy((snapshot, feedback))
            with patch(
                "urllib.request.urlopen", side_effect=AssertionError("No network")
            ):
                result = compare_editorial(snapshot, feedback)
            self.assertEqual((snapshot, feedback), before)
            saved = json.loads(
                (directory / f"editorial-results-{date}.json").read_text()
            )
            self.assertEqual(
                saved.pop("input_sha256"),
                dict(
                    zip(
                        ("snapshot", "feedback"),
                        [
                            hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in paths
                        ],
                    )
                ),
            )
            # Keep PR #27 results frozen; compare new behavior in a separate
            # artifact instead of rewriting historical admission decisions.
            delta = compare_context(snapshot, feedback, saved)
            followup = json.loads(
                (directory / f"context-results-{date}.json").read_text()
            )
            followup_hashes = followup.pop("input_sha256")
            self.assertEqual(
                followup_hashes["previous"],
                hashlib.sha256(
                    (directory / f"editorial-results-{date}.json").read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(delta, followup)
            totals[0] += result["policies"]["profile"]["owner_wanted_admitted"]
            totals[1] += result["policies"]["profile"]["owner_unwanted_admitted"]
            self.assertTrue(
                all(
                    row["frozen_link_outcome"] is None
                    for row in result["decisions"]
                    if row["url"] not in snapshot["link_outcomes"]
                )
            )
        self.assertEqual(totals, [18, 0])
