"""Explicit, bounded Workers AI Clef-flash adapter using the standard library."""

import http.client
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from scripts.model_assessment import (
    QUESTION_SHA256,
    QUESTION_VERSION,
    QUESTIONS,
    AssessmentAnswers,
    AssessmentError,
    AssessmentInput,
    AssessmentResult,
    question_schema,
)

MODEL = "@cf/cloudflare/clef-flash"
MAX_RESPONSE_BYTES = 64_000
MAX_REQUEST_BYTES = 24_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the account's bearer token to a redirect destination.
        return None


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssessmentError("invalid_response")
        result[key] = value
    return result


def probability(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def normalize_response(body):
    """Validate provider-specific answers before constructing the common contract."""
    if not isinstance(body, dict) or body.get("success") is not True:
        raise AssessmentError("provider_failure")
    result = body.get("result")
    if not isinstance(result, dict) or result.get("model") != "clef-flash":
        raise AssessmentError("invalid_response")
    answers = result.get("answers")
    if not isinstance(answers, dict) or set(answers) != {
        field for field, _, _ in QUESTIONS
    }:
        raise AssessmentError("invalid_answers")
    normalized = {}
    for field, _, options in QUESTIONS:
        answer = answers[field]
        criteria = {f"o{i}": option for i, option in enumerate(options)}
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise AssessmentError("invalid_answers")
        choice = answer.get("choice")
        probs = answer.get("probabilities")
        if (
            not isinstance(choice, str)
            or choice not in criteria
            or not isinstance(probs, dict)
            or set(probs) != set(criteria)
            or not all(probability(p) for p in probs.values())
            or abs(sum(probs.values()) - 1) > 0.01
            or not probability(answer.get("confidence"))
        ):
            raise AssessmentError("invalid_answers")
        if probs[choice] < max(probs.values()):
            raise AssessmentError("invalid_answers")
        normalized[field] = criteria[choice]
    usage = result.get("usage", {})
    if not isinstance(usage, dict):
        raise AssessmentError("invalid_usage")
    counts = []
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise AssessmentError("invalid_usage")
        counts.append(value)
    return AssessmentAnswers.from_mapping(normalized), counts


class CloudflareAssessmentProvider:
    """Sequential-use client; failed attempts consume budget and are never retried."""

    def __init__(
        self,
        account_id,
        api_token,
        *,
        timeout=30,
        request_limit=20,
        input_byte_limit=300_000,
        cache_ttl_seconds=86_400,
    ):
        if (
            not isinstance(account_id, str)
            or not re.fullmatch(r"[a-fA-F0-9]{32}", account_id)
            or not isinstance(api_token, str)
            or not re.fullmatch(r"[\x21-\x7e]+", api_token)
        ):
            raise AssessmentError("missing_or_invalid_credentials")
        if (
            type(timeout) not in (int, float)
            or not 0 < timeout <= 120
            or not math.isfinite(timeout)
            or type(request_limit) is not int
            or request_limit < 1
            or type(input_byte_limit) is not int
            or input_byte_limit < 1
            or type(cache_ttl_seconds) is not int
            or not 0 < cache_ttl_seconds <= 86_400
        ):
            raise AssessmentError("invalid_configuration")
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
        )
        self._token = api_token
        self._opener = urllib.request.build_opener(NoRedirect())
        self.timeout = timeout
        self.request_limit = request_limit
        self.input_byte_limit = input_byte_limit
        self.cache_ttl_seconds = cache_ttl_seconds
        self.requests_attempted = 0
        self.input_bytes_attempted = 0

    @classmethod
    def from_environment(cls, **kwargs):
        return cls(
            os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
            os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            **kwargs,
        )

    def assess(self, article):
        if not isinstance(article, AssessmentInput):
            raise AssessmentError("invalid_input")
        payload = json.dumps(
            {
                "model": "clef-flash",
                "state": asdict(article),
                "questions": question_schema(),
            },
            ensure_ascii=False,
        ).encode()
        if len(payload) > MAX_REQUEST_BYTES:
            raise AssessmentError("request_too_large")
        if (
            self.requests_attempted >= self.request_limit
            or self.input_bytes_attempted + len(payload) > self.input_byte_limit
        ):
            raise AssessmentError("request_budget_exhausted")
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
            method="POST",
        )
        self.requests_attempted += 1
        self.input_bytes_attempted += len(payload)
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise AssessmentError("http_error", http_status=response.status)
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise AssessmentError("unsupported_response_encoding")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise AssessmentError("http_error", http_status=status) from None
        except (
            TimeoutError,
            urllib.error.URLError,
            OSError,
            http.client.HTTPException,
        ):
            raise AssessmentError("network_error") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AssessmentError("response_too_large")
        try:
            body = json.loads(raw, object_pairs_hook=json_object)
        except (ValueError, UnicodeError, RecursionError):
            raise AssessmentError("invalid_response") from None
        answers, (input_tokens, output_tokens) = normalize_response(body)
        assessed_at = datetime.now(UTC)
        return AssessmentResult(
            answers=answers,
            provider="cloudflare",
            model=MODEL,
            question_version=QUESTION_VERSION,
            question_sha256=QUESTION_SHA256,
            input_sha256=article.input_sha256,
            text_sha256=article.text_sha256,
            provenance=article.provenance,
            completeness=article.completeness,
            truncated=article.truncated,
            assessed_at=assessed_at.isoformat(),
            expires_at=(
                assessed_at + timedelta(seconds=self.cache_ttl_seconds)
            ).isoformat(),
            latency_seconds=round(time.monotonic() - started, 6),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
