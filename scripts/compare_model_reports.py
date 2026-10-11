"""Build unpublished rules/model reports from one frozen evidence capture."""

import argparse
import copy
import hashlib
import http.client
import json
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from scripts import generate_report as report
from scripts.cloudflare_assessment import MODEL, CloudflareAssessmentProvider
from scripts.model_assessment import (
    QUESTION_SHA256,
    QUESTION_VERSION,
    AssessmentAnswers,
    AssessmentError,
    AssessmentInput,
    AssessmentResult,
)

POLICY_VERSION = "content-shadow-v1"
TECHNICAL_TYPES = {
    "technical explanation",
    "research or model release",
    "substantive case study",
}


def aware_date(value):
    date = datetime.fromisoformat(value)
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("Comparison dates must be timezone-aware")
    return date.astimezone(UTC)


def snapshot_candidates(snapshot):
    """Replay captured scores, never recalculate relevance from truncated summaries."""
    settings = snapshot["model_comparison"]
    if settings["schema_version"] != 1:
        raise ValueError("Unsupported comparison capture")
    now = aware_date(snapshot["captured_at"])
    hours = snapshot["lookback_hours"]
    if type(hours) is not int or hours <= 0:
        raise ValueError("Invalid coverage window")
    if set(settings["selection_parameters"]) != {"report_limit", "publisher_limit"}:
        raise ValueError("Invalid selection parameters")
    for limit in settings["selection_parameters"].values():
        if type(limit) is not int or limit <= 0:
            raise ValueError("Invalid selection limits")
    history = settings["published_urls"]
    for url, date in history.items():
        if (
            report.canonicalize_url(url) != url
            or datetime.fromisoformat(date).date() >= now.date()
        ):
            raise ValueError("Invalid frozen publication history")
    candidates = []
    for index, row in enumerate(snapshot["collection"]):
        frozen = row.get("comparison_candidate")
        if frozen is None:
            if row.get("rejection_reason") in {
                "",
                "title relevance filter",
                "event listing without technical topic",
            }:
                raise ValueError("Missing pre-admission comparison candidate")
            continue
        if (
            urlsplit(row["url"]).scheme not in {"http", "https"}
            or not urlsplit(row["url"]).netloc
        ):
            raise ValueError("Invalid candidate URL")
        if any(
            type(frozen[field]) is not bool
            for field in ("baseline_admit", "event_listing")
        ):
            raise ValueError("Invalid captured admission")
        score = frozen["rank_score"]
        if (
            type(score) not in (int, float)
            or not -1_000_000 < score < 1_000_000
            or not math.isfinite(score)
        ):
            raise ValueError("Invalid captured score")
        if type(frozen["stars"]) is not int or frozen["stars"] != max(
            1, min(5, math.ceil(score))
        ):
            raise ValueError("Captured stars differ from score")
        item = report.Item(
            row["title"],
            row["url"],
            row["source"],
            frozen["source_priority"],
            published=aware_date(row["published"]),
            canonical_url=frozen["canonical_url"],
            publisher=row["publisher"],
            category=row["category"],
            coverage=frozen["coverage"],
            rank_score=score,
            stars=frozen["stars"],
            word_count=frozen["word_count"],
            read_minutes=frozen["read_minutes"],
            content_provenance=frozen["content_provenance"],
        )
        item._comparison_id = index
        if item.canonical_url != report.canonicalize_url(item.url):
            raise ValueError("Candidate canonical identity differs from capture")
        reason = report.freshness_reason(item, now, hours)
        if not reason and item.canonical_url in history:
            reason = "previously published"
        if not reason and report.is_quiet_day_roundup(item):
            reason = "quiet-day title policy"
        if not reason and frozen["event_listing"]:
            reason = "event listing without technical topic"
        candidates.append((index, row, item, reason))
    return candidates


def admission(baseline, article, answers):
    if answers.ai_subject == "yes":
        return True, "model_ai_subject_yes"
    if answers.ai_subject == "insufficient evidence":
        return baseline, "insufficient_evidence_baseline"
    if (
        article.provenance in {"title_only", "feed_summary", "feed_excerpt"}
        or article.completeness == "partial"
        or article.truncated
    ):
        return baseline, "limited_negative_baseline"
    return False, "model_ai_subject_no"


def technical(answers):
    return (
        answers.ai_subject == "yes"
        and answers.engineering_detail == "yes"
        and answers.article_type in TECHNICAL_TYPES
    )


