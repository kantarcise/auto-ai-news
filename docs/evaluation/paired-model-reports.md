# Unpublished paired model reports

This implements the next comparison step in [issue #38](https://github.com/kantarcise/auto-ai-news/issues/38), using the [assessment adapter](model-assessment.md) and [content-shadow-v1 policy](model-assisted-policy.md). The daily publication workflow remains unchanged. This command writes local evaluation files and never creates or edits releases, updates publication history, or changes the production default.

## Freeze the candidate pool

Use a new evidence capture made with this version of the generator. Earlier captures lack the pre-admission baseline replay features and are rejected rather than reconstructed from truncated summaries.

```bash
python3 scripts/generate_report.py \
  --output /tmp/rules-preview.md \
  --evaluation-output /tmp/article-capture.json \
  --evaluation-article-content
```

This capture command fetches feeds, bounded article evidence and baseline selected links. When comparing production behavior, also pass the same `--publication-history` file used for that report. Omitting history explicitly means history is disabled in both arms. The capture contains bounded article text: keep it local, and do not commit or publish it without separate review.

Opt-in captures freeze the original feed-derived admission, score, star bucket and reading-time features for fresh linked candidates, including relevance rejects. Scoring a copy of each item preserves the publishing baseline; captured body text does not replace its title/summary inputs. Per-row source priority/category/publisher, editorial configuration, shared exclusions, publication URL history, selection limits and collection diagnostics remain frozen. The comparison reuses these captured features rather than rescoring truncated summaries under a later configuration.

The rules arm must reproduce the captured ordered selected URLs before a model comparison is accepted. Both arms then use the same canonical deduplication, detailed-title grouping, access checks, publisher limits and report limit. Reading times in these local reports are frozen feed estimates; the runner does not retrieve bodies for reading time. They can therefore differ from the separately enriched daily report's reading times.

## Default: offline rules replay

```bash
python3 -m scripts.compare_model_reports /tmp/article-capture.json \
  --output-dir /tmp/paired-rules
```

The output directory must be new. Default `--mode rules` uses no model, credentials or new network requests. It writes:

- `baseline.md` and `candidate.md`: unpublished reports; both use rules in this mode.
- `comparison.md`: a readable selected-URL difference table.
- `comparison.json`: decisions, shared exclusions, frozen sort keys, selection metadata, assessments, link outcomes, runtime and usage diagnostics.
- `assessments.json`: only validated assessment records used in this run; no article bodies, credentials or probabilities.
- `links.json`: frozen URL access outcomes, including any explicitly fetched supplementary checks.

Pass `--revision` to record the generator revision alongside the capture hash. The output shows `not_requested` until shadow mode is selected; that is not a successful model comparison.

## Explicit hosted shadow run

With a dedicated account-scoped Workers AI token and account ID in the environment:

```bash
python3 -m scripts.compare_model_reports /tmp/article-capture.json \
  --mode shadow --cloudflare --fetch-missing-links \
  --request-limit 20 --input-byte-limit 300000 --link-request-limit 100 \
  --output-dir /tmp/paired-content
```

`--cloudflare` explicitly enables hosted inference for cache misses. The Cloudflare client is created lazily, so complete valid caches can replay without credentials. Request/byte limits apply across the whole run, not once per article. Failed provider attempts remain diagnostic; reported usage can be unknown for failed calls. Summed token counts are reported usage, not account billing or a neuron spending cap.

`--fetch-missing-links` explicitly permits access checks for newly admitted candidates that the baseline never checked. Only needed missing outcomes are fetched, with a bounded count of URL checks; each URL is frozen once and reused by both arms. A URL check uses the generator's existing HEAD/GET behavior and timeouts, so this is not a count of individual HTTP requests. Recorded original outcomes cannot be overwritten by supplemental inputs. Without this flag or saved supplementary outcomes, a needed unchecked URL makes the model arm unavailable; it is never silently treated as inaccessible. No page text is retrieved by these access checks.

The model arm applies the reviewed policy: AI yes may recover a relevance reject; AI insufficient retains baseline admission; AI no from title/summary, feed excerpt, explicitly partial or truncated evidence retains baseline admission. Other AI no answers reject experimentally. Engineering detail changes only equal-score ordering, and a group receives preference only when every possible displayed representative qualifies. Link or publisher-cap replacements cannot borrow another article's preference. Major announcements and useful promotional stories remain eligible without engineering detail.

A model/provider/schema/budget or needed-link failure marks the whole model arm `unavailable` and writes the complete rules selection as its fallback. Partial decisions are marked unapplied and must not be evaluated as a completed model report. If the original baseline cannot be replayed, the command rejects the capture instead of inventing a baseline. Valid insufficient-evidence answers remain normal per-article fallback, not provider errors.

## Replay assessments and access outcomes

```bash
python3 -m scripts.compare_model_reports /tmp/article-capture.json \
  --mode shadow \
  --cache /tmp/paired-content/assessments.json \
  --link-outcomes /tmp/paired-content/links.json \
  --output-dir /tmp/paired-replay
```

This has no new inference or access requests. Cache lookup checks provider/model, question version/hash, full input hash (including title and provenance/limits), schema, UTC assessment/expiration times and token-count types. Hosted records expire after at most 24 hours; expired, mismatched or invalid records are ignored. Missing valid records without an explicitly enabled provider make the model arm unavailable. Duplicate exact assessment inputs reuse a validated result while it remains unexpired. Each decision references the exact assessment it used; the replay cache retains the latest result for each input. Admission and ranking are recalculated from validated answers, never cached policy outcomes, so changing policy does not reuse stale decisions. `policy_version` is recorded in every comparison.

For a bounded title-only arm, repeat the explicit shadow command with `--evidence-arm title` and a different output directory. It uses the same frozen candidate pool and policy but supplies only each headline, marked title-only. Title and content inputs have distinct cache identities. Compare both against the unchanged rules arm to distinguish richer evidence from a different admission mechanism.

## Review limits

These are unblinded development reports, not a randomized traffic experiment or a claim of improved quality. The difference table tracks selected representative URLs: changing a group's displayed representative can appear as an addition/removal without discovering a new underlying story. Group member URLs and frozen ordering are retained for inspection. Review recoveries, removals and ordering separately; sample candidates rejected by both arms using the decision records. Labels and probabilities are not human quality grades.

The opt-in evidence collector currently retrieves at most 20 unique article URLs; remaining candidates may use feed/summary/title fallbacks. A 20-request assessment budget can also be smaller than a capture's eligible pool: that run falls back rather than presenting partial evaluation as complete. Set a deliberate budget for the cohort; neither limit guarantees complete article bodies. Bounded captures, extraction failures and provider errors remain visible through provenance and diagnostics. No new inference or live-feed results are claimed by the implementation tests.

A trusted workflow integration, blinded editorial review over independent dates, agreed acceptance criteria and any production model-assisted default remain later work. Rules continue to work without credentials or GPU dependencies. Run the offline regression suite before changing the policy or comparison capture schema.
