# Article assessment adapter

Issue #38 now has a standard-library assessment layer for the
[candidate shadow policy](model-assisted-policy.md). This layer characterizes
articles; it does not implement admission, ranking, paired reports, persistent
caching or report-level fallback. The normal generator and daily workflow do
not import or call the adapter. No model credentials or GPU are needed to run
rules mode or the offline tests.

`scripts/model_assessment.py` defines immutable input/answer/result objects and
an `AssessmentProvider` protocol. The versioned three-question definition is
shared with future providers. `scripts/cloudflare_assessment.py` implements the
protocol for `@cf/cloudflare/clef-flash` through the
[documented typed-question REST endpoint](https://developers.cloudflare.com/workers-ai/models/clef-flash/).
All questions use choice answers, so insufficient evidence is an explicit
answer rather than a guessed threshold on a yes/no probability.

## Explicit use from Python

Run from the repository root. This example makes one hosted request when
executed; merely importing these modules makes none. `captured_evidence` is an
`article_evidence` record from an opt-in
[evaluation capture](../content-extraction.md#opt-in-evidence-before-relevance-filtering).

```python
from scripts.cloudflare_assessment import CloudflareAssessmentProvider
from scripts.model_assessment import AssessmentError, AssessmentInput

article = AssessmentInput.from_capture(title, captured_evidence)
provider = CloudflareAssessmentProvider.from_environment(request_limit=10)
try:
    assessment = provider.assess(article)
except AssessmentError as error:
    diagnostic = {"code": error.code, "http_status": error.http_status}
    # A future comparison runner must mark its model arm unavailable and
    # use the complete baseline report; it must not reinterpret this as "no".
else:
    record = assessment.to_record()
```

`from_capture` verifies the captured text hash and preserves exactly the text,
provenance, unknown/partial completeness and truncation flag. It rejects missing
or invalid capture fields. Inputs accept up to 1,000 title characters and
12,000 evidence characters. Oversized inputs fail explicitly, without silently
changing frozen evidence. The adapter also caps the complete UTF-8 request at
24,000 bytes; multibyte text can reach this cap before the character cap.

For local development, explicitly supply `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN` in the process environment, or pass credentials to the
constructor. The adapter does not discover Wrangler OAuth credentials or read
credential files. Use an account-scoped Workers AI token; Cloudflare's
[REST setup guide](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
specifies Workers AI Read and Edit permissions for custom tokens. Keep the token
out of committed configuration. No repository secret is configured by this PR.
A future workflow should expose a dedicated token only to trusted steps, with
the account ID stored separately as a variable; untrusted PR execution must not
receive the token.

## Validation, limits and records

The adapter checks the Cloudflare success envelope, expected model, exact
question IDs, answer types, option sets and selected options. Probability
values must be finite, within bounds and sum to approximately one; the selected
option must be maximal. Confidence is validated but neither it nor the
probabilities enter the common result or editorial scoring. Unknown labels,
missing/extra questions, duplicate JSON keys and malformed JSON fail explicitly.

A successful record contains the three normalized answers, provider/model,
question version/hash, input hash, text hash, provenance/limits, UTC assessment
and expiration times, elapsed latency and reported input/output token counts.
Absent token counts remain `None`, not zero. The input hash covers title and
provenance/limits as well as text. There is no calculated price or neuron total;
reported tokens are not account billing. The caller retains the original capture
for extraction diagnostics; the result does not contain copied article text.

The current question version is `article-assessment-v1`; its engineering question
explicitly requires AI-related detail, unlike the earlier experiments. Cache
identity in a future runner must include the provider/model, question version
and hash, input hash, and editorial policy version when caching policy outcomes.
The hosted model identifier does not pin weights. Records expire after at most
24 hours (configurable downward); a future cache must check expiration and must
not treat failed attempts as successful entries. This PR records expiration
metadata but performs no cache reads or writes.

Each sequential-use provider instance defaults to 20 attempted requests and
300,000 cumulative request-body bytes, including questions. Failed attempts
consume budget, and there are no automatic retries. Rejected inputs/budget
checks consume no requests. These are local request/byte limits, not a precise
token, neuron or account spending cap. A future multi-article runner must share
one provider instance rather than resetting the budget per article.

Each HTTP operation has a 30-second socket timeout (configurable up to 120
seconds), not a whole-run deadline. Responses are limited to 64,000 bytes;
redirects and compressed responses are refused. HTTP status is retained in a
sanitized error, while provider bodies and network exception messages are not
included. Do not log the request object, token or input object. Model inputs
are marked as untrusted data in the question instructions; this reduces
instruction confusion but is not a guarantee against model misclassification.

## Offline checks and remaining work

```bash
python3 -m unittest discover -s tests -p test_model_assessment.py
```

Tests mock every hosted call and cover capture identity, versioned schema,
valid insufficient-evidence answers, invalid distributions/labels/usage,
credentials, request and response bounds, request budgets, redirect refusal,
timeouts and safe diagnostics. No live compatibility or billing check is claimed.

Next, the paired comparison runner must apply the documented admission and
conservative group tie rules, freeze shared eligibility/history/link outcomes,
include baseline relevance rejects, implement report-level fallback and produce
both unpublished reports. That PR must test the policy's worked cases, including
short feed excerpts and inaccessible group representatives. Optional local
Decider can later implement the same `assess` protocol without adding CUDA/model
packages to the normal generator.