def cache_key(article):
    identity = [
        "cloudflare",
        MODEL,
        QUESTION_VERSION,
        QUESTION_SHA256,
        article.input_sha256,
    ]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def cached_result(record, article, now):
    """Untrusted cache metadata must match the actual request and current clock."""
    try:
        values = dict(record)
        values["answers"] = AssessmentAnswers.from_mapping(values["answers"])
        result = AssessmentResult(**values)
        expected = {
            "provider": "cloudflare",
            "model": MODEL,
            "question_version": QUESTION_VERSION,
            "question_sha256": QUESTION_SHA256,
            "input_sha256": article.input_sha256,
            "text_sha256": article.text_sha256,
            "provenance": article.provenance,
            "completeness": article.completeness,
            "truncated": article.truncated,
        }
        if type(result.truncated) is not bool or any(
            getattr(result, key) != value for key, value in expected.items()
        ):
            return None
        start, end = aware_date(result.assessed_at), aware_date(result.expires_at)
        if not start <= now < end or not timedelta(0) < end - start <= timedelta(
            days=1
        ):
            return None
        if (
            type(result.latency_seconds) not in (int, float)
            or not math.isfinite(result.latency_seconds)
            or result.latency_seconds < 0
        ):
            return None
        for count in (result.input_tokens, result.output_tokens):
            if count is not None and (type(count) is not int or count < 0):
                return None
        return result
    except (TypeError, ValueError, KeyError, OverflowError, AssessmentError):
        return None


class FrozenLinks:
    def __init__(self, outcomes, *, fetch_missing=False, request_limit=100):
        self.outcomes = copy.deepcopy(outcomes)
        self.fetch_missing = fetch_missing
        self.request_limit = request_limit
        self.requests = 0
        for value in self.outcomes.values():
            if (
                not isinstance(value, dict)
                or type(value.get("accessible")) is not bool
                or not isinstance(value.get("reason"), str)
            ):
                raise ValueError("Invalid frozen link outcome")

    def __call__(self, url):
        if url not in self.outcomes:
            if not self.fetch_missing:
                raise AssessmentError("missing_frozen_link")
            if self.requests >= self.request_limit:
                raise AssessmentError("link_budget_exhausted")
            self.requests += 1
            try:
                ok, reason = report.check_url_accessible(url)
            except (OSError, ValueError, http.client.HTTPException):
                raise AssessmentError("link_check_failed") from None
            self.outcomes[url] = {
                "accessible": ok,
                "reason": reason,
                "checked_at": datetime.now(UTC).isoformat(),
            }
        result = self.outcomes[url]
        return result["accessible"], result["reason"]


def select(items, limits, links, preferences=None):
    groups = report.group_stories(report.dedupe_items(copy.deepcopy(items)))
    if preferences is not None:

        def key(group):
            members = [group, *group.related_coverage]
            score, published = max(report.item_sort_key(item) for item in members)
            return score, all(preferences[id_key(item)] for item in members), published

        groups.sort(key=key, reverse=True)
    ordering = []
    for group in groups:
        members = [group, *group.related_coverage]
        score, published = max(report.item_sort_key(item) for item in members)
        ordering.append(
            {
                "url": group.url,
                "member_urls": [item.url for item in members],
                "score": score,
                "published_tiebreak": published.isoformat(),
                "technical_preference": bool(
                    preferences is not None
                    and all(preferences[id_key(item)] for item in members)
                ),
            }
        )
    selected, diagnostics = report.filter_accessible_items(
        groups, limits["report_limit"], limits["publisher_limit"], access_checker=links
    )
    return selected, diagnostics, ordering


def id_key(item):
    # Stable through deep copies, distinct even for repeated feed occurrences.
    return item._comparison_id


def alternate_coverage(items):
    return [
        {
            "representative_url": item.url,
            "urls": [member.url for member in item.related_coverage],
        }
        for item in items
        if item.related_coverage
    ]


