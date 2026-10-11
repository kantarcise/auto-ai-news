"""Closure comparison regressions; production admission is left untouched."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compare_final_admission import compare_final, main
from scripts.review_candidates import candidate_id

ROOT = Path(__file__).resolve().parents[1]


class FinalAdmissionTests(unittest.TestCase):
    def inputs(self, date):
        directory = ROOT / "docs/evaluation"
        return [
            json.loads((directory / f"{prefix}-{date}.json").read_text())
            for prefix in ("relevance-input", "owner-feedback")
        ]

    def test_saved_reviews_and_gates(self):
        september = compare_final(*self.inputs("2026-09-30"))
        october = compare_final(*self.inputs("2026-10-06"))
        self.assertEqual(september["candidate_count"], 24)
        self.assertEqual(october["candidate_count"], 45)
        self.assertEqual(september["policies"]["current"]["wanted_admitted"], 7)
        self.assertEqual(october["policies"]["current"]["wanted_admitted"], 11)
        self.assertEqual(september["changes"], [])
        self.assertEqual(len(october["changes"]), 1)
        self.assertEqual(
            october["changes"][0]["title"],
            "The Agent Said It Was Done. The Database Disagreed.",
        )
        self.assertIsNone(october["changes"][0]["owner_include"])
        self.assertEqual(october["policies"]["current"]["admitted"], 26)
        self.assertEqual(october["policies"]["broader"]["admitted"], 27)
        for result in (september, october):
            self.assertEqual(result["recovered_wanted"], [])
            self.assertEqual(result["added_unwanted"], [])
            self.assertEqual(result["wanted_still_rejected"], [])
            for policy in result["policies"].values():
                self.assertEqual(policy["unwanted_admitted"], 0)
            self.assertNotIn("selected", result)

    def test_generic_keyword_recovery_also_admits_ordinary_non_ai_use(self):
        snapshot, feedback = self.inputs("2026-10-06")
        extra = {
            "title": "An insurance agent explains household claims",
            "url": "https://example.com/insurance",
            "source": "Example",
            "published": "2026-10-06T12:00:00+00:00",
            "rejection_reason": "title relevance filter",
        }
        snapshot["collection"].append(extra)
        # Explicitly synthetic review, kept out of committed real-data results.
        feedback["items"].append(
            {
                "id": candidate_id(extra["url"]),
                "url": extra["url"],
                "title": extra["title"],
                "include": "no",
                "importance": 0,
                "inspection_evidence": "title",
                "evidence": "user_feedback",
            }
        )
        result = compare_final(snapshot, feedback)
        self.assertEqual(result["added_unwanted"][0]["url"], extra["url"])
        self.assertEqual(result["policies"]["current"]["unwanted_admitted"], 0)
        extra["rejection_reason"] = "quiet-day title policy"
        gated = compare_final(snapshot, feedback)
        self.assertEqual(gated["added_unwanted"], [])

    def test_provenance_and_inputs_preserved(self):
        snapshot, feedback = self.inputs("2026-10-06")
        original = copy.deepcopy((snapshot, feedback))
        compare_final(snapshot, feedback)
        self.assertEqual((snapshot, feedback), original)
        feedback["snapshot_sha256"] = "different"
        with self.assertRaises(ValueError):
            compare_final(snapshot, feedback)

    def test_cli_reproduces_results_and_prevents_overwrites(self):
        root = ROOT / "docs/evaluation"
        for date in ("2026-09-30", "2026-10-06"):
            snapshot = root / f"relevance-input-{date}.json"
            feedback = root / f"owner-feedback-{date}.json"
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "result.json"
                main([str(snapshot), str(feedback), "--output", str(output)])
                expected = json.loads(
                    (root / f"final-admission-results-{date}.json").read_text()
                )
                actual = json.loads(output.read_text())
                implementation = actual.pop("implementation_sha256")
                expected.pop("implementation_sha256")
                self.assertEqual(actual, expected)
                self.assertTrue(implementation)
                self.assertTrue(
                    all(len(value) == 64 for value in implementation.values())
                )
            with self.assertRaises(SystemExit):
                main([str(snapshot), str(feedback), "--output", str(snapshot)])


if __name__ == "__main__":
    unittest.main()
