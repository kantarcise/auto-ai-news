import copy
import datetime as dt
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report
from scripts.compare_contextual_admission import compare_context
from scripts.editorial_relevance import MAX_TEXT_CHARS, assess, load_config, tokens

NOW = dt.datetime(2026, 10, 8, 12, tzinfo=dt.timezone.utc)
NEGATIVES = [
    "Insurance agent opens a new office",
    "Fashion model poses for a magazine",
    "Electrical transformer maintenance",
    "Gemini horoscope for today",
    "Claude Monet exhibition opens",
    "Llama farm opens for visitors",
    "Mistral wind forecast",
    "Flux capacitor repairs",
    "Perfume diffusion measurements",
    "A neural anatomy exhibit",
]
POSITIVES = [
    ("An agent for code review", "Uses a language model to inspect patches."),
    ("A new model architecture", "A neural network for computer vision."),
    ("Transformer architecture", "Attention and tokenization for language models."),
    ("Gemini update", "A new multimodal language model with a larger context window."),
    ("Claude release", "LLM inference and improved reasoning."),
    ("Gemini99.17 announcement", ""),
    ("Claude-42 released", ""),
    ("Introducing Claude Opus", ""),
    ("Introducing Gemini model", ""),
    ("Introducing Mistral Large 4", ""),
    ("Introducing FLUX 99", ""),
    ("Disrupting a model-distillation campaign", ""),
    ("Training a model to grade reward hacks", ""),
    ("Deploying a generative recommender", ""),
    ("Vercel Agent installs packages from npm", ""),
    ("AI inference optimization workshop", ""),
    ("Machine learning research conference", ""),
]


class ContextualAdmissionTest(unittest.TestCase):
    def item(self, title, summary="", index=0):
        return report.Item(
            title, f"https://example.com/{index}", "Example", 3, summary, NOW
        )

    def test_negatives_through_assessment_final_admission_and_lab_classification(self):
        for title in NEGATIVES:
            with self.subTest(title=title):
                item = self.item(title)
                assessment = assess([{"title": title, "url": item.url}])[0]
                self.assertFalse(assessment.admitted)
                self.assertFalse(assessment.model_family)
                self.assertFalse(report.is_ai_related(item))
                item.category = "frontier_lab"
                item.editorial_relevance = assessment
                self.assertEqual(report.classify_story(item), "other")

    def test_paired_positive_headlines_and_summary_context(self):
        for title, summary in POSITIVES:
            with self.subTest(title=title):
                self.assertTrue(report.is_ai_related(self.item(title, summary)))

    def test_family_tokenization_cannot_be_undone_by_fallback_or_lab_bonus(self):
        config = load_config()
        for title in ("Gemini horoscope for today", "Claude Monet exhibition opens"):
            self.assertNotIn(
                "model_family",
                tokens(
                    title, config["model_families"], config["ambiguous_model_families"]
                ),
            )
        title = "Claude Monet and AI in 2026"
        item = self.item(title)
        item.category = "frontier_lab"
        item.editorial_relevance = assess([{"title": title, "url": item.url}])[0]
        self.assertTrue(
            report.is_ai_related(item)
        )  # AI context can make the article relevant.
        self.assertFalse(
            item.editorial_relevance.model_family
        )  # Monet is still the painter.
        self.assertEqual(report.classify_story(item), "other")

    def test_bounded_summary_context_and_unrelated_summaries(self):
        self.assertFalse(
            report.is_ai_related(self.item("Claude exhibition", "painting " * 10))
        )
        self.assertFalse(
            report.is_ai_related(
                self.item(
                    "Insurance agent opens an office",
                    "x" * MAX_TEXT_CHARS + " language model",
                )
            )
        )
        self.assertFalse(
            report.is_ai_related(self.item("Gardening tips", "GPU PyTorch LLM"))
        )
        self.assertFalse(
            report.is_ai_related(self.item("Fashion model", "more model model model"))
        )

    def test_full_collection_preserves_dates_diagnostics_and_shadow_ranking(self):
        source = report.Source("Example", "https://example.com", "https://feed", 3)
        entries = [self.item(title, index=i) for i, title in enumerate(NEGATIVES)]
        entries += [
            self.item(title, summary, i + 100)
            for i, (title, summary) in enumerate(POSITIVES)
        ]
        stale = self.item("Claude99 old", index=999)
        stale.published = NOW - dt.timedelta(hours=73)
        entries.append(stale)
        snapshot = {}
        with (
            patch.object(report, "fetch_url", return_value=(200, "https://feed", "")),
            patch.object(report, "parse_source", return_value=copy.deepcopy(entries)),
            patch.object(
                report, "check_url_accessible", return_value=(True, "")
            ) as check,
        ):
            selected, unavailable = report.collect_items(
                [source], NOW, evaluation=snapshot
            )
        self.assertEqual(len(selected), report.MAX_PER_PUBLISHER)
        self.assertTrue(
            {item.title for item in selected} <= {title for title, _ in POSITIVES}
        )
        self.assertEqual(check.call_count, report.MAX_PER_PUBLISHER)
        self.assertTrue(
            all(
                row["rejection_reason"] == ""
                for row in snapshot["collection"][len(NEGATIVES) : -1]
            )
        )
        self.assertEqual(
            snapshot["collection"][-1]["rejection_reason"], "older than coverage window"
        )
        self.assertTrue(any("Freshness:" in reason for _, reason in unavailable))
        self.assertTrue(
            {item.url for item in selected}
            <= set(snapshot["shadow_ranking"]["current_order"])
        )

    def test_publisher_bypass_remains_an_explicit_limitation(self):
        item = self.item("Insurance agent opens an office")
        for source in ("Latent Space", "smol.ai"):
            item.source = source
            self.assertTrue(report.is_ai_related(item))

    def test_context_admission_is_stable_across_unrelated_candidate_pools(self):
        rows = [
            {"title": title, "summary": summary, "url": f"https://example.com/{i}"}
            for i, (title, summary) in enumerate(POSITIVES)
        ]
        results = assess(rows)
        repeated = assess(
            rows
            + [{"title": "Robot work", "url": f"https://other/{i}"} for i in range(50)]
        )
        self.assertEqual(
            [(a.admitted, a.model_family) for a in results],
            [(a.admitted, a.model_family) for a in repeated[: len(rows)]],
        )

    def test_comparison_rejects_mismatched_previous_capture(self):
        directory = Path(__file__).resolve().parents[1] / "docs/evaluation"
        snapshot = json.loads(
            (directory / "relevance-input-2026-10-06.json").read_text()
        )
        feedback = json.loads(
            (directory / "owner-feedback-2026-10-06.json").read_text()
        )
        original = json.loads(
            (directory / "editorial-results-2026-10-06.json").read_text()
        )
        for mutate in (
            lambda old: old.update(captured_at="different"),
            lambda old: old["decisions"].pop(),
            lambda old: old["decisions"][0].update(title="different"),
            lambda old: old["decisions"][0].update(owner_include="no"),
            lambda old: old["decisions"][0].update(profile_admitted="yes"),
        ):
            previous = copy.deepcopy(original)
            mutate(previous)
            with self.assertRaises(ValueError):
                compare_context(snapshot, feedback, previous)
