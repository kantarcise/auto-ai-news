# Model-assisted daily reports

The daily workflow defaults to Cloudflare Clef-flash selection using the same `content-shadow-v1` policy and three questions used in the October 12–14 comparisons. The owner chose to adopt it before the planned October 18 trial end after preferring the content additions. The [October 13 feedback](evaluation/feedback-2026-10-13.md) and [October 14 feedback](evaluation/feedback-2026-10-14.md) preserve the actual judgments and their limitations; repeated articles are not independent evidence. This is an owner-approved editorial decision, not a claim of general benchmark superiority.

## What changes

The workflow first produces the existing rules report and captures best-effort article evidence before relevance filtering. It then asks Clef-flash about substantive AI subject matter, concrete AI-related engineering detail and article type. A positive AI-subject answer can recover a story rejected by the existing title/summary rules. Insufficient evidence and negatives from explicitly limited evidence retain the baseline decision. Other negative answers can remove a baseline story.

Original feed-derived scores, star buckets and selection limits are retained. Engineering detail only breaks equal-score ties under the existing conservative all-member group rule. This does not implement learned importance, semantic duplicate detection or additional questions. Dates, history, explicit event/quiet-day exclusions, canonical deduplication, attribution, link checks, grouping and publisher caps remain application checks. See the [exact policy](evaluation/model-assisted-policy.md).

The published report discloses the model, policy and limitations. Article evidence may be partial or missing; labels are provisional rather than factual verification. Model-selected report reading times use the captured feed features; supplemental evidence does not update those estimates, so an unknown reading time does not mean the model received no article text. Rules fallback preserves the ordinary generator report and its reading-time enrichment.

Production publication receipts contain the actually displayed model-selected URLs and alternate coverage, plus any URLs already published earlier on the same UTC date. They do not mistakenly record unselected baseline candidates. The existing catch-up and previous-report links remain available, and model-recovered URLs participate in tomorrow's repeat prevention.

## Configuration and rollback

The existing repository variable `CLOUDFLARE_ACCOUNT_ID` and secret `CLOUDFLARE_API_TOKEN` supply the account-scoped Workers AI credentials. Only the selection step receives the token. The daily job runs only on the default branch, checkout does not persist Git credentials, and there is no untrusted pull-request trigger. No GPU packages or new Python runtime dependencies are added.

`REPORT_SELECTION_MODE` is a repository variable:

- Unset or `model-assisted`: capture evidence and use bounded Clef-flash selection.
- `rules`: use the ordinary generator without evidence capture or any inference calls. The original rules code remains supported.
- Any other value: stop with a configuration error before generation/publication.

To roll back the next run:

```bash
gh variable set REPORT_SELECTION_MODE --body rules
```

To restore model-assisted selection:

```bash
gh variable set REPORT_SELECTION_MODE --body model-assisted
```

Changing the variable does not edit an existing release or trigger a run. No workflow dispatch, secret changes, setting changes or publication are performed by this PR. After merge, the next scheduled/default-branch manual run uses the new default unless `REPORT_SELECTION_MODE=rules` is set. Account credentials already configured for the trial are reused; successful live production integration remains unverified until that run.

## Failure behavior and usage

The Cloudflare step allows at most 100 inference attempts, 1,000,000 serialized input bytes and 100 supplemental link checks. Failed attempts consume the budget; there are no automatic retries. The client has a 30-second socket timeout, and the entire selection step is limited to five minutes.

A provider error, missing/invalid credentials, exhausted budget or invalid answer abandons all model selection changes and publishes the complete already generated rules report. The report has a prominent fallback notice, the workflow emits a warning and `daily-selection-*` stores a sanitized `status.json` with selection mode, failure code, counts and available token/runtime metrics. An unexpected comparison exception also uses that baseline without printing exception text. If the selection command crashes or hits the five-minute step timeout, the next workflow step explicitly restores and labels the rules report. No partially evaluated report is published as model-selected.

A failed baseline generation, failed test/history read, overall job cancellation/timeout or release-publication failure still stops publication. The fallback requires a successfully generated baseline; it cannot recover from a missing or failed GitHub job. GitHub's daily schedule remains 06:15 UTC and can start late. This PR does not solve scheduling delays.

Only sanitized status JSON is uploaded from the daily workflow. Captured article text, model answers and raw responses remain in runner temporary files. The prior ranking-evaluation artifact steps are replaced because an evidence capture now contains article text and must not be uploaded through the old artifact path. Provider usage and baseline/model selected counts remain visible in the replacement status artifact and logs.

The limits are per run, not a strict neuron cap or free-tier guarantee; other account usage and manual reruns share the allowance. Recent successful trial runs were well below the daily free allowance, but account analytics and invoices remain the usage source of truth. Local rules mode never needs Cloudflare credentials.

## Trial and local verification

The separate trial workflow loses its automatic schedule to avoid paying for a second daily inference run after adoption. Existing evaluation releases are preserved. Explicit manual comparisons remain possible within its configured seven-day gate; this PR does not trigger one or change the stored start date.

Local report generation remains rules-only by default:

```bash
python3 scripts/generate_report.py --output /tmp/rules-baseline.md \
  --evaluation-output /tmp/model-capture.json --evaluation-article-content
# Explicit hosted call; credentials must already be set in the environment:
python3 -m scripts.production_model_report \
  --baseline-report /tmp/rules-baseline.md --snapshot /tmp/model-capture.json \
  --output /tmp/model-daily.md --status-output /tmp/model-status.json
```

Use a publication-history capture when verifying cross-day receipts. Run normal offline tests plus Ruff lint/format checks. Tests cover recovered and removed URLs, alternate receipts, same-day history union, missing and partial provider failure, unexpected exceptions, empty reports and offline rules rollback. No live inference is required by the tests.
