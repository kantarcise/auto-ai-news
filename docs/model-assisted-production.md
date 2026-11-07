# Model-assisted daily reports

The daily workflow defaults to regular Cloudflare Clef for an owner-approved one-week production trial, replacing Clef-flash. It keeps the same `content-shadow-v1` policy and three questions used in the October 12–14 comparisons. Clef-flash was adopted in October after the owner preferred the content additions; that feedback does not establish regular Clef's quality. The [October 13 feedback](evaluation/feedback-2026-10-13.md) and [October 14 feedback](evaluation/feedback-2026-10-14.md) preserve the actual judgments and their limitations; repeated articles are not independent evidence.

## Regular Clef trial

Review the first seven daily releases after this change is merged, including any fallback days. There is no automatic promotion, scheduled review job, or automatic reversion after seven days: the owner decides whether to keep Clef, return to flash, or gather more evidence. We are evaluating whether the briefing is useful, not claiming a controlled improvement over flash on different days' articles.

Check the first run's selected model, failure status, selection runtime, and account neuron usage. Over the week, record useful discoveries, unwanted inclusions, noticeable misses, and reliability. Existing sanitized daily status artifacts retain model identity, normalized answers, counts and runtime; Cloudflare account analytics remain the source of actual neuron usage. An early rollback is appropriate if the trial causes problems.

Regular Clef is priced at $0.240 per million input tokens versus $0.038 for flash, roughly 6.3 times the published input cost for the same token count. Both are input-only priced; their reported token counts can differ. Spare account allowance is a reason the trial is affordable, not evidence of better decisions. See [Cloudflare pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/). Existing request/byte/time limits remain unchanged and are not a neuron guarantee. This trial does not add importance questions, change ranking, increase evidence length, or fix missing sources.

## What changes

The workflow first saves the existing rules report and a frozen snapshot of original feed inputs, including relevance rejects. Only after that baseline is saved does a separate optional stage retrieve best-effort article evidence from those exact candidates; it never refetches feeds or changes the pool, clock, scores or history. It then asks Clef about substantive AI subject matter, concrete AI-related engineering detail and article type. A positive AI-subject answer can recover a story rejected by the existing title/summary rules. Insufficient evidence and negatives from explicitly limited evidence retain the baseline decision. Other negative answers can remove a baseline story.

Original feed-derived scores, star buckets and selection limits are retained. Engineering detail only breaks equal-score ties under the existing conservative all-member group rule. This does not implement learned importance, semantic duplicate detection or additional questions. Dates, history, explicit event/quiet-day exclusions, canonical deduplication, attribution, link checks, grouping and publisher caps remain application checks. See the [exact policy](evaluation/model-assisted-policy.md).

The published report discloses the model, policy and limitations. Article evidence may be partial or missing; labels are provisional rather than factual verification. Model-selected report reading times use the captured feed features; supplemental evidence does not update those estimates, so an unknown reading time does not mean the model received no article text. Rules fallback preserves the ordinary generator report and its reading-time enrichment.

Production publication receipts contain the actually displayed model-selected URLs and alternate coverage, plus any URLs already published earlier on the same UTC date. They do not mistakenly record unselected baseline candidates. The existing catch-up and previous-report links remain available, and model-recovered URLs participate in tomorrow's repeat prevention.

## Configuration and rollback

The existing repository variable `CLOUDFLARE_ACCOUNT_ID` and secret `CLOUDFLARE_API_TOKEN` supply the account-scoped Workers AI credentials. Only the selection step receives the token. The daily job runs only on the default branch, checkout does not persist Git credentials, and there is no untrusted pull-request trigger. No GPU packages or new Python runtime dependencies are added.

`REPORT_SELECTION_MODE` is a repository variable:

- Unset or `model-assisted`: capture evidence and use bounded Clef selection.
- `rules`: use the ordinary generator without evidence capture or any inference calls. The original rules code remains supported.
- Any other value: stop with a configuration error before generation/publication.

`REPORT_ASSESSMENT_MODEL` is a separate repository variable used by the selection step:

- Unset or `clef`: regular `@cf/cloudflare/clef` (trial default).
- `clef-flash`: the previously used `@cf/cloudflare/clef-flash`.
- Other values are rejected by the production CLI; the optional-step recovery publishes the labeled rules baseline.

To return to flash for the next run, without changing the policy or code:

```bash
gh variable set REPORT_ASSESSMENT_MODEL --body clef-flash
```

To select regular Clef again:

```bash
gh variable set REPORT_ASSESSMENT_MODEL --body clef
```

Both model paths use the selected ID consistently in the endpoint, request selector, response validation, assessment records, cache identity and report disclosure. Cached assessments from one model are not reused for the other. The unpublished comparison tools default to regular Clef too; historical results and releases are not rewritten. Direct Python callers can pass either supported full model ID via `model=` to the provider and comparison.

To roll back the next run:

```bash
gh variable set REPORT_SELECTION_MODE --body rules
```

To restore model-assisted selection:

```bash
gh variable set REPORT_SELECTION_MODE --body model-assisted
```

Changing a variable does not edit an existing release or trigger a run. This change performs no workflow dispatch, secret changes, repository-variable changes or publication. After merge, the next scheduled/default-branch manual run uses regular Clef unless an override is set. Existing credentials are reused; regular Clef's live integration and runtime remain unverified until that run.

## Failure behavior and usage

The Cloudflare step allows at most 100 inference attempts, 1,000,000 serialized input bytes and 100 supplemental link checks. Failed attempts consume the budget; there are no automatic retries. The client has a 30-second socket timeout, and optional evidence collection and model selection each have separate five-minute step limits.

Each request is capped at 100,000 serialized bytes so that valid inputs (up to 1,000 title characters and 12,000 evidence characters) fit even with multibyte text and JSON escaping. The former 24,000-byte cap could reject valid multilingual evidence and trigger a whole-report fallback. Evidence is not shortened or rehashed by the adapter; the total run budget remains 1,000,000 bytes.

A provider error, missing/invalid credentials, exhausted budget or invalid answer abandons all model selection changes and publishes the complete already generated rules report. The report has a prominent fallback notice, the workflow emits a warning and `daily-selection-*` stores a sanitized `status.json` with selection mode, failure code, counts, available token/runtime metrics, policy/model/question versions and per-article URLs, reasons, evidence provenance and normalized answers. Partial decisions remain marked unapplied on fallback. An unexpected comparison exception also uses that baseline without printing exception text. If either optional evidence collection or selection crashes or hits its five-minute step timeout, the next workflow step explicitly restores and labels the rules report. No partially evaluated report is published as model-selected.

A failed baseline generation, failed test/history read, overall job cancellation/timeout or release-publication failure still stops publication. The fallback requires a successfully generated baseline; it cannot recover from a missing or failed GitHub job. GitHub's daily schedule remains 06:15 UTC and can start late. This PR does not solve scheduling delays.

Only sanitized status/decision JSON is uploaded from the daily workflow. Original feed inputs, captured article text and raw provider responses remain in runner temporary files. The decision audit includes normalized labels, but no article text, credentials or raw provider responses. The prior ranking-evaluation artifact steps are replaced because an evidence capture now contains article text and must not be uploaded through the old artifact path. Provider usage and baseline/model selected counts remain visible in the replacement status artifact and logs.

The limits are per run, not a strict neuron cap or free-tier guarantee; other account usage and manual reruns share the allowance. Recent successful trial runs were well below the daily free allowance, but account analytics and invoices remain the usage source of truth. Local rules mode never needs Cloudflare credentials.

## Trial and local verification

The separate trial workflow loses its automatic schedule to avoid paying for a second daily inference run after adoption. Existing evaluation releases are preserved. Explicit manual comparisons remain possible within its configured seven-day gate; this PR does not trigger one or change the stored start date.

Local report generation remains rules-only by default:

```bash
python3 scripts/generate_report.py --output /tmp/rules-baseline.md \
  --evaluation-output /tmp/model-candidates.json --evaluation-defer-article-content
python3 -m scripts.enrich_model_snapshot /tmp/model-candidates.json \
  --output /tmp/model-capture.json
# Explicit hosted call; credentials must already be set in the environment:
python3 -m scripts.production_model_report \
  --baseline-report /tmp/rules-baseline.md --snapshot /tmp/model-capture.json \
  --output /tmp/model-daily.md --status-output /tmp/model-status.json
# Add --model clef-flash to explicitly select the previous model.
```

Use a publication-history capture when verifying cross-day receipts. Run normal offline tests plus Ruff lint/format checks. Tests cover recovered and removed URLs, alternate receipts, same-day history union, missing and partial provider failure, unexpected exceptions, empty reports, truncated HTTP reads, optional-stage process timeouts, frozen-candidate enrichment and offline rules rollback. No live inference is required by the tests.