def report_text(items, diagnostics, snapshot, *, candidate=False, fallback=False):
    disclosure = (
        "Unpublished content-shadow-v1 comparison. Model AI-subject answers determine admission, with baseline fallback for insufficient or limited negative evidence. Original feed-derived scores and star buckets remain unchanged. Engineering detail breaks equal-score ties only when all possible group representatives qualify. The existing grouping, publisher caps and report limit apply."
        if candidate and not fallback
        else "Unpublished frozen rules replay. The original title/summary admission and heuristic scores are preserved, with existing grouping, publisher caps and report limit. No model answers affect this selection."
    )
    if fallback:
        disclosure += " Model comparison unavailable: the entire candidate report falls back to this rules report."
    history = snapshot.get("publication_history")
    previous = [
        (
            report.Item(
                row["title"],
                row["url"],
                row["source"],
                0,
                published=aware_date(row["published"]) if row["published"] else None,
            ),
            row["previous_report_date"],
        )
        for row in snapshot.get("previously_included", [])
    ]
    return report.render_report(
        items,
        diagnostics,
        aware_date(snapshot["captured_at"]),
        snapshot["lookback_hours"],
        history_enabled=history is not None,
        legacy_release_count=history.get("legacy_release_count", 0) if history else 0,
        previous_report_dates=history.get("report_dates", []) if history else None,
        previously_included=previous if history is not None else None,
        selection_disclosure=disclosure,
    )


