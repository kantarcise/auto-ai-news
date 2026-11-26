import json
import unittest
import urllib.error
from unittest.mock import MagicMock, Mock

from scripts import production_model_report
from scripts.enrich_daily_clairic import enrich, request_english, validated_english
from scripts.generate_report import markdown_link
from scripts.preview_clairic import read_response
from scripts.publication_history import receipt_comment
from tests.test_compare_model_reports import NOW, Provider, row, snapshot


def unchanged(excerpt, context):
    return excerpt


def approved(headline, source, context, candidate):
    return True


def report_inputs(count):
    articles = [
        {"id": i, "title": f"GPU (test) {i}", "url": f"https://example.com/{i}"}
        for i in range(count)
    ]
    snapshot = {
        "collection": [
            {
                "title": article["title"],
                "article_evidence": {
                    "text": "Measured 32 GB per GPU.",
                    "provenance": "article_body",
                },
            }
            for article in articles
        ]
    }
    selection = {
        "selection": "model-assisted",
        "selected_articles": articles,
        "decisions": [
            {
                "url": article["url"],
                "id": i,
                "applied": True,
                "candidate_admit": True,
                "answers": {"engineering_detail": "yes"},
            }
            for i, article in enumerate(articles)
        ],
    }
    report = "## New articles\n\n" + "".join(
        f"{i}. **{markdown_link(row['title'], row['url'])}**  \n   Metadata\n\n"
        for i, row in enumerate(articles, 1)
    )
    receipt = receipt_comment("2026-11-22", [row["url"] for row in articles])
    return report + receipt, snapshot, selection, receipt


