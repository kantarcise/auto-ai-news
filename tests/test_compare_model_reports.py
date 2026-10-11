"""Frozen paired-report comparisons with synthetic text and no live requests."""

import copy
import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import compare_model_reports as comparison
from scripts import generate_report as report
from scripts.article_evidence import evidence
from scripts.cloudflare_assessment import MODEL
from scripts.model_assessment import (
    QUESTION_SHA256,
    QUESTION_VERSION,
    AssessmentAnswers,
    AssessmentError,
    AssessmentInput,
    AssessmentResult,
)

NOW = datetime.now(UTC)
ANSWERS = AssessmentAnswers("yes", "yes", "technical explanation")
ANNOUNCEMENT = AssessmentAnswers("yes", "no", "announcement or event")


def row(
    index,
    *,
    title=None,
    admit=True,
    score=3.0,
    source=None,
    publisher=None,
    category="other",
    provenance="article_body",
    completeness="unknown",
    truncated=False,
):
    return {
        "title": title or f"AI topic {index}",
        "url": f"https://example.com/{index}",
        "source": source or f"Source {index}",
        "publisher": publisher or f"Publisher {index}",
        "category": category,
        "published": (NOW - timedelta(hours=index + 1)).isoformat(),
        "rejection_reason": "" if admit else "title relevance filter",
        "article_evidence": evidence(
            "Synthetic AI measurements.",
            provenance,
            completeness=completeness,
            truncated=truncated,
        ),
        "comparison_candidate": {
            "canonical_url": f"https://example.com/{index}",
            "source_priority": 3,
            "coverage": "mixed",
            "baseline_admit": admit,
            "event_listing": False,
            "rank_score": score,
            "stars": max(1, min(5, math.ceil(score))),
            "word_count": 0,
            "read_minutes": None,
            "content_provenance": "missing",
        },
    }


def snapshot(rows, *, inaccessible=(), publisher_limit=4, report_limit=30):
    value = {
        "captured_at": NOW.isoformat(),
        "lookback_hours": 72,
        "model_comparison": {
            "schema_version": 1,
            "published_urls": {},
            "collection_diagnostics": [],
            "selection_parameters": {
                "report_limit": report_limit,
                "publisher_limit": publisher_limit,
            },
        },
        "collection": copy.deepcopy(rows),
        "diagnostics": [],
        "link_outcomes": {
            entry["url"]: {
                "accessible": entry["url"] not in inaccessible,
                "reason": "HTTP 403." if entry["url"] in inaccessible else "",
            }
            for entry in rows
        },
        "policies": {"frontier": {"selected": []}},
    }
    candidates = comparison.snapshot_candidates(value)
    items = [
        item
        for _, entry, item, reason in candidates
        if not reason and entry["comparison_candidate"]["baseline_admit"]
    ]
    groups = report.group_stories(report.dedupe_items(items))
    selected, _ = report.filter_accessible_items(
        groups,
        report_limit,
        publisher_limit,
        access_checker=lambda url: (
            value["link_outcomes"][url]["accessible"],
            value["link_outcomes"][url]["reason"],
        ),
    )
    value["policies"]["frontier"]["selected"] = [
        report.evaluation_metadata(item) for item in selected
    ]
    return value


class Provider:
    def __init__(self, answers=None, *, fail_after=None):
        self.answers = answers or {}
        self.calls = []
        self.fail_after = fail_after

    def assess(self, article):
        self.calls.append(article)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise AssessmentError("network_error")
        return AssessmentResult(
            answers=self.answers.get(article.title, ANSWERS),
            provider="cloudflare",
            model=MODEL,
            question_version=QUESTION_VERSION,
            question_sha256=QUESTION_SHA256,
            input_sha256=article.input_sha256,
            text_sha256=article.text_sha256,
            provenance=article.provenance,
            completeness=article.completeness,
            truncated=article.truncated,
            assessed_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=12)).isoformat(),
            latency_seconds=0.1,
            input_tokens=20,
            output_tokens=0,
        )