def compare(
    snapshot,
    *,
    mode="rules",
    provider=None,
    cache=None,
    assessment_now=None,
    fetch_missing_links=False,
    link_request_limit=100,
    evidence_arm="content",
    frozen_links=None,
):
    if mode not in {"rules", "shadow"} or evidence_arm not in {"content", "title"}:
        raise ValueError("Invalid comparison mode or evidence arm")
    if type(link_request_limit) is not int or link_request_limit < 1:
        raise ValueError("Link request limit must be positive")
    now = assessment_now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Assessment clock must be timezone-aware")
    started = time.monotonic()
    candidates = snapshot_candidates(snapshot)
    limits = snapshot["model_comparison"]["selection_parameters"]
    outcomes = copy.deepcopy(snapshot["link_outcomes"])
    if frozen_links is not None:
        if not isinstance(frozen_links, dict):
            raise TypeError("Frozen links must be a mapping")
        allowed_urls = {item.url for _, _, item, _ in candidates}
        for url, outcome in frozen_links.items():
            if url not in allowed_urls:
                continue
            if url in outcomes and outcome != outcomes[url]:
                raise ValueError("Frozen link outcome conflicts with original capture")
            outcomes[url] = outcome
    links = FrozenLinks(
        outcomes,
        fetch_missing=fetch_missing_links,
        request_limit=link_request_limit,
    )
    baseline_items = [
        item
        for _, row, item, reason in candidates
        if not reason and row["comparison_candidate"]["baseline_admit"]
    ]
    # A missing baseline outcome means this capture cannot replay its own report.
    baseline, baseline_diagnostics, baseline_ordering = select(
        baseline_items, limits, links
    )
    expected = snapshot["policies"]["frontier"]["selected"]
    if [item.url for item in baseline] != [row["url"] for row in expected]:
        raise ValueError("Rules selection differs from captured baseline")
    captured_alternates = snapshot["policies"]["frontier"].get("alternate_coverage")
    baseline_alternates = alternate_coverage(baseline)
    if captured_alternates is not None and baseline_alternates != captured_alternates:
        raise ValueError("Rules alternate coverage differs from capture")
    source_diagnostics = [
        tuple(row) for row in snapshot["model_comparison"]["collection_diagnostics"]
    ]
    diagnostics = source_diagnostics + baseline_diagnostics
    baseline_report = report_text(baseline, diagnostics, snapshot)
    input_cache = {} if cache is None else cache
    if not isinstance(input_cache, dict):
        raise TypeError("Cache must be a record mapping")
    records = {}
    assessments = {}
    attempted_records = []
    decisions = []
    admitted = []
    preferences = {}
    failure = None
    if mode == "shadow":
        try:
            for index, row, item, reason in candidates:
                decision = {
                    "id": index,
                    **report.evaluation_metadata(item),
                    "baseline_admit": row["comparison_candidate"]["baseline_admit"],
                    "shared_exclusion": reason,
                }
                decisions.append(decision)
                if reason:
                    decision.update(candidate_admit=False, reason="shared_exclusion")
                    continue
                if evidence_arm == "title":
                    article = AssessmentInput(
                        item.title, item.title, "title_only", "unknown", False
                    )
                else:
                    article = AssessmentInput.from_capture(
                        item.title, row["article_evidence"]
                    )
                identity = cache_key(article)
                cache_now = now + timedelta(seconds=time.monotonic() - started)
                result = cached_result(
                    records.get(identity) or input_cache.get(identity),
                    article,
                    cache_now,
                )
                reused = result is not None
                if result is None:
                    if provider is None:
                        raise AssessmentError("missing_assessment")
                    attempted_records.append(None)
                    result = provider.assess(article)
                    # Real requests finish after the runner's initial clock.
                    if (
                        cached_result(
                            result.to_record(),
                            article,
                            max(cache_now, datetime.now(UTC)),
                        )
                        is None
                    ):
                        raise AssessmentError("invalid_assessment_record")
                    attempted_records[-1] = result.to_record()
                records[identity] = result.to_record()
                assessments[identity] = result.to_record()
                allow, why = admission(
                    decision["baseline_admit"], article, result.answers
                )
                decision.update(
                    candidate_admit=allow,
                    reason=why,
                    assessment_key=identity,
                    cache_hit=reused,
                    score=item.rank_score,
                    technical_preference=technical(result.answers),
                )
                preferences[id_key(item)] = technical(result.answers)
                if allow:
                    admitted.append(item)
            selected, candidate_diagnostics, candidate_ordering = select(
                admitted, limits, links, preferences
            )
        except AssessmentError as error:
            failure = {"code": error.code, "http_status": error.http_status}
            selected = copy.deepcopy(baseline)
            candidate_diagnostics = baseline_diagnostics
            candidate_ordering = baseline_ordering
            for index, row, item, reason in candidates[len(decisions) :]:
                decisions.append(
                    {
                        "id": index,
                        **report.evaluation_metadata(item),
                        "baseline_admit": row["comparison_candidate"]["baseline_admit"],
                        "shared_exclusion": reason,
                        "candidate_admit": None,
                        "reason": "model_arm_unavailable",
                    }
                )
    else:
        selected = copy.deepcopy(baseline)
        candidate_diagnostics = baseline_diagnostics
        candidate_ordering = baseline_ordering
    for decision in decisions:
        if "candidate_admit" not in decision:
            decision.update(candidate_admit=None, reason="model_arm_unavailable")
        decision["applied"] = failure is None
    status = (
        "unavailable"
        if failure
        else ("complete" if mode == "shadow" else "not_requested")
    )
    before = {item.url: position for position, item in enumerate(baseline, 1)}
    after = {item.url: position for position, item in enumerate(selected, 1)}
    differences = []
    for url in dict.fromkeys([*before, *after]):
        change = "unchanged"
        if status == "complete":
            change = (
                "added"
                if url not in before
                else "removed"
                if url not in after
                else "moved"
                if before[url] != after[url]
                else "unchanged"
            )
        differences.append(
            {
                "url": url,
                "baseline_position": before.get(url),
                "candidate_position": after.get(url),
                "change": change,
            }
        )
    return {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        "mode": mode,
        "evidence_arm": evidence_arm,
        "status": status,
        "failure": failure,
        "captured_at": snapshot["captured_at"],
        "assessment_at": now.isoformat(),
        "baseline_selected": [report.evaluation_metadata(item) for item in baseline],
        "candidate_selected": [report.evaluation_metadata(item) for item in selected],
        "alternate_coverage": {
            "baseline": baseline_alternates,
            "candidate": alternate_coverage(selected),
        },
        "differences": differences,
        "ordering": {"baseline": baseline_ordering, "candidate": candidate_ordering},
        "decisions": decisions,
        "shared_exclusions": [
            {
                key: row.get(key)
                for key in ("title", "url", "source", "published", "rejection_reason")
            }
            for row in snapshot["collection"]
            if "comparison_candidate" not in row
        ],
        "runtime_seconds": round(time.monotonic() - started, 6),
        "assessments": assessments,
        "cache": records,
        "link_outcomes": links.outcomes,
        "new_link_requests": links.requests,
        "usage": {
            "new_assessment_attempts": len(attempted_records),
            "reported_input_tokens": sum(
                record["input_tokens"] or 0
                for record in attempted_records
                if record is not None
            ),
            "reported_output_tokens": sum(
                record["output_tokens"] or 0
                for record in attempted_records
                if record is not None
            ),
            "unknown_input_usage_count": sum(
                record is None or record["input_tokens"] is None
                for record in attempted_records
            ),
            "unknown_output_usage_count": sum(
                record is None or record["output_tokens"] is None
                for record in attempted_records
            ),
        },
        "baseline_report": baseline_report,
        "candidate_report": report_text(
            selected,
            source_diagnostics + candidate_diagnostics,
            snapshot,
            candidate=mode == "shadow",
            fallback=failure is not None,
        ),
    }


