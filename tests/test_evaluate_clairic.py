import unittest

from scripts.evaluate_clairic import payload, review_result


class ClairicExperimentTest(unittest.TestCase):
    def test_review_preserves_evidence_and_scores_missing_values(self):
        case = {
            "text": "Clef context: 65,536 tokens",
            "metric": "Model context window in tokens.",
            "expected": {"model_name": "Clef", "hardware": None, "metric_value": 65536},
        }
        self.assertNotIn("expected", payload(case))
        self.assertNotIn("65536", str(payload(case)))
        body = {
            "success": True,
            "result": {
                "answers": {
                    "model_name": {"value": "context", "span": [5, 12]},
                    "hardware": {"value": None, "guess": "Clef", "span": [0, 4]},
                    "metric_value": {"value": 65536, "span": [14, 20]},
                },
                "usage": {"input_tokens": 120, "passes": 3},
            },
        }

        result = review_result(body, case)

        self.assertFalse(result["fields"]["model_name"]["match"])
        self.assertEqual(result["fields"]["model_name"]["source_slice"], "context")
        self.assertEqual(
            result["fields"]["hardware"],
            {"value": None, "expected": None, "match": True},
        )
        self.assertEqual(result["fields"]["metric_value"]["source_slice"], "65,536")
        self.assertEqual(result["usage"], {"input_tokens": 120, "passes": 3})

        body["result"]["answers"]["metric_value"]["value"] = True
        with self.assertRaisesRegex(ValueError, "unexpected field type"):
            review_result(body, case)