class PolicyTests(unittest.TestCase):
    def test_admission_table(self):
        for baseline in (False, True):
            for provenance, completeness, truncated, expected in (
                ("article_body", "unknown", False, False),
                ("feed_excerpt", "unknown", False, baseline),
                ("feed_summary", "unknown", False, baseline),
                ("title_only", "unknown", False, baseline),
                ("public_preview", "partial", False, baseline),
                ("rss_content", "partial", False, baseline),
                ("article_body", "unknown", True, baseline),
            ):
                article = AssessmentInput(
                    "title", "three word excerpt", provenance, completeness, truncated
                )
                with self.subTest(
                    baseline=baseline, provenance=provenance, truncated=truncated
                ):
                    decision, _ = comparison.admission(
                        baseline,
                        article,
                        AssessmentAnswers("no", "no", "opinion or discussion"),
                    )
                    self.assertEqual(decision, expected)
                    self.assertEqual(
                        comparison.admission(baseline, article, ANSWERS)[0], True
                    )
                    self.assertEqual(
                        comparison.admission(
                            baseline,
                            article,
                            AssessmentAnswers(
                                "insufficient evidence",
                                "no",
                                "mixed or insufficient evidence",
                            ),
                        )[0],
                        baseline,
                    )

    def test_announcement_promotion_mixed_and_opinion_no_preference(self):
        for kind in (
            "announcement or event",
            "mainly promotion",
            "mixed or insufficient evidence",
            "opinion or discussion",
        ):
            self.assertFalse(
                comparison.technical(AssessmentAnswers("yes", "yes", kind))
            )
        self.assertFalse(
            comparison.technical(
                AssessmentAnswers(
                    "yes", "insufficient evidence", "technical explanation"
                )
            )
        )
        self.assertTrue(comparison.technical(ANSWERS))

    def test_recovery_removal_and_insufficient_evidence(self):
        rows = [row(0), row(1, admit=False), row(2)]
        provider = Provider(
            {
                rows[0]["title"]: AssessmentAnswers(
                    "no", "no", "opinion or discussion"
                ),
                rows[2]["title"]: AssessmentAnswers(
                    "insufficient evidence",
                    "insufficient evidence",
                    "mixed or insufficient evidence",
                ),
            }
        )
        result = comparison.compare(
            snapshot(rows), mode="shadow", provider=provider, assessment_now=NOW
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(
            [entry["url"] for entry in result["candidate_selected"]],
            [rows[1]["url"], rows[2]["url"]],
        )
        self.assertEqual(
            [entry["change"] for entry in result["differences"]],
            ["removed", "unchanged", "added"],
        )
        self.assertEqual(len(provider.calls), 3)

    def test_engineering_changes_equal_scores_only(self):
        rows = [row(0, score=4), row(1), row(2)]
        provider = Provider(
            {rows[0]["title"]: ANNOUNCEMENT, rows[1]["title"]: ANNOUNCEMENT}
        )
        result = comparison.compare(
            snapshot(rows), mode="shadow", provider=provider, assessment_now=NOW
        )
        self.assertEqual(
            [entry["url"] for entry in result["candidate_selected"]],
            [rows[0]["url"], rows[2]["url"], rows[1]["url"]],
        )
        self.assertEqual(
            [entry["score"] for entry in result["ordering"]["candidate"]], [4, 3, 3]
        )

    def test_mixed_group_cannot_lend_preference_on_link_fallback(self):
        title = "An AI release with six detailed title tokens"
        rows = [
            row(0, title=title, category="frontier_lab"),
            row(1, title=title),
            row(2),
        ]
        for technical_primary in (True, False):
            # Same headline can have distinct feed text and different model answers.
            rows[1]["article_evidence"] = evidence(
                "Different AI announcement evidence.", "article_body"
            )
            provider = Provider()

            def assess(article, technical_primary=technical_primary):
                result = Provider().assess(article)
                answer = (
                    ANSWERS
                    if (article.text == rows[0]["article_evidence"]["text"])
                    == technical_primary
                    else ANNOUNCEMENT
                )

                return replace(result, answers=answer)

            provider.assess = assess
            result = comparison.compare(
                snapshot(rows, inaccessible=[rows[0]["url"]]),
                mode="shadow",
                provider=provider,
                assessment_now=NOW,
            )
            group = next(
                entry
                for entry in result["ordering"]["candidate"]
                if len(entry["member_urls"]) == 2
            )
            self.assertFalse(group["technical_preference"])
            self.assertIn(
                rows[1]["url"], [entry["url"] for entry in result["candidate_selected"]]
            )

    def test_all_technical_group_keeps_preference_on_fallback(self):
        title = "An AI release with six detailed title tokens"
        rows = [
            row(0),
            row(1, title=title, category="frontier_lab"),
            row(2, title=title),
        ]
        result = comparison.compare(
            snapshot(rows, inaccessible=[rows[1]["url"]]),
            mode="shadow",
            provider=Provider({rows[0]["title"]: ANNOUNCEMENT}),
            assessment_now=NOW,
        )
        self.assertEqual(result["candidate_selected"][0]["url"], rows[2]["url"])
        self.assertTrue(result["ordering"]["candidate"][0]["technical_preference"])

    def test_publisher_and_report_limits_identical(self):
        rows = [row(index, publisher="Same") for index in range(4)] + [row(4)]
        value = snapshot(rows, publisher_limit=1, report_limit=2)
        result = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        self.assertEqual(
            [entry["url"] for entry in result["candidate_selected"]],
            [rows[0]["url"], rows[4]["url"]],
        )

    def test_cap_replacement_uses_frozen_group_preference(self):
        title = "An AI release with six detailed title tokens"
        rows = [
            row(0, publisher="Capped", score=4),
            row(1, title=title, category="frontier_lab"),
            row(2, title=title, publisher="Capped"),
            row(3, title=title),
        ]
        rows[2]["article_evidence"] = evidence(
            "Alternate AI announcement.", "article_body"
        )
        for mixed in (False, True):
            provider = Provider()
            original = provider.assess

            def assess(article, mixed=mixed, original=original):
                result = original(article)
                return replace(
                    result,
                    answers=ANNOUNCEMENT
                    if mixed and article.text.startswith("Alternate")
                    else ANSWERS,
                )

            provider.assess = assess
            result = comparison.compare(
                snapshot(rows, publisher_limit=1, inaccessible=[rows[1]["url"]]),
                mode="shadow",
                provider=provider,
                assessment_now=NOW,
            )
            self.assertEqual(
                result["ordering"]["candidate"][1]["technical_preference"], not mixed
            )
            self.assertEqual(
                [entry["url"] for entry in result["candidate_selected"]],
                [rows[0]["url"], rows[3]["url"]],
            )


class RunnerTests(unittest.TestCase):
    def test_rules_mode_offline_and_input_unchanged(self):
        value = snapshot([row(0), row(1, admit=False)])
        before = copy.deepcopy(value)
        with patch.object(
            report, "check_url_accessible", side_effect=AssertionError("network")
        ):
            result = comparison.compare(value)
        self.assertEqual(result["status"], "not_requested")
        self.assertEqual(value, before)
        self.assertIn("original title/summary", result["baseline_report"])

    def test_missing_credentials_and_partial_failure_fall_back_whole_report(self):
        value = snapshot([row(0), row(1, admit=False), row(2)])
        for provider in (None, Provider(fail_after=1)):
            result = comparison.compare(
                value, mode="shadow", provider=provider, assessment_now=NOW
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["candidate_selected"], result["baseline_selected"])
            self.assertEqual(len(result["decisions"]), 3)
            self.assertTrue(all(not entry["applied"] for entry in result["decisions"]))
            self.assertIn(
                "entire candidate report falls back", result["candidate_report"]
            )

    def test_invalid_capture_hash_is_report_failure(self):
        value = snapshot([row(0)])
        value["collection"][0]["article_evidence"]["text"] = "changed"
        result = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        self.assertEqual(result["failure"]["code"], "evidence_hash_mismatch")

    def test_missing_candidate_link_is_unknown_not_inaccessible(self):
        rows = [row(0), row(1, admit=False)]
        value = snapshot(rows)
        del value["link_outcomes"][rows[1]["url"]]
        result = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        self.assertEqual(result["failure"]["code"], "missing_frozen_link")
        self.assertNotIn(rows[1]["url"], result["link_outcomes"])

    def test_explicit_missing_link_fetch_is_frozen_once(self):
        rows = [row(0), row(1, admit=False)]
        value = snapshot(rows)
        del value["link_outcomes"][rows[1]["url"]]
        with patch.object(
            report, "check_url_accessible", return_value=(True, "")
        ) as checker:
            result = comparison.compare(
                value,
                mode="shadow",
                provider=Provider(),
                assessment_now=NOW,
                fetch_missing_links=True,
            )
        self.assertEqual(result["status"], "complete")
        checker.assert_called_once_with(rows[1]["url"])
        self.assertEqual(result["new_link_requests"], 1)
        self.assertIn("checked_at", result["link_outcomes"][rows[1]["url"]])

    def test_supplemental_links_replay_offline_and_reject_conflicts(self):
        rows = [row(0), row(1, admit=False)]
        value = snapshot(rows)
        del value["link_outcomes"][rows[1]["url"]]
        supplemental = {rows[1]["url"]: {"accessible": True, "reason": ""}}
        with patch.object(
            report, "check_url_accessible", side_effect=AssertionError("network")
        ):
            result = comparison.compare(
                value,
                mode="shadow",
                provider=Provider(),
                assessment_now=NOW,
                frozen_links=supplemental,
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["new_link_requests"], 0)
        supplemental[rows[0]["url"]] = {"accessible": False, "reason": "changed"}
        with self.assertRaisesRegex(ValueError, "conflicts"):
            comparison.compare(value, frozen_links=supplemental)

    def test_missing_link_budget_and_errors_fall_back(self):
        rows = [row(0), row(1, admit=False), row(2, admit=False)]
        value = snapshot(rows)
        for entry in rows[1:]:
            del value["link_outcomes"][entry["url"]]
        with patch.object(report, "check_url_accessible", return_value=(True, "")):
            result = comparison.compare(
                value,
                mode="shadow",
                provider=Provider(),
                assessment_now=NOW,
                fetch_missing_links=True,
                link_request_limit=1,
            )
        self.assertEqual(result["failure"]["code"], "link_budget_exhausted")
        with patch.object(
            report, "check_url_accessible", side_effect=TimeoutError("raw error")
        ):
            result = comparison.compare(
                value,
                mode="shadow",
                provider=Provider(),
                assessment_now=NOW,
                fetch_missing_links=True,
            )
        self.assertEqual(result["failure"]["code"], "link_check_failed")

    def test_cache_reuses_answers_without_provider(self):
        value = snapshot([row(0)])
        first = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        second = comparison.compare(
            value, mode="shadow", cache=first["cache"], assessment_now=NOW
        )
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["usage"]["new_assessment_attempts"], 0)
        self.assertTrue(second["decisions"][0]["cache_hit"])

    def test_cache_expiring_during_slow_run_is_not_reused(self):
        rows = [row(0), row(1)]
        value = snapshot(rows)
        article = AssessmentInput.from_capture(
            rows[1]["title"], rows[1]["article_evidence"]
        )
        record = Provider().assess(article).to_record()
        record["expires_at"] = (NOW + timedelta(seconds=60)).isoformat()
        provider = Provider()
        original = provider.assess
        elapsed = [0]

        def slow_assess(article):
            elapsed[0] = 120
            return original(article)

        provider.assess = slow_assess
        with patch.object(comparison.time, "monotonic", side_effect=lambda: elapsed[0]):
            result = comparison.compare(
                value,
                mode="shadow",
                provider=provider,
                cache={comparison.cache_key(article): record},
                assessment_now=NOW,
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(provider.calls), 2)
        self.assertFalse(result["decisions"][1]["cache_hit"])

    def test_expired_in_run_duplicate_is_reassessed_and_usage_counted(self):
        rows = [row(0, title="Repeated title"), row(1), row(2, title="Repeated title")]
        provider = Provider()
        original = provider.assess
        elapsed = [0]

        def assess(article):
            result = original(article)
            if len(provider.calls) == 1:
                return replace(
                    result, expires_at=(NOW + timedelta(seconds=60)).isoformat()
                )
            elapsed[0] = 120
            if len(provider.calls) == 3:
                return replace(
                    result,
                    answers=AssessmentAnswers(
                        "no", "no", "mixed or insufficient evidence"
                    ),
                )
            return result

        provider.assess = assess
        with patch.object(comparison.time, "monotonic", side_effect=lambda: elapsed[0]):
            result = comparison.compare(
                snapshot(rows), mode="shadow", provider=provider, assessment_now=NOW
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(result["usage"]["new_assessment_attempts"], 3)
        self.assertEqual(result["usage"]["reported_input_tokens"], 60)
        first, refreshed = result["decisions"][0], result["decisions"][2]
        self.assertNotEqual(first["assessment_key"], refreshed["assessment_key"])
        self.assertTrue(first["candidate_admit"])
        self.assertFalse(refreshed["candidate_admit"])
        self.assertEqual(
            result["assessments"][first["assessment_key"]]["answers"]["ai_subject"],
            "yes",
        )
        self.assertEqual(
            result["assessments"][refreshed["assessment_key"]]["answers"]["ai_subject"],
            "no",
        )

    def test_cache_expiration_version_identity_and_schema(self):
        value = snapshot([row(0)])
        first = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        key = next(iter(first["cache"]))
        for updates in (
            {"expires_at": NOW.isoformat()},
            {"assessed_at": (NOW + timedelta(hours=1)).isoformat()},
            {"question_version": "old"},
            {"question_sha256": "bad"},
            {"input_sha256": "bad"},
            {"model": "other"},
            {"truncated": True},
            {"answers": {}},
            {"extra": "untrusted"},
            {"input_tokens": True},
        ):
            cache = copy.deepcopy(first["cache"])
            cache[key].update(updates)
            result = comparison.compare(
                value, mode="shadow", cache=cache, assessment_now=NOW
            )
            with self.subTest(updates=updates):
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["cache"], {})

    def test_identical_input_assessed_once_per_run(self):
        rows = [row(0, title="Identical title"), row(1, title="Identical title")]
        provider = Provider()
        result = comparison.compare(
            snapshot(rows), mode="shadow", provider=provider, assessment_now=NOW
        )
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result["usage"]["new_assessment_attempts"], 1)

    def test_title_arm_is_separate_and_keeps_baseline_fixed(self):
        value = snapshot([row(0), row(1, admit=False)])
        content = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        provider = Provider()
        title = comparison.compare(
            value,
            mode="shadow",
            provider=provider,
            cache=content["cache"],
            assessment_now=NOW,
            evidence_arm="title",
        )
        self.assertTrue(
            all(
                article.provenance == "title_only" and article.text == article.title
                for article in provider.calls
            )
        )
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(title["baseline_selected"], content["baseline_selected"])

    def test_shared_event_exclusion_skips_model(self):
        rows = [row(0), row(1, admit=False)]
        rows[1]["comparison_candidate"]["event_listing"] = True
        provider = Provider()
        result = comparison.compare(
            snapshot(rows), mode="shadow", provider=provider, assessment_now=NOW
        )
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result["decisions"][1]["reason"], "shared_exclusion")

    def test_hard_gates_preserve_frozen_history_and_skip_model(self):
        for change, expected in (
            ("old", "older than coverage window"),
            ("future", "future publication date"),
            ("history", "previously published"),
            ("quiet", "quiet-day title policy"),
        ):
            rows = [row(0), row(1, admit=False)]
            if change == "old":
                rows[1]["published"] = (NOW - timedelta(days=4)).isoformat()
            elif change == "future":
                rows[1]["published"] = (NOW + timedelta(hours=1)).isoformat()
            elif change == "quiet":
                rows[1].update(title="Not much happened today", source="Latent Space")
            value = snapshot(rows)
            if change == "history":
                value["model_comparison"]["published_urls"][rows[1]["url"]] = (
                    (NOW - timedelta(days=1)).date().isoformat()
                )
            provider = Provider()
            result = comparison.compare(
                value, mode="shadow", provider=provider, assessment_now=NOW
            )
            with self.subTest(change=change):
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(result["decisions"][1]["shared_exclusion"], expected)

    def test_canonical_duplicates_preserve_baseline_choice(self):
        rows = [row(0), row(1, score=4)]
        rows[1]["url"] = rows[0]["url"] + "?utm_source=feed"
        rows[1]["comparison_candidate"]["canonical_url"] = rows[0]["url"]
        value = snapshot(rows)
        result = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        self.assertEqual(len(result["candidate_selected"]), 1)
        self.assertEqual(result["candidate_selected"][0]["url"], rows[1]["url"])

    def test_history_catchup_links_remain_in_both_reports(self):
        value = snapshot([row(0)])
        date = (NOW - timedelta(days=1)).date().isoformat()
        value["publication_history"] = {
            "legacy_release_count": 2,
            "report_dates": [date],
        }
        value["previously_included"] = [
            {
                "title": "Prior AI story",
                "url": "https://example.com/prior",
                "source": "Prior source",
                "published": NOW.isoformat(),
                "previous_report_date": date,
            }
        ]
        result = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        self.assertIn("https://example.com/prior", result["baseline_report"])
        self.assertIn("https://example.com/prior", result["candidate_report"])

    def test_mismatched_baseline_or_missing_capture_rejected(self):
        value = snapshot([row(0)])
        value["policies"]["frontier"]["selected"] = []
        with self.assertRaisesRegex(ValueError, "differs"):
            comparison.compare(value)
        value = snapshot([row(0)])
        del value["collection"][0]["comparison_candidate"]
        with self.assertRaisesRegex(ValueError, "Missing pre-admission"):
            comparison.compare(value)

    def test_empty_report_and_external_markdown_escaped(self):
        value = snapshot([])
        result = comparison.compare(
            value, mode="shadow", provider=Provider(), assessment_now=NOW
        )
        self.assertEqual(result["status"], "complete")
        self.assertIn("No accessible", result["candidate_report"])
        value = snapshot([row(0, title="AI | [title] <script> & " + "long " * 100)])
        result = comparison.compare(value)
        self.assertIn("\\|", comparison.render_comparison(result))
        self.assertNotIn("<script>", result["baseline_report"])

    def test_cli_writes_new_local_directory_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "capture.json"
            source.write_text(json.dumps(snapshot([row(0)])))
            output = root / "comparison"
            with patch.object(
                report, "check_url_accessible", side_effect=AssertionError("network")
            ):
                self.assertEqual(
                    comparison.main([str(source), "--output-dir", str(output)]), 0
                )
            self.assertTrue((output / "baseline.md").exists())
            self.assertTrue((output / "candidate.md").exists())
            self.assertTrue((output / "assessments.json").exists())
            self.assertEqual(
                json.loads((output / "comparison.json").read_text())["status"],
                "not_requested",
            )
            with self.assertRaises(SystemExit):
                comparison.main([str(source), "--output-dir", str(output)])


if __name__ == "__main__":
    unittest.main()
