import copy
import datetime as dt
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.compare_relevance import compare, topic_matches
from scripts.generate_report import Item, is_ai_related
from scripts.review_candidates import candidate_id

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    snapshot = {
        "captured_at": "2026-10-06T12:00:00+00:00",
        "lookback_hours": 72,
        "source_snapshot_sha256": "test-source",
        "collection": [
            {
                "title": title,
                "url": f"https://example.com/{i}",
                "source": "Example",
                "published": "2026-10-06T00:00:00+00:00",
                "rejection_reason": reason,
            }
            for i, (title, reason) in enumerate(
                [
                    ("Qwen3.8 experiments", "title relevance filter"),
                    ("March to stop building AI", ""),
                    ("GPU cluster setup", "title relevance filter"),
                    ("Gardening tips", "title relevance filter"),
                ]
            )
        ],
        "selected_representatives": [],
        "link_outcomes": {},
    }
    feedback = {
        "snapshot_captured_at": snapshot["captured_at"],
        "snapshot_sha256": snapshot["source_snapshot_sha256"],
        "items": [
            {
                "id": candidate_id(row["url"]),
                "url": row["url"],
                "title": row["title"],
                "include": "yes" if i == 0 else "no",
                "importance": 2 if i == 0 else 0,
                "evidence": "user_feedback",
                "inspection_evidence": None,
            }
            for i, row in enumerate(snapshot["collection"][:2])
        ],
    }
    return snapshot, feedback


