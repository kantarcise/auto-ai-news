# Capture a broader review pool

Issue #12 needs more than feedback on selected articles. The optional evaluation export saves attributed metadata for every parsed entry, including entries rejected by freshness, missing-link, quiet-day, or title-relevance checks. It uses the same run and UTC clock as the report; enabling it changes no selection rules and makes no extra network requests.

For a local collection run, keep both outputs outside the repository:

```bash
python3 scripts/generate_report.py --output /tmp/daily-ai-news.md --evaluation-output /tmp/ai-news-snapshot.json --no-article-bodies
python3 -m scripts.review_candidates prepare /tmp/ai-news-snapshot.json --output /tmp/ai-news-review.json
python3 -m scripts.review_candidates evaluate /tmp/ai-news-snapshot.json /tmp/ai-news-review.json
```

The first command uses live feeds and ordinary link checks. The last two commands are offline. Body retrieval can be enabled by omitting `--no-article-bodies`; the snapshot is written before that optional enrichment, and contains no article text or body-extraction outcomes. No workflow or release publication is triggered by these local commands. Keep generated reports and unreviewed local captures out of commits.

## Snapshot contents

| Field | Meaning |
| --- | --- |
| `schema_version` | Version 1 of this broader capture format. |
| `captured_at`, `lookback_hours` | The timezone-aware UTC evaluation clock and coverage window. |
| `candidate_scope` | Explicitly identifies this review pool as all parsed linked entries, including pre-ranking rejects. |
| `collection` | Every parsed occurrence, with title, resolved original link, source/publisher/category, date or null, and first rejection reason. Empty reason means it passed the collection gates; it may still lose deduplication, grouping, ranking, caps or link checks. |
| `policies.frontier.candidates` | One review row per exact resolved nonempty URL from the whole collection, using the first occurrence's metadata. This is broader than the eligible ranking pool in the October 3 comparison. |
| `policies.frontier.selected` | Actual selected story representatives. |
| `policies.frontier.alternate_coverage` | Accessible attributed alternate URLs attached to selected representatives. |
| `story_groups` | Eligible groups after canonical deduplication, frozen before selection/fallback mutates membership. The first URL is the preferred representative at that stage. |
| `link_outcomes` | Only checks actually performed: accessible flag and failure reason. An absent URL was not checked, rather than found inaccessible. |
| `diagnostics` | Source failures and collection/selection diagnostics, including disabled sources, missing feed inputs, publisher caps and report limits. |

Titles and attribution are external data. JSON serialization preserves their text and original resolved links; no summary, full feed content, scraped article body or credential is intentionally exported. An entry with no link remains in `collection` but cannot receive a URL-based review ID. Duplicate URL occurrences stay in `collection`, while the review sheet contains one row per exact URL. Canonical URL variants may have separate review rows; assign human story IDs to connect them. Metadata from two source channels may differ for the same URL; inspect the collection records when that matters.

## Review and interpretation

Prepare the blank sheet before inspecting scores/outcomes, following the [rubric](editorial-rubric.md). The sheet omits gate reasons and selections; this does not undo familiarity with previously reviewed articles. Include-worthy labels express editorial value separately from the operational 72-hour window. A valuable stale article can receive a positive label without making it eligible for the current report. Unavailable evidence remains unsure or unreviewed.

The evaluator echoes `candidate_scope`. Recall now covers reviewed positives anywhere in this broader captured pool, including operationally ineligible rows; do not compare it directly to October 3's eligible-candidate recall. Use `collection` to investigate whether a miss came from relevance, freshness, deduplication or later selection. Precision counts selected representatives. The current evaluator does not credit alternate links or compute story-level recall; grouped valuable alternate coverage can look like an article-level miss. Label coverage and these limitations must accompany any reported metrics. Null labels still produce undefined quality scores, not evidence of poor quality.

This export preserves observed metadata and outcomes, not raw feed responses, summaries, ranking features or complete source configuration. It supports reproducible offline labeling against the saved selection, but cannot rerun the ranking pipeline or evaluate alternative algorithms from this file alone. The older `evaluate_selection` replay command expects the October 3 comparison format and must not be used on these exports. Candidate generation misses from inaccessible/disabled/unconfigured sources remain source-level diagnostics; absent articles cannot be reviewed from this snapshot.

Next, collect several dated pools with representative publishers, regions and modalities; agree on explicit labels and keep shared stories together in chronological evaluation splits. Set ranking acceptance targets from those results. No new weights, dependency, content-length exclusion or unconditional practitioner bonus is introduced here.