def render_comparison(result):
    lines = [
        "# Unpublished paired report comparison",
        "",
        f"Status: {result['status']}; evidence arm: {result['evidence_arm']}; policy: {POLICY_VERSION}.",
        "",
        "Both arms share the frozen clock, history, scores and downstream constraints. This is a development comparison, not evidence of improved editorial quality.",
        "",
    ]
    if result["failure"]:
        lines += [
            f"Model arm unavailable: {result['failure']['code']}. Candidate report uses the full baseline fallback; partial decisions are diagnostic only.",
            "",
        ]
    lines += [
        "| Article | Rules position | Candidate position | Change |",
        "| --- | --- | --- | --- |",
    ]
    titles = {
        row["url"]: row["title"]
        for row in result["baseline_selected"] + result["candidate_selected"]
    }
    for row in result["differences"]:
        lines.append(
            f"| {report.markdown_link(titles[row['url']], row['url'])} | {row['baseline_position'] or '—'} | {row['candidate_position'] or '—'} | {row['change']} |"
        )
    lines += [
        "",
        "Review additions, removals and moved stories separately. Inspect candidates rejected by both arms in the JSON decisions too. Valid insufficient evidence is not a negative label; incomplete model arms must not be scored as completed comparisons.",
        "",
    ]
    return "\n".join(lines)


class LazyCloudflare:
    def __init__(self, request_limit, input_byte_limit):
        self.client = None
        self.request_limit = request_limit
        self.input_byte_limit = input_byte_limit

    def assess(self, article):
        if self.client is None:
            self.client = CloudflareAssessmentProvider.from_environment(
                request_limit=self.request_limit, input_byte_limit=self.input_byte_limit
            )
        return self.client.assess(article)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("rules", "shadow"), default="rules")
    parser.add_argument(
        "--evidence-arm", choices=("content", "title"), default="content"
    )
    parser.add_argument("--cache", type=Path)
    parser.add_argument(
        "--link-outcomes",
        type=Path,
        help="Replay supplemental links.json outcomes without rechecking URLs.",
    )
    parser.add_argument("--revision", default="")
    parser.add_argument(
        "--cloudflare",
        action="store_true",
        help="Explicitly allow hosted inference for cache misses.",
    )
    parser.add_argument("--fetch-missing-links", action="store_true")
    parser.add_argument("--request-limit", type=int, default=20)
    parser.add_argument("--input-byte-limit", type=int, default=300_000)
    parser.add_argument("--link-request-limit", type=int, default=100)
    args = parser.parse_args(argv)
    if args.cloudflare and args.mode != "shadow":
        parser.error("--cloudflare requires --mode shadow")
    if min(args.request_limit, args.input_byte_limit, args.link_request_limit) < 1:
        parser.error("Request and byte limits must be positive")
    # New directory only: never overwrite captures, cached inputs or prior reports.
    if args.output_dir.exists():
        parser.error("--output-dir must be a new directory")
    try:
        raw = args.snapshot.read_bytes()
        cache = json.loads(args.cache.read_text()) if args.cache else {}
        if not isinstance(cache, dict):
            raise TypeError("Cache must be a record mapping")
        supplemental = (
            json.loads(args.link_outcomes.read_text()) if args.link_outcomes else None
        )
        result = compare(
            json.loads(raw),
            mode=args.mode,
            provider=LazyCloudflare(args.request_limit, args.input_byte_limit)
            if args.cloudflare
            else None,
            cache=cache,
            fetch_missing_links=args.fetch_missing_links,
            link_request_limit=args.link_request_limit,
            evidence_arm=args.evidence_arm,
            frozen_links=supplemental,
        )
    except (ValueError, TypeError, KeyError, OSError, AssessmentError):
        parser.error(
            "Cannot replay inputs; use a current --evaluation-article-content capture with frozen link outcomes."
        )
    result["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    result["revision"] = args.revision
    if args.link_outcomes:
        result["supplemental_links_sha256"] = hashlib.sha256(
            args.link_outcomes.read_bytes()
        ).hexdigest()
    args.output_dir.mkdir(parents=True)
    for name in ("baseline", "candidate"):
        (args.output_dir / f"{name}.md").write_text(
            result.pop(f"{name}_report"), encoding="utf-8"
        )
    (args.output_dir / "comparison.md").write_text(
        render_comparison(result), encoding="utf-8"
    )
    (args.output_dir / "assessments.json").write_text(
        json.dumps(result.pop("cache"), indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "links.json").write_text(
        json.dumps(result["link_outcomes"], indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "comparison.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