class CompareRelevanceTest(unittest.TestCase):
    def test_production_admits_tested_topics_without_source_or_summary_shortcuts(self):
        for title in (
            "Qwen3.8 27B experiments",
            "PyTorch conference guide",
            "GPU cluster setup",
            "ROCm data movement",
            "Vector search joins",
        ):
            self.assertTrue(
                is_ai_related(Item(title, "https://example.com", "Example", 3))
            )
        for title in ("Gardening tips", "Qwen3.8foo", "GPUish utility"):
            self.assertFalse(
                is_ai_related(
                    Item(
                        title,
                        "https://example.com",
                        "PyTorch",
                        3,
                        summary="GPU PyTorch",
                    )
                )
            )

    def test_second_date_preferences_and_production_match_frozen_alternative(self):
        snapshot = json.loads(
            (ROOT / "docs/evaluation/relevance-input-2026-09-30.json").read_text()
        )
        feedback = json.loads(
            (ROOT / "docs/evaluation/owner-feedback-2026-09-30.json").read_text()
        )
        result = compare(snapshot, feedback)
        self.assertEqual(result["owner_wanted"], 7)
        self.assertEqual(result["owner_unwanted"], 1)
        self.assertEqual(result["policies"]["current"]["owner_wanted_admitted"], 2)
        self.assertEqual(result["policies"]["alternative"]["owner_wanted_admitted"], 5)
        added = [
            row for row in result["decisions"] if row["id"] in result["newly_admitted"]
        ]
        self.assertEqual(len(added), 3)
        self.assertTrue(all(row["owner_include"] == "yes" for row in added))
        saved = json.loads(
            (ROOT / "docs/evaluation/relevance-results-2026-09-30.json").read_text()
        )
        hashes = saved.pop("input_sha256")
        self.assertEqual(saved, result)
        for field, filename in (
            ("snapshot", "relevance-input-2026-09-30.json"),
            ("feedback", "owner-feedback-2026-09-30.json"),
        ):
            self.assertEqual(
                hashes[field],
                hashlib.sha256(
                    (ROOT / "docs/evaluation" / filename).read_bytes()
                ).hexdigest(),
            )
        for row in result["decisions"]:
            self.assertEqual(
                is_ai_related(Item(row["title"], row["url"], row["source"], 0)),
                row["alternative_admitted"],
            )
        self.assertEqual(
            next(row for row in feedback["items"] if row["include"] == "no")[
                "importance"
            ],
            None,
        )
        result_without_clock = copy.deepcopy(snapshot)
        result_without_clock.pop("assessment_at")
        with self.assertRaises(ValueError):
            compare(result_without_clock, feedback)

    def test_word_boundaries_and_versioned_names(self):
        for title in [
            "Qwen3.8 27B",
            "GPT-6 release",
            "Llama 4",
            "PyTorch hardware",
            "GPU performance",
            "ROCm 10.1",
            "Vector search joins",
        ]:
            self.assertTrue(topic_matches(title), title)
        for title in [
            "qwenish",
            "Qwen3foo",
            "Qwen3.8foo",
            "mygpuutility",
            "vector searching",
            "GPUish",
            "gardening",
        ]:
            self.assertEqual(topic_matches(title), [], title)

    def test_preferences_uncertainty_and_no_network_or_input_mutation(self):
        snapshot, feedback = inputs()
        before = copy.deepcopy((snapshot, feedback))
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network")):
            result = compare(snapshot, feedback)
        self.assertEqual((snapshot, feedback), before)
        self.assertEqual(result["policies"]["current"]["admitted"], 1)
        self.assertEqual(result["policies"]["alternative"]["admitted"], 3)
        self.assertEqual(result["policies"]["alternative"]["owner_wanted_admitted"], 1)
        self.assertEqual(
            result["policies"]["alternative"]["owner_unwanted_admitted"], 1
        )
        self.assertEqual(
            result["policies"]["alternative"]["no_decided_preference_admitted"], 1
        )
        self.assertEqual(result["confirmed_article_inspections"], 0)
        self.assertTrue(
            all(row["frozen_link_outcome"] is None for row in result["decisions"])
        )

    def test_window_boundaries_unknown_dates_and_quiet_day_policy(self):
        snapshot, feedback = inputs()
        now = dt.datetime.fromisoformat(snapshot["captured_at"])
        for i, published in enumerate(
            [
                now - dt.timedelta(hours=72),
                now - dt.timedelta(hours=72, seconds=1),
                now + dt.timedelta(seconds=1),
                None,
            ]
        ):
            snapshot["collection"].append(
                {
                    "title": "GPU setup",
                    "url": f"https://example.com/extra-{i}",
                    "source": "Example",
                    "published": published.isoformat() if published else None,
                    "rejection_reason": "title relevance filter",
                }
            )
        snapshot["collection"].append(
            {
                "title": "GPU quiet-day example",
                "url": "https://example.com/quiet",
                "source": "Latent Space",
                "published": now.isoformat(),
                "rejection_reason": "quiet-day title policy",
            }
        )
        result = compare(snapshot, feedback)
        self.assertEqual(result["recent_candidates"], 6)
        quiet = next(row for row in result["decisions"] if row["url"].endswith("quiet"))
        self.assertFalse(quiet["alternative_admitted"])

    def test_current_bypass_and_access_failures_are_preserved(self):
        snapshot, feedback = inputs()
        snapshot["collection"][3]["rejection_reason"] = ""
        snapshot["collection"][3]["source"] = "Latent Space"
        snapshot["link_outcomes"]["https://example.com/0"] = {
            "accessible": False,
            "reason": "HTTP 403.",
        }
        result = compare(snapshot, feedback)
        admitted = next(row for row in result["decisions"] if row["url"].endswith("/3"))
        self.assertTrue(admitted["alternative_admitted"])
        blocked = next(row for row in result["decisions"] if row["url"].endswith("/0"))
        self.assertFalse(blocked["actually_selected"])
        self.assertEqual(blocked["frozen_link_outcome"]["reason"], "HTTP 403.")

    def test_mismatched_and_invalid_feedback_is_rejected(self):
        snapshot, original = inputs()
        mutations = [
            lambda f: f.update(snapshot_captured_at="different"),
            lambda f: f.update(snapshot_sha256="different"),
            lambda f: f["items"][0].update(url="https://wrong"),
            lambda f: f["items"][0].update(id="wrong"),
            lambda f: f["items"][0].update(title="wrong"),
            lambda f: f["items"].append(f["items"][0]),
            lambda f: f["items"][0].update(importance=True),
            lambda f: f["items"][0].update(include="maybe"),
            lambda f: f["items"][0].update(inspection_evidence="invented"),
        ]
        for mutate in mutations:
            feedback = copy.deepcopy(original)
            mutate(feedback)
            with self.assertRaises(ValueError):
                compare(snapshot, feedback)

    def test_real_frozen_comparison_counts_and_owner_recoveries(self):
        snapshot = json.loads(
            (ROOT / "docs/evaluation/relevance-input-2026-10-06.json").read_text()
        )
        feedback = json.loads(
            (ROOT / "docs/evaluation/owner-feedback-2026-10-06.json").read_text()
        )
        result = compare(snapshot, feedback)
        self.assertEqual(result["recent_candidates"], 45)
        self.assertEqual(result["owner_wanted"], 11)
        self.assertEqual(result["confirmed_article_inspections"], 5)
        self.assertEqual(result["policies"]["current"]["admitted"], 19)
        self.assertEqual(result["policies"]["alternative"]["admitted"], 27)
        added = [
            row for row in result["decisions"] if row["id"] in result["newly_admitted"]
        ]
        self.assertEqual(sum(row["owner_include"] == "yes" for row in added), 8)
        self.assertEqual(sum(row["owner_include"] is None for row in added), 0)
        saved = json.loads(
            (ROOT / "docs/evaluation/relevance-results-2026-10-06.json").read_text()
        )
        hashes = saved.pop("input_sha256")
        self.assertEqual(saved, result)
        for field, filename in (
            ("snapshot", "relevance-input-2026-10-06.json"),
            ("feedback", "owner-feedback-2026-10-06.json"),
        ):
            self.assertEqual(
                hashes[field],
                hashlib.sha256(
                    (ROOT / "docs/evaluation" / filename).read_bytes()
                ).hexdigest(),
            )
