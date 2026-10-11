"""Offline contract and HTTP-boundary regressions; no model calls."""

import copy
import hashlib
import http.client
import io
import json
import unittest
import urllib.error
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from scripts.cloudflare_assessment import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MODEL,
    CloudflareAssessmentProvider,
    NoRedirect,
    normalize_response,
)
from scripts.model_assessment import (
    QUESTION_SHA256,
    QUESTION_VERSION,
    QUESTIONS,
    AssessmentAnswers,
    AssessmentError,
    AssessmentInput,
    question_schema,
)

ACCOUNT = "a" * 32
TOKEN = "test-token-do-not-log"
ARTICLE = AssessmentInput(
    "A model release", "Synthetic article evidence.", "public_preview", "partial", False
)


def response_body():
    return {
        "success": True,
        "result": {
            "model": "clef-flash",
            "answers": {
                field: {
                    "type": "choice",
                    "choice": "o0",
                    "confidence": 1.0,
                    "probabilities": {
                        f"o{i}": 1.0 if i == 0 else 0.0 for i in range(len(options))
                    },
                }
                for field, _, options in QUESTIONS
            },
            "usage": {"input_tokens": 500, "output_tokens": 0},
        },
    }


class ContractTests(unittest.TestCase):
    def test_capture_preserves_exact_text_and_limits(self):
        capture = {
            "text": "three word excerpt",
            "provenance": "feed_excerpt",
            "completeness": "unknown",
            "truncated": False,
            "text_sha256": hashlib.sha256(b"three word excerpt").hexdigest(),
            "retrieval": {"reason": "unavailable"},
        }
        article = AssessmentInput.from_capture("title", capture)
        self.assertEqual(article.text, capture["text"])
        self.assertEqual(article.provenance, "feed_excerpt")
        self.assertEqual(article.completeness, "unknown")
        self.assertFalse(article.truncated)
        capture["text"] = "changed"
        with self.assertRaisesRegex(AssessmentError, "evidence_hash_mismatch"):
            AssessmentInput.from_capture("title", capture)

    def test_invalid_capture_fails_before_provider(self):
        for capture in (None, {}, {"text": "body"}):
            with self.subTest(capture=capture), self.assertRaises(AssessmentError):
                AssessmentInput.from_capture("title", capture)

    def test_invalid_input_bounds_and_types(self):
        cases = (
            {"title": "x" * 1001},
            {"text": "x" * 12_001},
            {"text": " "},
            {"text": None},
            {"text": "\ud800"},
            {"provenance": []},
            {"provenance": "unavailable"},
            {"completeness": "complete"},
            {"completeness": {}},
            {"truncated": 0},
        )
        for changes in cases:
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(AssessmentError, "invalid_input"),
            ):
                replace(ARTICLE, **changes)

    def test_input_identity_includes_title_and_provenance(self):
        for changes in (
            {"title": "other"},
            {"truncated": True},
            {"provenance": "feed_excerpt"},
        ):
            other = replace(ARTICLE, **changes)
            self.assertEqual(other.text_sha256, ARTICLE.text_sha256)
            self.assertNotEqual(other.input_sha256, ARTICLE.input_sha256)

    def test_schema_fresh_and_versioned(self):
        schema = question_schema()
        self.assertIn("AI-related", schema["engineering_detail"]["instructions"])
        self.assertEqual(
            schema["ai_subject"]["criteria"]["o2"], "insufficient evidence"
        )
        schema["ai_subject"]["criteria"]["o0"] = "mutated"
        self.assertEqual(question_schema()["ai_subject"]["criteria"]["o0"], "yes")
        self.assertEqual(len(QUESTION_SHA256), 64)

    def test_common_answers_reject_extra_missing_and_invalid_values(self):
        valid = {
            "ai_subject": "yes",
            "engineering_detail": "no",
            "article_type": "announcement or event",
        }
        self.assertEqual(AssessmentAnswers.from_mapping(valid).ai_subject, "yes")
        for invalid in (
            None,
            {},
            {**valid, "extra": 1},
            {**valid, "ai_subject": True},
            {**valid, "article_type": "unknown"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(AssessmentError):
                AssessmentAnswers.from_mapping(invalid)


class ResponseTests(unittest.TestCase):
    def test_insufficient_evidence_is_valid_not_an_error(self):
        body = response_body()
        answer = body["result"]["answers"]["ai_subject"]
        answer.update(choice="o2", probabilities={"o0": 0.0, "o1": 0.0, "o2": 1.0})
        normalized, usage = normalize_response(body)
        self.assertEqual(normalized.ai_subject, "insufficient evidence")
        self.assertEqual(usage, [500, 0])

    def test_invalid_envelope_or_model(self):
        for body in (
            None,
            [],
            {},
            {"success": False},
            {"success": True, "result": None},
            {"success": True, "result": {"model": "clef"}},
        ):
            with self.subTest(body=body), self.assertRaises(AssessmentError):
                normalize_response(body)

    def test_missing_or_extra_questions(self):
        for extra in (False, True):
            body = response_body()
            if extra:
                body["result"]["answers"]["extra"] = {}
            else:
                del body["result"]["answers"]["ai_subject"]
            with self.assertRaisesRegex(AssessmentError, "invalid_answers"):
                normalize_response(body)

    def test_invalid_choices_and_distributions(self):
        variants = (
            None,
            {"type": "noul"},
            {"choice": "unexpected"},
            {"choice": []},
            {"choice": "o1"},  # Does not match the maximum probability.
            {"probabilities": {"o0": 1}},
            {"probabilities": {"o0": True, "o1": 0, "o2": 0}},
            {"probabilities": {"o0": float("nan"), "o1": 0, "o2": 0}},
            {"probabilities": {"o0": 10**400, "o1": 0, "o2": 0}},
            {"probabilities": {"o0": 0.5, "o1": 0, "o2": 0}},
            {"confidence": float("inf")},
            {"confidence": True},
        )
        for changes in variants:
            body = response_body()
            if changes is None:
                body["result"]["answers"]["ai_subject"] = None
            else:
                body["result"]["answers"]["ai_subject"].update(changes)
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(AssessmentError, "invalid_answers"),
            ):
                normalize_response(body)

    def test_usage_missing_is_unknown_not_zero(self):
        body = response_body()
        del body["result"]["usage"]
        self.assertEqual(normalize_response(body)[1], [None, None])

    def test_invalid_usage(self):
        for invalid in (
            [],
            {"input_tokens": -1},
            {"input_tokens": True},
            {"output_tokens": 0.5},
        ):
            body = response_body()
            body["result"]["usage"] = invalid
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(AssessmentError, "invalid_usage"),
            ):
                normalize_response(body)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = CloudflareAssessmentProvider(ACCOUNT, TOKEN)
        self.opener = MagicMock()
        self.client._opener = self.opener
        self.response = self.opener.open.return_value.__enter__.return_value
        self.response.status = 200
        self.response.headers = {}
        self.response.read.return_value = json.dumps(response_body()).encode()

    def test_exact_endpoint_payload_and_safe_record(self):
        result = self.client.assess(ARTICLE)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(
            request.full_url,
            f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "clef-flash")
        self.assertEqual(payload["state"]["text"], ARTICLE.text)
        self.assertEqual(payload["questions"], question_schema())
        self.assertLessEqual(len(request.data), MAX_REQUEST_BYTES)
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 30)
        record = result.to_record()
        self.assertEqual(record["answers"]["ai_subject"], "yes")
        self.assertEqual(record["model"], MODEL)
        self.assertEqual(record["question_version"], QUESTION_VERSION)
        self.assertEqual(record["question_sha256"], QUESTION_SHA256)
        self.assertEqual(record["input_sha256"], ARTICLE.input_sha256)
        self.assertEqual(record["input_tokens"], 500)
        self.assertEqual(record["provenance"], "public_preview")
        start = datetime.fromisoformat(record["assessed_at"])
        end = datetime.fromisoformat(record["expires_at"])
        self.assertEqual(start.utcoffset(), timedelta(0))
        self.assertEqual(end - start, timedelta(days=1))
        rendered = json.dumps(record)
        for private in (TOKEN, ARTICLE.text, "probabilities", "confidence"):
            self.assertNotIn(private, rendered)

    def test_credentials_not_read_implicitly_or_printed(self):
        for account, token in (
            ("", TOKEN),
            (ACCOUNT, ""),
            ("../other", TOKEN),
            (ACCOUNT, "secret\nheader"),
        ):
            with self.assertRaisesRegex(
                AssessmentError, "missing_or_invalid_credentials"
            ):
                CloudflareAssessmentProvider(account, token)
        with patch.dict(
            "os.environ",
            {"CLOUDFLARE_ACCOUNT_ID": ACCOUNT, "CLOUDFLARE_API_TOKEN": TOKEN},
        ):
            provider = CloudflareAssessmentProvider.from_environment()
        self.assertNotIn(TOKEN, repr(provider))

    def test_configuration_bounds(self):
        for changes in (
            {"timeout": float("inf")},
            {"timeout": 10**400},
            {"timeout": True},
            {"request_limit": 0},
            {"input_byte_limit": -1},
            {"cache_ttl_seconds": 86_401},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(AssessmentError, "invalid_configuration"),
            ):
                CloudflareAssessmentProvider(ACCOUNT, TOKEN, **changes)

    def test_failed_attempt_consumes_request_budget(self):
        self.client.request_limit = 1
        self.opener.open.side_effect = TimeoutError(TOKEN)
        with self.assertRaisesRegex(AssessmentError, "network_error"):
            self.client.assess(ARTICLE)
        with self.assertRaisesRegex(AssessmentError, "request_budget_exhausted"):
            self.client.assess(ARTICLE)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_byte_budget_exhaustion_makes_no_request(self):
        self.client.input_byte_limit = 1
        with self.assertRaisesRegex(AssessmentError, "request_budget_exhausted"):
            self.client.assess(ARTICLE)
        self.opener.open.assert_not_called()
        self.assertEqual(self.client.requests_attempted, 0)

    def test_multibyte_input_never_silently_truncates(self):
        article = replace(ARTICLE, text="😀" * 12_000)
        with self.assertRaisesRegex(AssessmentError, "request_too_large"):
            self.client.assess(article)
        self.opener.open.assert_not_called()

    def test_network_errors_are_sanitized(self):
        for failure in (
            TimeoutError(TOKEN),
            urllib.error.URLError(TOKEN),
            http.client.IncompleteRead(TOKEN.encode()),
            OSError(TOKEN),
        ):
            self.opener.open.side_effect = failure
            with (
                self.subTest(failure=type(failure)),
                self.assertRaises(AssessmentError) as raised,
            ):
                self.client.assess(ARTICLE)
            self.assertEqual(str(raised.exception), "network_error")
            self.assertIsNone(raised.exception.__cause__)

    def test_http_errors_never_expose_provider_body(self):
        for status in (302, 401, 403, 429, 500):
            self.opener.open.side_effect = urllib.error.HTTPError(
                "url", status, TOKEN, {}, io.BytesIO(TOKEN.encode())
            )
            with (
                self.subTest(status=status),
                self.assertRaises(AssessmentError) as raised,
            ):
                self.client.assess(ARTICLE)
            self.assertEqual(raised.exception.code, "http_error")
            self.assertEqual(raised.exception.http_status, status)
            self.assertNotIn(TOKEN, str(raised.exception))

    def test_redirect_handler_refuses_all_destinations(self):
        self.assertIsNone(
            NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://other.invalid"
            )
        )

    def test_read_bound_and_response_encoding(self):
        self.response.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(AssessmentError, "response_too_large"):
            self.client.assess(ARTICLE)
        self.response.read.assert_called_with(MAX_RESPONSE_BYTES + 1)
        self.response.headers = {"Content-Encoding": "gzip"}
        with self.assertRaisesRegex(AssessmentError, "unsupported_response_encoding"):
            self.client.assess(ARTICLE)

    def test_non_200_response_without_http_exception(self):
        self.response.status = 204
        with self.assertRaisesRegex(AssessmentError, "http_error"):
            self.client.assess(ARTICLE)

    def test_malformed_duplicate_or_non_json_body(self):
        for body in (b"not json", b"\xff", b'{"success":true,"success":false}', b"[]"):
            self.response.read.return_value = body
            with self.subTest(body=body), self.assertRaises(AssessmentError):
                self.client.assess(ARTICLE)

    def test_input_object_required(self):
        with self.assertRaisesRegex(AssessmentError, "invalid_input"):
            self.client.assess({"text": "body"})
        self.opener.open.assert_not_called()

    def test_api_failure_is_not_insufficient_evidence(self):
        body = copy.deepcopy(response_body())
        body["success"] = False
        body["errors"] = [{"message": TOKEN}]
        self.response.read.return_value = json.dumps(body).encode()
        with self.assertRaisesRegex(AssessmentError, "provider_failure"):
            self.client.assess(ARTICLE)


if __name__ == "__main__":
    unittest.main()
