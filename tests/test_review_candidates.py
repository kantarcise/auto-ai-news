import copy
import unittest

from scripts.review_candidates import evaluate, prepare, validate


def snapshot():
    rows = [
        {
            "url": f"https://example.com/{i}",
            "title": f"AI {i}",
            "source": "Example",
            "published": "2026-10-03T00:00:00Z",
        }
        for i in range(2)
    ]
    return {
        "captured_at": "2026-10-03T12:00:00Z",
        "policies": {
            "baseline": {"candidates": rows, "selected": rows},
            "frontier": {"candidates": rows, "selected": rows[:1]},
        },
    }


class ReviewCandidatesTest(unittest.TestCase):
    def test_unreviewed_items_are_not_negative_labels(self):
        data = snapshot()
        review = prepare(data)
        metrics = evaluate(data, review)
        self.assertEqual(metrics["reviewed_candidates"], 0)
        for policy in metrics["policies"].values():
            self.assertIsNone(policy["precision_on_reviewed_selected"])
            self.assertIsNone(policy["recall_on_reviewed_candidates"])
            self.assertEqual(policy["review_coverage"], 0)

    def test_known_precision_recall_and_partial_coverage(self):
        data = snapshot()
        review = prepare(data)
        review["reviewer"] = "Test reviewer"
        review["items"][0].update(
            relevant="yes",
            include="yes",
            importance=3,
            story_id="model-launch",
            evidence="article",
        )
        partial = evaluate(data, review)
        self.assertEqual(partial["policies"]["baseline"]["review_coverage"], 0.5)
        review["items"][1].update(relevant="yes", include="no", evidence="article")
        metrics = evaluate(data, review)
        self.assertEqual(
            metrics["policies"]["baseline"]["precision_on_reviewed_selected"], 0.5
        )
        self.assertEqual(
            metrics["policies"]["frontier"]["precision_on_reviewed_selected"], 1
        )
        self.assertEqual(
            metrics["policies"]["frontier"]["recall_on_reviewed_candidates"], 1
        )

    def test_snapshot_identity_and_all_rows_are_required(self):
        data = snapshot()
        original = prepare(data)
        mutations = [
            lambda r: r.update(snapshot_captured_at="wrong"),
            lambda r: r["items"].pop(),
            lambda r: r["items"].append(r["items"][0]),
            lambda r: r["items"][0].update(url="https://wrong.example"),
        ]
        for mutate in mutations:
            review = copy.deepcopy(original)
            mutate(review)
            with self.assertRaises(ValueError):
                validate(data, review)

    def test_inconsistent_and_unavailable_labels_are_rejected(self):
        data = snapshot()
        review = prepare(data)
        review["reviewer"] = "Test reviewer"
        item = review["items"][0]
        item.update(
            include="yes",
            relevant="no",
            importance=3,
            story_id="story",
            evidence="article",
        )
        with self.assertRaises(ValueError):
            validate(data, review)
        item.update(relevant="yes", evidence="unavailable")
        with self.assertRaises(ValueError):
            validate(data, review)
        item.update(include="unsure", importance=None)
        validate(data, review)