class DailyClairicTest(unittest.TestCase):
    def test_uses_completed_chat_content_instead_of_reasoning(self):
        opener = MagicMock()
        read = opener.open.return_value.__enter__.return_value.read
        choice = {
            "finish_reason": "stop",
            "message": {"content": "47 seconds", "reasoning_content": "unused"},
        }
        body = {"success": True, "result": {"choices": [choice]}}
        read.return_value = json.dumps(body).encode()
        self.assertEqual(
            request_english(opener, "account", "token", "47초"), "47 seconds"
        )
        request = opener.open.call_args.args[0]
        self.assertEqual(
            json.loads(request.data)["chat_template_kwargs"], {"enable_thinking": False}
        )

        choice["finish_reason"] = "length"
        read.return_value = json.dumps(body).encode()
        self.assertIsNone(request_english(opener, "account", "token", "47초"))

    def test_uses_the_real_clef_output_contract(self):
        captured = snapshot([row(0, title="An AI benchmark (GPU)"), row(1)])
        captured["publication_history"] = {
            "report_date": NOW.date().isoformat(),
            "published": {},
        }
        report, selection = production_model_report.select_report(
            "Saved baseline", captured, provider=Provider()
        )
        extract = Mock(
            return_value=(
                {"input_tokens": 100, "passes": 1},
                {"detail": ("The board has 32 GB per GPU.", "source context")},
                None,
            )
        )
        updated, status = enrich(
            report, captured, selection, extract, translate=unchanged, verify=approved
        )
        self.assertIn("## New articles", updated)
        self.assertIn("Source detail (Clairic)", updated)
        self.assertEqual(status["shown"], 2)
        self.assertEqual(extract.call_count, 2)

    def test_decorates_up_to_fifteen_ranked_stories_and_preserves_receipt(self):
        report, snapshot, selection, receipt = report_inputs(17)
        extract = Mock(
            return_value=(
                {"input_tokens": 100, "passes": 1},
                {
                    "detail": (
                        "The board has 32 GB per GPU <example>.",
                        "source context",
                    )
                },
                None,
            )
        )
        updated, status = enrich(
            report, snapshot, selection, extract, translate=unchanged, verify=approved
        )
        self.assertEqual(extract.call_count, 15)
        self.assertEqual(
            status,
            {
                "attempts": 15,
                "shown": 15,
                "input_tokens": 1500,
                "passes": 15,
                "stop": "budget",
                "english_attempts": 15,
                "english_checks": 15,
                "english_rendered": 0,
                "english_skipped": 0,
            },
        )
        self.assertEqual(updated.count("Source detail (Clairic)"), 15)
        self.assertIn(
            "Metadata  \n   Source detail (Clairic) · “The board has 32 GB per GPU &lt;example&gt;\\.”",
            updated,
        )
        self.assertTrue(updated.endswith(receipt))

    def test_reported_token_budget_can_stop_before_request_cap(self):
        report, snapshot, selection, _ = report_inputs(17)
        extract = Mock(return_value=({"input_tokens": 8000, "passes": 1}, {}, None))
        updated, status = enrich(
            report, snapshot, selection, extract, translate=unchanged, verify=approved
        )
        self.assertEqual(updated, report)
        self.assertEqual(extract.call_count, 4)
        self.assertEqual(status["input_tokens"], 32_000)
        self.assertEqual(status["stop"], "budget")

    def test_skips_ineligible_and_stops_on_unknown_usage(self):
        report, snapshot, selection, _ = report_inputs(4)
        selection["decisions"][0]["answers"]["engineering_detail"] = "no"
        extract = Mock(
            side_effect=[
                ({"input_tokens": 200, "passes": 1}, {}, None),
                urllib.error.HTTPError("https://example.com", 429, "", None, None),
            ]
        )
        updated, status = enrich(
            report, snapshot, selection, extract, translate=unchanged, verify=approved
        )
        self.assertEqual(updated, report)
        self.assertEqual(status["attempts"], 2)
        self.assertEqual(status["input_tokens"], 200)
        self.assertEqual(status["stop"], "request_usage_unknown")

    def test_rules_fallback_uses_no_clairic(self):
        report, snapshot, selection, _ = report_inputs(1)
        selection["selection"] = "rules-fallback"
        extract = Mock()
        self.assertEqual(
            enrich(
                report,
                snapshot,
                selection,
                extract,
                translate=unchanged,
                verify=approved,
            )[0],
            report,
        )
        extract.assert_not_called()

    def test_duplicate_title_and_url_do_not_supply_other_rows_evidence(self):
        report, captured, selection, _ = report_inputs(1)
        article = selection["selected_articles"][0]
        captured["collection"].append(
            {
                "title": article["title"],
                "article_evidence": {
                    "text": "Wrong source",
                    "provenance": "article_body",
                },
            }
        )
        selection["decisions"].append({**selection["decisions"][0], "id": 1})
        extract = Mock(return_value=({"input_tokens": 20, "passes": 1}, {}, None))
        enrich(
            report, captured, selection, extract, translate=unchanged, verify=approved
        )
        extract.assert_called_once_with("Measured 32 GB per GPU.")

        extract.reset_mock()
        selection["decisions"][0]["answers"] = {"engineering_detail": "no"}
        enrich(
            report, captured, selection, extract, translate=unchanged, verify=approved
        )
        extract.assert_not_called()

    def test_translates_and_labels_korean_but_skips_invalid_renderings(self):
        report, snapshot, selection, receipt = report_inputs(4)
        source = "첫 응답 시간의 중앙값은 47초였습니다"
        extract = Mock(
            return_value=(
                {"input_tokens": 100, "passes": 1},
                {"detail": (source, source)},
                None,
            )
        )
        translate = Mock(
            side_effect=[
                "The median time to first response was 47 seconds.",
                "The median time to first response was 74 seconds.",
                source + ".",
                TimeoutError(),
            ]
        )
        updated, status = enrich(
            report,
            snapshot,
            selection,
            extract,
            translate=translate,
            verify=Mock(side_effect=[True, False]),
        )
        self.assertIn(
            "Source detail (Clairic, English rendering) · The median time", updated
        )
        self.assertNotIn(source, updated)
        self.assertNotIn("74 seconds", updated)
        self.assertEqual(updated.count("English rendering"), 1)
        self.assertEqual(status["english_attempts"], 4)
        self.assertEqual(status["english_skipped"], 3)
        self.assertTrue(updated.endswith(receipt))

    def test_checks_order_sign_units_and_renderable_unicode(self):
        pairs = [
            ("47 ms to 12 ms", "12 ms to 47 ms."),
            ("−2.5% difference", "+2.5% difference."),
            ("32 GB per GPU", "32 MB per GPU."),
            ("latency 12 µs", "latency 12 µs\ud800"),
            ("latency 12 µs", "latency 12 µs\x00"),
        ]
        for source, candidate in pairs:
            with self.subTest(candidate=repr(candidate)):
                self.assertIsNone(validated_english(source, candidate))
        self.assertEqual(
            validated_english("latency 12 µs", "Latency was 12 µs."),
            "Latency was 12 µs.",
        )

    def test_verifies_latin_script_and_keeps_good_detail_when_response_is_malformed(
        self,
    ):
        report, snapshot, selection, _ = report_inputs(4)
        sources = [
            "Latency was 12 µs.",
            "La latencia fue de 47 segundos.",
            "La durée était de 47 secondes.",
            "Used 32 GB",
        ]
        extract = Mock(
            side_effect=[
                ({"input_tokens": 100, "passes": 1}, {"detail": (source, source)}, None)
                for source in sources
            ]
        )
        translate = Mock(side_effect=[*sources[:3], "Used 32 GB\ud800"])
        verify = Mock(side_effect=[True, False, False])
        updated, status = enrich(
            report, snapshot, selection, extract, translate=translate, verify=verify
        )
        self.assertEqual(verify.call_count, 3)
        self.assertIn("Latency was 12 µs", updated)
        self.assertNotIn("47", updated)
        self.assertEqual(status["english_skipped"], 3)

    def test_skips_fragments_and_tangential_details(self):
        report, snapshot, selection, receipt = report_inputs(2)
        sources = [
            "1.37× the max throughput",
            "Octen returns results in approximately 0.17s.",
        ]
        extract = Mock(
            side_effect=[
                ({"input_tokens": 100, "passes": 1}, {"detail": (source, source)}, None)
                for source in sources
            ]
        )
        verify = Mock(return_value=False)
        updated, status = enrich(
            report, snapshot, selection, extract, translate=unchanged, verify=verify
        )
        verify.assert_called_once_with(
            "GPU (test) 1", sources[1], sources[1], sources[1]
        )
        self.assertEqual(status["english_skipped"], 2)
        self.assertEqual(updated, report)
        self.assertTrue(updated.endswith(receipt))

    def test_long_source_sentence_is_bounded_and_must_be_verbatim(self):
        sentence = (
            "On two GPUs, the study measured up to 1.37× peak prefill throughput "
            "with pipeline parallelism under the tested workload, compared with "
            "the baseline using expert and sequence parallelism."
        )
        state = f"Intro. {sentence} Next."
        body = {
            "success": True,
            "result": {
                "answers": {"detail": {"value": sentence}},
                "usage": {"input_tokens": 200, "passes": 1},
            },
        }
        self.assertEqual(read_response(body, state)[1], {})
        self.assertEqual(
            read_response(body, state, max_detail_chars=320)[1]["detail"][0], sentence
        )
        body["result"]["answers"]["detail"]["value"] = sentence.replace("1.37", "1.38")
        self.assertEqual(read_response(body, state, max_detail_chars=320)[1], {})

    def test_verifier_can_reject_a_missing_scope_qualifier(self):
        report, snapshot, selection, _ = report_inputs(1)
        excerpt = "Model A achieved 42 tokens/s on H100."
        context = f"In simulation only, {excerpt}"
        extract = Mock(
            return_value=(
                {"input_tokens": 100, "passes": 1},
                {"detail": (excerpt, context)},
                None,
            )
        )
        translate = Mock(return_value=excerpt)
        verify = Mock(return_value=False)
        updated, status = enrich(
            report, snapshot, selection, extract, translate=translate, verify=verify
        )
        translate.assert_called_once_with(excerpt, context)
        verify.assert_called_once_with("GPU (test) 0", excerpt, context, excerpt)
        self.assertEqual(updated, report)
        self.assertEqual(status["english_skipped"], 1)

    def test_quote_limit_survives_punctuation_changes(self):
        report, snapshot, selection, _ = report_inputs(1)
        excerpt = (
            "The team measured 42 tokens per second on the test system, using the"
            " same prompts as the earlier experiment on a separate cluster during a"
            " controlled dry run."
        )
        extract = Mock(
            return_value=(
                {"input_tokens": 100, "passes": 1},
                {"detail": (excerpt, excerpt)},
                None,
            )
        )
        translate = Mock(return_value=excerpt.replace(",", ""))
        verify = Mock()
        updated, status = enrich(
            report, snapshot, selection, extract, translate=translate, verify=verify
        )
        verify.assert_not_called()
        self.assertEqual(updated, report)
        self.assertEqual(status["english_skipped"], 1)
